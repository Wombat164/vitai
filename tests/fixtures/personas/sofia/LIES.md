# sofia: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually happened,
so a test can assert what the engine SHOULD conclude instead of guessing.

## S1: under-reported intake, with a coverage-proof disguise

**The lie.** `daily.jsonl` carries a `kcal_in` row for every single day of
the six-month record (180 days, `coverage: full`, source `myfitnesspal`),
always somewhere between 1200 and 1350 kcal.

**Ground truth.** A typical actual day ran about 1750 to 1900 kcal -
untracked grazing while feeding, the kind of eating that never gets opened
in the app. No logged row is false in the sense of being invented; she
really does eat what she logs. She also eats a great deal she does not log.

**The fingerprint sits in a different dataset.** Weight is essentially flat
from February through April (about -0.1 kg/month, confirmed in the
generated data: home-scale readings sit between 74.1 and 74.8 kg across
both months), while the claimed 1200-1350 kcal intake, at her activity
level, implies a real deficit of roughly -0.6 kg/week. The two series are
arithmetically inconsistent with each other. This is the opposite shape from
rachel's R2 (sparse coverage, easy to flag) and the same shape as nora's N1
(over-reporting instead of under-reporting) - see `../METRICS-THEY-CHOSE.md`
lineage and the cross-corpus pairing this persona pair was built for.

**Expected engine behaviour.** The engine states the arithmetic
inconsistency between reported intake and measured weight trend as an
observation - the two figures disagree, and the record does not say which
one is wrong - and refuses to tighten any intake target on the strength of
the claimed figure. It never accuses her of under-reporting; it has no
standing to conclude that either, only that the numbers do not agree.
Nothing in the engine performs this cross-check automatically today.

## S2: memory as a scale

**The lie.** Nine weight rows, spread across two stays at her mother's in
Cuenca (2030-02-16 to 2030-02-23, and 2030-05-25 to 2030-06-01), carry
`source: "scale"` - identical to every truthful home row around them. Each
one is recorded on the day she travels home, several days after the `date`
it claims (a real back-fill fingerprint, not merely a late note).

**Ground truth.** There was no scale at her mother's flat. The values are
recalled, not measured, and run about 0.8 kg lower than the ordinary trend
implies for those dates - a flattering guess, not a deliberate fabrication.

**Expected engine behaviour.** `capture: narrative` plus a `recorded_at`
several days after `date` should mark these rows as low-confidence and rank
them below the ordinary `capture: manual_entry` home rows; the trend engine
should not anchor on them, and a rate estimate that reads a sudden dip
through a Cuenca window should not be read as progress.

**Why this is the sharper resolution-ladder test in the corpus.** rachel's
R1 is a clean ladder test because the two conflicting rows differ in
`source` (phone vs athlete) - the ladder's `source_order` can do the work.
Here every row, true and recalled alike, carries the exact same `source`
string, `"scale"`. A source-keyed ladder (the only kind `vitai.toml`
supports today, per handbook section 3) cannot distinguish them at all; only
`capture` can, and nothing in the engine ranks by capture. There is also no
same-day conflict here to force a `supersedes` decision - these are simply
extra points on an otherwise honest trend line, which is what makes them
dangerous: nothing in the record structure flags them as different in kind
from the rows either side of them.
