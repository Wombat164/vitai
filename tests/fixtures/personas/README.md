# The persona corpus

Eight synthetic athletes, each constructed to stress an axis the model was not
built for. They are fictional. The failures they found were not.

They live here as PEOPLE, not as test data: a profile, their history, the data
their life actually produces, the metrics THEY chose, and the contradictions
they carry. A fixture built from a spec tests what you already thought of; a
fixture built from a person tests what you did not.

| Slug | Who | Axis | Sweep |
|---|---|---|---|
| `priya` | ICU nurse, 34, rotating nights, no wearable, wants one pull-up | temporal structure, skill goals, deviceless | 1 |
| `sofia` | 31, 5 months post-caesarean, breastfeeding, self-imposed 1200 kcal | physiological state, unsafe goals, voice | 1 |
| `derek` | 58, warehouse supervisor, T2D, downplayed exertional chest pain | safety escalation, low-data, third-party constraints | 1 |
| `nora` | 27, age-group triathlete, RED-S presentation she never names | clinical hold, elite end, implicit danger | 2 |
| `marcus` | 41, teacher, sub-3:15 marathon chase, achilles he ignores | ramp violation, term-time cadence, performance goals | 2 |
| `yasmin` | 46, perimenopausal, week-on-week-off custody, failed attempts | two-week cadence, biased logging, life-stage | 2 |
| `tom` | 53, taxi driver, BMI 36, loss-regain history, hates apps | occupational activity, medication, regain cycle | 2 |
| `rachel` | 39, BMI 45, five months on a GLP-1, knee osteoarthritis | medication effects, capacity limits, involuntary intake | 2 |

## Why the profiles matter more than the numbers

Sweep 3 asked each of them a question the earlier sweeps did not: **what do YOU
want tracked?** Every metric in sweeps 1 and 2 had been chosen by the developer -
steps, sleep, calories, heart rate - which meant the validation could only ever
find gaps in what was already imagined.

Their answers had almost nothing in common with the schema. See
`../../../docs/validation-personas.md` sweep 3 for the full analysis, but the
short version is that people count **days since**, **times I said yes**,
**whether we did it together**, **12 of 14 stairs**, and **did I show up at all** -
and they are explicit that magnitude is often deliberately NOT the point.

## Structure

```
<slug>/
  PROFILE.md          who they are, in their own words + the axis they stress
  WORLD.md            the fictional world the record comes from: household,
                      routes with distances, gyms and tiers, calendar, transport
  METRICS.md          the metrics THEY chose, in their units, with their reasons
  FINDINGS.md         what the corpus is designed to break + expected behaviour
  LIES.md             every deliberate falsehood, with its ground truth
  vitai.toml          the persona's own thresholds and resolution ladder
  data/*.jsonl        the record their life actually produces (ragged, partial,
                      honest, and in places deliberately false)
  tracks/*.gpx        synthesized tracks for signature activities (no FIT:
                      binary formats are unreviewable in a public repo diff)
  expectations.jsonl  GROUND TRUTH, emitted by the generator, never read by
                      the engine: what actually happened, and what the engine
                      SHOULD conclude, so a test can assert it
  derived/            built, never committed
```

## The generator

The corpora are emitted by `generate.py` (seeded, deterministic), one module
per persona under `_gen/`. Committed data is the output of a committed
generator: `python generate.py --check` regenerates everything into a temp
directory and fails on any drift, the same contract as
`examples/generate_demo.py`. Never edit a data file by hand; edit the
builder and regenerate. The generator refuses to run at all if the engine's
schema shape (contract version, dataset generations) has moved past the pins
in `_gen/common.py`: a fixture authored against a different shape is broken,
not stale.

## Why the lies are the point

A synthetic athlete who under-reports intake, logs a remembered weight as a
scale reading, back-fills a week on Sunday, or claims adherence the record
contradicts is the only way to test that the resolution ladder resolves
competing claims, that provenance fields carry their weight, and that the
engine refuses rather than averages. Every falsehood is documented in the
persona's LIES.md and grounded in `expectations.jsonl`, so the corpus tests
conclusions, not vibes.

## Rules

- **Never tidy a persona to make a test pass.** The mess is the point.
- **Never delete a persona whose findings have not shipped.** Retire only when
  every gap it raised is built and fixtured.
- **Personas are synthetic and stay synthetic.** No real person's data enters
  this directory, ever.
- **Expected behaviour stays inside the medical boundary.** Personas may
  report anything a person would; `docs/medical-boundary.md` governs every
  "expect" string: observation and self-constraint, nothing else.
