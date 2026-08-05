# CLAUDE.md - developing vitai

Instructions for working on the vitai TOOL (this public repo). For operating
inside an athlete's content repo, use the content repo's own CLAUDE.md (the
template ships in `src/vitai/templates/`).

## Non-negotiables

- **This repo is PUBLIC. No personal data, ever.** No real names, real
  measurements, real locations, real device IDs - not in code, comments,
  tests, fixtures, examples, or commit messages. Test data is synthetic.
- **The engine stays deterministic and stdlib-only.** No dependencies, no
  wall-clock nondeterminism in outputs (report generation takes an injectable
  `today`). Same input, same output.
- **The BUILD is network-free.** Nothing is fetched while a build runs: same
  input, same output. Network exists only in capture-side tools, is gated by
  the permission model (default deny, per use, recorded), never runs during a
  build, and its results enter the record as CLAIMS with provenance, never as
  derived truth.

  *Reworded 2026-08-05 (#264). The flat "no network" was contradicted by three
  decisions already taken: #84's settled resolver ladder including
  `hosted-coarse` and `hosted`, #224's outward asking channel, and G46's gated
  live lookups. The rationale was always that the BUILD is a function of the
  record; the old wording covered the whole engine and made ordered work a
  paper violation.*
- **No LLM in the number path.** Anything numeric the athlete will be judged
  or coached on is computed here, in reviewable Python, not by a model. The
  skills READ engine outputs.
- **Append-only is sacred.** Nothing in this codebase may edit, reorder, or
  rewrite a data line. Corrections flow through `supersedes`.

## Layout and conventions

- `src/vitai/` - engine + CLI. Python >= 3.11 (tomllib), type-hinted,
  ruff line-length 100.
- `skills/<name>/SKILL.md` - Claude Code compatible skill packages; keep
  them harness-agnostic in wording and lean (target under ~80 lines).
- `src/vitai/templates/` - what `vitai init` stamps; bracketed placeholders,
  synthetic example values only.
- Tests are pytest, in `tests/`, synthetic data only, and must pass with
  `pip install -e . && pytest -q`.
- Schema changes touch three places together: `schema.py`, the templates,
  and the skills that emit data. A schema change without a migration note in
  the README table is incomplete.

## Design guardrails (learned in the founding deployment)

- Weekly maintenance for the athlete must stay under ~3 minutes; every
  feature that adds recurring athlete effort is presumed wrong.
- Derive, never store, anything computable (pace, averages, totals).
- No server, no daemon, no app until the plain-text record has proven
  durable - and any future app reads this schema rather than inventing one.
