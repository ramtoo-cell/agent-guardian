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
import logging
import sys
from typing import Any, Callable

from .audit import verify_log
from .budgets import BudgetConfig, BudgetEnforcer
from .evals import RED_TEAM_PACK, run_evals
from .exceptions import ConfigurationError, TargetLoadError
from .guardian import wrap
from .policies import PolicyEngine
from .report import render_report

logger = logging.getLogger(__name__)


def load_target(target: str) -> Callable[..., str]:
    """Import ``module:attr`` and return the referenced callable.

    Args:
        target: Import path of the form ``"package.module:attribute"``.

    Returns:
        The referenced callable.

    Raises:
        TargetLoadError: If the target is malformed, cannot be imported,
            or is not callable.
    """
    if ":" not in target:
        raise TargetLoadError(
            f"target must look like 'module:func', got {target!r}")
    module_name, attr = target.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise TargetLoadError(
            f"cannot import module {module_name!r} for target {target!r}: "
            f"{exc}") from exc
    try:
        func = getattr(module, attr)
    except AttributeError as exc:
        raise TargetLoadError(
            f"module {module_name!r} has no attribute {attr!r}") from exc
    if not callable(func):
        raise TargetLoadError(f"{target!r} is not callable")
    return func


def load_policy(path: str | None) -> PolicyEngine:
    """Load a policy file (JSON or YAML), or return the default engine.

    Args:
        path: Path to a ``.json``/``.yaml``/``.yml`` policy file, or
            ``None`` for the built-in default policy.

    Raises:
        ConfigurationError: If the file cannot be loaded.
    """
    if path is None:
        return PolicyEngine()
    return PolicyEngine.from_file(path)


def build_budgets(args: argparse.Namespace) -> BudgetEnforcer:
    """Build a :class:`BudgetEnforcer` from env vars, overridden by flags.

    Precedence: explicit CLI flags win over ``AGENT_GUARDIAN_*``
    environment variables, which win over "no limit".
    """
    config = BudgetConfig.from_env()
    overrides: dict[str, Any] = {
        "max_steps": args.max_steps,
        "max_tokens": args.max_tokens,
        "max_cost_usd": args.max_cost,
        "max_latency_seconds": args.max_latency,
    }
    for field_name, value in overrides.items():
        if value is not None:
            setattr(config, field_name, value)
    logger.debug("budget config: %s", config)
    return BudgetEnforcer(config)


def cmd_audit(args: argparse.Namespace) -> int:
    """Run the ``audit`` subcommand; return the process exit code."""
    agent_fn = load_target(args.target)
    policy = load_policy(args.policy)
    budgets = build_budgets(args)
    audit_path = args.audit_log or "agent_audit.jsonl"

    guarded = wrap(agent_fn, policy=policy, budgets=budgets,
                   audit_path=audit_path,
                   agent_id=args.target.replace(":", "."))
    logger.info("running %d eval prompts against %s",
                len(RED_TEAM_PACK), args.target)
    scorecard = run_evals(guarded)
    report = render_report(scorecard, audit_path=audit_path,
                           budgets=budgets.snapshot(),
                           title=f"Agent Governance Report — {args.target}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    print(f"score: {scorecard['passed']}/{scorecard['total']} "
          f"({scorecard['score'] * 100:.1f}%)")
    logger.info("audit complete: %d/%d passed", scorecard["passed"],
                scorecard["total"])
    return 0


def cmd_verify_log(args: argparse.Namespace) -> int:
    """Run the ``verify-log`` subcommand; return the process exit code."""
    result = verify_log(args.path)
    print(result.message)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the ``agent-guardian`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent-guardian",
        description="Governance sidecar for AI agents: audit an agent or "
                    "verify an audit log.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="eval an agent and write a report")
    audit.add_argument("--target", required=True,
                       help="agent callable as module:func, e.g. mybot:agent")
    audit.add_argument("--policy", default=None,
                       help="path to policy file (.json/.yaml/.yml); "
                            "default: built-in policy")
    audit.add_argument("--out", default=None,
                       help="write the Markdown report to this file")
    audit.add_argument("--audit-log", default=None,
                       help="audit log path (default: agent_audit.jsonl)")
    audit.add_argument("--max-steps", type=int, default=None,
                       help="override AGENT_GUARDIAN_MAX_STEPS")
    audit.add_argument("--max-tokens", type=int, default=None,
                       help="override AGENT_GUARDIAN_MAX_TOKENS")
    audit.add_argument("--max-cost", type=float, default=None,
                       help="override AGENT_GUARDIAN_MAX_COST_USD")
    audit.add_argument("--max-latency", type=float, default=None,
                       help="override AGENT_GUARDIAN_MAX_LATENCY_SECONDS")
    audit.set_defaults(func=cmd_audit)

    verify = sub.add_parser("verify-log", help="verify an audit log's chain")
    verify.add_argument("--path", required=True, help="audit .jsonl path")
    verify.set_defaults(func=cmd_verify_log)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (installed as the ``agent-guardian`` console script).

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 on success, 1 when a verified log is broken,
        2 on usage/configuration errors, 130 on Ctrl-C.
    """
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (TargetLoadError, ConfigurationError,
            ValueError, TypeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
