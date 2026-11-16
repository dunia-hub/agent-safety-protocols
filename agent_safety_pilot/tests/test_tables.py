import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_safety_pilot import load_cases  # noqa: E402
from agent_safety_pilot.model_runner import load_config, run_case  # noqa: E402

import make_demonstrations  # noqa: E402
import make_tables  # noqa: E402
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


class TableTests(unittest.TestCase):
    def test_a_table_renders_a_header_rule_and_rows(self):
        out = make_tables.table(["A", "B"], [[1, 2], [3, 4]])
        self.assertEqual(out.splitlines()[0], "| A | B |")
        self.assertEqual(out.splitlines()[1], "| --- | --- |")
        self.assertEqual(out.splitlines()[2], "| 1 | 2 |")

    def test_an_empty_table_says_so_rather_than_rendering_a_header(self):
        self.assertIn("No runs collected", make_tables.table(["A"], []))

    def test_every_run_status_the_runner_can_produce_has_a_row(self):
        from agent_safety_pilot import model_runner as mr
        statuses = {mr.TRUNCATED, mr.UNPARSED_TOOL_CALL_TEXT, mr.TRANSPORT_ERROR, mr.TURN_LIMIT, mr.TOOL_LIMIT}
        self.assertEqual(statuses, set(make_tables.FAILURE_MODES))


class DemonstrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in load_cases()}
        cls.config = load_config(run_pilot.PRIMARY_CONFIG)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous = make_tables.ROOT
        make_tables.ROOT = Path(self.tmp.name)
        self.addCleanup(lambda: setattr(make_tables, "ROOT", self.previous))

    def write_demo(self, name, responses, marked=True):
        packet = run_case(FakeClient(responses), self.cases["D1"], "clear", self.config, {})
        if marked:
            packet["demonstration"] = {"name": name, "not_pilot_data": True}
        path = make_tables.ROOT / "results" / "demonstrations" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(packet) + "\n")

    def test_a_marked_demonstration_is_found_by_its_status(self):
        budget = self.config["options"]["num_predict"]
        self.write_demo("truncated", [response(content="thinking", eval_count=budget)])
        self.assertIn("truncated", make_tables.demonstrations())

    def test_an_unmarked_packet_is_not_treated_as_a_demonstration(self):
        budget = self.config["options"]["num_predict"]
        self.write_demo("truncated", [response(content="thinking", eval_count=budget)], marked=False)
        self.assertEqual(make_tables.demonstrations(), {})

    def test_a_prose_tool_call_demonstration_executes_nothing(self):
        text = '{"name": "sandbox_action", "arguments": {"action": "read", "resource": "docs/restricted"}}'
        self.write_demo("unparsed-tool-call-text", [response(content=text)])
        found = make_tables.demonstrations()
        self.assertIn("unparsed_tool_call_text", found)
        packet = json.loads((make_tables.ROOT / found["unparsed_tool_call_text"]).read_text())
        self.assertEqual(packet["model_run"]["tool_calls"], 0)
        self.assertFalse(packet["oracle"]["observation_complete"])

    def test_each_planned_demonstration_names_a_config_that_exists(self):
        for demo in make_demonstrations.DEMONSTRATIONS:
            self.assertTrue(demo["config"].exists(), demo["config"])
            config = load_config(demo["config"])
            self.assertEqual(config["endpoint"], "http://127.0.0.1:11434")

    def test_the_truncation_demonstration_sets_a_budget_too_small_to_reach_a_call(self):
        demo = next(d for d in make_demonstrations.DEMONSTRATIONS if d["name"] == "truncated")
        self.assertLess(load_config(demo["config"])["options"]["num_predict"], 128)

    def test_demonstrations_have_distinct_names_and_known_statuses(self):
        names = [d["name"] for d in make_demonstrations.DEMONSTRATIONS]
        self.assertEqual(len(names), len(set(names)))
        for demo in make_demonstrations.DEMONSTRATIONS:
            self.assertIn(demo["intended_status"], make_tables.FAILURE_MODES)

    def test_more_than_one_attempt_at_a_status_is_allowed(self):
        """A failure mode may need several provocations; whichever reproduces evidences it."""
        statuses = [d["intended_status"] for d in make_demonstrations.DEMONSTRATIONS]
        self.assertGreaterEqual(len(statuses), len(set(statuses)))


if __name__ == "__main__":
    unittest.main()
