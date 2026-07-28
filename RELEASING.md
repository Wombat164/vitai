# Releasing

## Version lockstep

Two files carry the version and must match before tagging:
`pyproject.toml` (`version = ...`) and `src/vitai/__init__.py`
(`__version__`).

## Pre-release checks

```bash
pytest -q
ruff check src tests
python scripts/personal_gate.py
```

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
