# Cross-metric inference & knowledge extraction (G22)

How vitai relates ONE metric to another - sleep to performance, weight to
pace, HR to calories, context to adherence - without manufacturing false
insight from one person's sparse, autocorrelated, confounded data. Design +
a researched evidence base (sport-science lookup + adversarial review,
2026-07-28). The governing fear, from the redteam: an engine that mines
metric pairs nightly will surface dozens of spurious "insights" a month by
chance, and an LLM that narrates them causally ("your bad run was the wine")
does real harm. Everything here exists to prevent that.

## The three-tier trust taxonomy (the core distinction)

A cross-metric relationship is exactly ONE of:

1. **DETERMINISTIC** - established physiology with a known formula. Encoded
   as registry math, computed directly, may state mechanism. The only tier
   allowed causal language. Examples: HR->kcal estimation (and its
   documented failure modes), threshold tripwires (elevated resting HR +
   short sleep -> a fatigue *monitoring flag*, which asserts a trigger, not
   a cause).
2. **HEDGED HYPOTHESIS** - plausible, real in the literature, but confounded
   by the fitness/time trend and daily context in n-of-1 data. Surfaced
   only as "for you, so far, under conditions X", with confounders named,
   NEVER graduated to asserted fact even after backtesting. Examples:
   sleep->performance, circadian->energy, weight->pace, adherence->context.
3. **STRUCTURALLY EXCLUDED** - single-incident causal narration. One bad day
   has dozens of uncontrolled co-factors; naming one is banned. Never
   reaches even hypothesis-with-confidence status. "The wine caused the bad
   run" is not a low-confidence claim - it is *no* claim.

The failure the taxonomy prevents is **confidence laundering**: a pattern
mined as tier-2 must never read as tier-1 fact once it sits in the registry.
The hedge is re-asserted at every coach utterance that cites it.

## The four inference shapes (your examples, typed)

- **Lagged causal-hypothesis** (sleep->next-day performance;
  circadian->energy): X earlier may affect Y later. Tier 2. The engine
  computes the lagged relationship deterministically with the statistical
  guards below; the coach offers it hedged, confounders named.
- **Leaky-model contradiction** (a lower-HR run burned MORE kcal): the naive
  model (HR->kcal) is being violated - and because the physiology is KNOWN
  (tier 1), the valuable output is deterministic: "your HR->kcal assumption
  leaked here; the likely confounder is duration / body mass / heat / device
  algorithm / cardiac drift." Not a mystery, an explained decoupling.
