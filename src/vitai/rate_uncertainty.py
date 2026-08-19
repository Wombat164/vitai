"""The phase-0 weight_rate uncertainty measurement, reproducible (#460).

`verdicts.ANSWERS_BY_METRIC` scores `weight_rate` as a DIRECTION and not a
number for EVERY record. The evidence is a pre-registered run on ONE: a median
`u_rate / half-band` of 1.74, with more than half of scored weeks admitting no
verdict word at all. That judgement carries a great deal - it is why a client
may not print a rate, why #372's forward band publishes order statistics rather
than a forecast, and why #458 decided against a modelled centre.

AND THE SCRIPT THAT PRODUCED IT WAS NEVER IN THIS REPOSITORY.
`docs/proposals/uncertainty/00-phase0-experiment.md` says so plainly: "a
~60-line script in the private record's tooling directory (never in the public
repo)". The number has therefore never been reproducible here, and nothing
could say whether it holds on a second record. This module is that script,
written to the same spec, so any record can be asked the same question.

THE ESTIMATOR, from section 1.1 of that document and not invented here:

    u_wk   = SD_within_week / sqrt(n)          for a week of n >= 3 readings
           = pooled_sd / sqrt(n)               where the week itself is thinner
    u_rate = sqrt(u_prev^2 + u_cur^2)
    ratio  = u_rate / half-band

`pooled_sd` is the root mean square of the within-week SDs over every week with
at least three readings, computed once over the whole record. The half-band is
`verdicts.RATE_DECISION_BAND`, imported rather than restated so this cannot
drift from the verdict it is about.

TYPE A ONLY. The document's variant B reads per-row `kg_lo`/`kg_hi` bands, and
its own gate decision recorded coverage of 20.4 per cent overall with every
device and connector source at zero - so a variant B figure would be computed
from a handful of rows and presented as a property of the record. The two must
never be added together in any case (GUM 4.3.10).

BOTH RATIOS ARE PUBLISHED because this repository's own prose disagrees about
which one 1.74 is. The ratio table in `00-phase0-experiment.md` defines
`R = u_measure / half-band` with `u_measure = sqrt(u_prev^2 + u_cur^2)`, a
STANDARD uncertainty, and lists 1.74 under `median u_rate / half-band`.
`verdicts.py`, `db.py` and `README.md` all describe the same 1.74 as a "95 per
cent half-width". Those differ by the coverage factor the same document
defines, `K95 = 1.960`, so at most one of them is right. Rather than pick,
`median_ratio` and `median_expanded_ratio` are both stated and the reader can
compare against either.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import sqrt
from statistics import median, stdev

from .verdicts import RATE_DECISION_BAND
from .weeks import week_key

# Coverage factor for a 95 per cent interval, from section 1.1. Adopted, not
# chosen: it is the number the pre-registration used.
K95 = 1.960

DERIVED_BY = "vitai-rate-uncertainty"

# Below three readings a week has no within-week SD of its own. The pooled
# fallback needs at least one such week somewhere in the record, or there is
# nothing to pool and the estimator returns nothing for every week.
REPLICATES = 3


def by_week(series: list[tuple[str, float]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for when, kg in series:
        # `weeks.week_key` and not a local Monday calculation: the engine
        # defines a week in exactly one place, and the first draft of this
        # made it six. `test_the_engine_defines_a_week_in_exactly_one_place`
        # said so, which is the same gate that has caught this five times
        # before.
        out.setdefault(week_key(when), []).append(kg)
    return out


def pooled_sd(weeks: dict[str, list[float]]) -> float | None:
    """RMS of the within-week SDs over every week thick enough to have one."""
    sds = [stdev(vals) for vals in weeks.values() if len(vals) >= REPLICATES]
    return sqrt(sum(s * s for s in sds) / len(sds)) if sds else None


def week_u(vals: list[float], pooled: float | None) -> float | None:
    """Standard uncertainty of a weekly mean, Type A."""
    if len(vals) >= REPLICATES:
        return stdev(vals) / sqrt(len(vals))
    if pooled is not None and vals:
        return pooled / sqrt(len(vals))
    return None


def compute(series: list[tuple[str, float]],
            target_for,
            build: str | None = None) -> dict:
    """The census for one record.

    `target_for(mean_kg, week)` returns the phase rate target in force, or
    None. Passed in rather than resolved here because the policy overlay is
    the caller's to assemble, and this module has no opinion about it.
    """
    weeks = by_week(series)
    pooled = pooled_sd(weeks)
    ratios: list[float] = []
    scored = judged = refusals = straddles = 0

    for week in sorted(weeks):
        prev = (date.fromisoformat(week) - timedelta(days=7)).isoformat()
        if prev not in weeks:
            continue
        scored += 1
        u_cur, u_prev = week_u(weeks[week], pooled), week_u(weeks[prev], pooled)
        if u_cur is None or u_prev is None:
            continue
        u_rate = sqrt(u_cur ** 2 + u_prev ** 2)
        ratios.append(u_rate / RATE_DECISION_BAND)

        rate = sum(weeks[prev]) / len(weeks[prev]) - sum(weeks[week]) / len(weeks[week])
        target = target_for(sum(weeks[week]) / len(weeks[week]), week)
        if target is None:
            continue
        judged += 1
        half = K95 * u_rate
        low, high = target - RATE_DECISION_BAND, target + RATE_DECISION_BAND
        # The two severities the pre-registration defines. `refusal` is the
        # interval crossing ONE edge, so the specific verdict word is not
        # supported; `straddle` is it covering the whole band, so no word is.
        if (rate - half) < low < (rate + half) or (rate - half) < high < (rate + half):
            refusals += 1
        if (rate + half) > high and (rate - half) < low:
            straddles += 1

    refused = None
    if not ratios:
        refused = (
            f"no week in this record holds {REPLICATES} weigh-ins, so the "
            f"within-week dispersion the estimator needs does not exist and "
            f"there is nothing to pool from either; {scored} week(s) could "
            f"otherwise have been scored")
    middle = median(ratios) if ratios else None
    return {
        "half_band": RATE_DECISION_BAND,
        "coverage_factor": K95,
        "weeks": len(weeks),
        "scored": scored,
        "measurable": len(ratios),
        "judged": judged,
        "pooled_sd": round(pooled, 4) if pooled is not None else None,
        "median_ratio": round(middle, 4) if middle is not None else None,
        "median_expanded_ratio": (round(middle * K95, 4)
                                  if middle is not None else None),
        "refusal_rate": round(refusals / judged, 4) if judged else None,
        "straddle_rate": round(straddles / judged, 4) if judged else None,
        "refused": refused,
        # Nothing is modelled: every figure is a dispersion of readings this
        # record holds, put through an estimator this repository wrote down
        # before it was run anywhere.
        "modelled": False,
        "derived_by": DERIVED_BY,
        "derived_build": build,
    }
