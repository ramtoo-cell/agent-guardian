# agent-guardian

**A governance sidecar for AI agents.** Wrap any Python agent callable and get policy enforcement, budget guardrails, a tamper-evident audit log, and built-in safety evals — with zero dependencies.

## Why

Agents that browse, write code, and spend money need the same controls any production system gets: who is allowed to do what, how much they may spend, and an audit trail nobody can quietly rewrite. agent-guardian puts those controls around *your* agent in a few lines, without changing how the agent works.

## Install

```bash
pip install agent-guardian
```

(Requires Python 3.9+. No dependencies — standard library only.)

## Quickstart

```python
from agent_guardian import PolicyEngine, BudgetConfig, wrap

policy = PolicyEngine(
    blocked_phrases=["drop table"],  # never allow these, in or out
    redact_pii=True,                 # mask emails, phones, SSNs, API keys
)
budgets = BudgetConfig(max_steps=10, max_tokens=4000, max_cost_usd=0.50)

def my_agent(prompt: str) -> str:
    return f"answer to: {prompt}"

safe = wrap(my_agent, policy=policy, budgets=budgets,
            audit_path="audit.jsonl")

print(safe("Hello, world"))
print(safe("my email is bob@example.com"))  # PII redacted before the agent sees it
safe("drop table users")                    # raises PolicyViolation
```

Or with the decorator:

```python
from agent_guardian import guard

@guard(policy=PolicyEngine(blocked_phrases=["drop table"]),
       budgets=BudgetConfig(max_steps=10))
def my_agent(prompt: str) -> str:
    ...
```

## What you get

| Module | What it does |
|---|---|
| `policies` | `PolicyEngine`: declarative allow/deny rules, blocked phrases, PII redaction (emails, phones, SSNs, credit cards, API keys), prompt-injection heuristics. `check(text) -> PolicyDecision`. |
| `budgets` | `BudgetEnforcer`: caps on steps, tokens (≈4 chars/token), USD cost, and latency. Raises `BudgetExceeded` with details. |
| `audit` | `AuditLog`: hash-chained (SHA-256) JSONL log of every input, output, and decision. `verify_log(path)` detects tampering. |
| `evals` | `run_evals(agent_fn)`: built-in red-team pack (jailbreak, prompt-injection, PII-extraction attempts + benign controls) → scorecard dict. |
| `guardian` | `wrap(agent_fn, ...)` and `@guard(...)`: the one-call integration. |
| `report` | `render_report(scorecard, audit_path)` → Markdown governance report. |

## CLI

Audit any importable agent and write a governance report:

```bash
agent-guardian audit --target mybot:agent --out report.md
agent-guardian audit --target mybot:agent --policy policy.json --max-cost 1.00
agent-guardian verify-log --path audit.jsonl
```

`policy.json` example:

```json
{
  "blocked_phrases": ["drop table", "rm -rf"],
  "redact_pii": true,
  "detect_injection": true,
  "max_chars": 8000,
  "rules": [
    {"id": "no-prod-deploys", "effect": "deny",
     "contains": ["deploy"], "context_equals": {"env": "prod"}}
  ]
}
```

## API reference

```python
from agent_guardian import (
    PolicyEngine, PolicyDecision, PolicyViolation,   # policies
    BudgetConfig, BudgetEnforcer, BudgetExceeded,    # budgets
    AuditLog, verify_log,                            # audit
    run_evals, RED_TEAM_PACK,                        # evals
    wrap, guard,                                     # main API
    render_report,                                   # reporting
)
```

- `PolicyEngine(blocked_phrases=[...], redact_pii=True, detect_injection=True, deny_on_injection=True, rules=[...], max_chars=None)` — `.check(text, context=None) -> PolicyDecision`; `.check_or_raise(text) -> str`; `.from_json("policy.json")`.
- `BudgetEnforcer(BudgetConfig(max_steps, max_tokens, max_cost_usd, max_latency_seconds))` — `.start()`, `.check_step()`, `.record_text(text, cost_usd=0.0)`, `.record_tokens(n, cost_usd=0.0)`, `.snapshot()`.
- `AuditLog(path, agent_id="agent")` — `.append(kind, payload)`; `verify_log(path) -> AuditVerification(ok, records_checked, first_bad_seq, message)`.
- `run_evals(agent_fn, pack=None)` → `{"total", "passed", "score", "by_category", "details"}`.
- `wrap(agent_fn, *, policy=None, budgets=None, audit_path="agent_audit.jsonl", agent_id=None, check_output=True)`.
- `render_report(scorecard, audit_path=None, title=...) -> str`.

## Design notes

- **Zero dependencies.** Everything is standard library, so the sidecar can be audited and vendored anywhere.
- **Deny-by-default posture for attacks, allow-by-default for content.** The engine blocks what you name (phrases, rules, injections) and redacts PII instead of refusing outright — the agent keeps working on safe content.
- **Tamper-evident, not tamper-proof.** The hash chain makes silent edits detectable; pair it with write-once storage for stronger guarantees.
- **Token counts are estimates.** Budgets use a documented ≈4-chars-per-token heuristic — good for guardrails, not for billing.

## License

MIT © 2026 Ramkumar Bharathan
