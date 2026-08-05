"""The weekly session rollup, and the one definition of a week (#208).

The read model had no table saying how far the athlete ran this week or how
many sessions he did, so every client computed it. One did, and was wrong
twice at once: it invented a type taxonomy that silently dropped 17 of 43
sessions, and it reimplemented the week boundary, agreeing with the engine's
Monday by luck.

Both halves are pinned here. The taxonomy test is the important one, because
the failure mode is a chart that looks entirely plausible while missing two
fifths of the record.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.db import CONTRACT_VERSION, DERIVED_TABLES
from vitai.schema import CURRENT_GENERATION, KEYS, validate_record
from vitai.weeks import session_weeks, week_key, week_of

_made = [0]


def s(**kw) -> dict:
    rec = {k: None for k in KEYS["sessions"]}
    rec.update({"date": "2030-05-06", "type": "run", "distance_km": 10.0,
                "duration_s": 3600, "source": "watch",
                "_gen": CURRENT_GENERATION["sessions"]})
    rec.update(kw)
    return rec


def record(tmp_path: Path, rows: list[dict]) -> Path:
    _made[0] += 1
    root = init(tmp_path / f"content{_made[0]}")
    (root / "data" / "sessions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return root


def test_every_session_type_in_the_record_survives_the_rollup(tmp_path):
    """THE DEFECT THIS TABLE EXISTS TO PREVENT.

    The client bucketed `run`/`test` as "runs" and anything starting `gym` as
    "gym", so `strength`, `walk` and `row` matched neither and vanished with
    their distance. The engine's vocabulary is the engine's: nothing here maps
    a type onto anything, and the counts must add up to the sessions logged.
    """
    rows = [s(type="run", distance_km=10.0),
            s(type="strength", distance_km=None),
            s(type="walk", distance_km=4.0),
            s(type="row", distance_km=6.0)]

    out = session_weeks(rows, "2030-05-06")

    assert {r["type"] for r in out} == {"run", "strength", "walk", "row"}
    assert sum(r["sessions"] for r in out) == len(rows)


def test_a_week_with_no_sessions_is_present_and_says_zero(tmp_path):
    """A gap must read as a gap.

    Dropping empty weeks makes a deload week, an injured month and a dead
    connector all look like time briefly running faster.
    """
    rows = [s(date="2030-05-06"), s(date="2030-05-27")]

    out = session_weeks(rows, "2030-05-27")

    weeks = [r["week"] for r in out]
    assert weeks == ["2030-05-06", "2030-05-13", "2030-05-20", "2030-05-27"]
    empty = [r for r in out if r["sessions"] == 0]
    assert [r["week"] for r in empty] == ["2030-05-13", "2030-05-20"]


def test_an_empty_week_is_told_apart_by_its_count_not_a_null_type(tmp_path):
    """A session whose type never got recorded is a LOGGED session.

    Marking empty weeks with a null type would make the two indistinguishable,
    and a week containing one untyped session would read as a week containing
    nothing.
    """
    rows = [s(date="2030-05-06", type=None), s(date="2030-05-20")]

    out = session_weeks(rows, "2030-05-20")
    untyped = [r for r in out if r["week"] == "2030-05-06"]
    empty = [r for r in out if r["week"] == "2030-05-13"]

    assert untyped[0]["type"] is None and untyped[0]["sessions"] == 1
    assert empty[0]["type"] is None and empty[0]["sessions"] == 0


def test_a_distance_nobody_recorded_is_null_and_never_zero(tmp_path):
    """Summing an absent distance as zero reports a swim, a strength session
    and a broken import identically, all as having covered no ground."""
    out = session_weeks([s(type="strength", distance_km=None)], "2030-05-06")

    assert out[0]["distance_km"] is None
    assert out[0]["duration_s"] == 3600


def test_a_partly_logged_week_sums_what_is_there_and_counts_them_all(tmp_path):
    """Three sessions, one distance. The count says 3 and the distance says
    what was written down, which is the honest shape of a partial week."""
    rows = [s(distance_km=10.0), s(distance_km=None), s(distance_km=None)]

    out = session_weeks(rows, "2030-05-06")

    assert out[0]["sessions"] == 3
    assert out[0]["distance_km"] == 10.0


def test_the_week_is_the_engines_monday_everywhere(tmp_path):
    """The boundary the client agreed with by luck.

    Checked against `schema`'s week rule, which is the one place in the engine
    that decides what a week is WITHOUT calling this function: it validates an
    authored `week` field by asserting the day is a Monday. An earlier version
    cross-checked `verdicts` instead, which was worthless twice over - the
    fixture produced no verdict rows so the assertion was vacuous, and
    `verdicts` now delegates here, so the two could not have disagreed.
    """
    assert week_key("2030-05-09") == "2030-05-06"      # a Thursday
    assert week_key("2030-05-06") == "2030-05-06"      # the Monday itself
    assert week_key("2030-05-05") == "2030-04-29"      # the Sunday before
    assert week_key(None) is None

    def week_complaints(value):
        row = {k: None for k in KEYS["emissions"]}
        row.update({"date": "2030-05-09", "kind": "verdict", "week": value,
                    "_gen": CURRENT_GENERATION["emissions"]})
        return [p for p in validate_record("emissions", row) if "week" in p]

    assert week_complaints(week_key("2030-05-09")) == []
    assert week_complaints("2030-05-09") != []         # the Thursday itself

    root = record(tmp_path, [s(date="2030-05-09")])
    assert {r["week"] for r in Vitai(root).session_weeks()} == {"2030-05-06"}


def test_a_row_the_engine_cannot_date_is_named_rather_than_bucketed(tmp_path):
    """The contract the dedup nearly lost, and it had no test until it did.

    Four copies of the week arithmetic carried TWO contracts: `verdicts`,
    `report` and `contributions` raised on a value that was not a date, and
    `query` returned "". Unifying onto the tolerant one passed every test in
    this repo while turning a named `ValueError` in the rollup into a `None`
    bucket that renders as a literal "None" week.

    Pinned at each CALLER rather than on the helper, because that is what a
    regression would change: switching one import from `week_of` to
    `week_key` is a one-word edit that nothing else here notices.
    """
    from vitai.contributions import _week_key as contributions_week
    from vitai.query import _week_key as query_week
    from vitai.report import _week_key as report_week
    from vitai.verdicts import _week_key as verdicts_week

    assert week_key("06/05/2030") is None
    with pytest.raises(ValueError) as raised:
        week_of("06/05/2030")
    assert "06/05/2030" in str(raised.value)

    for strict in (verdicts_week, report_week, contributions_week):
        with pytest.raises(ValueError) as raised:
            strict("06/05/2030")
        assert "06/05/2030" in str(raised.value), (
            "the value must be NAMED: a silent bucket under None renders as "
            "a week and reports the failure as data")

    # `query` is the one that always tolerated it, and still must.
    assert query_week("06/05/2030") == ""

    # And the new derivation refuses rather than dropping the row, which is
    # the same class of vanishing this whole table exists to stop.
    with pytest.raises(ValueError):
        session_weeks([s(date="06/05/2030")], "2030-05-06")


def test_a_session_type_that_is_not_a_string_does_not_stop_the_build(tmp_path):
    """Schema warns and the build proceeds, so sorting must not be the thing
    that refuses. One bad row taking down the whole read model is the failure
    `api.sets` already coerces against."""
    rows = [s(date="2030-05-06", type=3), s(date="2030-05-06", type="run")]

    out = session_weeks(rows, "2030-05-06")

    assert sum(r["sessions"] for r in out) == 2


def test_the_engine_defines_a_week_in_exactly_one_place():
    """`verdicts`, `contributions`, `report` and `query` each carried their
    own copy of this arithmetic. Four identical definitions are three chances
    for one of them to be corrected alone, and the argument against a client
    reimplementing the week is not weakened by the engine doing it four times.
    """
    src = Path(__file__).resolve().parents[1] / "src" / "vitai"
    offenders = []
    for path in sorted(src.glob("*.py")):
        if path.name == "weeks.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # The BUCKETING arithmetic specifically. `schema` calls
            # `.weekday()` to validate that an authored week field names a
            # Monday, which reads the definition rather than restating it.
            if "timedelta(days=" in line and "weekday()" in line:
                offenders.append(f"{path.name}:{n}")

    assert not offenders, (
        f"week bucketing outside weeks.py: {offenders}. Call "
        f"`weeks.week_key` instead of computing the Monday again.")


def test_the_table_reaches_the_read_model(tmp_path):
    """A derivation nothing writes out is the specified-and-never-written
    defect, which is what #204's register exists to catch."""
    root = record(tmp_path, [s(date="2030-05-06"), s(date="2030-05-20")])
    Vitai(root).build()

    con = sqlite3.connect(root / "derived" / "health.db")
    rows = con.execute(
        "SELECT week, type, sessions, distance_km FROM session_weeks "
        "ORDER BY week").fetchall()
    contract, = con.execute(
        "SELECT value FROM meta WHERE key='contract'").fetchone()
    con.close()

    assert [r[0] for r in rows] == ["2030-05-06", "2030-05-13", "2030-05-20"]
    assert rows[1][2] == 0                       # the empty week, as a row
    assert contract == CONTRACT_VERSION
    assert set(DERIVED_TABLES["session_weeks"]) == {
        "week", "type", "sessions", "distance_km", "duration_s"}


