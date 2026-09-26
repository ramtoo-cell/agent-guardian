"""Tests for agent_guardian.budgets."""
import os
import time
import unittest
from typing import ClassVar

from agent_guardian.budgets import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceeded,
    estimate_tokens,
)
from agent_guardian.exceptions import ConfigurationError


class TestEstimateTokens(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_scales_with_length(self):
        short = estimate_tokens("hi")
        long = estimate_tokens("word " * 1000)
        self.assertGreater(long, short)
        self.assertGreaterEqual(short, 1)


class TestBudgetEnforcer(unittest.TestCase):
    def test_steps_within_limit(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_steps=3)).start()
        enforcer.check_step()
        enforcer.check_step()

    def test_step_limit_raises_with_detail(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_steps=2)).start()
        enforcer.check_step()
        enforcer.check_step()
        with self.assertRaises(BudgetExceeded) as ctx:
            enforcer.check_step()
        self.assertEqual(ctx.exception.detail["limit"], "max_steps")

    def test_token_limit(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_tokens=10)).start()
        enforcer.record_tokens(5)
        with self.assertRaises(BudgetExceeded):
            enforcer.record_tokens(6)

    def test_cost_limit(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_cost_usd=0.05)).start()
        enforcer.record_tokens(10, cost_usd=0.04)
        with self.assertRaises(BudgetExceeded):
            enforcer.record_tokens(10, cost_usd=0.02)

    def test_record_text_counts_tokens(self):
        enforcer = BudgetEnforcer().start()
        enforcer.record_text("hello world, this is a test")
        self.assertGreater(enforcer.snapshot()["tokens"], 0)

    def test_latency_limit(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_latency_seconds=0.01)).start()
        time.sleep(0.03)
        with self.assertRaises(BudgetExceeded):
            enforcer.check_latency()

    def test_no_limits_never_raises(self):
        enforcer = BudgetEnforcer().start()
        for _ in range(100):
            enforcer.check_step()
            enforcer.record_tokens(1000, cost_usd=5.0)

    def test_kwargs_construction(self):
        enforcer = BudgetEnforcer(max_steps=1)
        self.assertEqual(enforcer.config.max_steps, 1)

    def test_snapshot_shape(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(max_steps=5, max_tokens=100)).start()
        enforcer.check_step()
        enforcer.record_tokens(10, cost_usd=0.01)
        snap = enforcer.snapshot()
        self.assertEqual(snap["steps"], 1)
        self.assertEqual(snap["tokens"], 10)
        self.assertAlmostEqual(snap["cost_usd"], 0.01)
        self.assertIn("limits", snap)

    def test_start_resets_counters(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_steps=1)).start()
        enforcer.check_step()
        enforcer.start()
        enforcer.check_step()  # would raise if not reset


if __name__ == "__main__":
    unittest.main()


class TestEstimateTokensV2(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_short_text(self):
        # 1 word / 0.75 = 1.34 -> rounded up to 2 (conservative by design)
        self.assertEqual(estimate_tokens("hi"), 2)

    def test_word_based(self):
        # 4 words / 0.75 = 5.34 -> 6
        self.assertEqual(estimate_tokens("one two three four"), 6)

    def test_cjk_counts_per_character(self):
        self.assertEqual(estimate_tokens("你好"), 2)
        mixed = estimate_tokens("hello 你好")
        self.assertEqual(mixed, 2 + 2)  # 1 word -> 2, plus 2 CJK

    def test_exact_tokenizer_override(self):
        self.assertEqual(estimate_tokens("hello world",
                                         tokenizer=lambda t: 42), 42)
        self.assertEqual(estimate_tokens("", tokenizer=lambda t: 7), 7)

    def test_enforcer_uses_custom_tokenizer(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_tokens=10),
                                 tokenizer=lambda t: 100)
        with self.assertRaises(BudgetExceeded):
            enforcer.record_text("tiny")


class TestBudgetConfigFromEnv(unittest.TestCase):
    PREFIX = "AGENT_GUARDIAN_"
    VARS: ClassVar[list] = ["MAX_STEPS", "MAX_TOKENS", "MAX_COST_USD",
                            "MAX_LATENCY_SECONDS"]

    def setUp(self):
        self._saved = {v: os.environ.get(self.PREFIX + v) for v in self.VARS}
        for v in self.VARS:
            os.environ.pop(self.PREFIX + v, None)

    def tearDown(self):
        for v in self.VARS:
            if self._saved[v] is None:
                os.environ.pop(self.PREFIX + v, None)
            else:
                os.environ[self.PREFIX + v] = self._saved[v]

    def test_empty_env_disables_all(self):
        config = BudgetConfig.from_env()
        self.assertIsNone(config.max_steps)
        self.assertIsNone(config.max_tokens)
        self.assertIsNone(config.max_cost_usd)
        self.assertIsNone(config.max_latency_seconds)

    def test_parses_all_vars(self):
        os.environ["AGENT_GUARDIAN_MAX_STEPS"] = "25"
        os.environ["AGENT_GUARDIAN_MAX_TOKENS"] = "1000"
        os.environ["AGENT_GUARDIAN_MAX_COST_USD"] = "1.5"
        os.environ["AGENT_GUARDIAN_MAX_LATENCY_SECONDS"] = "30"
        config = BudgetConfig.from_env()
        self.assertEqual(config.max_steps, 25)
        self.assertEqual(config.max_tokens, 1000)
        self.assertEqual(config.max_cost_usd, 1.5)
        self.assertEqual(config.max_latency_seconds, 30.0)

    def test_blank_is_ignored(self):
        os.environ["AGENT_GUARDIAN_MAX_STEPS"] = "  "
        self.assertIsNone(BudgetConfig.from_env().max_steps)

    def test_invalid_value_raises(self):
        os.environ["AGENT_GUARDIAN_MAX_STEPS"] = "many"
        with self.assertRaises(ConfigurationError):
            BudgetConfig.from_env()

    def test_custom_prefix(self):
        os.environ["MYAPP_MAX_STEPS"] = "7"
        config = BudgetConfig.from_env(prefix="MYAPP_")
        self.assertEqual(config.max_steps, 7)


class TestRecordCost(unittest.TestCase):
    def test_cost_only(self):
        enforcer = BudgetEnforcer(BudgetConfig(max_cost_usd=0.05))
        enforcer.start()
        self.assertAlmostEqual(enforcer.record_cost(0.02), 0.02)
        with self.assertRaises(BudgetExceeded):
            enforcer.record_cost(0.04)
