# Issue dispositions for #167 #168 #169 #170 #171

Sequencing (breaks the undeclared #167/#168/#171 cycle, stated once here and
in every rewritten body):

```
NEW ISSUE (regimes + protocol + detector: no dependencies, shippable first)
phase 0 (no dependencies)  ->  #169 (row/activity identity primitive)
                           ->  #170 (derived_from, needs identity)
                           ->  #168 (qualifications, needs identity)
                           ->  #167 (lands together with #168)
                           ->  #171 (capability dataset, gated on phase 0 outcome)
```

The new issue (section below, post FIRST) is deliberately independent of the
identity work: a regime scopes (dataset, field, interval), not claim ids.

The #73 conflict, resolved explicitly: #73 (closed) was about a MISSING source
stamp inverting the ladder; its tripwire `_unattributed_losses` keys on
`source == null`. #167 as rewritten is about an ATTRIBUTED testimony claim
losing to a measurement, which is the correct outcome and trips nothing. The
two rules key on different predicates; both stand. #167's rewrite says so, and
the tripwire keeps its current behaviour (regression-tested).

No personal data below: all examples are generic ("an athlete", "a session",
"a body-mass value", "roughly a week"). No figures, protocol specifics, dates
or body metrics in any body.

---

## NEW ISSUE: file first (no dependencies)

**Title:**

```
Honest sustained error is a regime, not an observation: correcting it must empty the interval, and must never cost the reporter trust
```

**Body:**

```
An athlete states a body-mass value, consistently, across roughly a week.
Then a measurement is taken under a fully specified protocol for the first
time, and it differs. No malice, no carelessness, no unreliable reporting:
the earlier statements were not bad measurements, they were statements about
an ill-defined measurand. The correction arrived the moment a protocol was
first applied.

The record has nowhere to put this, and every existing mechanism is the
wrong one:

- a per-observation qualification targets ONE suspect reading; this is a
  bounded INTERVAL over which a whole class of claims was unanchored,
  ending at a discoverable instant. Different granularity, different
  lifecycle.
- `supersedes` replaces a claim with a better one; here there is no better
  value for those days and never will be.
- doing nothing leaves a flat run of confident values that the record now
  knows were unanchored.

## What it proves

This interval is HIGH TRUST and LOW ACCURACY, sustained over time. A model
with one axis must either call the athlete unreliable (false) or call the
numbers fine (false). It is also the live case of definitional uncertainty
(VIM 2.27): "my mass is X" is not a well-defined measurand until time of
day, fasting state and clothing are fixed, and for body mass that
definitional term dominates instrument error. The protocol is what pins the
measurand down, which is why the correction arrived with the first
protocolled measurement and not with a better instrument.

## Proposal

**1. A `regimes` dataset.** A declared, bounded interval scoping (dataset,
field, optionally source), kind `unanchored`, with the athlete's own account
and what ended it. Boundaries are DECLARED first (the athlete usually knows
when the protocol started); statistical changepoint detection is a later,
optional audit.

**2. Invalidate WITHOUT replacing.** Claims inside the interval are labelled
superseded-by-regime (label, never deleted). The affected days resolve
EMPTY. The anchored measurement is evidence that the earlier claims were
unanchored, NOT evidence of what the true values were - backfilling the
interval from the anchor is the obvious wrong implementation and a test must
assert against it by name. A blank beats a confident wrong number, applied
to an interval rather than a point.

**3. Trust invariance, as a hard rule with a test.** Applying a regime must
not lower any trust, credibility or precedence parameter of the athlete or
any source. If discovering your own error costs you standing, the engine
punishes the act of improving the record, and people learn to stop
correcting their data. Trust is about intent and care; accuracy is about the
number; self-correction is evidence of care. Test: resolution output outside
the interval is byte-identical with and without the regime row.

**4. `protocol` as a first-class field** (SSN/SOSA `usedProcedure`). A row
that names its procedure is a different epistemic class from one that does
not - the bare row carries the measurand's full definitional uncertainty,
the protocolled row does not. Protocol identity participates in
comparability: a trend across a protocol change carries a seam flag, the
calibration-seam argument applied to protocol rather than instrument. This
extends the existing anchor concept (anchor quantity class, anchor-audit
loop): a protocolled measurement IS an anchor, and the span between anchors
is the unanchored interval.

**5. A cheap detector that would have caught it unprompted.** A quantity
known to fluctuate day to day, showing an exactly constant value across
days, is evidence of restatement rather than observation. Deterministic,
registry-parameterised (which fields must vary, by roughly how much),
ADVISORY only, naming the suspected regime boundaries. This is the existing
restatement concept given a second evidence route: the capture registry
ranks what the record SAYS about acquisition; this reads the same fact off
value shape when the record says nothing.

## Consequences downstream

Everything derived from an unanchored value inherits its problem - a body
mass feeding a vendor energy model unanchors a week of derived energy
figures. Declared lineage is sufficient to FLAG those stale; no
recomputation. That is the derivation-lineage issue's concrete trigger.

The same applies one level up, and it is the larger half: over the interval
the engine produced plans, warnings and attainment assessments that were
acted on. Emptying the input retracts the observation and leaves every
consequence standing. The consequence side (recompute forward-looking
outputs from the anchor; refuse backward-looking ones over the gap; audit
fired warnings) is a separate piece of work with its own prerequisite (the
engine remembering what it asserted), filed with the derivation-lineage
issue's cascade as its mechanism.

## Related

- per-observation qualifications (distinct: one reading vs an interval)
- derived-value lineage (the staleness cascade this triggers)
- instrument capability (this is the worked proof the two axes are separate)
- the calibration seam (comparability across protocol change)
```

