# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

Safety layer: the persona guardrail fixtures now hold (issue #12). All eight
`xfail(strict=True)` specifications flip to passing.

### Fixed
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
- Schema generations could only ever ADD. A retired key had no way to stop
  being required, so replacing a field would have forced every new line to
  keep writing the field it replaced. `KEY_RETIREMENT` fixes that, and is
  what makes the `hip_pain` generalization possible without a rewrite.
- `pain: 0` no longer demands a `pain_site`. "Nothing hurt today" is a
  complete statement, and it stays distinct from null, which means nobody
  looked.

---

Increment 1 - goals are data, contribution, and temporal validity
(G6 + G14 + G18 + G19 + G20). Read-model contract bumped to **2**.
Also unreleased: both increments ship together or in sequence once the
founding deployment has migrated (working rule 3).

### Added
- **`goals.jsonl`** - goals are data, not prose in `plan.md`. A goal carries
  its `metric`, `target`, contribution `policy`, `period`/`on_period_end`,
  `deadline`, lifecycle `status`, and the fields that make it answerable
  rather than just measurable: `motivator` (the why the coach anchors on),
  `rationale` (why *this* number), `on_success`/`on_miss`, `accountability`.
  A goal that lives in another app is `metric: "external"` plus a `tracker` -
  vitai models and reinforces it but never invents a verdict for it (G19).
  `dataset`/`session_type` scope which events feed a goal, because
  `distance_km` means walking on a `daily` line and running on a `sessions`
  one.
- **`thresholds.jsonl`** - every threshold is effective-dated (G14), with a
  `change_kind` separating a real policy change from a correction of a
  mis-entered number. `kcal_target` and `protein_g_target` live here rather
  than in `vitai.toml`, because a target edited weekly must be dated.
- **`achievements.jsonl`** - hand-recorded accomplishments, with a `source`
  carrying authorship so they are never confused with derived milestones.
- **`contributions`** - the fan-out (G18). One event is judged against every
  goal in force that day, each with its own signed verdict:
  `advances | partial | unbudgeted | neutral | regresses`. A goal declares
  `monotonic` (more always counts) or `guarded` (volume beyond `guard_pct`
  above the recent baseline is unbudgeted ramp and does NOT advance the
  goal). One walk can advance a steps goal and a calorie goal at once; one
  big unplanned run can advance the calorie goal while the running goal
  declines to credit it.
- **`milestones`** - target fractions crossed by COUNTED progress only, so a
  30 km week off a 12 km base mints nothing. The engine will not congratulate
  an athlete for the behaviour most likely to injure them.
- **`plan_churn`** - policy edits as a first-class derived signal (G20): what
  moved, which way, and a `suspicious` flag when a loosening lands within a
  week of a week that metric was missed. It carries the athlete's own
  `reason`, so an explained deload reads differently from a silent retreat.
  Nothing is blocked - the athlete owns the record; the flag invites a
  question.
- **`state(date)`** - as-of reconstruction. `Vitai.state(d)` returns the
  goals and thresholds in force on a date, which is what every judgment now
  uses.
- **`vitai goals`** (and `Vitai.goals()`, `.contributions()`, `.milestones()`,
  `.churn()`, `.state()`) - active goals with counted progress, percentage,
  declared/last-edited dates, recent per-goal contributions, and any flagged
  edits. CLI and API land together (P9).

### Fixed
- **Editing a threshold no longer re-scores the past.** Weekly verdicts are
  computed against the thresholds in force on each week's Monday, so lowering
  a floor today cannot turn last March's misses into hits on the next
  rebuild. This was the audit-trail flaw G14 named; the regression test is
  `test_past_week_keeps_the_threshold_in_force_then`.
- **Same-day corrections on identity-keyed datasets.** A correction that
  shares its slug and date with the line it replaces used to supersede
  itself, dropping both lines. Supersedes resolution is now positional: a
  line can only be retired by a LATER one, and a retired line still passes
  its reference on so a chain resolves.
- **Same-day events with mixed null types no longer break the build.** The
  contribution ordering tiebreak compared record items directly, which raises
  when two events on one date hold different types under the same key.

### Changed
- `meta.contract` is **2**. Existing repos need no migration: `vitai build`
  creates the new files and tables, and a repo with no goals simply has empty
  ones. See the migration table in the README.
- The demo athlete now carries the goal story: a monotonic steps goal (raised
  once, mid-block), a guarded running goal, an external segment goal, a
  missed travel week, and a floor loosened three days later - which the churn
  flag catches.

## [0.2.3] - 2026-07-28

Foundations F3 - temporal foundations (G30).

### Fixed
- **Rolling windows are calendar-day, not entry-count.** A "7d avg" now
  averages values within the last 7 CALENDAR days, and the weight-rate line
  compares two calendar-separated windows - not the last N list entries.
  Under irregular logging the old behavior silently mis-scoped every "the
  trend, not a single point" number (a "7d avg" could span three weeks).
  Regression tests included.

### Added / doctrine
- The **day-boundary rule** is now written doctrine (event's local day at the
  moment it happened; effective-dated for relocations). The timezone/offset
  FIELD is deferred to increment 2, where `start_time` gives it a consumer -
  a date-only daily summary has no timezone ambiguity.

## [0.2.2] - 2026-07-28

Foundations F0 - in-repo demo athlete + CI demo job (see PR #4).

## [0.2.1] - 2026-07-28

Foundations F1+F2 from the restructured v3 plan - the robustness the feature
increments depend on, shipped before them.

### Fixed
- **Schema-evolution robustness (G25)** - the code-verified critical bug: an
  additive nullable field no longer invalidates lines written before it
  existed. Per-line schema generation (`_gen`, default 1); a key is required
  only if its introduction generation is <= the line's generation. Shape-
  history-stability regression test included.
- **Ingestion/build integrity (G26)** - one malformed line no longer aborts
  the whole build. `read_lines` returns (good rows, errors) and never raises
  on a bad line; `build` quarantines and reports, proceeding from the good
  rows; `validate` reports every malformed line, not just the first. `vitai
  init` writes a `.gitattributes` pinning LF on the append-only JSONL.

### Added
- `jsonl.load_report` (records + quarantined-parse errors); `schema`
  generation helpers (`key_generation`, `line_generation`).

## [0.2.0] - 2026-07-28

### Added
- **Platform surface**: `vitai.api.Vitai(root)` library class (typed reads,
  `verdicts()`, `rollup()`, `build()`); the read model is now a versioned
  contract (`meta.contract`) with a new `verdicts` table (week, metric,
  value, target, verdict) - the deterministic weekly goal-attainment rows a
  game economy or dashboard consumes. `vitai verdicts` emits them as JSONL.
- **Third data tier - inferred knowledge**: `data/inferences.jsonl`
  (kind/statement/confidence/model/evidence, schema-validated, append-only,
  supersedes-capable), projected into the read model, never read by the
  number path.
- **`vitai infer`** (opt-in via `[inference]` in vitai.toml): pluggable
  model backends - `claude-cli` (your authenticated Claude Code CLI) and
  `openai-compatible` (Ollama, llama.cpp, LiteLLM, hosted) - with strict
  parse-and-validate (invalid lines rejected, never repaired) and
  `--dry-run`.
- ARCHITECTURE: "The platform" section - single-user store as the atom,
  multi-user as horizontal per-user stores (scaling, GDPR blast radius,
  aggregate-verdicts-not-records rationale).

### Changed
- `vitai build` now also projects verdicts into the read model.

## [0.1.0] - 2026-07-28

### Added
- Deterministic engine: append-only JSONL with `supersedes` resolution,
  health-domain schemas (weight/daily/sessions) with a practical validator,
  SQLite read model rebuilt from zero, weekly rollup with rate verdict and
  configurable tripwires (`vitai.toml`).
- CLI: `vitai init | build | validate | status`.
- Skills (Claude Code compatible): `vitai-onboard`, `vitai-coach`,
  `vitai-ingest`, `vitai-redteam`.
- Content-repo templates stamped by `vitai init`.
- Connector doctrine (`connectors/README.md`): LLM-mediated first, API-first
  code connectors only once a record has proven durable.
- Brand v1 (`assets/`): v-pulse mark, wordmark/lockup (outlined Outfit),
  dark-mode + mono variants, social card, BRAND.md incl. verbal identity.
- Research dossier (`docs/prior-art.md`): 7-angle prior-art sweep with
  uniqueness verdict.
- Community + scrutiny scaffolding: CONTRIBUTING, SECURITY (threat model +
  not-a-medical-device), Contributor Covenant 3.0, issue forms, PR template,
  dependabot, SHA-pinned CI (hygiene gate incl. hash-based personal-content
  gate + Linux/Windows test matrix), gated PyPI Trusted Publishing release
  workflow, Quartz v4 docs site source.
