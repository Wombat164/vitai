# bea: what this corpus is designed to break

Findings below were exposed by bea@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

Each item names the machinery under test and the expected behaviour, in the
medical boundary's terms: the engine observes the record and constrains its
own output; it never assesses her.

## Under test

1. **A part-of-day label taken from the wall clock is wrong for her, and only
   for her.** On days after a night shift she wakes about 16:00 and trains at
   18:30. Every other persona in this corpus sleeps at night, so a clock-derived
   label agrees with a sleep-derived one on all ten of them. Expected: a
   part-of-day is derived from her own sleep interval where one exists, or it
   is not stated. A default that reads 18:30 as evening is right nine times
   and wrong about her every shift week, which is the shape that survives
   review.

2. **A sleep interval lying wholly inside its own row's date.** Sleeping 09:00
   to 16:00 starts and ends on the day the `daily` row is keyed on. Every
   other record in this corpus has the night beginning the previous evening,
   so the convention that a night belongs to the day it ends on has never had
   to distinguish anything. Expected: handled without special-casing, and no
   reader assumes `sleep_start < date`.

3. **Duration present, timing absent, on about a third of her days.** The
   watch is off for the twelve hours of a shift, so `sleep_h` is her own
   estimate and both boundaries are null - 76 of 301 days, a quarter of the
   record. Expected: a day with no interval is
   reported as having no timing rather than silently anchored to midnight.
   This is the only shape in which that fallback can hide: a record with the
   field everywhere never exercises it, and a record without it anywhere never
   reaches the code.

4. **Steps inside a declared regime.** Across a block of nights her step count
   is a fact about a ward floor rather than about training, and reading it as
   activity flatters the week. The record says so in a `regimes` row -
   `unanchored`, 2029-09-15 to 2029-09-18, which is the first four-night
   block the roster actually produces. The dates are derived from it rather
   than written down beside it: the first version named four dates by hand and
   the roster made two of them days off. Expected: the interval is not read
   as training volume, and the regime is visible in any output that reports
   the period.

5. **One origin, two instruments.** The watch died on 2030-02-14 and its
   replacement reports under the same name. Nothing in her `daily` or
   `sessions` rows distinguishes them; the `instruments` register does, with
   an interval. Expected: a reading from January resolves to the old watch and
   one from March to the new one, and neither resolves to both.

6. **A scoring change that is not a change in her.** The new watch scores
   daytime sleep as napping, so the first week of March reports short totals.
   A `regimes` row says so. Expected: the dip is not read as a change in her
   sleep, and the engine does not infer a cause the record does not state.

7. **A capability that is a proxy, with the construct named.** The watch is a
   proxy for `sleep_h` on a shift week, and the record says what it actually
   measures: continuous nightly rest, which is not what she gets. Expected:
   any figure derived from it carries that qualification rather than a
   confidence number.

8. **A weigh-in gap that is a decision.** She weighs only on days off, because
   a measurement after twelve hours on the unit is not the same measurement.
   The procedure is stated in `protocols` and named on every weight row.
   Expected: the missing shift-day weigh-ins are not read as non-compliance.
