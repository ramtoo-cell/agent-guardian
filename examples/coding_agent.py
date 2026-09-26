"""Example 2: coding agent under strict cost/latency budgets.

A mock coding assistant is wrapped with tight budgets: a handful of steps, a
small token allowance, and a simulated per-call dollar cost (recorded with
``record_tokens(..., cost_usd=...)``). When the money runs out, the agent is
cut off mid-loop — the standard pattern for keeping LLM spend predictable.

Run from the repo root::

    pip install -e .
    python examples/coding_agent.py
"""

import os
import sys
import tempfile

# Allow running from a bare checkout without installing first.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

from agent_guardian import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceeded,
    PolicyEngine,
    estimate_tokens,
    wrap,
)

COST_PER_CALL_USD = 0.012  # pretend price of one model call


def coding_agent(prompt: str) -> str:
    """Mock coding assistant (stands in for your real agent)."""
    if "quicksort" in prompt.lower():
        return ("def quicksort(xs):\n"
                "    if len(xs) <= 1: return xs\n"
                "    p = xs[0]\n"
                "    return quicksort([x for x in xs[1:] if x < p]) "
                "+ [p] + quicksort([x for x in xs[1:] if x >= p])")
    return f"# TODO: implement {prompt[:40]!r}\npass"


def main() -> int:
    policy = PolicyEngine.from_file(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "policies", "strict_policy.json"))

    with tempfile.TemporaryDirectory() as tmp:
        audit_path = os.path.join(tmp, "coding_audit.jsonl")
        enforcer = BudgetEnforcer(BudgetConfig(max_steps=5,
                                              max_cost_usd=0.03,
                                              max_latency_seconds=30.0))
        safe = wrap(coding_agent, policy=policy, budgets=enforcer,
                    audit_path=audit_path, agent_id="coding-bot")

        tasks = [
            "write quicksort in python",
            "write a binary search",
            "write a trie implementation",
            "write an LRU cache",          # the money runs out here
            "write a bloom filter",
        ]
        for task in tasks:
            try:
                # Charge this call: the enforcer tracks spend separately
                # from the token heuristic (per-request provider billing).
                answer = safe(task)
                enforcer.record_cost(COST_PER_CALL_USD)
                tokens = estimate_tokens(task) + estimate_tokens(answer)
                print(f"✓ {task} "
                      f"(~{tokens} tok, ${COST_PER_CALL_USD:.3f})")
            except BudgetExceeded as exc:
                print(f"✗ {task}\n  budget cut the agent off: {exc}")
                break

        snap = enforcer.snapshot()
        print("\nfinal budget snapshot:")
        for key in ("steps", "tokens", "cost_usd", "elapsed_seconds"):
            print(f"  {key}: {snap[key]}")
        print(f"phase latencies (ms): {safe.last_phase_latencies}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
