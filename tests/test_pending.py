"""A refusal that means "not yet" (#202).

`no_input` says the record holds nothing. True, and it cannot tell an athlete
that nothing will ever come apart from a source that delivers in four hours -
so the honest client sentence built on it is "check again later", which is the
most robotic thing this engine makes anyone say.

`pending` says the question is answerable and not yet, and carries when. The
degradation is the point and most of this file: a refusal that stayed hopeful
forever would be a broken connector nobody noticed.

Driven through `Vitai.verdicts()` and the read model as well as through the
units. The first cut of these tests exercised the three functions directly and
passed against a feature that was inert in every default path and whose
contract-announced column did not exist.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.verdicts import (MIN_GAPS_FOR_CADENCE, NO_INPUT, PENDING,
                            REFUSAL_REASONS, _awaiting, _row, expected_next)

WEEK = "2030-06-10"                      # a Monday; the week ends the 16th


def scale(day: int, source: str = "scale") -> dict:
    return {"date": f"2030-06-{day:02d}", "kg": 80.0, "source": source}


DAILY = [scale(d) for d in range(1, 10)]          # every day, 1st to 9th


# --- the cadence is earned, never declared -----------------------------------

def test_a_daily_source_is_due_tomorrow():
    assert expected_next(DAILY, date(2030, 6, 9), "kg") == date(2030, 6, 10)


def test_a_weekly_source_is_due_in_a_week():
    weekly = [{"date": d, "kg": 80.0, "source": "hand"}
              for d in ("2030-05-05", "2030-05-12", "2030-05-19",
                        "2030-05-26", "2030-06-02", "2030-06-09")]
    assert expected_next(weekly, date(2030, 6, 9), "kg") == date(2030, 6, 16)


def test_a_thin_history_says_nothing():
    """The same discipline the verdict layer already applies to weigh-in
    timing: where the reference is thin, decline rather than average. A
    guessed cadence promises an athlete something is coming when nothing is."""
    for n in range(MIN_GAPS_FOR_CADENCE + 1):
        assert expected_next(DAILY[:n], date(2030, 6, 9), "kg") is None
    assert expected_next(DAILY[:MIN_GAPS_FOR_CADENCE + 1],
                         date(2030, 6, 9), "kg") is not None


def test_sources_are_not_pooled_into_a_cadence_neither_has():
    """A nightly device and a monthly clinic visit averaged together produce a
    cadence belonging to nobody. Per source, and the answer is the earliest
    next arrival, because the question is when this metric next lands."""
    nightly = [scale(d, "watch") for d in range(1, 10)]
    monthly = [{"date": d, "kg": 80.0, "source": "clinic"}
               for d in ("2030-01-05", "2030-02-05", "2030-03-05",
                         "2030-04-05", "2030-05-05")]
    assert expected_next(nightly + monthly, date(2030, 6, 9), "kg") == \
        date(2030, 6, 10)
    # The clinic alone is a monthly cadence, and is not dragged earlier by it.
    assert expected_next(monthly, date(2030, 6, 9), "kg") == date(2030, 6, 5)


def test_a_row_without_the_value_is_not_an_arrival():
    """A well-formed line whose field is null did not deliver that field, and
    counting it would promise a reading that never comes."""
    hollow = [{"date": f"2030-06-{d:02d}", "kg": None, "source": "scale"}
              for d in range(1, 10)]
    assert expected_next(hollow, date(2030, 6, 9), "kg") is None


def test_a_time_bearing_date_does_not_take_the_build_down():
    """A `date` carrying a time is a schema WARNING and still loads, so
    parsing it strictly here would break a build that worked yesterday."""
    timed = [{"date": f"2030-06-{d:02d}T07:30:00", "kg": 80.0,
              "source": "scale"} for d in range(1, 10)]
    assert expected_next(timed, date(2030, 6, 9), "kg") == date(2030, 6, 10)


def test_one_forgotten_week_does_not_move_the_estimate():
    """The MEDIAN gap, not the mean. A holiday, a flat battery or a forgotten
    week is the normal shape of a person's logging rather than an outlier to
    be cleaned, and a mean would let one of them make the estimate useless."""
    lapsed = [{"date": d, "kg": 80.0, "source": "scale"}
              for d in ("2030-06-01", "2030-06-02", "2030-06-03", "2030-06-04",
                        "2030-06-05", "2030-07-20")]
    assert expected_next(lapsed, date(2030, 7, 20), "kg") == date(2030, 7, 21)


def test_the_future_is_not_evidence():
    """Rows dated after the viewpoint cannot inform what is due, or a record
    reconstructed at a past instant would borrow tomorrow's arrivals."""
    assert expected_next(DAILY, date(2030, 6, 5), "kg") == date(2030, 6, 6)


# --- pending, and the degradation that keeps it honest -----------------------

def test_a_source_still_due_this_week_is_pending():
    assert _awaiting(DAILY, "kg", WEEK, date(2030, 6, 10)) == {
        "reason": PENDING, "due": "2030-06-10"}


def test_due_today_is_not_late():
    """"Arrives in four hours" is the case this exists for, and reading it as
    overdue would refuse the very situation it was built to describe."""
    assert _awaiting(DAILY, "kg", WEEK, date(2030, 6, 10))["reason"] == PENDING


