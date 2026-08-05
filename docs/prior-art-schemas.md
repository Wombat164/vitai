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

## The three-line verdict

1. **IEEE 1752.1 for the framing and for what it defines.** Already decided in
   #261. This survey adds evidence that it is live, and finds a part of it the
   earlier analysis missed.
2. **FHIR for vocabularies and for mapping outward**, never as our model.
   Specifically its goal vocabularies, which we independently arrived at, and
   its shape for predictions, which answers a question we were about to design
   from scratch.
3. **Nothing at all for prediction intervals and measurement uncertainty.**
   Both bodies punt. That gap is the finding of this survey.

## Health measures and metadata

### IEEE 1752.1: live, and larger than we thought

| | |
|---|---|
| Where | `opensource.ieee.org/omh/1752`, schemas resolvable via `w3id.org/ieee/ieee-1752-schema/` |
| Last activity | 2026-08-03 |
| Substantive commits | 2026-03-19 and 2026-05-04, both on the survey schemas |
| Size | 47 schema files, JSON Schema draft-07 |

Two corrections to the earlier analysis in #261, both of which change what
conformance is worth.

**`omh/1752-2` is not a second standard.** It is an identical mirror: same 47
files, same commit list, same head. Anyone finding it and concluding a 1752.2
is in draft will be wrong. The published standard is still 1752.1-2021.

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
  and typed unit values for kcal, length, speed, percent, frequency,
  temperature, illuminance and sound

What it does not cover, still true: body weight, body composition, heart rate,
blood pressure, nutrition. Those stay in a vitai namespace under
`schema_id.namespace`, which is what that field exists for.

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
same shape. We should not design that vocabulary ourselves. The answer types
are already split the way #212 wants: `survey-categorical-answer`,
`survey-date-answer`, `survey-time-answer`, `survey-unit-value-answer`.

**Recommendation: pull the survey schemas into #224/#232 before either is
designed, and put `end_status` in front of #93 and #221.**

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
actively developed. But there is no npm presence at all and the Python
implementations are hobby-scale or abandoned. openEHR is an archetype-driven
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

## Events and calendars

| Standard | Status | Ecosystem |
|---|---|---|
| **RFC 5545 iCalendar** | Internet Standard, 2009 | `ical-generator` 605k/wk, `ical.js` 434k/wk, `node-ical` 247k/wk; PyPI `icalendar` 7.2.2, 2026-07-20 |
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

**Verdict: adopt. It is the one vocabulary with no serious competitor.**

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
less hard than we did. This also means #214's meal-level detail problem has no
standard to defer to.**

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

`w3c/prov` has 1 star. The npm ports run 35 to 408 weekly downloads. The PyPI
`prov` package is at 3.0.0, 2026-07-27, which is the healthiest signal it has.

PROV-O is a 2013 W3C Recommendation. It is finished rather than abandoned, and
its `wasDerivedFrom` / `wasGeneratedBy` / `Activity` triple is the conceptual
ancestor of `derived_from` and `derived_op` from #184.

**Verdict: cite it as grounding for the lineage model. Do not serialise to it;
there is nobody to interoperate with.**

## Prediction and modelled numbers

This is the area the operator asked about, and the survey's real finding.

### FHIR `RiskAssessment` is the shape, and it is a separate resource

Maturity 2, Trial Use. Its elements:

| element | card | what it holds |
|---|---|---|
| `method` | 0..1 | the algorithm, process or mechanism used |
| `basis` | 0..* | references to the source data considered |
| `occurrence[x]` | 0..1 | when the assessment was made |
| `performer` | 0..1 | who or what produced it |
| `prediction.outcome` | 0..1 | what is predicted |
| `prediction.probability[x]` | 0..1 | decimal **or Range** |
| `prediction.qualitativeRisk` | 0..1 | low / medium / high |
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

### Model documentation is dead as tooling

- `tensorflow/model-card-toolkit`: **archived** 2023-07-26. PyPI
  `model-card-toolkit` last released 2023-04-03.
