---
title: The platform
---

vitai is built to be built ON: a game, a dashboard or a coach portal can
consume the engine without touching its internals.

## The three surfaces

1. **The library**: `vitai.api.Vitai(root)` - `datasets()`, `verdicts()`,
   `rollup()`, `build()`, `status_line()`, plus the goal surface added in
   contract 2: `goals()`, `contributions()`, `milestones()`, `churn()` and
   `state(date)` over one user's store.
2. **The read model**: `derived/health.db` - one table per dataset, plus
   `verdicts` (week, metric, value, target, verdict, goal), the goal
   derivations (`contributions`, `milestones`, `plan_churn`,
   `goal_progress`), and `meta` (contract version, plus the policy digest
   from contract 17). Rebuilt from zero on every build; consumers treat it
   as read-only.
3. **The CLI**: `vitai verdicts` and `vitai goals --json` emit the same rows
   as JSONL for non-Python consumers.

The `verdicts` table is the interesting one for games: deterministic weekly
goal-attainment rows - exactly the signal an economy should mint premium
currency from, and unforgeable in the sense that it only moves when the
engine's arithmetic over the record moves. Each row now carries the `goal`
it serves, so an economy can mint per goal rather than per metric.

`milestones` is the second mintable signal, and it is deliberately harder to
earn: it counts only progress that stayed inside a goal's contribution
policy, so a host cannot be gamed by an athlete who blows through a ramp
guard. `contributions` explains any single event's effect on any single goal,
which is what a UI needs to answer "why did this run not move my bar".

## Contract history

| Contract | Version | Change |
|---|---|---|
| 1 | 0.2.0 | Founding: one table per dataset, `verdicts`, `meta` |
| 2 | unreleased | `goals`/`thresholds`/`achievements` tables; `contributions`, `milestones`, `plan_churn`, `goal_progress` derivations; `verdicts.goal` linkage |
| 3 | unreleased | `measurements`/`context` tables; generation-2 columns on `daily` and `sessions`; the resolution layer - primary tables hold CANONICAL rows, with `claims`, `resolution`, `justifications`, `conservation`, `retractions` |
| 4 | unreleased | `medical` table; the safety layer's `gates` and `escalations` |
| 17 | unreleased | `meta` gains a `policy` row: a content hash of the config the record does not hold |

Contracts 5 to 16 are missing from this table rather than from the record -
the full per-contract history lives in `db.py` beside `CONTRACT_VERSION`,
and this summary stopped being maintained somewhere around contract 4.
Read `db.py` for anything not listed here.

A consumer should read `meta.contract` and refuse to render what it does not
understand. Contract 2 is additive - a contract-1 reader that ignores the new
tables still works, except that `verdicts` has gained a trailing column, so
`SELECT *` positional reads must be updated to named columns.

**Contract 17 is additive and safe to ignore.** `meta` gains a second row.
A reader that selects `key='contract'` is unaffected; only one that selects
the whole table and expects a single row needs to change. The row is
**optional** at 17 - a read model built without a digest omits it, so its
absence means "built without one" rather than "pre-17" or "no policy". Read
`contract` to know the shape; never infer a build's age from this row. What the row buys:
`as_of` reconstructs the record, and `vitai.toml` is not in the record, so
two reconstructions taken under different configs are not comparable and
nothing said so before. It does not make them comparable - it makes the
difference visible.

**Contract 3 changes what the primary tables MEAN**, which is the one
migration worth reading twice. `daily`, `sessions`, `weight` and
`measurements` now hold canonical rows - one adjudicated record per quantity
per date - rather than raw lines. A consumer that wants the raw claims must
read `claims` and join on `claim_id`. This is a change no reader can detect
by shape, only by contract number, which is exactly why the number exists.

For a single-source record nothing moves: with one witness per quantity, the
canonical row is that witness. The change bites only where the athlete owns
two devices, and there it stops the dashboard double-counting.

## Resolution, for consumers

A game or dashboard should build on canonical rows and treat `claims` as the
audit trail. Three tables explain what happened:

- `resolution` - each contested field: which source won, over what, and why.
  Routine output; render it when the athlete asks where a number came from.
- `conservation` - physically impossible arithmetic (sessions burning more
  than the day), flagged and never auto-fixed. Surface it; do not silently
  correct it, and do not mint anything from a day carrying one.
- `retractions` - claims that stopped being true and what fell with them.
  A consumer that caches derived values must honour these: an inference
  resting on a retracted claim is no longer current knowledge.

## Gates and escalations - the one table you must not ignore

Contract 4 adds `gates` and `escalations`, and they are different in kind
from everything else here. Every other table is an input you may render as
you see fit. These two constrain what you are allowed to render.

**Before suggesting any activity, read `gates`.** A gate row names the
activity classes it blocks (`run`, `impact`, `gym`, `all`, ...) and carries
its own escalation text. A consumer that skips this will cheerfully propose a
run to someone whose record has blocked running - which is the exact failure
the table exists to prevent. `Vitai.gated("run")` answers it in one call.

**`escalations` is not a notification feed.** Rows at `emergency` or `urgent`
level mean the engine has stopped programming against something in the record,
and the `action` string is fixed text that must be shown verbatim. Do not summarise it, rank it against other
UI priorities, or let a language model rewrite it for tone. A game must not
mint anything from a day carrying one, and must not treat a gated day as a
missed target.

Neither table is advisory and neither is a diagnosis - they are where the
engine stops. Every obligation above still stands: read `gates` before
suggesting an activity, render the escalation text verbatim, mint nothing
from a day carrying one, and never treat a gated day as a missed target. If
you are building something that could plausibly encourage training,
honouring these two tables is the minimum bar.

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
