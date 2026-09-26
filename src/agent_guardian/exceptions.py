"""Exception taxonomy for agent-guardian.

Every exception raised by this package derives from
:class:`AgentGuardianError`, so callers can catch the whole family with a
single ``except`` clause while still handling specific failure modes::

    try:
        safe("do something")
    except BudgetExceeded:
        ...          # back off / alert
    except PolicyViolation:
        ...          # log the attempt
    except AgentGuardianError:
        ...          # anything else from this library
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .policies import PolicyDecision

__all__ = [
    "AgentGuardianError",
    "AuditError",
    "BudgetExceeded",
    "ConfigurationError",
    "PolicyViolation",
    "TargetLoadError",
]


class AgentGuardianError(Exception):
    """Base class for every exception raised by agent-guardian."""


class PolicyViolation(AgentGuardianError):  # noqa: N818 - shipped public API name (v0.1.0); renaming would break users
    """Raised when inspected text violates the active policy.

    Attributes:
        decision: The :class:`PolicyDecision` that caused the denial, or
            ``None`` when the violation was raised without one.
    """

    def __init__(self, message: str,
                 decision: PolicyDecision | None = None) -> None:
        super().__init__(message)
        self.decision = decision


class BudgetExceeded(AgentGuardianError):  # noqa: N818 - shipped public API name (v0.1.0); renaming would break users
    """Raised when an agent run exceeds one of its budgets.

    Attributes:
        detail: Machine-readable breakdown, e.g.
            ``{"limit": "max_tokens", "used": 1200, "limit_value": 1000}``.
    """

    def __init__(self, message: str,
                 detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail: dict[str, Any] = detail or {}


class AuditError(AgentGuardianError):
    """Raised when the audit log cannot be written, read, or resumed."""


class ConfigurationError(AgentGuardianError):
    """Raised for invalid configuration: bad policy files, bad env vars."""


class TargetLoadError(ConfigurationError):
    """Raised when a ``module:attr`` agent target cannot be imported."""
