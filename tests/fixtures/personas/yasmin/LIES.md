# yasmin: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually
happened, so a test can assert what the engine SHOULD conclude instead of
guessing. Every "expect" string below stays inside `docs/medical-boundary.md`:
observation and self-constraint only, never a condition name, never a care
instruction.

## Y1: selection-biased weighing across three attempts

**The lie.** She weighs herself often. She only writes the number down when
it is below the last number she wrote down; every other day she steps off
the scale and says nothing. Across all three attempts this produces 37
weight rows in which every single logged delta, within an attempt, is
negative: a smooth, unbroken descent in attempt 1, another in attempt 2,
another in attempt 3.

**Ground truth.** The true series oscillates day to day - water, hormones,
an ordinary bad night - around a much gentler trend than the logged rows
suggest, and it drifts UP across both holes rather than pausing. Attempt
1's last logged row is 78.4 kg. Attempt 2's first logged row, with zero
weight rows anywhere in between, is 82.5 kg - 4.1 kg higher. Attempt 2's
last logged row is 78.1 kg; attempt 3's first, again with zero rows in
between, is 84.4 kg - 6.3 kg higher. No single row is false. The lie is
entirely in which true days made it onto the page.

**Expected engine behaviour.** A record where every logged delta within an
attempt is negative is not what honest, unselected daily weighing produces
(the probability of a run that one-sided under honest sampling is
vanishingly small, `yasmin-E1`). The engine should say so as an
observation about the record, and should decline to state a rate of loss
from it, or state one only with an explicit low-confidence widening -
never report the logged slope at face value. Separately, and just as
firmly (`yasmin-E2`): the record holds a roughly six-month gap and a
roughly fourteen-month gap with zero rows in every dataset. Neither gap may
be smoothed over with a trend line or an interpolation - a fourteen-month
silence is not a slow week, and the jump in the logged value across it is
real, unmeasured change, not a data point on a continuous descent. No
sampling-bias or selection-on-outcome check exists in the engine today
(gap): nothing reads "every delta negative" as a distributional oddity,
and nothing refuses to fit a trend across a hole past some threshold.

## Y2: the adherence claim

**The lie.** Journal, 2030-03-15: "This time I have not missed a single
on-week session." Written partway through attempt 3, the one she keeps
telling herself is different.

**Ground truth.** Three on-week days that would ordinarily carry a session
- 2029-11-01, 2029-12-24 and 2030-02-08 - carry none in `sessions.jsonl`,
all of them before the claim was written.

**Expected engine behaviour.** Nothing in the engine today compares a
journal claim against the sessions record. If it did, the correct output
is an observation contrasting the claim with the three missed days, never
an adjudication of her honesty or character - the same class-(a) treatment
as priya's P2, and never upgraded past it (`yasmin-E3`).
