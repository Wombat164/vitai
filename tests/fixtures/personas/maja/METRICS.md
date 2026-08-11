# maja: what the numbers do

Measured off the committed corpus.

## Sets

Four machines, three working sets each, two machines per session. 816 set rows
over nine months.

| machine | frame | top-set load | unit |
| --- | --- | --- | --- |
| leg press | plate-loaded sled | 120.0 to 140.0 | kg |
| seated row | selectorised | 52 to 60 | null |
| chest press | selectorised | 45 to 52 | null |
| leg curl | selectorised | 38 to 44 | null |

A PIN IS A WHOLE NUMBER and a plate load is not. The sled quantises to 2.5 kg
because that is the smallest disc; the three stacks are integers because the
number is a position in a column. The first version computed all four with the
kilogram formula, so the stacks carried 37.5 and 42.5 under a comment
asserting they were pin positions.

Top-set load rises 15.4% to 16.7% over the record depending on the machine -
the quantisation moves each one differently - which is slower than the
set-to-set variation and only visible over months.

Every set carries `seat_pos`, `pad_pos`, `lever_pos` and `angle_deg` where the
machine has one, and `rir` rather than `rpe`.

The leg curl is unilateral and alternates left and right over the whole
record: 102 sets each. It alternates on a running count rather than on the set
index, because the leg curl only falls in one half of the rotation and a
parity taken from the session index never flips.

## Nutrition

| field | mean |
| --- | --- |
| protein_g | 141 |
| carb_g | 213 |
| fat_g | 68 |
| fibre_g | 27 |
| sugar_g | 58 |
| sodium_mg | 2391 |

`kcal_in` is computed from the macros at 4/4/9 on every row, so a consumer
cross-checking energy against macros finds them in agreement - which is the
case it should handle before it meets a record where they disagree.

One day, 2030-03-11, is logged twice: as a daily total and as seven items off
packets. The total is computed FROM the items, so the two agree. They were
drawn independently in the first version and disagreed by 29 g of protein.

## Sleep

About 7.6 h, lights out around 23:00. Ordinary, deliberately: her fixture is
about sets and labels, and a second confound would make it impossible to say
which one an engine tripped over.
