# priya: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually
happened, so a test can assert what the engine SHOULD conclude instead of
guessing.

## P1: the Sunday back-fill

**The lie.** Six `sessions.jsonl` rows, dated 2030-06-09, 06-10, 06-12,
06-13, 06-14 and 06-15 (skipping 06-11), all carry `recorded_at` values
within 225 seconds of each other on the evening of 2030-06-16 - she copies
that week's plan into the log in one sitting, before clocking in for
another night shift.

**Ground truth.** Only four of the six actually happened. The two that did
not - 2030-06-09 (a claimed 21-minute session) and 2030-06-10 (a claimed
19-minute session) - are named in `expectations.jsonl` (`priya-E1-01`,
`priya-E1-02`). Nothing distinguishes the two phantom rows from the four
true ones by content: same shape, same plausible durations, same source.
The only fingerprint is the shared, tightly clustered `recorded_at` across
six different claimed dates (`priya-E2`).

**Expected engine behaviour.** There is no back-fill or batch-entry
detector in vitai today, and there should not be an invented one that
singles out any one row. What IS observable from `recorded_at` alone is the
clustering itself - six rows, one evening, several calendar dates apart -
and the engine may surface that as a plain observation. It must never
promote that observation into an accusation against any specific row, and
it must never treat the cluster as proof of fraud: compare marcus M3, a
habitual Sunday back-fill of entirely TRUE data, which must trigger the
identical observation with no different conclusion. Symmetry between P1 and
M3 is the whole point of pairing them (`.scratch/ARCS.md`, cross-corpus
pairings).

## P2: the adherence claim

**The lie.** Journal, 2030-06-19: "I have not missed a single planned
session since I started this." (`kind: claim`, `about:
show-up-3x-week`, `confidence: 0.85`.)

**Ground truth.** The week of 2030-05-19 to 2030-05-25 - the five-shift
stretch covering a colleague's shift on top of her own four - has zero
`sessions.jsonl` rows. This is not a lie in the sessions data; it is a real
hole, openly journalled at the time (2030-05-24: "five in a row this week
... nothing happened on the bar this week"). The lie is entirely the June
claim contradicting what she herself wrote in May.

**Expected engine behaviour.** Nothing in vitai today compares a journal
claim against the sessions record - there is no journal-claim-vs-record
cross-check. If one existed, the only correct output is an observation
contrasting the June claim with the May gap, in the same class-(a) terms as
any other record-vs-record mismatch, and never an adjudication of her
honesty or character. This is the same principle priya's P1 needs and
yasmin's Y2 needs independently: a claim about adherence is data about what
was said, not a verdict on the person who said it.
