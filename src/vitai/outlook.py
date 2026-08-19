"""What this record's own weight has done over an elapsed interval (#372).

THE ASK was a forward band for weight from the regime plus `kcal_in` and
`kcal_out`. Two measurements on the way here changed its shape, and both are
worth carrying in the source rather than in an issue thread.

FIRST, THE WIDTH CANNOT COME FROM THE ENERGY INPUTS. The operator settled it
on 2026-08-12: there is no published 24-hour total-expenditure validation for
wrist-optical devices of this class - every figure in that literature is a
laboratory bout of minutes against indirect calorimetry - so a daily
uncertainty term would be extrapolated from bout data and presented as though
it were sourced. "The width is the residual scatter of the athlete's own
weigh-in series around its own trend. Measured, not borrowed." It is also the
quantity a reader actually wants: where the scale will read, not how wrong the
watch is.

SECOND, THE CENTRE DOES NOT NEED A PHYSIOLOGICAL MODEL EITHER, and this module
does not carry one. #372 measured the classic 7700 kcal/kg rule against the
record it was raised on and found it out by 60 per cent over the same span, in
the direction that flatters a forecast, with intake logged on 24 per cent of
days and those days not a random sample. A centre from arithmetic that wrong,
wrapped in a width earned somewhere else, is the confident wrong number this
issue exists to refuse. So the centre here is an ORDER STATISTIC OF WHAT
HAPPENED: the median change this record has actually shown over that many
elapsed days. Nothing is modelled, which is why `modelled` is False rather
than absent, and a model that wants the job now has something to be checked
against - see `docs/proposals/weight-outlook.md`.

WHAT IS PUBLISHED, per horizon of `d` elapsed days:

    change      the median of every observed d-day change in the series
    change_p10  the tenth percentile of those changes
    change_p90  the ninetieth
    observed    how many d-day pairs the series holds
    windows     how many DISJOINT d-day stretches it actually observed

`p10`/`p90` AND NOT `lo`/`hi`, deliberately. A label is a claim (#400), and
`lo`/`hi` on a forward statement reads as "the weight will be in here", which
is a coverage claim about the next reading. These are order statistics of what
this record has already done. The distinction is the whole difference between
an earned band and a decorated guess.

TWO GATES, both mechanical, and a horizon that fails either is ABSENT rather
than narrow - a horizon nothing was measured over has no width to report:

  `windows >= 3`. Pairs at a fortnight horizon overlap almost completely - a
  90-day record holds dozens of them and six disjoint fortnights - so the pair
  count is not a sample size. Three is the floor `overlaps` already sets, for
  the reason contract 53 gives: below it the observations are the statement
  rather than a statement about them.

  `observed >= 11`. A tenth percentile IS the minimum until the sample reaches
  eleven, and #411 settled that observed extrema are not a coverage interval,
  since the minimum of a sample can only fall as days arrive. Eleven is the
  smallest sample in which both published quantiles are interior - derived
  from the quantile definition below rather than chosen.

SEAMS ARE THE CALLER'S TO REFUSE, and `api.Vitai.weight_outlook` does it with
the same three predicates `weight_rate` uses. A protocol change or an
undeclared instrument change under the series means the readings are not two
samples of one measurand, and averaging across them is not a series.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

# The floor `overlaps` sets, and taken from there on purpose: below three, the
# observations are the statement rather than a statement about them.
WINDOW_FLOOR = 3

# The smallest sample in which `_quantile(.., 0.10)` is not the minimum, which
# is a property of the definition below and not a number anyone picked.
SAMPLE_FLOOR = 11

DERIVED_BY = "vitai-weight-outlook"


def _kg(value: float) -> float:
    """A weight to the gram.

    A difference of two readings is exact in decimal and approximate in
    binary, so a hundred-gram change arrives from the arithmetic above as a
    seventeen-digit expansion. Publishing that would claim sixteen significant
    figures on a scale that reports two decimals, which is the same overclaim
    `weight_rate` was already caught making at three. A gram is below any
    scale's resolution, so nothing real is lost here and the artefact is.

    The digits are described rather than shown because `personal_gate.py` reads
    a long decimal as coordinate-shaped, and it is right to: that check is
    structural, and buying an illustration with a named exemption is the wrong
    trade.
    """
    return round(value, 3)


def _quantile(ordered: list[float], q: float) -> float:
    """Nearest-rank on an already-sorted list, no interpolation.

    Interpolation would invent a value between two readings, which is a small
    lie in the same family as the large ones this module refuses. It also has
    to be pinned somewhere: a consumer re-deriving these from the raw series
    with a different convention gets different edges, and this states which.
    """
    return ordered[int(q * (len(ordered) - 1))]


def observed(series: list[tuple[date, float]],
             days: int) -> list[tuple[date, float]]:
    """Every observed change across exactly `days` elapsed days, with its start.

    EXACTLY, not "about". Matching a 6-day gap to a 7-day horizon would fold
    two different elapsed intervals into one figure, and the elapsed interval
    is the whole independent variable here.
    """
    index = dict(series)
    return [(when, index[when + timedelta(days=days)] - kg)
            for when, kg in series
            if (when + timedelta(days=days)) in index]


def changes(series: list[tuple[date, float]], days: int) -> list[float]:
    """Just the changes, sorted, which is what the quantiles run over."""
    return sorted(change for _, change in observed(series, days))


def disjoint_windows(starts: list[date], days: int) -> int:
    """How many of these `days`-long stretches can be taken without overlap.

    NOT `span // days`, and the difference is the whole coverage claim. A
    record holding twenty readings in one week and twenty more a year later
    spans 365 days, so `span // 7` would call that 52 independent fortnights
    when the data lives in two clusters and speaks to a handful. Counting what
    was actually observed cannot be flattered by a gap.

    Greedy from the earliest start, which is the maximum for equal-length
    intervals and is deterministic - the alternative, "how many are there
    really", has no answer when they overlap, and any tie-break that is not
    the earliest is a choice.
    """
    count, free_from = 0, None
    for start in sorted(starts):
        if free_from is None or start >= free_from:
            count += 1
            free_from = start + timedelta(days=days)
    return count


def horizons(series: list[tuple[date, float]],
             upto: int | None = None) -> list[dict]:
    """Every elapsed interval this series can speak to, shortest first."""
    if len(series) < 2:
        return []
    span = (series[-1][0] - series[0][0]).days
    # The longest horizon that could hold `WINDOW_FLOOR` disjoint stretches.
    # Derived from the span rather than capped at a number somebody liked.
    longest = span // WINDOW_FLOOR
    if upto is not None:
        longest = min(longest, int(upto))
    rows = []
    for days in range(1, longest + 1):
        pairs = observed(series, days)
        seen = sorted(change for _, change in pairs)
        windows = disjoint_windows([start for start, _ in pairs], days)
        if len(seen) < SAMPLE_FLOOR or windows < WINDOW_FLOOR:
            continue
        rows.append({
            "days": days,
            "change": _kg(median(seen)),
            "change_p10": _kg(_quantile(seen, 0.10)),
            "change_p90": _kg(_quantile(seen, 0.90)),
            "observed": len(seen),
            "windows": windows,
        })
    return rows


def compute_outlook(series: list[tuple[date, float]],
                    upto: int | None = None,
                    refused: str | None = None,
                    build: str | None = None) -> dict:
    """The outlook over `series`, or the refusal that stops it being one.

    `refused` is passed IN rather than derived here because the reasons are
    seam predicates over full rows and this module is handed (date, kg) pairs.
    Kept as an argument rather than folded into the caller so that a refusal
    still returns the same shape - a client branching on `horizons` being
    empty and a client branching on `refused` are both right.
    """
    if refused is None and len(series) < 2:
        refused = ("fewer than two weigh-ins resolve on this record, and one "
                   "reading is not a series")
    rows = [] if refused else horizons(series, upto)
    if not rows and refused is None:
        # SAID, not left to be inferred from an empty list. A client that had
        # to tell "the seams refused this" from "nothing qualified" by looking
        # at which key was falsy would get it right by accident, and the
        # invariant worth having is the simple one: horizons are stated when
        # and only when `refused` is None.
        refused = (
            f"no elapsed interval has both {SAMPLE_FLOOR} observed changes "
            f"and {WINDOW_FLOOR} disjoint stretches behind it; this record "
            f"holds {len(series)} weigh-in(s)")
    anchor = series[-1][1] if series else None
    for row in rows:
        row["kg"] = _kg(anchor + row["change"])
        row["kg_p10"] = _kg(anchor + row["change_p10"])
        row["kg_p90"] = _kg(anchor + row["change_p90"])
    return {
        "as_of": series[-1][0].isoformat() if series else None,
        "from": series[0][0].isoformat() if series else None,
        "anchor_kg": anchor,
        "readings": len(series),
        "span_days": (series[-1][0] - series[0][0]).days if len(series) > 1 else 0,
        "horizons": rows,
        "refused": refused,
        # Contract 34's marks. `modelled` is False rather than absent because
        # the two say different things: absent is "nobody said", and this is a
        # positive claim that every figure above is an order statistic of
        # readings this record holds. A model gets an excuse for being wrong
        # that an order statistic does not, and claiming the mark would be
        # borrowing it.
        "modelled": False,
        "derived_by": DERIVED_BY,
        "derived_build": build,
    }
