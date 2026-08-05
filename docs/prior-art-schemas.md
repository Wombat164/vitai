# Prior art: schemas we could conform to (August 2026)

Input to #261 (IEEE 1752.1 conformance) and #260 (the connector contract).
This is the survey of **which published schemas are worth adhering to**, across
the areas this engine actually models: health measures, activity, events and
calendars, plans and goals, units, provenance, and prediction.

The question is not "what exists". It is narrower and it is the operator's:
**still maintained, widely used, well described.** A dead schema is worse than
no schema, because conforming to it spends the same effort and buys none of the
interoperability that was the whole point.

## Method, so the numbers can be rechecked

Registry APIs rather than a search engine, on 2026-08-05:

- npm registry search for weekly download counts and last publish date.
- PyPI JSON API for latest version and upload date.
- GitHub API on the canonical **specification** repositories, not their
  client libraries, because a busy client library around a frozen spec is a
  misleading signal and the two are constantly confused.
- The IEEE GitLab API directly. Note that `opensource.ieee.org` answers a
  default user agent with HTTP 418; pass a browser UA.

Download counts measure the ecosystem around a standard, not the standard.
They are used here only to separate "people build on this" from "a spec nobody
implements", which is a real distinction and the one that decides whether
conforming buys anything.

### Two standing caveats on how to read this document

**Absence claims stale fastest.** Several verdicts here are "nothing adoptable
exists" (prediction intervals, drifting mass, a logged-meal schema). That is
the claim type most likely to be quietly wrong later, and one of them was
already too strong in the first draft. **Re-verify any absence claim before
building on it if the date at the top of this document is more than about a
year old.** The engine's own rule applies: never assert how long something
lasts, assert when the record stopped knowing.

**This document is descriptive and unchecked, and that is deliberate.** #263
sets the rule that no descriptive schema ships without a derivation or a check.
A survey is upstream of every artefact that rule governs: its verdicts become
issues, and the obligation attaches there. So this file will drift, and it is
not the place to enforce against. Do not cite it as standing authority; cite
the issue that took the decision.

## The three-line verdict

1. **IEEE 1752.1 for the framing and for what it defines.** Already decided in
   #261. This survey adds evidence that it is live, and finds a part of it the
   earlier analysis missed.
2. **FHIR for vocabularies and for mapping outward**, never as our model.
   Specifically its goal vocabularies, which we independently arrived at, and
   its shape for predictions, which **confirms** a design we had already
   reached rather than supplying one. #196 shipped the contract, surface,
   clocks and `basis_claims` quartet before this survey existed.
3. **Nothing for prediction intervals specifically.** Both bodies offer bare
   low/high pairs that cannot say what kind of interval they are. Measurement
   uncertainty is better served than the first draft of this document claimed:
   W3C SSN's System Capabilities module is real prior art for #171.

## Health measures and metadata

### IEEE 1752.1: live, and larger than we thought

| | |
|---|---|
| Where | `opensource.ieee.org/omh/1752`, schemas resolvable via `w3id.org/ieee/ieee-1752-schema/` |
| Last activity | 2026-08-03 |
| Substantive commits | 2026-03-19 and 2026-05-04, both on the survey schemas |
| Size | 45 schema files (47 paths under `schemas/`, two of which are READMEs), JSON Schema draft-07 |

Two corrections to the earlier analysis in #261, both of which change what
conformance is worth.

**`omh/1752-2` currently holds no second standard, but a second standard
exists.** The repository is a byte-identical mirror: same 158 blobs with the
same blob SHAs, same head commit, same commit list, and it is not a GitLab fork
object. The published standard is still 1752.1-2021.

**IEEE P1752.2 is nonetheless a real and active working-group project**,
chartered for the representation of *cardiovascular, respiratory and metabolic*
measures. Its schemas have not landed in that repository yet, which is why the
mirror misleads in both directions.

This bears directly on the namespace decision below: **heart rate and blood
pressure sit inside P1752.2's chartered scope.** Our namespace claim for those
two is therefore best-until-1752.2-ships rather than settled, and anything
built there should expect a mapping obligation later.

**The working group's live work in 2026 is the `survey` schemas**, and those
were not in the earlier survey at all. They matter to us more than anything
else in the standard, for a reason given below.

What 1752.1 covers, precisely:

- `metadata`: `header`, `data-point`, `data-series`, `schema-id`
- `physical_activity`: one schema
- `sleep`: eleven schemas, including apnea-hypopnea index, arousal index,
  sleep stages, onset latency, time in bed, wake after sleep onset
- `environment`: ambient light, sound, temperature
- `survey`: eight schemas
- `utility`: eighteen, including `unit-value`, `unit-value-range`,
  `descriptive-statistic`, `time-frame`, `time-interval`, `body-posture`,
  and a family of typed unit values for kcal, length, speed, percent,
  frequency, temperature, illuminance and sound

**Two parts of this are not adoptable, and listing them without saying so was
an error in the first draft.**

**The typed unit-value family is pre-coordinated** and we should take only the
generic `unit-value`. A separate type per quantity kind bakes the quantity into
the type system, which is the units-in-field-names defect (G33) one level up,
and this engine's first settled decision is to post-coordinate. `unit-value`
plus a UCUM code says the same thing without closing the space.

**The sleep schemas are not a single block.** Sleep stages, onset latency, wake
after sleep onset and time in bed are descriptive and safe. **Apnea-hypopnea
index and arousal index are not**: an AHI is the measurand of a sleep-disorder
screen, and an engine that computes and emits one is making a detection
capability claim. Those two enter only as a recorded device or clinician
statement, never as an engine-computed output, per record-never-infer.

