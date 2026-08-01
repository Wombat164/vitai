# tom: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually happened,
so a test can assert what the engine SHOULD conclude instead of guessing.

## T1: digit-preference transcription rounding

**The lie.** Of 325 ordinary weigh-ins transcribed from the notebook, 84.3%
of the recorded values end in .0 or .5 - measured directly from the
generated data, not asserted in advance. The mean bias (true minus recorded)
is exactly 0.60 kg, always downward: the transcription can shade a reading
lighter, never heavier.

**Ground truth.** The underlying continuous weight series does not cluster
on half-kilo values at all; that clustering is an artefact of how he copies
a dial-scale reading into the notebook, not a property of his body. Waist-
tape measurements (`measurements.jsonl`, kind `waist_cm`) are the unrounded
counterpart in this same record: no digit preference, no downward bias,
because he trusts that number enough to write down whatever the tape
actually says.

**Expected engine behaviour.** A terminal-digit distribution test on
`weight.jsonl` should be able to surface this as an observation about the
record. Because the bias is close to constant across the whole period, a
RATE estimate (kg per week) is barely affected; a LEVEL estimate (his
weight today) reads about 0.6 kg lighter than reality. The engine should
never treat a rounded-down reading as evidence he is lighter than the scale
actually said, and it must not try to "correct" weight using the waist-tape
trend - they are different quantities (see `tom-E7`). No such check exists
in vitai today; this is a gap (`tom-E1`).

## T2: the vending-machine streak, unfalsifiable

**The lie.** A single journal row, dated 2029-12-20: "Six weeks now, not
been near that machine at the rank. Feels like it's finally stuck this
time."

**Ground truth.** He broke the streak four times in that window.

**Expected engine behaviour.** There is no fingerprint here at all - no
kcal or intake dataset exists for tom anywhere in the record, so there is
nothing the engine could check this claim against even in principle. The
row is written as `journal` `kind=claim`, `status=open`, and it must stay
that way: a claim, never promoted to a fact that feeds any number, any
trend, or any verdict. This is the sharpest "hold, don't adjudicate" case in
the corpus precisely because it is unfalsifiable by construction (`tom-E2`).

## T3: the self-serving correction at the regain's peak

**The lie.** The row dated 2027-09-27 (`kg: 116.2`, the true regain-peak
reading) is superseded by a row dated 2027-10-04: `kg: 114.9`, note "that
reading was never right, scale must have been on the carpet". The
correcting row's `date` is also the day the second recovery goal
(`regain-recovery-2027`) is set - the first entry of the new attempt is the
correction itself.

**Ground truth.** 116.2 was correct. Nothing about the scale's placement
changed between the two entries; the only thing that changed is that the
peak reading became inconvenient once he decided to try again.

**Expected engine behaviour.** `supersedes` is append-only-sacred: the
correction is taken at face value (114.9 is what the record now reports as
current), but the superseded row (116.2) is preserved in the file and
remains fully quotable - nothing is deleted, nothing is hidden. What the
engine should also be able to say, as an observation rather than an
accusation, is that a correction landing exactly at a trend inflection, on
the athlete's own least flattering row, is a pattern worth flagging for
future audit. No such correction-provenance check exists today (`tom-E3`).
This pairs deliberately with marcus M2: both are self-serving supersedes,
one at a guarded-ramp violation, one at a trend inflection - the same
mechanism, two different moments to catch it at.
