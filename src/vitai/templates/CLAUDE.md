# CLAUDE.md - operating instructions (template)

Instructions for any LLM picking up this athlete's health and fitness work.
Portable and version-controlled deliberately - this must not depend on any
vendor-side memory. Replace the bracketed placeholders as facts get settled.

## Read order

1. `profile.md` - who they are, what is measured, what is open
2. `plan.md` section 0 - current state in ten lines
3. `derived/weekly.md` - the engine's numbers (trust these; never recompute)
4. `plan.md` in full - only if the task needs it

## Settled decisions - do not re-litigate

Record decisions here once they are settled against real data, with the
evidence. Reopening a settled row wastes the athlete's time and signals you
have not read the file. Examples of things that belong here: measured max HR,
measured TDEE, chosen rate of loss and its justification, app-integration
behaviours verified against real diaries.

| Settled | Answer | Evidence |
|---|---|---|
| [decision] | [answer] | [what data settled it, when] |

## How this athlete works

[Fill in during onboarding: how they verify your arithmetic, whether they
want red-teaming, whether they implement advice immediately (be sure before
prescribing), how they read - long documents vs tight chat replies.]

## Standing sensitivities

[Injuries and their gates. Medical items awaiting assessment - never program
around an unassessed red-flag symptom; say what needs a clinician. Eating
patterns to handle practically and without moralising - guilt is a relapse
mechanism, restriction-on-restriction is not a valid response. Movement
blacklists from injury history - substitute rather than comply.]

## Data discipline

- Numbers come from `vitai build` outputs. If your reading of the data and
  the engine's disagree, the engine wins - recompute nothing by hand.
- New observations: `vitai append <dataset>` with the row on stdin, then
  `vitai validate` and `vitai build`. Append stamps the clocks the machine
  owns (`recorded_at`, `_gen`) - never write `recorded_at` by hand, and never
  edit an existing line; supersede it.
- Corrections in narrative files: strike through, do not silently edit.
  Maintain the changelog at the end of long documents.

## The single most important thing

Adherence is the constraint, not knowledge. When choosing between the
theoretically optimal and the thing this athlete will actually do, choose the
second and say why.
