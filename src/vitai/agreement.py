"""Does this record's own energy balance explain its own weight change? (#458)

#457 built the WIDTH of #372's forward band and left the CENTRE. #458 filed the
centre with an acceptance gate: a proposed centre must sit inside the observed
p10..p90 for that horizon. Measuring before building, which is what #457 was
for, says the gate cannot be run and the centre cannot be stated. The argument
and every number are in `docs/proposals/weight-outlook.md`; the short form:

THIRTEEN OF SIXTEEN RECORDS IN THIS REPOSITORY HOLD NOT ONE COMPLETE SEVEN-DAY
WINDOW - a window needing `kcal_in` and `kcal_out` on all seven days and a
weigh-in at each end. The three that do say no: knowing the balance does not
narrow the change, even with the energy density FITTED to that record rather
than taken from the literature.

AND THAT RESULT PROVES NOTHING ABOUT PHYSIOLOGY, which is the part that
decides this. `examples/generate_demo.py` draws weight from one random stream
and the two energy figures from two others; `nora` draws `kcal_in` from a
uniform beside a weight series it never sees. The correlation is zero BY
CONSTRUCTION. So this corpus can neither confirm nor refute an energy model -
the gate is uninformative in both directions, and a model that passed it here
would have passed against noise.

SO WHAT SHIPS IS THE INSTRUMENT AND NOT THE MODEL. This module answers whether
a centre COULD be earned on a given record and never what it would be. Its
answer everywhere it has been asked is no or cannot-say, and the day a record
answers otherwise is the day the question reopens with evidence behind it.

THE COMPARISON IS DELIBERATELY GENEROUS. The literature 7700 kcal/kg is not
what is tested - the density is fitted to the record by least squares, so the
model being scored is the BEST constant-density model that exists for it. A
family that cannot beat a median at its own best cannot beat it at a borrowed
constant, and testing the borrowed constant instead would leave "you used the
wrong number" available as an answer.

THE NULL IS THE RECORD'S OWN MEDIAN, which is #457's answer to the same
question. That is what a client has today, so it is what a model has to beat
to be worth anything; measuring a model's error against zero instead would
make any model look informative.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import correlation, linear_regression, median

# The same two floors the outlook uses, imported rather than restated: eleven
# is the smallest sample in which a tenth percentile is interior, and three is
# the floor `overlaps` sets. A second pair of numbers here would be a second
# opinion about the same question.
#
# `_quantile` comes across too, and its privacy is the reason it must: the
# spreads below are compared against the outlook's, and two quantile
# conventions would make the comparison meaningless while looking fine.
from .outlook import (SAMPLE_FLOOR, WINDOW_FLOOR,  # noqa: F401
                      _quantile, disjoint_windows)

DERIVED_BY = "vitai-energy-agreement"

# The horizon this is asked over unless a caller says otherwise. SEVEN because
# it is the unit `weight_rate` is already judged on, not because a week is a
# natural period for a body.
DEFAULT_DAYS = 7


def _spread(values: list[float]) -> float:
    """The p10..p90 width about the median, which is the outlook's statistic.

    ABOUT THE MEDIAN rather than about zero, and that is generous to the model
    on purpose: a model with a constant bias is forgiven it here, because a
    bias is correctable and a spread is not. If it fails even forgiven, it
    fails.
    """
    mid = median(values)
    centred = sorted(v - mid for v in values)
    return _quantile(centred, 0.90) - _quantile(centred, 0.10)


def windows(series: list[tuple[date, float]],
            daily: dict[date, dict],
            days: int) -> tuple[list[tuple[date, float, float]], int]:
    """Every fully-logged `days`-window, and how many windows existed at all.

    A window counts only where BOTH energy figures are present on every day
    inside it. A part-logged week is not a smaller week - the missing days are
    the ones this engine has already measured to be the unrepresentative ones
    (#372: intake logged on 24 per cent of days, and those the days eating
    went to plan), so filling or prorating them would build the selection bias
    into the arithmetic and then hide it inside a total.

    The second return is how many windows had weigh-ins at both ends
    regardless of energy, so a caller can tell "the model failed" from "the
    model was never tried".
    """
    index = dict(series)
    full: list[tuple[date, float, float]] = []
    possible = 0
    for when, kg in series:
        end = when + timedelta(days=days)
        if end not in index:
            continue
        possible += 1
        span = [daily.get(when + timedelta(days=i)) for i in range(1, days + 1)]
        if any(row is None or row.get("kcal_in") is None
               or row.get("kcal_out") is None for row in span):
            continue
        balance = sum(row["kcal_out"] - row["kcal_in"] for row in span)
        full.append((when, index[end] - kg, float(balance)))
    return full, possible


def compute_agreement(series: list[tuple[date, float]],
                      daily: dict[date, dict],
                      days: int = DEFAULT_DAYS,
                      refused: str | None = None,
                      build: str | None = None) -> dict:
    """Whether the balance explains the change, or why that cannot be asked."""
    full, possible = ([], 0) if refused else windows(series, daily, days)
    disjoint = disjoint_windows([start for start, _, _ in full], days)
    changes = [change for _, change, _ in full]
    balances = [balance for _, _, balance in full]

    if refused is None:
        if len(full) < SAMPLE_FLOOR or disjoint < WINDOW_FLOOR:
            refused = (
                f"this record holds {len(full)} fully-logged {days}-day "
                f"window(s) in {disjoint} disjoint stretch(es), and the "
                f"question needs {SAMPLE_FLOOR} and {WINDOW_FLOOR}; "
                f"{possible} window(s) had weigh-ins at both ends, so what is "
                f"missing is the logging rather than the weighing")
        elif len(set(balances)) < 2 or len(set(changes)) < 2:
            refused = ("every window carries the same balance or the same "
                       "change, so there is nothing for a slope to be a slope "
                       "of")

    out = {
        "days": days,
        "complete": len(full),
        "possible": possible,
        "windows": disjoint,
        "correlation": None,
        "implied_kcal_per_kg": None,
        "null_spread": None,
        "fitted_spread": None,
        "explains": None,
        "refused": refused,
        # Nothing is modelled HERE either: every figure below is a statistic
        # of readings the record holds. The model being scored is fitted and
        # then thrown away - it is never published and never applied.
        "modelled": False,
        "derived_by": DERIVED_BY,
        "derived_build": build,
    }
    if refused:
        return out

    fit = linear_regression(balances, changes)
    held = _held_out(full, days)
    if held is None:
        out["refused"] = (
            "no window can be scored against a fit that did not contain it; "
            f"every fully-logged window overlaps too many others to leave "
            f"{SAMPLE_FLOOR} scorable")
        return out
    out["correlation"] = round(correlation(balances, changes), 3)
    # PUBLISHED BESIDE THE CORRELATION AND NEVER ALONE. This is the successor
    # to #372's hand calculation that the 7700 rule was 60 per cent out on one
    # span - measured over every window instead. It is the slope of a fit, so
    # when the correlation is near zero it is a slope through noise and the
    # number it reports is meaningless in a way that looks authoritative. It
    # is here so a reader can see how far from 7700 the record lands, not so
    # anyone can use it.
    out["implied_kcal_per_kg"] = (
        round(-1.0 / fit.slope) if fit.slope else None)
    out["null_spread"] = round(_spread(changes), 3)
    out["fitted_spread"] = round(_spread(held), 3)
    # TWO CONDITIONS, AND THE FIRST IS A DOMAIN CONSTRAINT RATHER THAN A
    # THRESHOLD. An energy density is positive by definition: a record whose
    # weight RISES with its deficit has not produced a weak model, it has
    # produced a contradiction, and `implied_kcal_per_kg` coming back negative
    # says so in the plainest possible way.
    #
    # It is also what stops the second condition deciding on noise. A fit with
    # no slope predicts the mean, which is what the null already does, so its
    # residual spread lands within a gram of the null's and a strict `<` then
    # turns on the third decimal - `nora` sat at 1.299 against 1.300 across
    # 844 windows with a correlation of 0.022. Requiring the sign first
    # removes that class of tie without inventing a margin to compare against.
    out["explains"] = bool(
        out["implied_kcal_per_kg"] and out["implied_kcal_per_kg"] > 0
        and out["fitted_spread"] < out["null_spread"])
    return out


def _held_out(full: list[tuple[date, float, float]],
              days: int) -> list[float] | None:
    """Residuals from fits that never saw the window they are scoring.

    THE FIRST VERSION OF THIS SCORED THE FIT ON ITS OWN TRAINING DATA, and it
    reported that the shipped demo's energy balance EXPLAINS its weight change
    - on a record where `generate_demo.py` draws the two from unrelated random
    streams. A least-squares slope always reduces in-sample spread a little,
    because it has fitted the noise, so `fitted < null` was true by
    construction and the surface answered yes to a question it could only
    honestly answer no to.

    BLOCKED, not plain leave-one-out. The windows overlap - a seven-day window
    starting on Monday shares six readings with the one starting on Tuesday -
    so leaving out one window still leaves six near-copies of it in the fit,
    and the leak is most of the window. A fit for the window at `t` therefore
    sees only windows that do not touch `[t, t + days]` at all.

    None when too few windows can be scored that way, which is the honest
    answer for a record whose logged stretches are all one clump: there is
    nothing to hold out against.
    """
    residuals = []
    for start, change, balance in full:
        rest = [(c, b) for other, c, b in full
                if abs((other - start).days) >= days]
        if len(rest) < 2 or len({b for _, b in rest}) < 2:
            continue
        fit = linear_regression([b for _, b in rest], [c for c, _ in rest])
        residuals.append(change - (fit.slope * balance + fit.intercept))
    return residuals if len(residuals) >= SAMPLE_FLOOR else None
