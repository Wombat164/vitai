"""Round-number, personal-first and band milestones, goal-independent and
history-wide (#370).

`milestones` needs a declared goal and a scoring bucket; these three kinds do
not, which is why they are a new table (`crossings.py`, `db.CROSSING_KEYS`)
rather than a new row shape in that one. See `crossings.py`'s module
docstring for the full design, and `db.py` beside contracts 47 and 48 for the
column-by-column reasoning - this file holds it to the letter.

Most cases are checked against `compute_crossings`/`compute_band_crossings`
directly, over synthetic point lists, because the interesting behaviour is in
the walk across consecutive readings and a bare list of `{"date", "kg"}` (or
`{"date", "kind", "value"}` for a height) dicts is the whole input that logic
needs. The handful of cases that are about the ENGINE rather than the
arithmetic - canonical resolution, an empty record, the three surfaces
agreeing - go through a real `Vitai` instance instead.

THE CONTROL AT THE BOTTOM OF THIS FILE (`test_no_band_row_is_ever_rendered_
with_a_category_word`) IS NOT LIKE THE OTHERS. Every other test in this file
checks that the engine computes the right NUMBER. That one checks the rule
the whole feature exists to keep - "the engine may compute the ratio and
state the boundary as a boundary; it may never name the band" - against the
ACTUAL RENDERED TEXT a real consumer would see, over the WHOLE committed
persona corpus, using a category-word list authored independently of
`scripts/boundary_gate.py`'s own deny list. See that test's docstring for why
both of those choices are load-bearing rather than stylistic.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from vitai import mcp
from vitai.api import Vitai, init
from vitai.crossings import (BAND_LEVELS, CROSSING_DIRECTIONS, CROSSING_KINDS,
                             ROUND_NUMBER_LADDER, compute_band_crossings,
                             compute_crossings)
from vitai.db import CROSSING_KEYS

PERSONAS = Path(__file__).parent / "fixtures" / "personas"


def _rows(kind: str, points: list[dict]) -> list[dict]:
    return [r for r in compute_crossings(points) if r["kind"] == kind]


# --- round_number --------------------------------------------------------------

def test_a_downward_round_number_crossing_has_the_right_evidence_pair():
    """Two readings only, so there is no history below 80 to find - the
    evidence pair is null, the "first time ever" case, not the preceding
    reading (81.2, which is on the WRONG side of 80 to be evidence for a
    downward crossing at all)."""
    points = [{"date": "2030-01-01", "kg": 81.2}, {"date": "2030-01-05", "kg": 79.6}]
    got = _rows("round_number", points)
    assert got == [{
        "date": "2030-01-05", "kind": "round_number", "metric": "kg",
        "value": 80.0, "direction": "down",
        "previous_value": None, "previous_date": None,
    }]


def test_an_upward_round_number_crossing_has_the_right_evidence_pair():
    """Same shape, upward: 78.4 is on the wrong side to be evidence for
    "back above 80", and there is nothing earlier - null pair."""
    points = [{"date": "2030-01-01", "kg": 78.4}, {"date": "2030-01-05", "kg": 80.7}]
    got = _rows("round_number", points)
    assert got == [{
        "date": "2030-01-05", "kind": "round_number", "metric": "kg",
        "value": 80.0, "direction": "up",
        "previous_value": None, "previous_date": None,
    }]


def test_the_evidence_pair_names_the_destination_side_not_the_prior_reading():
    """#370's own worked example, built explicitly. A reading right before
    the crossing (81.0, last week) is on the WRONG side of 80 to answer
    "since when has this been true" - the record was below 80 six months
    ago, and that is the reading that makes "first below 80 since <date>"
    true. The far reading from 13 months back (75.0, a lower value but the
    WRONG fact - #370's "lowest ever" instinct) must not win just because it
    is more extreme; the nearer of the two on-side readings does."""
    points = [
        {"date": "2029-01-01", "kg": 75.0},   # 13 months back: lower, but stale
        {"date": "2029-02-01", "kg": 82.0},    # back above 80
        {"date": "2029-08-01", "kg": 79.0},    # 6 months back: last time below 80
        {"date": "2029-09-01", "kg": 83.0},    # back above 80 again
        {"date": "2030-02-01", "kg": 78.0},    # today: crosses 80 down again
    ]
    got = [r for r in _rows("round_number", points) if r["value"] == 80.0]
    todays = [r for r in got if r["date"] == "2030-02-01"]
    assert todays == [{
        "date": "2030-02-01", "kind": "round_number", "metric": "kg",
        "value": 80.0, "direction": "down",
        "previous_value": 79.0, "previous_date": "2029-08-01",
    }], todays


def test_approaching_a_level_without_reaching_it_mints_nothing():
    """Both readings stay on the SAME side of 80 - close is not crossed."""
    points = [{"date": "2030-01-01", "kg": 81.0}, {"date": "2030-01-05", "kg": 80.3}]
    assert _rows("round_number", points) == []


def test_landing_exactly_on_the_level_counts_as_reaching_it():
    """A scale reading of exactly 80.0 kg is "I broke 80" the same as 79.6 is
    - the level counts as crossed on the near (inclusive) side."""
    points = [{"date": "2030-01-01", "kg": 81.0}, {"date": "2030-01-05", "kg": 80.0}]
    got = _rows("round_number", points)
    assert got and got[0]["value"] == 80.0 and got[0]["direction"] == "down"


def test_a_recrossing_mints_a_second_row_with_its_own_evidence():
    """#370's own example: under 80, back over, under again - three
    crossings, not one deduplicated to a single "current side" fact. Each
    row's evidence is the last reading on the side it is ARRIVING at, so the
    first crossing (nothing below 80 in this short history yet) is null,
    and the second and third each cite a different, older reading - never
    the reading immediately before them, which is on the wrong side."""
    points = [
        {"date": "2030-01-01", "kg": 81.0},
        {"date": "2030-01-02", "kg": 79.0},   # crosses 80 down - no prior data below 80
        {"date": "2030-01-03", "kg": 82.0},   # crosses 80 up - last above 80 was 01-01
        {"date": "2030-01-04", "kg": 78.0},   # crosses 80 down - last below 80 was 01-02
    ]
    got = [r for r in _rows("round_number", points) if r["value"] == 80.0]
    assert [r["direction"] for r in got] == ["down", "up", "down"]
    assert [(r["date"], r["previous_date"], r["previous_value"]) for r in got] == [
        ("2030-01-02", None, None),
        ("2030-01-03", "2030-01-01", 81.0),
        ("2030-01-04", "2030-01-02", 79.0),
    ]


def test_a_big_jump_crosses_every_rung_in_between():
    """One gap between weigh-ins can skip several rungs. Each is a fact about
    the series independent of whether the athlete was weighed in between, so
    each gets its own row - but here 91.0 is the FIRST reading in the whole
    record, so none of the three rungs (80, 85, 90) has ever been visited
    from below before now: every evidence pair is null, the "first time
    ever" case, not the 91.0 reading itself (which sits above all three
    rungs and so is on the wrong side to be evidence for any of them)."""
    points = [{"date": "2030-01-01", "kg": 91.0}, {"date": "2030-03-01", "kg": 78.0}]
    got = _rows("round_number", points)
    # Sorted by VALUE, ascending, like every other tie on (date, kind,
    # direction) - `compute_crossings` makes no claim about which rung was
    # crossed "first" within one gap, only that all three were.
    assert [r["value"] for r in got] == [80.0, 85.0, 90.0]
    assert all(r["previous_value"] is None and r["previous_date"] is None
              for r in got)


def test_a_big_jump_can_give_each_rung_its_own_evidence():
    """Unlike the case above, when the series HAS prior history, different
    rungs crossed in one jump can each cite a DIFFERENT last-on-that-side
    reading - the destination side is a property of each level, not of the
    jump as a whole."""
    points = [
        {"date": "2029-01-01", "kg": 79.0},   # below every rung that matters here
        {"date": "2029-04-01", "kg": 84.0},   # below 90 and 85's near side only
        {"date": "2029-07-01", "kg": 89.0},   # below 90 only
        {"date": "2030-01-01", "kg": 91.0},   # now above all three rungs
        {"date": "2030-03-01", "kg": 78.0},   # crosses 90, 85 and 80 downward
    ]
    got = [r for r in _rows("round_number", points) if r["date"] == "2030-03-01"]
    by_value = {r["value"]: (r["previous_date"], r["previous_value"]) for r in got}
    assert by_value == {
        80.0: ("2029-01-01", 79.0),
        85.0: ("2029-04-01", 84.0),
        90.0: ("2029-07-01", 89.0),
    }


def test_a_first_ever_crossing_has_a_null_evidence_pair_not_missing_data():
    """A consumer must be able to tell "the series has never been on that
    side" apart from "the data is missing" - and does so structurally, not
    by inspecting a value: `compute_crossings` never mints a partial row, so
    BOTH keys are always present (`"previous_value" in row`), and a null
    evidence pair is always the deliberate pair - both fields None together,
    from a row that otherwise carries a real `date` and `value` - never a
    KeyError or a half-filled row a caller could confuse with a data gap."""
    points = [{"date": "2030-01-01", "kg": 91.0}, {"date": "2030-01-02", "kg": 78.0}]
    got = _rows("round_number", points)
    assert got, "the fixture must mint something to test this"
    for row in got:
        assert "previous_value" in row and "previous_date" in row
        assert row["previous_value"] is None
        assert row["previous_date"] is None
        # The rest of the row is a real, fully-formed fact - the null pair
        # is the ONLY thing distinguishing "never" from an ordinary row.
        assert row["date"] == "2030-01-02"
        assert isinstance(row["value"], float)


def test_a_down_then_up_then_down_series_names_a_different_date_each_time():
    """Three crossings of the same level, each citing a DIFFERENT reading -
    proof the evidence is recomputed per crossing over the whole series
    rather than carried forward from the last one found.

    The very first transition (below-80 to above-80) is unavoidably a
    fourth crossing with NULL evidence - nothing precedes the first reading
    in a record, so that one cannot help being the "first time ever" case.
    It is kept in the fixture rather than engineered away, because it is
    what establishes the "above 80" anchor the later `up` crossing needs;
    the three DOWN-UP-DOWN crossings that follow it are the ones under
    test, and every one of them gets a distinct real evidence date."""
    points = [
        {"date": "2029-01-01", "kg": 70.0},   # first reading: below 80, mints nothing
        {"date": "2029-06-01", "kg": 90.0},   # crosses 80 up (null evidence - anchor only)
        {"date": "2030-01-01", "kg": 70.0},   # T1: down - last below was 2029-01-01
        {"date": "2030-06-01", "kg": 90.0},   # T2: up - last above was 2029-06-01
        {"date": "2031-01-01", "kg": 70.0},   # T3: down - last below was 2030-01-01
    ]
    got = [r for r in _rows("round_number", points) if r["value"] == 80.0]
    assert [(r["date"], r["direction"], r["previous_date"], r["previous_value"])
           for r in got] == [
        ("2029-06-01", "up", None, None),
        ("2030-01-01", "down", "2029-01-01", 70.0),
        ("2030-06-01", "up", "2029-06-01", 90.0),
        ("2031-01-01", "down", "2030-01-01", 70.0),
    ]
    targets = [r for r in got if r["date"] != "2029-06-01"]
    assert [r["direction"] for r in targets] == ["down", "up", "down"]
    # Three target crossings, three distinct evidence dates - never the
    # reading immediately before the crossing it backs.
    assert len({r["previous_date"] for r in targets}) == 3


def test_sitting_on_a_rung_then_moving_off_it_does_not_recross_it():
    """The previous reading landed exactly ON 80; leaving it downward is not a
    NEW crossing of 80, because the series was already past the boundary
    the moment it arrived there."""
    points = [{"date": "2030-01-01", "kg": 80.0}, {"date": "2030-01-05", "kg": 78.0}]
    assert _rows("round_number", points) == []


def test_the_ladder_is_five_and_documented_as_a_choice():
    assert ROUND_NUMBER_LADDER == 5.0


# --- personal_first --------------------------------------------------------------

def test_a_new_alltime_low_mints_a_personal_first():
    points = [
        {"date": "2030-01-01", "kg": 80.0},
        {"date": "2030-01-02", "kg": 85.0},   # new high, not a new low
        {"date": "2030-01-03", "kg": 77.0},   # new low
    ]
    got = _rows("personal_first", points)
    lows = [r for r in got if r["direction"] == "down"]
    assert lows == [{
        "date": "2030-01-03", "kind": "personal_first", "metric": "kg",
        "value": 77.0, "direction": "down",
        "previous_value": 80.0, "previous_date": "2030-01-01",
    }]


def test_a_new_alltime_high_mints_a_personal_first():
    points = [
        {"date": "2030-01-01", "kg": 80.0},
        {"date": "2030-01-02", "kg": 85.0},
    ]
    got = _rows("personal_first", points)
    assert got == [{
        "date": "2030-01-02", "kind": "personal_first", "metric": "kg",
        "value": 85.0, "direction": "up",
        "previous_value": 80.0, "previous_date": "2030-01-01",
    }]


def test_a_tie_does_not_beat_the_running_extreme():
    points = [{"date": "2030-01-01", "kg": 80.0}, {"date": "2030-01-02", "kg": 80.0}]
    assert _rows("personal_first", points) == []


def test_the_evidence_pair_is_the_record_holder_not_the_prior_reading():
    """A reading that neither crosses nor stays in the middle does not move
    either running extreme, so the NEXT crossing still cites the older row."""
    points = [
        {"date": "2030-01-01", "kg": 80.0},   # sets both extremes
        {"date": "2030-01-02", "kg": 78.0},   # new low
        {"date": "2030-01-03", "kg": 79.0},   # neither extreme moves
        {"date": "2030-01-04", "kg": 76.0},   # new low again
    ]
    got = [r for r in _rows("personal_first", points) if r["date"] == "2030-01-04"]
    assert got == [{
        "date": "2030-01-04", "kind": "personal_first", "metric": "kg",
        "value": 76.0, "direction": "down",
        "previous_value": 78.0, "previous_date": "2030-01-02",
    }]


def test_the_first_reading_in_a_record_mints_nothing():
    """It is trivially both the lowest and the highest reading ever seen,
    because it is the only one - a crossing here would have no
    `previous_value` to cite and would be announcing a series of one."""
    assert compute_crossings([{"date": "2030-01-01", "kg": 80.0}]) == []
    assert compute_crossings([]) == []


# --- band (#370's third kind) ---------------------------------------------------
#
# A height of 200 cm makes BMI = kg / 4 exactly, which is why most of these
# fixtures use it: it turns the arithmetic into something checkable by eye
# without pretending to be a plausible human height, the same liberty the
# round_number tests above take with weights that are never meant to look
# like a real person's.

def _height(on: str, cm: float) -> dict:
    return {"date": on, "kind": "height_cm", "value": cm}


def test_a_downward_band_crossing_has_the_right_evidence_pair():
    """125 kg / 200 cm = BMI 31.25; 115 kg / 200 cm = BMI 28.75 - crosses the
    30.0 edge downward, and two readings is not enough history to have ever
    been on the far side before, so the evidence pair is the null "first
    time ever" case, exactly as the round_number equivalent above."""
    weight = [{"date": "2030-01-01", "kg": 125.0}, {"date": "2030-01-05", "kg": 115.0}]
    height = [_height("2029-01-01", 200.0)]
    got = compute_band_crossings(weight, height)
    assert got == [{
        "date": "2030-01-05", "kind": "band", "metric": "bmi",
        "value": 30.0, "direction": "down",
        "previous_value": None, "previous_date": None,
    }]


