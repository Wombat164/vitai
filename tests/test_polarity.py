"""Which direction counts as progress (#200).

`monotonic` and `guarded` both mean "more counts", so before this a cap was
scored as an accumulation and exceeding it read as excelling: 1100 kcal a day
against a 1200 limit reported 641.7% for the week and minted four celebratory
milestones for breaching it.

Polarity is a separate axis from `policy`, which says whether progress may run
backwards, and from the teleology axis, which says what KIND of thing a goal
is. Three questions, three fields.
"""

from __future__ import annotations

import json
import sqlite3


from vitai.api import Vitai, init
from vitai.schema import (CURRENT_GENERATION, DEFAULT_POLARITY,
                          GOAL_POLARITIES, KEYS, polarity_of, validate_record)

GOAL = {"date": "2030-06-01", "slug": "cap", "title": "Cap intake at 1200",
        "metric": "kcal_in", "dataset": "daily", "target": 1200,
        "policy": "monotonic", "period": "none", "status": "active",
        "tracker": "sum"}


def a_goal(**kw):
    """A goal line. Filled from `KEYS` so a later generation block does not
    have to edit this file to keep it validating."""
    g = {k: None for k in KEYS["goals"]}
    g.update(GOAL)
    g["_gen"] = CURRENT_GENERATION["goals"]
    g.update(kw)
    return g


_made = [0]


def scored(tmp_path, goal, kcal=1100, days=7):
    # A fresh directory per call: `init` refuses a non-empty one, and several
    # tests here score the same data under different polarities.
    _made[0] += 1
    root = init(tmp_path / f"content{_made[0]}")
    (root / "data" / "goals.jsonl").write_text(
        json.dumps(goal) + "\n", encoding="utf-8")
    def a_day(d):
        row = {k: None for k in KEYS["daily"]}
        row.update({"date": f"2030-06-{d:02d}", "kcal_in": kcal,
                    "source": "app", "_gen": CURRENT_GENERATION["daily"]})
        return row
    (root / "data" / "daily.jsonl").write_text("\n".join(
        json.dumps(a_day(d)) for d in range(1, days + 1)) + "\n",
        encoding="utf-8")
    return root, Vitai(root, on="2030-06-07").goals()[0]


# --- the migration promise ---------------------------------------------------

def test_an_undeclared_polarity_is_a_floor():
    """Both existing policies already meant "more counts", so this is what
    lets every row in the wild keep the answer it had."""
    assert polarity_of({}) == DEFAULT_POLARITY == "floor"
    assert polarity_of({"polarity": "ceiling"}) == "ceiling"


def test_an_existing_row_scores_exactly_as_before(tmp_path):
    """The 641.7% is preserved, deliberately. Nothing re-scores on upgrade:
    the row is not wrong, it is UNDECLARED, and changing its answer without
    the athlete saying anything would be the engine editing a goal."""
    _, row = scored(tmp_path, a_goal())
    assert row["progress_pct"] == 641.7
    assert row["milestones"] == 4
    assert row["polarity"] == "floor"


# --- what a ceiling does instead ---------------------------------------------

def test_the_motivating_case_scores_correctly_when_declared(tmp_path):
    """THE CASE THE ISSUE WAS FILED ABOUT: 1100 kcal a day against a 1200 cap.

    It read 641.7% and minted four milestones. Declared as what it is - a
    per-day ceiling - it now reports the hundred calories of room left and no
    breach at all. Getting the polarity right without a daily bucket would
    have turned a compliant week into a 6500 breach, which is the same error
    facing the other way, so `daily` ships with this.
    """
    _, row = scored(tmp_path, a_goal(polarity="ceiling", period="daily"))
    assert row["progress_pct"] is None
    assert row["counted"] == 1100
    assert row["room_left"] == 100
    assert row["breach"] is None
    assert row["milestones"] == 0


def test_a_ceiling_over_its_limit_reports_how_far(tmp_path):
    """641% must be UNREACHABLE rather than bounded: nothing divides by a
    limit any more, so the figure that read as success cannot be produced."""
    _, row = scored(tmp_path, a_goal(polarity="ceiling", period="daily",
                                     target=1000))
    assert row["progress_pct"] is None
    assert row["room_left"] == -100
    assert row["breach"] == "over"


def test_a_running_total_capped_forever_is_pointed_at(tmp_path):
    """A cap on a total that never resets pushes further over with every
    logged day. Legitimate for a monthly alcohol budget, almost never what
    someone means by a calorie cap, so it is advised rather than refused."""
    root, row = scored(tmp_path, a_goal(polarity="ceiling"))
    assert row["room_left"] == 1200 - 7700        # arithmetically right
    found = [a for a in Vitai(root).validate()["advisories"]
             if "never resets" in a]
    assert len(found) == 1 and "period to 'daily'" in found[0]


