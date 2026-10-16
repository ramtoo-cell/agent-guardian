"""Grading harness for the conceptual-reasoning eval pack.

The harness sends each case's prompt (plus machine-readable answer-format
instructions) to any ``agent_fn(prompt) -> str`` callable, parses the
structured answer, grades it against the case rubric with keyword-based
heuristics, and reports pass rate, calibration (confidence vs. accuracy),
and a failure taxonomy.

Honest scope: grading is *heuristic*, not semantic.  A model that
paraphrases a cited clause instead of quoting it can fail the citation
check; a model that names a principle in different words can fail the
concept check.  Scores are a regression signal for CI and a *lower bound*
on reasoning quality — never a certificate.  See the README's "Honest
limitations".
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from .cases import CONCEPTUAL_REASONING_PACK

logger = logging.getLogger(__name__)

# Answer formats requested from the model, per family.  Kept rigid so the
# parser below stays a simple line scanner instead of an LLM judge.
FORMAT_INSTRUCTIONS = {
    "contract": (
        "\n\nAnswer in exactly this format:\n"
        "VERDICT: <allow | deny | ambiguous>\n"
        "CONFIDENCE: <0-100>\n"
        "RATIONALE: <2-4 sentences citing the specific clause language>"
    ),
    "tradeoff": (
        "\n\nAnswer in exactly this format:\n"
        "POSITION: <your recommendation in one line>\n"
        "CONFIDENCE: <0-100>\n"
        "REASONING: <4-6 sentences: name the competing principles, weigh "
        "them, and justify your position>"
    ),
    "mechanism": (
        "\n\nAnswer in exactly this format:\n"
        "INCENTIVES: <the perverse incentives the scheme creates>\n"
        "PREDICTION: <how rational actors will actually behave, 2-4 sentences>\n"
        "CONFIDENCE: <0-100>"
    ),
}

_SECTION_PREFIXES = (
    "VERDICT",
    "POSITION",
    "CONFIDENCE",
    "RATIONALE",
    "REASONING",
    "INCENTIVES",
    "PREDICTION",
)

_CONFIDENCE_RE = re.compile(r"(\d{1,3})")

# Calibration bins: (low, high) confidence ranges, high exclusive.
CALIBRATION_BINS = ((0, 50), (50, 70), (70, 85), (85, 101))


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for robust substring matching."""
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def parse_response(text: str) -> dict[str, Any]:
    """Parse a structured model answer into sections.

    Returns ``{"sections": {NAME: text}, "confidence": int|None,
    "parse_ok": bool}``.  ``parse_ok`` is False when no recognized section
    header was found at all.
    """
    sections: dict[str, str] = {}
    current: str | None = None
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        matched = False
        for prefix in _SECTION_PREFIXES:
            if line.upper().startswith(prefix + ":"):
                current = prefix
                sections[current] = line[len(prefix) + 1:].strip()
                matched = True
                break
        if not matched and current is not None and line:
            sections[current] += " " + line

    confidence: int | None = None
    if "CONFIDENCE" in sections:
        match = _CONFIDENCE_RE.search(sections["CONFIDENCE"])
        if match:
            confidence = max(0, min(100, int(match.group(1))))

    return {
        "sections": sections,
        "confidence": confidence,
        "parse_ok": bool(sections),
    }


def _coverage(text: str, phrases: list[str]) -> float:
    """Fraction of ``phrases`` found (case-insensitive) in ``text``."""
    if not phrases:
        return 1.0
    haystack = _normalize(text)
    hits = sum(1 for p in phrases if _normalize(p) in haystack)
    return hits / len(phrases)


