"""A build is a function of the record (#207).

`goal_progress` is materialised against a viewpoint, and that viewpoint was the
wall clock. So two people building one record on different days got different
databases, nothing about the record having changed - and `meta` carried no
record of the choice, so a consumer could not tell "this athlete declared no
goals" from "none were in force on the day someone ran the build".

The example corpus shipped an empty `goal_progress` with twenty-three columns
beside a `contributions` table with 109 rows, which is what made it read as a
bug in the consumer rather than a property of the build.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from vitai.api import Vitai, init
from vitai.schema import CURRENT_GENERATION, KEYS

_made = [0]


def a_record(tmp_path: Path) -> Path:
    """A record whose horizon is a fixed date, with a goal in force on it.

    The dates are FIXED rather than relative to today, so what these tests
    assert does not drift with the calendar. 2030-06-14 is the horizon; no
    assertion here depends on where the wall clock sits relative to it.
    """
    _made[0] += 1
    root = init(tmp_path / f"content{_made[0]}")
    goal = {k: None for k in KEYS["goals"]}
    goal.update({"date": "2030-06-01", "slug": "steps", "title": "Walk daily",
                 "metric": "steps", "dataset": "daily", "target": 60000,
                 "policy": "monotonic", "period": "weekly", "status": "active",
                 "tracker": "sum", "_gen": CURRENT_GENERATION["goals"]})
    (root / "data" / "goals.jsonl").write_text(
        json.dumps(goal) + "\n", encoding="utf-8")

    def a_day(d):
        row = {k: None for k in KEYS["daily"]}
        row.update({"date": f"2030-06-{d:02d}", "steps": 9000,
                    "source": "watch", "_gen": CURRENT_GENERATION["daily"]})
        return row
    (root / "data" / "daily.jsonl").write_text("\n".join(
        json.dumps(a_day(d)) for d in range(1, 15)) + "\n", encoding="utf-8")
    return root


def meta_of(root: Path) -> dict:
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        return dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()


def progress_rows(root: Path) -> int:
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        return con.execute("SELECT count(*) FROM goal_progress").fetchone()[0]
    finally:
        con.close()


# --- the record decides, not the day someone ran it --------------------------

def test_an_unqualified_build_uses_the_records_last_date(tmp_path):
    root = a_record(tmp_path)
    Vitai(root).build()
    assert meta_of(root)["built_on"] == "2030-06-14"


def test_a_goal_in_force_during_the_record_is_scored(tmp_path):
    """The symptom that made this look like a consumer bug: an empty table
    with twenty-three columns, indistinguishable from an athlete who declared
    nothing."""
    root = a_record(tmp_path)
    Vitai(root).build()
    assert progress_rows(root) > 0


def test_two_builds_of_one_record_agree(tmp_path):
    """Rebuildability is the engine's central promise, and this table was
    quietly outside it.

    The equality alone would have passed under the old code too, whenever both
    builds ran on the same day - which is every run that does not straddle
    midnight. So it also pins WHICH viewpoint they agree on: the record's, not
    whichever day the suite happens to run.
    """
    root = a_record(tmp_path)
    Vitai(root).build()
    first = (meta_of(root), progress_rows(root))
    Vitai(root).build()
    assert (meta_of(root), progress_rows(root)) == first
    assert first[0]["built_on"] == "2030-06-14"


def test_a_record_that_ends_in_the_future_still_uses_its_own_horizon(tmp_path):
    """The point is not "an older date". It is the record's own horizon: a
    record whose last row is dated ahead of today builds as of that row."""
    root = a_record(tmp_path)
    # Past the record's own HORIZON, which is the premise that matters and
    # the one that does not expire. Asserting it is also past the wall clock
    # would plant a failure dated 2031 in a suite whose subject is removing
    # wall-clock dependence.
    ahead = "2031-01-02"
    assert date.fromisoformat(ahead) > Vitai(root).last_recorded()
    row = {k: None for k in KEYS["daily"]}
    row.update({"date": ahead, "steps": 100, "source": "watch",
                "_gen": CURRENT_GENERATION["daily"]})
    with (root / "data" / "daily.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    Vitai(root).build()
    assert meta_of(root)["built_on"] == ahead


# --- and a caller who names one is still obeyed ------------------------------

def test_an_explicit_viewpoint_still_wins(tmp_path):
    """"What does this look like now" is a real question; what changed is the
    answer when nobody asked it."""
    root = a_record(tmp_path)
    Vitai(root).build(today=date(2030, 6, 7))
    assert meta_of(root)["built_on"] == "2030-06-07"


def test_a_viewpoint_given_to_the_constructor_still_wins(tmp_path):
    root = a_record(tmp_path)
    Vitai(root, on=date(2030, 6, 7)).build()
    assert meta_of(root)["built_on"] == "2030-06-07"


def test_todays_date_passed_explicitly_is_honoured_not_overridden(tmp_path):
    """A caller who passes today's date and one who passes nothing hold the
    same value, and only one of them made a choice. `self.on` cannot tell them
    apart, which is why the request is tracked separately."""
    root = a_record(tmp_path)
    # ONCE. Reading the clock twice - here and inside the constructor - fails
    # across midnight, which is the whole class of bug this file is about.
    now = date.today()
    Vitai(root, on=now).build()
    assert meta_of(root)["built_on"] == now.isoformat()


# --- the horizon itself ------------------------------------------------------

def test_a_record_with_no_dated_rows_has_no_horizon(tmp_path):
    """Nothing whose visibility a viewpoint could decide, so there is nothing
    to take a horizon from and the build falls back to the clock."""
    _made[0] += 1
    root = init(tmp_path / f"empty{_made[0]}")
    assert Vitai(root).last_recorded() is None
    engine = Vitai(root)
    engine.build()
    assert meta_of(root)["built_on"] == engine.on.isoformat()


def test_the_horizon_is_the_latest_date_in_any_dataset(tmp_path):
    root = a_record(tmp_path)
    row = {k: None for k in KEYS["weight"]}
    row.update({"date": "2030-07-20", "kg": 80.0, "source": "scale",
                "_gen": CURRENT_GENERATION["weight"]})
    (root / "data" / "weight.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")
    assert Vitai(root).last_recorded() == date(2030, 7, 20)


# --- the horizon must survive the dates the validator accepts ----------------

def test_a_week_date_does_not_drag_the_horizon_backwards(tmp_path):
    """`date.fromisoformat` accepts ISO week dates and the basic format, and
    neither sorts chronologically against the extended one: `2030-W01-1`
    outranks every extended date in its year on the letter W alone. A string
    maximum picked a date months early, which put the build back on a viewpoint
    where nothing was in force - the exact symptom this exists to remove."""
    root = a_record(tmp_path)
    for odd in ("2030-W01-1", "20300101"):
        row = {k: None for k in KEYS["daily"]}
        row.update({"date": odd, "steps": 1, "source": "watch",
                    "_gen": CURRENT_GENERATION["daily"]})
        with (root / "data" / "daily.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    assert Vitai(root).last_recorded() == date(2030, 6, 14)


def test_a_date_that_will_not_parse_is_skipped_not_raised(tmp_path):
    """The loader promises a build proceeds from the good rows. Taking a record
    that built yesterday and refusing it today, over a horizon that one row
    could not have contributed to anyway, would break that promise."""
    root = a_record(tmp_path)
    for bad in ("2031-6-1", True, {"a": 1}, None):
        row = {k: None for k in KEYS["journal"]}
        row.update({"date": bad, "kind": "claim", "text": "x",
                    "source": "athlete"})
        with (root / "data" / "journal.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    # None of them raises, and none of them moves the horizon.
    assert Vitai(root).last_recorded() == date(2030, 6, 14)


def test_a_malformed_date_string_does_not_stop_the_build(tmp_path):
    """The string cases are what a loader actually hands through: JSON-valid,
    schema-invalid, never quarantined. A build that worked yesterday must not
    stop working because the horizon lookup met one.

    A NON-STRING date still fails the build, and did before this change too -
    sqlite cannot bind a dict. That is the loader validating at append rather
    than at load, and it is not this change's to fix.
    """
    root = a_record(tmp_path)
    row = {k: None for k in KEYS["journal"]}
    row.update({"date": "2031-6-1", "kind": "claim", "text": "x",
                "source": "athlete"})
    with (root / "data" / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    Vitai(root).build()
    assert meta_of(root)["built_on"] == "2030-06-14"


def test_the_rollup_agrees_with_the_weekly_file_the_build_writes(tmp_path):
    """Two renderings of one report disagreeing about when they were made."""
    root = a_record(tmp_path)
    Vitai(root).build()
    written = (root / "derived" / "weekly.md").read_text(encoding="utf-8")
    assert Vitai(root).rollup() == written


def test_accepting_an_inference_does_not_stamp_a_stale_horizon(tmp_path):
    """The rows go in through a MODULE function with no instance to tell, so
    the read cache still held the record as it was. A stale read would stamp a
    horizon the record no longer has, which is worse than a missing row."""
    root = a_record(tmp_path)
    engine = Vitai(root)
    engine.datasets()                          # warm the cache, as infer does
    engine.accept_inferences([{
        "date": "2030-07-05", "statement": "x", "model": "test",
        "confidence": "low", "evidence": "y", "depends_on": None}])
    assert meta_of(root)["built_on"] == "2030-07-05"
