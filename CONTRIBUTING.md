# Contributing to CIRecon

## Running tests locally

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Memory persistence

CIRecon tracks issue history across runs using a memory file at `/tmp/cirecon-memory/memory.json`.
To preserve memory between workflow runs, add the `actions/cache` step before the CIRecon step:

```yaml
- uses: actions/cache@v4
  with:
    path: /tmp/cirecon-memory
    key: cirecon-memory-${{ github.repository }}
```

Without the cache step, memory resets on every run and issue run counts will not accumulate.

## Adding a new rule

1. Create a new check function in `cirecon/rule_engine.py` that takes `(path: str, content: str) -> list[Issue]`
2. Import and add the function to `run_all_checks()` in the same file
3. Create a fixture YAML file in `tests/fixtures/` that triggers the new rule
4. Add tests in `tests/test_rule_engine.py` following the existing patterns
5. If the rule is auto-fixable, add a fix handler in `cirecon/fix_applier.py`

## PR guidelines

- Keep changes focused — one rule or fix per PR
- Include tests for every new check and fix
- Run `pytest tests/ -v` before opening the PR

## Code style

- Format with [Black](https://github.com/psf/black)
- Lint with [Ruff](https://github.com/astral-sh/ruff)
