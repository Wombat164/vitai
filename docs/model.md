# The vitai model (canonical consolidation)

The design grew to 23 gaps and 185 questions across `the-loop.md`. This is the
reconsolidation: the small set of PRINCIPLES those gaps are all instances of,
the ARTIFACT KINDS the system is built from, and a restated gap map (original
+ ten consolidating gaps G24-G33 from the 2026-07-28 whole-model redteam).
Read this first; `the-loop.md` is the exhaustive question bank, this is the
spine.

## Part 1 - Eight core principles

Every gap is an instance of one of these. When a new requirement arrives, find
its principle before inventing a mechanism.

**P1. Claims become adjudicated truth.** The one recurring move at every
altitude: multi-source observations resolve to one canonical value by
precedence (G15); an anchor recalibrates a disagreeing estimate, never the
reverse (P6/G16); a vendor insight is a competing claim arbitrated by the
transparent SSoT, never summed (G23); a mined inference is a claim that must
survive an out-of-sample backtest before it graduates into a curated registry
(G17/G21/G22). Sources are claims; the engine adjudicates. **Symmetry the
redteam demanded (G24):** the source itself earns trust over time - a
chronically-wrong device loses precedence, the same anchor-audits pattern one
layer earlier.

**P2. Everything mutable is effective-dated; the record is a timeline.** No
current-state values. Goals, thresholds, calorie/macro targets, planned
sessions, forecast models - all dated, all reconstructable via `state(date)`,
never re-scoring history against a newer value. Change itself is a metric
(`plan_churn`), and edits are auditable dated events (anti-goalpost-moving).
**Symmetry the redteam demanded (G31):** this must reach the CURATED REGISTRIES
too (a revised "what a plateau means" must not silently re-interpret old diary
days) and streak definitions (still in mutable `vitai.toml` - the exact G14 bug
un-migrated).

**P3. Epistemic tiering; confidence never launders upward.** Three data tiers
(observed / derived / inferred), three quantity classes (anchor > measured-flow
> modeled-estimate, with vendor-insights and forecasts as never-an-anchor
estimate sub-classes), three cross-metric trust tiers (deterministic / hedged /
structurally-excluded). All one rule: a lower-trust claim may never present with
a higher tier's confidence. **Symmetry the redteam demanded (G27):** the
DETERMINISTIC engine also owes doubt - a thin-sample verdict must carry a
maturity signal (cold/warming/stable), not look as certain as a year of data.

**P4. The deterministic number-path firewall.** The LLM never computes a
rolling average, a verdict, a forecast, or a correlation p-value; it proposes
and explains. Graduation from LLM-proposed to trusted requires an out-of-sample
backtest or human merge, never model say-so. **The redteam's hardest finding
(G28):** the one decision currently OUTSIDE this firewall is the highest-stakes
one - "see a clinician" lives as LLM prose in CLAUDE.md. Safety escalation must
be a deterministic tripwire-severity-to-action mapping like every other number.

**P5. The curated registry is a third artifact class (neither data nor code).**
`semantics/` (meaning) and `models/` (forecast formulas) are versioned,
evidence-tagged, human-mergeable knowledge stores. Verdicts/tripwires/forecasts
reference them as their activated subset; inference extends but never reinvents
them. **Symmetry the redteam demanded (G31):** registries need the same
continuous audit the model registry has (a semantics entry that stops matching
reality must be flaggable/retirable), and the same as-of dating as P2.

**P6. Anchors audit estimates; trends are the measurement; late truth reweights
everything downstream.** Body mass/measurements/labs are ground truth that
recalibrates estimates when they diverge; weight enters only as a trend, never
a single morning. **Generalized by the redteam (G29):** a corrected or
late-arriving anchor must retroactively reweight EVERY downstream trust score -
forecast backtests, milestone validity, streak state - not just the energy
audit. "Late truth cascades" is one doctrine, currently implemented once.

**P7. Voice/coaching ethical invariants.** Never punish, never shame, never
moralise; no single-incident causal narration; forgiveness before streaks; past
achievement judged against its own standard, never retro-diminished; hedge
ceiling ("for you, so far"). One motivational contract across streaks, goals,
cross-metric inference. **Explicit carve-out the redteam demanded:** the
safety-escalation tier (G28) is the ONE deliberate exception - a red-flag fires
loud; that exception is written down, not an accident.