def test_two_builds_of_one_record_agree(tmp_path):
    """Determinism (#207). The viewpoint bounds the last week, so a rebuild on
    another day cannot grow the table."""
    root = record(tmp_path, [s(date="2030-05-06")])
    v = Vitai(root)

    assert v.session_weeks("2030-05-06") == v.session_weeks("2030-05-06")
    # A LATER viewpoint carries the weeks between, rather than inventing rows
    # before the record starts.
    later = v.session_weeks("2030-05-20")
    assert [r["week"] for r in later] == ["2030-05-06", "2030-05-13",
                                          "2030-05-20"]
    assert later[0]["week"] == "2030-05-06"


def test_a_viewpoint_before_the_last_session_does_not_hide_it(tmp_path):
    """Hiding rows the record holds would be the engine editing history to
    match the day it was asked, which is not what a viewpoint is for."""
    rows = [s(date="2030-05-06"), s(date="2030-05-20")]

    out = session_weeks(rows, "2030-05-06")

    assert [r["week"] for r in out] == ["2030-05-06", "2030-05-13",
                                        "2030-05-20"]


def test_a_record_with_no_sessions_produces_no_rows(tmp_path):
    """No first week to start from. An empty table is the honest answer, and
    inventing a range around the viewpoint would manufacture weeks of zeros
    for a record that never claimed to hold sessions."""
    assert session_weeks([], "2030-05-06") == []