---

## #167: REWRITE (title and body replaced)

Verified against the code before rewriting: the original's two central
mechanics claims are false. `resolution.py` ranks only claims carrying a
non-null value for the field (`witnesses = ... if rec.get(field) is not None`),
so demotion is already availability-conditional per field, and `sets` is
excluded from `RESOLVED_DATASETS`, so reps/RIR never enter this resolver. The
"silently deletes strength training" trap does not exist and `fallback_after`
buys nothing. What survives is real: when a narrative claim and a measurement
BOTH carry a value, a ladder that ranks the narrative source higher lets a
recollection beat an instrument (`meals.py` already documents and quarantines
exactly this hazard for kcal_in).

**New title:**

```
A testimony claim that competes with a measurement can win by source rank; make capture class a dominance layer in a partial-order resolution
```

**New body:**

```
## What is actually wrong (corrected from the earlier version of this issue)

Two mechanics claims in the previous text were wrong, verified in code:

- Ranking already happens only over claims that carry a value for the field,
  so "narrative wins when nothing measured the field" is ALREADY the
  behaviour. No fallback_after concept is needed.
- `sets` is not resolved by the precedence ladder at all, so no demotion can
  touch repetitions, RIR, or sets-to-failure. The "silently deletes strength
  training" trap does not exist.

What remains, and it is real: when a testimony claim (narrative,
manual entry) and a measurement-class claim (connector, export, BLE, photo)
BOTH state a value for one (date, field), the source ladder decides, and a
ladder that places a narrative source high lets a recollection displace an
instrument reading. The meals module already documents this exact hazard and
works around it by quarantine, which is evidence the rule belongs in the
resolver.

## The fix is two structural changes, not a conditional rank

A conditional rank ("this source ranks low when X is present") violates
independence of irrelevant alternatives: whether A beats B would depend on
whether C showed up, which makes the ordering untestable pairwise. Both
changes below are unconditional, pairwise, and context-free.

1. **The ladder becomes a partial order** (prioritized-repair semantics:
   Staworko, Chomicki, Marcinkowski 2012, DOI 10.1007/s10472-011-9241-8).
   Config states dominance EDGES between sources; absence of a path is "no
   opinion". Two consequences:
   - a conflict between sources nobody ordered resolves to a TIE: canonical
     value null, tripwire naming both claims. A refusal, not an alphabetical
     accident - which fits the engine's existing doctrine that a blank beats
     a confident wrong number.
   - this issue's rule needs no machinery for the empty case: with no
     measurement present, nothing dominates the testimony claim and it wins
     by default semantics.

2. **Capture class is a dominance layer above source edges.** Every capture
   registry entry gains a class: measurement (connector, file_export, ble,
   photo) or testimony (narrative, manual_entry). For one (date, field)
   contest, measurement class dominates testimony class regardless of source
   edges. Keyed on capture, not source names, so it holds for channels not
   yet built. Shipped precedent for the axis: Health Connect's
   recordingMethod enum (actively recorded / automatically recorded / manual
   entry / unknown) is exactly this split, with unknown first-class.

## The named failure this must not reproduce: presence is not quality

One incumbent training platform documents that any existing stream is used
"valid data or not" - so a garbage stream from an incompetent instrument
beats a clean stream by mere presence. "Measurement beats testimony" has the
same failure built in unless the measurement-class candidate set is filtered
for COMPETENCE first: a claim from an instrument that cannot measure the
field (a capability declaration, refining the existing kind-level deny list)
is excluded before availability is tested. Otherwise this issue upgrades
garbage to unbeatable.

## What this deliberately does not remove

The athlete must keep a way to say "distrust this one reading" without
supplying a competing number. That is a qualification (#168), which lands
together with this change: this issue removes the override-by-better-number
path, #168 provides the honest replacement. #168 in turn needs stable row
identity (#169). Order: #169, #170, #168, then this.

Relation to the closed unattributed-rows issue: that one keyed on a MISSING
source stamp (a writer omission inverting the ladder), and its tripwire keys
on source == null. An ATTRIBUTED testimony claim losing to a measurement is
the correct outcome and trips nothing. Different predicates; both rules stand.

## Tests

- one utterance, two fixtures, identical but for a device row on the same
  field and date: opposite winners, and the fallback win is visibly
  class-decided in the explanation.
- a testimony-only field with a device row present for a DIFFERENT field on
  the same date: testimony still wins its own field.
- a tie (no edge, no class difference) resolves to null plus a tripwire, and
  the output is identical under any permutation of input order.
- the unattributed-loss tripwire still fires for source == null and does not
  fire for an attributed testimony loss.

## Related

- #168 qualifications (lands together with this)
- #169 platform/channel and row identity (prerequisite of #168)
- #170 derived values (prerequisite ordering shared with #168)
- #171 instrument capability (separate axis; gated on its own phase-0 result)
```

