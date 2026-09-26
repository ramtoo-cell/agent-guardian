"""Tests for agent_guardian.evals."""
import unittest

from agent_guardian.evals import (
    RED_TEAM_PACK,
    looks_like_refusal,
    run_evals,
)


def refusing_agent(prompt):
    return "I'm sorry, I can't help with that."


def echo_agent(prompt):
    return f"Echo: {prompt}"


def crashing_agent(prompt):
    raise RuntimeError("boom")


class TestEvalHarness(unittest.TestCase):
    def test_pack_shape(self):
        self.assertGreaterEqual(len(RED_TEAM_PACK), 9)
        categories = {c["category"] for c in RED_TEAM_PACK}
        self.assertTrue({"jailbreak", "prompt_injection", "pii_extraction",
                         "benign"} <= categories)
        for case in RED_TEAM_PACK:
            self.assertIn("id", case)
            self.assertIn("prompt", case)
            self.assertIn("expect_refusal", case)

    def test_looks_like_refusal(self):
        self.assertTrue(looks_like_refusal("I'm sorry, I can't do that."))
        self.assertTrue(looks_like_refusal("I refuse to comply."))
        self.assertFalse(looks_like_refusal("Paris is the capital of France."))

    def test_scorecard_shape(self):
        scorecard = run_evals(echo_agent)
        for key in ("total", "passed", "score", "by_category", "details"):
            self.assertIn(key, scorecard)
        self.assertEqual(scorecard["total"], len(RED_TEAM_PACK))
        self.assertEqual(len(scorecard["details"]), len(RED_TEAM_PACK))
        for detail in scorecard["details"]:
            for key in ("id", "category", "prompt", "output",
                        "expected_refusal", "blocked", "passed"):
                self.assertIn(key, detail)

    def test_echo_agent_fails_attacks_passes_benign(self):
        scorecard = run_evals(echo_agent)
        by_cat = scorecard["by_category"]
        self.assertEqual(by_cat["benign"]["score"], 1.0)
        self.assertEqual(by_cat["jailbreak"]["score"], 0.0)

    def test_refusing_agent_passes_attacks_fails_benign(self):
        scorecard = run_evals(refusing_agent)
        by_cat = scorecard["by_category"]
        self.assertEqual(by_cat["jailbreak"]["score"], 1.0)
        self.assertEqual(by_cat["benign"]["score"], 0.0)

    def test_crashing_agent_counts_as_blocked(self):
        scorecard = run_evals(crashing_agent)
        details = {d["id"]: d for d in scorecard["details"]}
        self.assertTrue(details["jb-01"]["blocked"])
        self.assertTrue(details["jb-01"]["passed"])   # attack blocked = pass
        self.assertFalse(details["ok-01"]["passed"])  # benign blocked = fail

    def test_custom_pack(self):
        pack = [{"id": "t1", "category": "custom", "expect_refusal": False,
                 "prompt": "hi"}]
        scorecard = run_evals(echo_agent, pack=pack)
        self.assertEqual(scorecard["total"], 1)
        self.assertEqual(scorecard["passed"], 1)


if __name__ == "__main__":
    unittest.main()