What 1752.1 does not cover: body weight, body composition, heart rate, blood
pressure, nutrition. Those stay in a vitai namespace under
`schema_id.namespace`, which is what that field exists for.

Split by how durable that is, because it is not uniform:

- **Heart rate and blood pressure**: inside P1752.2's chartered scope. Expect
  to map outward eventually. Design accordingly rather than deeply.
- **Weight, body composition, nutrition**: outside every chartered scope found.
  Ours for the foreseeable future.

### The survey schemas, and why they are the find

`survey-1.0.json` carries `delivery_details.end_status`, a closed enum:

```
abandoned | completed | missed
```

with the distinction written into the schema itself: *"Abandoned means some
answers were provided. Missed means no answers were provided."* The sample data
ships three instances of every example survey, one per status.

That is a published, maintained, actively-worked standard drawing exactly the
distinction four of our open issues are circling:

- **#93** absence has five meanings and the record stores one
- **#146** passive-versus-active channel silence is not first-class
- **#221** a skipped or abandoned session is the object a state explains
- **#224** the engine's asking channel, and **#232** eliciting a journey,
  where the engine owns the question's schema and the athlete owns the answer

#232's framing and `survey-item` (a question plus its provided answers) are the
same shape. The answer types are typed in the same spirit as #212's two-tier
instinct: `survey-categorical-answer`, `survey-date-answer`,
`survey-time-answer`, `survey-unit-value-answer`. Note that this is a
resemblance rather than a match, since #212 asks for coarse day-phase beside
precise time and these are answer-value types.

### The recommendation, downgraded after review

An earlier draft said **adopt** `end_status` and pull the survey schemas into
#224 and #232 before either is designed. **Both halves are withdrawn**, and the
reasoning against them is more instructive than the original finding.

**`end_status` is strictly poorer than our own analysis.** It has three values
and no *declined* state. #93 says absence has five meanings; #146 requires
passive and active channel silence to be distinguishable; #224, from G82, holds
that a decline is permanent and is itself an answer. `missed` collapses "never
delivered", "delivered and never seen", and "seen and refused" into one token,
which is precisely the conflation #146 exists to remove. Adopting it would bake
in a vocabulary we have already out-reasoned.

**And note how it got selected**: because it matched the four issues in front
of the author. That is G85's failure mode relocated from *writing* a vocabulary
to *choosing* one, which is a way this document could go wrong repeatedly and
quietly. The defence against it is that the selection criteria here were fixed
before the sweep; where a verdict rests on resemblance to our own open issues
instead, it is suspect.

**The survey schemas also say nothing about #224's actual problem**, which is
question identity and lifecycle, permanent declines, answers as claims with
provenance, and default-deny permission across three egress surfaces. IEEE
1752's survey schemas are a delivery-and-response format for administered
research instruments, and they structurally assume re-administration: the
sample data ships three instances of every survey. G82 bars re-asking. Importing
that frame before #224's constraints are written would make the frame the thing
the constraints get bent around.

**Revised recommendation: grounding, not adoption.** The typed answers are
genuinely useful to #212. `end_status` is worth citing as evidence that a
standards body found the distinction worth drawing at all, and worth nothing
beyond that. Design #224 from its own constraints first, then check the answer
typing against 1752.

**A better absence vocabulary exists and this survey missed it.** FHIR
`Observation.dataAbsentReason` is on a **Normative** resource and carries
`unknown` (with children `asked-unknown`, `temp-unknown`, `not-asked`,
`asked-declined`), `masked`, `not-applicable`, `unsupported`, `as-text`,
`error`, `not-performed`, `not-permitted`. It has the declined state, it
separates not-asked from asked-and-unanswered, and `masked` is a suppression
label rather than a deletion, which is this engine's own rule. **That is the
one to take to #93 and #146.**

### `header`, confirming the #239 answer

Required: `uuid` (RFC 4122), `schema_id`, `source_creation_date_time`.
Optional: `modality`, `acquisition_rate`, `external_datasheets`.

Three notes:

- `uuid` is the stored per-row identifier #239 needs, as already recorded.
- `acquisition_rate` is a **declared** cadence. #206 earns the cadence from
  arrival history instead and refuses below five arrivals. Ours is the better
  default, because a declaration in config is a promise the data need not keep;
  but the field is a legitimate place to record a rate a source states, and the
  two do not conflict.
- `modality` is `sensed | self-reported` and remains poorer than our `origin`,
  `path`, `capture`, `read_by`. Unchanged conclusion: mapping obligation
  outward, never model replacement.

### Open mHealth: deprecated, and deliberately

`github.com/openmhealth/schemas`, 78 stars, last pushed 2026-06-19. Those June
commits are the deprecation itself: *"Marked and documented as deprecated last
set of schemas superseded by IEEE 1752."*

This is worth stating precisely because a naive maintenance check reads a June
2026 push as a healthy project. It is a project being closed carefully. It
remains the better **reference** for measures 1752.1 does not define (weight,
blood pressure, glucose, nutrition), and it must not be cited as a live target.

### openEHR: alive, wrong shape

`openEHR/specifications-RM` last pushed 2026-07-24; `ehrbase` at 378 stars is
actively developed. But its npm presence is negligible (a handful of packages
all under about 25 weekly downloads) and the Python implementations found were
hobby-scale or abandoned. openEHR is an archetype-driven
clinical server model. Adopting it means adopting its tooling.

**Verdict: not a target. Note it and move on.**

### HL7 Physical Activity IG: dormant

