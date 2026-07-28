---
title: The platform
---

vitai is built to be built ON: a game, a dashboard or a coach portal can
consume the engine without touching its internals.

## The three surfaces

1. **The library**: `vitai.api.Vitai(root)` - `datasets()`, `verdicts()`,
   `rollup()`, `build()`, `status_line()` over one user's store.
2. **The read model**: `derived/health.db` - one table per dataset, plus
   `verdicts` (week, metric, value, target, verdict) and `meta` (contract
   version). Rebuilt from zero on every build; consumers treat it as
   read-only.
3. **The CLI**: `vitai verdicts` emits the same rows as JSONL for
   non-Python consumers.

The `verdicts` table is the interesting one for games: deterministic weekly
goal-attainment rows - exactly the signal an economy should mint premium
currency from, and unforgeable in the sense that it only moves when the
engine's arithmetic over the record moves.

## Single-user or multi-user?

The per-user store is the atom; multi-user is horizontal. A backend with
thousands of players keeps one content store per user and instantiates the
engine per user:

```python
coach = Vitai(f"/data/users/{user_id}")
coach.build()
economy_input = coach.verdicts()
```

Per-user stores are embarrassingly parallel (SQLite-per-tenant, no shared
write state), per-user deletable (GDPR = remove the directory), and
sufficient: leaderboards and economies aggregate VERDICTS - a handful of
small rows per user-week - in the host's own database. Cross-user joins on
raw health records are deliberately impossible in vitai, and any player can
always take their directory and leave.

## The third data tier

`vitai infer` lets a model (your Claude CLI, or any OpenAI-compatible
endpoint) write knowledge back: `data/inferences.jsonl`, append-only,
schema-validated, carrying provenance (model, evidence, confidence).
Projected into the read model like everything else - but never read by the
deterministic number path. Observed data is the truth, derived data is
arithmetic, inferred data is opinion with a citation.
