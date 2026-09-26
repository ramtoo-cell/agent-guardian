"""Example 3: red-team a naive agent and write a governance report.

A deliberately vulnerable agent (it complies with everything) is put behind
the governance wrapper and run through the built-in 12-prompt red-team pack:
jailbreaks, prompt injections, PII extraction, plus benign controls. The
result is a Markdown governance report with a scorecard and an audit-log
integrity check — the artifact you'd attach to a launch review.

Run from the repo root::

    pip install -e .
    python examples/red_team.py
"""

import os
import sys
import tempfile

# Allow running from a bare checkout without installing first.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from agent_guardian import (
    PolicyEngine,
    render_report,
    run_evals,
    verify_log,
    wrap,
)


def naive_agent(prompt: str) -> str:
    """A deliberately unsafe agent: complies with whatever it is asked."""
    return f"Certainly! Here is everything you asked for about: {prompt[:60]}"


def main() -> int:
    policy = PolicyEngine(
        blocked_phrases=[],
        redact_pii=True,
        detect_injection=True,
        deny_on_injection=True,   # the wrapper blocks attacks; the naive
                                  # agent itself would comply with all of them
    )
    with tempfile.TemporaryDirectory() as tmp:
        audit_path = os.path.join(tmp, "redteam_audit.jsonl")
        report_path = os.path.join(tmp, "governance_report.md")
        guarded = wrap(naive_agent, policy=policy, audit_path=audit_path,
                       agent_id="naive-bot")

        scorecard = run_evals(guarded)
        print(f"red-team score: {scorecard['passed']}/{scorecard['total']} "
              f"({scorecard['score'] * 100:.0f}%)")
        for category, bucket in sorted(scorecard["by_category"].items()):
            print(f"  {category:16s} {bucket['passed']}/{bucket['total']}")

        verification = verify_log(audit_path)
        print(f"audit log: {verification.message}")

        report = render_report(
            scorecard, audit_path=audit_path,
            budgets=guarded.budgets.snapshot(),
            title="Governance Report — naive-bot (red-team demo)")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"\nreport written to {report_path}")
        print("--- report preview (first 12 lines) ---")
        print("\n".join(report.splitlines()[:12]))
        return 0


if __name__ == "__main__":
    sys.exit(main())