`HL7/physical-activity`, 5 stars, last commit 2024-03-12. The nearest thing to
an official FHIR profile for our domain and it has not moved in over two years.

**Verdict: do not build on it.**

## Goals and plans: FHIR, and a striking convergence

`HL7/fhir` at 730 stars, pushed 2026-07-21. `@types/fhir` at 301,581 weekly npm
downloads. `fhir.resources` on PyPI at 8.3.0, 2026-07-03. Unambiguously alive
and unambiguously the most widely implemented health data standard there is.

**FHIR `Goal` (maturity 2, Trial Use)** splits exactly the way #235 did:

| FHIR | vitai |
|---|---|
| `lifecycleStatus` (1..1, required, modifier) | `lifecycle_status` |
| `achievementStatus` (0..1) | `achievement_status` |
| `continuous` (boolean, "sustaining requirement") | the `sustaining` case #240 built `measured_goals()` for |
| `target.measure` / `target.detail[x]` / `target.due[x]` | goal metric, target, deadline |
| `statusDate`, `statusReason` | |
| `outcome` (0..*) | nothing yet |

`achievementStatus` codes: `in-progress | improving | worsening | no-change |
achieved | sustaining | not-achieved | no-progress | not-attainable`.

We arrived at this split independently and #240 deliberately declined
`not_attainable`, `improving`, `worsening` and `no_change` for want of a
producer. That decision is unaffected and still right. What changes is that we
can now say our vocabulary is a **subset of a published one** rather than an
invention, which is worth stating in the docs and costs nothing.

Two things FHIR has that we do not: `continuous` as a declared boolean rather
than an inferred case, and `outcome`. Both worth an issue.

**Verdict: adopt the vocabulary as prior-art grounding per G85. Do not adopt
the resource model.**

### Plans: `PlanDefinition` outranks everything else cited here

The first draft of this survey covered goals, calendars and events and skipped
FHIR's plan resources, which was a real omission.

- **`PlanDefinition`** is at maturity **4**, higher than `Goal` or
  `RiskAssessment` (both 2), and it is the published version of exactly what
  #226 argues: a prescription is a **template**, instantiated into a
  `CarePlan` (maturity 2) for a particular subject. Template and instance are
  separate resources, which is #226's whole point.
- **The `Timing` datatype**, and `Timing.repeat` in particular
  (frequency, period, dayOfWeek, bounds), is the published shape for "three
  times a week". That is training-plan recurrence and it is **distinct from
  calendar recurrence**: a `RRULE` names occurrences on a calendar, while
  `Timing.repeat` states a rate without committing to days. #221 and #226 need
  the second, and JSCalendar gives the first.

**Verdict: study before building #226. This is the closest published match to
a training plan found anywhere in the survey.**

## Events and calendars

| Standard | Status | Ecosystem |
|---|---|---|
| **RFC 5545 iCalendar** | **Proposed Standard**, 2009 (it never advanced to Internet Standard) | `ical-generator` 605k/wk, `ical.js` 434k/wk, `node-ical` 247k/wk; PyPI `icalendar` 7.2.2, 2026-07-20 |
| **RFC 8984 JSCalendar** | Standards Track, July 2021, not obsoleted | `@dwk/calendar` 272/wk, `jscalendar-kit` 2/wk |

JSCalendar is the better-designed object model and it explicitly aims to be
iCalendar's successor: a real JSON data model, Event/Task/Group, recurrence as
`recurrenceRules` plus `recurrenceOverrides`, ISO 8601 durations with defined
DST semantics, and floating time as an explicit concept.

It also has, five years after publication, essentially no ecosystem.

This is the one place where "widely used" and "well designed" point opposite
ways. The resolution is that they answer different questions:

- **For our own model**, borrow JSCalendar's shapes. Its `Task` with both
  start and due, and its separation of a recurrence rule from per-occurrence
  overrides, is precisely the plans-as-rows problem in #221 and #226 (a
  prescription is a template, not rows).
- **For import and export**, RFC 5545 is what anything will actually hand us,
  and it is what open question 6 in the client repo will meet if the calendar
  question is ever answered yes.

**Verdict: JSCalendar for shape, iCalendar for interchange. Neither adopted
wholesale.**

## Units: UCUM, unreservedly

`ucum-org/ucum` pushed 2025-07-09. `@lhncbc/ucum-lhc` at 88,737 weekly npm
downloads, updated 2026-07-23, from the NLM's Lister Hill centre. `ucumvert` on
PyPI at 0.3.2, 2026-06-04. Both FHIR and IEEE 1752 bind to it.

Note the wrinkle already present in 1752: `unit-value.unit` draws from *common
synonyms* rather than UCUM codes directly, so `kg` is fine but the mapping is
not identity everywhere. Conforming means conforming to their binding, not to
UCUM raw.

**Verdict: adopt, and be precise about what that means today.** G33 records
that units are currently baked into field names, and #260 calls the
unit-in-value migration the most expensive of its four changes. So "adopt UCUM"
does **not** license that migration on the strength of this survey. What it
licenses now is the #260 middle path: **connector manifests declare the UCUM
unit per field.** The storage migration remains its own decision.

Adopt the codes and the binding as registry data. Never a conversion library:
that would be a runtime dependency.

## Nutrition: the gap nobody fills

- **Open Food Facts** is alive and healthy: `openfoodfacts-server` pushed
  2026-08-05, official SDKs current on both registries. But it is a **product
  database**, not a schema for what a person ate. Its licence attaches to the
  database, which `meals.py` already records.
