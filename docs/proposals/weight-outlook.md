# What the forward band for weight can honestly be

**Status: the WIDTH is built (#372). The CENTRE from energy arithmetic is NOT,
and the reason is written down here rather than left in a commit message, so
it can be argued with rather than rediscovered.**

`api.Vitai.weight_outlook` / `vitai outlook` states what this record's own
weight has done over an elapsed interval: the median change over `d` days, the
tenth and ninetieth percentiles of those changes, and the two counts behind
them. Nothing is modelled.

## Two decisions on the issue, and they disagree

Both are dated 2026-08-12 and both are labelled `Decided`.

**12:13 - the width comes from the athlete's own residuals, not from device
error.** With the reasoning in full: there is no published 24-hour
total-expenditure validation for wrist-optical devices of this class, every
figure in that literature is a laboratory bout of minutes against indirect
calorimetry, so any daily uncertainty term would be extrapolated from bout
data and presented as though it were sourced. "It needs no device-error term."

**18:39 - Forbes-informed deficit arithmetic, not Hall's ODE.** This one
resolves the MODEL question, and in doing so it restates the band description
from the 08:13 research comment verbatim: three terms, one of which is "a
stated wearable-EE interval rather than a point".

**The later comment reproduces a term the earlier one had just killed**, and
it does not mention the earlier one. Read together they are not consistent.

**Taken here: 12:13 governs the width, 18:39 governs the centre.** The 18:39
comment says of itself that it resolves the tension "between the issue body,
which put the model out of scope, and the comment, which recommended one" -
the model question - and its band paragraph is quotation rather than a second
ruling. The 12:13 argument against a device-error term is specific, evidenced,
and was not answered. So there is no wearable-EE term in what shipped.

## The centre is an order statistic, not Forbes

The decided model is not built, and this is the deliberate part.

#372's own measurement, on the record it was raised on: intake logged on **24
per cent of days**, those days not a random sample but disproportionately the
days eating went to plan; and the classic 7700 kcal/kg rule predicting **1.93
kg** over a span the record shows **3.1 kg** of - out by 60 per cent, in the
direction that flatters a forecast.

A centre from arithmetic that wrong, wrapped in a width earned somewhere else,
is the confident wrong number the issue exists to refuse. It would also be
worse than what it replaced: the median observed change over `d` days needs no
intake at all, and on this record it is not out by 60 per cent of anything,
because it is not a prediction - it is a report.

**What this makes possible, which did not exist before.** A model proposing a
centre now has something to be checked against: the distribution of what this
record actually did over that many days. Before this, "the 7700 rule is 60 per
cent out" was a hand calculation on one span. It is now a test anybody can run
on any record. That is the acceptance gate the energy centre was missing, and
it is why building the width first is not a detour.

## The consistency gate against `weight_rate`

`verdicts.ANSWERS_BY_METRIC` scores `weight_rate` as a DIRECTION and not a
number, because this project's pre-registered run measured the median
`u_rate / half-band` of a week-over-week rate at **1.74**, with more than half
of scored weeks admitting no verdict word at all. (This document first called
1.74 a 95 per cent half-width, copying a mislabel in `verdicts.py`; #460
corrected both. It is a standard uncertainty ratio, so the 95 per cent
half-width is about 3.4 half-bands.)

An outlook drawing a seven-day band NARROWER than that decision band would be
the same engine claiming, one surface over, a resolution it had already
measured away. So `verdicts.RATE_DECISION_BAND` is named rather than inline,
and `test_weight_outlook.py` asserts the seven-day spread against it.

On the shipped demo the seven-day spread is **0.90 kg against a 0.50 kg
decision band - 1.8 times it**.

**That 1.8 is not the same statistic as the pre-registered 1.74 and this
document first implied it was** (#460). One is a p10..p90 width of observed
seven-day changes against the whole band; the other is a standard uncertainty
of a weekly mean against the half-band. They landed near each other by
coincidence. What survives, and it is the part that mattered, is the
inequality: a week of this record's own change does not fit inside the band a
weekly rate is judged in. `vitai rate-uncertainty` now runs the pre-registered
estimator itself, and on this demo it returns 0.68 rather than 1.74.

## Where the two DO conflict, stated rather than smoothed over

Over the persona corpus, four fixtures produce a seven-day spread that fits
INSIDE the decision band: `vera` at 0.03 kg, `ines` at 0.05, `hana` at 0.10,
`stefan` at 0.50. On those records the engine could resolve a weekly rate and
refuses to.

That is a fact about the fixtures. `vera`'s series runs 59.18, 59.14, 59.14,
59.13; `hana`'s runs 71.40, 71.34, 71.29, 71.28. They are generated ramps with
the noise left off, and no scale reports 40-gram days. The register in
`test_weight_outlook.py` pins the list so that a fixture gaining realistic
scatter makes a test fail and somebody notices.

It is also the shape of a question the blanket policy has never been asked.
`weight_rate` is a direction for EVERY record on a measurement taken on ONE.
A record whose weigh-ins are tight enough could support a rate, and nothing in
the engine can currently notice that. Left open deliberately; it is #171's
refusal predicate territory, not this change's.

## Why this is not #402's first instance

#402 says an estimate's band comes from a measured overlap, a source that
publishes its own uncertainty, or an interval the athlete stated - "and from
nowhere else". The width here is none of those three, so either it breaks that
rule or the list is incomplete.

**Neither. It is a different claim about a different object.** #402 governs
attaching a width to a value somebody recorded: a bare `1500` and `1500 +/-
600` are different claims about that number. The outlook attaches nothing to
any recorded value. It says what the series has done over an interval, which
is a statement about the record rather than about any reading in it.

**The trap this leaves, named so nobody walks into it.** When #402 does come
to put a band on `weight.kg`, it must NOT take one from here. The day-one
spread in this table is not the measurement uncertainty of a weigh-in - it
contains a day of real change, which is most of it. The two quantities differ
by roughly an order of magnitude and a reader in a hurry would not notice.

## What is deliberately not here

- **A physiological model.** Above.
- **A smoothed trend line.** A time-aware EWMA needs a smoothing constant, and
  nobody has measured one for this record. The horizon table needs no trend:
  a median change over `d` days is a statement about `d`-day changes, and
  taking residuals against a curve nobody can justify would put an invented
  parameter under every number here.
- **A window on the series.** The outlook reads every reading since the last
  unbridged seam, which on a long record can reach back years. Bounding it
  would need a length nobody has measured. The extent is published (`from`,
  `as_of`, `span_days`) so a reader can see how far back it went; narrowing it
  is a decision with evidence behind it or it is a preference.
- **A refusal on weigh-in timing drift.** `weight_rate` refuses when the
  spread of weigh-in times could account for the rate, because it is judging a
  particular number. This surface makes no such claim - it reports the spread,
  and timing drift is one of the things making the spread what it is. A record
  weighed at scattered hours gets a wider outlook, which is the honest
  consequence rather than a refusal.

---

# The centre: it cannot be stated, and here is what would change that

**Status: DECIDED against, on measurement. #458.** What ships instead is the
instrument that decides - `api.Vitai.energy_agreement` / `vitai
energy-agreement` - which never states a centre.

#458 filed two undecided things and an acceptance gate. Measuring first, which
is what the width half was for, says one of them is answerable and moot, one is
not answerable at all, and a third that was not filed dominates both.

## 1. The intake coverage floor: answerable, and it never gets a turn

A floor is easy and needs no new numbers - the two `outlook.py` already
derives. A window needs `kcal_in` and `kcal_out` on all its days and a weigh-in
at each end; eleven such windows is the smallest sample in which a tenth
percentile is interior, and three disjoint stretches is `overlaps`' floor.

It is also not the binding constraint. Across the sixteen records this
repository holds:

| | records |
|---|---|
| not one complete seven-day window | **13** |
| enough to ask the question | 3 (`examples/demo` 40, `nora` 844, `stefan` 98) |

Thirteen of sixteen fail before a floor could be applied to them. Stating one
unblocks nothing.

## 2. The selection bias: not answerable, and worse than #458 wrote

#458 says a floor does not fix it. The obvious repair - measure the bias as the
median of the model's residuals on this record - **cannot work, and the reason
is the same one that makes the bias a problem**: residuals only exist on days
that were logged, which is exactly the sample the bias lives in. A record where
intake is logged on the days eating went to plan produces residuals from those
days, and their median is the bias on good days, not the bias.

Nothing inside the record can reach it. What could: logging coverage high
enough that the unlogged remainder cannot carry the bias, which is a fact about
the athlete's behaviour rather than about the schema, and is therefore not
something the engine can build its way to.

## 3. The one not filed, which decides it

**No record in this repository can validate a centre, and the reason is in the
generators.** `examples/generate_demo.py` walks weight with

    kg -= 0.05 * (0.7 + 0.6 * rng.random())

and draws the two energy figures from `rng.gauss(2850, 220)` and
`rng.gauss(2065, 260)` - three unrelated streams. `nora` draws `kcal_in` from
`rng.uniform(2050, 2200)` beside a weight series it never sees.

So the correlation is zero **by construction**, and the acceptance gate #458
proposed is uninformative in *both* directions: a good model fails it here and
a bad one does too. A model that passed would have passed against noise.

Measured on the three records that can be asked at all, with the energy density
**fitted to each record** rather than taken from the literature - the most
generous test the family admits:

| record | complete windows | correlation | implied kcal/kg | median-only spread | model spread |
|---|---|---|---|---|---|
| `examples/demo` | 40 | -0.055 | 40,307 | 0.900 kg | 1.022 kg |
| `nora` | 844 | +0.022 | -65,198 | 1.300 kg | 1.299 kg |
| `stefan` | 98 | +0.304 | -8,469 | 0.500 kg | 0.545 kg |

Two of the three imply a **negative** energy density. None beats the record's
own median.

## The argument that does not depend on the fixtures

Even with a perfect corpus, the centre needs an error term on `kcal_out` that
does not exist - the same finding that killed it as a *width* term on
2026-08-12, applied to the centre. It is not that the error is small and
unmeasured; it is unquantified and plausibly larger than the signal.

On the demo's own daily figures: mean `kcal_out` 2,823 and a mean balance of
665 kcal/day, so a seven-day window carries a signal of **0.60 kg**. The JMIR
2022 review puts wrist expenditure at a MAPE above 30 per cent, which is 847
kcal/day on that mean:

- if the error averaged out across days: **0.29 kg** over the window;
- if it does not, which is what a per-device bias means: **0.77 kg**, larger
  than the signal.

Nothing in the literature says which, because the daily figure has never been
validated for this device class. A centre stated on that input is a number
whose error is unknown and may exceed it.

## So: the centre cannot be stated

Not "not built yet". Three independent reasons, any one sufficient: the input
error is unquantified and may exceed the signal; the selection bias is
unreachable from inside the record; and nothing here can tell a model that
works from one that does not.

**What would change it, in the order it would have to happen:**

1. A record with at least eleven fully-logged windows in three disjoint
   stretches. `vitai energy-agreement` reports both counts and says which is
   missing, so a record can be asked rather than assumed.
2. Logging coverage high enough that the unlogged days cannot carry the bias.
   No number is proposed here; it is a behavioural fact and it needs its own
   evidence.
3. That record answering `explains: true` - the model, fitted to it and scored
   out of sample, beating its own median. That is the gate #458 wanted, made
   runnable.
4. And even then, a stated centre needs an honest error term. Today that means
   the residual spread on that record, which is the same trick the width uses
   and needs no device figure at all.

## The instrument, and the mistake it caught in its own first draft

`energy_agreement` compares the spread of the model's error against the spread
the record's own median already achieves - the null being #457's answer,
because that is what a client has today.

**The first version scored the fit on the data it was fitted to, and reported
that the demo's energy balance EXPLAINS its weight change** - on the record
whose generator draws the two from unrelated streams. A least-squares slope
always narrows the spread of its own training data, so `fitted < null` was true
by construction and the surface answered yes to the one question it could only
honestly answer no to.

Every residual now comes from a fit that never saw the window it scores, and
never saw a window overlapping it either - blocked rather than plain
leave-one-out, because a seven-day window starting on Monday shares six
readings with Tuesday's and leaving out one leaves six near-copies behind.

**And `explains` requires the implied density to be positive before it looks at
the spreads at all.** That is a domain constraint rather than a threshold: a
record whose weight rises with its deficit has not produced a weak model, it
has produced a contradiction. It is also what keeps the comparison off a knife
edge - a fit with no slope predicts the mean, which is what the null does, so
its spread lands within a gram of the null's. `nora` sat at 1.299 against 1.300
across 844 windows. Requiring the sign removes that tie without inventing a
margin.
