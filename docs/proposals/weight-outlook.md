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
number, because this project's pre-registered run measured the median 95 per
cent half-width of a week-over-week rate at **1.74 times the entire decision
half-band**, with more than half of scored weeks admitting no verdict word at
all.

An outlook drawing a seven-day band NARROWER than that decision band would be
the same engine claiming, one surface over, a resolution it had already
measured away. So `verdicts.RATE_DECISION_BAND` is named rather than inline,
and `test_weight_outlook.py` asserts the seven-day spread against it.

On the shipped demo the seven-day spread is **0.90 kg against a 0.50 kg
decision band - 1.8 times it**, which corroborates the pre-registered 1.74 by
a route sharing no arithmetic with it. Different record, different estimator,
same finding.

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