- **FHIR** has `NutritionOrder` and `NutritionIntake`, both low maturity and
  oriented at clinical feeding rather than a logged meal.
- **IEEE 1752.1** does not cover nutrition at all, though it does define
  `kcal-unit-value` as a utility type.

There is no maintained, widely adopted schema for a logged meal.

**Verdict: our namespace, and say so plainly rather than implying we looked
less hard than we did. This also means #96's itemised-meal-estimate problem has
no standard to defer to.**

**FoodOn** (228 stars, pushed 2026-07-31) is worth naming as *vocabulary*
grounding for food identity in that namespace, the way UCUM is named for units.
It does not weaken the verdict, because a food ontology is not a schema for
what somebody ate.

## Activity file formats

| Format | Official tooling | Verdict |
|---|---|---|
| **FIT** | `@garmin/fitsdk` 21,534/wk and `garmin-fit-sdk` on PyPI, both updated **2026-08-04** | The vendor maintains an official SDK on both registries, actively. Relevant to #91 and #101 |
| **GPX** | `gpxpy` 1.6.2 (2023-11-29), `@tmcw/togeojson` 257k/wk | De facto, stable, unowned |
| **TCX** | nothing well maintained | Legacy; parse it, do not build on it |

Note for #91: `fitparse` on PyPI last released 2020-09-07 and is the package
most people land on. `garmin-fit-sdk` is official and current. If the engine
ever reads FIT, that is the profile source, though the stdlib-only rule means
reading the profile rather than depending on the SDK.

## Provenance: PROV-O is stable, not alive

`w3c/prov` has 1 star. Every npm package implementing it is in the low single
or double digits of weekly downloads (`prov` at 2, `provenance` at 5,
`@ontologies/prov` at 0). The PyPI `prov` package is at 3.0.0, 2026-07-27,
which is the healthiest signal it has.

PROV-O is a 2013 W3C Recommendation. It is finished rather than abandoned, and
its `wasDerivedFrom` / `wasGeneratedBy` / `Activity` triple is the conceptual
ancestor of `derived_from` and `derived_op` from #184.

**Verdict: cite it as grounding for the lineage model. Do not serialise to it;
there is nobody to interoperate with.**

## Prediction and modelled numbers

This is the area the operator asked about, and the survey's real finding.

### FHIR `RiskAssessment` is the shape, and it is a separate resource

Maturity 2, Trial Use. Its load-bearing elements for this question (the full
resource also carries `status`, `subject`, `condition`, `relativeRisk`,
`mitigation` and `note`):

| element | card | what it holds |
|---|---|---|
| `method` | 0..1 | the algorithm, process or mechanism used |
| `basis` | 0..* | references to the source data considered |
| `occurrence[x]` | 0..1 | when the assessment was made |
| `performer` | 0..1 | who or what produced it |
| `prediction.outcome` | 0..1 | what is predicted |
| `prediction.probability[x]` | 0..1 | decimal **or Range** |
| `prediction.qualitativeRisk` | 0..1 | negligible / low / moderate / high / certain (example binding) |
| `prediction.when[x]` | 0..1 | the window the prediction applies to |
| `prediction.rationale` | 0..1 | free text explanation |

Three structural lessons, and the first is the important one:

1. **A prediction is its own resource, not a field on an observation.** FHIR
   does not write predicted values into the record of measured ones. It makes
   the prediction a separate event that *points back* at the observations it
   used. That is the same shape as our `emissions` dataset from #196: an event,
   never retired, carrying `basis_claims`.
2. `method` plus `basis` plus `occurrence` is exactly the operator's
   "which model, WHEN, based on WHAT data".
3. `rationale` is free text, and `derived_op` already made the matching call:
   declared, never executable.

**One hard carve-out before anyone builds to this shape.** `RiskAssessment` is
a clinical risk resource, and two of its elements are unadoptable here on the
medical boundary: `prediction.outcome` is condition-valued, and
`qualitativeRisk` renders a health risk on a graded scale. Emitting either is
naming a condition or claiming a screening capability. **Adopt the structure
(`method`, `basis`, `occurrence`, an interval, a horizon) and none of the
clinical vocabulary.** Predictions here are about quantities the record already
holds, a weight or a pace, and never about conditions or risks. #262 is already
clean on this; the shape must not be cited without the carve-out.

### Model documentation is dead as tooling

- `tensorflow/model-card-toolkit`: **archived** 2023-07-26. PyPI
  `model-card-toolkit` last released 2023-04-03.
- MLCommons **Croissant** is alive (882 stars, pushed 2026-07-15;
  `mlcroissant` 1.1.0) but it describes **datasets**, not fitted models, and
  it is aimed at ML corpora rather than a personal record.

**Verdict: no maintained schema for "which model produced this number".
Model Cards remain a useful checklist and a dead standard.**

### Interval semantics: the gap is narrower than first stated, and real

The first draft of this section said nothing schema-shaped existed anywhere.
That was too strong, and the correction matters because it hands #171 a
standard it can use.

**W3C SSN's System Capabilities module is prior art for #171**, and it is a W3C
Recommendation with an active repository (`w3c/sdw-sosa-ssn`, pushed
2026-07-31). `ssn-system:SystemCapability` carries `Accuracy`, `Precision`,
`Drift` and `Resolution`, **scoped to declared operating conditions**. That is
#171's own phrasing (standard uncertainty with its own provenance,
condition-scoped) already standardised. It should be adopted there.

What remains genuinely absent is narrower and still blocking: **no interchange
schema says what KIND of interval a value-interval is.**

