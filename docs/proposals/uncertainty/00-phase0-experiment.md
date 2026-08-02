# Phase 0: count refusals before building anything

Goal: settle F1 (is the refusal payoff reachable), F2 (does uncertainty metadata
exist where it is needed), F6 empirically, with zero new metadata. Everything
here runs against the existing schema. Nothing ships; this is an experiment
branch of the engine plus one counting script run over the private record.

The engine already contains the precedent: `verdicts.py:106-111` refuses a
weight_rate (emits NODATA with the value) when weigh-in timing drift alone could
account for the rate. Phase 0 extends the identical shape to measurement
dispersion. No new verdict vocabulary is needed for the experiment (a shipped
version would add one word to the closed vocabulary and bump the contract; see
`01-schema.md`).

## 0. RESULT (run 2026-08-02)

**This experiment has been run. It answered the question, and the answer is: do
not build the registry for verdicts.**

| measure | result |
|---|---|
| scored weight-rate weeks | 52 |
| refusal rate under variant B (total dispersion) | **76.9 %** |
| straddle rate (interval covers the whole band) | 53.8 % |
| refusal rate under variant A (per-row bands) | 7.7 %, but unavailable for 47 of 52 weeks |
| verdict flips | **12** |
| median u_rate / half-band | **1.74** |
| band coverage | 20.4 % overall, 0 % on every device and connector source |

`R_B >= 0.60` fired, so per the pre-stated rule the decision unit is wrong
rather than the metadata. `flips > 0` also fired, so the refusal predicate ships
regardless. The record's own dispersion landed inside the literature range, so
the per-field table in section 1b becomes shipped policy.

Full reasoning, the F2 finding and the scope consequences are recorded at
GATE A in `06-roadmap.md` and in the comment on #171. The counting script lives
in the private record's tooling and never here.

**The method below is retained as written**, because a later re-run must use the
same predicate and the same pre-stated thresholds for its result to mean
anything.

## 1. Code changes (experiment branch, not master)

### 1.1 Uncertainty of a weekly mean, two variants

Add to the experiment branch (eventually `src/vitai/uncertainty.py`, but for
phase 0 a private function in `verdicts.py` is fine):

```python
from math import sqrt
from statistics import stdev

RECT = sqrt(3.0)          # GUM 4.3.7: symmetric limits +/-a, no distribution
K95 = 1.960               # coverage factor for a 95 % interval

def _band_u(rec: dict) -> float | None:
    """Type B standard uncertainty from the row's own G37 band.

    kg_lo/kg_hi are validated limits (lo <= point <= hi), not a stated
    distribution, so the half-width is treated as rectangular: u = a/sqrt(3).
    """
    lo, hi = rec.get("kg_lo"), rec.get("kg_hi")
    if lo is None or hi is None:
        return None
    return (float(hi) - float(lo)) / 2.0 / RECT

def _week_mean_u_typeB(rows: list[dict]) -> float | None:
    """u of the weekly mean from per-row instrument bands. None if any row
    lacks a band (a partial budget understates, which is the wrong side)."""
    us = [_band_u(r) for r in rows]
    if not us or any(u is None for u in us):
        return None
    return sqrt(sum(u * u for u in us)) / len(us)

def _week_mean_u_typeA(rows: list[dict], pooled_sd: float | None) -> float | None:
    """u of the weekly mean from the athlete's own replicates (GUM 4.2).

    Total observed dispersion: instrument noise AND day-to-day biological
    variation, which is why Type A and Type B must never be added together
    for the same week (GUM 4.3.10 double-counting ban).
    """
    vals = [r["kg"] for r in rows if r.get("kg") is not None]
    n = len(vals)
    if n >= 3:
        return stdev(vals) / sqrt(n)
    if pooled_sd is not None and n >= 1:
        return pooled_sd / sqrt(n)
    return None
```

`pooled_sd`: root mean square of the within-week SDs over every week with >= 3
readings, computed once over the whole record. This is the SEM-style pooled
repeatability estimate; it is also the input MDC will need later, so the
experiment computes it anyway.

### 1.2 The refusal predicate

In the weight_rate block of `compute_verdicts` (after line 111, before the
`abs(rate - target) <= 0.25` comparison), for the experiment only:

