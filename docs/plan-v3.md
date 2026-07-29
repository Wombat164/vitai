# v3 build plan (restructured 2026-07-28)

Execution plan for the gap list in [the-loop.md](the-loop.md), organized by
the principles in [model.md](model.md). Written to hold two disciplines at
once: a structurally solid base (tests land, CI green, versioned contract)
AND frequent visible progress (every increment ships something demoable).
The failure mode this plan exists to prevent: spending four weekends on the
tool instead of the product.

**Restructure note (post whole-model redteam):** a FOUNDATIONS phase now
precedes the feature increments. The four-lens review found a code-verified
critical bug (G25: additive fields break validation of all existing lines)
and several robustness gaps (G26/G27/G30) that the feature increments
silently depend on - a feature built on those would need rework. Foundations
ships first, boring and invisible, so nothing later is built on sand. Safety
escalation (G28) is pulled into the medical increment as a schema+engine
change, not a doc. Cross-cutting concerns (G29 correction/explainability,
G24 source trust, G31-33) are slotted where they first become derivable.

## Working rules (the meta)

1. **One increment in flight.** No parallel half-built features. An
   increment is one squash-merged PR, tagged as a release when it changes
   behavior.
2. **Demo or it didn't happen.** The repo carries a synthetic demo athlete
   (`examples/demo/`, built in increment 0); every increment must change
   what the demo SHOWS, and CI proves the demo builds. "Something to show"
   is a gate, not a hope.
3. **Dogfood before tag.** The founding deployment (a real private content
   repo) migrates onto each increment before the release is cut. If
   migration hurts, the increment is wrong - fix it before anyone else
   feels it.
4. **Timebox + escape hatch.** Each increment lists what to CUT first if
   it overruns. The rule: if an increment exceeds two working sessions or
   grows beyond its NOT-list, stop, re-scope to the demo-able core, ship
   that, and move the remainder to the next increment. Zoom out
   deliberately (a birdseye pass) rather than grinding.
5. **Spikes are one hour.** Unknowns get a throwaway spike with a decision
   at the end, never open-ended exploration inside a feature branch.
6. **Tests land with the change; three standing invariants** get explicit
   regression tests from foundations onward:
   - determinism: two builds over the same inputs are byte-identical -
     AND (G26) stable across OS/Python (sorted iteration, a documented
     float-tolerance band for near-tied backtests, no hash-seed leakage);
   - value-history stability: editing a CURRENT threshold/goal never
     changes a PAST week's verdict (the G14/G20 regression);
   - shape-history stability (G25): adding a new nullable FIELD to a
     dataset never changes what a past line validates as.
7. **Contract discipline**: any read-model shape change bumps
   `meta.contract` and gets a line in the wiki platform page - same PR.
7b. **CLI + API parity (P9)**: every new capability lands as BOTH a CLI
   command and a `vitai.api` method in the same increment - the CLI is a
   harness over the API, never a separate path. Read exposure first; write/
   manipulation API follows to reach CLI parity. A verb shipped CLI-only is
   incomplete.
8. **CI stays fast.** The matrix + hygiene gates run on every push (they
   do today); the demo job is the only addition. Heavier future suites
   (property fuzzing) go behind `workflow_dispatch`, not on every PR.

## FOUNDATIONS (before any v3 feature)

Invisible robustness the feature increments depend on. Ships as its own
tagged release (v0.2.1) so the founding deployment sits on solid ground
before goals/context/medical land.

### F0 - the demo athlete (half a session)
- `examples/demo/`: a synthetic content repo (fictional athlete, ~8 weeks,
  a goal story with an edit, an injury-recovery arc), script-generated
  (`examples/generate_demo.py`) so it grows with the schema.
- CI `demo` job (renderfact pattern): build the demo, assert rollup +
  verdicts render with expected markers. README "See it" excerpt.

### F1 - schema-evolution robustness (G25) [CRITICAL, do first]
- Per-line schema generation: an optional `_gen` marker (or a validator
  rule keyed off which fields existed at write time) so an additive
  nullable field NEVER invalidates a line written before it existed.
