# Phase 0, reproduced on every record this repository holds

**#460. The gate decision in `06-roadmap.md` stands. The NUMBER behind it does
not generalise, the DECISION does, and twelve of sixteen records cannot be
asked at all.**

Gate A ran on 2026-08-02 over one private record and settled that `weight_rate`
is a direction rather than a number - for every record, not that one. That
judgement carries a great deal: it is why a client may not print a rate, why
#372's forward band publishes order statistics rather than a forecast, and why
#458 decided against a modelled centre.

**The counting script was never in this repository.** `00-phase0-experiment.md`
says so: "a ~60-line script in the private record's tooling directory (never in
the public repo)". So the measurement has never been reproducible here, and no
second record had ever been asked. `src/vitai/rate_uncertainty.py` is that
script, written to the same spec, reachable as `vitai rate-uncertainty`.

## What it finds

| record | weigh-ins | weeks | measurable | median `u_rate / half-band` | refusal | straddle |
|---|---|---|---|---|---|---|
| `examples/demo` | 62 | 11 | 9 | **0.68** | 100 % | 0 % |
| `nora` | 1096 | 157 | 156 | **0.75** | (no target) | |
| `sofia` | 76 | 26 | 25 | **0.71** | 84 % | 32 % |
| `tom` | 326 | 245 | 232 | **2.55** | 100 % | 91 % |
| the other twelve | | | **0** | not measurable | | |

Pre-registered: **1.74**.

## Twelve of sixteen cannot be asked

The Type A estimator needs replicates: `u_wk = SD_within_week / sqrt(n)` for a
week of three or more readings, falling back to a pooled SD taken over the
weeks that have one. **No week in any of those twelve records holds three
weigh-ins**, so there is no within-week SD anywhere and nothing to pool from
either.

That is the first finding and it is not about fixtures. A person who weighs
once or twice a week - which is most people, and most of this corpus - supplies
no replicates at all, so the measurement that decides whether their rate is
reportable cannot be taken on their record. The policy is applied to them
regardless.

**Every one of #463's four flat personas is in the uncomputable set**, which is
luck rather than design: a ramp has almost no within-week dispersion, so had
`vera` weighed three times in any week the estimator would have returned a
ratio near zero and reported that her weekly rate is precisely resolvable.
#462 is the outstanding fixture work.

## The number does not generalise

0.68, 0.71, 0.75, 2.55. Three of the four sit at roughly two fifths of 1.74 and
the fourth at half again as much - a spread of nearly four to one across four
records. **1.74 is a property of the record it was measured on**, and the
prose that cites it as though it were a property of the metric is overstating
what was established.

## The decision does generalise, on the records that can be asked

The refusal does not turn on 1.74. It turns on whether the 95 per cent interval
crosses a band edge, which begins once the expanded half-width exceeds the
half-band - a ratio above `1 / K95`, about **0.51**. The lowest measured here
is 0.68, a third above that line.

So every record that can be judged refuses on most of its weeks: 100 %, 84 %,
100 %, against the 60 % threshold Gate A pre-stated. **The conclusion Gate A
reached is reproduced on every record where it can be evaluated. Its magnitude
is not.**

## Which ratio 1.74 is

The ratio table in `00-phase0-experiment.md` defines `R = u_measure /
half-band` with `u_measure = sqrt(u_prev^2 + u_cur^2)`, a STANDARD uncertainty,
and lists 1.74 under `median u_rate / half-band`. Two comments in `verdicts.py`
and one line of `06-roadmap.md` described the same 1.74 as a "95 per cent
half-width", which at the `K95 = 1.960` the same document defines is a
different number - about 3.4 half-bands.

Corrected here. The mislabel understated the finding by a factor of two, and
`vitai rate-uncertainty` publishes both ratios so no reader has to guess which
one a figure is.

## What would settle it properly

1. **A record that weighs three times in a week.** Nothing in this corpus does.
   Until one exists, the census is four records, all synthetic, and the
   within-week dispersion in each of them is a generator's choice - the values
   are plausible (0.23 to 0.52 kg pooled SD, against a published 0.5 to 0.7 per
   cent of body weight) but they were not measured off a person.
2. **A second real record.** The pre-registration ran on one. A judgement that
   every record's rate is a direction needs more than one record to have said
   so, and this measurement now costs one command.
3. **A per-record predicate, if the answer turns out to vary.** Deliberately
   not proposed. Gate A's own decision was that the DECISION UNIT is wrong - a
   fortnightly rate with a guard band - and a third answer to a settled
   question needs its own evidence.
