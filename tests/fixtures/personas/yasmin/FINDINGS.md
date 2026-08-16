# yasmin: what this corpus is designed to break

Findings below were exposed by yasmin@1 unless marked otherwise (see
persona.toml; docs/persona-doctrine.md requires findings to record the
persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in
the medical boundary's terms: the engine observes the record and
constrains its own output; it never assesses her.

## Under test

1. **Selection-biased weighing (Y1).** 37 weight rows across three
   attempts; every logged delta within an attempt is negative, by
   construction (`yasmin-E1`). The two inter-attempt jumps - attempt 1's
   last row to attempt 2's first (+4.1 kg, zero rows between) and attempt
   2's last row to attempt 3's first (+6.3 kg, zero rows between) - are
   real weight the record never shows arriving. Expected: the engine
   states that a record with no non-negative deltas cannot support a
   trustworthy rate-of-loss estimate, and declines or widens any such
   claim (class a+b). No sampling-bias detector exists today (gap).
2. **Trend handling across a long hole (Y1, continued).** A six-month and
   a fourteen-month gap, both with zero rows in every dataset, sit inside
   this record (`yasmin-E2`). Expected: nothing here is fit with a trend
   line or interpolated across; each attempt is read as its own bounded
   window.
3. **Claim-vs-record contradiction (Y2).** A March 2030 journal claim of a
   perfect on-week streak, against three identifiable missed on-week
   sessions earlier in the same attempt (`yasmin-E3`). Same class as
   priya's P2: an observation contrasting claim and record, never an
   adjudication of character. No journal-vs-record cross-check exists
   today (gap).
4. **Custody cadence vs the calendar week (F5/G60).** On-week carries four
   to five sessions; off-week carries zero in attempts 1 and 2, a thinner
   but real handful in attempt 3 (`yasmin-E4`). A rollup keyed to the
   calendar week reads every off-week as a total lapse; a rollup keyed to
   her real two-week cadence does not.
5. **A goal period the enum cannot name exactly (F5/G60, continued).** The
   attempt-3 goal declares `period: "weekly"` with `on_period_end: "carry"`
   because there is no biweekly or custody-cycle value to declare instead
   (`yasmin-E5`).
6. **Re-entry as the dominant pattern, not a lie (F8/G63).** Three goal
   slugs, not one goal reopened three times: active-then-abandoned,
   active-then-abandoned, active-and-still-open (`yasmin-E6`). Expected:
   the engine reads this as three honest restarts, never as one
   continuously failing programme, and carries no penalty or rate
   assumption across a restart boundary.
7. **A band crossing exercised by real data, not only a unit test
   (yasmin@2, #370).** One `height_cm` row (165 cm, dated the record's own
   first day) turns her existing weight series into a BMI series that
   crosses `crossings.BAND_LEVELS`' 30.0 boundary five times, alternating
   direction, on 2027-08-09, 2028-05-15, 2028-05-29, 2029-10-01 and
   2029-12-31 - verified by running `Vitai(root).crossings()` against this
   corpus, not hand-computed (`yasmin-E7`). Before this, `height_cm` had
   been a legal `MEASUREMENT_KINDS` value since contract 47 but no persona
   in the corpus carried one, so a `band` crossing was exercised only by
   `tests/test_crossings.py`'s own fixtures. Expected: five `kind: "band"`
   rows, each carrying the boundary crossed (a number) and an evidence pair,
   and no rendering surface - CLI, JSON, or MCP - ever names the boundary.

## Arc facts a reader should know

- Attempt 1 (2027-07-02 to 2027-11-04): 43 sessions, weight opens at
  82.0 kg and its last logged row reads 78.4 kg.
- Attempt 2 (2028-05-07 to 2028-08-12): 29 sessions, weight opens at
  82.5 kg (4.1 kg above attempt 1's last row) and its last logged row
  reads 78.1 kg.
- Attempt 3 (2029-10-01 onward): 104 sessions through 2030-06-30, weight
  opens at 84.4 kg (6.3 kg above attempt 2's last row) and its most recent
  logged row reads 77.8 kg - genuinely the lowest of the three attempts so
  far, and still running.
- The gym membership tracks the same three-part shape as the attempts:
  parked through attempt 1 and 2, a basic tier from attempt 3's first
  month onward.
