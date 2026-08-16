"""Measuring what two instruments did when they measured the same thing (#402).

`comparability` (contract 46) is the dataset that holds a MEASURED overlap, and
it is the only route by which a band can be earned rather than assumed. It has
had no writer. The engine could express the statement and nothing produced one,
so a feature resting on it would ship dark: the rule says earn it, and there was
nothing to earn it from.

This module is the pipeline. It reads two origins' claims for one field over the
dates they both covered and states what the record actually saw.

WHAT IT DOES NOT DO, AND THIS IS THE LOAD-BEARING PART. Measuring that two
instruments disagree is not a licence to adjust either of them. Nothing here
corrects a reading, and there is deliberately no function that could: the row it
produces is evidence, and `schema`'s own rule is that the seam refusal lifts
only for `comparable`, never for `offset`. An offset is a measured difference
somebody may now reason about; applying it to a reading would be fabricating a
measurement (P4).

BIAS AND SPREAD ARE DIFFERENT FACTS AND THIS MODULE KEEPS THEM APART. A median
offset says which way the two lean; a spread says how far apart they got. The
case that motivated #402 has a median difference near zero and a wide spread,
which is the finding "these two agree on average and disagree per activity" -
and any design that collapsed the pair into one number would erase it.

THE ASYMMETRY DOES NOT SURVIVE, AND SAYING SO IS PART OF THE OUTPUT. A range
that runs further one way than the other cannot be written down here: `bias` and
`spread` are each a single number, so the schema can say "they leaned this way
by this much" and "they got this far apart" and cannot say "further above than
below". `observed` therefore returns both tails, `row` carries only what the
schema can hold, and the two are separate keys precisely so nobody mistakes the
second for the first. Symmetrising the tails into a plus-or-minus would be the
one thing this module must never do, because a band built from it would be wrong
in both directions at once - too wide on the short side, too narrow on the long.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from .schema import OFFSET, is_number

# The smallest overlap that can carry a spread at all.
#
# A DISTINCTION IN KIND, NOT A THRESHOLD PICKED TO FEEL SAFE, and the same
# distinction `outage` draws between an anecdote and a cadence. One pair gives a
# difference and no notion of how far apart the two USUALLY get; two pairs give
# two differences, whose range is just the two of them and describes no
# behaviour beyond the sample. Three is the smallest overlap for which "how far
# apart did they get" is a statement about the pair rather than a restatement of
# the observations.
#
# Below it this module emits no row. A `comparability` row with a spread nobody
# measured is worse than an empty dataset, because the entire value of the
# dataset is that a band resting on it can be trusted.
MIN_PAIRS = 3


def _paired(rows: list[dict], field: str, origin_a: str, origin_b: str,
            on: date | str | None) -> tuple[list[tuple[str, float, float]],
                                            list[str]]:
    """Dates where both origins carry exactly one usable reading of `field`.

    EXACTLY ONE, AND A DAY WITH TWO IS DROPPED RATHER THAN GUESSED AT. Two runs
    on a Saturday and two watch rows is four ways to pair them and no rule in
    the record for choosing, so the day says nothing about how the instruments
    compare. Dropped days are returned rather than swallowed: an overlap that
    looks thin because half of it was ambiguous is a different fact from one
    that was thin, and a caller deciding whether to trust a figure needs to see
    the difference.
    """
    horizon = (date.fromisoformat(on) if isinstance(on, str) else on)
    by_origin: dict[str, dict[str, list[float]]] = {origin_a: {}, origin_b: {}}
    for row in rows:
        origin = str(row.get("origin") or "")
        if origin not in by_origin:
            continue
        day = str(row.get("date") or "")
        try:
            when = date.fromisoformat(day)
        except ValueError:
            continue
        if horizon is not None and when > horizon:
            continue
        value = row.get(field)
        if not is_number(value) or isinstance(value, bool):
            continue
        by_origin[origin].setdefault(day, []).append(float(value))

    pairs, ambiguous = [], []
    for day in sorted(set(by_origin[origin_a]) & set(by_origin[origin_b])):
        left, right = by_origin[origin_a][day], by_origin[origin_b][day]
        if len(left) != 1 or len(right) != 1:
            ambiguous.append(day)
            continue
        pairs.append((day, left[0], right[0]))
    return pairs, ambiguous


def overlap_calibration(rows: list[dict], field: str, origin_a: str,
                        origin_b: str, *, on: date | str | None = None,
                        source: str = "derived") -> dict:
    """What the overlap between two origins says, and what it cannot say.

    NEVER None, for `policy.comparability`'s reason one step upstream: a caller
    asking what the record supports gets an answer in the vocabulary rather than
    a null it has to interpret. `row` is the `comparability` line the record
    could hold, or None with `refused` saying why.

    THE PAIR IS NORMALISED, because asking whether two instruments agree is one
    question regardless of which is named first. The origins are sorted, and
    every difference is the later-sorted value minus the earlier-sorted one, so
    the sign of `bias` means something fixed instead of depending on how the
    caller happened to phrase the question.

    IT ONLY EVER PROPOSES `offset`, AND NEVER `comparable`. That is not
    caution, it is the boundary between measuring and declaring. `comparable`
    LIFTS the seam refusal - it is the record saying a trend may be read across
    a change of instrument - and no overlap can establish that on its own. The
    first version of this decided the status from the arithmetic, calling a
    pair `comparable` when the median difference came out at exactly zero, and
    the corpus immediately produced the case that shows why it is wrong: two
    GPS sources whose median difference is 0.00 km and whose readings differ by
    up to 1.26 km on a given run. They agree on average and agree about nothing
    in particular, and calling them interchangeable on the strength of the
    average is exactly the fabrication the seam refusal exists to prevent.

    So a measured difference of zero is reported as an `offset` of zero, which
    is what it is: a difference that was measured and came out at nothing. It
    is the athlete who may look at that and decide the two are on one footing,
    by appending a row of her own. The engine measures; the record declares.

    `spread` IS A WIDTH, NOT A HALF-WIDTH, and it is the full observed range
    rather than a trimmed one. A band that must be EARNED should rest on the
    widest disagreement actually seen, not on a quartile that discards the days
    the two instruments diverged most - those days are the finding. A consumer
    must not read it as `bias` plus or minus `spread / 2`: where the range is
    asymmetric that reconstruction is wrong on both sides, and `observed` is
    where the two tails are readable.
    """
    origin_a, origin_b = sorted((origin_a, origin_b))
    pairs, ambiguous = _paired(rows, field, origin_a, origin_b, on)
    head = {"field": field, "origin_a": origin_a, "origin_b": origin_b,
            "pairs": len(pairs), "ambiguous_days": ambiguous,
            "observed": None, "row": None, "refused": None}

    if len(pairs) < MIN_PAIRS:
        head["refused"] = (
            f"{len(pairs)} paired reading(s) of {field!r}; a spread needs at "
            f"least {MIN_PAIRS}, because two differences are the observations "
            f"themselves rather than a statement about the pair")
        return head

    diffs = [round(right - left, 6) for _day, left, right in pairs]
    low, high = min(diffs), max(diffs)
    centre = median(diffs)
    head["observed"] = {
        "median": centre, "low": low, "high": high, "range": round(high - low, 6),
        "first": pairs[0][0], "last": pairs[-1][0],
        # THE HALF THE ROW CANNOT CARRY, stated as data rather than left for a
        # reader to infer from prose. `bias` is a point and `spread` a width, so
        # a range sitting further one side of the median than the other is
        # invisible in the row itself.
        "asymmetric": round(high - centre, 6) != round(centre - low, 6),
    }
    head["row"] = {
        "date": pairs[-1][0],
        "field": field,
        "origin_a": origin_a,
        "origin_b": origin_b,
        "status": OFFSET,
        "bias": centre,
        "spread": round(high - low, 6),
        "basis": "overlap",
        "overlap_ref": (f"{len(pairs)} day(s) both origins recorded "
                        f"{field}, {pairs[0][0]} to {pairs[-1][0]}"),
        "note": None,
        "source": source,
    }
    return head
