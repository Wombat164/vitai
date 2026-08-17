# Releasing

## Version lockstep

Two files carry the version and must match before tagging:
`pyproject.toml` (`version = ...`) and `src/vitai/__init__.py`
(`__version__`).

## Pre-release checks

Everything CI's `hygiene` job runs, in the order it runs it. Three of these
were missing from this list, which made them CI-only for anyone following it:

```bash
pytest -q
ruff check .
python scripts/personal_gate.py
python scripts/boundary_gate.py
python scripts/contract_literal_gate.py
python scripts/dependency_gate.py
python scripts/changelog_gate.py
python scripts/pin_gate.py
```

`pytest -q` already runs every one of these gates itself, so the list is a
belt-and-braces for a reader who wants each answer separately.
`scripts/pin_gate.py` is what holds this block to `ci.yml`, so a gate added to
one and not the other fails rather than drifts.

Update `CHANGELOG.md`: move entries from Unreleased into a dated version
section.

## Cut

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z - <short description>" --notes "<prose body>"
```

Release-notes style: one-line problem/feature statement, a short prose
paragraph, flat bullets naming config knobs/commands in backticks, close
with a test-count + compatibility line.

## PyPI

`release.yml` builds and `twine check`s on every tag. Actual PyPI publish is
gated behind the repository variable `PYPI_ENABLE=true` and uses Trusted
Publishing (OIDC, `pypi` environment) - no stored token. Before flipping the
variable: claim the `vitai` name on PyPI and register the publisher
(project settings on pypi.org -> publishing -> add GitHub
`Wombat164/vitai`, workflow `release.yml`, environment `pypi`).
