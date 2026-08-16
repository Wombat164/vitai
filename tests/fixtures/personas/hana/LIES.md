# hana: deliberate falsehoods and their ground truth

**There are none.** Every value in this record is what it claims to be.

That is deliberate and it is the point of her. The other records in this
corpus carry constructed falsehoods so a test can assert what the engine
should conclude instead of what a wrong record says. Hers carries none,
because the thing she is built to exercise is not a wrong value - it is four
channels that are all telling the truth and three of which have stopped, where
the engine's job is to work out which silence is worth a question.

A falsehood here would muddy that: an engine that asked about `chest-strap`
for the wrong reason would still look right.

`expectations.jsonl` therefore holds only `behavior` rows, and
`test_every_documented_lie_has_ground_truth` is satisfied vacuously - there
are no `lie` rows for this file to account for.
