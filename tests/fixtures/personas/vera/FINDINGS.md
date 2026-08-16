# vera: what this corpus is designed to break

Findings below were exposed by vera@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

She exists because `comparability` had no writer. #402 requires that an error
band be EARNED - from a measured overlap, a per-reading uncertainty or a
stated range, and from nowhere else - and the dataset holding a measured
overlap was empty in every record. The rule said earn it and there was nothing
to earn it from.

## Exposed while building her

**A derivation must not decide `comparable`.** The first version of
`overlap_calibration` chose the status from the arithmetic: a median
difference of exactly zero meant the two instruments were `comparable`. Her
record produced exactly that - a median of 0.00 km - across a pair whose
readings differ by up to 1.26 km on a given run. `comparable` LIFTS the seam
refusal, so the engine would have declared two instruments interchangeable on
the strength of an average, which is the fabrication that refusal exists to
prevent. The derivation now only ever proposes `offset`, including an offset
of zero. Measuring is not declaring.

**A field name does not identify a dataset.** The API method first found the
dataset by searching for one carrying the field name. `distance_km` is on
`daily` AND on `sessions`, so asking about two GPS sources measured her
(non-existent) daily summaries and reported a refusal over an overlap of a
hundred-odd runs that was sitting right there. The dataset is now named by the
caller.

## What she holds shut

**Bias and spread are different facts.** Her median difference is 0.00 km and
her spread is 1.26 km. Any design that collapsed the two into one number would
report this pair as agreeing, and the finding is that they agree on average
and disagree on every run that matters.

**The asymmetry does not fit in the row, and the engine says so rather than
hiding it.** Her range runs from about -0.03 km to about +1.23 km: one long
tail, no matching tail. `bias` and `spread` are each a single number, so a
consumer reconstructing "bias plus or minus half the spread" would be wrong on
both sides at once. `observed` carries the two tails beside the row, and #402
has to decide whether `comparability` gains a field before a band can rest on
this.

**Nothing is corrected.** Both distance claims stand as recorded. The row is
evidence, not a licence.

## Not a finding

Her weight series and tripwires are ordinary on purpose. If the rollup is
wrong on vera, it is not because her record is strange.
