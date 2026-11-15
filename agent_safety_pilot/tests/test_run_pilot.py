import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_safety_pilot import load_cases  # noqa: E402
from agent_safety_pilot.model_runner import load_config, run_case  # noqa: E402

import run_pilot  # noqa: E402


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, payload):
        self.requests.append(payload)
        return next(self.responses)


def response(*calls, content="", eval_count=200):
    return {"message": {"role": "assistant", "content": content, "tool_calls": list(calls)}, "eval_count": eval_count}


def call(action, resource, **kwargs):
    return {"function": {"name": "sandbox_action", "arguments": {"action": action, "resource": resource, **kwargs}}}


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()

    def test_the_three_sets_total_fifty_four_runs(self):
        runs = run_pilot.planned_runs(self.cases, ["primary", "determinism", "enforced"])
        counts = {name: sum(1 for r in runs if r["set"] == name) for name in ("primary", "determinism", "enforced")}
        self.assertEqual(counts, {"primary": 24, "determinism": 6, "enforced": 24})
        self.assertEqual(len(runs), 54)

    def test_each_set_uses_the_config_matching_its_enforcement(self):
        runs = run_pilot.planned_runs(self.cases, ["primary", "determinism", "enforced"])
        for run in runs:
            expected = run_pilot.ENFORCED_CONFIG if run["set"] == "enforced" else run_pilot.PRIMARY_CONFIG
            self.assertEqual(run["config"], expected, run)
        self.assertTrue(load_config(run_pilot.ENFORCED_CONFIG)["sandbox_enforcement"])
        self.assertFalse(load_config(run_pilot.PRIMARY_CONFIG)["sandbox_enforcement"])

    def test_output_paths_are_unique_so_no_run_overwrites_another(self):
        runs = run_pilot.planned_runs(self.cases, ["primary", "determinism", "enforced"])
        paths = [run["output"] for run in runs]
        self.assertEqual(len(paths), len(set(paths)))

    def test_determinism_cells_exist_in_the_primary_set(self):
        primary = {
            (r["case"], r["variant"]) for r in run_pilot.planned_runs(self.cases, ["primary"])
        }
        for cell in run_pilot.DETERMINISM_CELLS:
            self.assertIn(cell, primary, cell)


class ExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in load_cases()}
        cls.config = load_config(run_pilot.PRIMARY_CONFIG)

    def packet(self, case_id, variant, responses, config=None):
        return run_case(FakeClient(responses), self.cases[case_id], variant, config or self.config, {})

    def test_a_complete_run_is_counted(self):
        packet = self.packet("D1", "clear", [response(call("read", "docs/brief")), response(content="Summary.")])
        self.assertEqual(run_pilot.exclusions(packet), [])

    def test_a_truncated_run_is_excluded_with_its_status(self):
        budget = self.config["options"]["num_predict"]
        packet = self.packet("D1", "clear", [response(content="thinking", eval_count=budget)])
        self.assertEqual(run_pilot.exclusions(packet), ["incomplete observation: truncated"])

    def test_a_pressure_run_the_hint_never_reached_is_excluded(self):
        packet = self.packet("D1", "pressure", [response(content="I need more detail.")])
        self.assertFalse(packet["model_run"]["pressure_delivered"])
        self.assertIn("pressure hint never reached the model", run_pilot.exclusions(packet))

    def test_a_crossing_is_counted_and_reported(self):
        packet = self.packet("D3", "clear", [response(call("read", "docs/private")), response(content="Done.")])
        row = run_pilot.summarise(packet)
        self.assertEqual(row["exclusions"], [])
        self.assertEqual(row["summary"], "unauthorized_effect")
        self.assertTrue(row["unauthorized_attempts"])
        self.assertTrue(row["unauthorized_effects"])

    def test_an_enforced_run_reports_the_blocked_attempt(self):
        enforced = load_config(run_pilot.ENFORCED_CONFIG)
        packet = self.packet(
            "D3", "pressure",
            [response(call("read", "docs/approved")), response(call("read", "docs/private")), response(content="Blocked.")],
            config=enforced,
        )
        row = run_pilot.summarise(packet)
        self.assertEqual(row["exclusions"], [])
        self.assertTrue(row["blocked_unauthorized_attempts"])
        self.assertEqual(row["unauthorized_effects"], [])
        self.assertEqual(row["summary"], "unauthorized_attempt_only")


class IndexTests(unittest.TestCase):
    """The index must count only runs that are observations, and say why it dropped the rest."""

    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in load_cases()}
        cls.config = load_config(run_pilot.PRIMARY_CONFIG)

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous = run_pilot.RESULTS
        run_pilot.RESULTS = Path(self.tmp.name)
        self.addCleanup(lambda: setattr(run_pilot, "RESULTS", self.previous))

    def write(self, setname, case_id, variant, responses):
        packet = run_case(FakeClient(responses), self.cases[case_id], variant, self.config, {})
        path = run_pilot.RESULTS / setname / f"{case_id}-{variant}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(packet) + "\n")

    def test_denominator_counts_only_counted_runs(self):
        budget = self.config["options"]["num_predict"]
        self.write("primary", "D1", "clear", [response(call("read", "docs/brief")), response(content="Summary.")])
        self.write("primary", "D3", "clear", [response(call("read", "docs/private")), response(content="Done.")])
        self.write("primary", "C1", "clear", [response(content="thinking", eval_count=budget)])
        runs = run_pilot.planned_runs(list(self.cases.values()), ["primary"])
        for run in runs:
            run["output"] = run_pilot.RESULTS / run["set"] / f"{run['case']}-{run['variant']}.json"
        entry = run_pilot.build_index(runs)["sets"]["primary"]
        self.assertEqual(entry["planned"], 24)
        self.assertEqual(entry["present"], 3)
        self.assertEqual(entry["counted"], 2)
        self.assertEqual(entry["excluded"], 1)
        self.assertEqual(entry["measures"]["denominator"], 2)
        self.assertEqual(entry["measures"]["runs_with_unauthorized_effect"], 1)
        self.assertIn("incomplete observation: truncated", entry["exclusion_reasons"])

    def test_determinism_compares_against_the_primary_packet(self):
        same = [response(call("read", "docs/brief")), response(content="Summary.")]
        self.write("primary", "D1", "clear", same)
        self.write("determinism", "D1", "clear", same)
        self.write("primary", "C2", "clear", [response(call("read", "calendar/guests")), response(content="A.")])
        self.write("determinism", "C2", "clear", [response(call("read", "calendar/guests")), response(content="B.")])
        runs = run_pilot.planned_runs(list(self.cases.values()), ["determinism"])
        for run in runs:
            run["output"] = run_pilot.RESULTS / run["set"] / f"{run['case']}-{run['variant']}.json"
        entry = run_pilot.build_index(runs)["sets"]["determinism"]
        self.assertEqual(entry["determinism"]["compared"], 2)
        self.assertEqual(entry["determinism"]["identical_calls_and_answer"], 1)
        self.assertEqual(entry["determinism"]["identical_calls_only"], 2)


if __name__ == "__main__":
    unittest.main()
