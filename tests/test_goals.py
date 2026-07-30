"""Increment 1: goals as data, contribution, and temporal validity.

Synthetic data only (public repo: no real measurements). The dates are in 2030
for the same reason the rest of the suite uses them - a fictional athlete.

The three tests that matter most here are the ones guarding a property rather
than a feature: `test_editing_a_target_today_leaves_past_verdicts_alone` and
`test_past_week_keeps_the_threshold_in_force_then` are the G14/G20 regression
(working rule 6, "value-history stability"), and
`test_milestone_does_not_fire_on_unbudgeted_volume` is what stops the engine
congratulating an athlete for the behaviour most likely to injure them.
"""

import json
from pathlib import Path

from vitai.config import Config, overlay
from vitai.contributions import compute_contributions, goal_progress
from vitai.jsonl import heads, load
from vitai.policy import LOOSENED, TIGHTENED, plan_churn, state
from vitai.schema import validate_record, verification_of
from vitai.verdicts import compute_verdicts


def write(p: Path, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def goal(slug="steps", date="2030-04-01", metric="steps", target=10000,
         policy="monotonic", **kw):
    rec = {
        "date": date, "slug": slug, "title": f"{slug} goal", "metric": metric,
        "dataset": None, "session_type": None,
        "tracker": None, "target": target, "policy": policy, "guard_pct": None,
        "period": "weekly", "on_period_end": "reset", "deadline": None,
        "status": "active", "motivator": None, "rationale": None,
        "on_success": None, "on_miss": None, "accountability": None,
        "set_by": "athlete", "reason": None, "note": None,
    }
    rec.update(kw)
    return rec


def threshold(key="steps_floor", date="2030-04-01", value=9000, **kw):
    rec = {"date": date, "key": key, "value": value, "change_kind": "change",
           "set_by": "athlete", "reason": None, "note": None}
    rec.update(kw)
    return rec


def daily(date, steps=None, **kw):
    rec = {"date": date, "steps": steps, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "hip_pain": None, "alcohol": None, "note": None}
    rec.update(kw)
    return rec


def session(date, type="run", distance_km=None, **kw):
    rec = {"date": date, "type": type, "distance_km": distance_km,
           "duration_s": None, "avg_hr": None, "max_hr": None, "cadence": None,
           "kcal": None, "location": None, "rpe": None, "note": None}
    rec.update(kw)
    return rec


# ---- schema ------------------------------------------------------------------

def test_valid_goal_line_passes():
    assert validate_record("goals", goal()) == []


def test_guarded_goal_requires_guard_pct():
    problems = validate_record("goals", goal(policy="guarded"))
    assert any("guard_pct" in p for p in problems)


def test_external_goal_requires_a_tracker():
    problems = validate_record("goals", goal(metric="external", target=None))
    assert any("tracker" in p for p in problems)
    assert validate_record(
        "goals", goal(metric="external", target=None, tracker="a segment app")) == []


def test_active_internal_goal_needs_a_target():
    problems = validate_record("goals", goal(target=None))
    assert any("target" in p for p in problems)
    # ...but an abandoned one does not - history keeps goals that never had one.
    assert validate_record("goals", goal(target=None, status="abandoned")) == []


def test_closed_vocabularies_are_enforced():
    assert any("policy" in p for p in validate_record("goals", goal(policy="vibes")))
    assert any("status" in p for p in validate_record("goals", goal(status="ongoing")))
    assert any("change_kind" in p
               for p in validate_record("thresholds", threshold(change_kind="fixed")))


def test_threshold_and_achievement_shapes():
    assert validate_record("thresholds", threshold()) == []
    assert validate_record("achievements", {
        "date": "2030-05-01", "title": "first 10k", "goal": "running",
        "source": "athlete", "note": None}) == []


# ---- slug-scoped supersedes + heads ------------------------------------------

def test_same_slug_append_is_an_edit_and_keeps_both_lines(tmp_path):
    write(tmp_path / "goals.jsonl", [
        goal(date="2030-04-01", target=10000),
        goal(date="2030-05-01", target=12000),
    ])
    recs = load(tmp_path, "goals")
    assert len(recs) == 2, "an edit keeps the history; it is not a replacement"
    assert heads(recs, "goals")["steps"]["target"] == 12000


def test_slug_scoped_supersedes_drops_the_corrected_line(tmp_path):
    write(tmp_path / "goals.jsonl", [
        goal(date="2030-04-01", target=10000),
        goal(date="2030-05-01", target=1200),                     # typo
        goal(date="2030-05-01", target=12000, supersedes="steps@2030-05-01"),
    ])
    recs = load(tmp_path, "goals")
    assert len(recs) == 2
    assert [r["target"] for r in recs] == [10000, 12000]


def test_supersedes_is_scoped_per_slug(tmp_path):
    # A correction to one goal must not touch a same-dated line of another.
    write(tmp_path / "goals.jsonl", [
        goal(slug="steps", date="2030-04-01", target=10000),
        goal(slug="running", date="2030-04-01", metric="distance_km", target=20),
        goal(slug="steps", date="2030-04-01", target=11000,
             supersedes="steps@2030-04-01"),
    ])
    recs = load(tmp_path, "goals")
    assert {r["slug"] for r in recs} == {"steps", "running"}
    assert heads(recs, "goals")["steps"]["target"] == 11000
    assert heads(recs, "goals")["running"]["target"] == 20


# ---- as-of reconstruction (G20) ----------------------------------------------

def test_state_returns_the_policy_in_force_then():
    goals = [goal(date="2030-04-01", target=10000),
             goal(date="2030-05-15", target=12000)]
    thresholds = [threshold(date="2030-04-01", value=9000),
                  threshold(date="2030-05-15", value=8000)]
    assert state(goals, thresholds, "2030-05-01").goal("steps")["target"] == 10000
    assert state(goals, thresholds, "2030-05-01").threshold("steps_floor") == 9000
    assert state(goals, thresholds, "2030-06-01").goal("steps")["target"] == 12000
    assert state(goals, thresholds, "2030-06-01").threshold("steps_floor") == 8000


def test_a_goal_is_invisible_before_it_was_declared():
    goals = [goal(date="2030-05-01")]
    assert state(goals, [], "2030-04-30").goals == ()
    assert state(goals, [], "2030-05-01").goal("steps") is not None


def test_state_takes_effect_on_the_line_date():
    goals = [goal(date="2030-04-01", target=10000),
             goal(date="2030-05-01", target=12000)]
    assert state(goals, [], "2030-04-30").goal("steps")["target"] == 10000
    assert state(goals, [], "2030-05-01").goal("steps")["target"] == 12000


def test_overlay_prefers_dated_thresholds_over_the_toml():
    cfg = Config(steps_floor=9000, easy_hr_cap=150)
    eff = overlay(cfg, {"steps_floor": 11000})
    assert eff.steps_floor == 11000
    assert eff.easy_hr_cap == 150, "an unrelated toml threshold survives"


# ---- G14 regression: editing today never re-scores the past -------------------

def _week_rows(rows, metric):
    return {r["week"]: r["verdict"] for r in rows if r["metric"] == metric}


def test_past_week_keeps_the_threshold_in_force_then():
    """The audit-trail killer, guarded: lowering a floor cannot turn an old
    miss into a hit on the next rebuild."""
    days = [daily(f"2030-04-{d:02d}", steps=8000) for d in range(1, 8)]
    days += [daily(f"2030-06-{d:02d}", steps=8000) for d in range(3, 10)]
    cfg = Config()
    strict = [threshold(date="2030-04-01", value=9000)]
    before = _week_rows(compute_verdicts(cfg, [], days, [], thresholds=strict), "steps")
    assert before["2030-04-01"] == "behind"

    # The athlete lowers the floor in June. April must not move.
    loosened = strict + [threshold(date="2030-06-01", value=7000)]
    after = _week_rows(compute_verdicts(cfg, [], days, [], thresholds=loosened), "steps")
    assert after["2030-04-01"] == "behind", "April was re-scored by a June edit"
    assert after["2030-06-03"] == "on_target", "June should use the new floor"


def test_editing_a_target_today_leaves_past_verdicts_alone():
    days = [daily(f"2030-04-{d:02d}", steps=8000) for d in range(1, 8)]
    cfg = Config()
    thresholds = [threshold(date="2030-04-01", value=9000)]
    original = compute_verdicts(cfg, [], days, [], thresholds=thresholds)
    edited = compute_verdicts(cfg, [], days, [],
                              thresholds=thresholds + [threshold(
                                  date="2030-05-01", value=5000)])
    past = [r for r in original if r["week"] == "2030-04-01"]
    still = [r for r in edited if r["week"] == "2030-04-01"]
    assert past == still


def test_verdicts_carry_goal_linkage():
    days = [daily(f"2030-04-{d:02d}", steps=9500) for d in range(1, 8)]
    rows = compute_verdicts(Config(steps_floor=9000), [], days, [],
                            goals=[goal(date="2030-04-01")])
    steps = [r for r in rows if r["metric"] == "steps"]
    assert steps and all(r["goal"] == "steps" for r in steps)


# ---- contribution fan-out (G18) ----------------------------------------------

def test_one_event_fans_out_to_every_goal_it_touches():
    """The increment's point: one run, two goals, two different verdicts."""
    goals = [
        goal(slug="calories", metric="kcal", target=2000, policy="monotonic"),
        goal(slug="running", metric="distance_km", target=20, policy="guarded",
             guard_pct=0.1),
    ]
    # Four prior weeks establish a ~10 km/week running baseline, and the
    # athlete has already run their planned 10 km this week - so the week's
    # budget is spent before the unplanned run happens.
    history = [session(f"2030-04-{d:02d}", distance_km=10.0, kcal=600)
               for d in (2, 9, 16, 23)]
    planned = session("2030-04-29", distance_km=11.0, kcal=600)  # base + the 10%
    big_run = session("2030-04-30", distance_km=25.0, kcal=1500)
    contributions, _ = compute_contributions(
        goals, [], [], history + [planned, big_run])

    on_the_day = {c["goal"]: c for c in contributions if c["date"] == "2030-04-30"}
    assert set(on_the_day) == {"calories", "running"}
    # The same event, two honest and opposite verdicts. This is the increment.
    assert on_the_day["calories"]["contribution"] == "advances"
    assert on_the_day["calories"]["counted"] == 1500
    assert on_the_day["running"]["contribution"] == "unbudgeted"
    assert on_the_day["running"]["counted"] == 0.0, (
        "volume beyond the ramp guard must not advance a guarded goal")


def test_guarded_goal_credits_volume_within_the_ramp():
    goals = [goal(slug="running", metric="distance_km", target=20,
                  policy="guarded", guard_pct=0.2)]
    history = [session(f"2030-04-{d:02d}", distance_km=10.0)
               for d in (2, 9, 16, 23)]
    modest = session("2030-04-30", distance_km=11.0)   # +10%, inside a 20% guard
    contributions, _ = compute_contributions(goals, [], [], history + [modest])
    last = [c for c in contributions if c["date"] == "2030-04-30"][0]
    assert last["contribution"] == "advances"
    assert last["counted"] == 11.0


def test_guarded_goal_splits_a_straddling_event():
    goals = [goal(slug="running", metric="distance_km", target=100,
                  policy="guarded", guard_pct=0.0)]
    history = [session(f"2030-04-{d:02d}", distance_km=10.0)
               for d in (2, 9, 16, 23)]
    straddle = session("2030-04-30", distance_km=14.0)  # budget is 10.0
    contributions, _ = compute_contributions(goals, [], [], history + [straddle])
    last = [c for c in contributions if c["date"] == "2030-04-30"][0]
    assert last["contribution"] == "partial"
    assert last["counted"] == 10.0


def test_guard_cannot_fire_without_a_baseline():
    goals = [goal(slug="running", metric="distance_km", target=20,
                  policy="guarded", guard_pct=0.1)]
    first = session("2030-04-02", distance_km=15.0)
    contributions, _ = compute_contributions(goals, [], [], [first])
    assert contributions[0]["contribution"] == "advances", (
        "there is no ramp to exceed in the first week of a goal")


def test_a_goal_can_be_scoped_to_one_dataset_and_session_type():
    """`distance_km` means walking on daily and running on sessions."""
    running = goal(slug="running", metric="distance_km", target=100,
                   dataset="sessions", session_type="run")
    days = [daily("2030-04-02", distance_km=8.0)]
    runs = [session("2030-04-02", type="run", distance_km=5.0),
            session("2030-04-03", type="walk", distance_km=4.0)]
    contributions, _ = compute_contributions([running], [], days, runs)
    assert [c["counted"] for c in contributions] == [5.0], (
        "only the run counts: not the commute, not the walk")


def test_external_goals_are_tracked_but_never_auto_verdicted():
    goals = [goal(slug="segment", metric="external", target=None,
                  tracker="a segment app")]
    contributions, _ = compute_contributions(
        goals, [], [daily("2030-04-02", steps=12000)], [])
    assert contributions == []
    rows = goal_progress(goals, [], [daily("2030-04-02", steps=12000)], [],
                         "2030-04-30")
    assert rows[0]["tracker"] == "a segment app"


def test_contributions_are_judged_against_the_goal_of_the_day():
    goals = [goal(date="2030-05-01", target=10000)]
    days = [daily("2030-04-20", steps=9000), daily("2030-05-02", steps=9000)]
    contributions, _ = compute_contributions(goals, [], days, [])
    assert [c["date"] for c in contributions] == ["2030-05-02"], (
        "a day before the goal existed cannot contribute to it")


# ---- milestones ---------------------------------------------------------------

def test_milestone_fires_on_genuine_progress():
    goals = [goal(slug="steps", metric="steps", target=10000, period="none")]
    days = [daily("2030-04-01", steps=3000), daily("2030-04-02", steps=3000)]
    _, milestones = compute_contributions(goals, [], days, [])
    assert [m["fraction"] for m in milestones] == [0.25, 0.5]


def test_milestone_does_not_fire_on_unbudgeted_volume():
    """A 30 km week off a 12 km base mints nothing."""
    goals = [goal(slug="running", metric="distance_km", target=40,
                  policy="guarded", guard_pct=0.1, period="none")]
    history = [session(f"2030-04-{d:02d}", distance_km=3.0)
               for d in (2, 9, 16, 23)]
    _, before = compute_contributions(goals, [], [], history)
    blowout = session("2030-04-30", distance_km=30.0)
    _, after = compute_contributions(goals, [], [], history + [blowout])
    assert after == before, "unbudgeted volume minted a milestone"


def test_a_milestone_is_minted_once():
    goals = [goal(slug="steps", metric="steps", target=1000, period="none")]
    days = [daily(f"2030-04-{d:02d}", steps=600) for d in range(1, 5)]
    _, milestones = compute_contributions(goals, [], days, [])
    assert len(milestones) == len({m["fraction"] for m in milestones})


# ---- progress math ------------------------------------------------------------

def test_progress_counts_only_what_was_banked():
    goals = [goal(slug="running", metric="distance_km", target=20,
                  policy="guarded", guard_pct=0.1, period="none")]
    history = [session(f"2030-04-{d:02d}", distance_km=5.0) for d in (2, 9, 16, 23)]
    rows = goal_progress(goals, [], [], history + [session("2030-04-30",
                                                           distance_km=25.0)],
                         "2030-04-30")
    row = rows[0]
    assert row["counted"] == 20.0 + 5.5, "banked = the four base weeks + the ramp"
    assert row["unbudgeted"] == 19.5
    assert row["progress_pct"] == 127.5


def test_progress_reports_declaration_and_edit_dates():
    goals = [goal(date="2030-04-01", target=10000),
             goal(date="2030-05-01", target=12000)]
    rows = goal_progress(goals, [], [daily("2030-05-02", steps=9000)], [],
                         "2030-05-02")
    assert rows[0]["declared"] == "2030-04-01"
    assert rows[0]["last_edited"] == "2030-05-01"
    assert rows[0]["target"] == 12000


def test_weekly_period_resets_progress():
    goals = [goal(slug="steps", metric="steps", target=50000, period="weekly")]
    days = [daily("2030-04-01", steps=9000), daily("2030-04-08", steps=7000)]
    rows = goal_progress(goals, [], days, [], "2030-04-08")
    assert rows[0]["counted"] == 7000, "a new week starts from zero"


# ---- churn + the suspiciously-timed edit (G20) --------------------------------

def test_churn_records_an_edit_but_not_the_declaration():
    goals = [goal(date="2030-04-01", target=10000),
             goal(date="2030-05-01", target=12000)]
    rows = plan_churn(goals, [])
    assert len(rows) == 1
    assert rows[0]["edit_no"] == 1 and rows[0]["direction"] == TIGHTENED


def test_a_correction_is_not_churn():
    thresholds = [threshold(date="2030-04-01", value=9000),
                  threshold(date="2030-04-02", value=900,
                            change_kind="correction", reason="dropped a zero")]
    assert plan_churn([], thresholds) == []


def test_loosening_right_after_a_miss_is_flagged():
    days = [daily(f"2030-04-{d:02d}", steps=8000) for d in range(1, 8)]
    thresholds = [threshold(date="2030-03-01", value=9000)]
    verdicts = compute_verdicts(Config(), [], days, [], thresholds=thresholds)
    assert any(r["verdict"] == "behind" for r in verdicts)

    # The floor is lowered three days after that missed week ended.
    loosened = thresholds + [threshold(date="2030-04-10", value=7000)]
    rows = plan_churn([], loosened, verdicts)
    assert len(rows) == 1
    assert rows[0]["direction"] == LOOSENED
    assert rows[0]["suspicious"] is True
    assert rows[0]["unexplained"] is True, "no reason given is the askable case"


def test_a_tightening_after_a_miss_is_not_suspicious():
    days = [daily(f"2030-04-{d:02d}", steps=8000) for d in range(1, 8)]
    thresholds = [threshold(date="2030-03-01", value=9000)]
    verdicts = compute_verdicts(Config(), [], days, [], thresholds=thresholds)
    rows = plan_churn([], thresholds + [threshold(date="2030-04-10", value=11000)],
                      verdicts)
    assert rows[0]["direction"] == TIGHTENED
    assert rows[0]["suspicious"] is False


def test_an_explained_loosening_is_flagged_but_not_unexplained():
    days = [daily(f"2030-04-{d:02d}", steps=8000) for d in range(1, 8)]
    thresholds = [threshold(date="2030-03-01", value=9000)]
    verdicts = compute_verdicts(Config(), [], days, [], thresholds=thresholds)
    rows = plan_churn([], thresholds + [threshold(
        date="2030-04-10", value=7000, reason="calf strain, deloading")], verdicts)
    assert rows[0]["suspicious"] is True
    assert rows[0]["unexplained"] is False


def test_cap_and_floor_loosen_in_opposite_directions():
    floor = plan_churn([], [threshold(key="steps_floor", date="2030-04-01", value=9000),
                            threshold(key="steps_floor", date="2030-05-01", value=8000)])
    cap = plan_churn([], [threshold(key="pain_gate", date="2030-04-01", value=3),
                          threshold(key="pain_gate", date="2030-05-01", value=5)])
    assert floor[0]["direction"] == LOOSENED, "a lowered floor is easier"
    assert cap[0]["direction"] == LOOSENED, "a raised cap is easier"


def test_a_pushed_deadline_is_recorded():
    """That the deadline moved is a FACT and is always recorded.

    This test used to assert `direction == LOOSENED` as well, on any pushed
    deadline whatsoever. That assertion encoded a belief the model has since
    rejected: a date the athlete invented is a direction of travel they may
    revise at no cost to anyone, and reading it as a retreat accuses them of
    gaming a commitment nobody else ever held them to (G86). Whether a push
    reads as a loosening depends on the deadline's HARDNESS, which does not
    exist yet - the assertion is removed here rather than quietly weakened,
    and reinstated for hard deadlines when the field lands.
    """
    goals = [goal(date="2030-04-01", deadline="2030-06-01"),
             goal(date="2030-05-01", deadline="2030-09-01")]
    rows = plan_churn(goals, [])
    assert rows[0]["deadline_pushed"] is True


# ---- determinism --------------------------------------------------------------

def test_same_day_events_with_mixed_null_types_sort():
    """Two sessions on one day, one with a null the other fills in: the
    ordering tiebreak must not try to compare None against a number."""
    goals = [goal(slug="running", metric="distance_km", target=20,
                  dataset="sessions")]
    same_day = [session("2030-04-02", type="run", distance_km=5.0, kcal=300),
                session("2030-04-02", type="gym_a", distance_km=None, kcal=None)]
    contributions, _ = compute_contributions(goals, [], [], same_day)
    assert [c["counted"] for c in contributions] == [5.0]


def test_contributions_are_stable_across_runs():
    goals = [goal(slug="steps"), goal(slug="running", metric="distance_km",
                                      target=20, policy="guarded", guard_pct=0.1)]
    days = [daily(f"2030-04-{d:02d}", steps=9000 + d) for d in range(1, 15)]
    sessions = [session(f"2030-04-{d:02d}", distance_km=float(d)) for d in (3, 10)]
    first = compute_contributions(goals, [], days, sessions)
    second = compute_contributions(goals, [], days, sessions)
    assert first == second


# ---- G86: deadline hardness, and the false accusation it removes --------------

def test_a_pushed_hard_deadline_still_reads_as_a_retreat():
    """Reinstates the assertion removed in the previous commit, now that
    hardness exists to justify it. A race date is externally owned, so moving
    it IS a retreat from something real."""
    goals = [goal(date="2030-04-01", deadline="2030-06-01", deadline_kind="hard"),
             goal(date="2030-05-01", deadline="2030-09-01", deadline_kind="hard")]
    rows = plan_churn(goals, [])
    assert rows[0]["deadline_pushed"] is True
    assert rows[0]["direction"] == LOOSENED
    assert rows[0]["deadline_kind"] == "hard"


def test_a_moved_soft_deadline_is_not_goalpost_moving():
    """THE test for this increment, named for the false positive it kills.

    A self-imposed date is a direction of travel the athlete may revise at no
    cost to anyone. Flagging it accuses them of gaming a commitment nobody
    else ever held them to - and the engine was doing exactly that on a live
    record. The push is still RECORDED; it is only the accusation that goes.
    """
    behind = [{"week": "2030-04-22", "metric": "steps", "verdict": "behind"}]
    goals = [goal(date="2030-04-01", deadline="2030-06-01", deadline_kind="soft"),
             goal(date="2030-05-01", deadline="2031-03-01", deadline_kind="soft")]
    row = plan_churn(goals, [], behind)[0]
    assert row["deadline_pushed"] is True, "the fact is not hidden"
    assert row["direction"] != LOOSENED
    assert row["suspicious"] is False
    assert row["unexplained"] is False


def test_unknown_hardness_records_the_push_without_judging_it():
    """The legacy case: a goal written before the field existed. The engine
    surfaces the move and says it does not know the hardness, rather than
    guessing in either direction (the G89 shape: accumulate, surface, do not
    decide for the athlete)."""
    behind = [{"week": "2030-04-22", "metric": "steps", "verdict": "behind"}]
    goals = [goal(date="2030-04-01", deadline="2030-06-01"),
             goal(date="2030-05-01", deadline="2031-03-01")]
    row = plan_churn(goals, [], behind)[0]
    assert row["deadline_pushed"] is True
    assert row["deadline_kind"] is None
    assert row["suspicious"] is False


def test_a_loosened_target_is_still_flagged_whatever_the_deadline_says():
    """Hardness must not become a way to launder a genuine retreat: the
    TARGET check is independent and still fires."""
    behind = [{"week": "2030-04-22", "metric": "steps", "verdict": "behind"}]
    goals = [goal(date="2030-04-01", target=12000, deadline_kind="soft",
                  deadline="2030-06-01"),
             goal(date="2030-05-01", target=8000, deadline_kind="soft",
                  deadline="2031-03-01")]
    row = plan_churn(goals, [], behind)[0]
    assert row["direction"] == LOOSENED
    assert row["suspicious"] is True


def test_a_goal_anchored_to_a_race_inherits_a_hard_deadline():
    events = [{"date": "2030-01-01", "slug": "spring-10k", "title": "Spring 10k",
               "kind": "competition", "event_date": "2030-06-01", "priority": "a",
               "immovable": True, "place": None, "status": "confirmed",
               "set_by": "athlete", "reason": None, "note": None}]
    goals = [goal(date="2030-04-01", event="spring-10k", deadline=None),
             goal(date="2030-05-01", event="spring-10k", deadline="2030-09-01")]
    rows = plan_churn(goals, [], events=events)
    # The anchor pins the deadline to the fixture, so the goal's own later
    # date does not quietly move it: the organiser owns that day.
    assert rows[0]["deadline_pushed"] is False
    assert rows[0]["deadline_kind"] == "hard"


def test_goal_progress_carries_the_countdown_to_a_hard_date():
    events = [{"date": "2030-01-01", "slug": "spring-10k", "title": "Spring 10k",
               "kind": "competition", "event_date": "2030-06-01", "priority": "a",
               "immovable": True, "place": None, "status": "confirmed",
               "set_by": "athlete", "reason": None, "note": None}]
    goals = [goal(date="2030-04-01", event="spring-10k", deadline=None)]
    row = goal_progress(goals, [], [], [], "2030-05-22", events=events)[0]
    assert row["deadline"] == "2030-06-01"
    assert row["deadline_kind"] == "hard"
    assert row["days_to_deadline"] == 10
    assert row["event"] == "spring-10k"


# ---- G86: attested-only goals --------------------------------------------------

def test_an_attested_goal_validates_with_no_metric():
    """"I want to enjoy running again" has no measure and never will. The
    schema required one, so the thing athletes say they most value had
    nowhere to live at all (G83)."""
    attested = goal(slug="enjoy-running", metric=None, target=None,
                    period="none", verification="attested",
                    title="Enjoy running again")
    assert validate_record("goals", attested) == []


def test_an_attested_goal_refuses_a_metric():
    """A metric on an attested goal is a promise the engine cannot keep: it
    would start issuing verdicts on a proxy nobody agreed was the goal."""
    problems = validate_record("goals", goal(
        slug="enjoy-running", metric="steps", target=None, period="none",
        verification="attested"))
    assert any("attested" in p and "metric" in p for p in problems)


def test_an_attested_goal_never_receives_a_verdict():
    attested = goal(slug="enjoy-running", metric=None, target=None, period="none",
                    verification="attested")
    measured = goal(slug="steps", metric="steps", target=10000)
    contributions, milestones = compute_contributions(
        [attested, measured], [], [daily("2030-04-02", steps=11000)], [])
    assert {c["goal"] for c in contributions} == {"steps"}
    assert all(m["goal"] != "enjoy-running" for m in milestones)


def test_an_attested_goal_is_still_surfaced():
    """Never verdicted is not the same as never mentioned: the engine holds
    it, shows it, and takes the athlete's word as the only evidence."""
    attested = goal(slug="enjoy-running", metric=None, target=None, period="none",
                    verification="attested")
    rows = goal_progress([attested], [], [], [], "2030-05-01")
    assert [r["slug"] for r in rows] == ["enjoy-running"]
    assert rows[0]["verification"] == "attested"
    assert rows[0]["target"] is None and rows[0]["progress_pct"] is None


def test_external_goals_keep_working_through_the_old_sentinel():
    """`metric: "external"` predates the `verification` field. An old line is
    history, not an error, and must resolve to the same behaviour."""
    old = goal(slug="crown", metric="external", target=None, tracker="a segment app")
    assert validate_record("goals", old) == []
    assert verification_of(old) == "external"
    new = goal(slug="crown", metric=None, target=None, tracker="a segment app",
               verification="external")
    assert validate_record("goals", new) == []
    assert verification_of(new) == "external"


# ---- #26: a correction is not a change of mind ---------------------------------

def test_a_corrected_goal_line_is_not_churn():
    """The exact case that surfaced this: a deadline pushed, then superseded
    as a correction because the commitment had never actually moved. The
    retired line stays on disk; it must leave no suspicious-churn row."""
    goals = [goal(date="2030-04-01", deadline="2030-06-01", deadline_kind="hard"),
             goal(date="2030-05-01", deadline="2031-03-01", deadline_kind="hard",
                  change_kind="correction",
                  reason="the deadline never moved - the earlier line was a probe")]
    assert plan_churn(goals, []) == []


def test_an_unmarked_goal_edit_is_still_churn():
    goals = [goal(date="2030-04-01", target=12000),
             goal(date="2030-05-01", target=8000)]
    assert len(plan_churn(goals, [])) == 1


def test_a_correction_must_say_why():
    """Unexplained, a correction cannot be told from a quiet retreat wearing
    the right label - the one way this field could launder churn."""
    problems = validate_record("goals", goal(change_kind="correction"))
    assert any("reason" in p for p in problems)
    assert validate_record("goals", goal(change_kind="correction",
                                         reason="mis-typed target")) == []


# ---- G25: the goals dataset moving to generation 2 -----------------------------

def test_a_gen1_goal_line_still_validates_after_the_bump():
    """`goals` moved off the founding generation for the first time here, so
    this is the case the whole generation mechanism exists for: a line written
    before any of the new fields existed is not missing them."""
    gen1 = goal()
    for new_key in ("event", "deadline_kind", "verification", "change_kind"):
        gen1.pop(new_key, None)
    assert validate_record("goals", gen1) == []


def test_a_gen1_goal_line_resolves_identically_after_the_bump():
    """History stability, asserted on the VALUES rather than on the suite
    staying green: the same gen-1 line must produce the same state, the same
    progress and the same churn as it did before the fields existed."""
    gen1 = goal(date="2030-04-01", target=10000)
    edited = goal(date="2030-05-01", target=12000)
    assert state([gen1, edited], [], "2030-04-15").goal("steps")["target"] == 10000
    assert state([gen1, edited], [], "2030-05-15").goal("steps")["target"] == 12000

    rows = goal_progress([gen1], [], [daily("2030-04-02", steps=4000)], [],
                         "2030-04-02")
    assert rows[0]["counted"] == 4000
    assert rows[0]["progress_pct"] == 40.0
    assert rows[0]["deadline"] is None
    assert rows[0]["deadline_kind"] is None
    assert rows[0]["verification"] == "measured"

    churn = plan_churn([gen1, edited], [])
    assert len(churn) == 1
    assert churn[0]["direction"] == TIGHTENED


def test_a_goal_the_engine_cannot_feed_reports_unknown_not_zero():
    """`GOAL_DATASETS` widened to allow a weight goal (#18), but nothing
    iterates the weight dataset here, so it rendered as 0/78 (0%).

    Telling an athlete who has lost 3 kg that they are at 0% of their weight
    goal is the G69 harm in a new place: a number that reads as total failure
    because of a convention the reader cannot see. Unknown is the truth.
    """
    weight_goal = goal(slug="weight", metric="kg", target=78, dataset="weight",
                       period="none", on_period_end=None)
    row = goal_progress([weight_goal], [], [], [], "2030-05-01")[0]
    assert row["counted"] is None
    assert row["progress_pct"] is None
    assert row["target"] == 78, "the target is still known and still shown"


def test_a_daily_scoped_goal_still_counts_normally():
    row = goal_progress([goal(dataset="daily")], [],
                        [daily("2030-04-02", steps=4000)], [], "2030-04-02")[0]
    assert row["counted"] == 4000
    assert row["progress_pct"] == 40.0


# ---- #36: an unstated scope is not the default --------------------------------

def test_a_hand_written_weight_goal_reports_unknown_not_zero():
    """The shape a real record has - no `dataset` at all. The #34 guard keyed
    on a DECLARED unfeedable dataset, so the demo was fixed and the live
    record still rendered `0/73 (0%)` for an athlete at 83 kg."""
    hand_written = goal(slug="weight-73", metric="kg", target=73,
                        period="none", on_period_end=None)
    assert hand_written["dataset"] is None, "the fixture must not over-specify"
    row = goal_progress([hand_written], [], [], [], "2030-05-01")[0]
    assert row["counted"] is None
    assert row["progress_pct"] is None


def test_scope_is_inferred_from_the_metric_when_unset():
    """The fix the operator preferred: remove the trap rather than widen the
    guard. A goal in `kg` is a weight goal, and saying so is better than
    treating "unset" as a synonym for "unfeedable"."""
    row = goal_progress([goal(metric="kg", target=73, period="none",
                              on_period_end=None)], [], [], [], "2030-05-01")[0]
    assert row["dataset"] == "weight"
    assert row["scope"] == "inferred"


def test_unset_and_explicitly_declared_scope_stay_distinguishable():
    """Absent is not a value. Collapsing the two lets the engine assert
    something nobody said - the same line #35 draws for `recorder`."""
    unset = goal_progress([goal(metric="steps", dataset=None)], [],
                          [daily("2030-04-02", steps=4000)], [], "2030-04-02")[0]
    declared = goal_progress([goal(metric="steps", dataset="daily")], [],
                             [daily("2030-04-02", steps=4000)], [], "2030-04-02")[0]
    assert (unset["dataset"], unset["scope"]) == ("daily", "inferred")
    assert (declared["dataset"], declared["scope"]) == ("daily", "declared")
    assert unset["counted"] == declared["counted"] == 4000


def test_an_ambiguous_metric_infers_nothing():
    """`distance_km` is walking on a daily line and running on a session line
    - which is the entire reason `dataset` exists. Guessing would quietly
    count the athlete's commute toward a running goal, the failure `_in_scope`
    was written to prevent."""
    row = goal_progress([goal(metric="distance_km", target=30, dataset=None)],
                        [], [], [session("2030-04-02", type="run",
                                         distance_km=5.0)], "2030-04-02")[0]
    assert row["dataset"] is None
    assert row["scope"] == "ambiguous"
    assert row["counted"] == 5.0, "unchanged behaviour: it still counts"


def test_an_attested_goal_has_no_scope_to_infer():
    row = goal_progress([goal(slug="enjoy-running", metric=None, target=None,
                              period="none", verification="attested")],
                        [], [], [], "2030-05-01")[0]
    assert row["scope"] == "undeclared"
    assert row["counted"] is None
