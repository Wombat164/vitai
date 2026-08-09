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


def test_a_suppressed_row_keeps_its_flag(tmp_path):
    """A suppressed metric is still RECORDED, just not scored - the row keeps
    its figure by design. So there IS a number to call not-final, and the
    rewrite that relabels the row was silently dropping the flag.

    The test that stood here asserted the opposite rule over a fixture that
    produced no rows at all, so its loop never ran and it would have passed
    whatever the code did."""
    rows = [day(f"2030-05-{d:02d}") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage=PARTIAL))
    root = (tmp_path / "content")
    record(tmp_path, rows)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsteps_floor = 8000\n'
        '[preferences]\nsuppressed_metrics = ["steps"]\n', encoding="utf-8")
    got = steps_rows(Vitai(root))
    assert got and all(r["reason"] == "suppressed" for r in got), got
    assert all(r["value"] is not None for r in got), "the figure is kept"
    assert all(r["provisional"] is True for r in got), got


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


# --- the metrics the first cut skipped ----------------------------------------

def nutrition(tmp_path: Path, partial_last: bool) -> Vitai:
    """Fourteen days of intake, the last optionally still being logged."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    rows = [{**{k: None for k in KEYS["daily"]}, "date": f"2030-05-{n:02d}",
             "kcal_in": 1150, "protein_g": 90, "source": "app"}
            for n in range(1, 14)]
    last = {**{k: None for k in KEYS["daily"]}, "date": "2030-05-14",
            "kcal_in": 200, "protein_g": 12, "source": "app"}
    if partial_last:
        last["coverage"] = PARTIAL
    rows.append(last)
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["weight"]}, "date": "2030-05-01", "kg": 70.0,
         "source": "scale"}) + "\n", encoding="utf-8")
    return Vitai(root)


def test_the_incident_row_itself_is_marked(tmp_path):
    """THE MOTIVATING CASE, and the first cut skipped it. `intake_floor` is
    built from the same daily rows as the metrics that were wired, and it is
    the row the issue's whole account is about: a nutrition export taken at
    lunchtime producing a well-formed intake shortfall that had not happened.
    It rendered as final."""
    got = {r["metric"]: r for r in nutrition(tmp_path, True).verdicts()}
    assert got["intake_floor"]["provisional"] is True, got["intake_floor"]
    assert got["intake_floor"]["verdict"] == "behind", "still scored"
    assert got["intake_floor"]["value"] is not None


def full_record(tmp_path: Path, outvote: bool) -> Vitai:
    """Every daily-built metric at once, over an outvoted open day.

    Written after review found the three RED-S floors, `energy_availability`
    and the read-model path each unwitnessed - the fixtures above log steps
    only, so a floor row never existed for them to check. This one carries
    intake, protein, sleep, rhr and pain; a body-composition read and priced
    sessions so EA computes; and, when `outvote` is set, a watch calling the
    last day `full` against the app's `partial`.

    THE OUTVOTE IS THE POINT for the floors. They window over the RAW rows
    for the same reason the weekly loop does, and reading the canonical rows
    instead would take the watch's answer - which is the incident."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n'
        "[tripwires]\nsteps_floor = 8000\nsleep_floor_h = 7.5\n"
        "rhr_baseline = 45\npain_gate = 2\n"
        "[resolution]\nsource_order = ['watch', 'app']\n", encoding="utf-8")

    def full_day(date: str, **kw) -> dict:
        return {**{k: None for k in KEYS["daily"]}, "date": date, "steps": 9000,
                "kcal_in": 1150, "protein_g": 90, "sleep_h": 7.0, "rhr": 52,
                "pain": 1, "source": "watch", "coverage": "full", **kw}

    rows = [full_day(f"2030-05-{n:02d}") for n in range(1, 14)]
    rows.append(full_day("2030-05-14", kcal_in=200, protein_g=12,
                         coverage="full" if outvote else PARTIAL))
    if outvote:
        rows.append(full_day("2030-05-14", kcal_in=200, protein_g=12,
                             source="app", coverage=PARTIAL))
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    # A composition read, because `_fat_free_mass` never estimates one and EA
    # is simply not computed without it.
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["weight"]}, "date": "2030-05-01", "kg": 70.0,
         "body_fat_pct": 20.0, "source": "scale"}) + "\n", encoding="utf-8")
    (root / "data" / "sessions.jsonl").write_text(
        "".join(json.dumps(
            {**{k: None for k in KEYS["sessions"]}, "date": f"2030-05-{n:02d}",
             "sport": "run", "duration_s": 3600, "kcal": 600,
             "source": "watch"}) + "\n" for n in range(1, 15)), encoding="utf-8")
    return Vitai(root)


DAILY_BUILT = ("steps", "sleep", "rhr", "pain_gate", "intake_floor",
               "protein_floor", "energy_availability")