def test_an_upward_band_crossing_has_the_right_evidence_pair():
    """Same shape, upward: 115 kg (BMI 28.75) to 125 kg (BMI 31.25)."""
    weight = [{"date": "2030-01-01", "kg": 115.0}, {"date": "2030-01-05", "kg": 125.0}]
    height = [_height("2029-01-01", 200.0)]
    got = compute_band_crossings(weight, height)
    assert got == [{
        "date": "2030-01-05", "kind": "band", "metric": "bmi",
        "value": 30.0, "direction": "up",
        "previous_value": None, "previous_date": None,
    }]


def test_a_big_jump_crosses_every_nonuniform_level_in_between():
    """`BAND_LEVELS` (18.5, 25.0, 30.0) is NOT a uniform ladder, unlike
    `ROUND_NUMBER_LADDER` - this is the one behaviour that genuinely needs
    its own arithmetic (`_band_levels_crossed`) rather than reusing
    `_levels_crossed`. At 200 cm the three edges sit at 74, 100 and 120 kg;
    one gap from 130 kg (BMI 32.5) down to 70 kg (BMI 17.5) crosses all
    three, and - the series' opening move - none of them has been reached
    from below before, so every evidence pair is null."""
    weight = [{"date": "2030-01-01", "kg": 130.0}, {"date": "2030-03-01", "kg": 70.0}]
    height = [_height("2029-01-01", 200.0)]
    got = compute_band_crossings(weight, height)
    assert [r["value"] for r in got] == [18.5, 25.0, 30.0]
    assert all(r["direction"] == "down" for r in got)
    assert all(r["previous_value"] is None and r["previous_date"] is None
              for r in got)


