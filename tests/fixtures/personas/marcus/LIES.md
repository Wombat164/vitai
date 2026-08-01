# marcus: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually
happened, so a test can assert what the engine SHOULD conclude instead of
guessing. Every "expect" string below stays inside
`docs/medical-boundary.md`: observation and self-constraint only, never a
condition name, never a care instruction. Marcus's OWN journal, goals and
medical rows do name his achilles plainly - that is his self-report, not an
engine conclusion, and exactly as legitimate as rachel naming her knee
osteoarthritis.

## M1: a pain scalar that disagrees with the same week's journal

**The lie.** Eight dates between 2029-06-12 and 2029-10-20:
`daily.pain` reads 0 or 1 (site achilles, side right), while the same
week's `journal.jsonl` entry - written by the same person, about the same
thing - describes real trouble: "barking on the hills", "hobbling on the
stairs before school again". Neither row is false in the sense of
misreporting a fact nobody said; both are exactly what he said, in two
different places, and they do not agree.

**Ground truth.** The pain that week ran 4-6 on a 0-10 scale, not 0-1.

**Expected engine behaviour.** All eight dates fall BEFORE the achilles
episode is formally opened (2029-11-04), so the engine has nothing in
`medical.jsonl` to gate on yet. The contradiction between a low `daily.pain`
scalar and a same-week journal note is an observation about the record -
both rows are athlete-stated, neither outranks the other on any resolution
ladder, and the engine must not average them into one number or infer what
the pain "really" was that week. Once the episode opens, the gate applies
to what gets programmed going forward; it does not reach back and resolve
what these eight pairs of rows say (`marcus-E-M1-01` through `-08`).

**No fingerprint today.** No existing check reads a `daily.pain` value
against the same week's `journal.jsonl` text at all; the contradiction is
visible only by reading two datasets side by side, exactly as in derek's
D1.

## M2: a guarded ramp defeated by omission, then a downward correction

**The lie.** The week of 2029-08-06 to 2029-08-12, during the build-up to
the 2029-10-07 marathon and against a 68 km baseline the week before: true
volume was 92.0 km (21.5 Monday, 14.0 Tuesday, 19.0 Wednesday, 16.0
Thursday, 21.5 Sunday). Two separate acts hide it. First, the 14 km
Tuesday run is never entered as a `sessions.jsonl` row at all - its GPX
survives at `tracks/marcus-2029-08-07-omitted.gpx`, referenced by
expectation `marcus-E-M2-01`, but the record itself holds no session for
that day. Second, Thursday's run is logged true (16.0 km, device-recorded)
and then, two days later (2029-08-11), corrected down to 9.0 km via
`supersedes`, reason "mismapped" - the original was true, the correction is
false.

**Ground truth.** Logged at the time the omission alone accounts for
(excluding Tuesday, including Thursday's still-true 16.0 km): 78.0 km -
the figure the guarded weekly-volume goal actually evaluates against the
68 km baseline. After the later correction resolves, the current-state
total for that week is 71.0 km, lower still.

**Expected engine behaviour.** The guard (`guard_pct: 0.10` on the
`weekly-volume` goal) evaluates only what the record contains. Against
78 km (or 71 km, post-correction) and a baseline near 68 km, it correctly
stays quiet or credits only the budgeted share - a statement about the
engine's own inputs, not a diagnosis of the athlete. It cannot see a run
that was never logged, and that is the guard being defeated by its input,
not a failure of the guard itself (`marcus-E-M2-01`).

For the correction: supersedes is append-only-sacred. The engine takes the
correcting row at face value for any current-state query (class a); the
superseded original stays in the file in full, quotable, forever
(`marcus-E-M2-02`).

**The pattern across both edits.** No existing check flags a
downward-correcting supersedes landing during an active guarded-ramp goal
as a pattern worth a second look. This is the same shape as tom's T3 (a
self-serving correction at a trend inflection point) applied to a volume
ramp instead of a weight trend, which is why the two are the deliberate
FINDINGS pairing for this fixture (`marcus-E-M2-03`, gap).

**Why Friday and Saturday are rest days.** Not realism - construction. The
correction's `recorded_at` (2029-08-11, two days after the original) would
otherwise land between two other dated rows in `sessions.jsonl`'s
date-primary sort order and break file-order recorded_at monotonicity
(handbook lesson 2). Leaving those two days empty keeps the correction's
late stamp clear of any interleaving row.

## M3: a true back-fill, paired against priya's false one

**The lie - except it isn't one.** About 70% of term-time
`sessions`/`daily`/`weight` rows carry `recorded_at` on the Sunday evening
of their week, regardless of which day the thing actually happened on.
Holiday weeks are logged the same evening instead - the decision is made
once per week (never per row: an earlier version of this generator drew an
independent coin flip per row, which let one day in a week back-fill to
Sunday while a neighbouring day in the SAME week logged same-day, and that
broke file-order recorded_at monotonicity exactly as the handbook's lesson
2 warns).

**Ground truth.** Every back-filled row is true. Only the timing is late;
the content is exactly what happened.

**Expected engine behaviour.** A recorded_at cluster on one weekday is, by
itself, only an observation about when data enters the record - never
evidence of falsification. This is the deliberate pair with priya's P1
(phantom rows, same fingerprint, opposite ground truth): any future
back-fill heuristic must be built so that it can tell these two apart, or
it cannot be trusted to observe rather than accuse (`marcus-E-M3`).
