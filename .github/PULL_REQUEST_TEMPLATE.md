## What this changes

<!-- One paragraph. Link the issue if there is one. -->

## Why

<!-- The behaviour that is wrong or missing today. -->

## How it was verified

- [ ] `pytest -q` is green
- [ ] `ruff check src tests` and `ruff format --check src tests` are clean
- [ ] `mypy src` is clean
- [ ] `bandit -c pyproject.toml -r src` is clean
- [ ] the routes I touched were exercised against a booted `wsgi.py`, not only in tests

## Notes for the reviewer

<!-- Anything that is deliberately out of scope, or a trade-off worth arguing about. -->