def test_a_band_recrossing_mints_a_second_row_with_its_own_evidence():
    """The same real behaviour yasmin's corpus exercises (FINDINGS.md #7):
    under a boundary, back over, under again - three crossings, not one."""
    weight = [
        {"date": "2030-01-01", "kg": 124.0},   # BMI 31.0
        {"date": "2030-01-02", "kg": 116.0},   # BMI 29.0 - crosses down
        {"date": "2030-01-03", "kg": 128.0},   # BMI 32.0 - crosses up
        {"date": "2030-01-04", "kg": 112.0},   # BMI 28.0 - crosses down
    ]
    height = [_height("2029-01-01", 200.0)]
    got = [r for r in compute_band_crossings(weight, height) if r["value"] == 30.0]
    assert [r["direction"] for r in got] == ["down", "up", "down"]
    assert [(r["date"], r["previous_date"], r["previous_value"]) for r in got] == [
        ("2030-01-02", None, None),
        ("2030-01-03", "2030-01-01", 31.0),
        ("2030-01-04", "2030-01-02", 29.0),
    ]


def test_a_weight_reading_with_no_height_yet_in_force_mints_nothing():
    """THE STRADDLE (#370's own design constraint): two weight readings
    before the first height row exist have no ratio at all and are simply
    absent from the series - never a ratio back-filled from the height that
    arrives later. Only once the height exists does the ratio series start,
    so the first ratio point AFTER it (125 kg / 200 cm = BMI 31.25) is the
    series' effective opening move and mints nothing itself; the crossing
    below it is the first one with anything to compute at all."""
    weight = [
        {"date": "2029-01-01", "kg": 90.0},    # before any height: invisible
        {"date": "2029-03-01", "kg": 130.0},   # before any height: invisible
        {"date": "2029-07-01", "kg": 125.0},   # BMI 31.25 - first computable point
        {"date": "2029-09-01", "kg": 110.0},   # BMI 27.5 - crosses 30 down
    ]
    height = [_height("2029-06-01", 200.0)]
    got = compute_band_crossings(weight, height)
    assert got == [{
        "date": "2029-09-01", "kind": "band", "metric": "bmi",
        "value": 30.0, "direction": "down",
        "previous_value": None, "previous_date": None,
    }]


