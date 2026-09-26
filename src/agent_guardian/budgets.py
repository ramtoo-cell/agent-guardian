"""Budget enforcement for agent runs: steps, tokens, cost, latency.

Token counts are *estimates* (``~4 characters per token``) unless the caller
supplies exact counts via :meth:`BudgetEnforcer.record_tokens`.  They are good
enough for guardrails; they are not billing-grade.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


def estimate_tokens(text: str) -> int:
    """Rough token estimate for ``text`` (~4 chars per token, min 1)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class BudgetConfig:
    """Limits for a guarded agent run. ``None`` disables that limit."""
    max_steps: Optional[int] = None
    max_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None
    max_latency_seconds: Optional[float] = None


class BudgetExceeded(Exception):
    """Raised when an agent run exceeds one of its budgets."""
    def __init__(self, message: str, detail: Optional[Dict[str, object]] = None):
        super().__init__(message)
        self.detail: Dict[str, object] = detail or {}


class BudgetEnforcer:
    """Track usage against a :class:`BudgetConfig` and raise on overrun.

    Typical usage::

        budgets = BudgetEnforcer(BudgetConfig(max_steps=5, max_cost_usd=0.10))
        budgets.start()
        for _ in range(10):
            budgets.check_step()   # raises BudgetExceeded on the 6th call
    """

    def __init__(self, config: Optional[BudgetConfig] = None, **kwargs: object) -> None:
        self.config = config or BudgetConfig(**kwargs)  # type: ignore[arg-type]
        self._steps = 0
        self._tokens = 0
        self._cost_usd = 0.0
        self._start: Optional[float] = None

    # -- lifecycle ------------------------------------------------------

    def start(self) -> "BudgetEnforcer":
        """(Re)start the clock and zero the counters."""
        self._steps = 0
        self._tokens = 0
        self._cost_usd = 0.0
        self._start = time.monotonic()
        return self

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since :meth:`start` (0.0 if never started)."""
        if self._start is None:
            return 0.0
        return time.monotonic() - self._start

    # -- recording -------------------------------------------------------

    def check_step(self) -> int:
        """Count one agent step; raise :class:`BudgetExceeded` if over limit."""
        self._steps += 1
        limit = self.config.max_steps
        if limit is not None and self._steps > limit:
            raise BudgetExceeded(
                f"step budget exceeded: {self._steps} > {limit}",
                {"limit": "max_steps", "used": self._steps, "limit_value": limit},
            )
        self.check_latency()
        return self._steps

    def record_text(self, text: str, cost_usd: float = 0.0) -> int:
        """Estimate tokens for ``text`` and record them (plus optional cost)."""
        return self.record_tokens(estimate_tokens(text), cost_usd=cost_usd)

    def record_tokens(self, n: int, cost_usd: float = 0.0) -> int:
        """Record ``n`` tokens (and optional USD cost); raise if over budget."""
        self._tokens += max(0, int(n))
        self._cost_usd += max(0.0, float(cost_usd))
        tok_limit = self.config.max_tokens
        if tok_limit is not None and self._tokens > tok_limit:
            raise BudgetExceeded(
                f"token budget exceeded: {self._tokens} > {tok_limit}",
                {"limit": "max_tokens", "used": self._tokens,
                 "limit_value": tok_limit},
            )
        cost_limit = self.config.max_cost_usd
        if cost_limit is not None and self._cost_usd > cost_limit:
            raise BudgetExceeded(
                f"cost budget exceeded: ${self._cost_usd:.4f} > ${cost_limit:.4f}",
                {"limit": "max_cost_usd", "used": self._cost_usd,
                 "limit_value": cost_limit},
            )
        return self._tokens

    def check_latency(self) -> float:
        """Raise :class:`BudgetExceeded` if the elapsed time is over budget."""
        elapsed = self.elapsed_seconds
        limit = self.config.max_latency_seconds
        if limit is not None and elapsed > limit:
            raise BudgetExceeded(
                f"latency budget exceeded: {elapsed:.2f}s > {limit:.2f}s",
                {"limit": "max_latency_seconds", "used": elapsed,
                 "limit_value": limit},
            )
        return elapsed

    def check(self) -> None:
        """Validate every limit right now (raises on the first breach)."""
        self.check_latency()
        # Re-run the numeric checks without mutating counters.
        tok_limit = self.config.max_tokens
        if tok_limit is not None and self._tokens > tok_limit:
            raise BudgetExceeded(f"token budget exceeded: {self._tokens} > {tok_limit}")
        cost_limit = self.config.max_cost_usd
        if cost_limit is not None and self._cost_usd > cost_limit:
            raise BudgetExceeded(
                f"cost budget exceeded: ${self._cost_usd:.4f} > ${cost_limit:.4f}")
        step_limit = self.config.max_steps
        if step_limit is not None and self._steps > step_limit:
            raise BudgetExceeded(
                f"step budget exceeded: {self._steps} > {step_limit}")

    # -- introspection ----------------------------------------------------

    def snapshot(self) -> Dict[str, object]:
        """Current usage counters (safe to embed in audit records)."""
        return {
            "steps": self._steps,
            "tokens": self._tokens,
            "cost_usd": round(self._cost_usd, 6),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "limits": {
                "max_steps": self.config.max_steps,
                "max_tokens": self.config.max_tokens,
                "max_cost_usd": self.config.max_cost_usd,
                "max_latency_seconds": self.config.max_latency_seconds,
            },
        }