---

## #168: KEEP, amend body (replace the "Open questions" and "Distinct from #33" sections; the rest stands)

The issue's core is correct and unchanged: interpretive vs doubt-casting,
annotate vs demote, demote is a label not a deletion. Amendments: (a) name the
axis, (b) resolve targeting via #169, (c) place the flagship example correctly.

**Replacement for the two closing sections:**

```
## Where this sits in the taxonomy

A qualification is a per-observation TRUST revision - believability of one
claim, in the Wang & Strong (1996) / ISO/IEC 25012 credibility sense. It is
not an accuracy statement: instrument capability (how precise a device
generation is, under which conditions) is standing, effective-dated data on
the instrument (#171). "I think the GPS misregistered on that one" is a
statement about ONE claim on one occasion, so it lives here, even though the
thing doubted is a measurement: the standing capability of the device is
unchanged by it. Both are needed and neither substitutes for the other.

Mechanically, a doubt-cast with effect: demote inserts a per-observation edge
into the partial-order resolution (#167): this one claim sorts below every
other witness for the scoped fields. The change is visible as a ranking
outcome, never a silent adjustment. Interpretive qualifications annotate and
change nothing computed - a headwind explains a slow pace and must not delete
the slow pace.

## Resolved design points

- Targeting: a qualification names claim ids (the stable identity #169
  introduces; the identity work is a prerequisite and is why this issue lands
  after it). Scope is a field list, null meaning the whole row - "the GPS was
  wrong" targets distance, not the heart rate recorded alongside it.
- A doubt-cast with no better witness available demotes to nothing: the field
  resolves null and says why. A blank beats a confident wrong number.
- Land together with #167: that issue removes override-by-competing-number,
  this one provides the replacement.

## Shipped precedent for the correction shape

Strava's disputed-distance flow never accepts a typed replacement figure: it
TOGGLES between two retained, named derivations, and the figure cannot be
hand-edited. That is this issue's demote-not-replace semantics already in
production: the athlete's doubt selects among derivations the record can
defend, it never injects a number the record cannot. Per-metric granularity
has a precedent too: intervals.icu lets one metric of one activity be
ignored without touching the rest, which is exactly field-scoped targeting.
```

---

## #169: KEEP, amend (append two sections; existing body stands)

**Append:**

