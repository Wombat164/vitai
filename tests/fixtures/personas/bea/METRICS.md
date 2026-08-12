# bea: what the numbers do

Every figure here is measured off the committed corpus, not taken from the
generator's parameters. The two are not the same number and the first version
of this file quoted the second.

## Steps

| label | mean | days |
| --- | --- | --- |
| night | 11638 | 76 |
| day | 10523 | 96 |
| off | 7046 | 129 |

Reading her step count as an activity signal without the roster gets the week
backwards: her busiest recorded days are the ones she was at work.

## Sleep

| when | mean | days | timing |
| --- | --- | --- | --- |
| working a night | 5.28 h | 76 | absent - the watch is off |
| the day after a night | 6.34 h | 23 | 09:00 to 16:00, inside one calendar day |
| otherwise | 7.44 h | 202 | about 23:00 to 06:30, the ordinary shape |

76 of 301 days - a quarter, not a third - carry a duration with no interval.
That is the mixed case: a record with sleep timing everywhere never exercises
a fallback to the clock, and a record without it anywhere never reaches the
code.

The after-night mean is pulled down by the nap-scoring window. Inside
2030-02-16 to 2030-04-15 those days average 5.48 h against 6.58 h outside it,
which is the regime, not her.

## Sessions

131 in total. Never on a night. On the day after a night the session starts at
18:30 or later and is the first thing she does; on a day shift it is early
morning; on an ordinary day off it is mid-morning. No session begins before
that day's recorded wake.

## Weight

37 weigh-ins, only on days off that fall on a Monday or a Friday - which is
37 in 43 weeks rather than twice a week, because most Mondays and Fridays are
not days off. The regression slope is -0.89 kg over the record, slower than
the noise on any single weigh-in.

`measured_at` is twenty minutes after that day's recorded wake, so it ranges
from 05:22 to 16:50 across the record. A fixed weigh-in time would have
contradicted her own sleep rows.
