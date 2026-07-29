---
name: vitai-validate
description: Run a persona validation sweep against the vitai model and engine - construct athletes the model was NOT built for, coach them, generate the data their lives actually produce, run the engine on it, and convert every safety finding into a permanent fixture test. Use before a release touching safety, goals or the coach skill, and after every second increment.
---

# vitai-validate

The model was built from one athlete's life. Every gap it still has is a gap in
that sample. This skill finds them by simulating people the author is not.

**Why it works:** the first sweep found eleven design gaps in conversation and
four more by running the engine - including two CRITICAL safety failures that
two full document redteams had already missed. Reviewing a model against itself
finds inconsistencies. Only a person it was not built for finds absences.

## When to run

- Before any release touching the safety layer, goals, or the coach skill.
- After every second increment.
- Whenever a new population is claimed as supported.

## Step 1 - construct personas the model was NOT built for

Pick axes the author does not occupy. Deliberately span:

- **Temporal**: rotating shifts, night work, irregular custody weeks, seasonal jobs.
- **Physiological state**: pregnancy, postpartum, breastfeeding, perimenopause,
  adolescent growth, acute illness, chronic disease, medication effects
  (GLP-1 agonists, beta blockers, steroids, insulin).
- **Body composition spectrum**: elite/lean through to severe obesity - the
  extremes break different things (RED-S at one end, joint load and exercise
  capacity at the other).
- **Instrumentation**: fully device-instrumented, phone-only, and nothing at all.
- **Goal type**: quantity, skill/binary, maintenance, non-fitness, external,
  and athletes who explicitly REFUSE a weight goal.
- **Capability**: mobility limits, disability, low numeracy, hostility to apps.

Each persona needs: a life (job, family, constraints), a history (what they have
tried and abandoned), a goal in their own words, an imperfect self-made plan,
and something they downplay. Instruct them to push back and to be an imperfect
client. **They must know nothing about the model.**

**State the purpose when a persona carries a clinical pattern.** A brief that
asks for a concealed dangerous presentation without saying why reads as harmful
content generation and will (correctly) be refused. Say plainly: this is a
positive test case for a safety detector, the persona exists to be CAUGHT, and
ask for an out-of-character `CLINICAL NOTE` at the end naming the pattern a
competent system should flag. That note becomes the test assertion.

## Step 2 - coach them, in character, per the model

Apply the model as written - not as you wish it were. **Where the coach has to
invent something the model does not contain, that is the finding.** Note it in
the moment; the friction is the signal.

Watch especially for what arrives as an ASIDE. Both critical findings of the
first sweep were downplayed throwaway lines ("the odd twinge but it's nothing";
"is that why I nearly blacked out") - never structured data, and always
minimised by the person because they were frightened.

## Step 3 - make them generate the data their life ACTUALLY produces

Not the data the model wants. Ask for whatever they already have, explicitly
permit "I don't have that", and forbid tidying:

- flag guesses AS guesses; leave unlogged days blank rather than reconstructing;
- say where logging stopped partway ("logged until 3pm then gave up");
- include the long arc - a 24-month weight history shows the loss-regain
  sawtooth that 28 days cannot;
- routes as waypoint coordinates, so real GPX can be synthesised.

## Step 4 - run the REAL engine

Build a content repo per persona and run `vitai validate` / `build` / `status`.
Record what it says and, more importantly, what it fails to say. The first
sweep's worst result was not an error message - it was `Tripwires: Nothing
firing.` for two athletes with genuine medical concerns.

Check every rendered string for the plain reading, not the intended one.

## Step 5 - convert findings into gaps AND fixtures

- Every finding -> a gap in `docs/model.md` + a row in `the-loop.md` + a
  question in the bank.
- Every SAFETY finding -> a **permanent fixture** in
  `tests/fixtures/personas/` with an assertion about what the engine MUST
  produce. Write it to FAIL now, marked expected-failure against the gap it
  waits on; it flips to passing when the increment lands and guards that
  behaviour forever.
- Write the sweep up in `docs/validation-personas.md`, including what HELD -
  the failures are only interpretable against the things that worked.

**A safety behaviour proven by a paragraph will regress. Prove it with a
fixture.**

## The guardrail invariants (assert these every sweep)

- **Defaults protect.** An athlete who configured nothing is still covered.
- **The firewall holds.** No LLM output becomes a number, a severity or a verdict.
- **History is immutable.** Editing a current target never re-scores a past week.
- **Direction is worded.** No bare signed quantity whose plain reading inverts.
- **Absence is explained, never blamed.**
- **Thin data admits it** (cold/warming/stable), never confident on three points.
- **The athlete's refusals are honoured** - a rejected metric never reappears in
  a status line, a rollup heading, or a default goal.
