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

## The rollup (`derived/weekly.md`)

- **Weight**: last 14 points with 7-day rolling average, plus a rate line -
  `ON TARGET` / `FAST - raise intake` / `SLOW - check logging` against the
  phase target from `vitai.toml`.
- **Training by week**: km, run/gym counts, average easy-run HR with an
  easy-cap flag.
- **Tripwires**: resting-HR drift, pain gate, sleep floor, steps floor.
- **Coverage**: how sparse the record is (sparse is fine; abandoned is not).