def test_a_height_change_mid_series_uses_the_height_in_force_on_each_date():
    """THE HEIGHT MUST BE EFFECTIVE-DATED (#148's lesson, restated for
    #370): a ratio computed for a date must use the height that was in
    force ON THAT DATE, never the newest height the record happens to hold.

    Two readings before the height change (200 cm) cross 30 upward
    (116 kg = BMI 29.0 -> 124 kg = BMI 31.0). The height then changes to
    180 cm. Two readings after it: 110 kg is BMI 33.95 under the NEW height
    (still above 30, no crossing) and 90 kg is BMI 27.78 under the NEW
    height (below 30 - crosses down). Get either of those two BACKWARDS -
    using 200 cm after the change - and 110 kg reads as BMI 27.5, which
    would already be below 30 and change which pair of readings crosses at
    all. The evidence pair for the second crossing still reaches back
    correctly across the height change, to the 116 kg / 200 cm reading that
    was the last one on the "below 30" side, computed under the height that
    applied on ITS OWN date."""
    weight = [
        {"date": "2029-07-01", "kg": 116.0},    # BMI 29.0 (200 cm)
        {"date": "2029-08-01", "kg": 124.0},    # BMI 31.0 (200 cm) - crosses up
        {"date": "2030-02-01", "kg": 110.0},    # BMI 33.95 (180 cm) - stays above
        {"date": "2030-03-01", "kg": 90.0},     # BMI 27.78 (180 cm) - crosses down
    ]
    height = [_height("2029-01-01", 200.0), _height("2030-01-01", 180.0)]
    got = [r for r in compute_band_crossings(weight, height) if r["value"] == 30.0]
    assert got == [
        {"date": "2029-08-01", "kind": "band", "metric": "bmi",
         "value": 30.0, "direction": "up",
         "previous_value": None, "previous_date": None},
        {"date": "2030-03-01", "kind": "band", "metric": "bmi",
         "value": 30.0, "direction": "down",
         "previous_value": 29.0, "previous_date": "2029-07-01"},
    ]


