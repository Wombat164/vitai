"""Round-number and personal-first milestones, goal-independent and
history-wide (#370).

`milestones` needs a declared goal and a scoring bucket; these two kinds do
not, which is why they are a new table (`crossings.py`, `db.CROSSING_KEYS`)
rather than a new row shape in that one. See `crossings.py`'s module
docstring for the full design, and `db.py` beside contract 47 for the
column-by-column reasoning - this file holds it to the letter.

Most cases are checked against `compute_crossings` directly, over synthetic
point lists, because the interesting behaviour is in the walk across
consecutive readings and a bare list of `{"date", "kg"}` dicts is the whole
input that logic needs. The handful of cases that are about the ENGINE rather
than the arithmetic - canonical resolution, an empty record, the three
surfaces agreeing - go through a real `Vitai` instance instead.
"""

from __future__ import annotations

import json
import subprocess
import sys

from vitai import mcp
from vitai.api import Vitai, init
from vitai.crossings import (CROSSING_DIRECTIONS, CROSSING_KINDS,
                             ROUND_NUMBER_LADDER, compute_crossings)
from vitai.db import CROSSING_KEYS


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
