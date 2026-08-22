# kenji: what this corpus is designed to break

Findings below were exposed by kenji@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

He exists because of doctrine property 6 and its two named instances, both met
in one week: four weight series that are ramps (#459, #462) and a demo whose
energy and weight come from unrelated random streams (#458, #461). **A fixture
that cannot exhibit a phenomenon passes every test written against it and
proves nothing** - the test is green because the data is incapable, and from
the test's side that is indistinguishable from the engine being right.

## What he holds shut

**The estimator can now be wrong.** `agreement.compute_agreement` answered
`explains: false` on all three records it could be asked at all, with implied
energy densities of -65,198, -8,469 and +40,307 kcal/kg. A gate that has only
ever returned one answer has been exercised in one direction. On his record it
returns **true**, with a correlation of **-0.52** between weekly balance and
weekly weight change and an implied density of **7,095 kcal/kg** against the
7,700 he was built with. A change that breaks the arithmetic now fails
somewhere instead of agreeing with the corpus by accident.

**The scatter is adopted, not chosen.** Schneditz et al., *Day-to-day
variability in euvolemic body mass*, Ren Fail 2023;45(2):2273421 - 9,521 days
of standardised morning weighing in one healthy individual, SD of the relative
day-to-day difference **0.53%**, rising to **0.69%** at seven days. His record
reproduces both: **0.54%** at one day and **0.64%** at seven.

**And the paper reports the SD of a DIFFERENCE, not of a reading.** Two
independent deviations differ with SD sigma times root two, so injecting 0.53%
as per-reading scatter would give day-to-day movement near 0.75% - forty per
cent too much, which is the same class of error as being too flat and harder
to see. The generator divides by root two and says so.

## Exposed while building him

**Presence in the variation-floor register is not the finding; run length is.**
He was built to carry published variation and he joins `BELOW_THE_FLOOR`
anyway, with one run of six days. Rebuilding his series under 200 seeds, **143
of them (72%)** hold at least one stretch of five days or more under the
declared 0.2 kg floor; median longest run five days, longest seen nine. A
realistic daily series of this length is more likely than not to trip that
floor somewhere. `vera` at 71 days and `hana` at 26 are series that cannot
fluctuate; `nora` at six is a real flat fortnight; he belongs with `nora`.

That a fixture built specifically to fix flatness lands in a flatness register
is the clearest evidence available that the register measures something
narrower than its name suggests.

## What he does NOT show

**He is not evidence about physiology, and `explains: true` on his record must
never be read as any.** The coupling is authored. An estimator that finds it
has found something the generator put there. He makes the instrument
falsifiable; he says nothing about whether an energy model is true of a person,
and `agreement.py`'s own argument for why the centre cannot be stated is
untouched by him.

## Not a finding

His logging completeness is unusual on purpose and is stated as such in
`METRICS.md`. If something is wrong on kenji, it is not because his record is
strange - it is the most regular record here.
