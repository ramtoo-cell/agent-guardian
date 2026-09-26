"""Main API: wrap any agent callable with governance guardrails.

:func:`wrap` takes ``agent_fn(prompt, **kwargs) -> str`` and returns a guarded
callable with the same signature.  Every call flows through, in order:

1. **Input policy** — :class:`~agent_guardian.policies.PolicyEngine` inspects
   the prompt (PII is redacted before it reaches the agent).
2. **Budgets** — :class:`~agent_guardian.budgets.BudgetEnforcer` counts the
   step and its tokens.
3. **Agent** — the wrapped callable runs.
4. **Output policy** — the response is inspected (optional).
5. **Audit** — everything is appended to a hash-chained audit log.

Policy denials raise :class:`~agent_guardian.policies.PolicyViolation`;
budget overruns raise :class:`~agent_guardian.budgets.BudgetExceeded`.
Both are recorded in the audit log before being raised.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Dict, Optional

from .audit import AuditLog
from .budgets import BudgetConfig, BudgetEnforcer, BudgetExceeded
from .policies import PolicyDecision, PolicyEngine, PolicyViolation

__all__ = ["wrap", "guard"]


def _coerce_policy(policy: Optional[PolicyEngine]) -> PolicyEngine:
    if policy is None:
        return PolicyEngine()
    if isinstance(policy, dict):
        return PolicyEngine.from_dict(policy)
    return policy


def _coerce_budgets(budgets: Optional[BudgetEnforcer]) -> BudgetEnforcer:
    if budgets is None:
        return BudgetEnforcer()
    if isinstance(budgets, dict):
        return BudgetEnforcer(BudgetConfig(**budgets))
    if isinstance(budgets, BudgetConfig):
        return BudgetEnforcer(budgets)
    return budgets


def wrap(
    agent_fn: Callable[..., str],
    *,
    policy: Optional[PolicyEngine] = None,
    budgets: Optional[BudgetEnforcer] = None,
    audit_path: str = "agent_audit.jsonl",
    agent_id: Optional[str] = None,
    check_output: bool = True,
) -> Callable[..., str]:
    """Wrap ``agent_fn`` with policy, budget, and audit guardrails.

    Parameters
    ----------
    agent_fn:
        Callable ``(prompt: str, **kwargs) -> str`` to guard.
    policy:
        :class:`PolicyEngine`, or a dict accepted by
        :meth:`PolicyEngine.from_dict`. Defaults to a permissive engine
        (PII redaction + injection detection on, nothing blocked).
    budgets:
        :class:`BudgetEnforcer`, :class:`BudgetConfig`, or a dict of
        :class:`BudgetConfig` fields. Defaults to no limits.
    audit_path:
        Where the hash-chained JSONL audit log is written.
    agent_id:
        Label recorded in the audit log (defaults to the function name).
    check_output:
        Also run the policy engine over agent outputs.

    Returns a callable with the same signature as ``agent_fn``.  The
    wrapper exposes ``.policy``, ``.budgets`` and ``.audit`` attributes.
    """
    engine = _coerce_policy(policy)
    enforcer = _coerce_budgets(budgets)
    enforcer.start()
    name = agent_id or getattr(agent_fn, "__name__", "agent")
    log = AuditLog(audit_path, agent_id=name)
    log.append("guardian_init", {
        "agent": name,
        "budgets": enforcer.snapshot()["limits"],
        "check_output": check_output,
    })

    @functools.wraps(agent_fn)
    def guarded(prompt: str, **kwargs: Any) -> str:
        if not isinstance(prompt, str):
            prompt = str(prompt)

        # 1. input policy -------------------------------------------------
        decision_in: PolicyDecision = engine.check(prompt)
        enforcer.check_step()
        enforcer.record_text(decision_in.text)
        if not decision_in.allowed:
            log.append("policy_denial", {
                "phase": "input",
                "reason": decision_in.reason,
                "findings": [f.__dict__ for f in decision_in.findings],
                "prompt_chars": len(prompt),
            })
            raise PolicyViolation(
                f"input blocked by policy: {decision_in.reason}", decision_in)

        # 2+3. run the agent under budget supervision --------------------
        started = time.monotonic()
        try:
            output = agent_fn(decision_in.text, **kwargs)
        except BudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - log agent crashes too
            log.append("agent_error", {
                "error": f"{type(exc).__name__}: {exc}",
                "latency_seconds": round(time.monotonic() - started, 3),
                "budgets": enforcer.snapshot(),
            })
            raise
        latency = time.monotonic() - started
        output = "" if output is None else str(output)
        enforcer.record_text(output)
        enforcer.check_latency()

        # 4. output policy ------------------------------------------------
        decision_out: Optional[PolicyDecision] = None
        if check_output:
            decision_out = engine.check(output)
            if not decision_out.allowed:
                log.append("policy_denial", {
                    "phase": "output",
                    "reason": decision_out.reason,
                    "findings": [f.__dict__ for f in decision_out.findings],
                    "output_chars": len(output),
                    "budgets": enforcer.snapshot(),
                })
                raise PolicyViolation(
                    f"output blocked by policy: {decision_out.reason}",
                    decision_out)
            output = decision_out.text

        # 5. audit ---------------------------------------------------------
        log.append("agent_call", {
            "prompt_chars": len(prompt),
            "output_chars": len(output),
            "latency_seconds": round(latency, 3),
            "input_findings": [f.__dict__ for f in decision_in.findings],
            "output_findings": [f.__dict__ for f in
                                (decision_out.findings if decision_out else [])],
            "budgets": enforcer.snapshot(),
        })
        return output

    # introspection hooks (used by tests and the CLI)
    guarded.policy = engine          # type: ignore[attr-defined]
    guarded.budgets = enforcer       # type: ignore[attr-defined]
    guarded.audit = log              # type: ignore[attr-defined]
    return guarded


def guard(
    policy: Optional[PolicyEngine] = None,
    budgets: Optional[BudgetEnforcer] = None,
    audit_path: str = "agent_audit.jsonl",
    agent_id: Optional[str] = None,
    check_output: bool = True,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator form of :func:`wrap`.

    Example::

        @guard(policy=PolicyEngine(blocked_phrases=["drop table"]),
               budgets=BudgetConfig(max_steps=10))
        def my_agent(prompt: str) -> str:
            ...
    """
    def decorator(agent_fn: Callable[..., str]) -> Callable[..., str]:
        return wrap(agent_fn, policy=policy, budgets=budgets,
                    audit_path=audit_path, agent_id=agent_id,
                    check_output=check_output)
    return decorator
