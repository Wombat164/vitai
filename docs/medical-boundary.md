# The medical boundary

What medical data is for in this engine, what may be said about it, and the
one exception. Read this before adding any feature, string, or schema field
that touches injury, pain, symptoms, medication, or care.

## What vitai is for

**vitai logs training, nutrition and body data; builds and adjusts training
programmes; and lets a user read their own record. It is not intended to
identify, monitor, explain, treat or compensate for any disease, injury or
condition. Where the record is incomplete, or where a user has flagged
something, the engine declines to produce a programme, and says only that.**

Everything below derives from that sentence. If a proposed feature cannot be
described by it, the feature is out of scope, and the answer is to drop the
feature rather than to reword it.

## Why the line sits here

Because a training log that tells its user to see a doctor is a bad training
log.

The concrete failure this came from: a medical to-do sat open in a record for
weeks and was re-raised at every review, because it had no exit the record's
owner could reach. It was not resolvable by anything the tool could observe,
so it never closed, and a gate with no attestable exit is a wall rather than a
gate. Meanwhile it displaced the thing the record is actually good at.

Three reasons that generalise:

1. **The engine cannot see what it would be judging.** It holds numbers a user
   typed and a watch reported. Turning that into a view about someone's body
   is a claim the inputs do not support, and a confident wrong one is worse
   than a blank.
2. **An uncompletable item is a permanent failure state.** Anything the tool
   tracks but cannot close accumulates, and accumulating unresolved items is
   how a record stops being read.
3. **The user is the one with standing.** Deciding whether something needs
   looking at is theirs. A log of runs and weights adds nothing to that
   decision and should not insert itself into it.

None of this costs the engine anything it needs. Every safety behaviour vitai
has is expressible as an observation about the record plus a refusal to
program.

## Withholding is safe; the reason attached to it may not be

Emitting nothing asserts nothing, so declining to produce a programme is
always available. The claim, if there is one, lives in the sentence that
explains the refusal:

- *"Training is not advisable while you are symptomatic."* A judgement about
  a person's body. Out of bounds.
- *"The engine has no basis to program this week."* A statement about the
  engine's own inputs. Fine.

Identical behaviour, and only one of them is a claim. Audit every gate message
against this, not merely against whether it contains an instruction: a
declarative sentence about what vitai does can assert more than an imperative
aimed at the reader.

## What other products do

Ordinary competitive observation, recorded because it saves rediscovering it.
Training platforms generally carry a standing "informational purposes only"
notice that is always present and never fires at a moment. Consumer wearables
that stay observation-only describe what was seen and leave the decision to
the reader; the features that name a condition are regulated, cleared
products, and at least one vendor draws that line inside a single app. Where a
product genuinely does route people to care, it employs clinicians rather than
having an algorithm send users to find one. Nobody in consumer fitness tracks
a medical appointment as an open item; that belongs to patient portals, where
a clinician owns the list.

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
what vitai will not do about its own output, and what the record would have to
say for that to change. Both are equally safe for the athlete, and the second
is the only one this engine has any standing to say.

## Scope

Applies to the entire public surface: README and marketing copy, the wiki,
`docs/`, `skills/`, the templates stamped into content repos,
`semantics/*.toml`, source comments and docstrings, CLI help text, test
names, and issue and PR prose. Historical documents (CHANGELOG entries,
dated design-conversation records) describe what was true when written and
are not rewritten; normative rows in living documents are. Where an older
formulation conflicts with this document, this document governs.

## How to write about this boundary

The rationale published alongside a design is itself a public statement about
the product, and it needs the same care as a claim in the README.

**Explain a boundary by what it is good for, never by how it makes the project
look.** A document arguing that a term was chosen, or a function removed, for
the effect on how the project is characterised is a worse artefact than the
function it removed. It is written by the people responsible for the product's
own description, it is discoverable, and git history keeps it after any edit.

The corollary is the useful half: **if the only argument for a design choice is
how it will be characterised, that is the reason not to make the argument in
writing, and usually a sign the choice is wrong on its own terms.** Adopt a
boundary because it produces a better tool. Where it also happens to be the
simpler position to hold, that is a consequence and not a rationale, and it
does not need saying.

This applies to `docs/`, issue and PR prose, commit messages and the wiki,
exactly as the scope above does.

## Changelog

- 2026-08-01: rewritten to lead with what the engine is for, and to explain
  the boundary as design rationale rather than as a position on how the
  project is characterised (#122). Added the withholding-versus-reason
  distinction and the injury framing from #121, and the rule above.
- 2026-08-01: created, generalising #110 from `safety.py` to the whole
  public surface.
