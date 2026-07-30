# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

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