def test_no_height_at_all_mints_nothing():
    """A weight series alone is not a ratio series - `round_number` and
    `personal_first` need no height and still fire on this same data
    (`compute_crossings`, exercised elsewhere in this file); `band` needs
    one and, with none recorded, mints nothing rather than assuming a
    default stature."""
    weight = [{"date": "2030-01-01", "kg": 125.0}, {"date": "2030-01-05", "kg": 115.0}]
    assert compute_band_crossings(weight, []) == []


def test_the_ladder_is_adopted_not_a_round_number():
    """`BAND_LEVELS` is a fixed, cited set of population-reference edges
    (see the sourced comment beside the constant), not a derivation from
    `ROUND_NUMBER_LADDER` or from anything about the metric - a different
    shape of constant for a different kind of boundary."""
    assert BAND_LEVELS == (18.5, 25.0, 30.0)
    assert "band" in CROSSING_KINDS


def test_weight_metric_and_ratio_metric_are_both_parameters():
    """Neither `weight_metric` nor `metric` is hardcoded - the same proof
    `test_metric_is_a_parameter_not_hardcoded` gives for `compute_crossings`,
    over a differently-named weight field and a differently-named ratio."""
    weight = [{"date": "2030-01-01", "w": 125.0}, {"date": "2030-01-05", "w": 115.0}]
    height = [_height("2029-01-01", 200.0)]
    got = compute_band_crossings(weight, height, weight_metric="w", metric="ratio")
    assert got and all(r["metric"] == "ratio" for r in got)
    assert got[0]["value"] == 30.0


def test_band_rows_never_carry_a_string_value():
    """THE RULE THIS TABLE SHIPS UNDER: the engine may compute the ratio and
    state the boundary as a boundary, and may never name the band. Checked
    here at the level furthest from any renderer's wording - a `band` row's
    `value` is always a number, never a string, so the violation this issue
    is about is structurally unrepresentable in the row itself, whatever a
    consumer later chooses to print beside it."""
    weight = [{"date": "2030-01-01", "kg": 130.0}, {"date": "2030-03-01", "kg": 70.0}]
    height = [_height("2029-01-01", 200.0)]
    got = compute_band_crossings(weight, height)
    assert got, "the fixture above must actually mint something to test this"
    for row in got:
        assert isinstance(row["value"], float)
        assert isinstance(row["kind"], str) and row["kind"] == "band"


# --- the vocabulary and the column register -------------------------------------

def test_every_minted_row_uses_the_closed_vocabulary():
    """`round_number`'s first crossing (91.0 -> 79.0, the series' opening
    descent) has no history below any of the three rungs it passes, so its
    rows carry a null evidence pair - the "first time ever" case - while
    the later `round_number` rows and every `personal_first` row have real
    evidence. Both are legal; what is never legal is a HALF pair."""
    points = [
        {"date": "2030-01-01", "kg": 91.0}, {"date": "2030-01-02", "kg": 79.0},
        {"date": "2030-01-03", "kg": 82.0}, {"date": "2030-01-04", "kg": 78.0},
    ]
    got = compute_crossings(points)
    assert got, "the fixture above must actually mint something to test this"
    saw_null_pair = saw_real_pair = False
    for row in got:
        assert set(row) == set(CROSSING_KEYS)
        assert row["kind"] in CROSSING_KINDS
        assert row["direction"] in CROSSING_DIRECTIONS
        assert row["metric"] == "kg"
        # THE EVIDENCE PAIR IS NEVER HALF-ABSENT: `previous_value` and
        # `previous_date` are null together or present together. A row with
        # one but not the other would be neither a citable fact nor an
        # honest "never" - it would be ambiguous with missing data, which
        # this module's contract never produces (see `crossings.py`'s
        # `_last_on_destination_side`).
        assert (row["previous_value"] is None) == (row["previous_date"] is None)
        if row["previous_value"] is None:
            saw_null_pair = True
        else:
            saw_real_pair = True
    assert saw_null_pair and saw_real_pair, (
        "the fixture above must exercise both the null-pair (first time "
        "ever) and real-pair cases to test this")


