"""Goal status is two axes, not one (#235).

`{proposed, active, paused, achieved, abandoned}` mixed where a goal is in its
own LIFE with how it is going against its TARGET. That mixture is #199's
two-scoring-systems bug at the vocabulary level: `goals` held the lifecycle
axis, `verdicts` held the achievement axis, they were built by different code,
and the shipped demo had them disagreeing about steps.

`achieved` was the tell - an achievement value living in a lifecycle list.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai, init
from vitai.contributions import achievement_of
from vitai.policy import lifecycle_of
from vitai.schema import (ACHIEVEMENT_STATUSES, CURRENT_GENERATION,
                          GOAL_STATUSES, KEYS, LIFECYCLE_STATUSES,
                          validate_record)

_made = [0]


def a_goal(**kw):
    g = {k: None for k in KEYS["goals"]}
    g.update({"date": "2030-06-01", "slug": "steps", "title": "Walk daily",
              "metric": "steps", "dataset": "daily", "target": 60000,
              "policy": "monotonic", "period": "weekly", "tracker": "sum",
              "lifecycle_status": "active",
              "_gen": CURRENT_GENERATION["goals"]})
    g.update(kw)
    return g


# --- two vocabularies, and no word in both -----------------------------------

def test_the_axes_do_not_share_a_word():
    """A value in both lists would put the mixture back one level down."""
    assert not (LIFECYCLE_STATUSES & ACHIEVEMENT_STATUSES)


def test_every_achievement_value_has_something_that_emits_it():
    """A closed vocabulary carrying words nothing can produce is the
    specified-and-never-written class arriving in the vocabulary that was
    meant to fix a different defect. FHIR's `improving`, `worsening` and
    `no_change` are deliberately absent until their producers exist."""
    emitted = set()
    for lifecycle in LIFECYCLE_STATUSES:
        for counted, target, days in ((0, 100, None), (50, 100, None),
                                      (100, 100, None), (50, 100, -1)):
            got = achievement_of(counted, target, lifecycle, days)
            if got:
                emitted.add(got)
    assert emitted == ACHIEVEMENT_STATUSES


# --- the retirement, all three parts of G89 ----------------------------------

def test_an_old_line_still_validates():
    """A goal written before the split is not wrong, it is old."""
    old = a_goal(lifecycle_status=None, status="active", _gen=4)
    assert validate_record("goals", old) == []


def test_a_new_line_needs_a_lifecycle():
    problems = validate_record("goals", a_goal(lifecycle_status=None))
    assert any("needs a lifecycle" in p for p in problems), problems


def test_the_retired_vocabulary_is_still_accepted_on_the_old_field():
    for value in GOAL_STATUSES:
        assert validate_record("goals", a_goal(lifecycle_status=None,
                                               status=value, _gen=4)) == []


def test_the_old_values_read_forward_through_one_canonicaliser():
    """Re-implementing the fallback at each reader is how `hip_pain` ended up
    dual-active in five modules rather than retired in one."""
    assert lifecycle_of({"status": "active"}) == "active"
    assert lifecycle_of({"status": "paused"}) == "on_hold"
    assert lifecycle_of({"status": "abandoned"}) == "cancelled"
    # THE SPLIT ITSELF: `achieved` was an achievement value in a lifecycle
    # list, so forward it is lifecycle `completed` and the achievement half is
    # derived rather than carried.
    assert lifecycle_of({"status": "achieved"}) == "completed"


def test_the_successor_wins_over_the_retired_name():
    assert lifecycle_of({"lifecycle_status": "on_hold",
                         "status": "active"}) == "on_hold"


def test_a_line_carrying_neither_says_so():
    assert lifecycle_of({}) is None


# --- the derived axis --------------------------------------------------------

def test_achievement_is_none_where_the_engine_cannot_say():
    """An attested goal nobody can measure, or one with no target, gets no
    word - an answer to a question the engine was not able to ask."""
    assert achievement_of(None, 100, "active", None) is None
    assert achievement_of(50, None, "active", None) is None


def test_a_target_met_is_achieved():
    assert achievement_of(100, 100, "active", None) == "achieved"


def test_nothing_counted_is_not_the_same_as_something_counted():
    assert achievement_of(0, 100, "active", None) == "no_progress"
    assert achievement_of(1, 100, "active", None) == "in_progress"


def test_a_closed_window_is_not_achieved():
    """FHIR's reading, checked rather than assumed: `not-achieved` is "has not
    been met", which is a target unmet when its window closed.
    `not-attainable` means "not POSSIBLE to be met" - the modal claim G58's
    declaration gate makes - and using it here would be the word for the case
    it is not for."""
    assert achievement_of(50, 100, "active", -1) == "not_achieved"
    assert achievement_of(50, 100, "active", 3) == "in_progress"


def test_completed_and_still_holding_is_sustaining():
    """`achieved` was terminal and maintenance is not. A goal that reached its
    target and is keeping it had nowhere to live."""
    assert achievement_of(200, 150, "completed", None) == "sustaining"
    # A completed goal is judged against the CURRENT bucket, usually
    # half-elapsed. Reporting a shortfall there would assert "not met" about a
    # goal the athlete closed BECAUSE it was met, and would flip on a Monday.
    assert achievement_of(100, 150, "completed", None) is None


# --- and the measurement that makes `sustaining` possible at all -------------

def test_a_completed_goal_is_still_measured(tmp_path):
    """The missing word was not the only reason `sustaining` was
    inexpressible. The engine stopped counting the moment a goal left
    `active`, so a goal being held reported nothing to be held."""
    _made[0] += 1
    root = init(tmp_path / f"c{_made[0]}")
    (root / "data" / "goals.jsonl").write_text(json.dumps(a_goal(
        slug="hold", target=1000, lifecycle_status="completed")) + "\n",
        encoding="utf-8")

    def a_day(d):
        row = {k: None for k in KEYS["daily"]}
        row.update({"date": f"2030-06-{d:02d}", "steps": 9000,
                    "source": "watch", "_gen": CURRENT_GENERATION["daily"]})
        return row
    (root / "data" / "daily.jsonl").write_text("\n".join(
        json.dumps(a_day(d)) for d in range(1, 8)) + "\n", encoding="utf-8")

    Vitai(root, on="2030-06-07").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        counted, achievement, mints = con.execute(
            "SELECT counted, achievement_status, milestones FROM goal_progress"
        ).fetchone()
    finally:
        con.close()
    assert counted and counted > 0
    assert achievement == "sustaining"
    # MEASURED IS NOT SCORED-AGAINST. Passing a quarter of a target already
    # completed is not an achievement, and re-minting on every rebuild is the
    # celebratory defect this engine has taken out once already.
    assert mints == 0


# --- the read model ----------------------------------------------------------

def test_both_axes_reach_the_read_model_and_the_old_name_still_works(tmp_path):
    """`status` keeps its column carrying the same value, so a consumer
    reading the old name is not broken by the split.

    Built from the TRACKED demo data into tmp, never read from
    `examples/demo/derived/`, which is gitignored and produced by a different
    CI job - a test reading it passes on a developer's tree with a leftover
    build and fails on a fresh clone.
    """
    import shutil
    src = Path(__file__).resolve().parents[1] / "examples" / "demo"
    root = tmp_path / "demo"
    shutil.copytree(src, root, ignore=shutil.ignore_patterns("derived"))
    Vitai(root, on="2030-06-30").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(goal_progress)")]
        rows = con.execute("SELECT status, lifecycle_status, "
                           "achievement_status FROM goal_progress").fetchall()
    finally:
        con.close()
    for name in ("status", "lifecycle_status", "achievement_status"):
        assert name in cols
    assert rows and all(old == new for old, new, _ in rows)
    # The corpus demonstrates `sustaining`, which was inexpressible before:
    # `achieved` was terminal, and the engine stopped measuring a goal the
    # moment it left `active`.
    assert "sustaining" in {a for _, _, a in rows}
