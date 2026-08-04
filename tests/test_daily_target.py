"""A daily nutrition target, and which number a metric is judged against.

Two decisions land together (#191, #199). A declared goal target supersedes
the threshold for that metric while it is in force, and the safety floor
survives underneath as a gate declaring a target cannot switch off.

`goals` and `verdicts` were two scoring systems that never met: one held a
target the athlete chose and the other a floor he did not, they were computed
by different code, and the shipped demo had them disagreeing about steps.
"""

from __future__ import annotations

import json
import sqlite3

from vitai.api import Vitai, init
from vitai.safety import INTAKE_FLOOR_KCAL
from vitai.schema import CURRENT_GENERATION, KEYS, validate_record

_made = [0]


def a_goal(**kw):
    g = {k: None for k in KEYS["goals"]}
    g.update({"date": "2030-06-01", "slug": "walk", "title": "walk",
              "metric": "steps", "dataset": "daily", "target": 12000,
              "policy": "monotonic", "period": "daily", "tracker": "sum",
              "lifecycle_status": "active", "polarity": "floor",
              "_gen": CURRENT_GENERATION["goals"]})
    g.update(kw)
    return g


def a_record(tmp_path, goal, toml="[tripwires]\nsteps_floor = 8000\n", **fields):
    _made[0] += 1
    root = init(tmp_path / f"c{_made[0]}")
    (root / "vitai.toml").write_text(toml, encoding="utf-8")
    (root / "data" / "goals.jsonl").write_text(
        json.dumps(goal) + "\n", encoding="utf-8")

    def a_day(d):
        row = {k: None for k in KEYS["daily"]}
        row.update({"date": f"2030-06-{d:02d}", "source": "app",
                    "_gen": CURRENT_GENERATION["daily"], **fields})
        return row
    (root / "data" / "daily.jsonl").write_text("\n".join(
        json.dumps(a_day(d)) for d in range(1, 15)) + "\n", encoding="utf-8")
    return root


def verdict(root, metric):
    rows = [r for r in Vitai(root, on="2030-06-14").verdicts()
            if r["metric"] == metric]
    return rows[-1]


# --- the declared target wins, in the unit it was declared in ----------------

def test_a_daily_target_supersedes_the_threshold(tmp_path):
    """A threshold is a floor nobody chose; a target is an aim he did."""
    root = a_record(tmp_path, a_goal(target=12000), steps=9000)
    got = verdict(root, "steps")
    assert (got["target"], got["verdict"], got["goal"]) == (12000.0, "behind",
                                                            "walk")


def test_it_supersedes_downward_too(tmp_path):
    """His own lower aim is still the aim. The engine does not keep judging
    him against a default he has spoken about and replaced."""
    root = a_record(tmp_path, a_goal(target=5000), steps=9000)
    got = verdict(root, "steps")
    assert (got["target"], got["verdict"]) == (5000.0, "on_target")


def test_a_period_total_does_not_supersede_a_per_day_floor(tmp_path):
    """THE ARITHMETIC THE DECISION COULD NOT STATE, because it was about
    precedence. These rows compare a per-DAY average against a per-day floor;
    a weekly target is a period TOTAL. Swapping one in compared 9739 steps a
    day against 77000 a week and called it behind at 85% of target - trading a
    disagreement between two systems for a wrong answer from one.

    A period-total goal is already scored, by `goal_progress`.
    """
    root = a_record(tmp_path, a_goal(target=77000, period="weekly"),
                    steps=9000)
    got = verdict(root, "steps")
    assert got["target"] == 8000.0, "the weekly total was used as a daily floor"
    assert got["goal"] == "walk", "the linkage is still reported"


def test_a_metric_nobody_declared_still_uses_the_default(tmp_path):
    root = a_record(tmp_path, a_goal(metric="sleep_h", target=8,
                                     slug="sleep-goal"), steps=9000)
    got = verdict(root, "steps")
    assert got["target"] == 8000.0 and got["goal"] is None


# --- the floor underneath is not suppressible --------------------------------

def test_a_target_under_the_floor_does_not_switch_the_floor_off(tmp_path):
    """The floors are computed on a path that never consults goals, which is
    what makes them non-suppressible: a low target changes what he is scored
    against and cannot silence the sentence saying the floor was crossed."""
    root = a_record(tmp_path, a_goal(metric="kcal_in", target=1300,
                                     polarity="ceiling", slug="cut"),
                    kcal_in=790, protein_g=40)
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["weight"]}, "date": "2030-06-01",
         "kg": 80.0, "source": "scale",
         "_gen": CURRENT_GENERATION["weight"]}) + "\n", encoding="utf-8")
    assert verdict(root, "intake_floor")["verdict"] == "behind"
    assert verdict(root, "protein_floor")["verdict"] == "behind"


def test_a_target_below_the_floor_is_refused_at_declaration():
    """Otherwise this is a new way to declare an unmeetable number and be told
    you are behind it every period - alarm fatigue through the front door."""
    problems = validate_record("goals", a_goal(
        metric="kcal_in", target=INTAKE_FLOOR_KCAL - 400, polarity="ceiling"))
    assert problems and "safety floor" in problems[0]
    assert validate_record("goals", a_goal(
        metric="kcal_in", target=INTAKE_FLOOR_KCAL + 600,
        polarity="ceiling")) == []


def test_the_protein_half_is_not_guessed_at():
    """The energy floor is a constant, so a daily target below it is refusable
    here. The protein floor is per kilogram, and validation sees one record
    with no record around it, so a grams-per-day target cannot be compared
    against it without the athlete's weight."""
    assert validate_record("goals", a_goal(metric="protein_g", target=10)) == []


# --- and a daily bucket does not mint a milestone a quarter ------------------

def test_a_daily_period_mints_no_milestones(tmp_path):
    """Milestones key on (slug, bucket, fraction) with four fractions, so a
    daily period mints four a day - 1460 a year for one goal, measured. A
    quarter of the way through today is not an achievement, and burying the
    real ones under thousands of them is alarm fatigue again."""
    root = a_record(tmp_path, a_goal(metric="protein_g", target=150,
                                     slug="protein"), protein_g=160)
    Vitai(root, on="2030-06-14").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        assert con.execute("SELECT count(*) FROM milestones").fetchone()[0] == 0
    finally:
        con.close()


def test_a_weekly_period_still_mints_them(tmp_path):
    root = a_record(tmp_path, a_goal(metric="protein_g", target=150,
                                     slug="protein", period="weekly"),
                    protein_g=160)
    Vitai(root, on="2030-06-14").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        assert con.execute("SELECT count(*) FROM milestones").fetchone()[0] > 0
    finally:
        con.close()
