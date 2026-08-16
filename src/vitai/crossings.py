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

Three kinds, all in `CROSSING_KINDS`:

  round_number    a multiple of `ROUND_NUMBER_LADDER` crossed, either
                  direction - "I broke 80". A CHOICE of ladder, not a
                  derivation (see the constant below).
  personal_first  a reading that is the lowest, or the highest, the record has
                  ever seen at the point it was taken.
  band            a population-reference ratio (BMI, today) crossing one of
                  `BAND_LEVELS`, either direction. See "THE BAND CROSSING"
                  below - it carries a ruling the other two do not need.

All three read the CANONICAL series, never raw claims - `Vitai.canonical()`,
which runs every existing weight consumer through `resolution.resolve()`
first. A personal-first (or a band crossing) computed over raw rows would let
one morning's scale reading and its watch re-export count as two data points
instead of one adjudicated row, and a day that happens to hold two claims
either side of a level would mint a crossing that never happened to the
athlete, only to the file.

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

WHAT THE EVIDENCE PAIR NAMES, FOR `round_number`, IS NOT THE PRIOR READING
(#370's own worked example, and the whole reason this module looks the way it
does). Tested against a real record where the athlete crossed 80 kg and a
coach improvised a frame for it:

  - "lowest ever" - false. There was a reading 5 kg lower, 13 months back.
  - "first time below 80 in over a year" - false. The last reading below 80
    was six months ago, not thirteen.
  - The true statement is "first reading below 80 since February" - smaller
    than either instinct produced, and the only one a person can check.

The immediately preceding reading supports NONE of those three sentences. It
answers "what did the scale say last time", which nobody celebrates and which
the issue never asks for. The sentence worth minting is about the SERIES
having been on the far side of a level and now returning to it, which is a
question over the whole history, not over one adjacent pair. So for
`round_number`, `previous_value`/`previous_date` name the most recent reading
that was already on the DESTINATION side of the level being crossed - below
it for a downward crossing, above it for an upward one - searched back through
the full series, not just the one reading before this one. See
`_last_on_destination_side` for the exact rule, including why landing exactly
on a level counts as being on its near side, matching `_levels_crossed`'s own
convention.

`personal_first` keeps the prior design: its evidence pair is the running
extreme itself, which is honest THERE because a personal first is a claim
about the whole history's floor or ceiling moving, not about an interval - see
`_personal_firsts` below.

THE BAND CROSSING, decided by the operator on the issue and repeated here
because it is the one rule this module must never let slip: THE ENGINE MAY
COMPUTE THE RATIO AND STATE THE BOUNDARY AS A BOUNDARY. IT MAY NEVER NAME THE
BAND. A `band` row's `value` is the numeric boundary that was crossed - a
number, never a word - exactly the way a `round_number` row's `value` is the
rung and not a sentence about it. Nothing in this module has a string field
that could hold a band's name, and that is deliberate: the shape itself makes
the violation unrepresentable here, so the risk moves entirely to whatever
prose a CONSUMER builds around the row (`cli.py`'s renderer, today - see the
test in `tests/test_crossings.py` that renders every corpus persona's band
rows and fails on a category word appearing anywhere in the output).

`BAND_LEVELS` ARE ADOPTED, NOT INVENTED (G85), so each one is only here on
the strength of a source fetched and quoted while writing this, not
transcribed from memory - see the comment beside the constant. The classes a
public health body attaches to those same numbers (its names for the bands)
are the thing this module must not reproduce, so only the numbers travel;
where a boundary's provenance could not be confirmed against a fetched
source, it was left out rather than guessed at.

