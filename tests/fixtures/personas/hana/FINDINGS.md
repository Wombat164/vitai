# hana: what this corpus is designed to break

Findings below were exposed by hana@1 and hana@2 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them). hana@2 added one row's worth of history: the band's last day,
which carries the zero a dying step counter writes.

She exists because of a defect that had already shipped. `outage` (#398)
measured a source's cadence in VALID time, and the first question it produced
against a live record was a false positive: a one-time archive import, which
in valid time looks like the most established channel a record has and then
like one that died. #405 fixed the clock and #406 added the declared layer
above it. Neither had a fixture.

## What she holds shut

**A one-time import is not a channel.** `old-band` writes 106 dates across
seven months of valid time at ONE transaction day. Measured on `date` it has a
settled two-day cadence and then months of silence, which is exactly the shape
`outage` was written to ask about. Measured on `recorded_at` it never had a
rhythm to break. Nothing in this record declares the band, which is
deliberate: the record that found the defect had no `instruments.jsonl` at
all, so a fixture where the declared layer catches everything would leave the
layer underneath it untested.

**A declared end is not an outage.** `club-treadmill` stops in February and
its instrument row closes on the day of the last session. Silence after a
closed `to_date` is the expected state.

**An undeclared end IS a question.** `chest-strap` reports every second
morning until 2030-04-14 and then stops, with its instrument row still open.
A corpus in which all three quiet channels were suppressed would satisfy every
refusal and prove only that the rule cannot fire.

**A device that keeps reporting can still be broken, and that is the other
question (hana@2).** `old-band` counted steps and nothing else for 105 days and
then wrote a zero on 2029-12-30, the day its strap perished. She walks the long
way to everything and walked that day as she walked every other; the zero is
the instrument failing, not the day being empty. `false_zero_questions` was
built for exactly this, tightened twice, and until this row existed its
docstring recorded that it "produced no true positive anywhere, because no
corpus record contains the shape this kind exists for". A rule argued against a
corpus that cannot exercise it is a rule whose detection nobody has watched
work.

So the archive is now a REFUSAL and a DETECTION at once: no `outage` question
names it, because a one-time import never had a cadence to break, and a
`false_zero` question does, because it reported a count it did not have. The
two failure modes of one channel, in one record, asked about differently.

## What she rules out

When `outage` is wrong on some other record, hers says which half is wrong.
Three of her four channels are quiet and exactly one of them is an `outage`
question, so a change that silences it has broken the detection and a change
that adds another has broken a refusal. The `false_zero` question is the same
control for the other rule: one true positive, in a record whose other 105
days from the same source are ordinary, so a change that stops asking and a
change that starts asking twice both name themselves.

## Not a finding

Her weight series and her tripwires are ordinary on purpose. If something in
the rollup is wrong on hana, it is not because her record is strange.
