"""SQLite read model: rebuilt from zero on every build, never a store.

The table set IS the public contract a game/dashboard reads (see
ARCHITECTURE.md "The platform"): one table per dataset plus `verdicts`
(weekly goal-attainment rows) and `meta` (contract version, and the
policy digest of the config the record does not hold).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import KEYS, PRECISE_KEYS
from .weeks import SESSION_WEEK_KEYS as _SESSION_WEEK_KEYS

# Bump when a table/column changes shape; consumers check meta.contract.
# 2: increment 1 - goals/thresholds/achievements datasets, the contributions,
#    milestones, plan_churn and goal_progress derivations, and a `goal` column
#    linking each verdict row to the goal it serves.
# 3: increment 2 - measurements/context datasets, gen-2 provenance and context
#    fields on daily/sessions, and the resolution layer: primary tables now
#    hold CANONICAL rows, with raw claims in *_claims and the adjudication in
#    resolution/justifications/conservation/retractions.
# 4: increment 3 - the medical dataset, plus the safety layer's outputs:
#    `gates` (what is blocked today and why) and `escalations` (deterministic
#    severity-to-action). A consumer that renders training suggestions MUST
#    read `gates`, or it will propose activity the record has blocked.
# 5: gate mechanics - `checks` dataset, `onset_date`/`precondition` on
#    medical, `occurred_date` on achievements, and `status`/`precondition`
#    columns on `gates`. A consumer reading `gates` MUST now check `status`:
#    a row with status `cleared` is reported but does NOT block.
# 6: goals (G86/#26) - the `events` dataset (dated real-world fixtures a plan
#    is built backwards from), `deadline_kind`/`event`/`verification`/
#    `change_kind` on goals, and `deadline_kind` on `plan_churn`. TWO changes
#    a consumer must act on: a `goal_progress` row with `verification` of
#    `attested` has no metric, no target and no progress and MUST NOT be
#    rendered as 0% - it is a goal nothing can ever measure, not a goal going
#    badly; and a `plan_churn` row is only a retreat from a deadline when
#    `deadline_kind` is `hard`, so a consumer that reads `deadline_pushed`
#    alone will accuse the athlete of gaming a date they invented.
# 7: the clocks (#37) - `recorded_at` (transaction time) on EVERY dataset and
#    `measured_at` (observation time) on weight. Resolution now orders by
#    (date, recorded_at) instead of falling back to file position. A consumer
#    that reconstructs history MUST order by both, or a same-date correction
#    resolves by whatever order the rows happen to be in - and a `weight_rate`
#    verdict may now be `nodata` because the weigh-in times behind it are
#    spread widely enough to account for the rate.
# 8: goal scope (#36) - `goal_progress` gains `dataset` (the scope the goal
#    actually draws from, INFERRED from the metric where the row left it
#    unset) and `scope` (`declared` | `inferred` | `ambiguous` | `undeclared`).
#    A consumer must not read an unset `dataset` as "the default": unstated and
#    stated-as-daily are different, and a goal whose scope the engine cannot
#    feed reports null progress rather than 0.
# 9: the track foreign key (#43) - `track` (repo-relative path to the stored
#    GPX/FIT/TCX), `activity_id` (the platform's opaque id) and
#    `activity_source` (who ASSIGNED that id, which is not necessarily who
#    recorded it) on `sessions`. `activity_id` is also the per-row identity a
#    session previously lacked, so a correction can name one of two runs on a
#    day instead of retiring both. It is TEXT and must never be read as a
#    number: leading zeros and ids past 2^53 both occur.
# 10: provenance as a CHAIN (#35/#51) - `origin` (what observed reality),
#    `path` (the ordered hops it travelled) and `origin_evidence` on the
#    observation datasets, plus a `provenance` table carrying, per resolved
#    row, how many INDEPENDENT instruments observed it and what the journey
#    could have done to it. TWO things a consumer must change: `witnesses` on
#    `justifications` and `explanations` now counts distinct ORIGINS rather
#    than rows, so N platforms carrying one device's file is 1; and a
#    `resolution` row carries `independent`, which is false when the two
#    values are one measurement seen at two points on one pipe - that spread
#    measures pipeline fidelity and must never be read as agreement.
# 11: the acquisition axis (#77/#78) - `capture` (how a value was acquired)
#     and `read_by` (who did the reading, where one happened) on the
#     observation datasets, plus `origin`/`path`/`origin_evidence` finally
#     reaching `sessions`. `provenance.trust` gains a `transcribed` level: a
#     photograph of a console read by a model is an inference over an
#     artifact, not a reading of an instrument, and MUST NOT be rendered as
#     device-measured.
#     ALSO 11, shipped in the same build: resolution audit (#73). It was
#     briefly numbered 12 here, but no database ever emitted a 12 - the two
#     changes merged within an hour of each other and both went out under 11,
#     so a consumer gating on 11 gets both. Renumbered to say what shipped
#     rather than what was intended. `resolution` gains `discarded` (every claim
#     that lost, not only the runner-up) and `unattributed_loser`, and a new
#     `unattributed_claim_lost` tripwire. A consumer showing a canonical value
#     can now say what it beat; before this, a resolved value had no way to
#     say it had beaten anything at all.
# 12: was it measured at all (#49, #88) - `modelled` on the observation
#     datasets names the FIELDS on a row that are model outputs rather than
#     observations, and `type_source` on `sessions` says how a categorical
#     label was assigned. A consumer summing a column MUST check `modelled`:
#     an inflated estimate reaching a deficit reads ON TARGET while the scale
#     goes up. A `type` carrying `vendor-classified` is a third-party model's
#     guess, not something the athlete or a device asserted.
# 13: the artifact store (#80) - an `artifacts` manifest table (one row per
#     kept file: hash, media type, size, why it was kept) and an `artifact`
#     reference on weight, daily, sessions and measurements, so the evidence a
#     value was read FROM survives alongside the value. Two things a consumer
#     must not get wrong. A reference is a content address (`sha256:...`), not
#     a path, so it cannot drift from the row citing it - and resolving one to
#     bytes is a LOCAL lookup: the manifest travels in the read model, the
#     artifacts do not, and nothing in this contract authorises transmitting
#     one. And REMOVED IS NOT MISSING: an artifact the athlete deleted leaves a
#     tombstone with a reason, and a consumer that renders that as broken
#     evidence has turned a retention decision into a data-loss alarm.
# 14: the set as an atom (#97) - a `sets` table, one row per SET, because
#     three facts had nowhere to live: an attempted load that could not be
#     completed (`reps_attempted` 1, `reps_completed` 0), whether a set was
#     taken to failure, and what kind of number a load is. Two things a
#     consumer must not get wrong. A NULL `failure` means UNSTATED and MUST
#     NOT be read as maximal - a set logged against a stated max read as one
#     and was not, and that is the defect this dataset exists for. And a
#     `load` under `load_type: machine_stack` is a PIN NUMBER, not a mass:
#     66 on two machines is two different loads, so it is never comparable
#     across machines and never rendered in kilograms.
#     Also in 14: `rpe` widens from integer to numeric across every dataset
#     that carries it, `sessions` included. Half points are standard on the
#     RIR-anchored scale. Strictly looser, so no row that validated before
#     stops validating.
# 15: the itemised meal estimate (#96) - a `meals` table, one row per
#     INGREDIENT of a photographed meal, with a gram estimate, a gram RANGE,
#     and the per-100 g composition figures as the food table gave them
#     alongside the table's name. Three things a consumer must not get wrong.
#     Energy and macros are DERIVED from the quantity and are not columns: an
#     item whose portion is corrected must not keep a figure computed from the
#     old one. There is NO confidence column and there will not be one - the
#     range IS the confidence statement, and a number there would be a decimal
#     point pretending to be calibration. And A MEAL IS NOT A DAY: these rows
#     never feed `daily.kcal_in`, a total must never be rendered without its
#     range, and a consumer that sums meals into a day is asserting the
#     athlete ate nothing they did not photograph.
# 16: multi-device writes (#105) - `device` on EVERY dataset, naming the
#     machine that wrote the line down. Distinct from `source`, which names
#     the instrument that observed the value: a phone and a laptop are not two
#     instruments, and conflating them would manufacture corroboration out of
#     a sync (#35). Readers now take `<dataset>.<device>.jsonl` alongside
#     `<dataset>.jsonl` and union them, so ONE consumer-visible thing changes:
#     a dataset may contain rows written by several machines, ordered by
#     (recorded_at, device, position), and that order is TOTAL - two devices
#     rebuilding the same file set produce byte-identical output. A consumer
#     must not treat two rows describing one event from two devices as two
#     events; `duplicate_captures()` reports them and the engine never merges
#     them silently.
# 17: `meta` gains a `policy` row (#148) - a content hash of the config that
#     is NOT in the append-only record. Additive, and a contract-16 reader
#     that only selects `key='contract'` is unaffected; the bump is here
#     because `meta` was documented as carrying the contract version and
#     nothing else, so a consumer selecting the whole table saw one row and
#     may now see two. What it buys: a reconstruction judged under one
#     `vitai.toml` and one judged under another are not comparable, and until
#     now nothing said so. Thresholds without a dated row fall through to
#     whatever the toml says TODAY, so editing one silently re-judges every
#     historical week that lacked one. This does not fix that - it makes it
#     detectable rather than invisible. OPTIONAL at 17: `build_db` omits the
#     row when no digest is supplied, so absence means "built without one",
#     NOT "pre-17" and not "no policy". Every build the engine itself drives
#     writes it; a consumer must read `contract` to know the shape and must
#     not infer a build's age from this row missing.
# 18: `verdicts.reason` (#177) - `no_data` was one word for four states, and
#     the distinction was recoverable only by inspecting which fields were
#     null: both absent meant the input was missing, target absent meant no
#     policy was configured, both present meant the measurement could not
#     support a judgement. A fourth state did not use the word at all: a
#     contraindicated or suppressed metric had its row DELETED, which a
#     consumer cannot tell from a metric nobody computed.
#
#     Now the verdict answers "can a judgement be rendered" and `reason`
#     answers "why not": one of no_input, no_policy, not_supported,
#     contraindicated, suppressed. ADDITIVE and appended, so a consumer that
#     ignores it sees exactly the previous behaviour - except that a
#     suppressed metric now appears as a labelled row rather than as an
#     absence, which is the doctrine everywhere else in this engine and was
#     not honoured at the verdict layer.
# 19: protocol and regimes (#171 track 2) - `protocol` on weight and
#     measurements names the CONDITIONS a measurement was taken under, and a
#     row without one is a different epistemic class rather than a row with a
#     missing optional field: it carries the measurand's full definitional
#     uncertainty, which for body mass dominates instrument error. Plus two
#     policy datasets: `protocols` defines the slugs in the athlete's own
#     words, and `regimes` declares a bounded interval whose claims were
#     UNANCHORED. A consumer must not read an emptied interval as missing
#     data: the claims are still in `claims`, what ended is their standing as
#     values, and nothing is filled in behind them because the measurement
#     that ended a regime is evidence the earlier claims were unanchored
#     rather than evidence of what the true values were.
#     RENUMBERED from 18: #177 merged first, and the contract follows
#     MERGE order rather than issue order.
# 20: DECLARED derivation lineage. `derived_from` names the row references an
#     emitted value stands on and `derived_op` says how, in the athlete's own
#     words. Both are declared rather than executable: a consumer must not
#     read `derived_op` as a formula it can re-run, and the engine does not
#     re-run it either. Two consequences a consumer may rely on. A derived
#     value NEVER corroborates its own inputs, so rows standing on a shared
#     input count as one witness in `independent_sources` however many rows
#     they are. And a value whose input the record later retracted raises a
#     `stale_derivation` tripwire, which reports rather than corrects: the
#     stale number stays, visibly flagged, because an engine that cannot
#     re-run the derivation cannot produce a right answer and a confident
#     wrong one is worse than a flagged old one.
# 21: `emissions`, the engine's memory of what it TOLD the athlete. Phase 3
#     of the uncertainty proposal. Pass-through and append-only, never
#     resolved: two assertions made on one day are two events, not a
#     contested value.
#
#     SURFACED assertions only, written at delivery time by
#     `api.assert_delivery` and never at build. A consumer must not read this
#     as the set of verdicts the engine computed - it is the set it DELIVERED,
#     and a judgement nobody was shown had no consequence to retract. A
#     consumer that renders judgements and does not call `assert_delivery`
#     produces assertions the record cannot later retract; that is the
#     accepted residual risk, because logging computation instead of delivery
#     records the wrong event.
#
#     `basis_claims` is a JSON array in a TEXT column, like `derived_from`.
# 22: a `pending` refusal reason, and `due` on a refusal row. `no_input` said
#     the record holds nothing, which is true and cannot tell an athlete that
#     nothing will ever come apart from a source that delivers in four hours.
#     `pending` says the question is answerable and not yet, and carries WHEN.
#
#     THE DEGRADATION IS PART OF THE CONTRACT. A refusal is `pending` only
#     while the expected arrival is ahead. Once it passes, the reason drops
#     back to `no_input` and KEEPS `due`, so a consumer can report a source as
#     late rather than repeating that the answer is coming. A metric that
#     stayed pending forever would be a broken connector nobody noticed.
#
#     `due` is derived from the source's OWN arrivals, never declared: a
#     source with no established cadence produces `no_input`, exactly as
#     today.
# 23: `meta` gains a `built_on` row, and the build's viewpoint defaults to the
#     RECORD rather than the wall clock. `goal_progress` is materialised
#     against a viewpoint, so two people building one record on different days
#     got different databases and nothing recorded the choice: the demo shipped
#     an empty `goal_progress` beside 109 contribution rows, which reads as a
#     consumer bug rather than a property of the build.
#
#     A consumer may now read `built_on` and say "as of X" instead of guessing,
#     and an unqualified `vitai build` is reproducible: a record is a closed
#     thing and building it no longer consults the outside world. An explicit
#     `--on` still answers "what does this look like now".
#
#     #219 also claims 23. The contract follows MERGE order, so whichever
#     of the two lands second is renumbered rather than assumed.
# 24: goal POLARITY. `monotonic` and `guarded` both meant "more counts", so a
#     cap was scored as an accumulation: 1100 kcal a day against a 1200 limit
#     reported 641.7% for the week and minted four milestones for breaching
#     it. `polarity` says which direction is progress - floor, ceiling, band
#     or approach - and `target_hi` carries a band's upper bound.
#
#     WHAT A CONSUMER MUST NOT ASSUME: that `progress_pct` is always there. It
#     is the FLOOR's measure and is null for every other polarity, because a
#     percentage of a limit consumed is the figure that read as success.
#     A ceiling reports `headroom`, a band reports `headroom` and which side
#     it fell off, an approach reports `distance`, and `breach` says under or
#     over wherever the question has an answer.
#
#     Absent polarity reads as `floor`, so no existing row re-scores and no
#     row has to be edited to keep the answer it had. Rows whose title says
#     cap or limit while scoring as a floor now raise a validate ADVISORY
#     rather than having to be found by hand.
#     #219 also claimed 23 and was renumbered past it; see the note on 24.
# 25: goal status SPLITS into two axes. `status` mixed where a goal is in its
#     own life with how it is going against its target, which is #199's
#     two-scoring-systems bug at the vocabulary level: `goals` held the first,
#     `verdicts` held the second, they were built by different code, and the
#     demo had them disagreeing about steps.
#
#     `goals` gains `lifecycle_status` (DECLARED) and `status` is retired at
#     that generation - old lines keep validating and read forward through one
#     canonicaliser. `goal_progress` gains `lifecycle_status` and
#     `achievement_status` (DERIVED, never authored: a goals line is a
#     declaration, and the engine does not write its opinion into one).
#
#     `status` KEEPS its column on `goal_progress`, carrying the same value as
#     `lifecycle_status`, so a consumer reading the old name is not broken.
#     `achieved` splits: forward it is lifecycle `completed`, and the
#     achievement half is derived.
#
#     #219 also claims 24. The contract follows MERGE order, so whichever of
#     the two lands second is renumbered rather than assumed.
# 26: a declared SCALE beside each subjective number. `rpe`, `mood` and `pain`
#     validated as bare numerics, and a bare number with no scale is not
#     interpretable - for RPE it is ambiguous between two standard scales both
#     in common use, where a stored 7 is "quite light" on one and "very hard"
#     on the other.
#
#     `rpe_scale` on sessions and sets, `mood_scale` and `pain_scale` on
#     daily, naming a slug from `semantics/scales.toml`. Post-coordinated
#     rather than fixed per field, so an imported row can say which scale its
#     source used.
#
#     ABSENT MEANS UNSTATED and a consumer must not invent a denominator:
#     rendering "4 out of 10" against an undeclared scale asserts a bound the
#     record never carried. Where a scale IS declared the value is validated
#     against its range, which is the point of declaring one.
# 27: `best_efforts` - the fastest 1k, 5k, 10k, half and full of every stored
#     track. The question a runner asks first, and one no field could answer:
#     `sessions` holds a distance and a duration, so a 10.48 km run and a
#     9.74 km run are comparable on neither, and a pace computed from both
#     averages the warm-up in.
#
#     ONE ROW PER (track, distance): a track can hold several efforts, and
#     hanging them off `sessions` would flatten that. A track shorter than a
#     window simply yields fewer rows - the record cannot answer it, which is
#     not the same as zero.
#
#     `basis` IS LOAD-BEARING. `device` means the window was measured against
#     the watch's own cumulative distance, an observation; `derived` means
#     against the haversine sum this engine computes, which is not. A consumer
#     that cannot tell them apart will read both as a time trial.
#
#     `seconds` is ELAPSED: a stop inside the window counts, because excluding
#     it would be the engine deciding which pauses were real. That is why the
#     column is not called `moving_time`.
#
#     #253 claimed 26 as well and merged first, so this is 27. The
#     contract follows MERGE order, which is exactly why both sides
#     said so in their own comment rather than assuming.
# 28: `session_weeks` - how far and how often, per week, per the engine's own
#     session-type vocabulary, with a row for every week in range including
#     the ones holding nothing. Not one of 32 tables said how far the athlete
#     ran this week, so every consumer computed it; one mapped the engine's
#     types onto two buckets of its own and 17 of 43 sessions vanished with
#     their distance, under a chart that looked entirely plausible. Empty
#     weeks are rows because dropping them makes a deload, an injury and a
#     dead connector all read as time briefly running faster.
#
#     Claims 28 on the assumption nothing else bumps first. The contract
#     follows MERGE order, so if another table lands ahead of this one it
#     becomes 29 - said here rather than assumed.
# 29: `verdicts` gains `statistic` - what KIND of number `value` is, from
#     `semantics/statistics.toml`. One column carried a maximum, a
#     week-over-week change and six averages: `steps` at 9752 for a week is
#     the DAILY AVERAGE, and a consumer reading it as the weekly total saw a
#     week five thousand steps a day short of the one that happened. Adopted
#     from IEEE 1752.1's `descriptive-statistic` where its terms reach, under
#     a `vitai` namespace where they do not - a between-window comparison is
#     not a descriptive statistic of a set and the standard has no term for
#     it. Also `window_days`, because a statistic with no stated population
#     is half an answer and the missing half is the misleading one: the
#     safety floors are means over FOURTEEN days on a row keyed by one week.
#     Both are required wherever there is a value, enforced where the rows
#     are built, so a new metric cannot ship unlabelled.
#
# 30: `goal_progress` gains `observed` - the LATEST value of a level metric,
#     where `counted` is a sum of contributions. "Down to 78 kg" was scored as
#     an accumulation, so it counted nothing and reported nothing at all: no
#     count, no percentage, no breach, and a polarity reading "more is better"
#     for a goal whose title says down. `counted` was not broken; it was
#     correctly declining a question it was not built for, and nothing else
#     answered it. Which of the two columns carries the number is how a
#     consumer tells a level goal from a flow goal.
#
#     SCORED ONLY WHERE THE DIRECTION IS DECLARED. Polarity defaults to
#     `floor`, and scoring an undeclared level against that default does not
#     fix the defect - it upgrades a null to an inversion, measured at a goal
#     6.1 kg OVER its loss target reporting `achieved` at 109%. An undeclared
#     level still reports nothing and `validate` says what to write.
#
#     `weight` only. `measurements` also holds levels and is deliberately out:
#     it is entity-attribute-value, so a goal would be scored against the
#     latest reading of ANY kind - a body-fat percentage answering a waist
#     ceiling. `daily.rhr` is a level in a flow dataset and is out for the
#     same reason it always was.
# 31: `medical` gains `body_side` and `events` gains `outcome`, both found by
#     the persona corpus rather than by reading the schema.
#
#     A left-knee episode and a right-knee episode were the same episode, so
#     gating "the knee" banned a movement the athlete performs perfectly well
#     on the other leg - over-restriction, which is its own harm. `daily` has
#     carried `pain_side` since generation 2; this is the same field on the
#     dataset that does the gating, validated by the same rule rather than a
#     second copy of it.
#
#     And a confirmed, immovable race passed with no session row, its status
#     still `confirmed` forever - so a race that happened and produced no
#     data, one the athlete did not attend, and one that never took place all
#     read identically. `outcome` is a SECOND AXIS, the split #235 made for
#     goals: `status` is what the fixture is, `outcome` is what became of it.
#
#     BOTH OPTIONAL. Absent means nobody has said, never "did not happen",
#     and a consumer rendering an unanswered outcome as a miss accuses an
#     athlete of skipping a race the record knows nothing about.
# 32: `verdicts` gains `answers` - what the engine will VOUCH for on this
#     row, beside the `reason` it will not (#185/#189).
#
#     An athlete asks "have I had enough protein today". Protein against a
#     target is one logged quantity against a stated goal; energy balance is a
#     DIFFERENCE OF TWO INEXACT AGGREGATES, and subtracting those amplifies
#     the relative error rather than averaging it - "400 kcal left" can carry
#     uncertainty larger than the figure. The engine returned both with the
#     same confidence and only one deserved it.
#
#     `magnitude` means the engine vouches for the number as something to act
#     on. `direction` means it vouches only for ahead, behind or on track, and
#     a consumer must not present the figure as the thing being judged.
#
#     PRESENT ON EVERY JUDGED ROW AND ABSENT ON EVERY REFUSAL, which is
#     `reason`'s totality in the other direction. A refusal often keeps its
#     number - `not_supported` fires when weigh-in drift accounts for the
#     whole rate, so not even the sign is supported - and vouching for a
#     direction there would contradict the refusal beside it.
#
#     Four metrics are direction-only. `energy_availability` for the
#     arithmetic above. `weight_rate` because this project's pre-registered
#     run measured a median `u_rate / half-band` of 1.74 and found more than
#     half of scored weeks admit no verdict word at all - which does not
#     support `direction` either, and whose own remedy is the refusal
#     predicate #171 owns. `easy_hr` because the per-field table adopted at
#     that same gate says avg_hr is usable at rest and not at intensity.
#     `pain_gate` because it is an ordinal whose declared scale (contract 26)
#     does not reach this row, so the number has no denominator here.
#
#     ONE KNOWN TENSION, recorded rather than papered over: `weekly.md` still
#     prints the rate as a figure. That artifact is the engine's own prose and
#     #37 owns its wording; this column governs what a CONSUMER of the
#     verdicts table may present as judged.
# 33: the `plans` dataset - what a day was MEANT to be (#221).
#
#     The state work can explain why training did not happen and there was
#     nothing to attach the explanation to: an absence is not an object, and
#     no state can point at a gap in a session list.
#
#     NOT ROWS IN `sessions`, which means THIS HAPPENED and which every count,
#     weekly total and load figure depends on - a skipped row there sums to
#     zero and counts as one, corrupting all of them silently. So a plan is
#     its own row and a session cites it. `sessions.planned` is RETIRED and
#     stays legal forever: it is null on every row of every record because a
#     session that did not happen has none, so the only case it served is the
#     one it structurally could not represent.
#
#     Identity is a SLUG, because a plan is resolved later and the identity
#     has to be stable while `outcome` moves. Two 5 km runs planned on one day
#     are identical on every other field.
#
#     THREE THINGS A CONSUMER MUST NOT DO. `unresolved` is the default and
#     means nobody has answered - never a missed session, and any adherence
#     figure over plans must state how many were unresolved or it repeats the
#     defect that let a mostly-unjudgeable record display near-perfect
#     adherence. `reason` is COM-B (Michie et al 2011), a CLASSIFICATION and
#     never a score - nothing totals, ranks or trends it. And `tier` is not
#     authorship: `set_by` carries that, and a coach-set plan and a self-set
#     plan can both be binding.
#     CLAIMS 32, and #282 claims it too - both said so rather than assuming.
#     Whichever merges first keeps it and the other becomes 33; the contract
#     follows MERGE order, which is why the collision is stated here instead
#     of being discovered in a conflict.
# 34: `derived_by` and `derived_build` on every dataset that carries a
#     lineage - WHO computed a value the engine did not (#280).
#
#     `derived_external` said "not this engine" and stopped, which was enough
#     with one consumer. #158 settled that several clients read one record on
#     the same terms, and any of them may derive: two clients computing a pace
#     from duration and distance agree when both are right and differ when one
#     has a bug, and nothing could tell them apart - nor a figure from version
#     0.1 from the same field after 0.2 fixed it.
#
#     TWO FIELDS RATHER THAN A SLUG, because `client-0.1.0-a3f2` crams
#     orthogonal facts into an identifier a consumer has to parse. Required
#     together on a `derived_external` row from this generation on; an older
#     line never owed them.
#
#     `by-hand` is a real value: the single `derived_external` row in every
#     fixture this repo ships is an athlete taking a mean ON PAPER, so a field
#     naming only software would have had nothing to put there. It takes no
#     `derived_build`, because a notebook has no version.
#
#     NO INSTALL IDENTIFIER, deliberately. A stable per-install id is a
#     tracking key, `device` already says which machine wrote a line down, and
#     admitting one needs a rule about where it may travel - which is #205's
#     work rather than a field added in passing.
#
# 35: `place_precise` on `sessions` and `context`, and NO COLUMN FOR IT (#205).
#
#     The record's old stance was privacy by not storing the thing: `place`
#     was documented as coarse and never an address. That is blunt, and it
#     discards real utility - "outdoors" cannot tell the park an athlete likes
#     from the one they avoid. So the precise tier is now storable, `place`
#     keeps its name and its coarse meaning, and a precise value is refused
#     unless a coarse one travels with it.
#
#     THE READ MODEL IS INSIDE THE BOUNDARY. The coarse tier is the default
#     egress form, dropped once at the read door, so every surface downstream
#     inherits it - including this one. A column here would be null on every
#     row, and a null reads as "nobody wrote one" rather than "you are not
#     being shown this". So there is no column, and a consumer that needs the
#     precise tier names a release through the API rather than reading it out
#     of a file that was already written.
#
#     What it costs, recorded rather than discovered: a precise value that
#     leaks cannot be un-leaked. The claim moves from "we do not hold this" to
#     "we hold it and it does not escape", which is stronger and has to hold.
# 36: `seq` on every dataset whose key can collide (#239) - this row's stored
#     position among the rows already sharing its bare key - and
#     `supersedes_seq` beside `supersedes`, which narrows a reference to one
#     of them.
#
#     `line_key` falls back to `<date>/<source>`, so two runs on one day from
#     one watch shared a name: 71 per cent of sessions and 93 per cent of
#     journal rows on a live record. Contract 33 fixed what a reference
#     RETIRES - one reference takes one other row, the most recent. What
#     stayed broken was naming an EARLIER one, and five rows of one key
#     written as a chain could not be repaired by appending at all, because a
#     second append naming the same key retires the FIRST APPEND rather than
#     the next row down.
#
#     TWO FIELDS, NEVER A PARSED REFERENCE, and this is the load-bearing part
#     for a consumer. `supersedes` is untouched: same spelling, same meaning,
#     every reference already written keeps doing exactly what it did. The
#     position travels in its own field. Spelling it into the reference as
#     `K#n` was tried and abandoned - nothing stops a bare key containing the
#     separator, since `activity_id` is an opaque string and `source` is not
#     content-checked, and disambiguating by lookup made the MEANING OF A
#     STORED REFERENCE DEPEND ON WHAT ELSE WAS IN VIEW: a reference whose
#     target had not synced was read as a position and retired an unrelated
#     row, and one that had already applied flipped back when a matching
#     source arrived.
#
#     STORED, NOT COMPUTED. Read-time ordinals renumber when a device syncs a
#     row stamped earlier, so a reference written last week names a different
#     row. The reproduction is kept as a test.
#
#     MACHINE-SET. A caller may not supply `seq`, for the reason it may not
#     supply `recorded_at`: a writer that could choose its own position could
#     name a row that was never there. It is the higher of the count of
#     visible rows sharing the key and one past the highest position among
#     them, so a machine that can SEE positions 3 and 4 does not stamp 2.
#
#     WHAT IT DOES NOT FIX. Two machines offline at the same time cannot see
#     each other and will stamp the same number. `validate` reports that as a
#     key nothing can name apart, distinct from one that is merely ambiguous,
#     and it cannot be repaired by backfill - assigning positions to lines
#     already written means rewriting them.
# 37: `avg_power` on `sessions` (#91) - the one field on a cycling row that is
#     a MEASUREMENT rather than an estimate. `kcal` is modelled from heart rate
#     and mass, `distance_km` from wheel size or GPS; power is read from a
#     strain gauge.
#
#     The engine had nowhere to put watts, so any FIT ingest had to discard it.
#     `avg_power` rather than `power`, which is what the issue asks for: a bare
#     `power` is ambiguous between average, maximum and NORMALISED power, and
#     normalised is the figure cyclists quote - so half its readers would take
#     it for one and half for the other.
#
#     NO `max_power` and no normalised power. Max is a spike a consumer can
#     take from the track; normalised power is a weighted derivation with a
#     rolling window, which is a figure this engine would be COMPUTING rather
#     than recording.
# 38: An `unread_retired_value` tripwire, and the register behind it.
#
#     `KEY_RETIREMENT` recorded THAT a key was retired and nothing recorded
#     whether anything reads it forward, so the README and the wiki both said
#     `sessions.location` is read forward as `place`/`route` and no reader in
#     the package names it. Nobody was lying: a rename that widened and a
#     split into other types were assumed to be one kind of event.
#
#     `KEY_FORWARD` names the one CALLABLE that reads each mapped key forward,
#     and a test reads that callable's source for the key - naming a table
#     cannot be checked, and a register that certifies an absent reader is
#     worse than no register. `TERMINAL_RETIREMENT` says why the rest are
#     never read and what the athlete does instead, per key, because the two
#     terminal retirements here need opposite advice.
#
#     The tripwire is `review` and fires once per field, not once per line: a
#     record predating a retirement carries the old key across its whole
#     history. It does not claim the value is lost - the column still holds
#     it - only that no successor inherited it, so nothing built on the
#     successors sees it.
# 39: `verdicts` gains `observed_days` (#93, ask 2).
#
#     Contract 29 added `window_days` because "a statistic with no stated
#     population is half an answer and the missing half is the misleading
#     one". That was the DENOMINATOR. This is the numerator, and without it
#     the same sentence applies again: `sleep 6.7, window_days 7` is published
#     by this corpus for a week holding ONE night, judged against a floor and
#     rendering exactly like a week holding seven.
#
#     "No unaccounted efforts" becomes "no unaccounted efforts across 78 per
#     cent coverage", which the issue rightly calls a different and honest
#     claim. Every AVERAGE row carries it, the RED-S intake and protein floors
#     included - those fire from seven logged days inside a fourteen-day
#     window, so the fraction varies most exactly where it matters most.
#
#     NO THRESHOLD ANYWHERE IN IT. The engine does not decide how thin is too
#     thin - that number would have no published basis and this repo has paid
#     for hand-rolled cutoffs before (G85). It states the denominator and the
#     numerator and lets the reader judge.
# 40: `provenance` gains `field_sources` (#325).
#
#     A wrist watch and a rowing console recorded one session: the watch had
#     heart rate and an energy estimate, the console had distance, stroke rate
#     and watts. One session, two instruments, and the right outcome is one
#     row carrying both - which the resolution layer already produces, with
#     `source` reading `matrix-console+polar` to say so.
#
#     What it could not say is WHICH SOURCE SUPPLIED WHICH FIELD - the
#     CHANNEL, and the distinction is this repo's own (#35/#51): `source` is
#     the channel a value arrived by and `origin` is the instrument that
#     observed it. A watch relayed through a platform has one origin and two
#     possible sources, so a map keyed on source answers "which feed" rather
#     than "which device". The issue asks for instruments and proposes a
#     `source_of` map holding source values; this ships the map it proposes
#     and says plainly which of the two it carries. The origin chain is on the
#     same row, in `chain`. The
#     merged row's single `source` is true of half its values and false of the
#     rest, and a consumer emitting a per-value `source` - which the fact-pack
#     shape already does - was therefore uniformly wrong for half of them.
#
#     `explanations` looked like the answer and is not: it records the winner
#     of a CONTEST, and complementary instruments never contest. Heart rate
#     had one witness, distance had one witness, and a field with one witness
#     "is taken verbatim and explains nothing" - deliberately, or the
#     explanations become noise. So the case this is about was exactly the
#     case that stayed silent.
#
#     DERIVED, NOT STORED, and present only where MORE THAN ONE SOURCE
#     contributed - not merely more than one row, since two claims from one
#     writer are one writer. Nothing is asked of the athlete and nothing
#     changes on a single-source row, where the row's own `source` is already
#     the whole truth.
#
#     KNOWN LIMIT, stated rather than discovered later: a `provenance` row is
#     keyed by (dataset, date, origin) and carries no ordinal, so two MERGED
#     activities on one date - a morning and an evening outing, each watch
#     plus console - produce two rows a consumer cannot tell apart. That
#     ambiguity predates this column and is harmless for `trust` and `chain`,
#     which are cluster-symmetric; it is not harmless for per-field
#     attribution, and closing it needs an identity on the provenance row.
CONTRACT_VERSION = "40"

_TEXT_COLS = {"statistic", "answers",            # a slug, and REAL affinity would
              # A JSON map (#325), and every container column is TEXT for
              # the same reason `derived_from` is: REAL affinity would
              # mangle the serialised text.
              "field_sources",
              # `place_precise` (#205) has NO column and is absent from every
              # default projection, but `column_affinity` answers for any name
              # it is asked about and told a consumer building its own
              # projection that a street address was REAL. A field the engine
              # will not project still has to be described honestly.
              "place_precise",
                                      # have made `column_affinity` lie about it
              # Both word-valued (#145, #139), and `pain_side` was already
              # here while its own mirror was not - so `column_affinity`, the
              # accessor #257 published precisely so consumers stop guessing,
              # answered REAL for two columns holding "left" and "took_place".
              "body_side", "outcome",
              "derived_from", "derived_op",  # both TEXT: `derived_op = "7"`
              # under REAL affinity silently becomes 7.0, which is the defect
              # the `activity_id` note below already warns about
              #
              # `contract` is a version STRING and `policy_asof` an ISO date;
              # both are digits and hyphens, so REAL affinity would turn "21"
              # into 21.0 and lose the distinction. `statement`, `week` and
              # `metric` are already below, on other datasets.
              "basis_claims", "surface", "policy_asof", "contract",
              "track", "basis", "start", "end",
              # `polarity` and `breach` are words; a band's bounds are numbers
              # and stay numeric.
              "polarity", "breach",
              "lifecycle_status", "achievement_status",
              "rpe_scale", "mood_scale", "pain_scale",
              # `due` is an ISO date too (#202).
              "due",
              "date", "type", "source", "location", "note",
              "kind", "statement", "model", "evidence",
              "week", "metric", "verdict",
              # policy datasets
              "slug", "title", "tracker", "policy", "period", "on_period_end",
              "deadline", "status", "motivator", "rationale", "on_success",
              "on_miss", "accountability", "set_by", "reason", "key",
              "change_kind", "goal",
              # derivations
              "dataset", "contribution", "label", "bucket", "direction",
              "declared", "last_edited",
              # increment 2: provenance, context, resolution.
              # `mood`/`pain` and the two resolution VALUES stay numeric-
              # affinity on purpose - a claim's value may be a number, and
              # TEXT affinity would stringify it for every consumer.
              "feel", "coverage", "pain_site", "pain_side", "start_time", "setting",
              "route", "place", "with", "context", "planned", "weather",
              "facilities", "mode", "depends_on",
              "claim_id", "merged_into", "retracted_by", "cascaded_from",
              "field", "chosen_source", "over_source",
              "tier", "quantity_class", "severity", "detail",
              # increment 3: the medical layer and the safety outputs
              "title", "body_site", "status", "resolved_date", "restricts",
              "provider_type", "source_kind", "escalation", "level", "trigger",
              "action", "onset_date", "precondition", "occurred_date",
              "result",
              # #35/#51: the provenance chain.
              "origin", "path", "origin_evidence", "trust", "chain", "compares",
              "capture", "read_by",
              "discarded",
              "modelled", "type_source",
              "scope",
              # #43. `activity_id` MUST be TEXT: a REAL-affinity column
              # converts "9914203377" to a float, which destroys leading
              # zeros and any id past 2^53 - silently, and in exactly the
              # field whose whole job is to be an opaque token.
              "track", "activity_id", "activity_source",
              # G86: events, and the goal fields that anchor to them.
              "event_date", "priority", "event", "deadline_kind",
              "verification",
              # #37: the three clocks
              "recorded_at", "measured_at",
              # #105: which machine wrote the line down
              "device",
              # #80: the artifact store. `sha256` and `artifact` MUST be TEXT
              # for the same reason `activity_id` is - a content address is an
              # opaque token, and REAL affinity would mangle one silently.
              # `bytes` stays numeric so a consumer can sum held storage.
              "sha256", "artifact", "media_type", "captured_at",
# #97: the set. `exercise`, `machine` and `tempo` are labels;
              # the reps, loads and counters stay numeric.
              "exercise", "machine", "load_type", "load_unit", "set_type",
              "failure", "side", "tempo", "session_start",
# #96: the itemised meal estimate. The per-100 g figures and the
              # gram range stay numeric; only the labels are TEXT.
              "meal", "item", "food_table",
# #99: the categorical modifier axes. The parametric ones stay
              # numeric - including the machine-scoped ordinals, which ARE
              # numbers, just not comparable ones.
              "equipment", "angle_class"}

# APPENDED, so a consumer reading by name is unaffected and one reading
# positionally keeps every column it knew. `reason` (#177) is null on every
# judged row and never null on a refusal; `answers` (#185) is the exact
# inverse, and the two together mean a row always says either what it vouches
# for or why it will not.
VERDICT_KEYS = ["week", "metric", "value", "target", "verdict", "goal",
                "reason", "due", "statistic", "window_days", "observed_days",
                "answers"]

# Derived tables (rebuilt every build, like everything else in derived/).
CONTRIBUTION_KEYS = ["date", "goal", "metric", "dataset", "period", "value",
                     "counted", "contribution", "headroom"]
MILESTONE_KEYS = ["date", "goal", "period", "fraction", "value", "target", "label"]
CHURN_KEYS = ["date", "slug", "kind", "metric", "edit_no", "before", "after",
              "direction", "deadline_pushed", "deadline_kind", "reason",
              "set_by", "suspicious", "unexplained"]
PROGRESS_KEYS = ["slug", "title", "metric", "policy", "status", "period",
                 "bucket", "target", "counted", "unbudgeted", "progress_pct",
                 "dataset", "scope", "declared", "last_edited", "deadline",
                 "deadline_kind",
                 "days_to_deadline", "event", "verification", "motivator",
                 "tracker", "milestones",
                 # Appended (#200), so a positional reader keeps every column
                 # it knew. `progress_pct` above is now the FLOOR's measure
                 # and is null for the other three polarities.
                 "polarity", "target_hi", "room_left", "distance", "breach",
                 # Appended (#235), so a positional reader keeps every column
                 # it knew. `status` above stays, carrying the same value as
                 # `lifecycle_status`, so a consumer reading the old name is
                 # not broken by the split.
                 "lifecycle_status", "achievement_status",
                 # Appended (#273), for the same reason as the two blocks
                 # above. A LEVEL goal is scored on its latest observation
                 # rather than on a sum, so it carries `observed` where a flow
                 # goal carries `counted`, and which side holds the number is
                 # how a consumer tells the two shapes apart.
                 "observed"]

# Increment 2: the adjudication trail. Primary dataset tables hold CANONICAL
# rows; these say where those rows came from and what was overruled.
CLAIM_KEYS = ["claim_id", "dataset", "date", "source", "kind", "merged_into",
              "retracted"]
RESOLUTION_KEYS = ["date", "dataset", "field", "chosen_source", "chosen_value",
                   "over_source", "over_value", "witnesses", "reason",
                   "disagreed", "independent", "compares", "discarded",
                   "unattributed_loser"]
JUSTIFICATION_KEYS = ["date", "dataset", "field", "claim_id", "source", "tier",
                      "quantity_class", "witnesses", "origin", "trust"]
CONSERVATION_KEYS = ["date", "kind", "detail", "severity"]
RETRACTION_KEYS = ["date", "kind", "claim_id", "retracted_by", "reason",
                   "cascaded_from"]
# Increment 3. `gates` is the table a consumer must respect before suggesting
# any activity; `escalations` is the deterministic severity-to-action output.
GATE_KEYS = ["date", "source_kind", "slug", "restricts", "reason", "severity",
             "status", "precondition", "escalation"]
ESCALATION_KEYS = ["date", "level", "trigger", "detail", "action"]

PROVENANCE_KEYS = ["date", "dataset", "origin", "independent_sources",
                   "trust", "chain", "field_sources"]

# One row per (track, distance), because a track can hold several efforts and
# hanging them off `sessions` would flatten that.
BEST_EFFORT_KEYS = ["track", "date", "distance_m", "seconds", "start", "end",
                    "basis"]

# Owned by `weeks`, which computes them, rather than restated here: the two
# going out of step is the failure this whole table exists to stop happening
# one layer up.
SESSION_WEEK_KEYS = _SESSION_WEEK_KEYS

DERIVED_TABLES: dict[str, list[str]] = {
    "session_weeks": SESSION_WEEK_KEYS,
    "best_efforts": BEST_EFFORT_KEYS,
    "provenance": PROVENANCE_KEYS,
    "verdicts": VERDICT_KEYS,
    "contributions": CONTRIBUTION_KEYS,
    "milestones": MILESTONE_KEYS,
    "plan_churn": CHURN_KEYS,
    "goal_progress": PROGRESS_KEYS,
    "claims": CLAIM_KEYS,
    "resolution": RESOLUTION_KEYS,
    "justifications": JUSTIFICATION_KEYS,
    "conservation": CONSERVATION_KEYS,
    "retractions": RETRACTION_KEYS,
    "gates": GATE_KEYS,
    "escalations": ESCALATION_KEYS,
}


# Columns whose value is a LIST, JSON-encoded into a TEXT column by `_scalar`.
#
# Declared rather than inferred, because a consumer cannot tell one from a
# scalar by looking: both arrive as TEXT, and reading a JSON array as a string
# is the failure mode that drops the whole field rather than raising. #257's
# consumer hit the scalar half of exactly this.
#
# Every member must also be in `_TEXT_COLS` - a JSON array under REAL affinity
# is mangled - and `test_every_list_column_is_text` asserts it. The set is
# checked against the fixtures in both directions, so it cannot quietly
# describe a field that stopped being a list or miss one that became one.
LIST_COLS = frozenset({"derived_from", "basis_claims"})


def _cols(keys: list[str]) -> str:
    return ", ".join(f"{k} TEXT" if k in _TEXT_COLS else f"{k} REAL" for k in keys)


def column_affinity(field: str) -> str:
    """The SQLite affinity this engine gives `field`: `TEXT` or `REAL`.

    Public because a consumer building its own projection needs it and had no
    way to get it. `_TEXT_COLS` is a private set that has grown by roughly one
    entry per contract, so a consumer's own copy is stale the moment it is
    written - which is #257's whole complaint, and the reason the answer must
    come from here rather than be reproduced there.
    """
    return "TEXT" if field in _TEXT_COLS else "REAL"


def build_db(derived: Path, datasets: dict[str, list[dict]],
             verdicts: list[dict] | None = None,
             derivations: dict[str, list[dict]] | None = None,
             policy: str | None = None, built_on: str | None = None) -> Path:
    """Write the read model. `derivations` carries the computed tables
    (contributions, milestones, plan_churn, goal_progress); `verdicts` stays a
    named argument because it predates them and callers pass it positionally.

    `policy` is `config.policy_digest(cfg)` - the hash of the policy the
    record does not hold (#148). Optional so a caller building a read model
    from datasets alone still works, and ABSENT rather than a placeholder
    when it is not supplied: a fixed string would read as "policy unchanged"
    across two builds that were judged differently, which is the one wrong
    answer this row exists to prevent."""
    derived.mkdir(exist_ok=True)
    db = derived / "health.db"
    db.unlink(missing_ok=True)
    computed = dict(derivations or {})
    computed["verdicts"] = list(verdicts or [])
    con = sqlite3.connect(db)
    try:
        for table, keys in KEYS.items():
            # The precise tier has NO COLUMN (#205). It would be null on every
            # row anyway, because the rows reaching here came through the
            # coarse projection - and a null column is worse than no column:
            # it reads as "nobody wrote one" rather than "you are not being
            # shown this", which is the same distinction `schema.coarse` drops
            # the key for. A read model is a serialisation, so it is inside
            # the boundary and not an exception to it.
            _table(con, table, [k for k in keys if k not in PRECISE_KEYS],
                   datasets.get(table) or [])
        for table, keys in DERIVED_TABLES.items():
            _table(con, table, keys, computed.get(table) or [])
        con.execute("CREATE TABLE meta(key TEXT, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('contract', ?)", (CONTRACT_VERSION,))
        if policy is not None:
            con.execute("INSERT INTO meta VALUES ('policy', ?)", (policy,))
        # WHICH DAY THIS WAS BUILT AS OF (#207). `goal_progress` is
        # materialised against a viewpoint, so without this a consumer cannot
        # tell "the athlete declared no goals" from "none were in force on the
        # day someone happened to run the build" - an empty table reads as an
        # absence either way, and nothing in the database could say otherwise.
        if built_on is not None:
            con.execute("INSERT INTO meta VALUES ('built_on', ?)", (built_on,))
        con.commit()
    finally:
        con.close()
    return db


def _table(con: sqlite3.Connection, table: str, keys: list[str],
           rows: list[dict]) -> None:
    con.execute(f"CREATE TABLE {table}({_cols(keys)})")
    if rows:
        con.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' * len(keys))})",
            [tuple(_map_cell(r.get(k)) if k in MAP_COLS else _cell(r.get(k))
                   for k in keys) for r in rows],
        )


# COLUMNS WHOSE VALUE IS A MAP (#325). Scoped rather than handled in `_cell`,
# because `_cell` sees every raw line's every field: a blanket dict branch
# turned a malformed `note: {...}` on an athlete's line from a loud
# `InterfaceError` at build time into a silently stored JSON string. Widening
# what the engine accepts is not a side effect a serialiser gets to have.
MAP_COLS = frozenset({"field_sources"})


def _map_cell(v: object) -> object:
    """A map column, key-sorted.

    Sorted for the reason a list column is value-sorted: what a merged row
    says about which source supplied which field does not depend on the order
    the fields happen to be walked in, and two builds of one record must
    compare equal as text.
    """
    if not isinstance(v, dict):
        return _cell(v)
    return json.dumps({k: str(v[k]) for k in sorted(v)}, separators=(",", ":"))


def _cell(v: object) -> object:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (list, tuple)):
        # `derived_from` is the first list-valued column (#170). JSON, with
        # separators pinned so the text does not depend on a default that can
        # change, and SORTED so that two rows naming the same inputs in a
        # different order compare equal as strings - the order an author
        # happened to type is not part of what the lineage says. A consumer
        # reads it with `json.loads`.
        return json.dumps(sorted(str(x) for x in v), separators=(",", ":"))
    return v