def test_metric_is_a_parameter_not_hardcoded():
    """The same walk, over a differently-named field - proof the arithmetic
    does not know it is weight. `kg` is present and irrelevant on both rows,
    which `compute_crossings` must ignore when asked about a different one."""
    points = [{"date": "2030-01-01", "kg": 999, "waist_cm": 91.0},
              {"date": "2030-01-02", "kg": 999, "waist_cm": 79.0}]
    got = compute_crossings(points, metric="waist_cm")
    assert got and all(r["metric"] == "waist_cm" for r in got)
    assert [r["value"] for r in got if r["kind"] == "round_number"] == [80.0, 85.0, 90.0]


# --- the engine: canonical resolution, empty records, the three surfaces --------

def test_a_record_with_no_weight_mints_nothing(tmp_path):
    root = init(tmp_path / "content")
    assert Vitai(root).crossings() == []


def test_a_single_weight_reading_mints_nothing(tmp_path):
    """The engine-level echo of the first-reading decision above."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("weight", {"date": "2030-01-01", "kg": 80.0, "source": "scale"})
    assert v.crossings() == []


def test_the_canonical_series_is_used_rather_than_raw_rows(tmp_path):
    """Two sources disagreeing on one day must resolve to ONE canonical
    reading before crossings ever sees the day - `resolution.resolve()`
    adjudicates it, same as every other weight consumer.

    THE STRADDLE, CHOSEN AND VERIFIED RATHER THAN ASSUMED: day 2's two raw
    claims (79.0 and 81.0) sit on OPPOSITE sides of the 80 kg rung, so if
    `compute_crossings` ever saw both as separate points it would walk
    82 -> 79 -> 81 -> ... and mint TWO round-number crossings dated
    2030-01-02, one down and one back up - an artifact of one day carrying
    two numbers, not a fact about the athlete's weight moving twice in a
    day. Checked directly against `compute_crossings` on the raw shape
    before this test was written, so this is not a claim taken on faith:
    unresolved, this fixture mints exactly 2; resolved, at most 1, because a
    single canonical value for day 2 has only one relationship to 82.0.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("weight", {"date": "2030-01-01", "kg": 82.0, "source": "scale"})
    v.append("weight", {"date": "2030-01-02", "kg": 79.0, "source": "scale-a"})
    v.append("weight", {"date": "2030-01-02", "kg": 81.0, "source": "scale-b"})
    v.append("weight", {"date": "2030-01-03", "kg": 76.0, "source": "scale"})

    canonical_day2 = [r for r in v.canonical("weight") if r["date"] == "2030-01-02"]
    assert len(canonical_day2) == 1, (
        "resolution must merge same-day claims into one canonical row "
        "before crossings ever walks the series")

    on_day2 = [r for r in v.crossings()
              if r["date"] == "2030-01-02" and r["kind"] == "round_number"]
    assert len(on_day2) <= 1, (
        f"raw rows would have let day2's two conflicting claims - one either "
        f"side of 80 kg - register as two round-number crossings instead of "
        f"the one (or zero) the athlete's canonical record actually holds: "
        f"{on_day2}")


