"""agent-guardian — governance sidecar for AI agents.

Wrap any ``agent_fn(prompt) -> str`` callable and get policy enforcement,
budget guardrails, a tamper-evident audit log, and safety evals::

    from agent_guardian import wrap, PolicyEngine, BudgetConfig

    safe = wrap(my_agent,
                policy=PolicyEngine(blocked_phrases=["drop table"]),
                budgets=BudgetConfig(max_steps=10, max_cost_usd=0.50))
    print(safe("Hello, world"))
"""

from .audit import AuditLog, AuditVerification, verify_log
from .budgets import BudgetConfig, BudgetEnforcer, BudgetExceeded, estimate_tokens
from .cli import main as cli_main
from .evals import RED_TEAM_PACK, looks_like_refusal, run_evals
from .guardian import guard, wrap
from .policies import (
    PolicyDecision,
    PolicyEngine,
    PolicyFinding,
    PolicyViolation,
    detect_injection,
    redact_pii,
)
from .report import render_report

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AuditLog",
    "AuditVerification",
    "BudgetConfig",
    "BudgetEnforcer",
    "BudgetExceeded",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyFinding",
    "PolicyViolation",
    "RED_TEAM_PACK",
    "cli_main",
    "detect_injection",
    "estimate_tokens",
    "guard",
    "looks_like_refusal",
    "redact_pii",
    "render_report",
    "run_evals",
    "verify_log",
    "wrap",
]