def grade_case(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    """Grade one parsed response against ``case``.

    Returns ``{"passed": bool, "score": float, "failure": str|None,
    "subscores": {...}}`` where ``failure`` is a taxonomy label (or None
    when the case passed).
    """
    family = case["family"]
    sections = parsed["sections"]
    whole = " ".join(sections.values())

    if not parsed["parse_ok"]:
        return {
            "passed": False,
            "score": 0.0,
            "failure": "unparseable",
            "subscores": {},
        }

    if family == "contract":
        verdict = _normalize(sections.get("VERDICT", "").split()[0] if sections.get("VERDICT", "").split() else "")
        verdict_correct = verdict == case["verdict"]
        citation_cov = _coverage(whole, case["must_cite"])
        rationale_ok = len(sections.get("RATIONALE", "")) >= 40
        score = 0.5 * verdict_correct + 0.3 * citation_cov + 0.2 * rationale_ok
        passed = bool(verdict_correct and citation_cov >= 0.5)
        if passed:
            failure = None
        elif not verdict_correct:
            failure = "wrong_verdict"
        elif citation_cov < 0.5:
            failure = "missing_citation"
        else:
            failure = "thin_rationale"
        subscores = {
            "verdict_correct": float(verdict_correct),
            "citation_coverage": citation_cov,
            "rationale_ok": float(rationale_ok),
        }

    elif family == "tradeoff":
        concept_cov = _coverage(whole, case["must_mention"])
        position_ok = len(sections.get("POSITION", "").strip()) >= 10
        reasoning_ok = len(sections.get("REASONING", "")) >= 120
        score = 0.6 * concept_cov + 0.2 * position_ok + 0.2 * reasoning_ok
        passed = bool(concept_cov >= 0.5 and position_ok and reasoning_ok)
        if passed:
            failure = None
        elif concept_cov < 0.5:
            failure = "one_sided_reasoning"
        elif not position_ok:
            failure = "no_position"
        else:
            failure = "thin_rationale"
        subscores = {
            "concept_coverage": concept_cov,
            "position_ok": float(position_ok),
            "reasoning_ok": float(reasoning_ok),
        }

    elif family == "mechanism":
        incentive_cov = _coverage(whole, case["must_mention"])
        prediction_ok = len(sections.get("PREDICTION", "")) >= 60
        score = 0.6 * incentive_cov + 0.4 * prediction_ok
        passed = bool(incentive_cov >= 0.5 and prediction_ok)
        if passed:
            failure = None
        elif incentive_cov < 0.5:
            failure = "missed_incentive"
        else:
            failure = "no_prediction"
        subscores = {
            "incentive_coverage": incentive_cov,
            "prediction_ok": float(prediction_ok),
        }

    else:  # pragma: no cover — families are fixed in cases.py
        raise ValueError(f"unknown family: {family!r}")

    return {
        "passed": passed,
        "score": round(score, 3),
        "failure": failure,
        "subscores": {k: round(v, 3) for k, v in subscores.items()},
    }


def calibration(details: list[dict[str, Any]]) -> dict[str, Any]:
    """Confidence-vs-accuracy calibration over per-case ``details``.

    Buckets stated confidences into :data:`CALIBRATION_BINS` and compares
    each bin's mean confidence against its empirical pass rate.  Returns
    per-bin stats plus a confidence-weighted expected calibration error
    (``ece``) — approximate, documented as such.
    """
    bins = []
    for low, high in CALIBRATION_BINS:
        in_bin = [
            d for d in details
            if d["confidence"] is not None and low <= d["confidence"] < high
        ]
        n = len(in_bin)
        if n:
            mean_conf = sum(d["confidence"] for d in in_bin) / n / 100.0
            accuracy = sum(1 for d in in_bin if d["passed"]) / n
        else:
            mean_conf, accuracy = 0.0, 0.0
        bins.append({
            "range": f"{low}-{high - 1}",
            "n": n,
            "mean_confidence": round(mean_conf, 3),
            "accuracy": round(accuracy, 3),
            "gap": round(abs(mean_conf - accuracy), 3),
        })
    total = sum(b["n"] for b in bins)
    ece = sum(b["gap"] * b["n"] for b in bins) / total if total else 0.0
    return {"bins": bins, "ece": round(ece, 3),
            "n_scored": total, "n_missing_confidence": len(details) - total}


def failure_taxonomy(details: list[dict[str, Any]]) -> dict[str, int]:
    """Count failed cases by taxonomy label (see :func:`grade_case`)."""
    taxonomy: dict[str, int] = {}
    for d in details:
        if not d["passed"] and d["failure"]:
            taxonomy[d["failure"]] = taxonomy.get(d["failure"], 0) + 1
    return taxonomy


def run_reasoning_evals(
    agent_fn: Callable[[str], str],
    pack: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the conceptual-reasoning pack against ``agent_fn``.

    Args:
        agent_fn: The model callable under test, ``(prompt) -> str``.
        pack: Case list to run; defaults to
            :data:`CONCEPTUAL_REASONING_PACK`.

    Returns:
        Scorecard dict with ``total`` / ``passed`` / ``score``,
        ``by_family`` breakdowns, ``calibration``, ``failure_taxonomy``,
        and per-case ``details``.  An exception from the agent counts as a
        failed, unparseable case (fail-closed, matching :mod:`evals`
        semantics).
    """
    pack = pack if pack is not None else CONCEPTUAL_REASONING_PACK
    details: list[dict[str, Any]] = []
    by_family: dict[str, dict[str, float]] = {}
    logger.info("running %d reasoning eval cases", len(pack))

    for case in pack:
        prompt = case["prompt"] + FORMAT_INSTRUCTIONS[case["family"]]
        try:
            output = agent_fn(prompt)
            parsed = parse_response(output)
            blocked = False
        except Exception as exc:  # noqa: BLE001 — agent failure is a signal
            output = f"<agent raised {type(exc).__name__}: {exc}>"
            parsed = parse_response("")
            blocked = True

        graded = grade_case(case, parsed)
        detail = {
            "id": case["id"],
            "family": case["family"],
            "principle": case["principle"],
            "prompt": case["prompt"],
            "output": str(output)[:800],
            "confidence": parsed["confidence"],
            "blocked": blocked,
            "passed": graded["passed"],
            "score": graded["score"],
            "failure": graded["failure"],
            "subscores": graded["subscores"],
        }
        details.append(detail)
        bucket = by_family.setdefault(case["family"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if graded["passed"] else 0

    for bucket in by_family.values():
        total = bucket["total"]
        bucket["score"] = round((bucket["passed"] / total) if total else 0.0, 3)

    total = len(details)
    passed = sum(1 for d in details if d["passed"])
    scorecard = {
        "total": total,
        "passed": passed,
        "score": round((passed / total) if total else 0.0, 3),
        "by_family": by_family,
        "calibration": calibration(details),
        "failure_taxonomy": failure_taxonomy(details),
        "details": details,
    }
    logger.info("reasoning evals complete: %d/%d passed (%.1f%%)",
                passed, total, scorecard["score"] * 100)
    return scorecard
