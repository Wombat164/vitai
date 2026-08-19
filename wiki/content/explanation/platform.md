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
| 35 | unreleased | `place_precise` on `sessions` and `context`, with no column in this read model. The coarse tier is the default egress form and is dropped once at the read door, so every surface inherits it including this one; a null column would read as "nobody wrote one" rather than "you are not being shown this". A precise value is refused unless a coarse one travels with it, and a consumer that needs the precise tier names a release through the API |
| 36 | unreleased | `seq`: this row's stored position among the rows sharing its bare key, plus `supersedes_seq` which narrows a reference to one of them. `supersedes` is unchanged in spelling and meaning - the position is a second field rather than a suffix, because a parsed reference cannot be told apart from a bare key that happens to contain the separator. Stored rather than computed, because read-time positions renumber when a device syncs a row stamped earlier. Machine-set. Two machines offline together still collide, and `validate` reports that separately |
| 37 | unreleased | `avg_power` on `sessions`: the one field on a cycling row that is measured rather than estimated. Named `avg_power` because a bare `power` is ambiguous between average, maximum and normalised |\n
| 38 | unreleased | An `unread_retired_value` tripwire, and the register behind it: `KEY_FORWARD` names the one callable that reads each retired key forward and `TERMINAL_RETIREMENT` says why the rest are never read. A record carrying `sessions.location` or `sessions.planned` now gets one `review` per field saying no successor inherited those values, and what to append instead. Nothing about what is stored changes |
| 39 | unreleased | `verdicts` gains `observed_days` - how many days of the stated window actually held the metric. `window_days` was the denominator a reader assumes; this is the numerator, so an average over one logged night no longer renders like an average over seven. No threshold: the engine reports the fraction and lets the reader judge |
| 40 | unreleased | `provenance` gains `field_sources` - on a merged row, which source supplied each field. A merged row's single `source` is true of the row and of no value in it; `explanations` records only contested fields, and complementary instruments never contest. Derived, never stored, absent on a single-writer row |
| 41 | unreleased | `verdicts` gains `provisional` - the window includes a day the record marks `partial`, so the figure will change when the rest of that day arrives. A second field rather than a third value of `answers`: a provisional magnitude is still a magnitude. Absent coverage is not read as complete |
| 42 | unreleased | `provenance` gains `field_origins` - which INSTRUMENT supplied which field, beside `field_sources` for which FEED. `source` is the channel a value arrived by, `origin` is the device that observed it, and a hand-merged row carrying another instrument's figures forward makes the two disagree. Optional: a claim that does not name its instrument contributes no entry |
| 43 | unreleased | `goal_progress` gains `milestones_total` - every milestone the goal has crossed. The existing `milestones` column counts only the CURRENT bucket, which its name never said: a goal with 33 crossings reported 0. Both ship, because the old one's meaning is what consumers are already reading |
| 44 | unreleased | A `capabilities` dataset - what an INSTRUMENT can and cannot measure, dated and categorical. `competence` is measures / proxy / absent / unknown; a `construct` is required beside a proxy; no vendor figures. Keyed on `origin`, and silence resolves to `unknown` rather than to a default outside the record |
| 45 | unreleased | An `instruments` dataset - the ENTITY behind `origin`, over an interval. The join is `(origin, date)`, so a reading resolves to the instrument as it was THEN rather than to whatever reports under that name now; overlapping intervals for one origin are refused at validation. Named `instruments` because `device` already means the machine that wrote the line down, and resolved on `origin` alone because `source` is a channel. An unregistered origin resolves to nothing and renders as it does today |
| 46 | unreleased | A `comparability` dataset - whether two instruments' readings of one field may be read as one series, EARNED BY OVERLAP and never asserted. The default is NOT COMPARABLE. Keyed on `origin_a`/`origin_b`; `basis` is `overlap` and only `overlap`. Three statuses - `comparable`, `offset`, `not_comparable` - and `offset` does NOT license a spanning derivation: it records a measured difference, never a licence to apply it. The weight-rate instrument-seam refusal lifts only when every pair in the window resolves to `comparable`. The resolver answers a pair order-insensitively even though the stored identity is not |
| 47 | unreleased | A `crossings` dataset - round-number and personal-first milestones, GOAL-INDEPENDENT and history-wide, unlike `milestones` which needs a declared goal and a bucket. `round_number` mints on crossing a multiple of 5 kg either way (a chosen ladder, not a derivation); `personal_first` mints on a new lowest or highest reading, and the very first reading mints nothing since it has no prior evidence to cite. Every row carries `previous_value`/`previous_date`, the reading on the other side of the crossing. Reads the canonical weight series, never raw claims. Also: `height_cm` joins `MEASUREMENT_KINDS`, needing no contract number of its own since it widens an existing column's legal values rather than reshaping one; the band-crossing (BMI) milestone it will eventually feed stays undecided |
| 48 | unreleased | `crossings.kind` gains `band` - #370's third milestone kind, a population-reference ratio (BMI) crossing a boundary. No column moved (`CROSSING_KEYS` is unchanged); what moves is the closed vocabulary `kind` may hold, a consumer-visible change on its own. The ruling: the engine may compute the ratio and state the boundary as a boundary, and may never name the band - `value` is the numeric boundary crossed, never a word, and no field on this row can hold a category name. Boundaries are adopted, not invented (G85): fetched and cited in `crossings.py`. Height is effective-dated via `policy.height_on`, built on the same `_in_force` machinery goals and thresholds already use - a weight reading with no height yet in force mints no ratio |
| 49 | unreleased | `questions.kind` gains `outage` and `false_zero` - #398's fourth and fifth kinds, an instrument that stopped and a zero that should have been an absence. No field moved; what widens is the closed vocabulary `kind` may hold, so a client matching the three contract-48 values drops both new kinds silently. They stay two kinds because they want opposite gestures - a gap wants an append, a false zero wants a supersede against a row that exists and is wrong. Neither rule carries a number: silence is measured against the longest gap that source has already shown, and a zero is out of family when the source has never written one for that field |
| 50 | unreleased | `protocols` gains `controls` - the conditions a protocol DECLARES it fixes, from the closed vocabulary in `semantics/body_state.toml`. A protocols row said WHICH procedure was followed and never what it controls FOR, so a reading either named a protocol or did not and nothing could say which conditions were left free | **Nothing required**; null on every existing row. **The column carries no magnitude and a consumer must not supply one** - #404 lists rough masses to argue the problem is real, and a band comes from a measured overlap, a per-reading `u_obs` or an athlete-stated range and from nowhere else, so deriving a width from the COUNT of uncontrolled conditions is inventing precision about imprecision. **Absent and empty are different facts**: null means nobody has said, an empty list would assert the procedure fixes nothing and is refused. A condition not listed beside others is UNSTATED, never declared free, which is contract 44's silence-resolves-to-`unknown` rule one dataset over and why there is no companion `free` list. A JSON array in a TEXT column, in `LIST_COLS` |
| 51 | unreleased | `absent_fields` and `absent_reason` on the observation datasets - WHY a value is missing, not just that it is. A null said only that nothing is there, and "nobody measured it", "it was measured and rejected", "asked and declined", "asked and they do not know" and "it does not apply here" are different facts with opposite consequences. The other half of contract 49: retiring a false zero leaves a hole, and without a reason the next reader re-derives the same confusion | **Nothing required**; both null on every existing row. **A REASON EXPLAINS A HOLE AND NEVER FILLS ONE** - a consumer must not render one as a value, and a reason beside a value that is PRESENT is refused at validation rather than silently preferred, because that row makes two claims and offers no way to choose. Two fields rather than one parsed one (contract 36's lesson), and ONE reason for the fields it names: absence usually has one cause that takes several fields with it, so a per-field map would carry the same reason three times and let the copies drift. The vocabulary is FHIR `dataAbsentReason`'s distinctions and not its codelist - `unknown` and `not-asked` are dropped because a null already says that, `unsupported` because contract 44's `competence: absent` carries it, and the numeric sentinels because smuggling a value through a type is what 49 cured |
| 52 | unreleased | `comparability` gains `difference_lo` and `difference_hi` - the two ends of a MEASURED disagreement, which the row could not write down. `bias` is a point and `spread` a width, so the schema could say "they leaned this way by this much" and "they got this far apart" and could not say "further above than below"; before this the shape reached a reader only as a sentence in the row's `note` | **Nothing required**, and the two ends stay OPTIONAL beside `offset` on purpose: requiring them would force a writer who knows a width and not its ends to invent the ends, and would invalidate every `offset` row written before 52. **THEY EARN NO BAND.** `offset` still does not lift the instrument seam, so a row that may not be read across is not a row a band derives from; and observed extrema are not a coverage interval, since the minimum and maximum of a sample can only widen as days arrive and say nothing about the next reading. A consumer still may not draw a band from a comparability row alone - what changed is that the record can hold what was measured without losing half of it. Both ends or neither, in order, `spread` required beside them and equal to their difference, `bias` inside them, and all three forbidden beside `not_comparable`. Named for what they bound: `bias_lo`/`bias_hi` would read under this schema's own `_lo`/`_hi` convention as bounds on the BIAS, which is a confidence interval on a median and the exact coverage claim #402 forbids inventing |
| 53 | unreleased | An `overlaps` dataset - the paired-measurement window as its own row, and `overlap_ref` demoted from the only carrier of the evidence to the fallback where no window could be counted. A `comparability` row DECLARES that two origins may be read across and cited its evidence in `overlap_ref`, which was free prose. A reference that is a sentence is not a reference: nothing can follow it, nothing can count it, and a client deciding whether to trust the figure had to parse English | **One thing required, and only of a consumer that reads `overlap_ref`**: stop treating it as always present beside `comparable`/`offset`. Where the record holds a census the sentence is now REFUSED rather than merely redundant, so the field is null on exactly the rows carrying the better evidence - read the census instead, which is the same facts as columns (`paired_days`, `dropped_days`, `from_date`, `to_date`). Ignoring the new table is otherwise safe. **The statistics are NOT here.** The proposal that named this dataset listed the median, the low and the high among its columns; contract 52 put all three on the `comparability` row one contract earlier, held to each other by validation, and carrying them twice would be one width stated in two datasets kept honest by a cross-dataset rule - the second spelling refused when a fact contract 44 already carried was proposed a second field. `comparability` DECLARES and holds the statistics; `overlaps` COUNTS. **`dataset` is on the census and not on the declaration**, because a field name does not identify a dataset - `distance_km` is a column of both `daily` and `sessions` - so a census that did not say which readings it counted could not be followed back to them, which is the sentence's own defect one level down. **A window is EARNED**: fewer than three paired days is refused, being the count below which the engine will not measure a window at all, and `paired_days + dropped_days` may not exceed the days the window spans, because a day either paired or was dropped and a window cannot hold more days than it has |
| 54 | unreleased | `supersedes_device` beside `supersedes_seq` - which MACHINE wrote the row at the position a correction names. `seq` is stamped from the union the appending machine can SEE, and one writer per file is what makes a union merge safe by removing the shared counter that kept it unique - so two devices offline together stamp the same position, a seat holds two live rows, and a reference to it names both. Nothing is corrupted and no write is lost; what breaks is that a written correction stops meaning one thing | **Nothing required, and every existing correction keeps working.** Which occupant a correction retires, in order: the machine `supersedes_device` names; or the only occupant, where there is one - which is every single-device record and every record written before this; or the correction's OWN machine, which is what a correction authored on a laptop about a row that laptop wrote means; or nothing at all, reported rather than guessed. The third rule is why almost no correction needs to write the field, and it agrees with the second before a peer's file arrives, so one correction retires one row before and after a sync. **A consumer that AUTHORS corrections should write `supersedes_device` when it means a row another machine wrote**; one that only reads may ignore the field. What changes for an existing reader is that a contested position now REFUSES rather than retiring whichever row sorted last, and `validate` names the field to write. No clock is involved: ordering the occupants by `recorded_at` would pick one, and contract 26 settled that `recorded_at` is machine-set and not something a rule may reach across devices for |
### What each contract TOUCHED, and who has to care

Machine-readable, from contract 47 onward:
`src/vitai/semantics/contract_impact.toml`, published in `vitai schema --json`
under `impact`, and answered per client by `vitai contract-impact --since N
--reads <surfaces>` (exit 0 stay, 1 move, 2 cannot answer).

**There is deliberately no "must a client move" field here.** That question has
one safe answer, `yes`, which is never wrong and costs the author nothing, so a
field shaped like it stops carrying information within a month. The engine
states what it TOUCHED; a client intersects that with what it READS. A boolean
could not carry contract 48 in any case: no column moved, and a client matching
`kind` exhaustively silently drops every `band` row. Both are true, and they
answer different questions.

Surfaces come in three grammars because they have three audiences.
`table`/`table.column` is the built read model and the audience is a READER;
`meta:field` is a line-level field that is never a column and the audience is
an AUTHOR of corrections; `report:name` reaches a consumer through the report
and has no table at all, so a client gating on the SQLite shape can ignore
every one of them outright.

Surface first, contract third, and not by taste: a row beginning `| 47 |` is
indistinguishable from a migration row to the regexes that hold the two
contract tables together, so this one cannot begin with a number.

| Surface | Change | Contract | A reader of that surface |
|---|---|---|---|
| `crossings` | added | 47 | need not move |
| `measurements.kind` | widened | 47 | **must move** |
| `crossings.kind` | widened | 48 | **must move** |
| `report:questions.kind` | widened | 49 | **must move** |
| `protocols.controls` | added | 50 | need not move |
| `daily.absent_fields` | added | 51 | need not move |
| `daily.absent_reason` | added | 51 | need not move |
| `sessions.absent_fields` | added | 51 | need not move |
| `sessions.absent_reason` | added | 51 | need not move |
| `weight.absent_fields` | added | 51 | need not move |
| `weight.absent_reason` | added | 51 | need not move |
| `comparability.difference_lo` | added | 52 | need not move |
| `comparability.difference_hi` | added | 52 | need not move |
| `overlaps` | added | 53 | need not move |
| `comparability.overlap_ref` | narrowed | 53 | **must move** |
| `meta:supersedes_device` | added | 54 | need not move |
| `meta:supersedes_seq` | narrowed | 54 | **must move** |

`added` is a new table, column or field, and adopting it is a choice.
`widened` is a closed vocabulary gaining a member, so a reader matching
exhaustively drops rows silently. `narrowed` is a value that was always present
becoming absent or refused.

Below contract 47 this is UNSTATED and the API refuses rather than
answering partially: backfilling by re-reading prose is the "somebody fills in
a field" failure the design exists to prevent, and a wrong backfilled entry is
worse than an absent one because it will be trusted.

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
