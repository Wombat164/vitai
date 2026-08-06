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

`session_weeks` (contract 28) is the ordinary one: sessions, distance and
duration per week, per the engine's own session-type vocabulary, with a row
for every week in range including the ones holding nothing. It exists because
every consumer was computing it and one of them proved why that ends badly -
it mapped the engine's types onto two buckets of its own, so `strength`,
`walk` and `row` matched neither and 17 of 43 sessions vanished with their
distance, under a chart that looked entirely plausible.

Two rules come with it. **Do not re-bucket the types**: the vocabulary is the
engine's, and `type_source` exists because a label a vendor's classifier
assigned and one the athlete asserted are different facts. And **a week of
zeros means the record holds no sessions for it**, never that the athlete did
nothing - those are different facts, and telling them apart needs coverage.

`milestones` is the second mintable signal, and it is deliberately harder to
earn: it counts only progress that stayed inside a goal's contribution
policy, so a host cannot be gamed by an athlete who blows through a ramp
guard. `contributions` explains any single event's effect on any single goal,
which is what a UI needs to answer "why did this run not move my bar".

## Headline figures: what a client may put in large type

A conformance client deleted four stat tiles because each was a derivation the
engine does not emit. Three of those answers are worth stating, because every
client will otherwise invent its own.

**The rate was already there.** `verdicts` emits `weight_rate` judged against
the phase target, and `Vitai.status()` carries the same figure as one number
with a `direction` word. The client displayed neither and computed its own over
a different window. That is a discoverability failure rather than a missing
feature: reach for what the engine emits before deriving a second one.

**The weight average says what it is over.** `status()` carries `mean_kg_7d`,
and it is the mean of the last seven WEIGH-INS, not of seven days - on a record
with one weigh-in a week those seven points span six weeks. `mean_kg_span_days`
and `mean_kg_points` say so, and a client rendering the field name alone would
be describing a window the record never used.

**There is no cross-metric adherence percentage, and there should not be.** The
deleted tile collapsed every metric and every week into one number with
refusals dropped from the denominator, so a record ninety per cent unjudgeable
could display one hundred per cent adherence. `verdicts` carries a `reason`
column and refuses to write a declined row without one, precisely so a consumer
cannot flatten "the record holds nothing to judge" into "not counted". A single
percentage flattens it by construction. Show the judged rows and the refused
ones side by side; the count you would have hidden is the honest headline.

## Contract history

