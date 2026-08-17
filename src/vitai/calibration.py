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

THE ASYMMETRY NOW SURVIVES THE ROW, AND THAT IS CONTRACT 52 (#402). It did not
before: `bias` is a point and `spread` a width, so the schema could say "they
leaned this way by this much" and "they got this far apart" and could not say
"further above than below", and the shape of the disagreement reached a reader
only as a sentence in the row's `note`. `difference_lo` and `difference_hi`
carry the two observed ends, so `row` no longer drops half of what was measured.

WHAT THAT DID NOT CHANGE IS THE PART WORTH READING TWICE. Symmetrising the tails
into a plus-or-minus is still the one thing this module must never do, and on
the motivating shape it is wrong in both directions at once: `bias` plus or
minus half of `spread` puts the low edge at -0.63 km where the deepest low
reading in 101 runs is -0.03 and no observation at all falls below it, and cuts
the high edge at +0.63 where twenty-one of the 101 runs lie above, out to +1.23.
Six hundred metres of disagreement that never happened, and the finding missing.

AND THE ROW STILL EARNS NO BAND. `offset` does not lift the instrument seam, so
a row that may not be read across is not a row a band derives from whatever
columns it carries; and observed extrema are not a coverage interval, since the
minimum and maximum of 101 differences are the two most sample-dependent numbers
in the set and say nothing about the 102nd run. `observed` and `row` remain
separate keys: the pair count, the dropped days and the dates are evidence about
the derivation, and the row is what the record could hold.

THE EVIDENCE NOW HAS A RECORD OF ITS OWN, AND THAT IS CONTRACT 53 (#413). The
sentence above was true and was also the defect: "evidence about the derivation"
had nowhere to be written down, so it reached the record as `overlap_ref`, a
line of English restating the counts. `overlap` is a third key beside `row` -
the `overlaps` line holding the census - and `overlap_ref` is no longer written
here. The split is unchanged in substance: `comparability` DECLARES, `overlaps`
COUNTS, and the statistics stay on the declaration where contract 52 put them
rather than being restated in both.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from .schema import MIN_PAIRS, OFFSET, is_number

# `MIN_PAIRS` MOVED TO `schema` AT CONTRACT 53 (#413) and is imported rather
# than restated. It was this module's refusal threshold - below it nothing here
# emits a row, because a `comparability` row with a spread nobody measured is
# worse than an empty dataset - and it is now also the schema's, because an
# `overlaps` row below it records a window the engine would have refused to
# measure. One number with two enforcement points is one number; two copies of
# it would be two, and the second would be moved a contract late.
__all__ = ["MIN_PAIRS", "overlap_calibration"]


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
                        source: str = "derived",
                        dataset: str | None = None) -> dict:
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
    asymmetric that reconstruction is wrong on both sides, and the two ends are
    on the row itself as `difference_lo`/`difference_hi` (contract 52) as well
    as in `observed`.

    THE ROW IS STILL NOT A BAND, and the extra columns do not make it one. It
    proposes `offset`, `offset` does not lift the seam, and the ends are the
    extremes of a sample rather than a coverage interval over one. What a
    consumer may honestly state from this is a sentence about two instruments
    over a named overlap - not a plus-or-minus on any reading either of them
    took.
    """
    origin_a, origin_b = sorted((origin_a, origin_b))
    pairs, ambiguous = _paired(rows, field, origin_a, origin_b, on)
    head = {"field": field, "origin_a": origin_a, "origin_b": origin_b,
            "pairs": len(pairs), "ambiguous_days": ambiguous,
            "observed": None, "row": None, "overlap": None, "refused": None}

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
        # THE HALF THE ROW USED TO DROP (contract 52). The same two numbers
        # `observed` reports, written where the record can keep them, so an
        # athlete appending this line no longer destroys the asymmetry on
        # write. `spread` stays, rather than being left for a reader to
        # subtract: every existing consumer reads it, and schema validation
        # holds the two spellings of the width to each other.
        "difference_lo": low,
        "difference_hi": high,
        "basis": "overlap",
        # NO `overlap_ref` SINCE CONTRACT 53 (#413). It used to be built here,
        # and what it said was the census in English: how many days, from when
        # to when. That is the `overlap` line below, in columns, and writing
        # both would be the two-carriers-of-one-fact defect
        # `overlap_evidence_problems` now refuses - from the writer that
        # produced both of them. What the sentence carried that the census
        # cannot is the athlete's, and it goes on `note`.
        "overlap_ref": None,
        "note": None,
        "source": source,
    }
    # THE CENSUS, as the `overlaps` line the record could hold (#413). The
    # counts and the dates were always measured here and reported in the head;
    # what was missing was a shape the record could keep them in, so an athlete
    # appending what this produced kept the statistics and lost the evidence
    # about how they were derived.
    #
    # `dataset` IS THE CALLER'S TO STATE and is the one thing this function
    # cannot work out. It is handed `rows` and never learns which dataset they
    # came from, and `field` does not settle it - `distance_km` is a column of
    # both `daily` and `sessions`. Where the caller does not say, no census is
    # proposed, because a census that guessed which readings it counted would
    # be unfollowable in exactly the way the sentence it replaces was.
    if dataset is not None:
        head["overlap"] = {
            "date": pairs[-1][0],
            "dataset": dataset,
            "field": field,
            "origin_a": origin_a,
            "origin_b": origin_b,
            "paired_days": len(pairs),
            "dropped_days": len(ambiguous),
            "from_date": pairs[0][0],
            "to_date": pairs[-1][0],
            "note": None,
            "source": source,
        }
    return head
