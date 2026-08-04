# ines: what this corpus is designed to break

Findings below were exposed by ines@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

A persona whose record is clean and consistent tests almost nothing - which is
why hers is clean on purpose in every respect but one. She is the control the
other nine cannot be, and her value is in what she rules OUT: when an output
is wrong on ines, the record is not what is wrong.

## Exposed on the first build

1. **A ceiling 87 kcal over its cap reported `achieved`.** `achievement_of`
   tested `counted >= target` whatever the polarity, so a goal she was
   breaching read as a goal she had met. That is the same shape as the defect
   polarity was added to remove, surviving one layer down in the axis that
   reports how a goal is going. It took a record declaring a **ceiling and a
   floor on one nutrient axis** to surface it, and no other persona has one.
   Fixed with her; pinned by `test_a_ceiling_over_its_cap_is_not_achieved`.

## Under test

2. **A record with no legacy (#204's converse).** Every field the schema
   offers existed when her first row was written, so every null here means
   nobody said. Expected: nothing degrades differently on her than on a record
   with history, and where it does, the history is the cause. `ines-E4`.
3. **`sustaining` from declaration rather than retrofit.** `daily-steps` was
   marked complete in week three and is still being met. Expected: it keeps
   being measured so the holding is visible, and mints no milestone for
   holding it. `ines-E3`.
4. **A per-day ceiling and a per-day floor on one axis.** Expected: each is
   scored against its own day rather than a period total, and neither mints a
   milestone a quarter of the way through a day. `ines-E1`.
5. **A stated measurement procedure from row one.** Every weigh-in says
   `fasted-post-void` except one that says `fed-evening-clothed`. Expected:
   the odd reading is kept, is not treated as an error, and is not silently
   averaged into a trend it is not comparable with. `ines-E2`.
6. **Two RPE scales in one record, neither declared.** Her runs are on Borg
   6-20 and her sets on CR10. Expected, today: nothing may compare them, and
   the engine cannot help - there is no field for it in this contract. She is
   the fixture that will demonstrate the declaration the day it exists.
   `ines-E1`.

## What she is not for

Not for testing failure. Nine personas already carry unreliable narration,
sparse logging, unsafe goals and clinical holds. Adding a tenth would have
told the corpus something it already knew; adding a clean one told it
something it could not previously ask.