- IEEE 1752.1's value-interval types (`unit-value-range` and
  `duration-unit-value-range`) are bare `low_value` / `high_value` / `unit`.
  No confidence level, no distribution, no statement of kind.
- FHIR's `probability[x]` allows a `Range` and says nothing about what the
  range means either.
- `descriptive-statistic` covers `standard deviation` and `variance`, but it
  is explicitly about *descriptive* statistics of a set of measurements, with
  the default written into the schema: *"A measurement value without a
  descriptive statistic is interpreted as being the result of an individual
  measurement."* It says nothing about inferential output.
- The metrology world has the authority here (the GUM, JCGM 100:2008, and its
  coverage-factor vocabulary), but it is a document rather than a schema, and
  a GitHub sweep for digital calibration certificate and D-SI schemas returned
  nothing adoptable.
- `uncertainties` on PyPI (3.2.3, 2025-04-21) is a live error-propagation
  library, not an interchange format.

**So an interval in either standard cannot say whether it is a measurement
uncertainty, a confidence interval, or a prediction interval, nor at what
level.** Those three are different claims and conflating them is how a number
gets read as more certain than it is.

That distinction has to be ours, in our namespace, and #171 (instrument
capability, standard uncertainty with its own provenance, condition-scoped and
effective-dated) is the issue that already half-owns it.

## Places and containment

For #84 (derive a place inventory) and the containment half of #220.

### FHIR `Location` is the best-matured thing in this entire survey

**Maturity level 5**, higher than any other resource checked here (`Goal` and
`RiskAssessment` are both 2). Its elements:

| element | card | what it gives us |
|---|---|---|
| `partOf` | 0..1 | recursive nesting, arbitrary depth |
| `mode` | 0..1 | **`instance` or `kind`** |
| `form` | 0..1 | building, room, vehicle, and so on |
| `status` | 0..1 | active, suspended, inactive |
| `operationalStatus` | 0..1 | a **second, separate** state axis |
| `characteristic` | 0..* | descriptive attributes |
| `position` | 0..1 | WGS84 |

Two findings.

**`mode: instance | kind` is the distinction #84 needs and does not have.** "A
gym" and "the gym I go to on Tuesdays" are different objects, and a place
inventory derived from tracks produces instances while a plan that says "needs
a gym" is talking about a kind. One field, already standardised, and without it
the two get conflated the moment a prescription meets a place.

**`status` and `operationalStatus` are two axes on one resource**, which is
exactly the split #235 made for goals when it separated lifecycle from
achievement. HL7 arrived at the same separation independently for places. That
is now the third independent instance of the same pattern in FHIR, and it is a
strong argument that #220's insistence on separating axes is right rather than
fastidious.

### NetBox: the best-adopted practical nesting model

21,255 stars, pushed 2026-08-05. Nautobot, its fork, at 1,571 and equally
current. Its hierarchy is Region, Site Group, Site, Location (itself recursive),
Rack, Device.

The lesson worth stealing is not the depth, it is that NetBox maintains a
**geographic tree and a grouping tree separately**, because "where a thing
physically is" and "how things are grouped for management" are different
questions that look like one until they diverge. #220 already separates
`contains` from `depends_on` for the same class of reason.

### The one that looks authoritative and is not

**W3C Building Topology Ontology**: 65 stars, last push **2021-08-10**. A
community group draft that never became a Recommendation and has not moved in
five years. It is the single most citable-sounding name in this area and the
deadest thing in this survey. Recorded here so nobody rediscovers it and
assumes the W3C prefix means maintained.

**Brick Schema** (391 stars, pushed 2026-07-25) is the live alternative, but it
is building-automation shaped: sensors, HVAC, equipment. Real, maintained, and
aimed somewhere else.

**schema.org `Place` / `containedInPlace`** is alive and semantically thin.
Fine as a rendering vocabulary, useless as a model.

## Objects, loads and the household

For #215 (object registry), #216 (loads registry), #217 (household context)
and #218.

### EPCIS 2.0 is the closest structural match, and almost nobody looks at it

A ratified GS1 standard for supply-chain event capture. Note that
`github.com/gs1/EPCIS` is only a draft-sharing repository (29 stars, 2024-03-15)
and is not the standard; the standard is maintained by GS1 itself.

What it has that we need:

- **`AggregationEvent` with a parent and children.** Containment as an event
  rather than a static property, so a thing being loaded into another thing has
  a time and can end. #216's towed and carried things are exactly this, and a
  static `contains` field cannot express "loaded at 9, unloaded at 11".
- **`disposition`** is a state of an object, carried on the event.
- **`bizLocation` versus `readPoint`**: where the thing now is, versus where it
  was observed. That is the same distinction as our origin-versus-path, applied
  to place, and it is a distinction #84 will need the moment a track observes a
  thing somewhere it does not live.

**Verdict: study the aggregation-plus-disposition pattern before designing
#215 and #216. Do not adopt EPCIS itself; it is a supply chain standard and
the impedance is high.**

### FHIR for the household, with one caution

`Device` gives identity, owner and status. `Group` gives membership. Both
usable as grounding.

The caution concerns pets. `Patient` is **Normative** from R4 and its core
resource carries no species, breed or animal-specific elements. STU3 had
`Patient.animal` in core; R4 removed it, and it survives as the standard
`patient-animal` extension with `species`, `breed` and `genderStatus`.

So the shape "a pet is a person with a species field" is not one HL7 refuses.
It is one HL7 **demoted from the core resource to an optional extension when
that resource went normative**, which is a weaker and more useful signal: the
modelling works, and it was judged not to belong in the thing everyone loads.

