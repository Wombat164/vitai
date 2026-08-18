# Contributing

Thanks for considering a contribution. vitai is small on purpose; the bar for
new code is that it defends the three-layer design (private content /
deterministic engine / LLM skills), not that it adds surface.

## Development setup

```bash
git clone https://github.com/Wombat164/vitai.git
cd vitai
pip install -e . -r requirements-dev.txt
pytest -q          # 3000+ tests, ~2.5 minutes
ruff check .       # everything, not just src and tests
```

`requirements-dev.txt` pins `ruff` and `pytest` to the versions CI uses. Install
from it rather than by name: a ruff release adding a rule turns `main` red with
nothing having changed, and a lint you cannot reproduce locally is a lint you
cannot fix locally. `python scripts/pin_gate.py` holds this block, the
workflows and the requirements files to each other.

Python >= 3.11, stdlib only at runtime - a PR that adds a runtime dependency
needs a very good reason stated in the PR body.

## The rules that get PRs merged

1. **Tests land with the change.** New behavior, new test; fixed bug, test
   that would have caught it. All test data is synthetic.
2. **No personal data, ever.** No real names, measurements, locations,
   providers - not in code, tests, fixtures, examples, or commit messages.
   CI runs `scripts/personal_gate.py` (hash-based, blocking) plus a secrets
   scan. If the gate fires, your change contains something private.
3. **The engine stays deterministic, and the build is network-free.** Nothing
   is fetched while a build runs; no wall-clock nondeterminism in outputs; no
   LLM in the number path. Any capability that does touch the network is
   capture-side, gated by the permission model (default deny, per use,
   recorded), never runs during a build, and its results enter the record as
   claims with provenance. Skills (markdown) may be judgment-heavy; `src/`
   may not.
4. **Append-only is sacred.** Nothing may edit, reorder or rewrite a data
   line; corrections flow through `supersedes`.
5. **Schema changes touch three places together**: `schema.py`, the
   templates, and the skills that emit data - plus a migration note.
6. **Style**: ruff-clean (rules pinned in pyproject), ASCII punctuation in
   prose (no smart quotes, no em-dashes), plain hyphens.

## Pull requests

- Branch from `main`, keep the PR a single reviewable unit.
- Fill the PR template honestly - say what is NOT done as plainly as what is.
- CI must be green: hygiene (ruff + personal gate), the test matrix
  (Linux + Windows, Python 3.11/3.13), and `vacuity`.
- **`scripts/vacuity_gate.py` is the one gate `pytest -q` does not run**, since
  it measures the completed run. If you add a test, run it once locally:
  `coverage run --source=tests -m pytest -q && python scripts/vacuity_gate.py`.
  It reports a test that ran and executed none of its own assertions - which
  passes, and says nothing about the property it names (#424).
- Squash-merge is the repo policy; write the PR title as the future commit.
- **Do not edit `CHANGELOG.md`.** Add `changelog.d/<issue>.<category>.md`
  instead - one file per change, named for the issue the PR closes. Every PR
  used to append under the same heading, so any two open at once conflicted on
  the same lines; it happened four times in two days. See
  `changelog.d/README.md`. A maintainer folds the fragments in at release with
  `python scripts/changelog_gate.py --assemble`.

## Skills and templates

Skill files (`skills/*/SKILL.md`) are part of the product. Changes there are
reviewed for coaching safety: never moralise, never program around an
unassessed medical red flag, respect settled decisions. See the voice
principles in `assets/BRAND.md`.

## Brand and assets

Brand SVGs are governed by `assets/BRAND.md` (master mark, palette,
regeneration commands). Do not hand-edit outlined wordmark paths; edit the
`.text.svg` sources and re-outline.

## Docs

User-facing behavior changes update `README.md` and, when the docs site
exists for that area, the matching page under `wiki/content/`.
