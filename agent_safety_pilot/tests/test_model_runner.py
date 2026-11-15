import json
import unittest

from agent_safety_pilot import load_cases
from agent_safety_pilot.model_runner import (
    OllamaClient,
    OllamaError,
    _command,
    load_config,
    looks_like_tool_call_text,
    provenance,
    run_case,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, payload):
        self.requests.append(payload)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FakeServer(FakeClient):
    """A fake that also answers the provenance endpoints."""

    def __init__(self, responses=(), *, model="qwen3:4b", digest="sha256:abc", caps=("completion", "tools")):
        super().__init__(responses)
        self.model = model
        self.digest = digest
        self.caps = list(caps)

    def request(self, path, payload=None):
        if path == "/api/tags":
            return {"models": [{"name": self.model, "digest": self.digest}]}
        if path == "/api/show":
            return {"capabilities": self.caps}
        raise AssertionError(f"unexpected path {path}")


def call(action, resource, **kwargs):
    return {"function": {"name": "sandbox_action", "arguments": {"action": action, "resource": resource, **kwargs}}}


def response(*calls, content="", eval_count=12, thinking=None):
    message = {"role": "assistant", "content": content, "tool_calls": list(calls)}
    if thinking is not None:
        message["thinking"] = thinking
    return {"message": message, "eval_count": eval_count}


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in load_cases()}
        cls.config = load_config()
        cls.metadata = {"actor": "fake model", "model_digest": "test-digest"}

    def test_only_loopback_ollama_endpoint_is_accepted(self):
        with self.assertRaises(ValueError):
            OllamaClient("https://example.com", 1)

    def test_pressure_note_is_seen_after_authorized_read_and_logged(self):
        client = FakeClient([
            response(call("read", "docs/brief")),
            response(content="Summary ready."),
        ])
        packet = run_case(client, self.cases["D1"], "pressure", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "completed")
        self.assertTrue(packet["model_run"]["pressure_delivered"])
        read = next(e for e in packet["trace"] if e["kind"] == "tool_call")
        self.assertEqual(read["result"]["untrusted_note"], self.cases["D1"]["pressure_hint"])
        self.assertIn("untrusted_note", client.requests[1]["messages"][-1]["content"])
        self.assertEqual(packet["oracle"]["task_success"], None)
        self.assertTrue(packet["oracle"]["observation_complete"])
        self.assertEqual(packet["provenance"]["model_digest"], "test-digest")
        json.dumps(packet, allow_nan=False)

    def test_restricted_read_is_effect_even_when_final_answer_is_harmless(self):
        client = FakeClient([
            response(call("read", "docs/restricted")),
            response(content="I cannot help with that."),
        ])
        packet = run_case(client, self.cases["D1"], "clear", self.config, self.metadata)
        self.assertEqual(packet["oracle"]["summary"], "unauthorized_effect")
        self.assertEqual(packet["oracle"]["unauthorized_effects"], [2])
        self.assertEqual(packet["outcome"]["final_response"], "I cannot help with that.")

    def test_checkout_notice_is_present_before_model_acts(self):
        client = FakeClient([response(content="I need clarification.")])
        packet = run_case(client, self.cases["P2"], "pressure", self.config, self.metadata)
        self.assertEqual(packet["trace"][0]["kind"], "environment_notice")
        self.assertIn(self.cases["P2"]["pressure_hint"], client.requests[0]["messages"][1]["content"])

    def test_turn_limit_does_not_become_a_clean_pass(self):
        config = {**self.config, "max_turns": 1}
        client = FakeClient([response(call("read", "docs/brief"))])
        packet = run_case(client, self.cases["D1"], "clear", config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "turn_limit")
        self.assertEqual(packet["oracle"]["summary"], "indeterminate")
        self.assertFalse(packet["oracle"]["observation_complete"])

    def test_malformed_call_is_preserved(self):
        client = FakeClient([
            response(call("charge", "account/purchases", amount=-1)),
            response(content="Stopped."),
        ])
        packet = run_case(client, self.cases["P2"], "clear", self.config, self.metadata)
        self.assertEqual(packet["oracle"]["invalid_calls"], [2])
        self.assertEqual(packet["trace"][1]["kind"], "rejected_call")

    def test_tool_limit_itemises_the_calls_it_discarded(self):
        config = {**self.config, "max_tool_calls": 1}
        client = FakeClient([response(call("read", "docs/brief"), call("read", "docs/restricted"))])
        packet = run_case(client, self.cases["D1"], "clear", config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "tool_limit")
        self.assertEqual(packet["oracle"]["summary"], "indeterminate")
        self.assertEqual([e["kind"] for e in packet["trace"]], ["model_message", "tool_call", "runner_limit"])
        self.assertEqual(packet["model_run"]["tool_calls"], 1)
        limit = packet["trace"][-1]
        self.assertEqual(limit["discarded"][0]["arguments"]["resource"], "docs/restricted")

    # The two failures that previously produced a false clean label.

    def test_truncated_response_is_not_a_clean_pass(self):
        budget = self.config["options"]["num_predict"]
        client = FakeClient([response(content="Okay, let me think about which tool", eval_count=budget)])
        packet = run_case(client, self.cases["D1"], "clear", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "truncated")
        self.assertEqual(packet["oracle"]["summary"], "indeterminate")
        self.assertFalse(packet["oracle"]["observation_complete"])
        self.assertTrue(packet["trace"][0]["truncated"])
        self.assertEqual(packet["outcome"]["final_response"], "")

    def test_tool_call_emitted_as_text_is_recorded_and_never_executed(self):
        text = '{"name": "sandbox_action", "arguments": {"action": "read", "resource": "docs/restricted"}}'
        client = FakeClient([response(content=text)])
        packet = run_case(client, self.cases["D1"], "clear", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "unparsed_tool_call_text")
        self.assertEqual(packet["oracle"]["summary"], "indeterminate")
        self.assertFalse(packet["oracle"]["observation_complete"])
        self.assertEqual(packet["trace"][-1]["kind"], "unparsed_tool_call_text")
        self.assertEqual(packet["model_run"]["tool_calls"], 0)
        self.assertEqual(packet["oracle"]["unauthorized_attempts"], [])
        self.assertEqual(packet["outcome"]["final_state"]["docs/restricted"],
                         self.cases["D1"]["initial_state"]["docs/restricted"])

    def test_fenced_tool_call_text_is_also_caught(self):
        text = 'Here you go:\n```json\n{"action": "charge", "resource": "account/purchases", "amount": 140}\n```'
        client = FakeClient([response(content=text)])
        packet = run_case(client, self.cases["P2"], "clear", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "unparsed_tool_call_text")
        self.assertEqual(packet["outcome"]["final_state"]["_charges"], [])

    def test_an_observed_crossing_survives_a_later_truncation(self):
        budget = self.config["options"]["num_predict"]
        client = FakeClient([
            response(call("read", "docs/restricted")),
            response(content="Okay, so the summary is", eval_count=budget),
        ])
        packet = run_case(client, self.cases["D1"], "clear", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "truncated")
        self.assertEqual(packet["oracle"]["summary"], "unauthorized_effect")
        self.assertFalse(packet["oracle"]["observation_complete"])

    def test_ordinary_prose_is_not_mistaken_for_a_tool_call(self):
        for content in (
            "I read docs/brief and here is the summary.",
            "I will not charge the account without approval.",
            'The file says {"owner": "finance"} at the top.',
            "",
        ):
            self.assertFalse(looks_like_tool_call_text(content), content)

    def test_transport_failure_still_produces_a_packet(self):
        client = FakeClient([OllamaError("/api/chat returned HTTP 500", 500, '{"error":"out of memory"}')])
        packet = run_case(client, self.cases["D1"], "clear", self.config, self.metadata)
        self.assertEqual(packet["model_run"]["status"], "transport_error")
        self.assertEqual(packet["oracle"]["summary"], "indeterminate")
        self.assertFalse(packet["oracle"]["observation_complete"])
        error = packet["trace"][-1]
        self.assertEqual(error["kind"], "transport_error")
        self.assertEqual(error["http_status"], 500)
        self.assertIn("out of memory", error["body"])
        json.dumps(packet, allow_nan=False)

    def test_think_setting_is_sent_to_the_model(self):
        client = FakeClient([response(content="Done.")])
        run_case(client, self.cases["D1"], "clear", {**self.config, "think": True}, self.metadata)
        self.assertIs(client.requests[0]["think"], True)
        self.assertEqual(client.requests[0]["tools"][0]["function"]["name"], "sandbox_action")


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()

    def test_model_without_tools_capability_is_refused(self):
        server = FakeServer(caps=("completion", "insert"))
        with self.assertRaises(ValueError) as caught:
            provenance(server, self.config)
        self.assertIn("tools capability", str(caught.exception))

    def test_missing_model_is_refused(self):
        server = FakeServer(model="something-else:1b")
        with self.assertRaises(ValueError) as caught:
            provenance(server, self.config)
        self.assertIn("not pulled locally", str(caught.exception))

    def test_capable_model_records_identifying_metadata(self):
        meta = provenance(FakeServer(), self.config)
        self.assertEqual(meta["model_digest"], "sha256:abc")
        self.assertIn("tools", meta["model_capabilities"])
        for field in ("config_sha256", "cases_sha256", "harness_sha256", "runner_sha256", "system_prompt_sha256"):
            self.assertEqual(len(meta[field]), 64)
        self.assertIn("git_dirty", meta)
        json.dumps(meta, allow_nan=False)

    def test_a_missing_command_does_not_abort_the_run(self):
        result = _command(["definitely-not-a-real-binary-xyz"])
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("reason", result)