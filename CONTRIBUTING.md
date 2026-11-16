# Contributing

Thanks for helping improve quant-mcp.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

All of these must pass. CI runs the same checks.

```bash
ruff check src tests app.py
ruff format --check src tests app.py     # or run `ruff format` to fix
mypy
pytest -m "not network"
python scripts/generate_tool_docs.py --check   # run without --check to regenerate docs/tools.md
```

## Guidelines

- **Add tests with every behaviour change.** Financial code needs known-value tests, property tests, or reference
  implementations, not just "it runs".
- **Validate inputs.** New tools must go through `quant_mcp.validation` and raise `ValidationError` for bad input.
- **Keep the calculation core pure.** No I/O in `calculations.py`, `optimization.py` or `backtest.py`.
- **Document units.** State whether a rate is annual, whether a return is simple or log, and how theta and vega are scaled.
- **Never log tool inputs.** They may contain proprietary data.
- **Update `CHANGELOG.md`** under "Unreleased".

## Commit and PR conventions

- Small, focused PRs. Describe what changed and why.
- Conventional-style commit subjects are appreciated (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
