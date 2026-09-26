"""agent-guardian — governance sidecar for AI agents.

Wrap any ``agent_fn(prompt) -> str`` callable and get policy enforcement,
budget guardrails, a tamper-evident audit log, and safety evals::

    from agent_guardian import wrap, PolicyEngine, BudgetConfig

    safe = wrap(my_agent,
                policy=PolicyEngine(blocked_phrases=["drop table"]),
                budgets=BudgetConfig(max_steps=10, max_cost_usd=0.50))
    print(safe("Hello, world"))

All exceptions raised by this package derive from
:class:`AgentGuardianError`, so a single ``except`` clause catches the
whole family.
"""

from .audit import AuditError, AuditLog, AuditVerification, verify_log
from .budgets import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceeded,
    estimate_tokens,
)
from .cli import main as cli_main
from .evals import RED_TEAM_PACK, looks_like_refusal, run_evals
from .exceptions import (
    AgentGuardianError,
    ConfigurationError,
    TargetLoadError,
)
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

__version__ = "0.2.0"

__all__ = [
    "RED_TEAM_PACK",
    "AgentGuardianError",
    "AuditError",
    "AuditLog",
    "AuditVerification",
    "BudgetConfig",
    "BudgetEnforcer",
    "BudgetExceeded",
    "ConfigurationError",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyFinding",
    "PolicyViolation",
    "TargetLoadError",
    "__version__",
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