def test_it_reaches_the_derived_table_and_a_build(tmp_path):
    """Only two readings ever recorded, so there is no history below 80 to
    cite - the round-number row's evidence pair is the "first time ever"
    null, and the point of this test is that a null survives the round trip
    through SQLite as NULL, with every other column still intact."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("weight", {"date": "2030-01-01", "kg": 81.2, "source": "scale"})
    v.append("weight", {"date": "2030-01-05", "kg": 79.6, "source": "scale"})

    assert v.crossings() == v.derived("crossings")
    v.build()
    import sqlite3
    con = sqlite3.connect(root / "derived" / "health.db")
    stored = con.execute(
        "SELECT date, kind, metric, value, direction, previous_value, "
        "previous_date FROM crossings WHERE kind='round_number'").fetchall()
    con.close()
    # The second reading is ALSO a personal-first low (79.6 is the lowest of
    # two readings), which this query filters out - proved separately above
    # and not this test's concern, which is that the round-number row made it
    # through `build_db` with every column intact.
    assert stored == [("2030-01-05", "round_number", "kg", 80.0, "down", None,
                       None)]


def test_the_three_surfaces_agree(tmp_path):
    """P9: an agent, a script and a library caller get one answer."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for d, kg in (("2030-01-01", 81.2), ("2030-01-05", 79.6), ("2030-02-01", 84.0)):
        v.append("weight", {"date": d, "kg": kg, "source": "scale"})

    from_api = v.crossings()
    assert from_api, "the fixture above must actually mint something to test this"

    from_mcp = mcp.call(root, "crossings", {})

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "crossings", "--root", str(root),
         "--json"], capture_output=True, text=True, check=True)
    from_cli = [json.loads(line) for line in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli


# --- band, through the engine (P9: CLI and API in the same PR) ------------------

def test_a_band_crossing_reaches_the_engine_through_a_real_height_row(tmp_path):
    """`Vitai.crossings()` must combine weight-only crossings with the band
    kind, which needs `measurements` too - the engine-level echo of
    `compute_band_crossings`'s own unit tests above, through
    `Vitai.append`/`Vitai.canonical` rather than hand-built points."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("measurements", {"date": "2029-01-01", "kind": "height_cm",
                              "value": 200.0, "source": "self_report"})
    v.append("weight", {"date": "2030-01-01", "kg": 125.0, "source": "scale"})
    v.append("weight", {"date": "2030-01-05", "kg": 115.0, "source": "scale"})

    got = [r for r in v.crossings() if r["kind"] == "band"]
    assert got == [{
        "date": "2030-01-05", "kind": "band", "metric": "bmi",
        "value": 30.0, "direction": "down",
        "previous_value": None, "previous_date": None,
    }]


def test_a_weight_reading_before_any_height_reaches_the_engine_with_no_ratio(tmp_path):
    """The straddle, through `Vitai` rather than through hand-built points:
    a weight logged before any height row exists must not retroactively
    gain a ratio once a height is appended later - append order here mirrors
    an athlete who has been weighing in for a while and only later tells the
    engine their height."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("weight", {"date": "2029-07-01", "kg": 125.0, "source": "scale"})
    assert v.crossings() == []  # one reading, no height: nothing to mint yet

    v.append("measurements", {"date": "2029-06-01", "kind": "height_cm",
                              "value": 200.0, "source": "self_report"})
    v.append("weight", {"date": "2029-09-01", "kg": 110.0, "source": "scale"})
    got = [r for r in v.crossings() if r["kind"] == "band"]
    assert got == [{
        "date": "2029-09-01", "kind": "band", "metric": "bmi",
        "value": 30.0, "direction": "down",
        "previous_value": None, "previous_date": None,
    }]


def test_the_three_surfaces_agree_on_a_band_crossing_too(tmp_path):
    """P9, restated for the kind that needed a second dataset to compute:
    agent, script and library still get one answer once a height row is in
    the record."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("measurements", {"date": "2029-01-01", "kind": "height_cm",
                              "value": 200.0, "source": "self_report"})
    for d, kg in (("2030-01-01", 125.0), ("2030-01-05", 115.0)):
        v.append("weight", {"date": d, "kg": kg, "source": "scale"})

    from_api = v.crossings()
    assert any(r["kind"] == "band" for r in from_api), (
        "the fixture above must actually mint a band row to test this")

    from_mcp = mcp.call(root, "crossings", {})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "crossings", "--root", str(root),
         "--json"], capture_output=True, text=True, check=True)
    from_cli = [json.loads(line) for line in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli


def test_the_cli_states_the_boundary_and_never_a_name_for_it(tmp_path):
    """The class (a) sentence the ruling permits, reusing `round_number`'s
    template exactly (see `cli.py`'s `cmd_crossings`): a bound stated as a
    bound - "bmi below 30", "first bmi below 30 since <date>" - and nothing
    beside `bmi` and the figures that could ever spell a category word.

    Two readings only, so this is the null-evidence "first time in this
    record" sentence; the "since <date>" form is the same template `test_
    the_cli_says_since_rather_than_leaving_it_to_be_reconstructed` above
    already pins for `round_number`, and `band` shares that branch verbatim
    (see `cli.py`) rather than a second copy of it.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("measurements", {"date": "2029-01-01", "kind": "height_cm",
                              "value": 200.0, "source": "self_report"})
    v.append("weight", {"date": "2030-01-01", "kg": 125.0, "source": "scale"})
    v.append("weight", {"date": "2030-01-05", "kg": 115.0, "source": "scale"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "crossings", "--root", str(root)],
        capture_output=True, text=True, check=True).stdout

    assert "bmi below 30 for the first time in this record" in out, out


def test_the_cli_says_since_rather_than_leaving_it_to_be_reconstructed(tmp_path):
    """THE SENTENCE IS THE FEATURE. The issue's argument is that "lowest ever"
    and "first in over a year" were both false and "first below 80 since
    February" was true, so the prose surface has to be able to say the last
    one.

    The first version printed both kinds through one template, "(was X on
    DATE)". On a personal first that reads correctly - X is the record beaten.
    On a round number it reads as the OPPOSITE of the fact: "down to 80 (was
    75)" looks like a five-kilo gain, when 75 is the last reading BELOW 80 and
    the point is that the athlete is under 80 for the first time since then.

    Nothing pinned the prose, so the suite stayed green through the fix. This
    is that pin."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for d, kg in (("2029-01-01", 75.0), ("2029-02-01", 82.0),
                  ("2029-08-01", 79.0)):
        v.append("weight", {"date": d, "kg": kg, "source": "scale"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "crossings", "--root", str(root)],
        capture_output=True, text=True, check=True).stdout

    assert "first kg below 80 since 2029-01-01" in out, out
    # And the reading that was beaten is NOT presented as the prior weigh-in.
    assert "was 82" not in out
    # A first-ever crossing says so rather than naming a date it does not have.
    assert "for the first time in this record" in out, out


def test_the_cli_reports_no_crossings_rather_than_nothing(tmp_path):
    root = init(tmp_path / "content")
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "crossings", "--root", str(root)],
        capture_output=True, text=True, check=True)
    assert "no crossings" in out.stdout


def test_the_mcp_tool_is_pinned_in_the_protocol_register():
    """The register `test_it_speaks_the_protocol` in test_vitai.py holds this
    name; asserted here too so a rename shows up beside the tool itself."""
    assert "crossings" in mcp.TOOLS
    assert mcp.TOOLS["crossings"]["method"] == "crossings"


# --- the control that matters most -----------------------------------------------
#
# "The engine may compute the ratio and state the boundary as a boundary. It
# may never name the band." (the operator, decided on #370.) Everything above
# this line checks that the NUMBERS are right; this checks that the RULE
# holds, against real rendered text rather than against the row shape.
#
# TWO CHOICES HERE ARE LOAD-BEARING, both because this repo has hit variants
# of this exact defect five times before (per the task that asked for this
# control):
#
# 1. AN INDEPENDENT WORD LIST. `_CATEGORY_WORDS` below is authored fresh for
#    this file rather than imported from `scripts/boundary_gate.py`'s
#    `CATEGORY_WORDS`/`CATEGORY_WORDS_GENERIC`. Importing that list and
#    reusing it here would mean this control and the boundary gate share
#    exactly one blind spot: a word neither list's author thought of passes
#    both, and a bug in the gate's list silently becomes a bug in this test
#    too. This list is also DELIBERATELY BROADER than the gate's - it
#    includes "obesity" and "normal weight", which `boundary_gate.py`'s own
#    comments explain it leaves out on purpose (false positives elsewhere on
#    the public surface that do not apply to a `crossings` sentence) - so
#    a shared blind spot is structurally unlikely even by accident.
#
# 2. THE ACTUAL RENDERED OUTPUT, not the row or the template source. This
#    runs the real `vitai crossings` CLI (text AND `--json`) as a subprocess
#    against every persona in the committed corpus and greps the words
#    against what actually printed - the same distinction #379's own finding
#    drew between a lint over `cli.py`'s SOURCE (which has no category word
#    literal anywhere in it to catch) and a check over what that source
#    PRODUCES once real numbers pass through its f-strings.
_CATEGORY_WORDS = (
    "underweight", "overweight", "obese", "obesity",
    "healthy weight", "healthy range", "normal weight", "normal range",
    "ideal weight", "hypertensive", "hypertension", "prehypertension",
)
_CATEGORY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _CATEGORY_WORDS) + r")\b",
    re.I)


def _persona_dirs() -> list[Path]:
    return sorted(d for d in PERSONAS.iterdir()
                 if d.is_dir() and d.name != "_gen" and (d / "data").is_dir())


def _rendered_crossings_output(root: Path) -> str:
    """Every byte `vitai crossings` would print for this record, text and
    JSON both concatenated - the two shapes a real consumer actually reads."""
    out = ""
    for extra in ([], ["--json"]):
        proc = subprocess.run(
            [sys.executable, "-m", "vitai.cli", "crossings",
             "--root", str(root), *extra],
            capture_output=True, text=True, check=True)
        out += proc.stdout
    return out


def test_no_band_row_is_ever_rendered_with_a_category_word():
    """Renders `vitai crossings` for every persona in the committed corpus -
    not a synthetic fixture built to pass - and fails if a category word
    appears anywhere in the combined output.

    A SYNTHETIC FIXTURE WOULD BE BUILT FROM THE SAME ASSUMPTIONS THE
    RENDERER WAS, which is exactly the blind spot #370's own review of
    `scripts/boundary_gate.py` names: a control built from the material it
    polices can pass by construction rather than by having checked anything.
    The persona corpus is real, independently-authored data (`yasmin`'s band
    crossings measured against her actual weight series, not invented to
    exercise this test) - if a category word were EVER going to leak out of
    `cmd_crossings`'s f-strings for some combination of `metric`/`direction`/
    `previous_date` this repo's own corpus has not anticipated, running it
    against thirteen different real records is a better chance of finding it
    than one hand-built case.
    """
    rendered = "\n".join(_rendered_crossings_output(d) for d in _persona_dirs())
    assert rendered.strip(), "the corpus must render SOMETHING to test this"

    hit = _CATEGORY_RE.search(rendered)
    assert hit is None, (
        f"a category word ({hit.group()!r}) appeared in rendered `vitai "
        f"crossings` output - the ruling this table exists under is that "
        f"the engine may state a boundary but never name it")


def test_the_corpus_this_control_scans_actually_exercises_a_band_row():
    """Guards the guard: if no persona's rendered output ever carried a
    `band` row, the test above would pass by having nothing to say rather
    than by having checked the rule. `yasmin`'s corpus (FINDINGS.md #7)
    exists to make this assertion true."""
    rendered = "\n".join(
        _rendered_crossings_output(d) for d in _persona_dirs())
    assert "band" in rendered, (
        "no persona in the corpus rendered a `band` crossing - the category-"
        "word scan above would be vacuous")
