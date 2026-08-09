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
    would be a cutoff with no published basis.

    PARSED, NOT GREPPED. The first version searched for five literal spellings
    of `observed_days <`, which misses the natural one a consumer of the row
    dict would write - `row["observed_days"] < 3` - and every alias, every
    reversed operator and every missing space. A guard that a rename defeats
    is a guard that reads as coverage.
    """
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "vitai"
    offenders = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            # ORDERING ONLY. `observed_days is not None` is a presence check -
            # in fact the totality rule that a refusal carries no population -
            # and forbidding it would forbid the guard that keeps this field
            # honest. What must never appear is a comparison that decides
            # something from HOW MANY.
            if not any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
                       for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                if _names_the_count(side):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


def _names_the_count(node) -> bool:
    """Does this expression read `observed_days`, however it is spelled?"""
    import ast

    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "observed_days":
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == "observed_days":
            return True
        if (isinstance(sub, ast.Subscript)
                and isinstance(sub.slice, ast.Constant)
                and sub.slice.value == "observed_days"):
            return True
    return False


def test_the_ast_guard_can_actually_fail():
    """A guard on the guard. The grep it replaces passed for every spelling a
    real consumer would use, so this proves the parser sees them."""
    import ast

    for snippet in ('if observed_days < 3: pass',
                    'if observed_days<3: pass',
                    'if 3 > observed_days: pass',
                    'if row["observed_days"] < 3: pass',
                    'if r.observed_days >= 7: pass'):
        tree = ast.parse(snippet)
        found = any(
            _names_the_count(side)
            for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
                    for op in node.ops)
            for side in [node.left, *node.comparators])
        assert found, snippet


def test_the_guard_allows_the_totality_rule_it_must_not_forbid():
    """`observed_days is not None` is a presence check, and one of them is the
    rule that a refusal carries no population. A guard that banned it would
    have to be turned off, and a guard that is off is not a guard."""
    import ast

    tree = ast.parse("if verdict == NODATA and observed_days is not None: pass")
    ordering = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)
                and any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
                        for op in n.ops)]
    assert not ordering


# --- the sites the first version got wrong -----------------------------------

def test_easy_hr_counts_days_and_not_sessions(tmp_path):
    """SESSIONS ARE NOT MERGED PER DATE - only `daily` is - so counting rows
    here counted two runs on one Tuesday as two days. A week with doubles
    published `observed_days: 9` against `window_days: 7`, which is not a thin
    claim but a broken one, in a column whose whole contract is "how many days
    of the stated window actually held the metric".

    The shipped corpus never runs twice in a day, which is why no fixture
    witnessed it."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\neasy_hr_cap = 150\n',
        encoding="utf-8")
    runs = []
    for day in range(1, 8):                       # a run every day...
        runs.append({"date": f"2030-05-{day:02d}", "type": "run",
                     "duration_s": 1800, "avg_hr": 140, "source": "watch"})
    for day in (1, 2):                            # ...and a second on two
        runs.append({"date": f"2030-05-{day:02d}", "type": "run",
                     "duration_s": 900, "avg_hr": 145, "source": "watch",
                     "start_time": "18:00"})
    (root / "data" / "sessions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8")

    rows = {r["week"]: r for r in Vitai(root).verdicts()
            if r["metric"] == "easy_hr"}
    assert rows
    # 2030-05-01 is a Wednesday, so the first ISO week holds days 1-5 - five
    # DAYS carrying the metric, and SEVEN sessions once the two doubles are
    # counted. Row-counting reported 7 of 7; day-counting reports 5 of 7.
    first = rows["2030-04-29"]
    assert first["observed_days"] == 5, first
    assert sum(r["observed_days"] for r in rows.values()) == 7
    for row in rows.values():
        assert row["observed_days"] <= row["window_days"], row


def test_no_average_ever_claims_more_days_than_its_window():
    """The invariant the session count broke, over the whole corpus."""
    for persona in sorted(p for p in PERSONAS.iterdir()
                          if (p / "vitai.toml").exists()):
        for row in Vitai(persona).verdicts():
            if row.get("observed_days") is None:
                continue
            assert row["observed_days"] <= row["window_days"], (persona.name, row)


def test_the_safety_floors_carry_it_too(tmp_path):
    """The RED-S intake and protein floors average over FOURTEEN days and fire
    at seven, so observed genuinely varies 7..14 - and they shipped without the
    numerator, which made the contract note's "every average the engine
    publishes" false at the two rows where it matters most."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    rows = [daily(f"2030-05-{d:02d}", kcal_in=1200) for d in range(1, 9)]
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps({**r, "kcal_in": 1200}) + "\n" for r in rows),
        encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        json.dumps({"date": "2030-05-01", "kg": 70.0, "source": "scale"}) + "\n",
        encoding="utf-8")

    floors = [r for r in Vitai(root).verdicts()
              if r["metric"] in ("intake_floor", "protein_floor")
              and r.get("statistic") == AVERAGE]
    assert floors, "the intake floor fires from seven logged days"
    for row in floors:
        assert row["observed_days"] is not None, row
        assert row["window_days"] == 14, row


def test_every_average_emitting_site_passes_a_numerator():
    """The completeness half, over the corpus rather than over a fixture that
    happens to reach three of six sites."""
    seen = set()
    for persona in sorted(p for p in PERSONAS.iterdir()
                          if (p / "vitai.toml").exists()):
        for row in Vitai(persona).verdicts():
            if row.get("statistic") == AVERAGE and row.get("value") is not None:
                seen.add(row["metric"])
                assert row["observed_days"] is not None, (persona.name, row)
    assert len(seen) >= 4, seen


def test_a_refusal_is_refused_a_numerator():
    """Held where every row is built, with the other totality rules, rather
    than trusted at each caller. The first version had a test for this whose
    fixture produced no refusals at all, so the loop body never ran."""
    import pytest

    from vitai.verdicts import _row

    with pytest.raises(ValueError, match="describes nothing"):
        _row("2030-05-06", "steps", None, None, "no_data",
             reason="no_input", observed_days=3)


def test_the_rhr_tripwire_says_it_too():
    """An inconsistent surface is worse than a uniformly silent one: the reader
    learns the phrase means something and then trusts its absence. This line
    sat directly above two marked ones, averaging the same 7-day window."""
    rows = [daily(f"2030-05-{d:02d}", rhr=62) for d in (1, 2, 3)]
    rows += [daily(f"2030-05-{d:02d}", steps=9000) for d in (4, 5, 6, 7)]
    out = build_report(Config(rhr_baseline=50), [], rows, [], today=TODAY)
    line = next(ln for ln in out.splitlines() if "Resting HR" in ln)
    assert "over 3 of the last 7 days" in line, line
