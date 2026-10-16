# Changelog

All notable changes to agent-guardian are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `agent_guardian.reasoning_evals`: 30 hand-written conceptual-reasoning
  eval cases across three families — contract-clause interpretation
  (allow/deny/ambiguous with cited rationale), policy trade-offs (graded
  on reasoning quality, verdict open), and incentive/mechanism-design
  analysis. `run_reasoning_evals(agent_fn)` returns a scorecard with pass
  rate, per-family breakdown, confidence-vs-accuracy calibration, and a
  failure taxonomy. Grading is keyword-heuristic (documented limitations);
  scores are a regression signal, not a certificate. Also exported at top
  level as `CONCEPTUAL_REASONING_PACK` / `run_reasoning_evals`.

## [0.2.0] - 2026-09-26

### Added
- `agent_guardian.exceptions`: single-rooted exception taxonomy
  (`AgentGuardianError` base; `PolicyViolation`, `BudgetExceeded`,
  `AuditError`, `ConfigurationError`, `TargetLoadError`). Old import paths
  (`policies.PolicyViolation`, `budgets.BudgetExceeded`) keep working.
- `PolicyEngine.from_file()`: load policies from JSON or YAML files
  (YAML needs optional PyYAML); `from_json()` retained as an alias.
- `BudgetConfig.from_env()`: `AGENT_GUARDIAN_MAX_STEPS / _MAX_TOKENS /
  _MAX_COST_USD / _MAX_LATENCY_SECONDS` overrides; CLI flags take precedence.
- `BudgetEnforcer.record_cost()` for per-request provider billing, and an
  optional exact `tokenizer` callable for billing-grade counts.
- Thread-safe `AuditLog`: instance lock for threads, advisory `flock` for
  multi-process writers, tail re-read under lock, `fsync` per append.
- Per-phase latency tracking in `wrap()` (`phase_latency_ms` in audit
  payloads + `guarded.last_phase_latencies`).
- `examples/`: three runnable real-world demos (support bot, coding agent,
  red-team) plus sample YAML/JSON policies.
- `benchmarks/bench.py`: guarded-call overhead, audit throughput, eval
  runtime.
- `DESIGN.md`: full design doc (goals, architecture, tradeoffs, threat
  model).
- Repo hygiene: GitHub Actions CI (3.9–3.12, ruff, coverage, examples,
  build), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- `render_report()` accepts an optional budget snapshot section.

### Changed
- Smarter zero-dependency token estimator (word-based with CJK handling,
  ~±30% of BPE on English prose; documented in `DESIGN.md`).
- Google-style docstrings and structured `logging` throughout; no `print`
  in library code.

## [0.1.0] - 2026-09-26

Initial release: `wrap()`/`@guard` governance wrapper, `PolicyEngine`
(blocklists, rules, injection heuristics, PII redaction), `BudgetEnforcer`
(steps/tokens/cost/latency), hash-chained JSONL audit log with
`verify_log`, 12-prompt red-team eval pack, Markdown report renderer, and
the `agent-guardian` CLI (`audit`, `verify-log`).
