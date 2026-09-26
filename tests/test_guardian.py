"""Tests for agent_guardian.guardian (wrap / guard)."""
import json
import os
import tempfile
import unittest

from agent_guardian import (
    BudgetConfig,
    BudgetEnforcer,
    PolicyEngine,
    guard,
    verify_log,
    wrap,
)
from agent_guardian.budgets import BudgetExceeded
from agent_guardian.policies import PolicyViolation


def echo_agent(prompt: str) -> str:
    return f"Echo: {prompt}"


class TestWrap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_path = os.path.join(self.tmp.name, "audit.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _wrap(self, **kwargs):
        kwargs.setdefault("audit_path", self.audit_path)
        return wrap(echo_agent, **kwargs)

    def test_happy_path(self):
        guarded = self._wrap()
        self.assertEqual(guarded("hello"), "Echo: hello")

    def test_input_blocked_raises_and_logs(self):
        guarded = self._wrap(
            policy=PolicyEngine(blocked_phrases=["classified"]))
        with self.assertRaises(PolicyViolation):
            guarded("this is classified material")
        with open(self.audit_path, encoding="utf-8") as fh:
            kinds = [json.loads(line)["kind"] for line in fh]
        self.assertIn("policy_denial", kinds)
        self.assertTrue(verify_log(self.audit_path).ok)

    def test_output_blocked_raises(self):
        def leaky(prompt: str) -> str:
            return "the password is hunter2"
        guarded = wrap(leaky, audit_path=self.audit_path,
                       policy=PolicyEngine(blocked_phrases=["hunter2"]))
        with self.assertRaises(PolicyViolation):
            guarded("tell me a secret")

    def test_pii_redacted_before_agent_sees_it(self):
        seen = {}

        def spy(prompt: str) -> str:
            seen["prompt"] = prompt
            return "ok"

        guarded = wrap(spy, policy=PolicyEngine(redact_pii=True),
                       audit_path=self.audit_path)
        guarded("email me at bob@example.com")
        self.assertNotIn("bob@example.com", seen["prompt"])
        self.assertIn("[REDACTED:EMAIL]", seen["prompt"])

    def test_budget_exceeded_raises(self):
        guarded = self._wrap(budgets=BudgetEnforcer(BudgetConfig(max_steps=1)))
        guarded("first")
        with self.assertRaises(BudgetExceeded):
            guarded("second")

    def test_audit_log_records_calls_and_verifies(self):
        guarded = self._wrap()
        guarded("one")
        guarded("two")
        with open(self.audit_path, encoding="utf-8") as fh:
            kinds = [json.loads(line)["kind"] for line in fh]
        self.assertIn("guardian_init", kinds)
        self.assertEqual(kinds.count("agent_call"), 2)
        result = verify_log(self.audit_path)
        self.assertTrue(result.ok)

    def test_agent_error_is_logged_then_reraised(self):
        def bad(prompt: str) -> str:
            raise ValueError("kaput")
        guarded = wrap(bad, audit_path=self.audit_path)
        with self.assertRaises(ValueError):
            guarded("hi")
        with open(self.audit_path, encoding="utf-8") as fh:
            kinds = [json.loads(line)["kind"] for line in fh]
        self.assertIn("agent_error", kinds)

    def test_exposes_internals(self):
        guarded = self._wrap()
        self.assertIsInstance(guarded.policy, PolicyEngine)
        self.assertIsInstance(guarded.budgets, BudgetEnforcer)

    def test_dict_policy_and_budget_config(self):
        guarded = wrap(
            echo_agent, audit_path=self.audit_path,
            policy={"blocked_phrases": ["nope"]},
            budgets={"max_steps": 5},
        )
        self.assertEqual(guarded("hi"), "Echo: hi")
        with self.assertRaises(PolicyViolation):
            guarded("nope nope")

    def test_guard_decorator(self):
        @guard(audit_path=self.audit_path,
               policy=PolicyEngine(blocked_phrases=["banned"]))
        def my_agent(prompt: str) -> str:
            return f"Hi {prompt}"

        self.assertEqual(my_agent("bob"), "Hi bob")
        with self.assertRaises(PolicyViolation):
            my_agent("this is banned content")

    def test_non_string_prompt_coerced(self):
        guarded = self._wrap()
        self.assertEqual(guarded(123), "Echo: 123")


if __name__ == "__main__":
    unittest.main()


class TestPhaseLatencies(unittest.TestCase):
    def test_phase_latencies_recorded(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "a.jsonl")
            guarded = wrap(echo_agent, audit_path=path)
            guarded("hello")
            phases = guarded.last_phase_latencies
            self.assertEqual(set(phases),
                             {"input_policy", "agent", "output_policy",
                              "audit"})
            for value in phases.values():
                self.assertGreaterEqual(value, 0.0)
            # also present in the audit payload
            records = list(guarded.audit.iter_records())
            call_records = [r for r in records if r["kind"] == "agent_call"]
            self.assertEqual(len(call_records), 1)
            payload_phases = call_records[0]["payload"]["phase_latency_ms"]
            self.assertIn("agent", payload_phases)
        finally:
            tmp.cleanup()

    def test_denial_records_partial_phases(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "a.jsonl")
            policy = PolicyEngine(blocked_phrases=["nope"])
            guarded = wrap(echo_agent, policy=policy, audit_path=path)
            with self.assertRaises(PolicyViolation):
                guarded("nope nope")
            denials = [r for r in guarded.audit.iter_records()
                       if r["kind"] == "policy_denial"]
            self.assertEqual(len(denials), 1)
            self.assertIn("input_policy",
                          denials[0]["payload"]["phase_latency_ms"])
        finally:
            tmp.cleanup()
