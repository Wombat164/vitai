"""Goal-independent, history-wide milestones over an observation series (#370).

`milestones` (see `contributions._milestones`) answers a different question:
fractional progress toward a DECLARED goal target, scored per bucket and
gated to floor-polarity goals - a weight goal is an `approach` and mints
nothing there, by design. A `crossings` row needs no goal at all. "You broke
80 kg" and "that is the lowest you have ever weighed" are true or false of the
SERIES itself, on every date the record covers, whether or not the athlete
ever declared a target - and `milestones`' columns (`goal`, `period`,
`fraction`, `target`) have no honest value to give either fact. Forcing them
in would mean inventing a fake goal and a fake fraction for something that has
neither, which is why this is a new table rather than a new row shape in that
one.

Two kinds, both in `CROSSING_KINDS`:

  round_number    a multiple of `ROUND_NUMBER_LADDER` crossed, either
                  direction - "I broke 80". A CHOICE of ladder, not a
                  derivation (see the constant below).
  personal_first  a reading that is the lowest, or the highest, the record has
                  ever seen at the point it was taken.

Both read the CANONICAL series, never raw claims - `Vitai.canonical()`, which
runs every existing weight consumer through `resolution.resolve()` first. A
personal-first computed over raw rows would let one morning's scale reading
and its watch re-export count as two data points instead of one adjudicated
row, and a day that happens to hold two claims either side of a level would
mint a crossing that never happened to the athlete, only to the file.

`metric` IS A PARAMETER, never a hardcoded field name, though `kg` is the only
metric wired to a caller today (#370 builds the weight case; the issue is
explicit that nothing here should block a second metric arriving later
without touching this module).

EVERY MINTED ROW CARRIES ITS EVIDENCE PAIR: `previous_value` and
`previous_date` name the reading that establishes the OTHER side of the
crossing. A row with a `value` and no `previous_value` would be an assertion
- "this is a round number" - rather than a fact about the series moving
across one. Because of that, nothing here ever mints a row for a series with
fewer than two points: the first reading has no `previous_value` to cite, so
it cannot be evidence for anything yet, only a first fact for a later row to
cite against.
"""

from __future__ import annotations

import math

from .schema import is_number

# The vocabulary, the way `schema.COMPETENCES` is a bare closed set beside the
# dataset it classifies. Lives here rather than in `schema.py` because it is
# not athlete-facing input vocabulary - nothing appends a `crossings` row and
# nothing validates one; it is this module's own output shape, the same
# relationship `contributions.MILESTONE_FRACTIONS` has to `_milestones`.
CROSSING_KINDS = {"round_number", "personal_first"}
CROSSING_DIRECTIONS = {"down", "up"}

# A CHOICE, not a derivation - nothing about a kilogram makes 5 the right
# step. It is what people actually say out loud: "I broke 80", not "I broke
# 82.5" or "I broke 75". Round numbers in fives are how a scale reading turns
# into a sentence a person would say to another person, and that is the whole
# basis for picking it over any other step size.
ROUND_NUMBER_LADDER = 5.0


def _levels_crossed(prev_v: float, curr_v: float,
                    ladder: float) -> list[float]:
    """Multiples of `ladder` the series moved past between two READINGS,
    ordered in the direction of travel (nearest `prev_v` first).

    STRICT ON THE FAR SIDE, INCLUSIVE ON THE NEAR ONE: a level `L` counts as
    crossed downward when `prev_v > L >= curr_v`, and upward when
    `prev_v < L <= curr_v`. Landing exactly on `L` counts as having reached
    it - a scale reading of exactly 80.0 kg is "I broke 80" the same as 79.6
    is - but SITTING at `L` already does not count as leaving it: if the
    previous reading was itself exactly on a level, this function will not
    re-report that level on the next step away from it, because `prev_v` is
    no longer STRICTLY past it. That is what stops a series sitting at
    80.0, 80.0, 79.9 from minting two crossings of 80 for one departure.

    ALL LEVELS IN ONE JUMP, not just the nearest. Two readings a long gap
    apart can skip several rungs - 91 kg to 78 kg crosses 90, 85 and 80 - and
    each one is a fact about the series independent of whether the athlete
    was weighed in between. Only the LAST recorded step's evidence pair backs
    every level in the jump, because that pair is the only observation the
    record actually holds for it.
    """
    if curr_v == prev_v:
        return []
    if curr_v < prev_v:
        top = math.floor(prev_v / ladder) * ladder
        if top >= prev_v:            # prev_v itself sits exactly on a rung
            top -= ladder
        levels, level = [], top
        while level >= curr_v:
            levels.append(level)
            level -= ladder
        return levels
    bottom = math.ceil(prev_v / ladder) * ladder
    if bottom <= prev_v:             # prev_v itself sits exactly on a rung
        bottom += ladder
    levels, level = [], bottom
    while level <= curr_v:
        levels.append(level)
        level += ladder
    return levels


