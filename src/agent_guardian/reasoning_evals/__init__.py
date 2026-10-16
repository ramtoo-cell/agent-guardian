"""Conceptual-reasoning evaluations for agent callables.

Thirty hand-written cases across three families — contract-clause
interpretation, policy trade-offs, and incentive/mechanism-design
analysis — aimed at the kind of structured reasoning Anthropic's
Conceptual Reasoning Fellowship targets (philosophy, cognitive science,
economics, policy, law)::

    from agent_guardian.reasoning_evals import run_reasoning_evals

    scorecard = run_reasoning_evals(my_model_fn)
    print(scorecard["score"], scorecard["failure_taxonomy"])

Grading is keyword-heuristic (see :mod:`harness`); scores are a
regression signal, not a certificate.  Cases live in :mod:`cases`.
"""

from .cases import (
    CONCEPTUAL_REASONING_PACK,
    FAMILIES,
    cases_by_family,
    get_case,
)
from .harness import (
    CALIBRATION_BINS,
    FORMAT_INSTRUCTIONS,
    calibration,
    failure_taxonomy,
    grade_case,
    parse_response,
    run_reasoning_evals,
)

__all__ = [
    "CALIBRATION_BINS",
    "CONCEPTUAL_REASONING_PACK",
    "FAMILIES",
    "FORMAT_INSTRUCTIONS",
    "calibration",
    "cases_by_family",
    "failure_taxonomy",
    "get_case",
    "grade_case",
    "parse_response",
    "run_reasoning_evals",
]
