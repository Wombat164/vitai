"""A day still open (#186).

`daily.coverage` has carried `full | partial | manual` since generation 2, been
validated all along, and been read by nothing.

The cost is not theoretical. A nutrition export taken while a day was still
being logged captured breakfast and lunch and read as under half of what that
day eventually totalled. For the seven minutes until the next import, the
record held a perfectly well-formed row asserting a large intake shortfall that
had not happened - and it rendered exactly like a row asserting one that had.

The issue is blunt about the choice: scoring an open day is fine, scoring it as
FINAL is the one option that is wrong. So a weekly figure built over a day the
record marks `partial` now says so.

A SECOND FIELD, NOT A THIRD VALUE OF `answers`, which departs from a note in
`verdicts.py` reserving `provisional` there. They answer different questions:
`answers` says what RESOLUTION the engine will vouch for, and a provisional
magnitude is still a magnitude - a number to render, marked not-final. Folded
together, a consumer would have to choose between knowing the figure is
provisional and knowing it is a figure.

WHAT IS NOT FIXED HERE, and the register keeps saying so: `coverage` is one
field on a row several sources write to, so whichever importer sets it wins
uncontested. Reading it errs the safe way - over-marking a figure as not-final
is the direction the issue asks for - but whose opinion it is remains open.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai
from vitai.db import VERDICT_KEYS
from vitai.schema import COVERAGES, KEYS, PARTIAL

PERSONAS = Path(__file__).resolve().parent / "fixtures" / "personas"


def day(date: str, **kw) -> dict:
    return {**{k: None for k in KEYS["daily"]}, "date": date, "steps": 9000,
            "source": "manual", **kw}


def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsteps_floor = 8000\n',
        encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def steps_rows(v: Vitai) -> list[dict]:
    return [r for r in v.verdicts() if r["metric"] == "steps"]


# --- the signal ---------------------------------------------------------------

def test_a_week_holding_an_open_day_is_marked_provisional(tmp_path):
    # 2030-05-06 is a Monday, so 6..12 is exactly one ISO week - a fixture
    # straddling two of them marks only the week holding the open day, which
    # is correct behaviour and proves nothing about the rule.
    rows = [day(f"2030-05-{d:02d}") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage=PARTIAL))
    got = steps_rows(record(tmp_path, rows))
    assert got and all(r["provisional"] is True for r in got), got


def test_one_open_day_is_enough(tmp_path):
    """The aggregate changes when the rest of that day arrives, however many
    finished days sit beside it."""
    rows = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage=PARTIAL))
    assert all(r["provisional"] for r in steps_rows(record(tmp_path, rows)))


def test_a_finished_week_is_not(tmp_path):
    rows = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 13)]
    got = steps_rows(record(tmp_path, rows))
    assert got and not any(r["provisional"] for r in got), got


def test_absent_coverage_is_not_read_as_complete_and_not_as_open(tmp_path):
    """Most of every record predates the field. Reading silence as complete is
    the confident answer this removes; reading it as open would mark the whole
    corpus and make the signal worthless."""
    rows = [day(f"2030-05-{d:02d}") for d in range(6, 13)]
    got = steps_rows(record(tmp_path, rows))
    assert got and not any(r["provisional"] for r in got), got


def test_manual_is_not_open(tmp_path):
    """`full` and `manual` both describe a day that was logged. Only `partial`
    says the record knew there was more to come."""
    rows = [day(f"2030-05-{d:02d}", coverage="manual") for d in range(6, 13)]
    assert not any(r["provisional"] for r in steps_rows(record(tmp_path, rows)))


def test_the_open_week_and_the_finished_week_are_told_apart(tmp_path):
    """The confusion the field exists to remove, in one record: two weeks, the
    same figures, one of them unfinished."""
    rows = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 13)]
    rows += [day(f"2030-05-{d:02d}", coverage="full") for d in range(13, 19)]
    rows.append(day("2030-05-19", coverage=PARTIAL))
    by_week = {r["week"]: r for r in steps_rows(record(tmp_path, rows))}
    assert len(by_week) >= 2
    marked = {w for w, r in by_week.items() if r["provisional"]}
    assert len(marked) == 1, by_week


# --- and it does not decide anything -------------------------------------------

def test_the_verdict_itself_is_unchanged(tmp_path):
    """Scoring an open day is fine. The row says the figure is not final; it
    does not refuse, and it does not move the judgement - a threshold on
    completeness would be a number nobody published."""
    finished = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 13)]
    open_week = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 12)]
    open_week.append(day("2030-05-12", coverage=PARTIAL))

    a = steps_rows(record(tmp_path / "a", finished))[0]
    b = steps_rows(record(tmp_path / "b", open_week))[0]
    assert a["verdict"] == b["verdict"] == "on_target"
    assert a["value"] == b["value"]
    assert a["provisional"] is not True and b["provisional"] is True


def test_a_provisional_magnitude_is_still_a_magnitude(tmp_path):
    """Why this is a second field rather than a third value of `answers`. As a
    value it would make a consumer choose between knowing the figure is
    provisional and knowing it is a figure."""
    rows = [day(f"2030-05-{d:02d}") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage=PARTIAL))
    row = steps_rows(record(tmp_path, rows))[0]
    assert row["provisional"] is True
    assert row["answers"] == "magnitude"
    assert row["value"] is not None


def test_a_refusal_carries_no_provisional_flag(tmp_path):
    """It describes a value. A row with none has no figure to call not-final."""
    rows = [day(f"2030-05-{d:02d}", steps=None, coverage=PARTIAL)
            for d in range(6, 13)]
    for r in record(tmp_path, rows).verdicts():
        if r.get("value") is None:
            assert not r.get("provisional"), r


# --- the vocabulary and the column ---------------------------------------------

def test_the_open_value_has_one_home():
    """`PARTIAL` is named rather than spelled at each reader: a verdict turns
    on it, and a literal in a comparison is how a vocabulary quietly grows a
    second spelling."""
    assert PARTIAL == "partial" and PARTIAL in COVERAGES


def test_it_reaches_the_read_model(tmp_path):
    rows = [day(f"2030-05-{d:02d}") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage=PARTIAL))
    v = record(tmp_path, rows)
    con = sqlite3.connect(v.build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(verdicts)")]
        assert "provisional" in cols
        got = con.execute(
            "SELECT provisional FROM verdicts WHERE metric = 'steps'").fetchall()
        assert got and all(r[0] == 1 for r in got), got
    finally:
        con.close()


def test_the_column_is_appended_rather_than_inserted():
    before = ["week", "metric", "value", "target", "verdict", "goal", "reason",
              "due", "statistic", "window_days", "observed_days", "answers"]
    assert VERDICT_KEYS[:len(before)] == before
    assert "provisional" in VERDICT_KEYS[len(before):]


def test_the_corpus_exercises_it():
    """Against the shipped record rather than a fixture written to show it -
    `yasmin` logs partial days, so the signal has a witness that was not
    written for the signal."""
    marked = [r for r in Vitai(PERSONAS / "yasmin").verdicts()
              if r.get("provisional")]
    assert marked, "yasmin has weeks holding a partial day"
    assert all(r["value"] is not None for r in marked)
