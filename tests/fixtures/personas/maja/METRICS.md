# maja: what the numbers do

## Sets

Four machines, three working sets each, two machines per session. About 816
set rows over nine months.

| machine | frame | load | unit |
| --- | --- | --- | --- |
| leg press | plate-loaded sled | 120 kg rising | kg |
| chest press | selectorised | pin ~45 | null |
| seated row | selectorised | pin ~52 | null |
| leg curl | selectorised | pin ~38 | null |

Load drifts up about 0.06% per day from the start, so roughly a 16% rise over
the record - slower than the set-to-set variation, and only visible over
months.

Every set carries `seat_pos`, `pad_pos`, `lever_pos` and `angle_deg` where the
machine has one, and `rir` rather than `rpe`.

## Nutrition

| field | mean |
| --- | --- |
| protein_g | ~142 |
| carb_g | ~210 |
| fat_g | ~66 |
| fibre_g | ~27 |
| sugar_g | ~58 |
| sodium_mg | ~2400 |

`kcal_in` is computed from the macros at 4/4/9, so the row is internally
consistent by construction: a consumer checking energy against macros finds
them in agreement, which is the case it should handle before it meets a
record where they disagree.

## Sleep

About 7.6 h, lights out around 23:00. Ordinary, deliberately: her fixture is
about sets and labels, and a second confound would make it impossible to say
which one an engine tripped over.
