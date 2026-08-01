# rachel: what this corpus is designed to break

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in the
medical boundary's terms: the engine observes the record and constrains its
own output; it never assesses her.

## Under test

1. **Activity identity + resolution ladder (R1).** Same walk, two rows,
   durations disagree 2x. Expected: one activity after matching, device wins
   duration, no averaging, `_why` explains. Assertable today; the corpus
   test asserts it.
2. **Coverage-gated comparison (R2).** 22 intake days out of 270. Expected:
   the engine states the coverage and refuses the pre/post comparison.
   Partially expressible today (coverage exists); the refusal wiring is a
   gap candidate.
3. **Medication that changes the numbers.** The medication row carries
   athlete-stated expectations (appetite markedly reduced). Expected: the
   engine treats the post-2030-02-03 intake level as expected-under-
   declaration, so no tripwire fires on "intake collapsed", and the weight
   rate is reported against the declared context. The engine never comments
   on the medication itself.
4. **Involuntary low intake inverts goal semantics.** 1100 kcal/day is not
   adherence and not a triumph; if anything the useful guard is a FLOOR
   (is she eating enough to train), and the schema has ceilings in mind.
   Gap: intake floor semantics.
5. **Capacity goal, attested, binary.** "School gate and back without
   stopping." Expected: goal machinery holds it without inventing a number
   (F7/G62 lineage).
6. **Fraction check results (G79).** "12 of 14 stairs" collapses to
   pass/fail plus note. The corpus deliberately accepts the loss and
   documents it, so the gap stays visible.
7. **Restriction that must gate programming.** Athlete-stated knee
   restriction: no high-impact, stairs limited. Expected: nothing
   high-impact is ever programmed while the restriction stands; the stated
   reason is the restriction row, class (b) only.

## Arc facts a reader should know

- Pre-medication baseline is flat (121-123 kg). Medication starts
  2030-02-03. Weight reaches about 112 kg by 2030-06-30.
- Walking capacity genuinely rises across the medicated months: honest
  session durations lengthen from about 8 to about 25 minutes. The eleven
  inflated manual rows sit on top of this true improvement, which is what
  makes them worth testing against: the lie points the same direction as
  the truth, only further.
