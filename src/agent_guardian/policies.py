"""Declarative policy engine for AI agent inputs and outputs.

A :class:`PolicyEngine` inspects text through four layers, in order:

1. **Length cap** — hard limit on characters.
2. **Blocked phrases** — literal substrings that are never permitted.
3. **Declarative rules** — allow/deny rules expressed as plain data.
4. **Detectors** — prompt-injection heuristics and PII redaction
   (emails, phones, SSNs, credit-card-like numbers, API keys).

``check()`` always returns a :class:`PolicyDecision` and never raises.
Use :meth:`PolicyDecision.raise_if_denied` (or ``check_or_raise``) when a
violation should become an exception.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Findings, decisions, violations
# ---------------------------------------------------------------------------

@dataclass
class PolicyFinding:
    """One thing the policy engine noticed while inspecting text."""
    kind: str      # 'length' | 'blocked_phrase' | 'rule' | 'injection' | 'pii'
    detail: str
    redacted: bool = False


@dataclass
class PolicyDecision:
    """The verdict of a single policy check."""
    allowed: bool
    reason: str
    text: str                          # redacted text when PII redaction ran
    findings: List[PolicyFinding] = field(default_factory=list)

    def raise_if_denied(self) -> "PolicyDecision":
        """Raise :class:`PolicyViolation` unless the text was allowed."""
        if not self.allowed:
            raise PolicyViolation(self.reason, self)
        return self


class PolicyViolation(Exception):
    """Raised when inspected text violates the active policy."""
    def __init__(self, message: str, decision: Optional[PolicyDecision] = None):
        super().__init__(message)
        self.decision = decision


# ---------------------------------------------------------------------------
# PII detection / redaction
# ---------------------------------------------------------------------------

PII_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    "api_key": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|gsk_[A-Za-z0-9]{16,}"
        r"|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{8,})\b"
    ),
}


def redact_pii(text: str) -> Tuple[str, List[PolicyFinding]]:
    """Replace PII matches with ``[REDACTED:<KIND>]`` placeholders.

    Returns the redacted text and one finding per replacement.
    """
    findings: List[PolicyFinding] = []
    for kind, pattern in PII_PATTERNS.items():

        def _repl(match: "re.Match[str]", kind: str = kind) -> str:
            findings.append(PolicyFinding(
                kind="pii", detail=f"{kind} redacted", redacted=True))
            return f"[REDACTED:{kind.upper()}]"

        text = pattern.sub(_repl, text)
    return text, findings


# ---------------------------------------------------------------------------
# Prompt-injection heuristics
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: List["re.Pattern[str]"] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+[a-z]+", re.I),
    re.compile(r"you\s+are\s+now\s+[a-z]", re.I),
    re.compile(r"new\s+system\s+prompt", re.I),
    re.compile(r"(?m)^\s*system\s*:", re.I),
    re.compile(r"override\s+your\s+(safety|system|core)\s+", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"do\s+anything\s+now", re.I),
    re.compile(r"developer\s+mode", re.I),
]


def detect_injection(text: str) -> List[PolicyFinding]:
    """Return one finding per injection heuristic that fires."""
    findings = []
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(PolicyFinding(
                kind="injection",
                detail=f"possible prompt injection: {match.group(0).strip()[:60]!r}",
            ))
    return findings


# ---------------------------------------------------------------------------
# Declarative rules
# ---------------------------------------------------------------------------
# A rule is a plain dict, e.g.::
#
#     {"id": "no-prod-deletes", "effect": "deny",
#      "contains": ["drop table", "rm -rf /"]}
#     {"id": "admin-only", "effect": "deny",
#      "regex": ["\\bgrant\\s+admin\\b"],
#      "context_equals": {"role": "admin"}, "invert_context": True}
#
# Supported matchers: ``contains`` (case-insensitive substrings),
# ``regex`` (patterns), ``context_equals`` (all key/values must match the
# ``context`` mapping passed to :meth:`PolicyEngine.check`).  Deny rules win
# over allow rules.

Rule = Dict[str, Any]


def _rule_matches(rule: Rule, text: str,
                  context: Optional[Mapping[str, Any]]) -> bool:
    """True when the rule's textual and/or context matchers all fire."""
    lowered = text.lower()
    text_hit = False
    for needle in rule.get("contains", []) or []:
        if str(needle).lower() in lowered:
            text_hit = True
    for pattern in rule.get("regex", []) or []:
        if re.search(str(pattern), text, re.IGNORECASE):
            text_hit = True

    expected = rule.get("context_equals")
    if expected:
        context = context or {}
        matched = all(context.get(k) == v for k, v in expected.items())
        if rule.get("invert_context"):
            matched = not matched
        has_textual = bool(rule.get("contains") or rule.get("regex"))
        # Context gates the rule: it must match, plus the textual
        # matchers when any are given.
        return matched and (text_hit or not has_textual)
    return text_hit


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Inspect agent inputs/outputs against a declarative policy.

    Parameters
    ----------
    blocked_phrases:
        Literal substrings (case-insensitive) that always deny the text.
    redact_pii:
        Replace detected PII with ``[REDACTED:<KIND>]`` placeholders.
    detect_injection:
        Run prompt-injection heuristics.
    deny_on_injection:
        Deny the text when an injection heuristic fires (otherwise the
        text is allowed but the finding is recorded).
    rules:
        Declarative allow/deny rule dicts (deny wins on conflict).
    max_chars:
        Hard character limit; longer text is denied.
    """

    def __init__(
        self,
        blocked_phrases: Optional[Sequence[str]] = None,
        redact_pii: bool = True,
        detect_injection: bool = True,
        deny_on_injection: bool = True,
        rules: Optional[Sequence[Rule]] = None,
        max_chars: Optional[int] = None,
    ) -> None:
        self.blocked_phrases = [p.lower() for p in (blocked_phrases or [])]
        self.redact_pii = redact_pii
        self.detect_injection = detect_injection
        self.deny_on_injection = deny_on_injection
        self.rules: List[Rule] = list(rules or [])
        self.max_chars = max_chars

    # -- construction helpers -------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PolicyEngine":
        """Build an engine from a plain dict (e.g. parsed ``policy.json``)."""
        return cls(
            blocked_phrases=data.get("blocked_phrases"),
            redact_pii=data.get("redact_pii", True),
            detect_injection=data.get("detect_injection", True),
            deny_on_injection=data.get("deny_on_injection", True),
            rules=data.get("rules"),
            max_chars=data.get("max_chars"),
        )

    @classmethod
    def from_json(cls, path: str) -> "PolicyEngine":
        """Build an engine from a ``policy.json`` file."""
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    # -- inspection ------------------------------------------------------

    def check(self, text: str,
              context: Optional[Mapping[str, Any]] = None) -> PolicyDecision:
        """Inspect ``text`` and return a :class:`PolicyDecision` (never raises)."""
        if not isinstance(text, str):
            text = str(text)
        findings: List[PolicyFinding] = []

        # 1. length cap
        if self.max_chars is not None and len(text) > self.max_chars:
            findings.append(PolicyFinding(
                kind="length",
                detail=f"text is {len(text)} chars; limit is {self.max_chars}",
            ))
            return PolicyDecision(
                allowed=False,
                reason=f"text exceeds max_chars={self.max_chars}",
                text=text, findings=findings)

        # 2. blocked phrases
        lowered = text.lower()
        for phrase in self.blocked_phrases:
            if phrase and phrase in lowered:
                findings.append(PolicyFinding(
                    kind="blocked_phrase",
                    detail=f"blocked phrase {phrase!r} present",
                ))
        if any(f.kind == "blocked_phrase" for f in findings):
            return PolicyDecision(
                allowed=False, reason="blocked phrase matched",
                text=text, findings=findings)

        # 3. declarative rules (deny wins)
        denied_by: Optional[str] = None
        for rule in self.rules:
            if _rule_matches(rule, text, context):
                effect = str(rule.get("effect", "deny")).lower()
                findings.append(PolicyFinding(
                    kind="rule",
                    detail=f"rule {rule.get('id', '?')!r} matched (effect={effect})",
                ))
                if effect == "deny":
                    denied_by = str(rule.get("id", "rule"))
        if denied_by:
            return PolicyDecision(
                allowed=False, reason=f"denied by rule {denied_by!r}",
                text=text, findings=findings)

        # 4. detectors: injection heuristics, then PII redaction
        if self.detect_injection:
            findings.extend(detect_injection(text))
        injection_hit = any(f.kind == "injection" for f in findings)
        if injection_hit and self.deny_on_injection:
            return PolicyDecision(
                allowed=False, reason="prompt-injection heuristic matched",
                text=text, findings=findings)

        redacted_text = text
        if self.redact_pii:
            redacted_text, pii_findings = redact_pii(text)
            findings.extend(pii_findings)

        return PolicyDecision(
            allowed=True, reason="ok", text=redacted_text, findings=findings)

    def check_or_raise(self, text: str,
                       context: Optional[Mapping[str, Any]] = None) -> str:
        """Like :meth:`check` but raises :class:`PolicyViolation` on denial.

        Returns the (possibly redacted) text when allowed.
        """
        return self.check(text, context).raise_if_denied().text
