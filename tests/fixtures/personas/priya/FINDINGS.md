# priya: what this corpus is designed to break

Findings below were exposed by priya@1 (see persona.toml; docs/persona-doctrine.md requires findings to record the persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in
the medical boundary's terms where relevant: the engine observes the record
and constrains its own output; it never assesses her.

## Under test

1. **Deviceless / low-data mode (F10/G64).** Zero steps rows across all
   eight weeks, sleep_h on 23 of 57 days, no heart rate anywhere, ever.
   Expected: status output and the rollup read this as a complete record
   for a life with no wearable, not as an incomplete import waiting for a
   device to catch up. `priya-E4`.
2. **Binary/skill goals and proxy indicators (F7/G62).** `strict-pullup` is
   `target = null`, `verification = attested`: there is no percentage-
   complete anywhere the goal machinery can produce one. The real
   progression - dead hang, 20 second hold, 3 second negative, 1
   band-assisted rep, 2 second chin-over hold - lives entirely in
   `checks.jsonl`'s `value`/`note` fields, five rows that all read
   `result: fail`. Expected: the engine reads progress from the checks
   series and never treats five straight fails as a stalled goal, and never
   invents a completion percentage for a goal that structurally has none.
   `priya-E5`.
3. **The subjective day (F6/G61).** The 2030-05-15 02:50 session's own note
   calls it "still feels like Tuesday's shift", because the night shift it
   belongs to started the evening of 2030-05-14. The row's `date` field
   correctly says 2030-05-15 - that is what the calendar read at 02:50 -
   but nothing in the schema carries the fact that, to her, it was one
   continuous shift-day straddling midnight. Expected: the stored `date` is
   authoritative and is never re-derived from note text; a future
   cadence/day-anchor feature could recognise the mismatch as a shift-work
   signal, but none exists today. `priya-E6`.
4. **Back-fill clustering as observation, not accusation (new).** The six
   `sessions.jsonl` rows recorded within 225 seconds of each other on
   2030-06-16 evening, spanning six calendar dates - two of which never
   happened - is the corpus's sharpest test of a principle with no
   machinery behind it yet: `recorded_at` clustering is visible today, but
   nothing evaluates it, and nothing should conclude anything about any one
   row in the cluster from the clustering alone. `priya-E1-01`, `priya-E1-02`,
   `priya-E2`; see LIES.md P1 and its deliberate pairing with marcus M3.
5. **A journal claim the record itself contradicts (new).** "I have not
   missed a single planned session since I started this" (2030-06-19)
   against a real, openly-journalled zero-session week five weeks earlier.
   No journal-vs-sessions cross-check exists; if built, its only safe
   output is a class-(a) observation of the contradiction. `priya-E3`; see
   LIES.md P2.
6. **A cadence the calendar week does not fit (F5/G60), present but not the
   corpus's focus.** The 16-day rota cycle (four days, four off, four
   nights, four off) never lines up with a Monday-anchored week; "show up
   3x/wk" is tracked weekly regardless, which is itself part of what makes
   week 3's zero sessions and the June back-fill both plausible in this
   specific life.
7. **An explicitly refused metric that must never appear (sweep 3, G79-
   adjacent).** The bad-shift count (patient deaths) is named in
   METRICS.md and nowhere else - not in `journal.jsonl`, not in a check,
   not in a note. The refusal is the fixture; there is deliberately nothing
   here for an expectation row to point at.

## Arc facts a reader should know

- Both goals are set on day one, 2030-05-05, and neither ever resolves:
  the pull-up stays `fail` through the final check on 2030-06-27, and
  "show up 3x/wk" is met in six of the eight nominal weeks (weeks with
  three-plus real strength sessions) and missed outright in week 3.
- The rota is a 16-day cycle (four day shifts / four off / four nights /
  four off), overridden once: 2030-05-20, normally an off day, becomes an
  extra shift covering a colleague, which turns the four ordinary day
  shifts that follow (2030-05-21 to 05-24) into five working days in a row
  before any rest. That stretch is week 3's entire explanation - no lie
  sits inside it, it is simply a week the record does not have.
- 24 of the 29 `sessions.jsonl` rows are strength (the goal-relevant type);
  5 are unmeasured canal-towpath walks that never carry a `distance_km`,
  because nothing in this life ever measures distance.