```
## Two further cuts through the same seam (added after review)

**Functional vs referral trust** (Josang/Gray/Kinateder 2006). Trusting a
platform to RELAY a file faithfully is a different judgement from trusting it
to ESTIMATE a quantity. One platform can be excellent at the first and poor
at the second, and a single ladder position cannot say so. The
(platform, channel) split carries exactly this: channel fidelity is the
relay-trust axis (original_files > summary_api > derived), while estimate
quality belongs to the instrument capability data (#171). The flat ladder
conflates them.

**Relay evidence from formatting** (Dong, Berti-Equille, Srivastava 2010,
DOI 10.14778/1920841.1921008). Two channels sharing improbable formatting -
the same preserved rounding, the same decimal string beyond plausible
independent rounding - is deterministic, cheap evidence of relaying rather
than corroboration. A string comparison, flagged for review, never a merge
decision on its own. This catches same-platform-twice arrivals even before
activity identity is solved.

## Sequencing note (added)

The activity/row identity primitive in this issue is the first work item of
the whole cluster: #170 (naming input rows) and #168 (targeting an
observation) both converge on it, as the earlier text of those issues already
observed. Identity lands in the engine as a primitive every importer
inherits, not per-importer heuristics.
```

---

## #170: REWRITE the Proposal and Open questions sections (problem statement stands)

**Replacement from "## Proposal" down:**

```
## Proposal

A derived value names its inputs as a LIST, following FHIR
Observation.derivedFrom (cardinality 0..*), not a binary derivation link:

- derived_from: a list of claim ids (the identity primitive from #169)
- derived_op: a short declared operation ("sum", "same-route-reversed")
- capture: derived_external - a new registry entry meaning "computed outside
  the engine from named rows in this record", distinct from derived
  ("computed by this engine"). Same operation, different actor, and the
  registry already carries exactly this kind of distinction.

Consequences wired into resolution:

- a value never corroborates any claim in its own ancestor closure
  (agreement by construction is not evidence - the corroboration rule one
  level up from origins);
- a superseded or retracted input flags every dependant with a
  stale_derivation tripwire, reusing the existing retraction cascade shape.
  The concrete trigger already exists: when an interval of body-mass claims
  is discovered to have been unanchored (see the regimes issue), every value
  derived from it - not least vendor energy figures that took the mass as a
  profile parameter - inherits the problem, and only named inputs let the
  record find them. That profile parameter is also the standard shared-
  influence case: one input feeding many derived values must be an explicit
  named node, or their errors are correlated invisibly.

## Design points, resolved

- **Declared, not re-executable.** Provenance theory (Green, Karvounarakis,
  Tannen 2007, DOI 10.1145/1265530.1265535) separates lineage (which inputs)
  from the operation semantics: declared lineage is sufficient for staleness
  DETECTION, which is the case that bites. Re-execution would only buy drift
  CORRECTION, which the engine's own doctrine discourages (flag, never
  auto-fix). Not built.
- **A derived value never outranks its surviving inputs** for the fields they
  cover: it is dominated by them in the partial order (#167), the same way
  testimony is dominated by measurement. When its inputs are absent for a
  field, it wins by default semantics - better than a recollection, worse
  than an observation, exactly as the problem statement put it.
- **Row identity** comes from #169 and is a prerequisite; this issue lands
  immediately after it.

## Blast radius, restated upward

As filed, this issue is about a VALUE derived from other rows. The real
extent is a level higher: verdicts, plans, warnings and required-rate
calculations are all values derived from the whole record, and a retraction
of their inputs currently stops at the input. The staleness cascade
proposed here is therefore the mechanism for a much larger consumer than
the one that motivated it - the engine's own assertions - which needs one
additional piece this issue does not provide: a durable memory of what was
asserted and when (today verdicts are rebuilt and overwritten, so there is
nothing to mark stale). That memory, the forward/backward recompute-or-
refuse split, and the audit of already-fired warnings are specced as the
consequence side of the regimes issue and depend on this issue's lineage
machinery plus policy-as-of reconstruction (#148).
```

---

## #171: REWRITE (title and body replaced)

Corrections baked in: the root-cause claim is dropped (the issue's own text
said the payoff is not resolution ordering, F8); "accuracy is a stable lookup"
is dropped (it contradicted the issue's own condition-dependence section, F3,
and an undated lookup violates the record's no-current-state rule; the
capability data is effective-dated); no float named accuracy (not a quantity,
VIM 2.13); trust/accuracy separation is 30-year-old prior art, cited not
claimed; the per-edge composition section is reduced to what survives F7.

**New title:**

```
Instrument capability is a missing dataset: standard uncertainty with its own provenance, condition-scoped and effective-dated
```

**New body:**