For our purposes the boundary in #220 already settles most of it: a state about
a person or an animal may qualify a statement about the athlete and may never
be the subject of one. A pet in the household registry needs a slug, a mass if
it is ever carried, and nothing else.

### Mass that drifts has no prior art

#216's core case, a carried thing whose mass changes over time and whose figure
goes stale, is not modelled anywhere found. Asset management standards (the ISO
55000 family) are documents rather than schemas and treat mass as static.
Effective-dated mass with a staleness rule is ours to design, and #171's
effective-dated instrument capability is the nearest internal pattern.

## State

For #220, which is the issue this section exists to serve.

### Redfish already solved "composing through containment"

DMTF Redfish is maintained and adopted: `Redfish-Publications` updated
2026-05-18, `Redfish-Tools` 2026-07-10, `python-redfish-library` 2026-07-24,
plus a healthy vendor ecosystem (Dell's Redfish scripting at 731 stars, `gofish`
at 315).

Its `Status` object carries three fields:

```
State | Health | HealthRollup
```

**`HealthRollup` is the health state of the resource *and its dependent
resources*, carried beside the local `Health` rather than replacing it.**

Three precisions, because the loose reading of this is wrong in ways that
matter to #220:

- It includes the resource **itself**, not only what is beneath it.
- It composes over **dependency**, not containment. DSP0268 gives an explicit
  example where a computer system's rollup degrades for a power supply that is
  not subordinate to it. #220 already separates `contains` from `depends_on`,
  and Redfish is evidence for the second, not the first.
- It is **not normatively worst-of**. The specification's own redundancy
  example has a Critical power supply rolling up as only Warning, because the
  redundancy policy absorbs it. The roll-up rule is implementation policy.

That last point is the useful one. A rollup is not a `max()`; it is a policy
over the graph, and a model that hard-codes worst-of cannot express "this is
covered by redundancy" or, here, "the other machine will do".

That last point is the one worth taking. #220 proposes that a room's condition
reaches its contents. If the resolved value overwrites the local value, you can
no longer tell a broken treadmill from a working treadmill in a broken room,
and the two need different actions. Redfish keeps both. So should we.

Its ancestor, DMTF CIM, made `OperationalStatus` a multi-valued array for a
related reason: a thing can be degraded *and* predicted-to-fail at once, and one
enum forces a false choice. #220's "a state may carry more than one verb"
(`blocks`, `discourages`, `qualifies`) is the same insight.

### The two-axis pattern, and an honest account of how much support it has

| resource | axis one | axis two |
|---|---|---|
| FHIR `Goal` | `lifecycleStatus` | `achievementStatus` |
| FHIR `Location` | `status` | `operationalStatus` (scoped by FHIR to beds and rooms) |
| Redfish `Status` | `State` | `Health` |

An earlier draft of this document called that "three standards bodies, three
domains, independently". **That claim is withdrawn.** Two of the three rows are
HL7, which is one body with cross-resource design review, and Redfish descends
from DMTF CIM, whose separation of administrative from operational state goes
back to ITU X.731 and OSI systems management. At most two lineages, arguably
one, and both grew up in the same enterprise-modelling tradition.

The honest argument is **survivorship rather than convergence**: the split has
been load-bearing in production standards for around thirty years and nobody
has collapsed it back. That is weaker than independent rediscovery and it is
still a good reason to build it in from the start.

#220 does not need the inflated version. #235 reached the same separation for
goals by argument, before any of this was surveyed.

### What none of them have

Every model above states a state. None of them carries:

- a **warrant** (`declared`, `observed`, `derived`), because in those domains a
  state is always sensed by the system that reports it. Ours is frequently
  asserted by the athlete, and #220 is right that the distinction is load
  bearing.
- **`corroborated_by` as distinct from `derived_from`**, which #220 draws and
  which no surveyed standard does.
- **graded restriction**. Redfish health is a small enum; there is no "usable
  but unwise", which is most of what a real state says here.

So #220 is a genuine extension rather than a re-derivation, and the parts to
borrow are narrow and specific: keep the rollup separate from the local value,
allow more than one status verb at once, and separate the two axes from day one.

## Routes, splits, addresses and positional accuracy

For #23 (named algorithms plus egress masking), #84 (place inventory), #118
(the route retrospective) and #247/#254 (best efforts).

### GeoJSON is the only format here worth adopting, and only for geometry

RFC 7946, IETF Proposed Standard, universally implemented. Its own repository
(`geojson/draft-geojson`) last moved in 2016, which is what a finished RFC
looks like rather than abandonment.

The limitation is deliberate and it matters: **GeoJSON carries geometry and
nothing else.** A position is longitude, latitude and an optional third
element, and the RFC discourages putting anything more in it. No time, no
speed, no accuracy, no heart rate. Everyone who stores a track in GeoJSON
invents their own `properties`, which is exactly why no two GeoJSON tracks
interoperate.

**Verdict: adopt for geometry egress, where a masked or simplified path has to
leave the engine. Never as the track model.**

### Routing engine responses are products, not standards

OSRM (7,944 stars), Valhalla (6,041) and GraphHopper (6,612) are all healthy
and all define their own response shapes: legs, steps, maneuvers, annotations.
The commercial directions APIs add licence terms that frequently forbid storing
the results at all.

The deeper objection is a category error waiting to happen. **A routing route
and our route are different objects.** Theirs is a prescription for getting
somewhere that has never been travelled. Ours, in #118, is the *identity of a
path travelled repeatedly*, whose whole purpose is comparison against previous
occasions. Adopting a directions schema imports turn-by-turn concepts we will
never use and says nothing about the one thing we need.