- **Expectation-vs-actual** (lost 2kg, pace didn't improve): a tier-1/2
  PREDICTION (G21 weight->pace model) that didn't materialize. First-class
  signal, not disappointment: route to the candidate explanations (water not
  fat lost, muscle loss, deficit fatigue, near the body-fat floor, or
  just noise over too short a window) - never assert the formula "failed".
- **Behavioral-contextual** (only 3 sessions in 2 weeks / busy work): link an
  adherence dip to life context. Tier 2, and the never-shame case - a
  context-driven dip gets a target auto-adjustment and neutral
  acknowledgment, NOT a broken-streak alert.

## The statistical guards (non-negotiable, deterministic)

From the n-of-1 methodology research + redteam - these run BEFORE any
confidence is attached to a mined pair:

- **Detrend first.** Difference/detrend both series before correlating; a
  training-block drift makes almost any pair (RHR down, weight down, pace up)
  correlate spuriously. A pattern that vanishes after detrending is
  discarded, not downgraded.
- **Effective-N, not calendar-N.** Daily self-tracked series are
  autocorrelated; correct the effective sample size
  (`n_eff = n*(1-r1x*r1y)/(1+r1x*r1y)`, or ARIMA-prewhiten) before any
  p-value. Many data points is NOT many independent observations.
- **Multiple-comparisons discipline.** Across the metric-pair x lag search
  grid, apply FDR (Benjamini-Hochberg) OR a hard nightly pattern-proposal
  budget with a pre-registered short list of hypothesized pairs. Never report
  the single largest correlation found among all pairs scanned.
- **A-priori lag from mechanism.** Lags come from a hypothesized mechanism
  (sleep leads performance; load leads adherence-drop - per Kinnunen), not
  scanned post-hoc and reported as "the best lag".
- **Change-point segmentation.** Segment regimes (PELT/CUSUM/Bayesian
  online) before correlating; a fixed model across a non-stationary history
  misrepresents every period.
- **Missingness is not random.** People skip logging on bad days and log
  obsessively after a bad outcome; a stated minimum-coverage + interpolation
  policy is required, because silent gap-filling is itself a forking-path.
- **Backtest must be out-of-sample.** Graduation to the registry requires a
  held-out temporal backtest on data unseen during mining - never a refit on
  the history that discovered the pattern (circular validation).

## The causal-language firewall (coach + inference tier)

- Outside tier 1, the word "causes" is banned. Patterns carry
  direction: hypothesized/unknown, evidence, and confidence - never "your
  body does X".
- Single-incident narration is structurally disallowed: a bad day
  ENUMERATES candidate co-factors, never names one culprit.
- Hard n-of-1 ceiling: no pattern, however well backtested, is worded
  stronger than "for you, so far, under conditions X".
- Medical topics are excluded from inference entirely - cross-metric
  fatigue/HR/energy patterns must not drift into thyroid/cardiac/hormonal
  diagnosis-adjacent claims. They get no causal claim and no interpretation;
  the engine's fixed text is the only output.
- Never-moralise at the generation layer: "you drank wine, that's why you
  failed" reads as judgment of a choice - banned even when statistically
  weak.

## Knowledge extraction (the graduation pipeline)

Reuses the claims-into-truth shape of the whole system:
`vitai infer` proposes a cross-metric pattern (with evidence + the guards'
outputs) -> the pattern is a tier-2 hedged hypothesis, surfaced flagged ->
if it survives an out-of-sample temporal backtest it graduates into the
curated registry (`semantics/` for interpretation, `models/` for any
formula) - STILL tier-2-hedged for confounded relationships - and the coach
cites it with the hedge re-asserted. Only established physiology (tier 1)
enters the registry as asserted fact, and that comes from literature, not
mining.

## Evidence base (researched priors - population averages, NOT personal facts)

Curated 2026-07-28 as seed registry content. Every number below is a
GROUP-level prior from controlled studies; applying it to one person is an
extrapolation the coach must hedge.

### sleep -> performance (tier 2)
- Domain-specific decrements after acute sleep loss (pooled SMD / approx %):
  skill/complex-motor ~-0.87 / -21% (largest); aerobic endurance ~-0.55 to
  -0.76 / -5.5%; explosive power/anaerobic ~-0.63 / -6%; speed ~-0.52 / -3%;
  max strength ~-0.24 to -0.35 / -3% (smallest); RPE +0.39 (rises even when
  output holds - the earliest signal). A blanket "sleep hurt today" is
  wrong-grained; scope to the session TYPE performed.
- Effect-modifier gate: acute effects concentrate in PM sessions after
  late-restriction/deprivation; early-restriction is near-null except
  endurance/skill. Condition on session time-of-day.
- Model sleep as a rolling 3-7 day debt/EWMA vs personal baseline, not a
  single last-night scalar - one good night doesn't clear a week's debt.
- Injury-risk OR ~1.3-1.6 for <7-8h. Wearable sleep scores are noisy inputs,
  not ground truth. Reverse causation live (hard session -> bad sleep).

### circadian -> energy (mostly tier-1 NULL - important)
- In-session exercise energy expenditure is ~constant across time of day for
  a matched protocol: **do NOT adjust a session's kcal for clock time.** RMR
  has a trivial circadian amplitude (~28 kcal/day). So "late-night burned
  less" is almost certainly device kcal-estimate noise (+/-20-30%) or
  accumulated-fatigue/lower-output, NOT a metabolic-rate change - a
  leaky-model explanation, not a circadian one.
- Real tier-2 handle: evening exercisers show higher downstream
  appetite/NEAT (~80-250 kcal/day) - a nutrition-coaching flag, not an
  in-session correction. Performance capacity does cosinor-track core temp
  (peak ~16-18h) but gate it behind chronotype, not raw clock.

### HR -> kcal (tier 1 - encode the physiology AND its failure modes)
- MET formula: `kcal/min = METs x 3.5 x kg / 200` (ignores fitness/grade/load).
  HR-regression (Keytel-style) is what watches use; error grows for the very
  fit/unfit, in heat, or with cardiac drift.
- Device EE error is large (median 27-93% across devices; Stanford n=60)
  while HR error is small (2-7%) - the input is measured well, the OUTPUT is
  estimated badly. A device kcal readout is NOT ground truth.
- Why lower HR can burn more: duration (total = rate x minutes; the long
  slow run wins on volume), body mass, hills/load, EPOC/anaerobic
  contribution, and - crucially - cardiac drift (+10-15 bpm steady, +20-30
  in heat) and PPG sensor error INFLATE HR without more work. Deterministic
  flag: mark a kcal estimate low-confidence once HR drifts >X bpm from the
  first-10-min baseline at matched pace/power.

### weight -> pace (tier 2)
- Heuristic ceiling: `delta_pace_% ~= delta_mass_kg / mass_kg` (2kg on 70kg
  ~2.9%); anchor ~1.2-1.5 s/km per kg (Daniels). Treat as a ceiling, apply
  diminishing returns past 2-3kg, and normalize by % bodyweight not absolute
  kg.
- Only credit it when fat-loss is plausible AND rate <=~0.5-1%/week; else
  low-confidence (deep-deficit zone). Reverses near the body-fat floor
  (~10-12% men / 18-22% women).
- Expectation-vs-actual: if the predicted gain isn't seen in 2-4 weeks, route
  to candidates (water/glycogen not fat, muscle loss, fatigue, noise) -
  never assert failure from one comparison.

### adherence -> context (tier 2, never-shame)
- Operationalize external load as a COMPOSITE (calendar-busy-hours +
  travel-days + caregiving/on-call flag + stress/sleep-debt), correlate its
  7/14-day rolling delta against session-frequency at a 1-tick lag (load
  LEADS the drop - Kinnunen).
- Classify the PATTERN, and never the person (G90). Two shapes, and the
  arithmetic is unchanged: a LOAD-COINCIDENT dip is load-composite rising +
  frequency drop coincident/lagging + enjoyment/intent NOT declining; a
  LOAD-INDEPENDENT dip is frequency falling without a load rise, or preceding
  it, or enjoyment falling with it. Use the person's OWN load-vs-adherence
  history, not population thresholds.
  These names describe frequency and load, which is all the record holds.
  The earlier wording called the second one a "motivation dip", and that
  single word was the whole violation: it concludes a psychological state from
  a training pattern, with no anchor in anything he said and no way for him to
  show it wrong. Compute the shape freely; do not name the state. Where that
  reading is worth having, PROPOSE it (G38) and let him accept or decline -
  only the accepted version becomes a declared state, and a decline is
  permanent (G82).
- Response ladder (Marlatt lapse-vs-relapse): one context-driven period ->
  auto-adjust to a reduced-dose maintenance target + neutral acknowledgment,
  NOT a broken-streak alert; sustained -> renegotiate the plan; only a flat
  load with falling frequency -> a values/goal check-in. For a FATIGUE-driven
  dip, target recovery, not more volume ("push harder" is the wrong response
  exactly when it's most tempting).
- Confounders: illness/injury looks identical in raw frequency; planned vs
  unplanned busyness carry opposite valence; reverse causation (packing the
  calendar to avoid training); self-serving attribution in user "busy" tags -
  corroborate against actual calendar density, don't just trust the tag.

## Vendor insights as second opinions (G23)

The dedicated apps already run their own science: Garmin/Firstbeat VO2max
and Training Load, WHOOP recovery/strain, Oura readiness, MFP/MacroFactor
adaptive TDEE, Strava Relative Effort and fitness/freshness, Runna and
Garmin race predictors. These are worth ingesting - but as a distinct class:
**foreign-model estimates** (principle 6, class 3), another vendor's model
over their data, tagged `derived + source + model-opaque`. Never an
observation, never an anchor.

Three legitimate uses:

- **Corroborate**: a vendor estimate agreeing with vitai's own derivation
  raises confidence - it becomes an ensemble member in forecasting (G21),
  weighted by its own backtested accuracy like any model.
- **Challenge**: disagreement is a flagged signal worth explaining - a
  WHOOP recovery cratering while vitai's own signals look fine is a
  hypothesis to surface, not noise to discard.
- **Backfill**: where vitai has no model yet, a vendor estimate is a hedged
  stand-in, clearly marked as the vendor's opinion, not vitai's finding.

The critical eye is the same one this whole document argues for: vendor
models are black boxes with their own documented errors (device EE 27-93%;
VO2max estimates noisy; recovery-score efficacy mostly vendor marketing).
So a vendor insight is a CLAIM audited by the anchors (principle 6) and
arbitrated by vitai's transparent, resolved SSoT - which wins on
disagreement precisely because it is auditable and the vendor is not.
Conservation (G15) applies: a vendor's kcal or load is a competing claim
about the same physical quantity, resolved by precedence, never summed with
vitai's own, and a vendor estimate may never masquerade as the anchor that
is supposed to audit it.

## Sources

Sport-science lookup (meta-analyses/reviews preferred) + adversarial design
review, 7-agent workflow 2026-07-28. Key anchors: sleep-performance
meta-analyses (PMC9584849, PMC11996801); HR/kcal device-accuracy validation
(Stanford PMC5491979); circadian RMR/performance cosinor literature; Daniels
running-economy per-kg heuristics; Kinnunen workload-vs-PA and Marlatt
relapse-prevention models; n-of-1 / single-subject methodology (TLCCF,
effective-N, FDR, change-point, Granger). Full per-agent findings in the
run journal; numbers are population priors, hedged for personal use.
