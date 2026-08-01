---
title: The medical boundary
---

## What vitai is for

**vitai logs training, nutrition and body data; builds and adjusts training
programmes; and lets you read your own record. It is not intended to identify,
monitor, explain, treat or compensate for any disease, injury or condition.
Where the record is incomplete, or where you have flagged something, the engine
declines to produce a programme, and says only that.**

Everything below derives from that sentence. If a proposed feature cannot be
described by it, the feature is out of scope, and the answer is to drop it
rather than to reword it.

## Why the line sits here

Because a training log that routes its user to care is a bad training log.

The concrete failure this came from: a medical to-do sat open in a record for
weeks and was re-raised at every review, because it had no exit its owner could
reach. It was not resolvable by anything the tool could observe, so it never
closed, and a gate with no attestable exit is a wall rather than a gate.
Meanwhile it displaced the thing the record is actually good at.

Three reasons that generalise:

1. **The engine cannot see what it would be judging.** It holds numbers you
   typed and a watch reported. Turning that into a view about your body is a
   claim the inputs do not support, and a confident wrong one is worse than a
   blank.
2. **An uncompletable item is a permanent failure state.** Anything the tool
   tracks but cannot close accumulates, and accumulating unresolved items is
   how a record stops being read.
3. **You are the one with standing.** Deciding whether something needs looking
   at is yours. A log of runs and weights adds nothing to that decision and
   should not insert itself into it.

None of this costs the engine anything it needs. Every safety behaviour vitai
has is expressible as an observation about the record plus a refusal to
program.

## Withholding is safe; the reason attached to it may not be

Emitting nothing asserts nothing, so declining to produce a programme is always
available. The claim, if there is one, lives in the sentence that explains the
refusal:

- *"Training is not advisable while you are symptomatic."* A judgement about a
  person's body. Out of bounds.
- *"The engine has no basis to program this week."* A statement about the
  engine's own inputs. Fine.

Identical behaviour, and only one of them is a claim.

## Every gate exits on the record, never on a person

A gate whose exit condition is "a clinician has reviewed you" is not a gate, it
is a wall: you cannot reach it through the tool, so the state is permanent as
far as anything here can tell, and a permanent warning is one that gets
dismissed.

Every escalation level therefore states its own exit, and each one is something
you can satisfy by recording what is true. What you do about your health is
yours to decide; the SYSTEM's state is something you can always change.

## The one exception

The acute tier keeps an instruction, and it is a closed list of two: chest pain
with the features that make it cardiac until proven otherwise, and losing
consciousness.

**Calling emergency services is not an appointment.** It is an act you can
perform immediately, alone, at any hour, with no gatekeeper, which is exactly
what makes it different from naming a professional to go and find. That
distinction is the whole carve-out, and this list is short and closed on
purpose.

## How it is enforced

Not by good intentions. Three deterministic checks run in CI:

- A **boundary lint** over the whole public surface: README, docs, wiki,
  skills, templates, source comments and CLI help. Marketing copy asserts an
  intended purpose exactly as strongly as code does.
- A test that **no message you read names a condition**. Describing an
  observable state is fine; naming the syndrome is a diagnosis whoever says it.
- A test that the module **never claims to watch for anything**, over comments
  as well as strings, because a comment reads as the authors describing what
  they built.

Plus a fixture that hashes the acute strings, so softening one is a deliberate
act rather than an edit.

## How to write about this

The rationale published alongside a design is itself a public statement about
the product. **Explain a boundary by what it is good for, never by how it makes
the project look.** If the only argument for a design choice is how it will be
characterised, that is usually a sign the choice is weak on its own terms.
