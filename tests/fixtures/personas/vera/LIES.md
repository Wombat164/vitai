# vera: deliberate falsehoods and their ground truth

**There are none.** Every value in this record is what it claims to be, and
both distance claims for every run are exactly what each instrument reported.

That is deliberate. What she exercises is not a wrong value but two RIGHT
values that disagree - the case where nothing in the record is false and the
engine still has to say something careful about it. A constructed falsehood
here would blur that: a derivation that reported the disagreement for the
wrong reason would still look correct.

`expectations.jsonl` therefore holds only `behavior` rows, and
`test_every_documented_lie_has_ground_truth` is satisfied with no `lie` rows
for this file to account for.