def test_every_metric_built_from_the_daily_rows_answers_the_question(tmp_path):
    """An inconsistent flag is worse than none, because absence reads as
    "this one is final" - so a consumer would have to hardcode which metrics
    are wired, which is the duplication this engine exists to prevent.

    `pain_gate` was the one left out, and the first version of this test
    hardcoded a set that did not name it - a consistency check written around
    the gap it was there to find. The fixture now reaches all seven."""
    got = {r["metric"]: r for r in full_record(tmp_path, False).verdicts()}
    missing = [m for m in DAILY_BUILT if m not in got]
    assert not missing, f"fixture no longer reaches {missing}"
    for metric in DAILY_BUILT:
        assert got[metric]["provisional"] is True, metric
        assert got[metric]["value"] is not None, f"{metric} still scores"


def test_the_floors_hear_the_open_claim_that_lost_the_contest(tmp_path):
    """The floors window over the RAW rows, not the canonical ones.

    Review found this unwitnessed: replacing `open_day_in(raw_window or
    window)` with `open_day_in(window)` in all three floors passed the whole
    suite, because the outvote fixture above logs steps and produces no floor
    row. Here the watch wins the day and calls it `full`, and the floors must
    still hear the app."""
    v = full_record(tmp_path, True)
    canonical = [r for r in v.canonical("daily") if r["date"] == "2030-05-14"]
    assert canonical[0]["coverage"] == "full", "the ladder picked the watch"
    got = {r["metric"]: r for r in v.verdicts()}
    for metric in ("intake_floor", "protein_floor", "energy_availability"):
        assert got[metric]["provisional"] is True, metric


def test_the_outvoted_claim_reaches_the_read_model_too(tmp_path):
    """The SQL surface, on the path review found unwitnessed: reverting
    `raw_daily` at the `_derivations` call site - the one `build()` uses -
    passed all 2295 tests, so a consumer querying the table lost the flag in
    exactly the case the issue is about while `verdicts()` kept it."""
    con = sqlite3.connect(full_record(tmp_path, True).build())
    try:
        got = dict(con.execute(
            "SELECT metric, provisional FROM verdicts "
            "WHERE metric IN ('intake_floor', 'energy_availability')"))
        assert got and all(v == 1 for v in got.values()), got
    finally:
        con.close()


def test_a_finished_fortnight_says_final_rather_than_nothing(tmp_path):
    """`False`, not `None`. A consumer must be able to tell "checked, and
    final" from "never checked", and a bare `or None` deletes the negative."""
    got = {r["metric"]: r for r in nutrition(tmp_path, False).verdicts()}
    assert got["intake_floor"]["provisional"] is False, got["intake_floor"]


def test_a_partial_claim_is_not_outvoted_by_a_source_that_did_not_know(tmp_path):
    """`coverage` is not in `NON_QUANTITY_FIELDS`, so two sources disagreeing
    about it resolve by the precedence ladder - and a watch that syncs steps
    and calls the day `full` beat a nutrition app's lunchtime `partial`. That
    is the incident losing a contest it should never have entered: a claim of
    openness is not a competing measurement, and one source saying "there is
    more to come" is not refuted by another not knowing it."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsteps_floor = 8000\n'
        "[resolution]\nsource_order = ['watch', 'app']\n", encoding="utf-8")
    rows = [day(f"2030-05-{d:02d}", coverage="full") for d in range(6, 12)]
    rows.append(day("2030-05-12", coverage="full", source="watch"))
    rows.append(day("2030-05-12", coverage=PARTIAL, source="app"))
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    v = Vitai(root)
    canonical = [r for r in v.canonical("daily") if r["date"] == "2030-05-12"]
    assert canonical[0]["coverage"] == "full", "the ladder picked the watch"
    got = steps_rows(v)
    assert got and all(r["provisional"] is True for r in got), (
        "and the app's claim still counts")


def test_the_rhr_row_carries_it_too(tmp_path):
    """Covered by nothing on the first pass: the fixtures read steps and the
    corpus witness is all sleep, so reverting the rhr call site passed the
    entire suite."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nrhr_baseline = 45\n',
        encoding="utf-8")
    rows = [day(f"2030-05-{d:02d}", rhr=52) for d in range(6, 12)]
    rows.append(day("2030-05-12", rhr=52, coverage=PARTIAL))
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = [r for r in Vitai(root).verdicts() if r["metric"] == "rhr"]
    assert got and all(r["provisional"] is True for r in got), got


def test_the_sleep_row_carries_it_too(tmp_path):
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsleep_floor_h = 7.0\n',
        encoding="utf-8")
    rows = [day(f"2030-05-{d:02d}", sleep_h=6.0) for d in range(6, 12)]
    rows.append(day("2030-05-12", sleep_h=6.0, coverage=PARTIAL))
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = [r for r in Vitai(root).verdicts() if r["metric"] == "sleep"]
    assert got and all(r["provisional"] is True for r in got), got
