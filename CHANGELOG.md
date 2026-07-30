# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

Safety layer: the persona guardrail fixtures now hold (issue #12). All eight
`xfail(strict=True)` specifications flip to passing.

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