- `validate_record` distinguishes "key postdates this line's generation"
  (fine) from "key missing and should exist" (error).
- The shape-history-stability regression test (working rule 6).
- Without this, increment 1's first field addition breaks `vitai build`
  on the dogfood repo. This is the unblock.

### F2 - ingestion/build integrity (G26)
- Parse fault-tolerance: quarantine a malformed line with a warning, keep
  building from the rest (today one bad byte `sys.exit`s the whole build).
- Exact-duplicate-append detection (same date+source+value, no supersedes)
  surfaced, not silently deduped.
- Per-line identity / generation id so a connector can revise its own
  earlier same-day line (the live Q127 gap) and a resynced-twice pull is
  idempotent.
- Determinism hardening: sort all set/dict iteration; `.gitattributes`
  `*.jsonl text eol=lf` in the template; a cross-OS build fixture.

### F3 - temporal foundations (G30)
- Timezone/offset field on `date` and (G4's future) `start_time`; an
  explicit, documented, tested day-boundary rule (home-tz vs device-tz at
  event); DST 23h/25h arithmetic.
- Calendar-day vs entry-count window semantics (G27, part): a "7d avg"
  means 7 calendar days, not 7 entries - fix `_rolling`/rate now, before
  the shape grammar (increment 4) hard-references these window names.

Foundations cut-first: the README excerpt, exact-duplicate detection (F2),
DST edge (defer the 23/25h case, keep the tz field). NOT cuttable: F1
(the plan can't proceed without it) and the calendar-window fix.

## Increment 1 - goals are data + contribution + temporal validity (v0.3.0; G6 + G14 + G18 + G19 + G20) [2-3 sessions]

The core promise: "did today serve a goal, when was it set, when edited" -
one event feeds many goals with different signs, goals are rich and
abstract, and the plan is a TIMELINE (every past day judged against the
targets in force then, changes are auditable dated events).

- `goals.jsonl` (contribution policy: monotonic vs guarded; G19 fields:
  `external` metric + `tracker`, reinforced `motivator`, `period` +
  `on_period_end`, `rationale`, `on_success`/`on_miss`),
  `achievements.jsonl` (with an authorship/source field, G31 finding),
  `thresholds.jsonl` (+ a correction-vs-change marker, G31) - AND streak
  definitions migrated out of mutable vitai.toml into a dated dataset here
  (G31: same G14 bug, same migration increment, so streaks in increment 4
  are built on dated config not current-state); schemas, validation,
  templates; slug-scoped supersedes resolution in the loader.
- Engine: `contributions` derivation (per event x goal signed verdict);
  `milestones` derivation (thresholds crossed, only on in-policy progress);
  verdicts gain goal linkage; **as-of reconstruction `state(date)`** so
  every judgment (and the lens diary) uses the policy in force THEN;
  calorie target + macros move into `thresholds.jsonl` (retired from
  vitai.toml); `plan_churn` change-metric + suspiciously-timed-edit flag
  (G20); contract bump to 2.
- CLI: `vitai goals` - active goals with progress %, declared/last-edited
  dates, deadline pace, and each recent event's per-goal contribution.
- Skills: onboard writes goals with contribution policies, motivators,
  periods and rationale (incl. external/non-fitness goals); coach judges
  each event per goal, never celebrates a guardrail-violating milestone,
  and gains the proactive motivator-anchored check-in ("6th of 8 gym
  visits - tonight?"; "Local Legend attempt - trying again?").
- Tests: goal lifecycle; slug-head resolution; threshold history (G14
  regression); the contribution fan-out (one run: calorie-goal +,
  running-goal 0/- under the ramp guard); milestone fires on genuine
  progress, NOT on over-target guarded volume; **as-of reconstruction (a
  past day judged against then-targets is unchanged by editing today's;
  `state(date)` returns the right in-force values); churn/suspicious-edit
  flag fires on a right-after-a-miss loosening** (G20); progress math;
  contract.
- Demo: the demo athlete has a steps goal (monotonic) and a running goal
  (guarded); a big unplanned run shows the split verdict and no milestone.
- NOT: multi-goal CONFLICT detection (inference's job), ambitions
  (increment 5), prescriptions-as-data, gamified rewards (host-side).
- Cut-first: `achievements.jsonl` hand-logging UX; deadline-pace
  projection. NOT cuttable: the contribution model - it is the point.

## Increment 2 - provenance, context, feel + RESOLUTION (v0.4.0; G1, G3, G4, G7, G15) [2 sessions]

The whole-life differentiation plus the conservation golden rule: a
calorie is eaten once, burned once - multiple sources RESOLVE to one
canonical truth, never sum. Promoted into this increment because the
founding deployment already has two sources claiming the same dates.

- `daily`: `source`, `mood`, `feel`, `coverage`; `pain` + `pain_site`
  generalization with `hip_pain` read-compat (old lines keep validating;
  the engine maps them; migration note in CHANGELOG).
- `sessions`: `source`, `start_time`, `elevation_m`, `setting`, `route`,
  `place` (supersedes free-text `location`), `with` (comma slugs),
  `context`, `planned`, `weather`.
- `measurements.jsonl` (G16): sparse anchor-class dataset (body fat %,
  circumferences) - additive, rides this schema pass; anchors top the
  resolution precedence ladder.
- `suppressed_metrics` profile field (G33: "leave this one alone" - the
  subtractive primitive) alongside G7's `nudge_ok`; storage-is-SI /
  display-converts-at-edge becomes written doctrine (G33 units).
- `context.jsonl` (G34): dated situational mode (vacation/work/conference/
  weekend/social/deadline/heatwave/travel) + facilities (scale/gym/AC/
  routes) + location. Engine: mode-aware baseline; missingness EXPLAINED by
  context (an absent weigh-in under no-scale is not flagged); coach reads it
  to constrain prescriptions and to proactively explain/comfort. Effective-
  dated (P2).
- Ingest skill: extracts the new fields when visible, never nags;
  validator messages stay actionable.
- **Resolution layer (G15)**: field-wise per-quantity precedence merge of
  same-date claims into one canonical row; fuzzy session
  overlap-matching (time-intersect via `start_time` + its tz offset from
  F3, else type+duration/distance tolerance bands); energy-as-attribution
  rule; conservation tripwires (sessions exceeding daily burn, near-miss
  duplicates, device disagreement). Canonical rows feed everything
  downstream; claims projected to `*_claims` tables. Retires the
  connector-politeness era (skip-existing), unblocks the MFP kcal_in
  merge. **Resolution-precedence decisions are exposed as routine
  explanations (G29)** - which day/source won and why - not only as a
  failure tripwire.
- Tests: nullability of every new field, pain migration, mixed old/new
  lines in one file; resolution: two-source day merges field-wise, same
  run via two platforms collapses to one, sessions-exceed-day fires the
  tripwire, single-source behavior byte-identical to v0.3.0 (regression).
- Demo: one richly-contextful demo day (partner walk, rain, known route,
  good mood) AND a two-source day resolving cleanly in the rollup.
- NOT: any new derivation over the new fields yet; no enrichment fetching.
- Cut-first: `weather` + `route` (pure context); keep `mood`/`feel` and
  the resolution core (the golden rule is not cuttable).

## Increment 3 - medical layer + SAFETY ESCALATION (v0.5.0; G11 + G28) [2 sessions]

Lands BEFORE streaks because forgiveness is computed from it. Now also
carries the highest-stakes redteam finding: safety escalation must be a
DETERMINISTIC tripwire, not LLM prose.

- `medical.jsonl`: episode lifecycle (slug, onset `date`, `resolved_date`,
  status), restriction gates (`restricts`), coarse provider types, and a
  `severity` field the ENGINE reads (not just the LLM).
- **Safety escalation (G28)**: a symptom CLASS beyond musculoskeletal
  (cardiac/chest-pain and other red flags), ABSOLUTE-danger thresholds
  (RHR outside a physiological range, not only baseline+5), a RED-S /
  low-energy-availability composite detector over deficit + rate-of-loss +
  load (the syndrome this tool's own coaching can cause), a `severity=
  red_flag` engine branch that fires a hardcoded non-LLM message, and a
  FAST PATH (`vitai build --now` / an escalation surface) that bypasses the
  weekly cadence for a same-day dangerous entry.
- Voice: the written never-shame CARVE-OUT (P7) - the gate/red-flag tier is
  the one deliberate loud exception; documented, not accidental.
- Engine: active-episode windows; rollup gains a gates line; tripwires
  respect gates. Coach: gate rules become data-backed checks.
- Tests: episode window math; gate firing; supersedes within a slug; a
  chest-pain entry produces an URGENT message not a hip-substitution; an
  absolute-danger RHR fires without relative drift; RED-S composite fires
  on a deep-deficit + high-load synthetic; the fast path surfaces same-day.
- NOT: FHIR import, document attachments, medication interactions,
  diagnosis (route to clinician).
- Cut-first: lab/medication kinds; the RED-S composite (ship the red-flag
  branch + absolute thresholds + fast path first). NOT cuttable: the
  deterministic severity->action mapping - that is the point of G28.

## Increment 4 - baselines, shape grammar + streaks (v0.6.0; G2, G8, G17) [2-3 sessions]

The comparison engine and the flagship demo.

- `features` derivation (G17): the uniform shape grammar over all
  canonical metrics (slope, acceleration, extrema + prominence, plateaus,
  variance, band position, registered lagged pairs) - one extractor, every
  metric, every CALENDAR window (F3 semantics). **`baselines` becomes a
  PROJECTION of features** (median band = a feature, trend slope = a
  feature), resolving the G2/G17 redundancy (one source of truth for "what
  is normal") - the increment-4 zoom-out decision, made.
- **Maturity signal (G27)**: a per-metric cold/warming/stable state driven
  by a declared minimum-N per derivation type, carried as one more uniform
  attribute in the shape grammar and surfaced to the coach - a 3-day-old
  user's number never looks as certain as a year's. The
  deterministic-engine's own confidence/doubt signal (P3 symmetry).
- `source_reliability` derivation (G24): each source's estimates backtested
  against landed anchors; chronically-wrong sources lose resolution
  precedence over time (anchor-audits-source, the P1 symmetry fill). Feeds
  back into increment-2's resolution ranking.
- `semantics/` registry seeded (G17), now with as-of dating + a decay/audit
  check (G31: a meaning that stops matching reality is flaggable, like a
  forecast model - registries obey P2/P5, not frozen).
- streaks derivation moves to increment-4 scope note below.
- Coach + infer skills updated to consume the registry (quote, extend,
  never reinvent) and to speak maturity ("still learning your baseline").
- `streaks` derivation: definitions in config, weekly-first vocabulary,
  forgiveness computed from medical episodes + goal `rest_days`; current/
  best/at-risk.
- `energy_audit` derivation (G16): weekly implied TDEE from canonical
  intake + weight TREND; divergence vs device/logged estimates surfaced
  as a calibration signal - the anchor audits the ledger.
- Rollup + `vitai status` surface both; contract bump.
- Tests: forgiveness (sick week keeps the streak - THE test of the
  increment), record detection, trend slopes on synthetic series,
  determinism invariant re-run over the full new surface.
- Demo: the flagship - a streak that survives the injury arc, a personal
  record firing.
- NOT: any reward/currency logic (game-side), notifications, charts.
- Cut-first: weekday profiles + monthly rollups (bands/records/streaks
  are the core).

## Increment 5 - journal + correction/explainability + policy-as-data (v0.7.0; G12, G13, G10, G9, G29, G32) [2 sessions]

- `journal.jsonl` (reflection | life_event | ambition | feedback, with an
  authorship/source field, G31); goals' `motivation` references ambitions.
- **Correction & explainability (G29)**: `vitai explain <metric> <date>`
  composing claims -> resolution decision -> derivation -> registry meaning
  -> verdict into one trace; an athlete-facing correction VERB (not raw
  supersedes-key editing); a correction CASCADE that retracts/annotates the
  milestones/streaks/inferences/forecast-backtests that already consumed a
  since-corrected value (the P6 "late truth cascades" doctrine, named once,
  applied here + in forecasting).
- **Access scope + consent-as-data (G32)**: per-consumer read scope on the
  platform surface (game=verdicts; coach=+plan/sessions/goals;
  clinician-export=+medical; journal=athlete-only by default) - not full
  `Vitai(root)` for everyone; a consent ledger dataset (effective-dated,
  per purpose, revocable); G10's deletion cascade rewritten to enumerate
  ALL derived/graduated artifacts + the host-ledger invalidation boundary;
  a documented STANCE on household/shared-device isolation and minors
  (Art. 8) even if "v1 = separate adult devices".
- `PRIVACY.md` (household exemption, hosted DPIA, single-line-erasure
  limitation, retention tiers, coarseness) + `docs/game-boundary.md`.
- Tests: journal schema; explain-trace correctness; a corrected day
  retracts its milestone; access scope denies a game the journal; consent
  revocation is dated and honored.
- Demo: a life-event line explaining a quiet fortnight; a corrected day
  showing its retracted celebration.
- Cut-first: the consent ledger UX (ship the access-scope contract + the
  correction cascade first).

## Increment 6 - enrichment at ingest (v0.8.0; G5, G35) [1-2 sessions, optional]

- Doctrine + ingest-skill support for stored-at-ingest weather/calendar
  context; no engine changes (fields landed in increment 2).
- Geodata & location-time (G35): routes/GPS on sessions (coarse route-slug
  by default, G32); a where-was-I-when signal from many sources (photo
  geodata, calendar, Maps/Waze route history, chat mentions) feeding
  mode/facility/place inference (which populates G34's context.jsonl);
  multi-source location as claims (P1). Privacy: coarse-by-default,
  finer opt-in.
- Explicitly the first thing to POSTPONE if real-world usage (dogfood or
  early adopters) surfaces better-informed priorities by then.

## Increment 7 - forecasting (v0.9.0; G21) [2-3 sessions]

The engine projects, not just describes. Depends on baselines + the shape
grammar (increment 4) and planned-inputs as data (planned sessions from
G6/increment 1, intake plan from the dated targets).

- `models/` registry seeded: weight (thermodynamic ~7700 kcal/kg,
  adaptive-TDEE, metabolic-adaptation), fitness (Banister CTL/ATL/TSB,
  load-to-pace) - each a documented scientific formula with parameters.
- `forecasts` derivation: enabled models + accuracy-weighted ensemble over
  planned inputs -> dated trajectories with prediction intervals (widening
  with horizon), model-provenanced.
- `backtest` derivation: each landed anchor scores prior predictions,
  reweights the ensemble, sets interval widths; divergence detection
  separates model-error from regime-change (plateau) and flags the latter
  via the shape registry. **A corrected anchor (supersedes) retroactively
  rescores the backtest** (G29/P6: late truth cascades - the ensemble
  never carries phantom confidence earned against data that no longer
  exists).
- `forecast(date)` as-of provenance; coach uses forecasts for "if you hold
  this plan, here's where you land (+/- band)" and explains divergences.
- Lens track L-forecast: fan-chart bands over the actual trajectory,
  per-model backtest-accuracy panel, "predicted-for-today-8-weeks-ago"
  overlay.
- Tests: interval widens with horizon; a landed anchor reweights the
  ensemble; a synthetic plateau (model accurate then flat) fires
  regime-change NOT model-error; forecasts never appear in any verdict
  row; deterministic (same inputs -> same forecast); as-of provenance
  correct.
- NOT: LLM-generated forecasts (formulas only); the LLM only explains and
  proposes-for-backtest.
- Cut-first: metabolic-adaptation and VO2max models (ship thermodynamic +
  adaptive-TDEE + Banister as the honest core); the accuracy panel.

## Increment 8 - cross-metric inference + vendor insights (v0.10.0; G22, G23) [2-3 sessions]

The engine relates metrics and ingests other apps' science - honestly.
Last, because it stands on features (4), forecasting (7), and resolution (2).

- Cross-metric correlation engine (G22): deterministic stats guards
  (detrend, effective-N, multiple-comparisons budget/FDR, a-priori lags,
  change-point segmentation, missingness policy, AND coach-induced/
  intervention confound - G33: the system must not measure its own nudge as
  a discovered trait) over metric pairs; the three-tier trust taxonomy in
  code (tier-1 deterministic registry entries; tier-2 hedged hypotheses;
  tier-3 single-incident narration structurally excluded). Seed the
  evidence base from docs/cross-metric-inference.md.
- Knowledge-extraction pipeline: `vitai infer` proposes patterns ->
  out-of-sample temporal backtest -> registry graduation (still hedged for
  confounded relationships).
- Vendor-insight ingestion (G23): foreign-model estimates tagged
  derived+source, wired as ensemble members (corroborate) / challenge
  signals / hedged backfill; conservation-resolved. **Estimate-vs-estimate
  tie-break (G31)**: when no anchor arbitrates, backtested accuracy decides,
  NOT home-team "SSoT wins" - that default was self-favoring.
- Coach: the causal-language firewall (enumerate co-factors, no single-day
  cause, "for you so far" ceiling, medical->clinician).
- Tests: a pair that vanishes after detrending is discarded; effective-N
  shrinks a naive p-value; the pattern budget caps nightly proposals; a
  single-incident causal claim is structurally impossible to emit; a
  vendor kcal is resolved as a competing claim, never summed; SSoT wins a
  vendor disagreement while logging it.
- NOT: any tier-2 pattern asserted as fact; medical inference; vendor
  scores trusted over the resolved SSoT.
- Cut-first: the adherence-context classifier (needs calendar enrichment,
  G5); ship sleep/HR-kcal/weight-pace handling first.

## Increment ordering note

Forecasting (7) is deliberately LAST of the CORE engine increments, and
cross-metric/vendor inference (8) sits after it: both stand on canonical
resolution (2/G15), baselines + shape features (4/G2+G17), dated targets +
planned inputs (1/G14+G20), and the anchor-audit pattern (G16). Do not pull
them forward - a forecaster or a correlation engine over unresolved,
feature-less, current-state data produces fiction with a confidence score.

## The lens track (parallel repo: vitai-lens)

The stats frontend lives in its own repo
([vitai-lens](https://github.com/Wombat164/vitai-lens)) and follows the
same increment discipline with its own numbering (L0 shipped: sql.js deck
with weight/weekly/heatmap/verdict views over the demo athlete; L1
drilldowns + filters; L2 cross-correlation explorer; L3 baselines/streaks/
inference panels; L4 goal views). Boundary rule: EXPLORATORY analytics
(correlation mining, ad-hoc slicing) belong in the lens; CANONICAL
derivations (verdicts, baselines, streaks) belong in the engine - if a
lens feature starts being treated as truth, it graduates into the engine
with tests. Lens increments consume engine releases, never pre-release
schemas; a contract bump is the synchronization point.

## Cadence and review

- Each increment: branch -> PR (template honesty section filled) -> CI
  green -> squash-merge -> dogfood migration -> tag + release notes ->
  wiki page touch. The machinery for all of this already exists; the plan
  just commits to using it every time.
- After increments 1 and 4 (the two structural ones): a deliberate
  zoom-out against the-loop's question bank - re-tag what moved from GAP
  to SHIPPED, and let the remaining tags re-rank the rest of the plan.
  The question bank is the acceptance test; the plan serves it, not the
  other way around.
- The loop for a personal deployment stays the boss: if the weekly
  check-in ever exceeds three minutes because of something this plan
  added, that addition reverts first.

## Changelog

- 2026-07-28: created.