def test_a_ceiling_mints_no_milestones(tmp_path):
    """A quarter of the way to a cap is not an achievement, and minting it was
    the celebratory half of the defect."""
    _, row = scored(tmp_path, a_goal(polarity="ceiling", period="daily"))
    assert row["milestones"] == 0


def test_an_achieved_goal_is_not_nagged_about(tmp_path):
    """An achieved or abandoned goal is never scored, so the hazard the
    advisory describes does not exist for it."""
    root, _ = scored(tmp_path, a_goal(status="achieved"))
    assert not [a for a in Vitai(root).validate()["advisories"]
                if "polarity" in a]


# --- bands and approaches ----------------------------------------------------

def test_a_band_says_which_side_it_fell_off(tmp_path):
    """Under and over are different failures with different remedies, and one
    word for both would be the overloading this engine keeps removing."""
    _, low = scored(tmp_path, a_goal(polarity="band", target=8000,
                                     target_hi=9000))
    assert low["breach"] == "under"
    _, high = scored(tmp_path, a_goal(polarity="band", target=1000,
                                      target_hi=2000))
    assert high["breach"] == "over"
    _, inside = scored(tmp_path, a_goal(polarity="band", target=7000,
                                        target_hi=8000))
    assert inside["breach"] is None and inside["progress_pct"] is None


def test_an_approach_measures_distance_and_ignores_the_sign(tmp_path):
    """On a cut less is progress, on a bulk more is, and at maintenance either
    direction is the miss. One metric, three readings, and the only thing
    common to them is how far off the value sits."""
    _, over = scored(tmp_path, a_goal(polarity="approach", target=7000))
    _, under = scored(tmp_path, a_goal(polarity="approach", target=8400))
    assert over["distance"] == 700.0 and under["distance"] == 700.0
    assert over["progress_pct"] is None and over["breach"] is None
    assert over["milestones"] == 0


# --- the schema will not accept a half-declared band -------------------------

def test_a_band_needs_both_bounds():
    problems = validate_record("goals", a_goal(polarity="band"))
    assert problems and "both bounds" in problems[0]


def test_a_band_runs_upward():
    assert validate_record("goals", a_goal(polarity="band", target=2000,
                                           target_hi=1000))
    assert validate_record("goals", a_goal(polarity="band", target=1000,
                                           target_hi=2000)) == []


def test_only_a_band_carries_a_second_bound():
    """Written and never read is the same defect as specified and never
    written, arriving from the other direction."""
    problems = validate_record("goals", a_goal(polarity="ceiling",
                                               target_hi=1500))
    assert problems and "upper bound of a BAND" in problems[0]


def test_the_polarity_vocabulary_is_closed():
    assert validate_record("goals", a_goal(polarity="sideways"))
    for p in GOAL_POLARITIES:
        extra = {"target_hi": 2000} if p == "band" else {}
        assert validate_record("goals", a_goal(polarity=p, target=1000,
                                               **extra)) == []


# --- the advisory that stops the hunt-by-hand --------------------------------

def test_a_cap_scored_as_a_floor_is_pointed_at(tmp_path):
    """The issue's own remedy was that such rows are "identifiable by hand".
    Hunting them by hand is the part that does not survive a growing record."""
    root, _ = scored(tmp_path, a_goal())
    found = [a for a in Vitai(root).validate()["advisories"] if "polarity" in a]
    assert len(found) == 1 and "reads like a cap" in found[0]


def test_a_declared_goal_is_not_nagged_about(tmp_path):
    root, _ = scored(tmp_path, a_goal(polarity="ceiling"))
    assert not [a for a in Vitai(root).validate()["advisories"]
                if "polarity" in a]


def test_the_advisory_never_fails_a_build(tmp_path):
    """A title is prose and prose is not a declaration. "Cap the ramp at 10
    percent" may well be a floor on volume with a separate guard, and refusing
    it would make the engine the author of a goal it only read the label of."""
    root, _ = scored(tmp_path, a_goal())
    report = Vitai(root).validate()
    assert report["ok"] and not report["problems"]


# --- and it reaches the read model -------------------------------------------

def test_the_polarity_columns_reach_the_read_model(tmp_path):
    root, _ = scored(tmp_path, a_goal(polarity="ceiling"))
    Vitai(root, on="2030-06-07").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(goal_progress)")]
        row = con.execute("SELECT polarity, room_left, breach, progress_pct "
                          "FROM goal_progress WHERE slug='cap'").fetchone()
    finally:
        con.close()
    for name in ("polarity", "target_hi", "room_left", "distance", "breach"):
        assert name in cols
    assert row == ("ceiling", float(1200 - 7700), "over", None)
