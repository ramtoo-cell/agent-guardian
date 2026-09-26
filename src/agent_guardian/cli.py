"""Command-line interface for agent-guardian.

Subcommands
-----------
``audit``
    Run the built-in red-team eval pack against an agent callable
    (``--target module:func``), through the governance wrapper, and write a
    Markdown governance report.
``verify-log``
    Verify the hash chain of an audit log.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any, Callable, List, Optional

from .audit import verify_log
from .budgets import BudgetConfig, BudgetEnforcer
from .evals import RED_TEAM_PACK, run_evals
from .guardian import wrap
from .policies import PolicyEngine
from .report import render_report


def load_target(target: str) -> Callable[..., str]:
    """Import ``module:attr`` and return the referenced callable."""
    if ":" not in target:
        raise ValueError(
            f"target must look like 'module:func', got {target!r}")
    module_name, attr = target.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, attr)
    if not callable(func):
        raise TypeError(f"{target!r} is not callable")
    return func


def load_policy(path: Optional[str]) -> PolicyEngine:
    """Load a policy from ``policy.json`` (or return the default engine)."""
    if path is None:
        return PolicyEngine()
    return PolicyEngine.from_json(path)


def cmd_audit(args: argparse.Namespace) -> int:
    agent_fn = load_target(args.target)
    policy = load_policy(args.policy)
    budgets = BudgetEnforcer(BudgetConfig(
        max_steps=args.max_steps, max_tokens=args.max_tokens,
        max_cost_usd=args.max_cost, max_latency_seconds=args.max_latency))
    audit_path = args.audit_log or "agent_audit.jsonl"

    guarded = wrap(agent_fn, policy=policy, budgets=budgets,
                   audit_path=audit_path,
                   agent_id=args.target.replace(":", "."))
    scorecard = run_evals(guarded)
    report = render_report(scorecard, audit_path=audit_path,
                           title=f"Agent Governance Report — {args.target}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    print(f"score: {scorecard['passed']}/{scorecard['total']} "
          f"({scorecard['score'] * 100:.1f}%)")
    return 0


def cmd_verify_log(args: argparse.Namespace) -> int:
    result = verify_log(args.path)
    print(result.message)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-guardian",
        description="Governance sidecar for AI agents: audit an agent or "
                    "verify an audit log.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="eval an agent and write a report")
    audit.add_argument("--target", required=True,
                       help="agent callable as module:func, e.g. mybot:agent")
    audit.add_argument("--policy", default=None,
                       help="path to policy.json (default: built-in policy)")
    audit.add_argument("--out", default=None,
                       help="write the Markdown report to this file")
    audit.add_argument("--audit-log", default=None,
                       help="audit log path (default: agent_audit.jsonl)")
    audit.add_argument("--max-steps", type=int, default=None)
    audit.add_argument("--max-tokens", type=int, default=None)
    audit.add_argument("--max-cost", type=float, default=None)
    audit.add_argument("--max-latency", type=float, default=None)
    audit.set_defaults(func=cmd_audit)

    verify = sub.add_parser("verify-log", help="verify an audit log's chain")
    verify.add_argument("--path", required=True, help="audit .jsonl path")
    verify.set_defaults(func=cmd_verify_log)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point (installed as the ``agent-guardian`` console script)."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, TypeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