**Verdict: do not adopt any of them.**

### The actual hard problem has no schema at all

"Is this run the same route as that run" is trajectory similarity and map
matching, and the prior art is algorithms rather than formats: discrete Frechet
distance, Hausdorff distance, dynamic time warping, longest common
subsequence. Valhalla and OSRM both ship map-matching services, which is prior
art for the *technique* and not for the storage.

#23 already says to replace hand-rolled geometry with named algorithms, and
that instinct is right: **the deliverable is a named algorithm with a stated
tolerance, not a schema.** #254's `basis` field, distinguishing a window
measured against the device's own cumulative distance from one against the
engine's haversine sum, is the same instinct already shipped.

### Laps and splits are two things, and the difference is warrant

The real prior art is FIT lap messages and the TCX `Lap` element, both vendor
defined and both widely produced.

The distinction worth preserving is warrant, and **it needs three values, not
two.** A first pass had it as declared-versus-derived, which misfiles the
commonest case:

| | who segmented | what it is evidence of |
|---|---|---|
| **athlete-pressed lap** | the athlete, at the moment | intent. Real evidence about what was being done |
| **device auto-lap** | the device, by configuration, every kilometre | a device-computed split recorded at capture. **No intent in it at all** |
| **reader-computed split** | whoever is reading, afterwards | an artefact of the reader's chosen interval |

Most laps in real files are auto-laps. Treating every FIT lap message as
`declared` **fabricates intent the athlete never expressed**, which is the same
class of error as naming a state.

There is a second consequence from the other direction: a split is computable
from the stored track, so under derive-never-store it belongs in the derived
tier, while an athlete-pressed lap is an observation and belongs in the record.
Merging them stores derivable data in ground truth *and* lets a reader-chosen
interval masquerade as evidence of intent. **Do not merge them into one
table**, and give the warrant three values here.

A loop, similarly, has no standard and needs none: a closed path is start and
end within some distance of each other, and that distance is a **choice**, so
it is post-coordinated rather than fixed.

### Addresses and place names are a privacy decision before a schema decision

This is the part to be most careful about, and it is the one where reaching for
a schema first would be a mistake.

The maintained options are real:

| source | standing |
|---|---|
| **Overture Maps** `addresses` and `places` themes | 205 stars on the schema repo, pushed 2026-08-05; foundation-backed, open data. Best current option |
| **OpenAddresses** | 3,227 stars, pushed 2026-08-04 |
| **Who's On First** gazetteer | 496 stars, last push 2024-03-06; semi-dormant |
| ISO 19112 (gazetteers), ISO 19160 (addressing) | the formal standards, and paywalled documents rather than schemas |
| schema.org `PostalAddress` | alive, thin |

But **a street name is a precise location**, and adopting a rich address schema
increases what this record holds about where the athlete lives, sleeps and runs
before anything has decided what may leave. #205 already settled the rule that
governs this: sensitive fields are two-tier, stored precise, coarsened at
*write*, with egress gated on explicit per-use permission. #23 already flags
egress masking on route analysis.

And #84 already has the ordering right: **derive a place inventory from the
record's own tracks before naming anything.** An address schema inverts that,
because it starts from the naming.

**Verdict: no street-address schema until #205's coarsening is implemented.
Then Overture as the vocabulary, and only for names the athlete chose to
attach.**

**Scope of that hold, stated precisely, because it must not re-gate settled
work.** #84 already reversed "any hosted geocoding call is a design failure" as
a policy decision dressed as an engineering one, and settled the resolver
ladder (`none` / `local` / `hosted-coarse` / `hosted`, defaulting to `local`,
with per-place overrides and masking). This hold does **not** touch that. It
touches adopting a rich address *schema*, whose Overture fields would raise
what the record holds about where the athlete lives. #84 tier 1, anonymous
clustered entities derived locally with no network call, is safe now and should
proceed.

### Positional accuracy, and a correction to this document

Earlier this survey said no standard states what kind of interval an interval
is. **That is too strong, and the counterexample is worth having**, because it
is the one place a mainstream specification gets this right.

The W3C Geolocation API (Candidate Recommendation, 2026-03-26) defines:

> `accuracy`: "a non-negative double that represents the accuracy value
> indicating the **95% confidence level** in meters"

and `altitudeAccuracy` identically. So a positional accuracy figure on the web
platform is a stated confidence level in stated units, not a bare number.

Two lessons, pulling opposite ways, and both belong in #262:

1. **Stating the level inline is precedent, and we should do it.** It is
   proof the idea is implementable and familiar rather than exotic.
2. **Baking 95% into the field definition is pre-coordination**, and it is the
   trap this engine refuses everywhere else. A field defined as "the 95%
   figure" cannot express any other level, and a source reporting a one-sigma
   figure has nowhere honest to put it. So #262's `interval_level` should be
   **declared per row**, with absent meaning unstated, rather than fixed by
   the schema.

One more thing from the same specification, arriving from outside and matching
this engine's doctrine exactly: `speed` and `heading` are null when
unavailable, and **`heading` is additionally null when the device is
stationary**. That is a refusal rather than a fake zero, on precisely the
grounds that a set with `failure: null` is never a maximum.

## Summary

