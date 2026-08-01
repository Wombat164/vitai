# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **`adduction` and `abduction` on the pattern axis** (#58). Found live, on a
  machine the athlete was about to load. Twelve patterns and none of them
  named adduction, so a seated hip-adduction machine - about as direct a
  loaded hip movement as a gym contains - could not be described by the
  restriction system that exists to protect a hip.

  The coarse `restricts: strength` projection caught it. That is luck rather
  than design: had the restriction been written narrowly, which is exactly
  what post-coordination encourages, the precise form would have been the only
  one and would have said nothing.

  **`plane = frontal` is not a substitute**, and using it as one is the
  mistake this avoids: it would also catch abduction, lateral lunges and side
  planks, a far wider ban than any clinician said, and over-restriction is its
  own harm. A plane is where a movement happens; a pattern is what it does.

  Grounded rather than invented - the registry already carried `flexion`,
  `extension` and `rotate` from standard planes-of-motion terminology, so this
  finishes a vocabulary that was half adopted instead of starting a second one
  (G85).
- **A content-addressed artifact store** (#80). The evidence behind a value
  was discarded the moment it was read: an athlete photographs a gym console,
  a model reads the numbers off it, the numbers enter the record and the
  photograph is stored nowhere. So the richest single-instrument reading in a
  record was also the only one that could never be re-checked - and `#79`'s
  capture axis can say a value was *transcribed* without anything being able
  to say transcribed *from what*.

  `data/artifacts.jsonl` is a manifest (hash, media type, size, why it was
  kept); `artifact` on `weight`, `daily`, `sessions` and `measurements` cites
  a row in it. The reference is a content address (`sha256:...`) rather than a
  path, so it cannot drift from the row citing it, a filename is a validation
  error, and storing the same bytes twice stores one copy. One artifact can
  back several rows, which is why the manifest is its own dataset rather than
  a column - a console photograph carries distance, pace, power and stroke
  rate at once.

  `vitai artifact ls | get | verify`. `verify` checks both directions: PREMIS
  fixity (the stored bytes must hash to their own address) and referential
  integrity (a value whose evidence is gone). It fails on a promise the record
  is no longer keeping - and `not_erased`, an artifact the manifest says was
  deleted whose bytes are still on disk, is one of them: the athlete has no
  other way to find out. An orphan, a not-yet-cited artifact and a deliberate
  deletion are printed and do not fail a build, because a check that cries
  wolf over disk hygiene teaches the athlete to ignore the one finding that
  matters. `artifact get` requires `--out`: where personal bytes land is not
  something a default should guess.

  **Removed is not missing.** Deleting an artifact appends a tombstone with a
  reason rather than rewriting the row that cites it: a retention decision and
  a data loss are completely different facts and the record has to keep them
  apart. A removal without a reason is a validation error.

  The backend is behind an interface and the default is a local directory. The
  mechanism is public; the artifacts are personal data. Nothing here uploads,
  syncs or attaches - storing an artifact is not consent to transmit it - and
  no artifact, manifest row or hash of a real one appears in this repository,
  including in the tests, where the bytes are synthetic.
- **A value can say it was never measured** (#49, #88). The orthogonal
  question to origin and capture: those say which instrument and how it
  reached us, this says whether the number was observed at all.

  A model output arriving in a field whose name and type imply measurement is
  invisible by construction. `kcal_out: 1728` on two different dates is BMR
  modelling because the tracker was not worn - and **five separate instances
  turned up in one import**, which is what makes it a rule rather than three
  patches. `modelled` names the FIELDS on a row that are model outputs,
  because the distinction is per-field: one row can carry a measured step
  count and an estimated burn.

  The same defect applies to a categorical label. **1,093 of 1,502 session
  types in one live record were a vendor classifier's guess**, and nothing
  distinguished them from the 409 the athlete asserted - so any analysis
  grouping by `type` was silently mixing attestations with model output at
  unknown confidence. `type_source` records how a label was arrived at.

  A RED-S screen run on an estimated burn now **declares its basis** rather
  than declining. Refusing would remove a false positive by creating a
  silence, for every athlete whose tracker models their burn - which is most
  of them - and in that tier silence is the dangerous direction.
- **A capture axis: how a value was acquired** (#77, #78). Three questions
  were answered by one string and two of them had no field at all: what
  observed it (`origin`, shipped in #51), HOW it got here, and what evidence
  survives (#80, still to come).

  The athlete's framing is the issue: *"me telling narratively what the rower
  said is different from me taking a picture of it, or having a Bluetooth
  connection and seeing the data that way, or the app importing it through a
  connector."* Those four share ONE origin - the same console showing the same
  number - and have completely different error modes. So `capture` is a
  property of the ACQUISITION EVENT rather than of the chain: a photo-read and
  a BLE-read of one console on one evening are two claims with one origin and
  two captures.

  **The ordering is not a quality ranking.** `ble` has no reader in the loop
  and no durable artifact; `photo` has a reader in the loop but the evidence
  survives and can be re-read. Different virtues, and a query can ask for
  either. Grounded in FHIR `Observation.method`, which is deliberately
  separate from `Observation.device` and `Observation.performer`.

  `trust_ceiling` gains a `transcribed` level, taken as the weakest of the
  acquisition and the chain: a photograph of a console read by a model is an
  inference over an artifact, not a reading of an instrument, and must not
  present as device-measured.
- **`sessions` finally carries the provenance chain.** `origin`, `path` and
  `origin_evidence` landed on `weight`, `daily` and `measurements` in #51 and
  were never extended - and sessions is exactly where multi-instrument claims
  collide.
- **A catalogued source registry** (#79). Source names were free text, so a
  console meant whatever the writer typed that day, and nothing knew a scale
  cannot observe distance. `semantics/sources.toml` catalogues 49 instruments
  with a `kind` (Google Fit's `Device.type` axis, extended) and aliases, so
  `Polar Pacer Pro`, `polar-pacer-pro` and `PacerPro` are one thing.

  It answers `provenance.toml`'s own "roles, not vendors" rule rather than
  contradicting it: that file classifies what KIND of hop something is, this
  one normalises WHICH instrument. And it avoids the G85 failure the same way
  `session_types` did - an unrecognised source RESOLVES to `other` carrying
  its kind, never errors, and there is deliberately no `other-console` or
  `other-wearable` to multiply the catalog by the kind axis.

  **Nothing personal lives in it.** A source named for someone's own gym or
  their own spreadsheet resolves to `other`, which is what the catchall is
  for, and the checks work on the kind so nothing is lost by that.

  The catalog implies no precedence. Which instrument to believe stays in the
  athlete's config, because a figure stated in chat outranks a vendor channel
  in one record and would not in another.
- **A claim its instrument cannot have made is a validation finding.** A
  scale reporting distance, a rowing console reporting sleep: not resolution
  ties to adjudicate but rows that cannot be true as written.

  Held as a **deny list at the kind level**. It was first written as a
  per-instrument list of what each device CAN observe, and that was wrong in
  the direction that costs something - an Oura ring does report calories, a
  hand-typed row can carry a heart rate read off a watch, a relaying app
  carries whatever it received, and watch models differ. Every one of those
  was flagged by a whitelist that merely forgot them. An omission from a deny
  list produces silence instead.
- **`track`, `activity_id` and `activity_source` on `sessions`** (#43). The
  link from a session to the file that recorded it lived in a prose note and
  was recovered by regex - unqueryable, unvalidatable, and silently broken by
  any change of wording. Two fields rather than one, post-coordinated: `track`
  is a LOCAL ARTIFACT (a repo-relative path, what `vitai route` reads),
  `activity_id` is an EXTERNAL IDENTITY (what dedupes a re-run import). They
  have different lifetimes - an archive can be re-laid-out without the id
  changing, and an id is meaningless off-platform while the file stays
  readable. `activity_source` names who ASSIGNED the id, which is not
  necessarily who recorded the activity (#35).

  `vitai route --session <activity_id|date>` and `Vitai.session_route()`
  resolve the track from the record, so route geometry can rebuild from
  `data/*.jsonl` like everything else in `derived/`.

  An absolute path is a validation error - it leaks a username and a machine
  layout into a portable record, and breaks a rebuild anywhere else. A
  dangling pointer is an ADVISORY and never fails a build: the session is the
  fact, the track is an attachment.
- **The record is bitemporal: `recorded_at` on every dataset** (#37).
  Transaction time - when a line was *written* - alongside the valid time
  `date` already carried. Found on a live record: two `goals` rows shared an
  effective date, one superseding the other, and **nothing in the data said
  which won**. Resolution fell back to file order, which is real information
  right up until a sort, a reformat, a merge or a git conflict resolution
  rewrites it. An ordering a formatter can change is not an ordering.

  Putting a time on `date` would have been the wrong repair: it forces the
  athlete to state something they never meant - "I decided this at 14:32" is
  a fact about a keystroke - and it still would not sort, because **valid
  time is not monotonic and must not be**. A line written today about a
  decision made last week is legitimately backdated. Transaction time is
  monotonic by construction and never authored by a human, which is exactly
  what a tie-break needs (Snodgrass: valid time vs transaction time).

  The migration is a **read no-op**: absent sorts before present, so a file
  of unstamped rows resolves in exactly the order it always did.
- **`append_many` / `Vitai.append_many()` and JSONL on `vitai append`'s
  stdin** (#44). The primitive bulk import actually wants: the file is read
  once to find where the clock got to, every row is stamped strictly past the
  one before it, every row is validated before any is written, and the batch
  lands in a single open. Looping over the single-row form re-parses a growing
  file per row - 5,425 rows take 0.11 s as a batch against 2.5 s for 1,000 in
  a loop, and the gap widens with the import. A batch containing one bad row
  writes nothing at all, rather than leaving a caller to work out how far it
  got.
- **`vitai append` / `Vitai.append()`** (#37). The write half of P9, and the
  reason the clock is trustworthy rather than aspirational: every row in this
  record is written by a hand-rolled script, and a field callers must
  remember to set will be absent exactly when two rows land on the same date,
  which is the only moment it was needed. Append stamps `recorded_at` and
  `_gen`, fills absent keys with null, **refuses a caller-supplied
  `recorded_at`** - a clock you can write is not a clock - and validates
  before writing, because an append-only file cannot be un-appended.
- **`weight.measured_at`** (#37): observation time, HH:MM local. Body mass
  swings about a kilogram between morning-fasted and evening, so an
  unrecorded drift from evening to morning weigh-ins manufactures a week of
  apparent progress. Absent stays absent - the engine never infers a probable
  weigh-in time, it says the rate could not be checked.

- **Events: the dated fixtures a plan is built backwards from** (#24, G86).
  A new `events` dataset - a race, a scan, a wedding, a competition weigh-in.
  An event is not a milestone: a milestone is a fraction of a target the
  engine DERIVES from progress already made, while an event happens whether
  the athlete is ready or not and is owned by somebody else. Two concepts had
  one word and only the derived one existed. Goals anchor to an event, and an
  immovable fixture makes the goal's deadline hard by derivation rather than
  by re-declaring it. `vitai events` + `Vitai.events()`, and a "Coming up"
  countdown in the weekly rollup.

  The vocabulary is a registry (`semantics/events.toml`), post-coordinated on
  two axes: `kind` (what sort of fixture) from RFC 5545 VEVENT, and
  `priority` (how much the plan bends for it) from Friel's A/B/C.
- **Attested-only goals** (#24, G86/G83). `verification` says who can ever
  settle a goal: the engine (`measured`), another app (`external`, the G19
  case) or *nobody* (`attested`). "I want to enjoy running again" has no
  metric and never will, and the schema REQUIRED one - so the thing athletes
  say they would be saddest to lose in five years had nowhere to live at all.
  The engine now holds a goal it can never verdict: it tracks it, surfaces
  it, asks about it, and takes the athlete's word as the only evidence there
  will ever be. An attested goal is never scored and never rendered at 0%.

### Fixed
- **An unattributed row lost every contest it entered, silently** (#73). A
  row with no `source` ranks last in the precedence ladder - right for
  genuinely unknown provenance, wrong for the commonest cause, which is a
  writer that forgot to stamp it.

  **The asymmetry is the point.** A vendor channel always stamps itself,
  because a machine wrote it. A hand-entered figure, a chat-stated number, a
  note typed on a phone are the rows a human forgets - and they are exactly
  the rows the ladder is written to rank ABOVE vendor channels. So the
  omission inverted the ladder precisely where it matters, twice in one live
  session, both times worth over 1,000 kcal/day.

  Three things now report it. `vitai validate` flags a source term present in
  data but absent from the ladder, catching the cheaper instance at the door -
  and it found five in this repo's own demo on its first run, including a
  first-hand `hand` reading sorted below two relayed vendor channels.
  Resolution records EVERY discarded claim rather than only the runner-up, so
  a resolved value can say what it beat. And an `unattributed_claim_lost`
  tripwire fires when a claim carrying no source was discarded with a
  different value.

  **Ranking is deliberately unchanged.** Whether unattributed should sort
  last at all is a real question, and changing it silently would be its own
  inversion; what was unacceptable was that it happened with no trace.
- **`recorded_at` is now strictly monotonic, so bulk-appended rows can
  actually be ordered** (#44). Importing 227 readings through the helper #37
  added produced **one distinct stamp across all of them** on this machine -
  a second is an eternity in a write loop, and the monotonicity check admitted
  equal when equal is the failure case. A tie orders nothing, which was the
  field's only purpose.

  The stamp is now a hybrid logical clock at microsecond resolution:
  wall-clock time whenever it has genuinely moved on, otherwise one tick past
  its predecessor. Under load it drifts microseconds ahead of true time, which
  is the right trade - an ordering that is occasionally a few microseconds
  optimistic is strictly better than one that does not exist. A wall clock
  more than a minute BEHIND the last stamp is refused rather than clamped,
  because that is a wrong clock rather than a coarse one.

  Bulk import is not an edge case here, it is how rows arrive: every source so
  far lands as hundreds of rows in a tight loop. It also blocked #37's own
  migration, since backfilling offsets across 172 session rows is itself a
  bulk write.
- **A repeated `recorded_at` is now reported whatever the rows are dated.**
  The tie check keyed on `(identity, date, recorded_at)`, so a bulk import
  spanning 227 different dates stamped every row identically and `vitai
  validate` called the file valid. That narrow check is what let the defect
  hide. A serial appender cannot write two rows at one instant.
- **Transaction time is compared as an INSTANT, not as text.** Two stamps
  written either side of a timezone change were ordered by wall clock, since
  `+02:00` sorts after `+00:00` as a string regardless of which came first -
  the #38 mistake, one clock over.
- **A record holding both naive and offset-aware `start_time` no longer
  crashes the build** (#38). `_same_activity` raised
  `TypeError: can't compare offset-naive and offset-aware datetimes` the
  moment both shapes coexisted - and the schema's own validator example shows
  an offset while the Polar connector wrote naive, so **following the
  documentation broke the engine**. That is the worst version of this bug: it
  punishes the correct behaviour.

  It also blocked its own repair. Offsets cannot be backfilled row by row,
  because from the first converted row until the last the record holds both
  shapes and is unbuildable - so the comparison had to tolerate the mixture
  before any migration could begin.

  **No offset is guessed.** Two naive values share a frame by construction and
  stay comparable; two aware values compare as instants across differing
  offsets; a MIXED pair is declined and reported, and the weaker shape test
  decides. The obvious repair - lend the aware row's offset to the naive one -
  fails on the commonest pairing there is, since platforms routinely emit UTC
  beside a connector writing naive local time, and a `+00:00` lent to a
  `+02:00` row lands two hours from where it happened while still looking like
  a clean instant. A misplaced instant is worse than an absent one.

  The undecidable case is reported as `incomparable_timestamps` rather than as
  a shape-only merge: both rows *have* a `start_time`, and telling the athlete
  to record one they already have would send them nowhere. `vitai validate`
  reports a mixed record as an ADVISORY, never an error - those rows are
  history, not mistakes.

  GPX fix times are now read as UTC when written without a designator, which
  is what GPX 1.1 specifies rather than a guess, so one track carrying both
  spellings cannot raise either.
- **A weight rate no longer prints an actionable verdict it cannot support**
  (#37). When the weigh-in times behind a rate are spread widely enough that
  the diurnal drift alone accounts for it, the rollup reads `NOT READABLE -
  weigh-in times vary too much` and `verdicts` emits `nodata`, both alongside
  the number and a caveat quantifying the spread. Previously the demo record
  rendered `SLOW - check logging` off a rate that 12.4 h of weigh-in spread
  could fully explain - advice to cut harder, derived from a clock. P3:
  confidence never launders upward, and a crisp verdict on an unreadable
  number is exactly that.

- **A moved SOFT deadline is no longer flagged as goalpost-moving** (#24,
  G86/G20). `deadline_kind` (`hard` | `soft`) on goals. A race date cannot be
  moved, so pushing it is a retreat from something real; a date the athlete
  invented is a direction of travel they may revise at no cost to anyone, and
  flagging that accuses them of gaming a commitment nobody else ever held
  them to. A live record was carrying exactly that false positive.

  Where hardness is UNKNOWN - a goal written before the field existed - the
  engine records that the deadline moved and says it does not know whether
  that matters, rather than guessing in either direction. The push is never
  hidden; only the accusation is withheld. A loosened TARGET is still flagged
  regardless, so hardness cannot be used to launder a genuine retreat.
- **A goal correction is no longer counted as churn** (#26, G31). `goals`
  gains `change_kind` (`change` | `correction`), which `thresholds` has had
  since G31 and which matters more on goals because goals are what
  `plan_churn` analyses. A correction asserts the retired line was never a
  real intention; counting it manufactures a plan-stability problem that does
  not exist. A correction must carry a `reason` - unexplained, it cannot be
  told from a quiet retreat wearing the right label.
- **A goal scoped to `weight` or `measurements` reports unknown progress, not
  0%.** `GOAL_DATASETS` widened in #18, but the contribution engine only
  iterates `daily` and `sessions`, so a weight goal silently rendered as
  `0/78 (0%)`. Telling an athlete who has lost 3 kg that they are at 0% of
  their weight goal is the G69 harm in a new place. Reaching a target from a
  starting point is an APPROACH, not an accumulation, and modelling it needs
  the goal KINDS of G62; until then the engine says it does not know, which
  is both true and safe.

### Changed
- **Vocabularies are curated registries, not Python sets** (#18, G85).
  `semantics/session_types.toml` and `semantics/restrictions.toml` join
  `body_sites.toml`, loaded by a new `vitai.vocab`.

  The root cause, stated plainly: *a vocabulary in code can only be extended
  by a developer, so it can only ever contain what the developer had seen.*
  `gym_a` and `gym_b` - one athlete's Strength A and Strength B days - shipped
  in a public MIT engine, while cycling, swimming, rowing, hiking, yoga,
  climbing, skiing and every team and racket sport collapsed to `other`.
- **Restrictions are post-coordinated.** `ACTIVITY_CLASSES` mixed a scope
  quantifier, a setting, a loading modality, anatomical regions and specific
  activities in one flat list, and could not express two real clinical gates:

  | The clinician said | The old vocabulary |
  |---|---|
  | No loaded lumbar flexion | no value came close |
  | No loaded hip work, squats still fine | `lower_body` bans the permitted squats |

  Both sat in a live record with `restricts: null` and a RESTRICTION NOT
  ENFORCEABLE marker, because a wrong gate is worse than an unenforced one -
  so an athlete with an active injury gate got `no active safety escalations`.
  A new `restriction` field (gen 3) says it on separate axes:
  `pattern=hinge region=hip load=loaded`. An absent axis means "any"; a squat
  is `pattern=squat`, so the hip rule leaves it alone. `region` reuses
  `body_sites.toml` wholesale, sites and regions and aliases - "lumbar"
  resolves to `lower_back`.
- **`Vitai`/`safety` gained `is_movement_gated`** for "may I do a hip thrust
  today", alongside `is_gated`'s "may I run today".
- **Session-to-gate-class mapping moved into the registry.** The hardcoded map
  gave `gym_a` and `gym_b` identical class sets, so the two labels carried no
  gating information at all - which is its own evidence they were programme
  names rather than a taxonomy.
- **A goal can be scoped to `weight`** (folded in from #24): `dataset` accepted
  only `daily`/`sessions`, so a weight goal - the most common goal in the
  domain - had nowhere to point.
- `docs/vocabularies.md` records the rule and the sweep.

### Fixed
- The rollup counted strength sessions with `startswith("gym")`, which would
  have silently zeroed the weekly column on any rename. No test covered it;
  one does now.

### Deliberately not done
- **`gym_a`/`gym_b` are retired, not deleted.** A value-level retirement
  (`KEY_RETIREMENT` works on keys, not values): they stay legal forever, stop
  being offered, and resolve forward to `strength`.
- **`severity` keeps `red_flag`.** It does mix a magnitude scale with a
  routing decision, but it is what the safety asymmetry rests on and what the
  ingest skill instructs writing. Its own change, not a side effect here.
- **`restricts` survives as a coarse projection**, so no read-model consumer
  breaks.
- Seven non-safety vocabularies (`CONTEXT_MODES`, `SETTINGS`, `WEATHERS`,
  `MEASUREMENT_KINDS`, `SESSION_CONTEXTS`, `PROVIDER_TYPES`, `FEELS`) are
  still Python sets with their defects documented. Next slice.

Safety layer: the persona guardrail fixtures now hold (issue #12). All eight
`xfail(strict=True)` specifications flip to passing.
### Added
- **`vitai check` - adjudicate a stated value against the record** (#15).
  An LLM coach narrates numbers, and its narration is as untrustworthy a
  source as any vendor estimate. P1 says sources are claims the engine
  adjudicates; that rule had never been applied to the coach's own sentences.
  `check` answers **CONFIRMED / REFUTED / NOT-IN-RECORD** with the values and
  the delta, and exits 1 on a refutation so a skill can be held to the record
  mechanically rather than on its honour.
  - It checks the claim against BOTH the day's total and each individual row,
    because "I ran 8k" may mean one 8 km run or two 4 km runs - and says which
    reading makes it true rather than picking one and being confidently wrong.
  - **NOT-IN-RECORD is a distinct verdict.** Absence cannot refute a claim: a
    day with nothing logged does not prove the run did not happen, and
    answering REFUTED there would be the engine overreaching in exactly the
    way it accuses the model of.
  - Tolerance is a config value (`[preferences] check_tolerance`, default 2%),
    not a constant.
- **`vitai day` / `vitai window` / `vitai ramp`** - read-only factual dumps
  that exist so a number is never stated from memory. `day` shows what the
  canonical row is hiding, including claims that were merged away. `window`
  totals over N **calendar** days, since a window that skipped the empty ones
  would report a fortnight as a week. `ramp` prints week-on-week volume with
  its **base-size caveat attached** - a ramp percentage over a one-week base
  is not a trend, and that maturity signal (G27) is engine-owned rather than
  something each caller has to remember to add.
- All four land as CLI **and** `Vitai.*` methods in the same change (P9).

### Fixed
- **Resolution no longer false-merges repeated similar activities** (#14).
  Shape-matching - same type, similar duration, similar distance - was being
  used as a proxy for identity when `start_time` was absent. For repeated
  activities it is a proxy for ROUTINE instead: a dog walked three times a
  day, a commute each way, sets of the same length. Anyone with a habit
  generates near-identical shapes by design, and the resolver was merging
  them. A real record reported **1.39 km** of walking on a day when **6.26 km
  across four walks** had happened, and nothing surfaced it.

  This is the mirror of double-counting and worse: double-counting inflates a
  number visibly, a false merge silently deletes data and leaves a plausible
  canonical row behind. Three changes:
  - A shape match now also requires **disjoint sources**. A genuine
    cross-platform duplicate has a signature shape does not carry - two
    different systems claiming one physical event. Two claims from the same
    source with the same shape are far more likely to be two real events, and
    an identical re-emission from one connector is a connector bug that
    exact-duplicate detection (G26) already covers.
  - More than two shape-alike, timestamp-less claims of one type on a date is
    a **routine, not a duplicate set** - none are merged.
  - Every shape-only merge, every near miss, and every routine left unmerged
    now emits a **visible tripwire** saying what was decided and that
    recording `start_time` resolves it positively. Previously a merge was
    invisible outside the `claims` table.

  `_same_activity` returns three outcomes rather than two -
  `match | possible | distinct` - so an uncertain pair is a refusal to decide
  rather than a weak merge.
### Added
- **Gate preconditions** (#19). A rehab plan says *"5 gentle hops on the right
  leg before each run; pain in the groin means do not run that day"* - a gate
  CONDITIONAL on a test performed that morning. The engine could say
  restricted or not restricted, so the whole instruction had to sit in a
  `note` where no rule could read it: the prose problem G28 exists to solve,
  reappearing one level down. A medical episode may now carry a
  `precondition` naming a daily check, with results in a new `checks.jsonl`.

  A preconditioned gate has **three** states, not two:
  - `cleared` - today's check passed; the restriction lifts, for today only;
  - `blocked` - today's check failed;
  - `check_not_done` - nothing recorded, and the restriction stands.

  **Not-done is not pass.** An athlete who never ran the check is not cleared
  by silence, and `Vitai.pending_checks()` lets a coach say "you have not done
  the hop test today" rather than assuming either outcome. This is the first
  mechanism that can CLEAR a gate from athlete-supplied input, so the
  asymmetry is preserved deliberately: only an explicit pass clears, and only
  for that day.
- **`onset_date` on medical, `occurred_date` on achievements** (#19). The row
  `date` was doing double duty as when-this-was-written and
  when-it-began. Recording a resolved 2025 injury today produced
  `resolved_date 2025-12-01 precedes onset 2026-07-27`, and back-dating the
  row to work around it destroyed the only record of when it was entered -
  which P2 needs (the record is a timeline of what was KNOWN when) and G29
  needs (a condition recorded today that began two years ago should inform
  old weeks). Both dates now exist; onset defaults to the row date, so
  nothing existing moves.
  - `resolved_date` is validated against onset rather than the entry date.
  - The episode window opens at **onset**; head selection still reads `date`,
    because P2's as-of reconstruction is a question about knowledge.

### Changed
- `meta.contract` is **5**: adds the `checks` table, `onset_date`/
  `precondition` on `medical`, `occurred_date` on `achievements`, and
  `status`/`precondition` columns on `gates`. **A consumer reading `gates`
  must now check `status`** - a row with status `cleared` is reported but does
  not block.
- The demo carries a conditional gate whose check passes, fails, and is left
  undone on consecutive days, so all three states render; plus a historical
  episode with an onset two years before its entry date.

Increment 3 - medical layer + SAFETY ESCALATION (G11 + G28). Read-model
contract bumped to **4**.

### Added
- **`medical.jsonl`** (G11): one condition's whole lifecycle under a `slug` -
  onset, visit, restriction, resolution. Carries `severity` that the ENGINE
  reads, `restricts` (which activity classes are gated), `resolved_date`
  (which closes the episode window streak-forgiveness will be computed from),
  and a coarse `provider_type` - which KIND of clinician, never which one.
- **Deterministic severity-to-action (G28)** in `safety.py`. This was the last
  decision outside the P4 firewall: "see a clinician" lived as prose in a
  skill file, where a coach optimising for adherence could reason around it,
  soften it, or never reach it. It is now a branch, and the escalation
  messages are module constants - what an athlete reads in an emergency is
  exactly what was reviewed and tested, not something a model assembled.
  - a symptom CLASS beyond musculoskeletal: pain recorded at `chest` routes
    to a clinician from EITHER dataset, because `chest` is a legitimate
    musculoskeletal site and that is exactly the trap - a coach handed it
    alongside a hip will happily suggest a substitution;
  - ABSOLUTE-danger thresholds judged with no reference to baseline (resting
    heart rate outside 30-120, self-reported pain at 9+). The existing rhr
    tripwire is relative, which is the right tool for fatigue and the wrong
    one for danger: a baseline that drifted upward over months never trips;
  - a **RED-S / low-energy-availability composite** over deficit + rate of
    loss + training load - the syndrome that a tool which coaches deficits
    can itself cause, which is why the engine watches for it rather than the
    athlete;
  - an explicit `severity: red_flag` path, honoured whoever wrote it.
- **Gates as data.** An open episode that restricts an activity class, or
  pain over the configured gate, produces a gate row carrying its own
  escalation text. `Vitai.gated("run")` is a deterministic fact about a date.
- **The fast path.** The weekly cadence is right for coaching and wrong for
  danger. Anything urgent dated today prints at `vitai build` time on stderr,
  before any coaching output exists to bury it, and `vitai safety` exits **2**
  while something urgent stands so a script can ask "safe to train today?"
  without parsing prose.
- **`vitai safety`** plus `Vitai.safety()`, `.urgent()`, `.gates()`,
  `.gated()`, `.episodes()` and `.safety_banner()` (P9 parity).
- **`vitai build --on DATE`** to evaluate gates, escalations and the rollup as
  of a date - which is also what lets the demo render its own live gate.
- The weekly rollup gains a **Gates** section, below tripwires: a tripwire is
  something to discuss, a gate is already decided.
- The **never-shame carve-out is now written down** in the coach skill, with
  its boundaries: it licenses urgency and plainness, never blame; it applies
  only to the gate/escalation tier; the words are the engine's.

### Changed
- `meta.contract` is **4**, adding `medical`, `gates` and `escalations`. A
  consumer that renders training suggestions MUST read `gates` or it will
  propose activity the record has blocked.
- The rollup's pain tripwire reads `pain`/`pain_site` (falling back to the
  retired `hip_pain`) and names the site rather than assuming the hip.
- The CI demo job builds as of the synthetic athlete's last day and asserts
  a live gate renders and a resolved episode does not.

### Deliberately not done
- No diagnosis, ever. Every escalation routes to a human clinician and the
  banner says so.
- Out of scope per the plan: FHIR import, document attachments, medication
  interactions.
- Thresholds are conservative SCREENING bounds, not clinical criteria. The
  resting-heart-rate floor sits below a trained endurance athlete's genuinely
  low rate on purpose - a safety layer that cries wolf at normal athlete
  physiology teaches people to ignore it.

---

Body sites become a curated vocabulary (follow-up to increment 2).

### Added
- **`semantics/body_sites.toml`** - the first curated registry (P5): neither
  data nor code, versioned in-repo, human-mergeable, with its evidence in its
  own comments. About 25 musculoskeletal sites in a two-level
  `region -> site` hierarchy, each with aliases.
- **`pain_side`** (`left | right | bilateral | null`), post-coordinating
  laterality rather than baking it into the site name. This is the HL7 FHIR
  (`BodyStructure.includedStructure.structure` + `.laterality`) and openEHR
  (`CLUSTER.anatomical_location`) pattern - two standards that made the same
  call independently. It also stops the vocabulary doubling.
- **`vitai.anatomy`**: `resolve()` maps what an athlete actually types onto
  the canonical slug ("IT band" and "itb" -> `knee`, "lumbar" -> `lower_back`),
  plus `region_of()`, `is_paired()`, `describe()` and a verified-only
  `osiics_of()`.
- **`docs/prior-art-anatomy.md`** - the sweep behind all of the above, with
  adopt/adapt/avoid calls.

### Changed
- **`pain_site` is now a closed vocabulary** instead of free text, so "knee",
  "Knee", "left knee" and "patella" stop being four unrelated places. Unknown
  sites are rejected with the vocabulary listed; aliases are accepted and
  normalised to the canonical slug at read time.
- A **paired** site with a pain score now requires a side - "my knee hurts"
  does not tell a coach which knee to stop loading - and a **midline** site
  refuses one, because claiming a side there is false precision.
- Legacy `hip_pain` lines still map forward to `pain` at site `hip` and are
  deliberately given **no** side: the old field never recorded which hip, and
  inventing one would manufacture a fact.

### Deliberately not done
- No clinical ontology is vendored. SNOMED CT cannot be redistributed by
  non-Affiliates; UBERON is multi-species and runs to tens of thousands of
  classes. OSIICS (the IOC's sports system, free with acknowledgement) is
  mapped instead - but only the region letters verified from a primary source
  are recorded, and the rest are left blank rather than guessed.
- Pain remains one score at one site per day. Multiple simultaneous sites and
  pain quality (sharp/dull/burning) are not modelled.

## [Unreleased] - increment 2

Increment 2 - provenance, context, feel + RESOLUTION (G1, G3, G4, G7, G15,
G29). Read-model contract bumped to **3**.

### Added
- **The resolution layer (G15) - the conservation golden rule.** A calorie is
  eaten once and burned once. When two sources describe the same day, the
  record holds ONE canonical value per quantity, chosen by precedence, and
  never a sum. Three rules: per-quantity precedence (the watch wins
  `kcal_out` while the food ledger wins `kcal_in`, on the same day);
  activity identity, so one run logged on two platforms is one run, matched
  by intersecting `start_time` intervals or, lacking times, by type plus
  duration/distance tolerance bands; and energy as attribution, not addition
  - a device's daily burn already contains its sessions' energy.
  Primary tables now hold canonical rows; raw claims are projected to
  `claims`, and every adjudication is auditable.
- **Resolution explanations (G29)** as ROUTINE output, not an error channel:
  `vitai resolve` says which source won a contested field and why, every
  time, so "why does the record say 2,443" always has an answer.
- **Conservation tripwires**, flagged and never auto-fixed: sessions
  attributing more energy than the day measured, near-miss duplicate
  sessions that failed the fuzzy match narrowly, and high-precedence sources
  disagreeing beyond tolerance.
- **Claims as JTMS nodes (Doyle 1979) with cascade retraction.** Each
  resolved value carries a justification (`claim_id`, source, tier, quantity
  class). Revoking a justification retracts what stood on it: an inference
  declaring `depends_on` a corrected claim is retracted with it rather than
  left as a stale belief whose evidence no longer exists. The labeled-
  assumption-set and cascade-invalidate rule only - no ATMS engine, and
  confidence remains a property of tier and source, never LLM-assigned.
- **`daily` gen-2 fields**: `source`, `mood`, `feel`, `coverage`, and
  `pain` + `pain_site` generalizing `hip_pain`.
- **`sessions` gen-2 fields**: `source`, `start_time`, `elevation_m`,
  `setting`, `route`, `place`, `with`, `context`, `planned`, `weather`.
- **`measurements.jsonl`** (G16): sparse anchor-class reads that do not come
  off the scale (tape, DEXA, InBody). Anchors top the precedence ladder.
- **`context.jsonl`** (G34): dated situational mode, facilities and place.
  The engine uses it to EXPLAIN missingness rather than flag it - a week
  with no weigh-in while the facilities line says there was no scale is not
  a lapse. `has_facility()` deliberately distinguishes "no scale" from "we
  do not know".
- **`suppressed_metrics`** (G33, the subtractive primitive) and **`nudge_ok`**
  (G7) in `[preferences]`. A suppressed metric keeps being recorded and
  stops being scored: someone recovering from a bad relationship with a
  number can stop being judged on it without deleting their history.
- **`vitai resolve` and `vitai context`**, with `Vitai.resolution()`,
  `.canonical()`, `.explanations()`, `.conservation()`, `.retractions()`
  and `.context()` (P9 parity).

### Changed
- **Migration: `hip_pain` -> `pain` + `pain_site`.** No action required and
  nothing to rewrite. `hip_pain` is retired at generation 2, which means it
  stays legal forever and stops being required: old lines keep validating
  and the engine reads them as pain at site `hip`. A line carrying both
  keeps its explicit `pain`. The same mechanism retires `sessions.location`
  in favour of `place` + `route`.
- **`meta.contract` is 3.** Primary tables changed meaning: they now hold
  canonical rows rather than raw lines. A single-source repo is unaffected -
  where there is nothing to adjudicate, nothing moves, which the
  `test_single_source_resolution_is_byte_identical` regression pins.
- Weekly verdicts read `pain` (falling back to `hip_pain`) and skip any
  metric listed in `suppressed_metrics`.
- The demo athlete gained a mid-block generation switch (so one file holds
  both shapes), a declared travel week whose missing weigh-ins are explained
  by context rather than flagged, a two-source day resolving field-wise, a
  rainy partner walk on a named route, and sparse tape/DEXA measurements.

### Fixed
- **Resolution no longer false-merges repeated similar activities** (#14).
  Shape-matching - same type, similar duration, similar distance - was being
  used as a proxy for identity when `start_time` was absent. For repeated
  activities it is a proxy for ROUTINE instead: a dog walked three times a
  day, a commute each way, sets of the same length. Anyone with a habit
  generates near-identical shapes by design, and the resolver was merging
  them. A real record reported **1.39 km** of walking on a day when **6.26 km
  across four walks** had happened, and nothing surfaced it.

  This is the mirror of double-counting and worse: double-counting inflates a
  number visibly, a false merge silently deletes data and leaves a plausible
  canonical row behind. Three changes:
  - A shape match now also requires **disjoint sources**. A genuine
    cross-platform duplicate has a signature shape does not carry - two
    different systems claiming one physical event. Two claims from the same
    source with the same shape are far more likely to be two real events, and
    an identical re-emission from one connector is a connector bug that
    exact-duplicate detection (G26) already covers.
  - More than two shape-alike, timestamp-less claims of one type on a date is
    a **routine, not a duplicate set** - none are merged.
  - Every shape-only merge, every near miss, and every routine left unmerged
    now emits a **visible tripwire** saying what was decided and that
    recording `start_time` resolves it positively. Previously a merge was
    invisible outside the `claims` table.

  `_same_activity` returns three outcomes rather than two -
  `match | possible | distinct` - so an uncertain pair is a refusal to decide
  rather than a weak merge.
- **RED-S no longer requires the scale to move.** The composite demanded a
  deficit AND rate of loss AND load, all three. That reasoning holds for a
  losing athlete and is wrong for the syndrome: RED-S very commonly presents
  WEIGHT-STABLE, because the body downregulates instead of shedding - resting
  heart rate drifts, periods stop, resting metabolic rate falls. Requiring
  loss made weight stability *exonerating*, when in this syndrome stability is
  frequently the finding itself. Rate of loss is now sufficient but not
  necessary: low **energy availability** + training load + any ONE
  corroborating marker (fast loss, sustained resting-HR drift, menstrual
  function reported absent, bone-stress history) fires.
- **Energy availability is computed properly** - (intake - exercise energy) /
  fat-free mass - which is the measure the syndrome is actually defined by and
  needs no weight trend at all. It is never estimated: with no body-composition
  read the metric is not produced, because a guessed body-fat percentage is a
  manufactured input to a clinical decision.

### Added
- **The prose safety net (G59).** The escalation path only worked for athletes
  who file structured entries. Five exertional chest-pain episodes of
  increasing duration went unseen because every one was written into a
  free-text note and downplayed - which is how frightened people report
  things. A deterministic phrase scan over notes now escalates red-flag
  language wherever it was actually written. It is a net, not a parser: it can
  only ADD an escalation, and it is negation-guarded so "no chest pain" does
  not cry wolf.
- **Absolute intake and protein floors (G68)**, firing with no configuration
  at all - the same pattern as the absolute resting-HR band. The athlete who
  exposed this had configured nothing, as every new user has not, and got
  `tripwires: none` while eating ~1200 kcal a day and losing a kilo a week.
- **The clinical hold tier (G73).** A hold is not a louder message, it is a
  different act: it routes through the gate mechanism, so algorithmic
  progression suspends and the coach is structurally unable to issue training
  advice. Printing a warning and then carrying on prescribing was the failure
  it exists to prevent.
- **Physiological states and medications as modifiers (G57/G72).**
  `medical.jsonl` gains `kind: state` and an `expects` field. A declared state
  (nursing, pregnancy) RAISES the intake floor; a medication that expects
  rapid loss suppresses the rate verdict, which would otherwise tell someone
  whose treatment is working that she is failing a target nobody set for her.
  A modifier may raise a floor or drop a misfiring verdict - it can never
  silence an absolute floor.
- Safety findings now also surface as **verdict rows** (`intake_floor`,
  `protein_floor`, `energy_availability`, `symptom_chest_pain`,
  `symptom_syncope`), because a finding that only exists in a channel nobody
  renders is a finding nobody sees.

### Changed
- **`status` no longer leads with weight** (G62/G64). Weight-first was
  architectural rather than chosen, and it meant an athlete who had explicitly
  refused a weight goal opened every session being told she had failed to
  weigh herself. It now reports what is in the record - steps, or days logged.
- **The rollup gained a Steps section** (G64): fourteen days of phone step
  data, the only real data one athlete's life produces, rendered nowhere.
- **The rate line states its direction in words** (G69). It rendered
  `+1.10 kg/week` to an athlete who had LOST 1.5 kg, because positive means
  losing. For a scale-anxious under-eater that misreading is actively
  dangerous, so it now reads "losing 1.10 kg/week" and the sign is a detail.

## [Unreleased] - increment 3