**P9. CLI and API are one surface; expose (read) first, then write-parity.**
Every capability ships as BOTH a CLI command and a library/API method - the
CLI is a thin harness over the same `vitai.api` the platform consumes, never a
separate code path. Read/query exposure comes first (a game/dashboard/agent
can observe everything the CLI can); WRITE/manipulation API follows, reaching
full parity with the CLI so a consumer can eventually do through the API
everything the CLI does (append a correction, declare a goal, trigger a
build), not just read. This is why `Vitai(root)` already mirrors
`build/verdicts/status`, and why every new verb (`explain`, `goals`,
correction) lands as CLI + API together. The CLI is the reference harness; the
API is the contract. (Golden operator principle, 2026-07-28.)

**P8. Capture-cost economy bounds schema growth; genericity + per-user atom.**
The ~3-minute weekly budget is the immune system - nullable/additive fields,
screenshot-inferable, at-most-one-question-a-week; the minimum day is one
number. (Scoped to daily/weekly cadence, NOT to occasional coach-assisted goal
authoring.) And the whole engine is domain-agnostic (the goal/contribution/
motivator model serves a language streak as well as a run), with multi-user as
horizontal per-user-store replication, never a shared schema or cross-user
join.

## Part 2 - Artifact kinds

The system is built from exactly five kinds of thing. Every feature is one of
these; nothing else exists.

1. **Observation datasets** (`data/*.jsonl`) - append-only claims tagged with
   `source`, per-line schema generation (G25), timezone-aware dates (G30).
   weight/daily/sessions/measurements/goals/medical/journal/achievements/
   thresholds/inferences.
2. **Deterministic derivations** (`derived/`, rebuilt from zero) - resolution
   -> canonical values -> verdicts/baselines/features/streaks/contributions/
   milestones/forecasts/energy_audit/plan_churn/source_reliability. The read
   model (`health.db`) is the versioned platform contract.
3. **Curated registries** (`semantics/`, `models/`) - versioned human-mergeable
   knowledge; the activated subset drives verdicts/tripwires/forecasts.
4. **Skills** (`skills/*/SKILL.md`) - the LLM layer: onboard/coach/ingest/
   redteam/schedule; propose + explain, never assert numbers or causes.
5. **Policy-as-data** - the prose-to-data discipline applied to everything
   safety/privacy-critical: consent ledger, access-scope, suppression prefs -
   NOT markdown pages (the redteam's "prose still hiding where data is needed").

## Part 3 - The ten consolidating gaps (G24-G33)

Each folds several redteam findings and fills a symmetry hole in a principle.

- **G24 Source-reliability learning** (P1). Observation sources earn/lose trust
  by backtest against anchors, not a static onboarding rank. The
  anchor-audits-source loop. HIGH.
- **G25 Schema-evolution robustness** (P8/artifact-1). CODE-VERIFIED CRITICAL:
  additive nullable fields currently break validation of every pre-existing
  line (validate re-checks all history against the current schema). Needs a
  per-line schema-generation marker + a "key postdates this line" validator
  rule, plus a history-stability regression test for schema shape. Blocks
  increment 1 on day one. CRITICAL, foundations.
- **G26 Ingestion/build integrity** (P1 at the syntactic layer). Parse
  fault-tolerance (quarantine one bad line, keep building - today one bad byte
  `sys.exit`s the whole build); exact-duplicate detection; connector idempotency
  via per-line identity (the Q127 same-source-revision gap); cross-platform +
  hash-seed float/iteration determinism; `.gitattributes` LF policy. HIGH,
  foundations.
- **G27 Cold-start & maturity** (P3). A minimum-N per derivation; a
  cold/warming/stable maturity signal surfaced to the coach and carried in the
  shape grammar; a deterministic-engine confidence signal for thin samples; and
  the calendar-day-vs-entry-count window fix (a "7d avg" must mean 7 calendar
  days, not 7 entries spanning three weeks). HIGH, foundations + increment 4.
- **G28 Safety escalation** (P4/P7). Deterministic severity->action: a symptom
  class beyond musculoskeletal (cardiac/chest-pain red flags), absolute-danger
  thresholds (not only relative-to-baseline RHR), a RED-S/low-energy-
  availability composite detector (a tool that coaches deficits must watch for
  the syndrome it can cause), a fast-path that bypasses the weekly cadence, and
  the written never-shame carve-out. CRITICAL, into increment 3.
- **G29 Correction cascade & unified provenance** (P6). `vitai explain <metric>
  <date>` composing claims -> resolution decision -> derivation -> registry
  meaning -> verdict into one trace; a correction that retracts/annotates the
  milestones/streaks/inferences/backtests that already consumed the old value
  (G10 covered deletion, not correction); resolution-precedence decisions as a
  first-class routine explanation, not only a failure tripwire. HIGH.
- **G30 Temporal foundations** (P2/P1). **Rolling windows are calendar-day,
  not entry-count** (SHIPPED foundations F3: a "7d avg" means 7 real days -
  the entry-count bug that silently mis-scoped every trend under irregular
  logging is fixed). Day-boundary DOCTRINE (below); the timezone/offset FIELD
  rides with G4's `start_time` in increment 2 (a date-only daily summary has
  no timezone ambiguity - only an intraday timestamp does, so the field lands
  where it has a consumer). DST 23h/25h arithmetic with it. HIGH.

  **Day-boundary rule (doctrine, ready for increment 2):** an event's calendar
  day is its LOCAL day at the moment it happened (device-local time at the
  event), not the sync time or a fixed home zone - a workout finished 23:30 in
  one timezone belongs to that day even if synced after midnight elsewhere.
  Sleep spanning midnight is attributed to the wake day (matching device
  convention). The rule is itself effective-dated (P2): a permanent
  relocation changes the home zone from a date forward, and past days keep the
  zone that applied then. Until `start_time` + offset land, dates are treated
  as already-local (the current, now-explicit behavior).