def _round_numbers(points: list[tuple[str, float]], metric: str,
                   ladder: float) -> list[dict]:
    """One row per rung of `ladder` the series crosses, in either direction.

    RE-CROSSING IS NOT DEDUPLICATED, on purpose (#370's own example): a value
    that goes under 80, back over, and under again has crossed three times,
    and each is a fact about a different stretch of the series with its own
    evidence pair. Suppressing repeats would be treating the third crossing
    as noise about the first, which is exactly the thing a round number is
    supposed to let a person notice.
    """
    out: list[dict] = []
    for (prev_date, prev_v), (this_date, this_v) in zip(points, points[1:]):
        for level in _levels_crossed(prev_v, this_v, ladder):
            out.append({
                "date": this_date, "kind": "round_number", "metric": metric,
                "value": level,
                "direction": "down" if this_v < prev_v else "up",
                "previous_value": prev_v, "previous_date": prev_date,
            })
    return out


def _personal_firsts(points: list[tuple[str, float]], metric: str) -> list[dict]:
    """One row per reading that beats every reading before it, low or high.

    THE FIRST READING MINTS NOTHING (#370's own question). It is trivially
    both the lowest and the highest value the record has ever seen, because
    it is the only one - and a crossing with no `previous_value` to cite
    would be announcing a fact about a series of one, which is not a fact
    about a series at all. It becomes the FLOOR the second reading is judged
    against instead, which is the only thing it is honestly evidence for.

    STRICT COMPARISON: a reading equal to the running extreme ties it rather
    than beating it, and a tie is not a new personal anything.
    """
    if len(points) < 2:
        return []
    out: list[dict] = []
    (low_date, low_v), (high_date, high_v) = points[0], points[0]
    for this_date, this_v in points[1:]:
        if this_v < low_v:
            out.append({
                "date": this_date, "kind": "personal_first", "metric": metric,
                "value": this_v, "direction": "down",
                "previous_value": low_v, "previous_date": low_date,
            })
            low_date, low_v = this_date, this_v
        elif this_v > high_v:
            out.append({
                "date": this_date, "kind": "personal_first", "metric": metric,
                "value": this_v, "direction": "up",
                "previous_value": high_v, "previous_date": high_date,
            })
            high_date, high_v = this_date, this_v
    return out


def compute_crossings(rows: list[dict], metric: str = "kg",
                      ladder: float = ROUND_NUMBER_LADDER) -> list[dict]:
    """Round-number and personal-first crossings over one canonical series.

    `rows` is a CANONICAL dataset - one row per date, already adjudicated by
    `resolution.resolve()` - never raw claims. `metric` names the field to
    read off each row (`kg` for the weight dataset today); nothing below this
    line knows it is weight, so a second metric is a second call, not a
    second code path.

    Ordered by (date, kind, direction, value) so two rows sharing a date -
    a round number and a personal first on the same reading, which the demo
    record does hit - sort deterministically rather than by dict insertion
    order, which is not a promise this function makes anywhere else.
    """
    points = sorted((r["date"], r[metric]) for r in rows if is_number(r.get(metric)))
    out = _round_numbers(points, metric, ladder) + _personal_firsts(points, metric)
    out.sort(key=lambda r: (r["date"], r["kind"], r["direction"], r["value"]))
    return out
