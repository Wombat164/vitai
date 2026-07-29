---
title: CLI reference
---

All commands run from (or take `--root` pointing at) a content repo.

## vitai init PATH

Stamps a content-repo skeleton: narrative templates, `vitai.toml`, empty
`data/*.jsonl`, `derived/`. Refuses a non-empty target (except `.git`).

## vitai build

`data/*.jsonl` -> `derived/health.db` (SQLite read model, rebuilt from
zero) + `derived/weekly.md` (rollup). Reads thresholds from `vitai.toml`;
an absent threshold disables its verdict rather than guessing a default.
Schema problems are warnings here - `validate` is the strict gate.

## vitai validate

Schema-checks every data line (including superseded ones): missing keys,
unknown keys, bad dates, wrong types, unknown session types, out-of-range
pain scores. Exit 1 on any problem. Fix by APPENDING corrections, never by
editing lines.

## vitai status

One line: latest weight, 7-day average and rate, firing-tripwire count.

## vitai verdicts

Weekly goal-attainment rows as JSONL on stdout - one object per
(week, metric) with `value`, `target` and a closed verdict vocabulary
(`on_target | ahead | behind | no_data`). The same rows live in the read
model's `verdicts` table. Each row also carries the `goal` it serves. This is
the contract a game economy or dashboard consumes; see
[[explanation/platform|the platform page]].

## vitai goals

Where each active goal stands: counted progress against target, percentage,
the dates it was declared and last moved, its motivator, and the recent
per-goal contributions behind the number.

    vitai goals                      # active goals, last 10 contributions
    vitai goals --recent 0           # progress only
    vitai goals --on 2030-05-01      # as the goals stood on that date
    vitai goals --json               # one JSON object per goal, for scripts

Progress is COUNTED progress. For a `guarded` goal that means volume beyond
its ramp guard is reported separately as unbudgeted rather than folded in -
the number reflects what was banked, not what was logged.

A closing section lists policy edits worth a question: a target or threshold
loosened within a week of a week that metric was missed, shown with whatever
reason the athlete recorded. It is a prompt for the coach, not a judgment -
nothing is blocked, and an explained deload is meant to read as one.

## vitai infer (opt-in)

Runs the intelligence layer through a pluggable model backend (your Claude
CLI, or any OpenAI-compatible endpoint like Ollama), configured in the
`[inference]` section of `vitai.toml`. The model reads the rollup and
recent data and emits candidate knowledge; every line is schema-validated
and invalid lines are REJECTED (never repaired) before anything is appended
to `data/inferences.jsonl`. `--dry-run` prints without appending. Inferred
knowledge never feeds the deterministic number path.

## The rollup (`derived/weekly.md`)

- **Weight**: last 14 points with 7-day rolling average, plus a rate line -
  `ON TARGET` / `FAST - raise intake` / `SLOW - check logging` against the
  phase target from `vitai.toml`.
- **Training by week**: km, run/gym counts, average easy-run HR with an
  easy-cap flag.
- **Tripwires**: resting-HR drift, pain gate, sleep floor, steps floor.
- **Coverage**: how sparse the record is (sparse is fine; abandoned is not).