```python
u_prev = week_u(prev_rows)          # variant A or B
u_cur  = week_u(cur_rows)
if u_prev is not None and u_cur is not None:
    u_rate = sqrt(u_prev**2 + u_cur**2)
    half = K95 * u_rate
    lo_edge, hi_edge = target - 0.25, target + 0.25
    spans_low  = (rate - half) < lo_edge < (rate + half)
    spans_high = (rate - half) < hi_edge < (rate + half)
    refusal = spans_low or spans_high          # interval crosses a boundary
    straddle = (rate + half) > hi_edge and (rate - half) < lo_edge
                                               # spans the WHOLE band: cannot
                                               # even say which side
```

Two severities on purpose: `refusal` (the interval crosses one boundary, so the
specific verdict word is not supported) and `straddle` (the interval covers the
entire band, so no verdict word is supported at all). F1 predicts variant B
makes `straddle` the dominant case.

### 1.3 The counting script

A ~60-line script in the private record's tooling directory (never in the
public repo), reading via `vitai.api`:

Outputs one table:

| week | n_cur | n_prev | rate | u_A | u_B | verdict_today | refuses_A | refuses_B | straddles_B | flips |
|---|---|---|---|---|---|---|---|---|---|---|

plus four scalar counts: scored weeks, refusal rate under A, refusal rate under
B, verdicts that FLIP (a week the current engine scores AHEAD/BEHIND where the
interval actually contains the opposite verdict's region).

And the F2 measurement: `%` of weight rows carrying `kg_lo`/`kg_hi` at all,
split by source. Prediction from F2: connector-imported rows near 0 %.

## 1b. Expected-outcome model (validation literature, stream 2)

F1 is answered by the literature per field, and the answer differs sharply by
field: refusal kills exactly one field outright (kcal at day resolution) and
one derived level (body fat %); everywhere else it constrains the RESOLUTION
of the claim rather than forbidding it. Phase 0 validates this prior against
the athlete's own dispersion; the table is the prediction the run is checked
against.

| field | realistic error (literature) | verdict survives? |
|---|---|---|
| steps | 10-15 % lab, 20-30 %+ free-living | YES trends and large changes; NO day-to-day deltas |
| kcal / kcal_out | 20 to >90 % MAPE, SYSTEMATIC, activity-dependent | NO at day resolution, ever (not a target, a deficit, or a two-day comparison); survives only as a within-source ordinal with the source unchanged |
| distance_km | 1-4 % open sky, 3.5-9 % forest/urban | YES per session; NO for a ~2 % pace PB |
| avg_hr / rhr | 2-5 bpm rest, 10-30 % at intensity (wrist optical) | YES at rest; NO at intensity |
| sleep_h | TST bias -0.3 to +46.8 min by device | YES gross duration; NO stages; NO cross-device |
| kg | instrument +/-0.1-0.2 kg; biology 0.5-2 kg/day (5x-15x larger) | YES 7-14 day trends; NO single readings or day-to-day deltas |
| body fat % | limits of agreement +/-4 to 8 points | NO (a consumer reading is compatible with a huge range) |

Citations: Shcherbina 2017 (PMID 28538708, no device under 20 % EE error);
O'Driscoll 2020 (PMID 30194221, I2 > 75 %, rankings flip by activity);
Fuller 2020 (PMID 32897239); Germini 2022 (PMID 35060915); Gilgen-Ammann
2020 (PMID 32396865, GPS); Chinoy 2021 (PMID 33378539, sleep); Orsama 2014
(PMID 24504358, weekly weight rhythm).

Two structural notes the table forces:

- weight_rate's week-vs-week mean IS the mandatory 7-14 day trend filter for
  kg; single-reading deltas are never scored today and must never be.
- the deficit arithmetic (kcal_in - kcal_out) inherits the dead field: any
  phase-2 interval work treats day-level energy balance as ordinal-only.

## 2. Decision thresholds, stated in advance

Let `R_B` = refusal rate under variant B (total dispersion), `C` = band
coverage (share of rows with lo/hi).

| Observation | Decision |
|---|---|
| R_B >= 0.60 | The weekly +/-0.25 band cannot support single-week verdicts at real dispersion. Do NOT build a per-instrument accuracy registry to rescue verdicts: a registry describes instrument noise and cannot reduce biological dispersion, which dominates. Remedy is the decision unit: two-week rates, or refuse-by-default weekly with a guard-banded fortnight verdict. Registry work restricted to seam detection (#33), not verdicts. |
| R_B <= 0.20 | Interval verdicts are viable at weekly cadence. Build `01-schema.md` minimal (capability rows only for sources lacking replicates) and the JCGM 106 guard band. |
| 0.20 < R_B < 0.60 | Narrow: ship the two-gate verdict where full refusal fires only on `straddle`; a one-boundary crossing keeps the point verdict and gains a stated conformance caveat. Registry deferred. |
| C < 0.10 | Variant A is unreachable on the live record (confirms F2). Stream 2 forecloses the borrowed-Type-B rescue (vendors publish nothing usable): per-row bands arrive only from future protocolled/overlap capture, so only variant B machinery proceeds. |
| Verdict flips > 0 | Each flip is a manufactured false all-clear or false alarm in the shipped engine today. Any flip at all justifies shipping the refusal predicate regardless of R_B, because a blank beats a confident wrong number. |
| Own-record dispersion vs the 1b prior | If the record's Type A numbers land inside the literature ranges, the per-field expected-outcome table becomes the shipped per-field refusal policy with no further data. If they disagree, the OWN-RECORD figure governs for this athlete (an own-replicates estimate outranks a population figure) and the disagreement is itself recorded. |

## 3. Ratio table: instrument noise / decision band, every scored metric

R = u_measure / half-band. R << 1: verdict robust. R ~ 1: guard band needed.
R >> 1: verdict unreachable, refusal is the honest output. Computed by the same
script where inputs exist; NEEDS DATA where marked.

| metric (verdicts.py) | decision half-band | u_measure formula | inputs needed | status |
|---|---|---|---|---|
| weight_rate | 0.25 kg/wk (hardcoded, line 112, exactly one place) | sqrt(u_wk^2 + u_wk_prev^2), u_wk = SD_within_week/sqrt(n) | record only (Type A) | COMPUTABLE NOW |
| easy_hr | none (hard cap); effective band = \|avg - cap\| | SD of run avg_hr within week / sqrt(n_runs); instrument term needs optical-HR error | record (partial); wearable HR error PENDING stream 2 | PARTIAL |
| steps | \|avg - floor\| | between-day SD/sqrt(n) is BEHAVIOUR not instrument; device step error is Type B | step-count error figures PENDING stream 2; definitional u dominates | NEEDS DATA |
| sleep | \|avg - floor_h\| | staging error vs polysomnography, Type B only | PENDING stream 2 | NEEDS DATA |
| rhr | 5 bpm (baseline + 5) | SD_within_week/sqrt(n) (Type A) | record only | COMPUTABLE NOW |
| pain_gate | threshold on max of ordinal 0-10 self-report | not a measurement error problem; max-statistic of an ordinal has no u | none | NOT APPLICABLE: refusal machinery must never touch this row |
| intake_floor | \|mean - floor\| | logging error dominates; no instrument | PENDING stream 2 (under-reporting literature) | NEEDS DATA |
| protein_floor | \|per_kg - floor\| | compound: logging error + weight u; propagation demo | as above | NEEDS DATA |
| energy_availability | \|ea - threshold\| | compound of kcal_in, kcal_out, kg: the propagation test case for 02-engine | as above | NEEDS DATA |
| symptom_* | count vs 0 | counts; not applicable | none | NOT APPLICABLE |

Two rows are COMPUTABLE NOW (weight_rate, rhr). The script computes R for both.
That is enough to settle F1, because weight_rate is the metric F1 was stated
about.

## 4. What phase 0 does NOT do

- No schema change, no new fields, no config. Runs on what exists.
- No Type B registry. If variant A coverage is ~0 (expected), that fact is the
  finding, not a blocker: variant B needs nothing.
- No verdict vocabulary change on master. `straddle`/`refusal` live in the
  experiment output only until the gate decision.
- Does not touch `sets`, `pain_gate`, symptom rows: refusal machinery is for
  measured continuous quantities only.

Failure mode of the experiment itself: too few weeks with n >= 3 weigh-ins to
form a pooled SD. If fewer than 8 such weeks exist, report that count and
stop: the record cannot yet answer F1 from its own data, and the section 1b
literature prior (biology 0.5-2 kg/day, 5x-15x instrument error) governs the
gate provisionally until enough replicate weeks accumulate.

Effort: one afternoon (branch patch + script + run + table).
