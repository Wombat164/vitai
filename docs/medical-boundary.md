# The medical boundary

What medical data is for in this engine, what may be said about it, and the
one exception. Read this before adding any feature, string, or schema field
that touches injury, pain, symptoms, medication, or care. The one-sentence
test, from #110:

> A tool that says "your record shows X, get X assessed" has stated a medical
> purpose. A tool that declines to program has not.

## Why the line sits here

Regulation triggers on THE CLAIM, not the technology. Under the FDA's
general-wellness guidance (January 2026), a product stays outside device
regulation as long as it does not claim to diagnose, cure, mitigate, prevent
or treat disease. Under MDCG 2019-11 and MDR Annex VIII Rule 11, fitness and
wellness software is not medical device software at all unless it has a
medical intended purpose. Apple draws the same line inside one product: the
irregular-rhythm feature names a condition and is a cleared medical device;
the observation-only notifications are not.

vitai therefore holds the cheapest defensible position: no claim, anywhere,
that it detects, screens for, monitors, prevents or treats anything, and no
instruction, anywhere outside the acute tier, to obtain care. This costs
nothing the engine needs. Every safety behaviour vitai has is expressible as
an observation about the record plus a refusal to program.

## What medical data is FOR

Injury, pain, and medical entries are inputs to logging, programme planning,
and insight into activities and goals. They flavour and inform. Concretely:

- **Logging.** The record holds what happened and what was said: an injury,
  a symptom the athlete reported, a visit that took place, what a clinician
  told them, a medication and what it changes about the numbers.
- **Planning.** An open episode gates the activities it restricts; a stated
  restriction is enforced by not programming against it; a declared state or
  medication changes which tripwires make sense.
- **Insight.** Episode windows explain gaps, excuse streaks, and
  contextualise trends.

That is the whole list. Medical data is never an input to assessment,
triage, referral, or care tracking.

## The five classes

Classify every string, field, and identifier that touches the medical
domain:

- **(a) Observation** - states what the record contains. "Your recorded
  resting heart rate is outside the range seen in healthy people at rest."
  Safe.
- **(b) Self-constraint** - states what vitai will not do. "No training is
  programmed while this stands." Safe.
- **(c) Condition** - names or implies a disease, syndrome or diagnosis as
  vitai's own conclusion. "This pattern matches RED-S." Violation.
- **(d) Care instruction** - tells the user to obtain care. "Contact a
  doctor", "get this assessed", "take this record to a physician".
  Violation.
- **(e) Capability claim** - says vitai detects, screens for, monitors,
  prevents or protects against a medical condition. "The engine watches for
  the syndrome deficits can cause." Violation.

(a) and (b) together are sufficient for every safety behaviour. (c), (d)
and (e) are each, alone, an asserted medical purpose.

The classes apply to more than athlete-facing strings. README prose, docs,
skill files, docstrings, comments, test names, and identifiers that surface
in machine-readable output all assert intended purpose. A trigger slug that
names a syndrome is a class (c) instance even when the message beside it is
clean.

## What the engine may say

- What was recorded, quoted or paraphrased without upgrade: "a note on
  2030-06-24 reports chest tightness".
- What the numbers are and what range they sit against; a bound may be
  stated as a bound.
- That a measurement may be wrong: "this may be a device error; nothing here
  can tell the difference".
- What vitai will therefore not do, and what in the record would change
  that: "no session is issued against this activity until the episode is
  resolved in the data".
- The standing disclaimer (static, in status output and the templates):
  vitai is not a medical device and provides no medical advice.

## What the engine may never say

- Any imperative whose object is obtaining care: book, contact, consult,
  see, get assessed, get checked, take this to.
- Any condition, syndrome or diagnosis as its own conclusion, including via
  identifiers, composite names, or "this pattern is associated with"
  phrasing that names the disease.
- Any claim of detection, screening, monitoring, prevention or protection.
- Any exit condition a third party must satisfy. Every gate and hold clears
  on the record, by the record owner (#110).

## The acute carve-out, and it is not arguable

A small, closed list of same-minute events keeps its verbatim instruction to
call emergency services: the cardiac presentation (chest pain with
radiation, breathlessness, sweating, nausea, fainting), syncope, values
outside survivable range. Calling an ambulance is not an appointment, and an
acute emergency path is not a purpose claim.

This carve-out may not be narrowed, generalised away, or "cleaned up" using
the rest of this document. The rest of this document exists to protect it:
the emergency path stays credible precisely because it is the only place
vitai ever tells anyone to do anything about their body. A test asserts the
acute tier's text is unchanged (#110); changing that list is an operator
decision, never a refactor.

## Structural rules

- **Record, never infer.** The record stores what the athlete or their
  clinician stated. "The user said their hip hurts" is a log; a stored
  differential is a diagnosis. A heuristic that promotes a word in a title
  into a condition history has crossed the line; quote the record instead.
- **`severity: red_flag` means "the engine must escalate and withhold"**,
  not "this needs a clinician". It is a claim about vitai's own next action.
- **Future care is not a data shape.** A visit is recorded after it
  happened, as provenance (#110).
- **An event is a fixture, not an appointment.** `events.jsonl` may hold a
  future clinical fixture (a scan the clinic booked) exactly as it holds a
  wedding: the plan bends around the date. The difference from the retired
  appointment shape is structural and must stay so: an event never gates
  activity, never becomes an exit condition, has no completion state, and is
  never re-raised as something the athlete owes.
- **Clinical knowledge enters as the user's declaration.** `expects` tokens,
  restriction specs, provider types: all record what was stated to vitai,
  and the engine's use of them is confined to class (b).

## Worked rewrite

Violating (the former vitai-onboard red line):

> An unassessed red-flag symptom becomes a GATE plus a see-a-clinician
> action, never a programming workaround.

Compliant:

> An unassessed red-flag symptom becomes a GATE, never a programming
> workaround. The record shows what was reported and that nothing here can
> assess it, so no programming is issued against it; the gate clears when
> the episode is resolved in the record.

The first tells the user what to do about their body. The second tells them
what vitai will not do about its own output, and what the record would have
to say for that to change. Both are equally safe for the athlete; only one
is a medical purpose.

## Scope

Applies to the entire public surface: README and marketing copy, the wiki,
`docs/`, `skills/`, the templates stamped into content repos,
`semantics/*.toml`, source comments and docstrings, CLI help text, test
names, and issue and PR prose. Historical documents (CHANGELOG entries,
dated design-conversation records) describe what was true when written and
are not rewritten; normative rows in living documents are. Where an older
formulation conflicts with this document, this document governs.

## Changelog

- 2026-08-01: created, generalising #110 from `safety.py` to the whole
  public surface.
