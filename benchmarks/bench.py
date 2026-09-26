"""Micro-benchmarks for agent-guardian.

Measures the overhead the governance wrapper adds, so the README can quote
honest numbers instead of adjectives. All measurements use the standard
library only.

Run from the repo root::

    pip install -e .
    python benchmarks/bench.py [--calls N] [--appends N]

Typical results on a shared Linux VM (your hardware will vary — run it
yourself):

    | benchmark                       | result              |
    |---------------------------------|---------------------|
    | guarded call overhead¹          | ~250–600 µs         |
    | audit append throughput         | ~2,000–7,000 app/s  |
    | red-team eval suite (12 prompts)| ~2–6 ms             |
"""

import argparse
import logging
import os
import statistics
import sys
import tempfile
import time

# Benchmarks measure the machine, not the loggers: keep the library's
# warning logs (denied red-team prompts are *expected* here) off stderr.
logging.disable(logging.CRITICAL)

# Allow running from a bare checkout without installing first.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from agent_guardian import (
    AuditLog,
    BudgetConfig,
    PolicyEngine,
    run_evals,
    wrap,
)


def _trivial_agent(prompt: str) -> str:
    return "ok"


def bench_wrap_overhead(calls: int = 2000) -> float:
    """Median per-call overhead (µs) of wrap() vs. the bare agent.

    This is the *full* guarded-call cost: input policy check, budget
    accounting, output policy check, and one fsync'd audit append.  The
    audit fsync dominates — see :func:`bench_audit_throughput`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        guarded = wrap(_trivial_agent,
                       policy=PolicyEngine(),
                       budgets=BudgetConfig(),
                       audit_path=os.path.join(tmp, "bench.jsonl"))

        # Warm up (imports, first-compile, file creation).
        for _ in range(50):
            guarded("warmup")
            _trivial_agent("warmup")

        bare = time.perf_counter()
        for i in range(calls):
            _trivial_agent(f"prompt {i}")
        bare_s = time.perf_counter() - bare

        guarded_t = time.perf_counter()
        for i in range(calls):
            guarded(f"prompt {i}")
        guarded_s = time.perf_counter() - guarded_t

    return max(0.0, (guarded_s - bare_s) / calls) * 1e6


def bench_audit_throughput(appends: int = 2000) -> float:
    """Sustained audit-log appends per second (fsync included)."""
    with tempfile.TemporaryDirectory() as tmp:
        log = AuditLog(os.path.join(tmp, "bench.jsonl"))
        for _ in range(50):  # warm up
            log.append("warmup", {"i": 0})
        start = time.perf_counter()
        for i in range(appends):
            log.append("agent_call", {"i": i, "prompt_chars": 24,
                                      "output_chars": 2})
        elapsed = time.perf_counter() - start
    return appends / elapsed if elapsed > 0 else float("inf")


def bench_eval_suite(repeats: int = 5) -> float:
    """Median wall-clock seconds for the 12-prompt red-team pack."""
    with tempfile.TemporaryDirectory() as tmp:
        guarded = wrap(_trivial_agent,
                       policy=PolicyEngine(),
                       budgets=BudgetConfig(),
                       audit_path=os.path.join(tmp, "bench.jsonl"))
        run_evals(guarded)  # warm up
        samples = []
        for _ in range(repeats):
            start = time.perf_counter()
            run_evals(guarded)
            samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def run(calls: int = 2000, appends: int = 2000,
        repeats: int = 5) -> dict:
    """Run all benchmarks; return ``{name: value}`` (see module docstring)."""
    return {
        "wrap_overhead_us": bench_wrap_overhead(calls),
        "audit_appends_per_sec": bench_audit_throughput(appends),
        "eval_suite_seconds": bench_eval_suite(repeats),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", type=int, default=2000)
    parser.add_argument("--appends", type=int, default=2000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args(argv)

    results = run(args.calls, args.appends, args.repeats)
    rows = [
        ("guarded call overhead¹",
         f"~{results['wrap_overhead_us']:.0f} µs"),
        ("audit append throughput",
         f"~{results['audit_appends_per_sec']:,.0f} appends/sec"),
        ("red-team eval suite (12 prompts)",
         f"~{results['eval_suite_seconds']:.3f} s"),
    ]
    print()
    print("| benchmark                       | result              |")
    print("|---------------------------------|---------------------|")
    for name, value in rows:
        print(f"| {name:<31} | {value:<19} |")
    print()
    print("Measured on this machine just now — run `python benchmarks/bench.py`")
    print("on your own hardware.")
    print()
    print("¹ Full guarded-call cost: input policy + budget accounting + output")
    print("  policy + one fsync'd audit append. The fsync dominates; see")
    print("  DESIGN.md §4 (D6) for the durability/latency tradeoff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