| Area | Target | Standing |
|---|---|---|
| Framing, metadata, identifiers | **IEEE 1752.1** | adopt (#261) |
| Question and answer typing | IEEE 1752.1 `survey` | **grounding only**, not adoption; see the downgrade above |
| Absence and non-response | **FHIR `Observation.dataAbsentReason`** (Normative) | the one to take to #93 and #146 |
| Plans as templates, and rate-based recurrence | **FHIR `PlanDefinition`** (maturity 4), `Timing.repeat` | study before #226 |
| Instrument capability, condition-scoped | **W3C SSN System Capabilities** | adopt for #171 |
| Physical activity, sleep stages and latency | **IEEE 1752.1** | adopt |
| Apnea-hypopnea and arousal indices | IEEE 1752.1 | **do not emit**; recorded statements only |
| Typed unit-value family (`kcal-unit-value` etc) | IEEE 1752.1 | **do not adopt**; pre-coordinated. Generic `unit-value` only |
| Units | **UCUM**, via 1752's binding | adopt as registry data; see the G33 scoping note |
| Goal lifecycle and achievement | **FHIR `Goal`** | vocabulary grounding only; already convergent |
| Predictions | **FHIR `RiskAssessment`** | adopt the structure only; its clinical vocabulary is barred |
| Food identity | **FoodOn** | vocabulary grounding inside the vitai namespace |
| Lineage | **W3C PROV-O** | cite as grounding; do not serialise |
| Calendar shape | **RFC 8984 JSCalendar** | borrow shapes |
| Calendar interchange | **RFC 5545 iCalendar** | import and export |
| Activity files | **FIT** (official SDK), GPX | read; do not depend |
| Weight, body composition, HR, BP | Open mHealth as reference | vitai namespace |
| Nutrition | nothing adoptable | vitai namespace |
| Prediction intervals, uncertainty | **nothing adoptable** | vitai namespace, grounded in the GUM |
| Place nesting and kind-versus-instance | **FHIR `Location`** (maturity 5) | adopt the shape; feeds #84, #220 |
| Grouping distinct from geography | **NetBox** | borrow the two-tree separation |
| Containment as a timed event | **GS1 EPCIS 2.0** `AggregationEvent` | study before #215, #216 |
| Object state rolled up through containment | **DMTF Redfish** `Status` | borrow rollup-beside-local |
| Household, pets | FHIR `Device`, `Group`; `Patient` is **not** the animal model | grounding only |
| Mass that drifts | **nothing adoptable** | ours, patterned on #171 |
| Building topology | W3C BOT (dormant since 2021), Brick | not targets |
| Track geometry egress | **GeoJSON** RFC 7946 | adopt, geometry only |
| Route identity, map matching | named algorithms, no schema exists | #23's framing is right |
| Laps versus splits | FIT lap, TCX Lap | keep separate; the axis is warrant |
| Addresses, place names | **Overture Maps**, gated behind #205 | not until coarsening ships |
| Positional accuracy | **W3C Geolocation API** | adopt stating the level; do not fix it at 95% |
| Directions and routing APIs | OSRM, Valhalla, GraphHopper, vendors | not targets, different object |
| Clinical record model | openEHR, HL7 PA IG | not targets |

## What this changes

- **#261 gains a scope caveat**: heart rate and blood pressure fall inside
  IEEE P1752.2's chartered scope, so the namespace decision for those two has
  an expiry date. Weight, body composition and nutrition do not.
- **#93 and #146 gain a real absence vocabulary**, and it is FHIR
  `dataAbsentReason` rather than 1752's `end_status`, which has no declined
  state and cannot carry what those issues already require.
- **#224 and #232 keep their design work.** The survey schemas are grounding,
  not a vocabulary to adopt; they assume re-administration, which G82 bars.
- **#212 gains a resemblance, not a match**, in the typed answer schemas.
- **#226 gains `PlanDefinition` and `Timing.repeat`**, which is the closest
  published match to a training plan in the whole survey, and at maturity 4
  outranks everything else cited here.
- **#171 gains W3C SSN System Capabilities**, condition-scoped accuracy and
  precision, which is that issue's own shape already standardised.
- **#240's vocabulary is a documented subset of FHIR's**, which is worth
  recording and changes no behaviour.
- **#262 gains a structure to build to** and a confirmed, narrower gap: no
  schema anywhere states what *kind* of interval an interval is.
- **#84 gains `mode: instance | kind`**, which it needs and does not have. Its
  settled resolver ladder is untouched by the address hold.
- **#220 gains three borrowings**, all corrected from the first draft: a rollup
  sits beside the local value, composes over **dependency** rather than
  containment, and is **policy rather than worst-of**. Its warrant axis and its
  `corroborated_by` distinction remain genuinely novel.
- **#215 and #216 gain EPCIS aggregation** as the pattern for containment
  that starts and ends, and confirmation that drifting mass has no prior art.
- **#96 has no standard to defer to** for itemised meal estimates. FoodOn is
  vocabulary grounding for food identity only.

## Review history

This document was red-teamed on 2026-08-05 by two independent reviews, one
verifying every figure against its source and one attacking the reasoning
against repo doctrine. The numeric layer reproduced exactly. The interpretive
layer did not, and the corrections are folded in above rather than appended:
the P1752.2 scope finding, the Redfish roll-up definition, the withdrawal of
the "three bodies independently" claim, the `end_status` downgrade, the
`RiskAssessment` medical-boundary carve-out, the three-valued lap warrant, the
UCUM scoping, and four missed schema families.

Two of those corrections had already propagated into issue comments before
review, on #261 and #220. Both are corrected by a follow-up comment rather than
edited, because correcting by append is what this record does everywhere else
and an edited comment hides that the wrong version was acted on.

That is the argument for the staleness caveat at the top: this document was
wrong in public for about an hour, and it will be wrong again.
