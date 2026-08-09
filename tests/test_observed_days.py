"""A mean over how many? (#93, ask 2)

Contract 29 added `window_days` because "a statistic with no stated population
is half an answer and the missing half is the misleading one". That was the
DENOMINATOR. The numerator was never published, and the same sentence applies
again: a `sleep` average carrying `window_days: 7` is indistinguishable from an
average of one Tuesday.

The shipped corpus publishes exactly that. `yasmin` has weeks whose sleep
average is judged against a floor on ONE logged night, rendering identically to
a week with seven. In the rollup, three logged step days out of seven print as
"Steps 12,000/day avg - floor met", with a coverage line underneath saying
"daily: 7" that actively reinforces the wrong reading.

The issue's own phrasing: "no unaccounted efforts" becomes "no unaccounted
efforts across 78 per cent coverage", which is a different and honest claim.

NO THRESHOLD ANYWHERE IN IT, which is the part most likely to be added later
and should not be. The engine does not decide how thin is too thin - that
number would have no published basis, and this repo has been bitten twice by
cutoffs it invented (G85). It states the fraction and lets the reader judge.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.config import Config
from vitai.db import VERDICT_KEYS
from vitai.report import build_report, over_days
from vitai.verdicts import AVERAGE

PERSONAS = Path(__file__).resolve().parent / "fixtures" / "personas"
TODAY = date(2030, 5, 7)


def daily(day: str, **kw) -> dict:
    return {"date": day, "steps": None, "rhr": None, "sleep_h": None,
            "note": None, "source": "manual", **kw}


def record(tmp_path: Path, rows: list[dict], toml: str) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


# --- the phrase ----------------------------------------------------------------

def test_it_says_the_fraction():
    assert over_days(3, 7) == " over 3 of the last 7 days"


def test_it_is_silent_when_the_window_is_complete():
    """A phrase on every line is a phrase nobody reads. The marked minority is
    legible precisely because the unmarked majority is quiet."""
    assert over_days(7, 7) == ""
    assert over_days(8, 7) == ""


def test_it_says_nothing_when_there_is_nothing():
    """Zero observed days produces no line at all upstream, so the phrase has
    no sentence to attach to."""
    assert over_days(0, 7) == ""


def test_it_carries_no_adjective_and_no_verdict():
    """The engine has no published basis for where thin begins. It states the
    fraction and stops - anything else is a cutoff it invented."""
    for observed in range(1, 7):
        phrase = over_days(observed, 7)
        for word in ("sparse", "thin", "few", "unreliable", "only", "just",
                     "insufficient", "poor"):
            assert word not in phrase, (observed, phrase)


# --- the prose -------------------------------------------------------------

def test_three_logged_days_of_seven_no_longer_read_as_a_week():
    """The motivating render. An athlete who walked 12,000 on three days and
    logged nothing on four was told a daily floor was met, in a sentence
    identical to the one a full week produces."""
    rows = [daily(f"2030-05-{d:02d}", steps=12000) for d in (1, 2, 3)]
    rows += [daily(f"2030-05-{d:02d}", rhr=50) for d in (4, 5, 6, 7)]
    out = build_report(Config(steps_floor=8000), [], rows, [], today=TODAY)
    line = next(ln for ln in out.splitlines() if "Steps" in ln and "avg" in ln)
    assert "over 3 of the last 7 days" in line, line
    assert "floor met" in line, "the verdict itself is unchanged"


def test_a_complete_week_reads_exactly_as_it_did():
    rows = [daily(f"2030-05-{d:02d}", steps=12000) for d in range(1, 8)]
    out = build_report(Config(steps_floor=8000), [], rows, [], today=TODAY)
    line = next(ln for ln in out.splitlines() if "Steps" in ln and "avg" in ln)
    assert "of the last" not in line, line


def test_the_sleep_floor_says_it_too():
    rows = [daily(f"2030-05-{d:02d}", sleep_h=5.0) for d in (1, 2)]
    rows += [daily(f"2030-05-{d:02d}", steps=9000) for d in (3, 4, 5, 6, 7)]
    out = build_report(Config(sleep_floor_h=7.0), [], rows, [], today=TODAY)
    line = next(ln for ln in out.splitlines() if "Sleep" in ln)
    assert "over 2 of the last 7 days" in line, line


# --- the machine-readable half ----------------------------------------------

def test_every_average_carries_its_numerator(tmp_path):
    rows = [daily(f"2030-05-{d:02d}", steps=12000, sleep_h=5.0, rhr=50)
            for d in (1, 2, 3)]
    rows += [daily(f"2030-05-{d:02d}") for d in (4, 5, 6, 7)]
    v = record(tmp_path, rows,
               "[tripwires]\nsteps_floor = 8000\nsleep_floor_h = 7.0\n"
               "rhr_baseline = 45\n")
    averages = [r for r in v.verdicts() if r.get("statistic") == AVERAGE]
    assert averages
    for row in averages:
        assert row["observed_days"] == 3, row
        assert row["window_days"] == 7, row


def test_the_corpus_publishes_a_weekly_average_of_one_night():
    """Against the shipped record rather than a fixture written to show it.
    This is what the field is for: the row renders like a week and is not one."""
    v = Vitai(PERSONAS / "yasmin")
    thin = [r for r in v.verdicts()
            if r.get("statistic") == AVERAGE and r.get("observed_days") == 1]
    assert thin, "yasmin has weekly averages built from a single day"
    assert thin[0]["window_days"] == 7
    assert thin[0]["value"] is not None, "and it is judged, not refused"


def test_a_judgement_is_unchanged_by_knowing_the_numerator(tmp_path):
    """It reports the denominator; it does not decide anything with it. A
    verdict that moved would be a threshold nobody published."""
    rows = [daily(f"2030-05-{d:02d}", steps=12000) for d in (1, 2, 3)]
    rows += [daily(f"2030-05-{d:02d}") for d in (4, 5, 6, 7)]
    v = record(tmp_path, rows, "[tripwires]\nsteps_floor = 8000\n")
    steps = [r for r in v.verdicts() if r["metric"] == "steps"]
    assert steps and all(r["verdict"] == "on_target" for r in steps), steps


def test_it_reaches_the_read_model(tmp_path):
    """A column, not just an API key - the SQL consumer and the API consumer
    see one answer."""
    rows = [daily(f"2030-05-{d:02d}", steps=12000) for d in (1, 2, 3)]
    rows += [daily(f"2030-05-{d:02d}") for d in (4, 5, 6, 7)]
    v = record(tmp_path, rows, "[tripwires]\nsteps_floor = 8000\n")
    con = sqlite3.connect(v.build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(verdicts)")]
        assert "observed_days" in cols
        got = con.execute(
            "SELECT observed_days FROM verdicts WHERE metric = 'steps'"
        ).fetchall()
        assert got and all(row[0] == 3 for row in got), got
    finally:
        con.close()


def test_it_sits_beside_the_denominator_in_the_column_order():
    """Appended, never inserted, and next to the field it completes."""
    assert VERDICT_KEYS[-3:] == ["window_days", "observed_days", "answers"]


def test_a_refusal_carries_no_numerator(tmp_path):
    """`observed_days` describes a value. A row with no value has no
    population to state, and filling it would be describing nothing."""
    rows = [daily(f"2030-05-{d:02d}", steps=12000) for d in (1, 2, 3)]
    v = record(tmp_path, rows, "[tripwires]\nsteps_floor = 8000\n")
    for row in v.verdicts():
        if row.get("value") is None:
            assert row.get("observed_days") is None, row


def test_no_threshold_was_smuggled_in_with_it():
    """The part most likely to be added later and most likely to be wrong.
    Nothing in the engine may branch on how many days were observed - that
    would be a cutoff with no published basis."""
    src = Path(__file__).resolve().parents[1] / "src" / "vitai"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        body = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))
        for pattern in ("observed_days <", "observed_days >", "observed_days ==",
                        "observed_days >=", "observed_days <="):
            assert pattern not in body, f"{path.name}: {pattern}"
