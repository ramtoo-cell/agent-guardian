# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅        |
| 0.1.x   | ✅        |

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.** Instead, use
GitHub's private vulnerability reporting on the
[agent-guardian repo](https://github.com/ramtoo-cell/agent-guardian/security/advisories/new),
or email the maintainer via the address on
[their profile](https://github.com/ramtoo-cell).

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce (a minimal script is ideal)
- The version you're running (`pip show agent-guardian`)

You can expect an acknowledgment within 72 hours and a fix or mitigation
plan within 14 days for confirmed issues. This is a side project maintained
by one person; timelines are best-effort but reports are taken seriously.

## Scope notes (read before reporting)

agent-guardian is a **detective/preventive control layer**, not a security
boundary. The following are documented limitations, not vulnerabilities:

- **Prompt-injection heuristics can be bypassed.** They are regex-based and
  documented as best-effort (`deny_on_injection` is a knob, not a proof).
  A novel jailbreak evading them is expected behavior, not a CVE.
- **The audit log is tamper-evident, not tamper-proof.** Anyone with write
  access to the log file can rewrite history from a new genesis; `verify_log`
  detects edits to an *existing* chain. See `DESIGN.md` §6 for the full
  threat model and mitigation guidance (write-once storage, off-host copies).
- **Token estimates are approximate** (±30% on English prose). They are
  guardrail-grade by design; pass an exact `tokenizer` for billing use.
- **Refusal detection in evals is string-heuristic.** It measures the
  wrapper's behavior, not the model's safety.

Reports about these documented behaviors will be closed as wontfix with a
pointer to `DESIGN.md` — which is exactly why the threat model is written
down.