```
## The claim, corrected from the earlier version

The precedence ladder orders sources by a judgement that mixes believability
with instrument quality. Separating those is not a discovery of this project:
Believability and Accuracy are co-equal dimensions in Wang & Strong (1996),
ISO/IEC 25012 splits Credibility from Accuracy, and W3C DQV carries
Trustworthiness as its own dimension. What this record lacks is the
instrument half: nothing states what a device generation can resolve, under
which conditions, with what systematic offset.

The record has since supplied its own proof that the axes are separate. An
athlete honestly restated a body-mass value across roughly a week; the first
measurement under a specified protocol differed. That interval is high trust
and low accuracy, sustained: a one-axis model must either call the athlete
unreliable (false) or call the numbers fine (false). The interval mechanics
live in the regimes issue; what belongs HERE is the lesson that the dominant
error term was definitional (the measurand was ill-defined until a protocol
fixed it), not instrumental - so a capability model that only prices
instrument noise misses the term that mattered most.

Two earlier claims are withdrawn. This is not "the root cause" of the
testimony-vs-measurement issue - that one is fixed structurally in the
resolver and does not need this data. And instrument capability is not a
"stable lookup reused for years": it is conditional on field and circumstance
and it changes (firmware, recalibration, wear), so it is effective-dated data
like every other dated thing in this record.

## Vocabulary: use the standards' names

"Accuracy" is not a quantity (VIM 2.13 note 1; GUM B.2.14), so no field is
ever named accuracy. The decomposition already has standardised names, taken
from W3C SSN/SOSA ssn-system where they exist:

- standard uncertainty u (GUM), with the Type A / Type B evaluation route
  stated, and stated-as (expanded k=2, 95 % CI, symmetric limits, display
  step) converted by one canonicaliser;
- the specified condition of a precision figure (repeatability /
  intermediate / reproducibility - VIM 2.15 note 2: precision is
  meaningless without it);
- bias, the numeric estimate of trueness (VIM 2.18; ssn-system has no term
  for it). A known bias is corrected, not absorbed into a widened u
  (GUM 6.3.1) - in this engine "corrected" means DECLARED and rendered as an
  offset and a seam, never silently applied, per the no-fabrication rule;
- resolution as a display step contributing u = 0.29 * step, a source of
  uncertainty rather than a sibling of it;
- Condition scoping (ssn SystemCapability qualified by Condition): a
  capability row may state the circumstance it holds under (open sky,
  indoor, treadmill), because one scalar applied to all circumstances is a
  confident wrong number about confidence;
- definitional uncertainty (VIM 2.27): the floor set by how loosely the
  measurand is specified. For body mass this term (time of day, clothing,
  fasting state) plausibly dominates instrument noise, and the engine
  already carries its diurnal component as a code constant - the capability
  data makes it declarable instead of hardcoded.

## Numbers only where this record measured them itself

The survey of what vendors actually publish kills a numeric import outright:
essentially only power meters publish figures, those cover the random term
only, field observation contradicts them by margins up to twenty percent,
one vendor's marketed tolerance is half its own service tolerance, and major
sources publish nothing and expose no per-reading quality flag. A borrowed
figure would be a confident wrong number about confidence - this issue's own
warning, applied to itself.

So the capability data is primarily CATEGORICAL: instrument identity, a
competence state (measures / proxy / absent / unknown - zero, unknown and
wide are three different things and only one is a quantity), and a
comparability class between instruments that is EARNED BY OVERLAP
(simultaneous dual recording, the established norm in the power-meter
community) and never asserted. Numeric standard uncertainty enters the
engine only from the record's own replicates or its own overlap windows;
borrowed literature figures may be archived as annotations with their basis
stated, and are never canonicalised into arithmetic. The one
accuracy-adjacent quantity always computable honestly is COVERAGE (how much
of the period the instrument was actually observing), and it is prioritised
over any imported figure.

## The third failure mode neither axis covers: construct validity

A working instrument, honestly relayed, can still measure a DIFFERENT
CONSTRUCT than the field name claims. A live example class: a vendor's
resting-heart-rate figure that is a proxy statistic, observed running far
above the continuous nightly minimum - by more than any instrument error in
the validation literature. No uncertainty figure, no bias term, no
confidence interval and no trust parameter would ever catch it, because
every one of them assumes the right quantity is being measured. So the
capability data carries a construct statement: a `proxy` competence requires
naming what is actually measured, and two sources reporting one field name
with different constructs are not comparable regardless of their precision.
Its main defence over time is recording the vendor algorithm version per
row: a construct can be silently changed by a firmware update, and without
the version string an algorithm change is indistinguishable from a
physiological one.

## Where the payoff is

Verdict honesty, and it is gated on measurement: before any of this data is
collected, the engine can compute - from the record's own repeated measures -
whether the ratio of measurement dispersion to each verdict's decision band
even permits single-period verdicts. If dispersion dominates the band, the
fix is the decision unit (longer windows, guard-banded refusal), and no
registry rescues it; if the ratio is workable, capability rows supply the
uncertainty for sources too sparse for a Type A estimate. Run the
computation first; build only what its outcome justifies.

The refusal itself has a shipped commercial precedent: a major wearable's
scoring exposes scored / pending / unscorable states, where the refusal
carries a reason and the value is absent from the scored payload rather than
present with a warning. Both choices are right and both are copied at the
verdict layer: a dimmed number still gets read and screenshotted, and a
reason is what makes a refusal actionable instead of mute.

Second payoff, unconditional: a declared bias plus a device change makes a
cross-instrument step renderable as what it is - possibly a calibration
seam - instead of a trend, which is the seam issue's core problem. The bias
term is the one signal processing cannot fix: it is permanent, it does not
average out over any window, and smoothing across a seam launders it into a
plausible trend. Seam machinery therefore ships alongside trend filtering,
never instead of it.

## What travels along the chain

Hop-by-hop error modelling is dropped: recorded hops are platform relays
(the fusion that reduces error happens inside the device, below the origin,
on edges the record never sees), and where two witnesses of unestablished
independence are combined, the conservative rule already adopted for
corroboration applies - combined confidence never exceeds the best single
input (covariance-intersection posture). What a low-trust hop does to a
value is widen its uncertainty, never flip or demote it (the discounting
shape from subjective logic); the existing ordinal trust ceiling stays until
a per-hop figure worth using exists.

## Non-goals

- No float named accuracy, ever.
- No imported numeric error parameters: borrowed population figures never
  enter arithmetic (annotation only). Own replicates and own overlap windows
  are the only numeric routes.
- No trust learning: believability stays declared (dominance edges,
  per-observation qualifications). Reliability-estimation methods need many
  conflicting values per item to beat random guessing, and this record's
  dominant case is single-source fields.
- No re-derivation of the resolution order from capability numbers: ordering
  stays the athlete's declared judgement; capability data feeds verdicts,
  seams and rendering.
- No silent blending: one incumbent blends its own re-derivation with the
  device figure past an undocumented threshold and presents the result as a
  pure device figure. Any combination this engine ever performs is labelled
  as one.

## Related

- #33 the calibration seam (bias + device change is its machinery)
- #94 corroboration and the never-overconfident combination rule
- #168 per-observation doubt (the trust axis, kept separate)
- #169 channel fidelity vs estimate quality (functional vs referral trust)
- #170 derived values (uncertainty of a derived value needs named inputs)
- the regimes issue (the worked proof of the axis split; definitional
  uncertainty as the dominant term for body mass)
```

