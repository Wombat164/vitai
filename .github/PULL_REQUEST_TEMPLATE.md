## What this changes

<!-- One reviewable unit. Link the issue if one exists. -->

## Why

## Checklist

- [ ] Tests land with the change (synthetic data only) and `pytest -q` is green
- [ ] `ruff check .` is clean (everything, not just `src` and `tests`)
- [ ] `python scripts/personal_gate.py` is clean (no private content)
- [ ] The other gates are clean: `boundary_gate.py`, `contract_literal_gate.py`,
      `dependency_gate.py`, `changelog_gate.py`, `pin_gate.py` - all under
      `scripts/`, and all also run inside `pytest -q`
- [ ] `scripts/vacuity_gate.py` is clean - the one gate `pytest -q` cannot run,
      so run `coverage run --source=tests -m pytest -q` first. A new test that
      executes none of its own assertions passes and guards nothing (#424)
- [ ] Schema changes (if any) updated `schema.py` + templates + emitting skills together, with a migration note
- [ ] Docs updated where behavior changed (README / wiki page)
- [ ] Honest scoping: anything specified but NOT done is called out below

## Not done / out of scope
