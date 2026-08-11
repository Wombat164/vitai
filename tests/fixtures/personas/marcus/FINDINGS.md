# marcus: what this corpus is designed to break

Findings below were exposed by marcus@1 and marcus@2 (see persona.toml; docs/persona-doctrine.md requires findings to record the persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in
the medical boundary's terms: the engine observes the record and constrains
its own output; it never assesses him.

## Under test

1. **Scalar-vs-narrative contradiction, pre-gate (M1).** Eight dates between
   2029-06-12 and 2029-10-20 carry a low `daily.pain` (0 or 1, site
   achilles, side right) while the same week's journal entry describes real
   trouble ("barking on the hills", "hobbling on the stairs before school").
   All eight fall BEFORE the achilles episode is formally opened
   (2029-11-04). Expected: with no open episode yet, the engine has nothing
   to gate on; the contradiction between two athlete-stated rows is an
   observation, and the engine must not average the two into a single pain
   figure or infer which one is "true" (`marcus-E-M1-01..08`).
2. **A guarded ramp defeated by omission (M2).** A 92 km week (2029-08-06 to
   2029-08-12) against a 68 km baseline is logged as 78 km by omitting a
   14 km run entirely - its GPX survives at
   `tracks/marcus-2029-08-07-omitted.gpx`, the sessions row does not.
   Expected: the guard evaluates only what the record holds and correctly
   stays quiet on 78 km against a 68 km baseline; this is the guard being
   defeated by its input, not a failure of the guard (`marcus-E-M2-01`).
3. **A downward supersedes during the same ramp (M2).** The same week's
   Thursday run is logged true (16 km), then corrected false (9 km) via
   supersedes two days later, reason "mismapped". Expected: the engine
   takes the correction at face value for any current-state read; the
   superseded original remains in the file, quotable. No mechanism today
   flags a downward-correcting supersedes landing during an active guarded
   goal as a pattern worth a second look - the same shape as tom's T3 at a
   different kind of trend, which is why the two are paired
   (`marcus-E-M2-02`, `marcus-E-M2-03`).
4. **True back-fill, paired against a false one (M3).** About 70% of
   term-time sessions/daily/weight rows carry `recorded_at` on the Sunday
   evening of their week, regardless of which day the thing happened.
   Every one of these rows is true. Paired deliberately with priya's P1
   (phantom rows, same fingerprint, opposite ground truth): a future
   back-fill heuristic must stay an observation and never become an
   accusation (`marcus-E-M3`).
5. **A performance-threshold goal has no accumulation semantics.** The
   marathon-time goal (3:20, then 3:15) is authored as `verification:
   attested` with no metric or target, even though both numbers are exact
   and well defined. `contributions.py`'s own contribution model only
   accumulates a metric across a period (MONOTONIC: more always counts;
   GUARDED: a ramp ceiling against a rolling baseline); it has no goal KIND
   for a single-event threshold to beat. The source names the missing piece
   itself - "goal KINDS of G62 (quantity | skill | maintenance)" - a
   threshold/skill goal needs its own contribution model, distinct from the
   volume accumulator this file implements today (`marcus-E-goal-01`).
6. **Medical has no laterality field.** Every achilles medical.jsonl row
   carries `body_site: achilles` with no side; which achilles is
   consistently right, but survives only in title and note prose.
   `daily.pain_side` is a structured field for exactly this question on the
   exact same paired site; medical carries no equivalent
   (`marcus-E-medical-laterality`).
7. **The restriction gate is scoped to what vitai programs, not to what he
   does.** The athlete-stated achilles restriction (no impact loading)
   stands from 2029-11-04 onward and is never lifted. He ran the 2030-04-07
   marathon anyway - 42.2 km of impact loading, five months after the
   restriction was recorded. Expected: the engine's self-constraint never
   programs or suggests impact training against an open restriction, and
   this record shows that boundary holding; his own decision to race
   through it is outside anything the gate is responsible for. Recorded
   because a corpus that only shows a restriction being respected cannot
   test that the gate's scope is "what vitai programs", not "what the
   athlete does" (`marcus-E-restriction`).
8. **Spectatorship has no schema home.** `sessions.context: family` and
   `sessions.with` describe a child running ALONGSIDE him; nothing records
   a child watching him race alone, which is exactly the metric he named
   unprompted in sweep 3 (`marcus-E-spectator`, `METRICS.md`).
9. **Episode opened late, with earlier symptom rows already on record.**
   The achilles slug carries four `kind: symptom` / `status: monitoring`
   rows from June through September 2029 before the same slug escalates to
   `kind: injury` / `status: active` in November. The lifecycle is one
   slug, dated CHANGE rows throughout, exactly as the identity model
   intends.

## Arc facts a reader should know

- 3:29 -> 3:21 -> 3:17 (PB) -> DNF -> 3:26. The PB is only interesting
  because of what regresses after it - the same shape ARCS calls "the
  canonical case".
- True volume the M2 week: 21.5 (Mon) + 14.0 (Tue, omitted) + 19.0 (Wed) +
  16.0 (Thu, true) + 21.5 (Sun) = 92.0 km. Logged at the time, excluding the
  omission and before the later correction: 78.0 km. After the correction
  resolves (Thursday's row becomes 9.0 km), the current-state total for
  that week is 71.0 km - lower still, and further from the truth than the
  78 km figure the guard actually saw when it mattered.
- Friday and Saturday of the M2 week are rest days by construction, not
  realism: they keep the correction's late `recorded_at` (two days after
  the original) from landing between two other dated rows and breaking
  file-order monotonicity (handbook lesson 2).
- The achilles is never named in any `expectations.jsonl` "expect" string
  as a condition; it is named freely in the athlete's own journal, goals
  and medical rows, which is his self-report, not an engine conclusion.

## Added at marcus@2

10. **The night has an interval, not just a length (`marcus@2`).** Every
    `daily` row now carries `sleep_start` and `sleep_end` beside `sleep_h`. It
    was the length alone before, in this corpus and in every other: across the
    ten personas and the demo, `sleep_h` was 61.8% populated and both
    boundaries were 0%. A design that has to say when a day begins, or what
    part of the day a session fell in, cannot be confirmed against a corpus
    with no sleep timing in it at all - which is how the gap surfaced.

    The interval is DERIVED FROM THE WORK PATTERN rather than sampled from
    nothing. He teaches, so the night before a school day is the constrained
    one and runs about an hour earlier than the night before a Saturday, a
    Sunday or a school holiday; `HOLIDAYS` already encodes his terms. Expected:
    an engine reading these must not assume a fixed bedtime, and must not read
    the holiday shift as disturbance.

    `sleep_end` is `sleep_start` plus the `sleep_h` already on the row, to the
    second. Two fields describing one night that disagree would teach a reader
    to trust neither.

11. **The night bounds the day it is dated to (`marcus@2`).** No session and
    no weigh-in falls before that morning's wake. It is worth stating because
    the first cut did not hold it: the bedtime rule knows his weekday and his
    school terms and nothing about what he logged, so 73 of 441 sessions and
    33 of 260 weigh-ins landed inside the recorded night. Expected: a consumer
    confirming an athlete-proposed time against sleep (#212) meets no
    contradiction here that was not put there deliberately.

12. **Five nights cross a clock change (`marcus@2`).** 2028-03-26, 2028-10-29,
    2029-03-25, 2029-10-28 and 2030-03-31 begin at one UTC offset and end at
    another, because British Summer Time starts or ends while he is asleep.
    The wall clock moves an hour; the elapsed time does not. Expected: a reader
    that subtracts local times gets an hour wrong on exactly these five rows,
    and one that compares instants does not - the naive-versus-aware
    distinction the engine already refuses to guess at, now present in a
    fixture rather than only in a rule.

    2029-10-28 is the one that catches a lazy implementation. He goes to bed
    at 00:30, which is BST: the changeover is at 02:00 local, so the clock
    does not go back until after he is asleep. Deciding the offset from the
    DATE rather than the instant stamps it GMT and the crossing disappears,
    which is what the generator did until this was measured.
