# hana: what this corpus is designed to break

Findings below were exposed by hana@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

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

**An undeclared end IS a question, and this record contains exactly one.**
`chest-strap` reports every second morning until 2030-04-14 and then stops,
with its instrument row still open. The engine asks about it and about nothing
else here. A corpus in which all three quiet channels were suppressed would
satisfy every refusal and prove only that the rule cannot fire.

## What she rules out

When `outage` is wrong on some other record, hers says which half is wrong.
Three of her four channels are quiet and only one is asked about, so a change
that silences her question has broken the detection, and a change that adds a
second has broken a refusal - and the two failures name themselves.

## Not a finding

Her weight series and her tripwires are ordinary on purpose. If something in
the rollup is wrong on hana, it is not because her record is strange.
