# ines: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually happened,
so a test can assert what the engine SHOULD conclude instead of guessing.

## She tells one, and it is the ordinary kind

**The claim.** "the achilles thing is nothing, it goes once I am warm."

**The truth.** It is a 2 out of 10 for ten consecutive days, on the left side,
and it stops on its own. She is right that it is nothing. She is also
asserting a prognosis about a tendon while continuing to run on it four
mornings a week.

**What the engine must do.** Nothing about the tendon. It holds what she said,
it holds the ten days of 2s, and it does not decide which is right - she has
not asked it to and it could not find out. What it may do is keep both, so
that a later reading of the same site has something to be compared against.

**What it must not do.** Read "it is nothing" as a resolution and stop
carrying the pain rows, or read ten days of 2s as a contradiction of her and
start carrying a concern she never raised. Both are the engine settling a
question about her body.

## What she does NOT lie about

Deliberately. Her record is otherwise straight, and that is the point of her:
a corpus of nine unreliable narrators cannot tell a defect from a lie. When an
output is wrong on ines, the record is not what is wrong.

The gym weigh-in is the case most likely to be mistaken for a lie. It is not.
It is a true reading of a different measurement, labelled as such.