| Contract | Version | Change |
|---|---|---|
| 1 | 0.2.0 | Founding: one table per dataset, `verdicts`, `meta` |
| 2 | 0.3.0 | `goals`/`thresholds`/`achievements` tables; `contributions`, `milestones`, `plan_churn`, `goal_progress` derivations; `verdicts.goal` linkage |
| 3 | 0.3.0 | `measurements`/`context` tables; generation-2 columns on `daily` and `sessions`; the resolution layer - primary tables hold CANONICAL rows, with `claims`, `resolution`, `justifications`, `conservation`, `retractions` |
| 4 | 0.3.0 | `medical` table; the safety layer's `gates` and `escalations` |
| 5 | 0.3.0 | Adds the `checks` dataset, `onset_date`/`precondition` on `medical`, `occurred_date` on `achievements`, and `status`/`precondition` on `gates` |
| 6 | 0.3.0 | Adds the `events` dataset (dated real-world fixtures), `deadline_kind`/`event`/`verification`/`change_kind` on `goals` (generation 2), `deadline_kind` on `plan_churn`, and `days_to_deadline`/`event`/`verification` on `goal_progress` |
| 7 | 0.3.0 | Adds `recorded_at` (transaction time) to **every** dataset and `measured_at` (observation time, HH:MM local) to `weight`. Resolution orders by `(date, recorded_at)` instead of falling back to file position |
| 8 | 0.3.0 | `goal_progress` gains `dataset` (the scope the goal actually draws from, inferred from the metric where the row left it unset) and `scope` (`declared` \ |
| 9 | 0.3.0 | Adds `track` (repo-relative path to the stored GPX/FIT/TCX), `activity_id` (the platform's opaque id) and `activity_source` (who ASSIGNED that id, not necessarily who recorded it) on `sessions` |
| 10 | 0.3.0 | Provenance as a CHAIN: `origin` (what observed reality), `path` (the ordered hops it travelled) and `origin_evidence` on the observation datasets, plus a `provenance` table carrying how many INDEPENDENT instruments observed each resolved row |
| 11 | 0.3.0 | The acquisition axis: `capture` (how a value was acquired) and `read_by` (who did the reading, where one happened) on the observation datasets; `origin`/`path`/`origin_evidence` reach `sessions`; `provenance.trust` gains a `transcribed` level. Also 11: the resolution audit - `resolution` gains `discarded` and `unattributed_loser`, plus an `unattributed_claim_lost` tripwire |
| 12 | 0.3.0 | `modelled` on the observation datasets names the FIELDS on a row that are model outputs rather than observations; `type_source` on `sessions` says how a categorical label was assigned |
| 13 | 0.3.0 | The artifact store: an `artifacts` manifest table (hash, media type, size, why it was kept) and an `artifact` reference on weight, daily, sessions and measurements, so the evidence a value was read FROM survives alongside the value |
| 14 | 0.3.0 | A `sets` table, one row per SET: an attempted load that could not be completed, whether a set was taken to failure, and what kind of number a load is. Also `rpe` widens from integer to numeric across every dataset carrying it |
| 15 | 0.3.0 | A `meals` table, one row per INGREDIENT of a photographed meal, with a gram estimate, a gram RANGE, and the per-100 g composition figures as the food table gave them alongside the table's name |
| 16 | 0.4.0 | `device` on EVERY dataset, naming the machine that wrote the line down - distinct from `source`, which names the instrument that observed the value. Readers take `<dataset>.<device>.jsonl` alongside `<dataset>.jsonl` and union them |
| 17 | 0.4.0 | `meta` gains a `policy` row: a content hash of the config the record does not hold |
| 18 | 0.4.0 | `verdicts` gains `reason`: `no_data` was one word for four states, distinguishable only by which fields were null |
| 19 | 0.4.0 | `protocol` on weight and measurements (the CONDITIONS a measurement was taken under); the `protocols` and `regimes` datasets |
| 20 | 0.5.0 | `derived_from` and `derived_op`: which rows a computed value stands on, and how. Both DECLARED rather than executable - do not re-run `derived_op`, and do not assume the engine did. Rows standing on a shared input count as ONE witness in `independent_sources`, so that number may fall. A value whose input was later restated raises `stale_derivation` and is left in place, flagged rather than corrected |
| 21 | 0.5.0 | `emissions`: what the engine TOLD the athlete, and when. Pass-through, append-only, never resolved - two assertions on one day are two events, and no correction retires either. Read it as DELIVERED rather than computed: it holds what a consumer surfaced, not what the engine calculated, because a judgement nobody was shown had no consequence to retract. Written at delivery time via `api.assert_delivery`, never at build |
| 22 | 0.5.0 | `verdicts` gains a `pending` reason and a `due` date: the question is answerable and not yet. `pending` is NOT permanent - once `due` is past the reason degrades to `no_input` and the row keeps `due`, so a late source reads as late rather than as still coming. `due` is earned from the source's own arrivals, so a source with no established cadence refuses with `no_input` exactly as before |
| 23 | 0.5.0 | `meta` gains a `built_on` row, and an unqualified build takes its viewpoint from the record's last date rather than the wall clock. An explicit `--on` is unchanged; a build nobody dated is now reproducible, and `goal_progress` is populated where it was silently empty |
| 24 | 0.5.0 | goals gain `polarity` (floor, ceiling, band, approach) and `target_hi`; `goal_progress` gains `polarity`, `target_hi`, `room_left`, `distance` and `breach`. An absent polarity reads as `floor`, so nothing re-scores. `progress_pct` is now the FLOOR's measure and is null for the other three; a ceiling reports `room_left`, an approach `distance`, and `breach` says under or over. Milestones are minted for floors only |
| 25 | 0.5.0 | goal status splits into two axes: `goals` gains `lifecycle_status` and retires `status`; `goal_progress` gains `lifecycle_status` and `achievement_status`. Old lines keep validating and map forward - `paused` to `on_hold`, `abandoned` to `cancelled`, `achieved` splits into lifecycle `completed` plus achievement `achieved`. `status` keeps its column on `goal_progress` with the same value, so a consumer reading the old name is unaffected |
| 26 | 0.5.0 | a declared scale beside each subjective number: `rpe_scale` on sessions and sets, `mood_scale` and `pain_scale` on daily. Absent means unstated and a consumer must not invent a denominator; where a scale is declared the value is validated against its range |
| 27 | 0.5.0 | `best_efforts`: the fastest 1k, 5k, 10k, half and full of every stored track, one row per (track, distance). Read `basis` before quoting a time - `device` is measured against the watch's own distance, `derived` against the engine's haversine sum. `seconds` is elapsed, so a stop inside the window counts |
| 28 | unreleased | `session_weeks`: sessions, distance and duration per week per session type, with a row for every week in range including the ones holding nothing. Do not re-bucket the types - the vocabulary is the engine's, and a consumer that mapped them onto its own dropped 17 of 43 sessions with their distance. A week of zeros means the record holds no sessions for it, never that the athlete did nothing. `distance_km` and `duration_s` sum only the rows carrying one and are null where none did |
| 29 | unreleased | `verdicts` gains `statistic` (what KIND of number `value` is, from `semantics/statistics.toml`) and `window_days` (over what population). One column carried a maximum, a between-window change, a composite index and six averages: `steps` at 9752 for a week is the DAILY AVERAGE, and read as a weekly total it describes a week five thousand steps a day short of the one that happened. `pain_gate` is a MAXIMUM, because a gate is about the worst day. The safety floors are means over FOURTEEN days on a row keyed by one week, which is what `window_days` exists to say. Terms are IEEE 1752.1's `descriptive-statistic` verbatim where they reach, checked against the published enum; a between-window comparison and a composite index have no term there and carry `vitai`-namespaced ones. Present wherever there is a value and absent on a refusal, which has no number to describe |
| 30 | unreleased | `goal_progress` gains `observed`, the latest value of a LEVEL metric where `counted` is a sum of contributions. A goal to reach a level is not a goal to accumulate: scored as the latter it reported no count, no percentage and no breach at all. A level goal carries `observed` and null `counted`, a flow goal the reverse, and that is how a consumer tells the two shapes apart. Scored only where the direction is DECLARED, since the `floor` default would otherwise read a goal to lose weight as one to gain it. Only `weight`: `measurements` is entity-attribute-value and levels in `daily`, such as resting heart rate, are not covered |
| 31 | unreleased | `medical` gains `body_side` and `events` gains `outcome`. A side is what stops a gate over-restricting - gating "the knee" bans a movement the athlete performs perfectly well on the other leg - and the gate reason now names it. `outcome` is a second axis beside `status`: what the fixture IS versus what became of it. Both optional, and absent means nobody has said rather than "did not happen" |
| 32 | unreleased | `verdicts` gains `answers`: `magnitude` where the engine will vouch for the number, `direction` where it will vouch only for ahead/behind/on-track. A client cannot derive this without reimplementing the per-field policy. `energy_availability`, `weight_rate`, `easy_hr` and `pain_gate` are direction-only - the first is a difference of two inexact aggregates, the second because the pre-registered run measured a median `u_rate / half-band` of 1.74 and found more than half of scored weeks admit no verdict word at all, `easy_hr` because avg_hr is policy-usable at rest and not at intensity, and `pain_gate` because its declared scale does not reach this row. Present on judged rows, absent on refusals |
| 33 | unreleased | the `plans` dataset, with `sessions.planned` retired. A plan is not a session: `sessions` means this happened, so a skipped row there would corrupt every count silently. Identity is a slug, because a plan is resolved later. `unresolved` means nobody has answered and never a missed session; `reason` is COM-B and is a classification rather than a score; `tier` is not authorship |
| 34 | unreleased | `derived_by` and `derived_build`: who computed a value this engine did not. `derived_external` said only "not this engine", which cannot tell one client's figure from another's or from a bug fixed two versions ago. Two fields rather than a parsed slug; `by-hand` for a person with a pen, which takes no build; and no install identifier, because that is a tracking key |

`db.py` carries the same history beside `CONTRACT_VERSION`, at more length
and with the reasoning. This table is the summary; that comment is the
source. The two had drifted - this one stopped at contract 4 and the
README's at 8, while the engine was at 16 - which is worth naming, because
a consumer contract nobody maintains is a consumer contract nobody can rely
on. A test now holds the three of them together.

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
