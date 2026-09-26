"""Budget enforcement for agent runs: steps, tokens, cost, latency.

Token counts are *estimates* unless the caller supplies exact counts via
:meth:`BudgetEnforcer.record_tokens` or a custom ``tokenizer``.  The default
estimator is a zero-dependency heuristic (see :func:`estimate_tokens`) —
good enough for guardrails, not billing-grade.
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Callable

from .exceptions import BudgetExceeded, ConfigurationError

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetConfig",
    "BudgetEnforcer",
    "BudgetExceeded",
    "ConfigurationError",
    "estimate_tokens",
]

# CJK characters are near one-to-one in BPE tokenizers, so they are counted
# individually instead of being folded into the word-based estimate.
_CJK_RE = re.compile(
    "[\u2e80-\u2eff\u3000-\u303f\u3040-\u30ff\u3100-\u312f"
    "\u3200-\u32ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
_WORD_RE = re.compile(r"\S+")


def estimate_tokens(text: str,
                    tokenizer: Callable[[str], int] | None = None) -> int:
    """Estimate the token count of ``text``.

    Args:
        text: The text to measure.
        tokenizer: Optional exact tokenizer, ``(str) -> int`` — e.g.
            ``len(tiktoken_encoding.encode(text))``.  When given, its result
            is used verbatim instead of the heuristic.

    Returns:
        The estimated token count (at least 1 for non-empty text, 0 for
        empty text).

    The zero-dependency heuristic works as follows:

    * CJK characters count ~1 token each (BPE treats them nearly one-to-one).
    * Remaining text is split on whitespace; the word count is divided by
      0.75, the widely observed average of ~0.75 English words per token.
    * The result is rounded up.

    On English prose this lands within roughly ±30% of real BPE counts;
    dense code, long URLs, or unusual punctuation can skew it further.
    Treat it as guardrail-grade, not billing-grade.
    """
    if tokenizer is not None:
        return max(0, int(tokenizer(text)))
    if not text:
        return 0
    cjk_chars = len(_CJK_RE.findall(text))
    words = len(_WORD_RE.findall(_CJK_RE.sub(" ", text)))
    return max(1, cjk_chars + math.ceil(words / 0.75))


@dataclass
class BudgetConfig:
    """Limits for a guarded agent run. ``None`` disables that limit.

    Attributes:
        max_steps: Maximum agent calls before :class:`BudgetExceeded`.
        max_tokens: Maximum estimated tokens (in + out) before the breach.
        max_cost_usd: Maximum accumulated USD cost before the breach.
        max_latency_seconds: Maximum wall-clock seconds since
            :meth:`BudgetEnforcer.start` before the breach.
    """

    max_steps: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_latency_seconds: float | None = None

    @classmethod
    def from_env(cls, prefix: str = "AGENT_GUARDIAN_") -> BudgetConfig:
        """Build a config from environment variables.

        Reads ``<PREFIX>MAX_STEPS``, ``<PREFIX>MAX_TOKENS``,
        ``<PREFIX>MAX_COST_USD`` and ``<PREFIX>MAX_LATENCY_SECONDS``.
        Unset (or empty) variables leave the corresponding limit disabled;
        unparsable values raise :class:`ConfigurationError` so typos fail
        loudly instead of silently disabling a guardrail.

        Args:
            prefix: Environment variable prefix, default
                ``"AGENT_GUARDIAN_"``.

        Returns:
            A :class:`BudgetConfig` with the limits found in the environment.

        Raises:
            ConfigurationError: If a set variable cannot be parsed.
        """
        spec = {
            "max_steps": ("MAX_STEPS", int),
            "max_tokens": ("MAX_TOKENS", int),
            "max_cost_usd": ("MAX_COST_USD", float),
            "max_latency_seconds": ("MAX_LATENCY_SECONDS", float),
        }
        kwargs: dict[str, object] = {}
        for field_name, (suffix, cast) in spec.items():
            name = prefix + suffix
            raw = os.environ.get(name)
            if raw is None or raw.strip() == "":
                continue
            try:
                kwargs[field_name] = cast(raw)
            except (ValueError, TypeError):
                raise ConfigurationError(
                    f"environment variable {name}={raw!r} is not a valid "
                    f"{cast.__name__}") from None
        config = cls(**kwargs)  # type: ignore[arg-type]
        logger.debug("BudgetConfig.from_env(%r) -> %s", prefix, config)
        return config


class BudgetEnforcer:
    """Track usage against a :class:`BudgetConfig` and raise on overrun.

    Args:
        config: The limits to enforce.  Defaults to an empty
            :class:`BudgetConfig` (nothing enforced).
        tokenizer: Optional exact ``(str) -> int`` tokenizer used by
            :meth:`record_text` instead of the :func:`estimate_tokens`
            heuristic.
        **kwargs: Shortcut for :class:`BudgetConfig` fields, e.g.
            ``BudgetEnforcer(max_steps=5)``.

    Typical usage::

        budgets = BudgetEnforcer(max_steps=5, max_cost_usd=0.10)
        budgets.start()
        for _ in range(10):
            budgets.check_step()   # raises BudgetExceeded on the 6th call
    """

    def __init__(self, config: BudgetConfig | None = None,
                 tokenizer: Callable[[str], int] | None = None,
                 **kwargs: object) -> None:
        self.config = config or BudgetConfig(**kwargs)  # type: ignore[arg-type]
        self.tokenizer = tokenizer
        self._steps = 0
        self._tokens = 0
        self._cost_usd = 0.0
        self._start: float | None = None

    # -- lifecycle ------------------------------------------------------

    def start(self) -> BudgetEnforcer:
        """(Re)start the clock and zero the counters.

        Returns:
            ``self``, for chaining.
        """
        self._steps = 0
        self._tokens = 0
        self._cost_usd = 0.0
        self._start = time.monotonic()
        logger.debug("budget clock started: %s", self.config)
        return self

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since :meth:`start` (0.0 if never started)."""
        if self._start is None:
            return 0.0
        return time.monotonic() - self._start

    # -- recording -------------------------------------------------------

    def check_step(self) -> int:
        """Count one agent step; raise :class:`BudgetExceeded` if over limit.

        Returns:
            The new step count.

        Raises:
            BudgetExceeded: If the step (or latency) budget is breached.
        """
        self._steps += 1
        limit = self.config.max_steps
        if limit is not None and self._steps > limit:
            raise BudgetExceeded(
                f"step budget exceeded: {self._steps} > {limit}",
                {"limit": "max_steps", "used": self._steps,
                 "limit_value": limit},
            )
        self.check_latency()
        return self._steps

    def record_text(self, text: str, cost_usd: float = 0.0) -> int:
        """Estimate tokens for ``text`` and record them, plus optional cost.

        Args:
            text: Text whose tokens are counted (via ``tokenizer`` when set,
                else the :func:`estimate_tokens` heuristic).
            cost_usd: Optional USD cost to accumulate.

        Returns:
            Total tokens recorded so far.

        Raises:
            BudgetExceeded: If the token or cost budget is breached.
        """
        return self.record_tokens(estimate_tokens(text, self.tokenizer),
                                  cost_usd=cost_usd)

    def record_tokens(self, n: int, cost_usd: float = 0.0) -> int:
        """Record ``n`` tokens (and optional USD cost); raise if over budget.

        Args:
            n: Exact token count to record.
            cost_usd: Optional USD cost to accumulate.

        Returns:
            Total tokens recorded so far.

        Raises:
            BudgetExceeded: If the token or cost budget is breached.
        """
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

    def record_cost(self, cost_usd: float) -> float:
        """Record USD cost without any tokens; raise if over budget.

        Useful when the caller prices calls itself (e.g. per-request
        billing from a model provider) rather than deriving cost from
        tokens.

        Args:
            cost_usd: USD cost to accumulate.

        Returns:
            Total cost recorded so far.

        Raises:
            BudgetExceeded: If the cost budget is breached.
        """
        self.record_tokens(0, cost_usd=cost_usd)
        return self._cost_usd

    def check_latency(self) -> float:
        """Raise :class:`BudgetExceeded` if elapsed time is over budget.

        Returns:
            Elapsed seconds since :meth:`start`.

        Raises:
            BudgetExceeded: If the latency budget is breached.
        """
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
        """Validate every limit right now; raise on the first breach.

        Unlike the ``record_*``/``check_*`` methods this does not mutate any
        counter.
        """
        self.check_latency()
        tok_limit = self.config.max_tokens
        if tok_limit is not None and self._tokens > tok_limit:
            raise BudgetExceeded(
                f"token budget exceeded: {self._tokens} > {tok_limit}")
        cost_limit = self.config.max_cost_usd
        if cost_limit is not None and self._cost_usd > cost_limit:
            raise BudgetExceeded(
                f"cost budget exceeded: ${self._cost_usd:.4f} > ${cost_limit:.4f}")
        step_limit = self.config.max_steps
        if step_limit is not None and self._steps > step_limit:
            raise BudgetExceeded(
                f"step budget exceeded: {self._steps} > {step_limit}")

    # -- introspection ----------------------------------------------------

    def snapshot(self) -> dict[str, object]:
        """Current usage counters and limits.

        Returns:
            A JSON-serializable dict, safe to embed in audit records::

                {"steps": 3, "tokens": 412, "cost_usd": 0.001,
                 "elapsed_seconds": 1.234,
                 "limits": {"max_steps": 10, ...}}
        """
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