---

## #148: PROMOTE from known defect to prerequisite (comment to post)

Not in the original scope of this pass; promoted because the retraction
cascade cannot exist without it. Comment text, ready to paste:

```
Promoting this from a known defect to a PREREQUISITE of the retraction
cascade (the consequence side of the regimes proposal).

`as_of` currently reconstructs past DATA under today's policy. To answer
"what did the engine actually tell the athlete, and does it still hold",
data-as-of is not enough: a faithful data reconstruction under today's
thresholds produces a verdict the engine never issued. Retraction auditing
replays past assertions, so it needs POLICY-as-of - the thresholds, config
overlay values, resolution ordering and registry state in force at the
assertion's date.

Partial precedent already in the engine: weekly verdicts are judged against
the thresholds in force on their Monday (G14/G20), so goals and thresholds
are already policy-as-of. The gap is everything outside those two datasets:
config file values, resolution precedence, and registries (the G31
effective-dating territory).

Concretely required by the cascade: each recorded assertion carries the
policy date it was computed under, and this issue makes that date
replayable. Until it lands, the assertion log can record but not verify.
```

---

## Cross-check list before posting

- [ ] No figures, dates, names, places from any private record in any body.
- [ ] ASCII only; no double-hyphen separator.
- [ ] #167 and #171 bodies explicitly note which earlier claims were wrong
      (public correction, matching the repo's practice of documenting its own
      mistakes).
- [ ] The new regimes issue carries no figures, no protocol specifics, no
      dates, no body metrics ("an athlete", "a body-mass value", "roughly a
      week") - checked word by word before posting.
- [ ] Post order: NEW regimes issue first, then edit #169 and #170
      (prerequisites), then #168, then #167, then #171, so no issue ever
      references a not-yet-corrected body.
