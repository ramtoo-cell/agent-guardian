"""Tests for agent_guardian.budgets."""
import time
import unittest

from agent_guardian.budgets import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceeded,
    estimate_tokens,
)


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