def test_a_source_that_did_not_come_degrades_and_keeps_the_date():
    """THE TRAP THIS AVOIDS. A metric that stayed pending forever is a broken
    connector nobody noticed. Once the expected day is past the reason drops
    back to `no_input` - and the date rides along, so a consumer reports a
    late source rather than repeating that the answer is coming."""
    assert _awaiting(DAILY, "kg", WEEK, date(2030, 6, 12)) == {
        "reason": NO_INPUT, "due": "2030-06-10"}


def test_an_arrival_that_lands_outside_the_week_cannot_fill_it():
    """Either side. A rate needs two weeks, and waiting for tomorrow to fill
    last week is waiting for the wrong thing."""
    assert _awaiting(DAILY, "kg", "2030-05-06", date(2030, 6, 10)) == {
        "reason": NO_INPUT}
    assert _awaiting(DAILY, "kg", "2030-07-01", date(2030, 6, 10)) == {
        "reason": NO_INPUT}


def test_no_established_cadence_refuses_exactly_as_before():
    assert _awaiting(DAILY[:2], "kg", WEEK, date(2030, 6, 10)) == {
        "reason": NO_INPUT}


def test_without_a_viewpoint_nothing_is_pending():
    """`pending` is a claim about a moment, and there is no moment here."""
    assert _awaiting(DAILY, "kg", WEEK, None) == {"reason": NO_INPUT}


# --- the row will not let it ship half-said ----------------------------------

def test_pending_without_a_date_is_refused():
    """Without an instant it is `no_input` wearing optimism."""
    with pytest.raises(ValueError, match="carries WHEN"):
        _row(WEEK, "weight_rate", None, None, "no_data", reason=PENDING)


def test_a_judgement_carries_no_due_date():
    with pytest.raises(ValueError, match="carries no due date"):
        _row(WEEK, "weight_rate", 0.3, 0.35, "on_target", due="2030-06-15")


def test_pending_is_in_the_refusal_vocabulary():
    assert PENDING in REFUSAL_REASONS
    assert _row(WEEK, "weight_rate", None, None, "no_data", reason=PENDING,
                due="2030-06-15")["due"] == "2030-06-15"


def test_every_judged_row_carries_a_null_due():
    row = _row(WEEK, "weight_rate", 0.3, 0.35, "on_target")
    assert row["due"] is None and row["reason"] is None


# --- through the engine, which is where the first cut of this was inert ------

def _repo(tmp_path: Path) -> Path:
    """Weigh-ins every day to the 9th, and a step count on the 10th so the
    week of the 10th exists to be judged at all."""
    root = init(tmp_path / "content")
    (root / "vitai.toml").write_text(
        "[targets]\nphases = [[80.0, 70.0, 0.5]]\n", encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text("\n".join(
        json.dumps({"date": f"2030-06-{d:02d}", "kg": 80.0 - d * 0.05,
                    "source": "scale", "note": None})
        for d in range(1, 10)) + "\n", encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(json.dumps(
        {"date": "2030-06-10", "steps": 9000, "source": "watch",
         "note": None}) + "\n", encoding="utf-8")
    return root


def test_the_viewpoint_reaches_the_refusal(tmp_path):
    """`Vitai.verdicts()` dropped its pinned viewpoint on the floor, so every
    refusal answered `no_input` however obviously a source was due. `rollup`
    carries a comment about this exact trap two methods below."""
    root = _repo(tmp_path)
    rows = [r for r in Vitai(root, on=date(2030, 6, 10)).verdicts()
            if r["metric"] == "weight_rate" and r["week"] == "2030-06-10"]
    assert len(rows) == 1
    assert rows[0]["reason"] == PENDING
    assert rows[0]["due"] == "2030-06-10"


def test_the_same_record_a_week_later_is_not_still_hopeful(tmp_path):
    root = _repo(tmp_path)
    rows = [r for r in Vitai(root, on=date(2030, 6, 17)).verdicts()
            if r["metric"] == "weight_rate" and r["week"] == "2030-06-10"]
    assert rows and rows[0]["reason"] == NO_INPUT
    assert rows[0]["due"] == "2030-06-10"      # and it says how late


def test_due_reaches_the_read_model(tmp_path):
    """The contract announces a `due` column, so there has to be one."""
    root = _repo(tmp_path)
    Vitai(root, on=date(2030, 6, 10)).build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(verdicts)")]
        assert "due" in cols
        got = con.execute(
            "SELECT reason, due FROM verdicts WHERE metric='weight_rate' "
            "AND week='2030-06-10'").fetchall()
    finally:
        con.close()
    assert got == [(PENDING, "2030-06-10")]


def test_an_unnamed_viewpoint_comes_from_the_record(tmp_path):
    """This asserted that a caller who names no viewpoint gets no claim about
    what is still coming, because there was no viewpoint to make one from -
    `self.on` was the wall clock, and against a 2030 record every source was
    long overdue.

    There is always a viewpoint now: the record's own last day. So the same
    call answers what it would have answered had the caller named that date,
    which is the point of one viewpoint everywhere.
    """
    root = _repo(tmp_path)
    unnamed = [r for r in Vitai(root).verdicts() if r["metric"] == "weight_rate"]
    named = [r for r in Vitai(root, on=date(2030, 6, 10)).verdicts()
             if r["metric"] == "weight_rate"]
    assert unnamed == named
    assert any(r["reason"] == PENDING for r in unnamed)