THE RATIO ITSELF, AND WHY THIS TABLE DOES NOT CARRY IT: like `round_number`'s
`value`, which is the rung and never the reading that revealed it, a `band`
row's `value` is the boundary and never the athlete's actual computed ratio
on `date`. A consumer wanting to say "your ratio is 25.4 and the boundary is
25.0" - `docs/medical-boundary.md` class (a), permitted - already has
everything needed to compute 25.4 itself, from the same canonical weight and
`measurements` rows this module reads; storing it a second time here would be
exactly the kind of derived value this engine keeps out of the ground truth
and does not need to keep out of a read-only table either, when nothing here
is authoritative for it.
"""

from __future__ import annotations

import math

from .policy import height_on
from .schema import is_number

# The vocabulary, the way `schema.COMPETENCES` is a bare closed set beside the
# dataset it classifies. Lives here rather than in `schema.py` because it is
# not athlete-facing input vocabulary - nothing appends a `crossings` row and
# nothing validates one; it is this module's own output shape, the same
# relationship `contributions.MILESTONE_FRACTIONS` has to `_milestones`.
CROSSING_KINDS = {"round_number", "personal_first", "band"}
CROSSING_DIRECTIONS = {"down", "up"}

# A CHOICE, not a derivation - nothing about a kilogram makes 5 the right
# step. It is what people actually say out loud: "I broke 80", not "I broke
# 82.5" or "I broke 75". Round numbers in fives are how a scale reading turns
# into a sentence a person would say to another person, and that is the whole
# basis for picking it over any other step size.
ROUND_NUMBER_LADDER = 5.0

# ADOPTED, NOT INVENTED (G85) - three numbers, fetched while writing this
# change rather than typed from memory. Deliberately NOT quoting the source's
# own sentence here, unlike a citation elsewhere in this codebase might: its
# wording is built entirely from the vocabulary this module exists to keep
# out of its own comments, let alone its output, and #382 exists precisely
# because that vocabulary is easy to reproduce by accident while explaining
# why it is forbidden.
#
# SOURCE: US NHLBI, "Assessing Your Weight" (fetched 2026-08-13),
# https://www.nhlbi.nih.gov/health/educational/lose_wt/BMI/bmi_dis.htm -
# a table of four adjoining bands over the BMI scale, split at three
# lower edges: 18.5, 25.0 and 30.0. Those three numbers are
# `BAND_LEVELS` below; nothing about what the source CALLS each band
# travels with them.
#
# A finer split above the third edge (three narrower bands rather than one)
# is common in secondary sources but is NOT included here: the two primary
# pages fetched while writing this change - the one above, and a CDC page
# that would carry the same finer split - either omitted it (this one does)
# or returned an error rather than content (the CDC page, HTTP 403). A
# boundary this module could not confirm against a source it could actually
# read stays out of the ladder, on the same principle #382's deny list is a
# floor rather than a definition: better three checked edges than a fourth
# dressed up as equally authoritative.
BAND_LEVELS = (18.5, 25.0, 30.0)


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


def _last_on_destination_side(points: list[tuple[str, float]], idx: int,
                              level: float, direction: str) -> tuple[str | None, float | None]:
    """The most recent reading at or before `points[idx]` that already sat on
    the DESTINATION side of `level` - the side this crossing is arriving at:
    below `level` for a "down" crossing, above it for an "up" one. That
    reading is what makes "first below 80 since <date>" true rather than
    fabricated, so this is the whole mechanism the fix in #370 turns on.

    SIDE MEMBERSHIP REUSES `_levels_crossed`'s OWN NEAR-SIDE-INCLUSIVE RULE: a
    value sitting exactly ON `level` already counts as having reached the
    down side (`v <= level`) or the up side (`v >= level`), the same
    convention that makes "sitting on a rung" not re-cross it on the way off.
    Anything else would let this function and the crossing detector disagree
    about what "on that side" means for the one value that sits on the
    boundary.

    `idx` is the index of the reading immediately BEFORE the one that
    triggered this crossing, so the scan starts there and walks backward.
    That reading is included for completeness but can never itself match: by
    construction, every level `_levels_crossed` returns is strictly on the
    far side of `points[idx]`'s value (that is what "crossed" means), so the
    scan always has to look further back to find a match - which is exactly
    how "the previous reading was 81" gets replaced by "six months ago", not
    "the reading before this one".

    Returns `(None, None)` when no earlier reading was ever on that side -
    the series' first-ever arrival there. THAT IS A STRONGER FACT, not a data
    gap, and a caller tells the two apart because a data gap cannot happen
    here: nothing in this module ever mints a row from a partial or missing
    point, so a null pair from a MINTED round_number row always means "never
    before", and only that.
    """
    on_side = (lambda v: v <= level) if direction == "down" else (lambda v: v >= level)
    for j in range(idx, -1, -1):
        d, v = points[j]
        if on_side(v):
            return d, v
    return None, None


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
    for idx, ((_prev_date, prev_v), (this_date, this_v)) in enumerate(zip(points, points[1:])):
        direction = "down" if this_v < prev_v else "up"
        for level in _levels_crossed(prev_v, this_v, ladder):
            ev_date, ev_v = _last_on_destination_side(points, idx, level, direction)
            out.append({
                "date": this_date, "kind": "round_number", "metric": metric,
                "value": level, "direction": direction,
                "previous_value": ev_v, "previous_date": ev_date,
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


def _band_levels_crossed(prev_v: float, curr_v: float,
                         levels: tuple[float, ...]) -> list[float]:
    """Boundaries in `levels` crossed between two RATIO readings, ordered in
    the direction of travel (nearest `prev_v` first) - `_levels_crossed`'s own
    convention, generalised from a uniform LADDER step to an arbitrary,
    irregularly-spaced set of levels.

    SAME RULE, DIFFERENT ARITHMETIC. `_levels_crossed` walks a uniform ladder
    by floor/ceil-ing to the nearest rung, which has no equivalent over a set
    like `BAND_LEVELS` (18.5, 25.0, 30.0 - not evenly spaced), so this is a
    fresh walk rather than a call into it. But the INCLUSION RULE is the one
    `_levels_crossed` already established, not a second convention invented
    beside it: a level `L` counts as crossed downward when
    `prev_v > L >= curr_v`, and upward when `prev_v < L <= curr_v` - strict on
    the far side, inclusive on the near one, so landing exactly on `L` counts
    as having reached it and sitting there already does not re-cross it on the
    way off.
    """
    if curr_v == prev_v:
        return []
    if curr_v < prev_v:
        return sorted((L for L in levels if prev_v > L >= curr_v), reverse=True)
    return sorted(L for L in levels if prev_v < L <= curr_v)


def _band_points(weight_points: list[tuple[str, float]],
                 measurement_rows: list[dict]) -> list[tuple[str, float]]:
    """(date, ratio) for every weight point with a height already in force.

    ONE RATIO SERIES BUILT FROM TWO CANONICAL SERIES: `weight_points` is the
    same (date, reading) list `compute_crossings` builds for `round_number`
    and `personal_first`, and `measurement_rows` supplies the height in force
    on each of those dates via `policy.height_on` - THE HEIGHT MUST BE
    EFFECTIVE-DATED (#148's lesson, restated when `height_cm` was decided),
    and `height_on` is `_in_force`'s own machinery reused rather than a second
    sort-and-pick-last written here.

    A WEIGHT READING WITH NO HEIGHT YET IN FORCE CONTRIBUTES NOTHING - not a
    ratio back-filled from a LATER height. This is what makes a weight series
    that starts before the first `height_cm` row safe to feed straight in:
    its early readings are simply absent from the ratio series, the same way
    every other gap in this module is honoured by omission rather than by
    inventing a value. "A record with no height before some date has no ratio
    before that date" is this loop's whole body, not a special case bolted
    onto it.
    """
    out: list[tuple[str, float]] = []
    for d, w in weight_points:
        h_cm = height_on(measurement_rows, d)
        if h_cm is None or h_cm <= 0:
            continue
        h_m = h_cm / 100.0
        out.append((d, w / (h_m * h_m)))
    return out


def _band_crossings(points: list[tuple[str, float]], metric: str,
                    levels: tuple[float, ...]) -> list[dict]:
    """One row per band boundary the ratio series crosses, in either
    direction - `_round_numbers`'s own shape, over `levels` (an arbitrary,
    irregular set) instead of a uniform ladder, and over a RATIO series
    instead of a raw reading series.

    RE-CROSSING IS NOT DEDUPLICATED, for the reason `_round_numbers` gives: a
    ratio that drops under a boundary, climbs back over, and drops under it
    again has crossed it three times, and each is a fact about a different
    stretch of the series with its own evidence pair - real behaviour a real
    persona in this corpus exhibits (see `tests/fixtures/personas/yasmin`),
    not a hypothetical this module has to imagine to justify not
    deduplicating it.

    THE EVIDENCE PAIR REUSES `_last_on_destination_side` UNCHANGED. That
    function has never known its `points` were weight - it walks whatever
    series it is given - so pointing it at a ratio series answers exactly the
    question it already answers for `round_number`: the most recent reading
    already on the side THIS crossing is arriving at, never the ratio
    computed at the visit immediately before.

    `value` IS THE BOUNDARY, NEVER A NAME - the whole point of this table
    (see the module docstring's THE BAND CROSSING section). A downstream
    consumer may say "the ratio is 25.4 and the boundary is 25.0"; nothing
    here has anywhere to put the word a population-health source would
    attach to that boundary.

    STATED PRECISELY, because the loose version of this sentence said "no
    field on this row is a string" and that is simply false - `date`, `kind`,
    `metric` and `direction` all are. The true property is narrower and is
    what actually closes the hole: `value` is always numeric, and every
    string field is either an ISO date or drawn from a closed vocabulary
    (`kind` from `CROSSING_KINDS`, `direction` from up/down, `metric` from
    the metric this was computed for). There is no free-text field anywhere
    on the row, so no category word can arrive as data - it could only ever
    arrive from a renderer, which is why the control that guards this rule
    scans rendered output rather than the row shape.
    """
    out: list[dict] = []
    for idx, ((_prev_date, prev_v), (this_date, this_v)) in enumerate(zip(points, points[1:])):
        direction = "down" if this_v < prev_v else "up"
        for level in _band_levels_crossed(prev_v, this_v, levels):
            ev_date, ev_v = _last_on_destination_side(points, idx, level, direction)
            out.append({
                "date": this_date, "kind": "band", "metric": metric,
                "value": level, "direction": direction,
                "previous_value": ev_v, "previous_date": ev_date,
            })
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


def compute_band_crossings(weight_rows: list[dict], measurement_rows: list[dict],
                           weight_metric: str = "kg", metric: str = "bmi",
                           levels: tuple[float, ...] = BAND_LEVELS) -> list[dict]:
    """Band crossings (BMI, today) over one canonical weight series and one
    canonical `measurements` series (#370's third kind).

    A SEPARATE FUNCTION, NOT A THIRD BRANCH OF `compute_crossings`, because a
    band crossing needs TWO series where the other two kinds need one: a
    weight reading alone cannot say whether a boundary was crossed without
    the height in force on the same date. `weight_rows` is
    `Vitai.canonical("weight")`, exactly as `compute_crossings` already reads
    it; `measurement_rows` is `Vitai.canonical("measurements")` - the same
    resolved series `policy.height_on` reads to answer "the height in force
    on this date". Both canonical for the reason `compute_crossings`'s own
    docstring gives: a day resolved from two competing claims, weight or
    height, must count once before a crossing is ever computed over it.

    `weight_metric` names the raw field (`kg`); `metric` names the RATIO this
    function's rows carry (`bmi`) - two parameters because they are two
    different things, the way a `round_number` row's rung is not the reading
    that revealed it. Nothing below this line knows the ratio is BMI
    specifically - dividing `weight_metric` by a squared height IS what makes
    it BMI - so a second population-reference ratio, built the same way, is a
    second call with a different `weight_metric`/`levels` pair, not a
    rewrite.

    A DATE WITH NO HEIGHT YET IN FORCE MINTS NOTHING - see `_band_points`. A
    record whose weight history starts before its first `height_cm` row
    straddles cleanly: the early readings are simply absent from the ratio
    series, and the earliest crossing this function can ever mint is on or
    after the date a height first exists to divide by.

    Ordered by (date, kind, direction, value), the same key `compute_crossings`
    sorts by, so a caller combining both lists (`Vitai.crossings()` does) gets
    one deterministically-ordered sequence rather than two independently-sorted
    ones concatenated.
    """
    weight_points = sorted((r["date"], r[weight_metric]) for r in weight_rows
                           if is_number(r.get(weight_metric)))
    band_points = _band_points(weight_points, measurement_rows)
    out = _band_crossings(band_points, metric, levels)
    out.sort(key=lambda r: (r["date"], r["kind"], r["direction"], r["value"]))
    return out
