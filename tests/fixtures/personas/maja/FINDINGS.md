# maja: what this corpus is designed to break

Findings below were exposed by maja@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

## Under test

1. **A machine setting identifies the movement.** Every set carries the seat,
   pad and lever positions and the angle where the frame has one. The corpus
   had no record in which any of those was written down, so nothing could tell
   a leg press at seat 3 from the same load at seat 5. Expected: two sets of
   one exercise at different settings are not compared as the same movement
   without the difference being visible.

2. **Two machines, two kinds of number.** The leg press is plate-loaded and
   its load is kilograms; the other three are selectorised and their number is
   a pin position with no unit. Expected: they are never summed, averaged
   together, or converted. The schema already refuses `load_unit: kg` on a
   stack, and this is the first record that exercises both sides of that rule.

3. **Laterality that is a real fact.** The leg curl is worked one leg at a
   time, so `side` alternates left and right across her sets - 102 each,
   balanced over the record. Everything else
   is `bilateral`. Expected: per-side work is not double-counted as volume,
   and the two sides are not silently merged.

4. **A goal that is a band.** Protein 130 to 160 g, both bounds declared.
   Expected: reaching the upper bound is not reported as a failure. A range is
   a different shape from a floor with a ceiling stacked on it and nothing
   else in this corpus declares one.

5. **A label is rounded before the athlete sees it.** Her meals carry
   per-hundred-gram figures off packaging, including fibre, sugar and sodium,
   which no other record has. Expected: a value derived from them is not
   reported to more precision than the label had, and the rounding is not
   attributed to her logging.

6. **Energy that agrees with its macros.** `kcal_in` is computed from protein,
   carbohydrate and fat at 4/4/9, so her rows are internally consistent by
   construction. Expected: a consumer that cross-checks the two finds them in
   agreement here - which is the case it must handle correctly before meeting
   a record where they disagree.

7. **A cancelled event with a reason.** The April refurbishment was cancelled
   because the works moved to the autumn. Expected: distinguishable from an
   event that simply passed, and from one that was never entered.

8. **A plan that did not survive the week.** Two plans for the week of 18
   November: one completed, one skipped because the gym shut early for a burst
   pipe, with the reason typed as `opportunity_physical`. The outcomes are read
   off the sessions rather than declared - the first version asserted a skip on
   a day the record has a full session with six sets behind it. Expected: the miss
   is attributed to the circumstance the record states rather than to
   motivation, which is the distinction the reason vocabulary exists for.
