# Persona doctrine

How the validation corpus works as an institution: what makes a persona valid,
how one is versioned, when a finding counts, and when a persona may change.

The corpus itself lives in `tests/fixtures/personas/` and its README is the
index of who exists. This document is the set of rules that index obeys.

## What a persona is for

A persona is a **test oracle in the shape of a person**. Its job is to produce
engine outputs that can be judged right or wrong by someone who knows what the
person's life actually was.

That framing settles most arguments. An oracle that cannot be wrong is not an
oracle; an oracle that changes silently is worse than none, because the tests
keyed to it keep passing for reasons nobody checked.

## The five properties of a valid persona

A persona that fails any of these is decoration.

### 1. It can fail

There is at least one concrete expectation that would break if the engine
regressed. "Stresses temporal structure" is an intention, not a property. "Her
week starts Thursday and a Monday-anchored rollup mis-bins four of seven
sessions" is a property, and it is checkable.

### 2. It carries contradiction, with ground truth

At least one deliberate falsehood, recorded as such where a test can read it,
never only in prose. A weight entered from memory and captured as a scale
reading; a week back-filled on Sunday; adherence claimed against a device that
disagrees.

This is the whole reason the corpus can test the resolution ladder,
`capture`, `value_kind` and refusal. A record with no competing claims exercises
none of it. **Every planted falsehood pairs with the truth it hides**, or the
test can assert only that something happened, not that the right thing did.

### 3. It names a metric the schema cannot express

This is the rule that keeps the corpus from being a mirror. Validation built
only on metrics the developer chose can find gaps only in what the developer
already imagined; the corpus's own sweep 3 is the evidence, where the answers
to "what do YOU want tracked" were days since, times I said yes, whether we did
it together, 12 of 14 stairs, and did I show up at all.

**If a new persona has nothing the schema cannot hold, it was built from the
schema and it will confirm the schema.** Send it back.

### 4. It is not a variation of the author

Being synthetic is not sufficient. Eight fictional athletes who all reason like
the person who wrote them are one persona with eight names, and they will agree
with the model for the same reason the author did.

The check is not demographic box-ticking. It is whether the persona would
*disagree* with the engine's framing: about what counts as progress, whether a
number should exist at all, what is worth logging, what a bad week means.

### 5. It is honest about its own coverage

The corpus states what it does NOT cover. Eight personas is a sample, and a
fixture set that implies completeness is the same failure as a dashboard that
implies coverage it does not have.

## Versioning

Three different things drift and they are not the same version.

### The schema generation the corpus was authored against

Corpus-wide, mechanical, and a **hard failure** rather than a warning. Pin the
per-dataset `CURRENT_GENERATION` values and the `CONTRACT_VERSION`, and stop
generation when the installed engine has moved past them.

Do NOT pin the package version. `__version__` rises for a docs fix with no
schema change and stays still while the schema moves. Both directions are live
in this project's own history. Record it as provenance for a bug report; never
gate on it.

A fixture exists to be asserted against, so one authored against a different
shape is not a note in a log. It is broken.

### The persona's own version

Per persona, never corpus-wide: a change to one person's history has no bearing
on another's findings, and a shared number would invalidate everything on every
edit.

**`persona_version` bumps when the person's history changes in a way that could
change an engine output.** Their arc, the dates, the values, the placement of a
falsehood, the metrics they chose.

It does NOT bump for prose in the profile, a typo, or recording a new finding.
Those describe the persona; they are not the persona.

### The seed, if generated

Seed plus generator plus schema generation must reproduce the corpus byte for
byte. Dates come from an epoch passed in, never from the wall clock, or the
fixtures rot at midnight and the failure looks like a regression.

## Personas are append-only, like the record they test

This is the rule the other versioning rules exist to serve, and it is the same
doctrine the engine applies to its own data.

**Once a persona has exposed a finding, its history is evidence.** Editing it
breaks the link between the finding and the thing that produced it, and the
regression test keyed to that finding will keep passing without anyone noticing
it now passes for a different reason. That is the worst available outcome: a
green test guarding nothing.

So:

- **Extend rather than edit.** A persona whose life needs to continue gets a
  new epoch appended, not a rewritten past.
- **Supersede rather than overwrite.** If an arc was genuinely wrong, add the
  corrected persona and mark the old one superseded, keeping both while any
  shipped test depends on the old one.
- **A retired persona's data stays** as long as anything asserts against it.
  Retirement means no longer extended, not deleted.

## Findings

- **A finding records the persona version that exposed it.** `nora@2 exposed
  G91`. Without that, a later version of nora cannot be checked for whether the
  evidence still exists.
- **A finding is not a finding until it has a gap number or an issue.**
  Otherwise the findings file becomes a diary, and nothing in it is actionable
  or closable.
- **A persona may not be tidied to make a test pass.** The mess is the point,
  and a fixture adjusted to suit the engine has stopped being independent
  evidence.
- **A persona is retired only when every gap it raised is built AND fixtured.**
  Shipped-but-unfixtured means the next regression will not be caught.

## What this corpus is not

It is not a benchmark and it does not produce a score. There is no percentage
of personas passing, because a persona is not supposed to pass: it is supposed
to be handled correctly, and "correctly" for several of them means the engine
refuses to answer.

A corpus that reports a pass rate will be optimised, and the cheapest way to
raise it is to tidy the personas.

## Changelog

- 2026-08-01: created alongside the eight-persona corpus, to hold the rules
  that were accumulating informally in its README.
