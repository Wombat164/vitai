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

## Part 3 - The consolidating gaps (G24-G89)

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
  > **SPECIALISED by #220 (state model), 2026-08-03.** Implemented, with live
  > rows, and retained. The general state shape specialises to this rather than
  > replacing it.
- **G35 Geodata & location-time provenance** (P1/G5/G32). Routes/GPS on
  sessions + a where-was-I-when signal from many sources (photo geodata,
  calendar events, Maps/Waze route history, chat mentions) feeding
  mode/facility/place inference. Coarse-by-default (place/route-slug, not raw
  traces - the G32 minimization line), finer opt-in; multi-source location is
  claims (P1); enrichment stored-at-ingest (G5). MEDIUM.
  - **Extraction is plumbing; INTERPRETATION is the capability, and it splits
    across three trust tiers that must not be conflated:**
  - *Tier 1 - route GEOMETRY (deterministic, P4 number path).* From a stored
    GPX/stream, derive facts that are TRUE by computation: origin->destination
    (reverse-geocoded to place slugs), shape class (out-and-back / loop /
    point-to-point via start-end proximity + self-intersection), laps (a
    sub-path repeated N times), distance, elevation gain, surface/segment
    splits, and "vs your usual" (shorter/longer/detour) by matching against
    your own history for that O-D pair. These are derivations, not opinions -
    they live in the report layer and never carry a confidence score.
  - *Tier 2 - the route REGISTRY (curated artifact, P5 + P2).* Recurring
    realizations cluster into named canonical routes ("gym commute", "Fort
    loop"), each a registry entity with a distribution of past traversals;
    the "normal route" for an O-D pair is its modal path. Effective-dated -
    routes change (construction, a move, a new shortcut), and a past walk is
    judged against the route library IN FORCE THEN.
  - *Tier 3 - PRESCRIPTIVE routing (external-model inference, never truth).*
    "Where could I add 100 m / a km", "route me away from busy streets",
    "quieter/greener next time" are MODEL outputs over external map data
    (OSM graph, road-class/traffic weights) - a G22/G23 vendor-model class.
    They are SUGGESTIONS carried in the inference/proposals layer with
    provenance, NEVER in the deterministic number path, and always anchored on
    a goal (hit a step/distance target) + a stated preference (quiet / green /
    safe / avoid-crossings, held in the profile registry). This is where the
    coach's proactive, goal-anchored nudge lands ("your usual gym walk is
    1.4 km; the moat loop is 2.4 on a quieter path - want it today?").
  - *The G5 tension, resolved:* route geometry + its derived facts are
    stored-at-ingest (deterministic rebuild holds); prescriptive suggestions
    are model calls against live external data and are therefore NON-
    deterministic proposals (inference dataset), not derived truth - which is
    exactly why they sit in a different tier. *The G32 tension, named:*
    "avoid busy streets" implies pulling map/road data around your home and
    routine locations - the most sensitive geodata of all - so this tier is
    strict opt-in, coarse-area by default, and the routing runs on-boundary
    (local), not by shipping your home coordinates to a third party.
- **G33 Reflexivity & the subtractive primitive** (P7/P8). Add
  "coach-induced/intervention change" as a named confound class in G22's guards
  (the system must not measure its own nudge as a discovered trait); acknowledge
  capture-level observer effect (asking about alcohol changes alcohol logging);
  a per-metric suppression primitive ("leave this one alone" - subtractive
  symmetry to an additive-only design); and units as a storage-is-SI /
  display-converts-at-the-edge doctrine (units are baked into field names today).
  MEDIUM.
- **G36 Composition-resolved weight & the partitioning model** (P1/P3/P4).
  Scale weight is a LOSSY proxy for the goal-relevant quantity (fat), and it
  cannot by itself distinguish fat loss from recomposition. The design:
  - *Observed atoms* are `kg` + `body_fat_pct` (each with a G37 band). Fat mass
    and fat-free mass are DERIVED (weight x bf%, and the complement), never
    stored - the decomposition is rebuildable, so it lives in the report layer,
    not the ground-truth log (P4 firewall).
  - *The trustworthy signal is the fat-mass trajectory over WEEKS, not the daily
    scale or the daily bf%.* Bioimpedance FFM is hydration-noisy day to day (a
    real series can swing ~1 kg of "FFM" within a week - water, not muscle), so
    short-term FFM change is structurally excluded from any muscle claim; only
    the multi-week smoothed slope is read.
  - *The prediction is a PARTITIONING (p-ratio) forecast, not a scale forecast.*
    Energy balance predicts total tissue energy; a fat-partition fraction splits
    it into a fat-mass trajectory and a lean-mass trajectory, each with an error
    band; the scale-weight forecast is their SUM and is explicitly the least
    informative view. The partition fraction is CALIBRATED from the athlete's own
    weeks-smoothed bf%-x-weight history (the anchor-audit loop, G24/P6); when
    history is thin it falls back to a physiological prior from starting body-fat
    %, training status, protein adequacy and deficit size (a Forbes/Hall-class
    prior). A hand-built cut spreadsheet's fixed "0.5 kg muscle/month" assumption
    is the naive, un-calibrated version of exactly this - our model learns the
    number instead of assuming it.
  - *Recomposition detector.* A deterministic signal fires when the weeks-smoothed
    fat trend is falling AND the weeks-smoothed FFM trend is flat-or-up: the
    athlete is recomposing (best case), and the scale being flat is the SIGNATURE,
    not a stall. When there is no composition read at all, the engine raises a
    "measurement-limited: recomposition invisible to the scale" flag and offers a
    Tier-2 proxy read (progressive overload in the strength log + protein adequacy
    + circumference/photo trend -> "likely recomposition, not confirmed", low
    confidence, never a kg-of-muscle number).
  - *Personal kcal-per-kg is calibrated, not textbook - and the DENOMINATOR must
    be named.* Two different ratios get conflated and must not be: (a)
    physiological tissue-energy per SCALE-kg (~6,000-6,500 for a well-run cut,
    since a scale-kg is a fat+lean+water blend, each cheaper than pure fat); and
    (b) TRACKED-deficit per FAT-kg, which routinely lands well above the 7,700
    textbook (5-figure numbers appear). Ratio (b) is NOT a physiology finding -
    a kg of fat is ~7,700 kcal, full stop. Its excess over 7,700 measures
    TRACKING OPTIMISM: logged expenditure too high (generous TDEE/RMR-by-mode,
    no metabolic-adaptation discount) plus logged intake too low (universal
    food under-logging). The excess IS the calibration: tracked-deficit x
    (7700 / observed-kcal-per-fat-kg) recovers the real deficit (a ~0.7x
    correction is typical), and this is exactly what the adaptive-TDEE +
    anchor-audits-source loop (increment 7 / G24) learns from history rather
    than making the athlete find by hand. A naive
    cumulative-deficit-vs-scale-weight number is separately nonsense when a
    holiday plateau corrupts scale weight while the deficit keeps booking. HIGH.
- **G37 Measurement-uncertainty intervals on observations** (P3/P1). An observed
  reading carries an instrument band (`kg_lo`/`kg_hi`, `body_fat_lo`/`body_fat_hi`)
  distinct from a forecast error band; a wide band (bioimpedance, a jittery scale)
  downgrades trust in that reading without discarding it, and band ordering
  (lo<=point<=hi) is validated at ingest. Epistemic tiering (P3) now spans
  observations, not only inferences. MEDIUM.
- **G38 Context & data-quality inferred from record shape** (G34/G26/P1). Mode
  (G34) and tracking-lapse (G26) can be READ OFF the record when undeclared:
  `intake==expenditure` exact ties for N days = a placeholder fill, not
  measurement; an overnight >1 kg jump = water/glycogen (a feast), not fat; a
  weight plateau while a deficit is still booked = the cut paused. The engine
  flags the low-trust window and PROPOSES a mode; the athlete confirms. Inference,
  never a silent overwrite (P1). MEDIUM.
- **G39 Event -> tiered question loop (the ask/infer/answer engine)** (P3/P7/P8).
  Grounded in prior art (see [prior-art-world-model.md](prior-art-world-model.md)
  s4). One event (a walk) posts to a **blackboard**; independent knowledge sources
  (GPS parser, weight-log, calendar, weather) opportunistically fill a **slot
  schema** (who/what/where/purchase/mood/...), each slot carrying a **fill-source
  tag** - `auto-filled | inferred-hedge | must-ask | skipped` - which IS the
  answerability tiering ("some claims automatically answerable, some only the
  athlete can answer"). What to ASK: rank unfilled slots by
  `info-gain x downstream-coaching-value / capture-cost` (active learning /
  Horvitz mixed-initiative) and keep only the top 1-2. WHEN to ask: a JITAI
  decision point under a hard EMA-style budget, mandatory skip/defer, **no
  same-day re-ask** - the operational form of "never nag" (P8's 3-minute budget).
  A skipped slot is data too (an answered-absence, not a hole). Auto-derivable
  facts are stated; inferences are hedged; only the genuinely user-only slots
  (with-a-kid, bought-something, why-you-stopped) are ever surfaced as a
  question. HIGH.
- **G40 Semantic-trajectory layer (GPS -> narrative, deterministic-first)**
  (P4/P1/G35). The concrete build of G35 tiers 1-2, grounded in the semantic-
  trajectory field (prior-art s5). The atomic unit is a **STOP** (stayed > R
  metres for > T seconds) or a **MOVE** (transit), detected by a CB-SMoT-style
  deterministic pass (speed/radius/time) - cheap, explainable, per-user tunable,
  no ML; POSMIT-style stop-*probability* is a later confidence layer for noisy
  urban GPX. Mode by speed band (walk<7 / run 7-15 / bike 15-25 / car>25 km/h)
  before any classifier. Enrichment is two-stage: segment into stops, THEN a
  POI-category->activity lookup + time-of-day prior, with the LLM only as a
  fallback disambiguator for the ambiguous residual. **Privacy is a pipeline
  property**: on-device reverse-geocode against a locally cached POI tile so no
  raw coordinate crosses a network boundary; if a cloud lookup is unavoidable,
  coarsen to a 100-300 m cell (geo-indistinguishability) first - the concrete
  form of G35 tier-3's opt-in/on-boundary rule. NB the live walk analysis already
  ran the crude version and its best find was an ABSENCE - the untracked 8-min gap
  between two point-to-point walks was the real stop; gaps are first-class events.
  MEDIUM.

- **G41 Data lifecycle: lossless cold-store + progressive warm rollup**
  (P4/P3/P2/P5). As the record grows, age it - but the naive "downsample old
  data" breaks determinism and correctability, so the ladder splits in two:
  - *Raw is sacrosanct.* Data older than a threshold moves to high-ratio
    LOSSLESS cold-store (columnar + zstd, or Gorilla-style delta-of-delta for
    regular samples), NEVER lossily reduced or deleted - the deterministic
    rebuild (P4) and late-correction cascade (G29) both need the complete
    source. Any period rehydrates and rebuilds bit-identical.
  - *The warm read model carries a per-metric, effective-dated retention/rollup
    LADDER* (the registry, P5/P2): e.g. 14d full / 1mo 3/4 / 6mo 1/2 / 1y 1/4 /
    2y 1/8 / 10y 1/20 - but PER METRIC by value-density, not global. Continuous
    HR (~13 s samples) decays to near-worthless in days; a weigh-in anchor is
    valuable forever; and old GEODATA's warm form is its G40 semantic-trajectory
    summary ("Fort loop, 1.5 km, one 8-min stop"), the raw 800-point trace going
    cold. Rollups are DERIVED, provenance-tiered (P3), rebuildable, reversible.
  - *Coarse old data confesses it (G27).* A query over a 1/20-fidelity period
    returns values tagged with their tier; the coach says "roughly ~72 kg that
    quarter", never a false-precise number.
  - Prior art: RRDtool round-robin archives, Graphite/Whisper retention schemas,
    Prometheus/Thanos + TimescaleDB downsampling/continuous-aggregates, Facebook
    Gorilla. The ADAPTATION: those DELETE fine data (disposable observability);
    a personal life-record cold-stores it losslessly instead. It is memory
    consolidation - episodic detail -> semantic gist, ACT-R activation decay -
    made deterministic and reversible. DEFERRED until data actually grows. MEDIUM.
- **G42 Moment-relative context assembly (the coach's working set)**
  (P4/P8/P3). The coach/agent has a BOUNDED attention; it must load the minimum
  SUFFICIENT slice of the world model at moment T, never all of it. Assembly =
  a compact always-on STATE SUMMARY (active goals, current phase, recent trend,
  live tripwires - the `MEMORY.md`-index analogue) + full RECENT detail + any
  old period the CURRENT QUERY makes relevant, PAGED IN from cold and rehydrated
  to higher fidelity on demand ("compare to my last cut" pulls a 2y-old block
  back to full detail though it sits at 1/8 by default). Recency + relevance +
  the question drive the working set; the G41 ladder is only the DEFAULT.
  Firewall: assembly feeds NARRATION only - the deterministic number-path
  computes over full raw + rollups, never over the truncated window, so the coach
  never derives a number from what happens to be in context (P4). P8's
  capture-cost economy extends to a CONTEXT-cost economy: minimum sufficient, not
  maximum available. Prior art: MemGPT / Letta (virtual context management,
  paging main-context <-> external memory over unbounded data); ACT-R activation-
  boosted retrieval; the operator's own `MEMORY.md` discipline (bounded index +
  relevance-paged topic files) is this pattern already in production. Couples
  tightly to G41 (the rollups ARE the default warm context; cold-store is what
  pages back in). DEFERRED with G41. MEDIUM.

- **G43 Conversational capture -> typed claims** (P1/G39/P4). The world model
  GROWS from what the athlete says. A chat statement ("I like running to Zwin",
  "we're in Knokke till Sunday", "Meerminlaan 30 is the flat") is parsed by the
  LLM into a PROPOSED typed claim, filed to the right dataset (context / goals /
  preferences / places), effective-dated, `provenance=stated-in-chat`, confidence
  per how explicit it was. The athlete CONFIRMS (or it lands low-trust, pending);
  never silently written. This is the G39 loop run in REVERSE - the app extracts
  structure and confirms, instead of asking. Firewall: the LLM proposes
  STRUCTURE, never computes a number; an extraction is a claim, adjudicated like
  any other (P1). This is literally how the cold-boot scenario's facts got into
  the model. HIGH.
- **G44 Places, routes & multi-modal journeys** (extends G40). Named PLACE
  entities (home-base, a destination reserve, a trailhead) with coarse coords
  (G32). ROUTES between places are first-class and SOURCED: the athlete's OWN
  history (Strava/Polar GPX -> the registry) is deterministic/high-trust with
  real distance/elevation/typical-time; an external-routed path (OSM) is
  inference-tier. Route MATCHING + ADAPTATION - "an exact home->Zwin route? a
  near-match to adapt? or route it fresh?" - the own-history one always wins.
  And JOURNEYS are composite/multi-modal: a transit leg (drive/bus, external
  schedule) + a ONE-WAY run leg, enabling further-out point-to-point runs ("bus
  east, run the 12 km home along the dike"); the planner sizes the run leg to the
  goal target. MEDIUM.
  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > places and journeys are entities that states attach to; a route is not a place. Do not re-derive this entry; extend #220.
- **G45 Plan <-> route <-> goal reconciliation** (P1 / increment-1). A scheduled
  session carries a TARGET (distance/duration/pace) from the coach's plan OR an
  external plan (Runna/imported). A candidate route carries ESTIMATED parameters
  (own-history or external routing). The app reconciles: does this route ACHIEVE
  the target? Match -> propose it; mismatch -> extend/shorten/pick another, and
  say why. Multiple plan sources (coach vs Runna) are themselves reconciled like
  any conserved claim - one canonical target, provenance kept, disagreement
  surfaced not summed. MEDIUM.
- **G46 Source router + gated live world-lookups** (extends G42; P4/G32). The
  operational answer to "what to query vs live-look-up, and when". Every fact the
  coach needs routes to a source-of-truth:
  - STORED (world-model DB: goals, mode, preferences, own routes, places) -> read.
  - DERIVED (route distance from a stored trajectory, time from distance x pace,
    today's deficit) -> compute in the engine.
  - LIVE-LOOKUP (weather / FIRE-risk, road/trail CLOSURES, transit schedules,
    novel routing) -> external, and only under three gates: CONSENT (granted
    source, G32), NECESSITY (looked up when a decision needs it, not speculatively
    on every boot), PRIVACY (on-boundary / coarsened).
  SAFETY overrides the capture budget: a fire advisory on a planned nature-reserve
  run, or a closure on the route, is surfaced PROACTIVELY even though it is a live
  lookup. On boot: read stored + granted-volatile only; DEFER routing / transit /
  fire lookups until the athlete engages the relevant decision. This is the
  machinery under the cold-boot greeting - the router is what lets the app "know
  on opening what to query and what to live look up (if allowed)". HIGH.

  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > a world state that is FORECASTABLE can gate a plan before the fact, and a safety rule overrides it. Do not re-derive this entry; extend #220.
- **G47 Blocking vs enriching questions (answer-gating)** (refines G39). G39
  ranks WHICH slots to ask; this decides WHEN. A slot whose value would CHANGE
  the recommendation is **BLOCKING** and must be resolved BEFORE the answer -
  either asked first, or handled by an explicit BRANCH ("if you have a step ->
  this circuit; if bare floor -> that one"). A slot that merely enriches is
  non-blocking and may trail or be dropped entirely. **Never produce a confident
  single recommendation resting on an unstated assumption about a blocking
  slot** - the failure mode is a plan that is quietly wrong plus a footnote
  asking the question that would have changed it. Prefer BRANCHING over asking
  when the branch is cheap (2-3 outcomes); ask when the space is wide. Corollary
  (P7/P1): an unknown must be visibly unknown - a coach that says "at their age"
  without holding the age is fabricating, which is a firewall breach in prose
  form. HIGH.
- **G48 Per-place facility & equipment inventory** (extends G34/G44). A PLACE
  entity (G44) carries a persistent, effective-dated inventory: EQUIPMENT (step,
  band, kettlebell, mat, bike, rower), AMENITIES (AC, fan, stairwell, garden,
  pool, scale), CONSTRAINTS (neighbours/noise, floor type, space, hours).
  Captured ONCE when a place enters the model - a short onboard-this-place flow
  or extracted from chat (G43) - then reused forever and editable. This is what
  turns "do you have a step?" from a question asked every session into a fact
  asked once. G34's coarse facilities (scale/gym/AC) generalize into this; the
  planner reads it to constrain what it may propose (no rower where there is no
  rower, no 21:00 skipping above a neighbour). MEDIUM.
  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > a place's facilities vary over time and gate what is possible there. Do not re-derive this entry; extend #220.
- **G49 Household, dependents & availability windows** (P2/G34). The model must
  know WHO is around and WHEN a session is actually possible. DEPENDENTS with
  ages (data, never assumed - ages gate what they can join in with and whether
  they can be left unattended), their routine (awake / screen-time / asleep /
  own activity), the PARTNER's schedule, and the resulting **availability
  windows**. A proposal must land in a REAL window, not an abstract "evening":
  "20:00 while they are on the sofa - they can join the first rounds" vs "21:00
  once they are down, so keep it quiet". Windows intersect with the heat and
  daylight windows (G34) and the calendar; the intersection IS the schedulable
  slot. Dependent-care is a hard constraint, not a preference - it can veto an
  otherwise-perfect plan (a stairwell session means leaving the flat). MEDIUM.
- **G50 Context-scoped preferences** (P2/P5/G43). A preference is rarely global;
  it is SCOPED: `{subject, domain, scope: {place?, mode?, phase?, time-of-day?,
  weather?, with-whom?}, strength, provenance, effective-dated}`. "Likes running
  to Zwin" is scoped to a place; "prefers short circuits" may be scoped to
  phase=cutting; "will not do burpees" is global. Resolution when several apply:
  **most-specific wins** (CSS-specificity-like), ties broken by strength then
  recency, and the coach can always say WHICH preference drove a proposal.
  Preferences are learned from statement (G43, higher trust) AND from behaviour -
  what actually gets done vs silently skipped - the latter at lower trust and
  never asserted as a stated preference (P3). This is what lets "preferred
  exercises", "preferred exercises at Knokke", and "preferred exercises when
  cutting" coexist without contradiction. MEDIUM.

- **G51 Person model: people as typed entities AND constraint sources**
  (subsumes G49's dependents; P2/G32). A `people` dataset of typed entities -
  `relationship`: partner | child | family | friend | colleague | coach | other;
  flags `household` (shares my resources) and `dependent` (+ age as DATA, never
  guessed). Each carries only what MY planning needs:
  - *Participation capability*: which sports/intensities they do, rough level or
    pace band, what they can join ("kids can do 10 min of a circuit", "X runs my
    easy pace"). Turns a solo session into a joint one.
  - *Availability & travel state*: home place, and where they will BE in the
    planning window - home | out | away | on-holiday | at-a-conference, and
    crucially **with-me or without-me** (a partner at a conference *with* me
    shares my mode and place; *without* me flips me to sole care duty).
  - *Coarse restriction*: "unavailable for running until <date>" - a planning
    fact, NOT a diagnosis.
  **The load-bearing semantic is CONSTRAINT PROPAGATION - another person's state
  changes MY feasible set, in both directions:**
  - their PRESENCE can block me (they are using the shared crosstrainer -> G52);
  - their ABSENCE can block me (they leave -> I hold dependent care -> no
    leave-the-house session, however good the weather);
  - their AVAILABILITY can expand me (free + willing + able -> a partner run, or
    the kids joining rounds).
  The planner must evaluate people-state before proposing, not after.
  **Third-party privacy is a hard line (G32).** These people never consented to
  being in my health record. Store the MINIMUM for planning - availability,
  participation capability, coarse restriction - and NEVER their medical detail,
  their metrics, or their location history. Another person's health data belongs
  to them, in their own record if they want one. Minors get extra restraint. A
  person entity is a planning aid, not a dossier. HIGH.
  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > people are constraint sources, and their availability can EXPAND the athlete's feasible set as well as block it. Do not re-derive this entry; extend #220.
- **G52 Shared-resource contention & allocation** (extends G48; P2). G48 says a
  place HAS an asset; this says whether it is FREE. Shared assets (a
  crosstrainer, the car, one bike, a single mat, a bookable gym slot) have
  **exclusive use over a window**: a household member's claimed use BLOCKS mine
  for that window, and the planner checks asset AVAILABILITY, not merely asset
  existence. Generalizes past equipment - if the partner has the car, the
  drive-to-trailhead journey (G44) is off, which silently invalidates an
  otherwise-valid plan. Contention resolves against the availability windows of
  G49/G51: the intersection of (my free window) x (asset free) x (care duty
  clear) is the real schedulable slot. A blocked asset is a REASON the coach can
  state ("the crosstrainer is taken till 19:45 - want the 20:00 slot, or the
  bodyweight version now?"), never a silent omission. MEDIUM.

  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > contention is availability, not fault - the planner checks availability, never mere existence. Do not re-derive this entry; extend #220.
- **G53 Kit, attire, access credentials & carry-load** (P8/G48/G52). The
  logistics layer that silently invalidates otherwise-perfect plans. A planned
  activity carries REQUIREMENTS, and the athlete carries STATE:
  - *Kit requirements* per activity x place: a gym session needs a towel and a
    bag to carry it; a run needs running clothes; finishing anywhere that is not
    home needs shower kit, a drying towel, fresh underwear. What is needed
    depends on what the PLACE already affords (G48): a gym with showers and towel
    hire changes the packing list entirely.
  - *Access credentials are HARD GATES*, not conveniences: the phone that shows
    the entry QR, a badge, a members card, a booking confirmation. Missing it
    means the session cannot happen at all - the planner must treat it as a
    feasibility precondition, at the same level as "is the gym open".
  - *Attire state*: the athlete IS in some attire (running kit, civilian, work
    clothes), and changing requires being somewhere with the right kit. Driving
    to the office in civilian clothing forecloses a run there unless it was
    packed.
  - *CARRY LOAD CONSTRAINS LOCOMOTION MODE* - the sharp one. Carried mass and
    bulk restrict which modes are available for the NEXT leg: 10 kg of shopping
    means walking, not running; a loaded backpack makes a run possible but slower
    and less pleasant; hands-full rules out some modes entirely. Carry state is a
    first-class planning variable, not a detail.
  - *PREPARATION LEAD TIME (pack-ahead)*: kit must be surfaced at the LAST MOMENT
    THE ATHLETE CAN STILL ACT - before leaving home this morning for a session
    this evening - never on arrival, when the information is useless. A
    pre-departure checklist is a rare nudge that EARNS its interrupt (G39/P8):
    high value, time-critical, and cheap to act on.
  MEDIUM.
  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > entitlement is a hard feasibility precondition, distinct from both equipment fault and injury. Do not re-derive this entry; extend #220.
- **G54 Trip chaining & leg-state propagation** (extends G44/G51). A journey is
  a SEQUENCE OF LEGS, and each leg MUTATES the state the next leg depends on -
  so legs cannot be validated independently. Shopping on the way home from the
  gym adds carry-load, which downgrades the last leg from run to walk (G53); a
  session leaves the athlete sweaty, which gates what comes next without a
  shower; a one-way route consumes the outbound transport. The planner validates
  the WHOLE CHAIN and reports where it breaks, rather than proposing a pretty
  first leg that strands the athlete.
  **Transport legs may need SECURING, not merely choosing.** A one-way route
  ("run home from a town along the coast") requires an outbound leg that actually
  exists and is arranged: a bus with a real timetable, a taxi/rideshare that must
  be booked, a lift from a family member - which is a dependency on ANOTHER
  PERSON (G51) and needs their agreement before the plan is real. An unsecured
  transport leg makes the plan a proposal, not a schedule, and the coach must say
  so ("the Cadzand start needs a lift or the bus at 08:40 - want me to lay out
  the options?"). Autonomous booking is never done on the athlete's behalf.
  MEDIUM.

  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > state propagates along a sequence; each leg mutates what the next depends on. Do not re-derive this entry; extend #220.
- **G55 Owned gear inventory & consumable lifecycle** (extends G53/G48/G52).
  G53 covers what is CARRIED for a session; this covers what is OWNED, and it
  behaves differently in three ways:
  - *Gear GATES activities.* No racket, no tennis; no stick, no hockey. The
    planner may only propose sports the athlete is equipped for, and acquiring
    gear is a signal in itself - a new stick or racket often means a new sport
    entering the plan, which the coach should notice and ask about rather than
    ignore (a goal may be forming).
  - *Consumables have a LIFECYCLE, and it is deterministically trackable.*
    Running shoes are the canonical case: they carry accumulated mileage and a
    replacement threshold (commonly ~600-800 km, brand and model dependent). The
    engine can sum run distance per shoe pair since purchase and flag
    replacement - a genuine derived metric, in the number path, not a guess.
    Worn-out shoes are an injury-risk factor, so this is a safety-adjacent
    signal, not a shopping reminder. HR-strap batteries, worn kit and expiring
    memberships are the same shape.
  - *Gear has a LOCATION and may not be duplicated.* Shoes at the home address
    are not shoes at the holiday flat; a watch left on the charger at home is
    unavailable. Gear location joins the place inventory (G48) and the carry/kit
    check (G53), and a single-instance item is contended like any shared asset
    (G52) when a household member has it.
  Condition/availability (dead battery, kit in the wash, shoes soaked from
  yesterday's rain) gates use as hard as absence does. MEDIUM.
- **G56 Goal currencies & equivalent-outcome substitution** (P7/G18/G45). The
  hardest live tension in coaching: the athlete wants to ramp fitness AND hold a
  deficit AND avoid injury, and a guardrail that only says NO loses to
  motivation every time. The resolution is that **different goals are bought in
  different CURRENCIES at different risk prices**:
  - the calorie/deficit goal is bought with TIME ON FEET - walking is nearly
    free (no ramp cost, no injury price, no recovery debt);
  - the running-fitness goal is bought with RUNNING VOLUME - scarce, expensive,
    injury-priced, and the only currency that actually builds the fitness.
  The characteristic error is **paying for calories with the expensive
  currency**: a long run chosen "for the burn" spends scarce ramp budget on
  something cheap movement buys for free. So the engine carries a per-goal
  currency + risk-price, and when a guardrail rejects the athlete's plan the
  coach's move is NOT to decline but to **SUBSTITUTE - same outcome, cheaper
  currency**: cap the risk-priced component at what the ramp affords, then buy
  the remaining outcome with the free one. (Worked case: a walk-run-walk
  sandwich delivered an identical deficit at ~45% less running load, with the
  walks doubling as warm-up and cool-down - strictly better, not a compromise.)
  Design consequences:
  - a rejection must always ship with a **counter-offer** - "here is how to get
    what you wanted, for less" - because "doing something beats a rest day" is a
    real adherence fact, not a weakness to be corrected (P7);
  - substitutions are computed from the athlete's OWN calibrated rates (their
    logged kcal/min per modality), never textbook METs, so the equivalence claim
    is theirs and defensible;
  - the coach names honestly what is lost and gained, including the
    MOTIVATIONAL stat (an external tracker still logs the walk; the compounding
    metric is weekly consistency; holding back now is what makes the easy pace
    fall later). A substitution sold as a downgrade gets refused; sold as the
    same outcome at a lower price, it gets taken. HIGH.

- **G57 Life-stage & physiological states (contraindications, not context)**
  (P3/G28/G34). CRITICAL, found in persona validation. Breastfeeding adds ~500
  kcal/day of demand and makes an aggressive deficit CONTRAINDICATED; pregnancy,
  postpartum, adolescent growth, menopause, acute illness and injury recovery
  likewise change what the numbers MEAN and what is SAFE. `context.jsonl` (G34)
  models situational mode (vacation, heatwave) - a different axis entirely. A
  physiological state alters energy requirements, safe rate bounds, and which
  interventions are permitted at all. Without it the engine will cheerfully help
  an athlete run a dangerous deficit. See [validation-personas.md](validation-personas.md) F3. CRITICAL.
  > **SPECIALISED by #220 (state model), 2026-08-03.** Implemented, with live
  > rows, and retained. The general state shape specialises to this rather than
  > replacing it.
- **G58 Goal safety & feasibility validation at declaration** (P1/G6/G28).
  CRITICAL. A goal is currently stored as data and tracked faithfully however
  unsafe it is - the engine would report an athlete BEHIND against "12 kg in 6
  weeks" week after week while they ate less to catch up. Declaration needs a
  gate: physiological rate bounds, life-stage contraindications (G57), deadline
  sanity. The output is a NEGOTIATION ("here is what 6 weeks can actually
  deliver") - never silent compliance, never a bare rejection. Validation F4.
- **G59 Red-flag capture from PROSE + resolution scope** (P4/G28/G43). CRITICAL,
  and the highest-value finding of the persona validation. Red flags arrive as
  downplayed asides in conversation, never as data: "the odd twinge now and
  again but it's nothing" (which turned out to be EXERTIONAL chest pain), "is
  that why I nearly blacked out". The person does not believe it is data,
  often precisely because they are frightened. G28 reads severity from a
  structured entry or a threshold breach and would have seen NOTHING in either
  case. Resolution preserving P4: **the LLM recognises and CLASSIFIES symptom
  language into a structured claim (the G43 capture path); the deterministic
  engine maps severity to action and emits hardcoded escalation text.** LLM
  extracts, engine decides - neither half suffices alone. Corollary: **a prior
  negative workup must not suppress a NEW or CHANGED symptom** - episode
  resolution carries a scope and an expiry, and re-fires regardless of status.
  Validation F1, F2.
  > **SPECIALISED by #220 (state model), 2026-08-03.** Implemented, with live
  > rows, and retained. The general state shape specialises to this rather than
  > replacing it.
- **G60 The cadence unit is not the calendar week** (P2/G30). HIGH. Verdicts,
  rollup, streaks and goal periods all bucket by Monday-anchored calendar week.
  For a rotating-shift worker that unit is fiction ("my week never looks the
  same twice"). Needs a configurable cadence: calendar week | rolling N days |
  a user-defined cycle (a shift block). Affects nurses, police, fire, logistics,
  hospitality, military - a large population, not an edge case. Validation F5.
- **G61 The subjective day anchor** (P2/G30). HIGH. G30 fixed timezone and DST
  but kept a midnight-anchored day. A night worker sleeps 09:30-15:00 and works
  19:30-08:00, so every shift straddles midnight and "last night's sleep" lands
  in a calendar afternoon. The day boundary must follow the person's SLEEP
  (wake-to-wake), not the clock; naive midnight bucketing silently splits every
  night shift in two. Validation F6.
- **G62 Goal kinds + proxy indicators** (G6/G18/P8). HIGH. "One unassisted
  pull-up" is target=1 with a progress series of 0,0,0,...,1: monotonic-vs-
  guarded is meaningless and 25/50/75/100% milestones generate nothing. Needs a
  goal `kind`: **quantity** (accumulate) | **skill** (binary, achieve) |
  **maintenance** (hold). Skill goals additionally need **proxy / leading
  indicators** carrying the visible progress the goal cannot (hang time,
  lowering tempo, assistance load) - the proxies are what the athlete watches,
  the goal is what eventually pops. Generalises past fitness (an exam, a
  certification), which is P8's genericity claim actually tested. Validation F7.
- **G63 Re-entry contract & sanctioned pause** (P7/G8). HIGH - plausibly the
  highest-ROI behaviour in the product. The dominant adherence failure is not
  training, it is RE-ENTRY: "I miss two sessions, feel like I've fallen off,
  three weeks pass, I feel stupid going back like I'm starting from nothing, so
  I don't." Needs (a) a re-entry contract - resume at the SAME load, the coach
  never asks where you have been, a lapse is structurally not a broken streak;
  and (b) a **sanctioned pause** as a declarable state with a named
  minimum-viable dose, because **the absence of shame is not the presence of
  permission** - an athlete who is not explicitly told "stopping is fine" will
  invent the guilt anyway. Falling off is unplanned and carries guilt;
  downshifting is planned and does not. A pause also needs a gentle
  pre-authorised integrity check (the athlete's own request: don't let me use
  the exam as a shield for everything). Validation F8, F9.
  > **ABSORBED into #220 (state model), 2026-08-03.** The MECHANISM proposed
  > here is superseded by the general state shape - subject, warrant, extent,
  > resolved at read time. The CONSTRAINT is retained and must survive it:
  > a sanctioned pause is declarable, and the absence of shame is not the presence of permission. Do not re-derive this entry; extend #220.
- **G64 Low-data / deviceless mode + plain language** (P8/P3). HIGH. Two of
  three personas had no wearable and no intention of getting one; one tracks
  nothing at all and distrusts apps. The resolution layer, `kcal_out`, HR caps,
  RHR baselines and rate verdicts all assume device data. P8's "minimum viable
  day is one number" has never been tested. Needs an explicit mode where the
  record is qualitative (did it happen, how did it feel) and the coach stays
  useful with zero instrumentation - plus plain-language translation of the
  athlete's own clinical numbers (an HbA1c carried for two years without ever
  being explained). Validation F10, F16.
- **G65 Goal contention & deliberate deprioritisation** (G18/G6). MEDIUM. G18
  fans one event out to many goals, but nothing models goals COMPETING for one
  finite budget of time, energy and attention - a certification exam eating the
  same days off that training needs, and mattering more. "This goal outranks
  that one until November" must be a declarable state that changes what the
  coach asks for. Validation F12.
- **G66 Occupational & incidental activity** (P1/G22). MEDIUM. "I reckon I do
  miles a day but I've never measured owt" - eight hours a day on his feet is
  almost certainly the largest energy term in his life and is entirely
  unmodelled. The engine assumes activity arrives as sessions plus device steps;
  for manual workers occupational load dominates both, and ignoring it makes
  every energy number wrong. Validation F13.
- **G67 Off-limits domains & deferred levers** (P7/G33). MEDIUM. G33 suppresses
  a METRIC; this is an entire intervention DOMAIN declared untouchable ("that's
  a battle I've already lost, don't even suggest it" - a partner's cooking), and
  separately a lever the athlete acknowledges and PARKS ("I don't see that as
  the problem"). Correct behaviour differs: an off-limits domain is respected
  silently and worked around; a deferred lever is named honestly ONCE without
  moralising, then left alone and revisited much later. Nagging either loses the
  athlete. Validation F14.

- **G68 Safety must not be opt-in; defaults fire unconfigured** (P4/G28).
  CRITICAL, found by RUNNING the engine. A nursing mother eating ~1200 kcal,
  losing ~1 kg/week, protein 40-58 g, with a near-syncope, produced
  `tripwires: none` - because the rate verdict needs configured phase targets
  and tripwires need configured thresholds, and she is a new user who has
  configured nothing. **The entire safety apparatus is inert by default**, which
  is backwards for the population most at risk: new, motivated, uninformed, and
  already doing something dangerous. Absolute-danger rules (impossible rate of
  loss, intake below a floor, a red-flag symptom) must fire from DEFAULTS.
  Configuration may TIGHTEN the net; it must never be the thing that creates it.
  See [validation-personas.md](validation-personas.md) E1.
- **G69 Signed quantities must be labelled, not bare** (P7/G34). HIGH. The
  rollup rendered `**Rate:** +1.10 kg/week` for an athlete who had LOST 1.5 kg -
  the convention is `(older - newer)`, so positive means losing, but the plain
  reading of "+1.10 kg/week" is gaining. For a scale-anxious athlete already
  under-eating, that misreading is the single input most likely to make her cut
  further. Every signed quantity states its direction in WORDS ("losing 1.10
  kg/week"), never a bare sign the reader must know a convention to decode.
  Validation E3.
- **G70 Resistance training is unmodelled** (P8/artifact-1). HIGH. `sessions`
  carries `distance_km`, `duration_s`, `avg_hr`, `cadence`, `elevation_m`,
  `route`, `weather` - every field is an ENDURANCE field. **There is nowhere to
  record a set, a rep or a load anywhere in the schema**, so a gym session can
  only be stored as a duration plus a note. This blocks: any strength goal
  (an athlete whose entire objective was a pull-up), progressive-overload as a
  signal, and the Tier-2 recomposition proxy G36 explicitly depends on. A large
  hole for a project claiming domain-genericity. Needs a sets/reps/load
  structure and a `setting` value for `gym` (the enum today is home | indoor |
  outdoor | treadmill). Validation E5.
- **G71 Quantities recorded as booleans and scalars** (P1/P3). MEDIUM.
  `alcohol` is a BOOLEAN: five pints on a Friday and one can with dinner both
  store as `true`, hiding ~1,400 kcal across a weekend that is plausibly the
  athlete's largest dietary lever. `sleep_h` is a SCALAR: "2-4 hours broken
  across three wakings" and "5.5 daytime hours behind blackout blinds" both
  reduce to a number, and fragmentation plus timing are the entire story for
  both athletes. Where a quantity or a structure exists, store it. Validation E6.

- **G72 Medication as a first-class modifier** (P3/G57/G28). CRITICAL, sweep 2.
  A GLP-1 agonist (semaglutide) changes the meaning of nearly every number:
  appetite suppression produces INVOLUNTARY sub-800 kcal days that are not
  restriction and not non-compliance; rapid loss is EXPECTED, so a naive
  rate tripwire fires wrongly; and the real risk is lean-mass loss from rapid
  loss plus inadequate protein plus no resistance training. Beta blockers
  invalidate HR caps and zones; steroids alter weight and glucose; insulin and
  sulfonylureas create hypoglycaemia risk around exercise; SSRIs, diuretics and
  statins all matter. **Voluntary and involuntary under-eating need opposite
  interventions**, and no field distinguishes them. See
  [validation-personas.md](validation-personas.md) sweep 2.
- **G73 A CLINICAL HOLD tier above "flag"** (P4/P7/G28). CRITICAL, sweep 2. The
  RED-S persona showed a severity that no existing tier expresses: recurrent
  bone stress injury + amenorrhea + energy availability far below the clinical
  threshold is not a tripwire to surface alongside the week's rate line. The
  correct system behaviour is a **hold**: suspend algorithmic load progression,
  BLOCK the coach from issuing training advice on the case at all, and surface a
  mandatory clinical referral. G28 as written escalates a message; this
  escalates by DISABLING the product's own advice. A system that logs
  "tripwire: nutrition" here is still under-detecting.
- **G74 The athlete's benign self-explanation is not evidence** (P1/P3/G59).
  HIGH, and the sharpest cross-cutting finding of sweep 2 - it appeared in FOUR
  of eight personas. Each supplied an innocent cause for a concerning sign:
  "it's the reflux" (exertional chest pain), "that's just what happens when you
  train hard" (five months of amenorrhea), "my legs aren't used to carrying the
  lighter me" (weakness on stairs during rapid loss on a GLP-1 - i.e. probable
  sarcopenia), "I stood up too fast" (near-syncope while under-eating). The
  athlete's causal attribution is a CLAIM like any other (P1) and must never
  suppress the pattern it explains away. The engine reads the sign; the
  explanation is recorded, not deferred to.
- **G75 Subjective and objective measures are different quantities** (P1/P3).
  MEDIUM. A device reported 6.1 h of sleep and the athlete reported "felt like
  5", every night, systematically. These are not competing claims to resolve
  (G15) - both are true, and the DIVERGENCE is itself the signal (in
  perimenopause, fragmented sleep with normal duration is the presentation).
  Resolution must not collapse a perceived measure into a measured one.
- **G76 Logging bias is not the same as logging coverage** (P1/G26). MEDIUM.
  "I log breakfast and lunch because those are the meals that already look
  fine" - her logged 1580-1710 kcal days are systematically biased low, not
  merely incomplete. `coverage: partial` records that something is missing; it
  cannot record that what is PRESENT is unrepresentative. A biased sample read
  as a complete one produces confidently wrong energy arithmetic.
- **G77 Capacity-limited progression** (G6/G62). MEDIUM. For an athlete with
  knee osteoarthritis the limiter is PAIN, not fitness: 15 minutes of walking is
  a hard ceiling that no ramp rule can progress through, and the goal (a 5 km
  walk) must be approached by changing the constraint - load, surface, footwear,
  strength work, clinical input - rather than by adding volume. The model's
  progression logic assumes the limiter is conditioning.

- **G78 Athlete-defined metrics: the schema is a developer's ontology**
  (P8/P5/artifact-1). CRITICAL, and the largest finding of the whole validation
  programme. Sweeps 1-2 only ever asked for metrics the DEVELOPER chose - steps,
  sleep, calories, heart rate - so they could only find gaps in what was already
  imagined. Sweep 3 asked eight athletes what THEY wanted counted. **Almost
  nothing they named fits the schema**, and several are things they have counted
  privately for years: nights without the 3am vending machine; whether the stairs
  happened without stopping ("12 of 14"); belt holes measured against a kept
  wedding-day belt; times saying yes instead of "you go on, I'll wait here";
  meals eaten sitting down rather than over the sink; magpies on the path before
  7am. A fixed schema cannot serve this. The athlete must be able to DECLARE a
  metric - name, kind, unit, scale, cadence - and have the engine count, streak,
  trend and celebrate it as a first-class citizen, without a developer.
- **G79 Metric KINDS beyond measurement** (extends G78/G62). The invented
  metrics are almost never measurements. They are: **counters** (times I said
  yes); **days-since with reset** (days since a bad night - "reset to zero, like
  a superstition"; weeks since a session felt easy); **reset-on-fail streaks**
  (nights without the vending machine, "resets the second a Twix happens");
  **fractions of a named obstacle** ("12 of 14 stairs"); **pass/fail against a
  fixed personal landmark** (the staircase whose bannister he built);
  **occupational capacity** (fares in a row before needing a sit); **affective
  quality** (did it feel EASY - explicitly "not RPE; RPE tells you how hard,
  this is whether it felt light"); and **deliberate-omission counts** (sessions
  skipped guilt-free with no makeup session - counting NOT training as the
  achievement).
  **Crucially, magnitude is often EXCLUDED on purpose**: "a day where I did five
  useless minutes counts the same as the full session, because the
  not-showing-up is the actual enemy", and "whether we did it - not the
  distance, not the calories". Quantifying these would destroy what they measure.
- **G80 Relational metrics: the achievement is shared** (P8/G51). SIX of eight
  athletes named a metric whose subject is a RELATIONSHIP, unprompted: did we sit
  down together of an evening; did we talk with no phones; days since we had a
  proper meal rather than crossing in the kitchen; whether we walked together
  ("not the distance - whether we did it"); whether the kids came and watched -
  **and WHICH one, because (in his words) the two of them watching are two
  different things to him**. The engine is single-athlete throughout. These are not the
  athlete's metrics with a person attached; the dyad is the subject.
- **G81 Per-metric privacy, and the refusal to capture** (extends G32/G33).
  Several metrics were disclosed WITH an explicit privacy condition: "I'd want it
  private, not something that shows up on a screen anyone else sees" (a chest
  feeling after eating late); "I would never say this to my old coach" (the
  magpies); "I'd never admit to him that I know the score" (a private
  head-to-head ledger with a friend); a countdown that "sounds like I'm wishing
  time away with my own kid". Needs per-metric visibility - including HIDDEN FROM
  THE COACH. And the harder case: a quantity the athlete keeps, will not record,
  and does not want recorded - a running count of bad shifts, "some of it isn't
  for tracking". **The model must be able to know a thing exists and deliberately
  not hold it.** A capture system that treats every disclosed quantity as
  capturable is a system people stop talking to.
- **G82 The unaccounted period** (P1/P2/G34). EIGHT of eight, independently and
  unprompted, described a stretch of months that resists any form - and in every
  case it is where the actual story lives. "A gap where I wasn't really present
  for my own life." "Nothing changed, I just quit paying attention, on purpose,
  because checking meant admitting it was going wrong again." "Frightened and
  frozen and ashamed all at once and none of those turn into a walk."
  Three consequences the model must absorb:
  - **A gap is data, not missing data.** The absence has a shape and a duration
    and is often the most informative region of the record.
  - **The recorded reason may be a self-protective fiction.** One athlete's log
    attributes a months-long drop to an Achilles injury; the real cause was his
    father's stroke, and he "let the Achilles take the blame because it was
    easier than saying the actual thing". A stated reason is a claim (P1), and
    the engine must not treat it as ground truth.
  - **The most valuable period may contain no data at all.** An athlete's ten
    weeks off after a fracture - eating ad-lib, cross-training only - is the
    natural experiment that shows her physiology recovering, and it is "a hole in
    the spreadsheet... it just closes over in the log like it didn't happen".
  And the boundary: an athlete may decline to explain a gap. "I wouldn't want
  there to be [a box], some of it isn't for tracking." Never demand a reason.
- **G83 What they would be sad to lose is never a number** (P7/G6). Asked what
  they would want to look back on in five years, NOT ONE of eight named a metric,
  a target or a weight. They named an identity or a relationship: "that I still
  had a me outside the ward"; "who was standing at the finish line, not the time
  on the clock"; "walking her down that aisle without her having to slow her pace
  for me"; "if I've kept the weight off but I'm still the mum who says 'you go
  on', I'd count that as having lost, whatever the scale says"; "I'd rather
  remember running with him in the pram and him laughing at the wind than
  remember hitting 62". The goal model is target-based all the way down. It needs
  a layer ABOVE targets - the thing the targets are FOR - so progress is judged
  against what the athlete actually values, and a target met while the thing it
  served was lost registers as the failure it is.
- **G84 Conflict shapes the model cannot express** (extends G56/G65). Every
  athlete named a genuine trade, and three have shapes the substitution
  machinery (G56) does not cover:
  - **Cost-before-benefit, and that trough is where people quit.** "Cutting the
    wine costs me before it pays me anything back, and that gap is exactly where
    I've quit before." An intervention with a delayed payoff needs its trough
    modelled and defended, not just its endpoint promised.
  - **Negative return on effort.** Pushing the walking flares the knee, which
    costs two days of school runs - so MORE effort yields LESS total activity.
    Ramp logic assumes monotonic returns.
  - **The intervention destroys the mechanism.** "Eating more deliberately means
    it stops feeling like the drug is doing it for me, and if I have to TRY, it
    will go the way of every other diet." The physiologically correct change
    undermines the psychological property that made it work at all.
  Plus the honest refusal: two hours of pints a week are "the only two hours I'm
  not being useful to somebody... I'm not sure I want it squared." A conflict may
  be correctly left unresolved.

- **G85 Genericise before encoding: one axis per vocabulary, registry not
  code** (P5/P8/artifact-3). CRITICAL as a PROCESS gap - it is the failure mode
  that produced several of the others, and it has now been caught twice.
  Closed vocabularies were written from ONE athlete's examples rather than
  designed as taxonomies, so they mix orthogonal axes and cannot express cases
  that were not in front of the author. The evidence:
  - `SESSION_TYPES` ships `gym_a` and `gym_b` - one person's programme labels -
    in a public engine, while cycling, swimming, rowing, climbing and every
    team sport collapse to `other`;
  - `ACTIVITY_CLASSES` mixes a scope quantifier, a setting, a loading modality,
    anatomical regions and specific activities in one flat list, and could not
    express either of two real clinical gates;
  - `CONTEXT_MODES` mixes weather, health, calendar, employment state and
    social; `SEVERITIES` mixes a magnitude scale with a routing decision
    (`red_flag`); `SETTINGS` contains a piece of equipment; `WEATHERS` cannot
    say "cold and raining"; `MEASUREMENT_KINDS` bakes units into value names.
  **The rule:** one axis per vocabulary; POST-coordinate rather than
  pre-coordinate (the `body_sites` pattern - the one vocabulary that got a
  prior-art sweep, and the only one without this defect); ground every
  vocabulary in real prior art before writing it (Compendium of Physical
  Activities for activities, ICF for activity limitations, FHIR value sets for
  provider roles); and put it in `semantics/*.toml` as a curated registry
  (artifact kind 3), never a Python `set`.
  **The structural reason this keeps happening:** a vocabulary in CODE can only
  be extended by a developer, so it can only ever contain what the developer
  had seen. A vocabulary in the REGISTRY can be extended by the athlete, which
  is also exactly what G78 requires. Same fix, two problems.
  **The same rule applies to ALGORITHMS, not only vocabularies** (extended
  2026-07-30 after the operator caught it a second time). Route analysis was
  hand-rolled in throwaway scripts: a raw haversine sum over 1,467 GPS points
  (which systematically OVERESTIMATES - jitter adds phantom length on every
  sample, and the resulting 1.50 km was reported against a watch odometer of
  1.39 km as if the watch were the odd one out); a 38-metre grid-cell overlap
  ratio invented on the spot to decide "is this the same route", when the real
  problem has named solutions with published thresholds (discrete Frechet, DTW,
  LCSS, or map-matching to an OSM edge sequence); and an eyeballed judgement
  that 115 m of elevation gain was noise, which was right by luck rather than
  by a DEM correction with a minimum-climb threshold. The one component that
  behaved well - stop detection - was the one grounded in prior art (CB-SMoT).
  **Rule: before implementing an analysis, find the named algorithm and the
  maintained library. A hand-rolled metric with no published threshold cannot
  be defended, cannot be tuned, and cannot be told apart from a bug.** And
  scratchpad scripts are not an implementation: an analysis the coach relies on
  ships as versioned code with tests and a CLI+API surface (P9), or it is not
  reproducible and its numbers are not evidence.
  Tracked in issue #18. See also G78 (athlete-defined metrics) - the general
  form of the same mistake, found by asking eight athletes what they count.

- **G86 Events, deadline hardness, and attested-only goals** (G6/G20/G62).
  HIGH. Three distinctions the goal model collapses, all named by the operator
  on 2026-07-30 and all with real coaching consequences.
  - **An EVENT is not a derived milestone.** The engine derives milestones as
    fractions of a target (25/50/75/100%). What actually anchors training is a
    dated real-world FIXTURE: a wedding, a competition weigh-in, a 10k race, a
    scan, a holiday. Those are immovable, externally owned, and they are what
    periodisation is built backwards from. Two different concepts share one
    word, and only the derived one exists. Needs an `events` dataset (date,
    slug, title, kind, immovable, place) that goals can anchor to.
  - **A deadline is HARD or SOFT, and the difference is not cosmetic.** A race
    date cannot be moved; a self-imposed "73 kg by Q1 2027" can be moved at no
    cost to anyone. Consequences: a hard date forces backwards planning and a
    taper, and its approach RAISES urgency; a soft date is a direction of
    travel. **And G20's churn logic actively misfires without this** - it flags
    a pushed deadline as possible goalpost-moving, which is exactly right for a
    target quietly slipped after a bad week and exactly wrong for a soft date
    the athlete may legitimately move. Accusing someone of gaming a deadline
    they invented is a trust-destroying false positive.
  - **Some goals are ATTESTED-ONLY: no metric can ever touch them.** Distinct
    from G19's `external` (another app measures it - a segment crown, a
    language streak). Attested means *nothing measures it*: "I want to enjoy
    running again", "I want to stop worrying about my hip", "I want to be the
    parent who joins in". The schema currently REQUIRES a non-empty `metric`,
    so these have no home at all - and the persona sweep found (G83) that what
    athletes say they would be sad to lose in five years is almost always of
    exactly this kind. The engine must be able to hold a goal it can never
    verdict: track it, surface it, ask about it, and take the athlete's word as
    the only evidence there will ever be.
  - **Goals overlap, and that is normal.** Two goals may share a metric, or be
    coupled (weight loss serves a pace goal). G18 already fans one event out to
    many goals, so contribution is handled; what is missing is recognising the
    RELATION - so the coach can say "these two move together" rather than
    treating them as independent, and so a single event is not celebrated twice
    as if it were two wins.
  Found while capturing a real goal, which also surfaced a G85 instance: goal
  `dataset` scopes only to `daily`|`sessions`, so a WEIGHT goal - the most
  common goal in the domain - cannot be scoped to the weight dataset.

- **G87 Egress masking for location and habit** (P8/G32/G35). HIGH. The record
  is personal and local-first, so the risk is EGRESS, not storage. What leaves
  the machine is governed by ONE toggle, and the design has four parts the
  literature makes non-obvious:
  - **The endpoints are the asset, not the route.** Golle and Partridge
    (Pervasive 2009) found the median anonymity set for a known home/work pair
    at census-block granularity is ONE - two coarse points re-identify most
    people, no trajectory required. Standard home-detection clusters stay
    points at trip START and END, which is where every run begins: the front
    door. So masking is endpoint-weighted - heavy on the first and last
    100-200 m, light or absent in the interior, which keeps route matching
    working (it needs only 10-50 m precision).
  - **A stable pseudo-anchor, NEVER a fresh random draw per export.** The
    obvious design - "replace home with a random point within r" - fails to a
    trivial averaging attack: N exports with independent noise let an observer
    average back to the true centre, and accuracy improves as sqrt(N). The
    offset must be DETERMINISTIC per place (a keyed hash of the place id), so
    the same anchor is emitted every time and repetition reveals nothing.
    Geo-indistinguishability (planar Laplace, Andres et al. 2013) is the
    principled alternative but needs a privacy budget tracked across queries;
    a fixed pseudo-anchor is the cheap version that survives repetition.
  - **Radius must exceed building scale.** 100 m is roughly a block and is
    likely too tight; the offline-geocoding sweep put street-block redaction at
    H3 res8-9 (~150-450 m) or geohash 6-7. Configurable, with the honest
    trade stated: tighter is more useful and less private.
  - **Spatial cloaking (k-anonymity) does NOT apply here.** It hides a person
    among k others, and a single-user record has no population to hide in - k
    degenerates to 1. This is exactly the 2018 Strava heatmap failure:
    aggregation is not anonymisation where the local population is near zero.
  **Temporary anchors count, and are arguably worse.** A holiday flat is a home
  for that fortnight, and publishing it also announces that the real home is
  empty. Any place the athlete sleeps gets anchor treatment, not just the
  registered address.
  **HABIT is its own leak, and geometry masking does not cover it.** Recurring
  routes at recurring times reveal when a house is empty - "runs 21:30 Tue,
  Thu, Sat from the same anchor" is a schedule, and a schedule egresses even
  when every coordinate is masked. Timing needs coarsening or suppression on
  the same toggle.
  **The toggle is a hard boundary, not a rendering preference.** The unmasked
  value must be structurally unable to cross - one function, one place, tested
  - rather than depending on every call site remembering to mask. And the fact
  that the athlete may already have given this data to vendors is not a reason
  for this engine to add another copy: each egress is a separate decision
  (consent-per-consumer, G32).

- **G88 Degraded data must be self-describing at every boundary** (P3/G37/P4).
  HIGH, and the thing that makes masking (G87) safe rather than actively
  harmful. If a value is altered on its way out - masked, coarsened, rounded,
  imputed, defaulted, sampled - and the receiver is not TOLD, the receiver will
  compute on it as though it were exact and produce confidently wrong
  inferences. The masking then does more damage than no masking, because it
  substitutes a plausible falsehood for a known unknown.
  **The trap is specific to GOOD masking.** A stable pseudo-anchor (G87) is
  deliberately deterministic so repeated exports cannot be averaged back to the
  truth - and that same self-consistency makes it INDISTINGUISHABLE from a real
  observation. Noisy masking at least wobbles suspiciously; deterministic
  masking is perfectly believable and silently wrong. The property that buys
  the privacy is the property that invites the false inference.
  So a degraded value travels with its own description:
  - **What was done** (`masked | coarsened | rounded | imputed | defaulted |
    sampled`) and by what method.
  - **The error it introduces, as a band.** This is not a new mechanism - it is
    G37's measurement-uncertainty interval, reused: a 300 m keyed offset IS an
    observation with a +/-300 m band, and it must present as one. A masked
    coordinate that reports itself to 5 decimal places is lying about its own
    precision.
  - **What may NOT be derived from it.** Distance from a masked start point,
    "did the run begin somewhere unusual", time-of-day patterns from coarsened
    timestamps - each is a derivation the degradation has destroyed, and the
    payload should say so rather than leave the consumer to work it out.
  **Derivations over degraded inputs either propagate the band or refuse.**
  A 2.29 km walk measured from a +/-300 m anchor is not 2.29 km. The engine
  must not silently produce a precise-looking number from an imprecise input -
  that is exactly the confidence-laundering P3 forbids, arriving through the
  privacy layer instead of the inference layer.
  **This is a CONTRACT at the boundary, not a hope about the consumer.** The
  payload declares its own degradation so an LLM, a dashboard, a game backend
  or a future maintainer cannot reason past it by accident. A consumer that
  receives an undeclared masked value has been misled by the system, not by
  the athlete.
  Generalised beyond masking on purpose (the G85 lesson): the same rule covers
  a coarsened timestamp, a rounded weight, an imputed missing day, a
  default-substituted threshold and a sampled subset. Any lossy transform
  applied on the way to a consumer is a tier demotion, and a tier demotion that
  is not announced is indistinguishable from data corruption.
- **G89 A retirement is not done until every reader prefers the new name**
  (P8/G25). CODE-VERIFIED, and the standing rule for ALL future key
  evolutions. G25 makes an old line keep VALIDATING after a key is
  generalised. This is the other half: making the engine keep READING it, and
  reading the successor in preference. Miss it and the old data works
  perfectly while the new data quietly loses a linkage.
  **The verified instance.** `hip_pain` was retired at generation 2 in favour
  of `pain` + `pain_site`. `canonical_daily` mapped it forward, old rows kept
  gating, the suite stayed green. But the pain verdict still resolved its goal
  as `_goal_for(active, "hip_pain")`, and that lookup is an exact string
  match. An athlete who had only ever written `pain`, and declared a goal with
  `metric: "pain"`, got the correct pain number attached to `goal: None`. A
  missing linkage renders exactly like having declared no goal at all, so
  nothing looked wrong.
  **The asymmetry is structural, not an oversight.** Retirement is designed so
  the legacy path keeps working, which means the legacy path is the one under
  test, and the successor path is exercised by nobody until a second adopter
  appears. Compatibility work is self-testing in the direction that does not
  matter. Only the originating record, the one repo still carrying the retired
  field, exercised the branch that worked.
  So retiring a key is a THREE-part change, and doing two parts is worse than
  doing none, because it looks finished:
  1. The successor exists and old lines stay legal (`KEY_RETIREMENT`, G25).
  2. Forward mapping lives in exactly ONE canonicaliser. A fallback
     re-implemented at each reader means the key is not retired, it is
     dual-active in every module that names it. `hip_pain` is currently read
     in five modules for this reason.
  3. **Every lookup, filter, dispatch key and comparison naming the old key
     tries the successor FIRST, with the old name as fallback.** Exact string
     matches are the specific hazard: they fail silently and return a
     plausible result. Grep the retired name across the whole tree, not only
     the module that owns the schema.
  **A retirement also needs an end date.** `KEY_RETIREMENT` records when a key
  stopped being expected and has no slot for when it stops being legal.
  Without one, every retired key is permanent public surface area, and a
  general engine ends up carrying one private record's migration debt
  indefinitely. Migrate the originating data with the supersedes machinery,
  then schedule removal at a stated generation.
  HIGH. Tracked as #126.

## The frame: a guardrailed world model (belief-state, not a learned net)

vitai is a **world model of a person** in the cognitive-science sense - a
structured internal *state plus transition rules* the coach reasons over - and
NOT in the ML sense (a learned latent-dynamics net a la Dreamer/JEPA). It is a
symbolic **belief-state digital twin**: the `Know You Before You Speak` split
maps 1:1 - semantic-memory = facts + provenance tiers, user-state = goals +
context, world-model = the effective-dated derivation/update rules - and, as
that work notes, the athlete's true state is never directly observed, only held
as a justified belief (which is exactly what P3's tiers are). The "guardrail" is
the P4 firewall plus provenance: claims behave as **JTMS/ATMS-style nodes**
(`value, tier, justification, effective_date`) so revoking a justification
cascade-retracts everything derived from it (this unifies P1, P3 and the G29
correction cascade under one named model). Any future learned forecasting is a
separate, lowest-tier **prediction layer** that reads symbolic state and writes
back tagged with its own tier - it never upgrades or overwrites a fact (P3:
confidence never launders upward). What no ML world model or mechanistic digital
twin in the survey keeps, and vitai does, is that every value is inspectable,
effective-dated, and firewalled. Full sweep + citations:
[prior-art-world-model.md](prior-art-world-model.md).

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
