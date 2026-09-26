"""Tests for agent_guardian.exceptions: the single-rooted taxonomy."""
import unittest

import agent_guardian.audit as audit_mod
import agent_guardian.budgets as budgets_mod
import agent_guardian.policies as policies_mod
from agent_guardian import (
    AgentGuardianError,
    AuditError,
    BudgetExceeded,
    ConfigurationError,
    PolicyDecision,
    PolicyViolation,
    TargetLoadError,
)
from agent_guardian import exceptions as exceptions_mod


class TestTaxonomy(unittest.TestCase):
    def test_single_root(self):
        for exc in (PolicyViolation, BudgetExceeded, AuditError,
                    ConfigurationError, TargetLoadError):
            self.assertTrue(issubclass(exc, AgentGuardianError),
                            f"{exc.__name__} is not an AgentGuardianError")

    def test_target_load_is_configuration_error(self):
        self.assertTrue(issubclass(TargetLoadError, ConfigurationError))

    def test_catch_all_with_base(self):
        with self.assertRaises(AgentGuardianError):
            raise BudgetExceeded("boom")
        with self.assertRaises(AgentGuardianError):
            raise PolicyViolation("boom")

    def test_policy_violation_carries_decision(self):
        decision = PolicyDecision(allowed=False, reason="nope", text="x")
        exc = PolicyViolation("denied", decision)
        self.assertIs(exc.decision, decision)
        self.assertIsNone(PolicyViolation("denied").decision)

    def test_budget_exceeded_carries_detail(self):
        exc = BudgetExceeded("over", {"limit": "max_steps"})
        self.assertEqual(exc.detail["limit"], "max_steps")
        self.assertEqual(BudgetExceeded("over").detail, {})

    def test_backwards_compatible_import_paths(self):
        # v0.1.0 import locations still resolve to the same classes.
        self.assertIs(budgets_mod.BudgetExceeded, BudgetExceeded)
        self.assertIs(policies_mod.PolicyViolation, PolicyViolation)
        self.assertIs(audit_mod.AuditError, AuditError)
        self.assertIs(exceptions_mod.AgentGuardianError, AgentGuardianError)


if __name__ == "__main__":
    unittest.main()
