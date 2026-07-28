## What this changes

<!-- One reviewable unit. Link the issue if one exists. -->

## Why

## Checklist

- [ ] Tests land with the change (synthetic data only) and `pytest -q` is green
- [ ] `ruff check src tests` is clean
- [ ] `python scripts/personal_gate.py` is clean (no private content)
- [ ] Schema changes (if any) updated `schema.py` + templates + emitting skills together, with a migration note
- [ ] Docs updated where behavior changed (README / wiki page)
- [ ] Honest scoping: anything specified but NOT done is called out below

## Not done / out of scope
