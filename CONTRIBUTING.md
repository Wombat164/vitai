# Contributing

Thanks for considering a contribution. vitai is small on purpose; the bar for
new code is that it defends the three-layer design (private content /
deterministic engine / LLM skills), not that it adds surface.

## Development setup

```bash
git clone https://github.com/Wombat164/vitai.git
cd vitai
pip install -e . pytest ruff
pytest -q          # 17+ tests, seconds
ruff check src tests
```

Python >= 3.11, stdlib only at runtime - a PR that adds a runtime dependency
needs a very good reason stated in the PR body.

## The rules that get PRs merged

1. **Tests land with the change.** New behavior, new test; fixed bug, test
   that would have caught it. All test data is synthetic.
2. **No personal data, ever.** No real names, measurements, locations,
   providers - not in code, tests, fixtures, examples, or commit messages.
   CI runs `scripts/personal_gate.py` (hash-based, blocking) plus a secrets
   scan. If the gate fires, your change contains something private.
3. **The engine stays deterministic.** No network, no wall-clock
   nondeterminism in outputs, no LLM in the number path. Skills (markdown)
   may be judgment-heavy; `src/` may not.
4. **Append-only is sacred.** Nothing may edit, reorder or rewrite a data
   line; corrections flow through `supersedes`.
5. **Schema changes touch three places together**: `schema.py`, the
   templates, and the skills that emit data - plus a migration note.
6. **Style**: ruff-clean (rules pinned in pyproject), ASCII punctuation in
   prose (no smart quotes, no em-dashes), plain hyphens.

## Pull requests

- Branch from `main`, keep the PR a single reviewable unit.
- Fill the PR template honestly - say what is NOT done as plainly as what is.
- CI must be green: hygiene (ruff + personal gate) and the test matrix
  (Linux + Windows, Python 3.11/3.13).
- Squash-merge is the repo policy; write the PR title as the future commit.

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