- **G31 Registry & config effective-dating** (P2/P5). Registries get `state
  (date)` for meaning + an ongoing decay/audit; streak definitions migrate out
  of mutable `vitai.toml` into a dated dataset (into increment 1, the migration
  increment); thresholds get a correction-vs-change marker so typo-fixes don't
  pollute the plan_churn signal; the estimate-vs-estimate tie-break (no anchor
  present) resolves by backtested accuracy, not home-team "SSoT wins". MEDIUM.
- **G32 Access scope & consent-as-data** (P5/P8, hosted). Per-consumer
  redaction/ACL (a game sees verdicts; a coach portal sees +plan/sessions/goals;
  a clinician export sees +medical; journal is athlete-only) - `Vitai(root)`
  today gives every consumer everything. A consent ledger (effective-dated, per
  purpose, revocable) as data not prose; deletion-cascade widened to ALL
  derived/graduated artifacts and the host-ledger boundary; a documented stance
  on household/shared-device isolation and minors (Art. 8). MEDIUM->HIGH for any
  hosted deployment.
- **G34 Situational context & facilities** (P7/P8/P2). A dated `context.jsonl`
  (mode: vacation/work/conference/weekend/social/deadline/heatwave/travel;
  facilities: scale/gym/AC/routes; location). Three jobs: sets the baseline
  (mode-aware judging), EXPLAINS missingness (no scale -> the absent weigh-in
  is expected, not non-compliance - reassure, never shame), and CONSTRAINS
  the plan/scheduler (facilities + weather gate what the coach prescribes).
  Plus the coach behavior it enables: proactively EXPLAIN and COMFORT a
  scary-looking number (a big deficit, an app disagreement) unprompted -
  comfort is coaching. HIGH.
- **G35 Geodata & location-time provenance** (P1/G5/G32). Routes/GPS on
  sessions + a where-was-I-when signal from many sources (photo geodata,
  calendar events, Maps/Waze route history, chat mentions) feeding
  mode/facility/place inference. Coarse-by-default (place/route-slug, not raw
  traces - the G32 minimization line), finer opt-in; multi-source location is
  claims (P1); enrichment stored-at-ingest (G5). MEDIUM.
- **G33 Reflexivity & the subtractive primitive** (P7/P8). Add
  "coach-induced/intervention change" as a named confound class in G22's guards
  (the system must not measure its own nudge as a discovered trait); acknowledge
  capture-level observer effect (asking about alcohol changes alcohol logging);
  a per-metric suppression primitive ("leave this one alone" - subtractive
  symmetry to an additive-only design); and units as a storage-is-SI /
  display-converts-at-the-edge doctrine (units are baked into field names today).
  MEDIUM.

## Part 4 - Consolidations (merges, not new gaps)

- **G1 folds into G15**: "device disagreement, keep both, arbitration" IS the
  per-quantity precedence merge. Retire G1 as a distinct gap.
- **G2 is a projection of G17**: baselines (median bands, trends) should derive
  FROM the shape grammar's features, not compute in parallel - one source of
  truth for "what is normal". Decide at the increment-4 zoom-out.
- **G10 scope-widens, not a new gap**: the deletion cascade must enumerate all
  derived/graduated artifact classes + the host-ledger boundary (folded into
  G32).
- **P6 is one doctrine, not per-instance**: energy_audit (G16), forecast
  backtest (G21), and correction-reweights (G29) are the same "late truth
  cascades" rule - name it once, cite it everywhere.

## Changelog
- 2026-07-28: created. Reconsolidation of the whole model after the four-lens
  whole-model redteam; eight principles, five artifact kinds, ten consolidating
  gaps G24-G33, four merges.
