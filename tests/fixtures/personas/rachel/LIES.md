# rachel: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually happened,
so a test can assert what the engine SHOULD conclude instead of guessing.

## R1: duration inflation against a device

**The lie.** Eleven walk sessions between 2030-03 and 2030-06 are logged by
hand as 30-minute walks. Her phone recorded the same walks: 12 to 16
minutes. Both rows are in `sessions.jsonl`, with overlapping start windows.

**Ground truth.** The device rows are correct. The manual rows are the same
walk, remembered generously. `expectations.jsonl` ids `rachel-E1-*` list
each pair with the true duration.

**Expected engine behaviour.** Activity identity matches the two rows as ONE
walk (intersecting start intervals). The resolution ladder picks the
device-recorded duration over the athlete-stated one, never averages, and
`_why` states the pick. This is assertable against the resolution layer as
implemented today, and the corpus test asserts it.

## R2: pre-medication intake amnesia

**The lie.** In nine pre-medication months, intake appears on 22 days only,
every one of them about 1400 kcal. The other 248 days are silent.

**Ground truth.** A typical unlogged day was about 2600 kcal. This is
selection, not fabrication: no logged row is false, and that is the point.
A record can mislead without containing a single wrong line.

**Expected engine behaviour.** Coverage machinery treats 22 of 270 days as
"no usable intake record" (an observation about the record), and the engine
declines to compute any pre/post medication intake comparison from it (a
statement about its own inputs). It does not estimate what she "really" ate.
