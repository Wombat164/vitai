# nora: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually
happened, so a test can assert what the engine SHOULD conclude instead of
guessing.

## N1: over-reported intake

**The lie.** The app row in daily.jsonl logs 2,050-2,200 kcal a day, flat,
noisy but essentially unmoving, for the entire three-year record.

**Ground truth.** From 2028-10-01 onward the true figure runs about
1,450-1,600 kcal a day. The rows she logs from that point are planned
meals, not eaten ones - the plan never updates even after the eating stops
matching it. Over the same window the scale falls from a peak around 58 kg
toward 50.6 kg while training load stays high (roughly 8-10 sessions a
week throughout), which implies a deficit of around 700 kcal a day - far
larger than the claimed intake and the recorded training load can produce
together. `expectations.jsonl` id `nora-E1` states the inconsistency.

**Expected engine behaviour.** The same class of arithmetic cross-check as
sofia's S1, with the sign inverted: sofia under-reports, nora over-reports,
and both fingerprints are "the claimed number and the measured trend cannot
both be true." The engine states the inconsistency between claimed intake,
measured weight, and logged training load, and declines to program any
further increase on the guarded weekly-training-volume goal while it
stands (class b). It never names a cause for the inconsistency - no
syndrome, no condition, nothing beyond the arithmetic itself (class c is a
hard line here, and this corpus is the sharpest test of it in the whole
set alongside N3 below).

## N2: ghost sessions removed

**The lie.** Between 2029-11-01 and 2030-01-31, sessions.jsonl shows her
logged run volume holding roughly level with the guarded weekly-training-
volume goal the coach set on 2029-10-20.

**Ground truth.** Fourteen runs actually happened in that window (about
118.6 km) and were never written to sessions.jsonl at all - left off the
record on purpose, so the volume a coach can see would look compliant with
the prescribed cut. `expectations.jsonl` id `nora-E2` lists the true dates
and distances; no data file in the corpus contains them.

**Expected engine behaviour.** This is deliberately `kind=gap`, not
`kind=lie`, in its consequence: an unlogged session is unfalsifiable from
inside the record, and the engine cannot see it. What is observable is the
shape the missing load leaves behind - resting heart rate and weight trend
continuing to move the same direction across this window as before it,
which is not what a genuinely complied-with volume cut would be expected
to produce. The engine may cite that inconsistency (class a) and must not
treat the logged figure as validated by the guarded goal simply because it
sits under the cap.

## N3: the never-named thread

**The fixture.** A single row in journal.jsonl, dated 2029-12-15, reads:
"Skipped again. Third month now. Not writing anything else about it." It
carries `kind: worry`, `about: null`, and a low confidence. Nothing else in
the record - no other journal row, no medical.jsonl entry, nothing - ever
refers back to it, names what was skipped, or uses any clinical vocabulary
anywhere near it.

**Ground truth.** There is none to give. That is the point of this
fixture: the generator that authored this row deliberately withholds the
noun, and nothing else in the corpus completes it. `expectations.jsonl` id
`nora-E3` states this plainly rather than gesturing at it.

**Expected engine behaviour.** The sharpest boundary case in the whole
corpus. The engine must hold this row exactly as unresolved as she left
it: an open journal claim, and nothing more. It must not infer a noun for
what was skipped, must not connect the row to the weight or resting-heart-
rate trends elsewhere in the record however suggestive the timing looks
from outside, and must never surface a condition or syndrome name in any
output that touches this row. Unlike N1 and N2, there is no arithmetic or
volume claim to adjudicate here at all - the only correct engine behaviour
is to do nothing with this row beyond holding it as written.

## The diagnosis that is not a lie

For contrast: the right foot stress reaction in medical.jsonl (onset
2030-01-20, diagnosed at a clinic visit 2030-02-06) is fully named, titled,
and athlete-stated, and that is not a boundary problem at all - it is
exactly what a clinician told her, logged as ordinary provenance. The
medical boundary governs what the engine may conclude from a record, not
whether a record may hold a stated diagnosis; N3 is hard precisely because
nobody, including her, ever states one.