- MLCommons **Croissant** is alive (882 stars, pushed 2026-07-15;
  `mlcroissant` 1.1.0) but it describes **datasets**, not fitted models, and
  it is aimed at ML corpora rather than a personal record.

**Verdict: no maintained schema for "which model produced this number".
Model Cards remain a useful checklist and a dead standard.**

### Measurement uncertainty: nothing schema-shaped, anywhere

This is the honest and slightly uncomfortable conclusion.

- IEEE 1752.1's only interval type is `unit-value-range`: `low_value`,
  `high_value`, `unit`. No confidence level, no distribution, no statement of
  what kind of interval it is.
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

The caution concerns pets. `Patient` is **Normative** from R4 and carries no
species, breed or animal-specific elements at all; animals are accommodated by
the general resource and by extension. So the most mature health data standard
there is, having gone normative, does **not** model an animal as a variant of a
person. Anyone reaching for "a pet is a person with a species field" is
choosing a shape HL7 does not use.

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

**`HealthRollup` is the worst health of anything contained beneath this
element.** That is #220's phrase "composing through containment", already
specified, already implemented by every server vendor, and already carrying the
lesson that a rolled-up value must be a *separate field* from the local one.

That last point is the one worth taking. #220 proposes that a room's condition
reaches its contents. If the resolved value overwrites the local value, you can
no longer tell a broken treadmill from a working treadmill in a broken room,
and the two need different actions. Redfish keeps both. So should we.

Its ancestor, DMTF CIM, made `OperationalStatus` a multi-valued array for a
related reason: a thing can be degraded *and* predicted-to-fail at once, and one
enum forces a false choice. #220's "a state may carry more than one verb"
(`blocks`, `discourages`, `qualifies`) is the same insight.

### The two-axis pattern, three times independently

| resource | axis one | axis two |
|---|---|---|
| FHIR `Goal` | `lifecycleStatus` | `achievementStatus` |
| FHIR `Location` | `status` | `operationalStatus` |
| Redfish `Status` | `State` | `Health` |

Three standards bodies, three domains, same separation: **where the thing is in
its lifecycle** is not **how the thing is doing**. #235 found it for goals by
argument. It is worth recording that the argument has independent support,
because it means the pattern generalises to states and #220 should build it in
from the start rather than rediscovering it a fourth time.

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

## Summary

| Area | Target | Standing |
|---|---|---|
| Framing, metadata, identifiers | **IEEE 1752.1** | adopt (#261) |
| Surveys, questions, non-response | **IEEE 1752.1 `survey`** | adopt; feeds #224, #232, #93, #221 |
| Sleep, physical activity | **IEEE 1752.1** | adopt where defined |
| Units | **UCUM**, via 1752's binding | adopt |
| Goal lifecycle and achievement | **FHIR `Goal`** | vocabulary grounding only; already convergent |
| Predictions | **FHIR `RiskAssessment`** | adopt the shape, not the resource |
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
| Clinical record model | openEHR, HL7 PA IG | not targets |

## What this changes

- **#261 gains a fourth answer**: adopt the survey schemas, which the original
  three-way split did not consider because the earlier survey missed them.
- **#224 and #232 should not design a question vocabulary.** One exists, it is
  maintained, and its answer typing already matches what #212 asked for.
- **#93 and #221 gain a published discriminator** in `end_status`.
- **#240's vocabulary is a documented subset of FHIR's**, which is worth
  recording and changes no behaviour.
- **The prediction question has a shape to build to** and, for the interval
  semantics, a confirmed absence of prior art rather than an unsearched one.
  Recorded as #262.
- **#84 gains `mode: instance | kind`**, which it needs and does not have.
- **#220 gains three specific borrowings** (rollup beside local, multiple
  status verbs, two axes from the start) and confirmation that its warrant
  axis and its `corroborated_by` distinction are genuinely novel.
- **#215 and #216 gain EPCIS aggregation** as the pattern for containment
  that starts and ends, and confirmation that drifting mass has no prior art.
