# Contributing to agent-guardian

Thanks for your interest — this is a small, carefully-scoped library, and
contributions that keep it that way are welcome.

## Ground rules

1. **Stdlib-only core.** The library must install with zero dependencies.
   New integrations (PyYAML, tiktoken, OTel) belong behind optional imports
   with clear error messages, never hard requirements.
2. **Fail closed.** A new guardrail must deny by default on uncertainty;
   permissive modes are opt-in and loudly documented.
3. **Evidence first.** Any new decision the wrapper makes must land in the
   audit log with enough context to reconstruct it later.
4. **Honest docs.** If a heuristic has known failure modes, document them
   in the docstring *and* the README's limitations section.

## Development setup

```bash
git clone https://github.com/ramtoo-cell/agent-guardian
cd agent-guardian
pip install -e ".[dev]"   # ruff, build, coverage, pyyaml
```

## Checks (all must pass)

```bash
ruff check src tests examples benchmarks   # lint
coverage run -m unittest discover -s tests  # tests
coverage report                             # must stay >= 85%
python examples/customer_support.py         # examples still run
python examples/coding_agent.py
python examples/red_team.py
python benchmarks/bench.py --calls 100 --appends 100 --repeats 1
python -m build                             # packaging still works
```

CI runs the same checks on Python 3.9–3.12.

## Style

- Google-style docstrings (`Args:` / `Returns:` / `Raises:`) on all public
  APIs; type hints everywhere.
- `logging`, not `print`, in library code (the CLI may print).
- Keep the exception taxonomy rooted at `AgentGuardianError`; don't invent
  parallel hierarchies.
- Update `CHANGELOG.md` under `[Unreleased]` and add tests for new
  behavior. Aim to keep coverage at or above the configured floor.

## Design proposals

For anything beyond a bugfix, open an issue first describing the problem,
the proposed change, and the tradeoff — or send a PR that updates
`DESIGN.md`. This repo keeps its design doc living and versioned.
