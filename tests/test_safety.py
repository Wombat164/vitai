"""Increment 3: the medical layer and deterministic safety escalation (G28).

Synthetic data only (public repo: no real measurements). Every athlete,
symptom and number below is invented.

This file is the regression suite for the one decision that is not a coaching
input. The tests that matter most are the ones proving what the engine does
WITHOUT help: `test_chest_pain_escalates_instead_of_being_programmed_around`
(the site a coach would otherwise substitute around),
`test_absolute_rhr_fires_without_any_relative_drift` (danger judged with no
reference to baseline), and `test_a_gate_cannot_be_cleared_by_anything_a_model_emits`
(the firewall itself).
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.config import Config
from vitai.report import build_report
from vitai.safety import (
    EMERGENCY, PAIN_ABSOLUTE, RHR_ABSOLUTE_MAX, RHR_ABSOLUTE_MIN, URGENT,
    active_episodes, banner, escalations, gates_on, is_gated, is_open,
    episodes_on, urgent_now,
)
from vitai.schema import validate_record


def write(p: Path, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def medical(date="2030-05-01", slug="hip-strain", kind="injury",
            title="Hip strain", status="active", **kw):
    rec = {"date": date, "slug": slug, "kind": kind, "title": title,
           "body_site": None, "severity": "moderate", "status": status,
           "resolved_date": None, "restricts": None, "provider_type": None,
           "source": "athlete", "note": None}
    rec.update(kw)
    return rec


def daily(date="2030-05-01", **kw):
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "alcohol": None, "note": None, "source": "watch",
           "mood": None, "feel": None, "coverage": None, "pain": None,
           "pain_site": None, "pain_side": None, "_gen": 2}
    rec.update(kw)
    return rec


def session(date="2030-05-01", type="run", **kw):
    rec = {"date": date, "type": type, "distance_km": None, "duration_s": None,
           "avg_hr": None, "max_hr": None, "cadence": None, "kcal": None,
           "rpe": None, "note": None, "source": "watch", "start_time": None,
           "elevation_m": None, "setting": None, "route": None, "place": None,
           "with": None, "context": None, "planned": None, "weather": None,
           "_gen": 2}
    rec.update(kw)
    return rec


# ---- the medical schema ------------------------------------------------------

def test_a_valid_medical_line_passes():
    assert validate_record("medical", medical()) == []


def test_closed_vocabularies_are_enforced():
    assert any("kind" in p for p in validate_record("medical", medical(kind="vibe")))
    assert any("status" in p for p in validate_record(
        "medical", medical(status="ongoing")))
    assert any("severity" in p for p in validate_record(
        "medical", medical(severity="quite bad")))
    assert any("provider_type" in p for p in validate_record(
        "medical", medical(provider_type="my mate dave")))


def test_body_site_must_come_from_the_registry():
    assert validate_record("medical", medical(body_site="knee")) == []
    assert any("body_site" in p for p in validate_record(
        "medical", medical(body_site="soul")))


def test_restrictions_must_name_known_activity_classes():
    assert validate_record("medical", medical(restricts="run impact")) == []
    assert any("activity class" in p for p in validate_record(
        "medical", medical(restricts="parkour")))


def test_a_resolved_episode_needs_a_closing_date():
    problems = validate_record("medical", medical(status="resolved"))
    assert any("resolved_date" in p for p in problems)
    assert validate_record("medical", medical(
        status="resolved", resolved_date="2030-06-01")) == []


def test_a_closing_date_cannot_precede_onset():
    problems = validate_record("medical", medical(
        date="2030-05-10", status="resolved", resolved_date="2030-05-01"))
    assert any("precedes onset" in p for p in problems)


def test_an_unresolved_episode_may_not_carry_a_closing_date():
    problems = validate_record("medical", medical(resolved_date="2030-06-01"))
    assert any("not 'resolved'" in p for p in problems)


# ---- episode windows ---------------------------------------------------------

def test_episode_state_is_as_of_the_date_asked():
    """P2: last Tuesday is judged by what was known last Tuesday."""
    lines = [medical(date="2030-05-01", status="active"),
             medical(date="2030-06-01", status="resolved",
                     resolved_date="2030-06-01")]
    assert episodes_on(lines, "2030-05-15")[0]["status"] == "active"
    assert episodes_on(lines, "2030-06-10")[0]["status"] == "resolved"
    assert episodes_on(lines, "2030-04-01") == []


def test_open_window_math():
    active = medical(date="2030-05-01", status="active")
    monitoring = medical(date="2030-05-01", status="monitoring")
    resolved = medical(date="2030-05-01", status="resolved",
                       resolved_date="2030-05-20")
    assert is_open(active, "2030-05-15") is True
    assert is_open(monitoring, "2030-05-15") is True
    assert is_open(resolved, "2030-05-15") is True, "still open ON the closing day"
    assert is_open(resolved, "2030-05-20") is True
    assert is_open(resolved, "2030-05-21") is False


def test_a_resolution_does_not_retroactively_unclose_the_injured_weeks():
    lines = [medical(date="2030-05-01", status="active", restricts="run"),
             medical(date="2030-06-01", status="resolved",
                     resolved_date="2030-06-01", restricts="run")]
    assert active_episodes(lines, "2030-05-15") != []
    assert active_episodes(lines, "2030-06-05") == []


def test_supersedes_within_a_slug(tmp_path):
    """A correction to one episode line must not disturb a different episode."""
    write(tmp_path / "medical.jsonl", [
        medical(date="2030-05-01", slug="hip-strain", severity="moderate"),
        medical(date="2030-05-01", slug="calf-strain", title="Calf strain"),
        medical(date="2030-05-01", slug="hip-strain", severity="mild",
                supersedes="hip-strain@2030-05-01"),
    ])
    from vitai.jsonl import heads, load
    recs = load(tmp_path, "medical")
    assert len(recs) == 2
    by_slug = heads(recs, "medical")
    assert by_slug["hip-strain"]["severity"] == "mild"
    assert by_slug["calf-strain"]["title"] == "Calf strain"


# ---- gates -------------------------------------------------------------------

def test_a_restricting_episode_gates_its_activity_class():
    lines = [medical(restricts="run impact", title="Achilles tendinopathy")]
    gates = gates_on(lines, "2030-05-10")
    assert len(gates) == 1
    assert is_gated(gates, "run") is True
    assert is_gated(gates, "test") is True, "a time trial is still running"
    assert is_gated(gates, "walk") is False


def test_an_all_gate_blocks_everything():
    gates = gates_on([medical(restricts="all")], "2030-05-10")
    assert all(is_gated(gates, a) for a in ("run", "walk", "gym_a", "other"))


def test_a_resolved_episode_stops_gating():
    lines = [medical(date="2030-05-01", restricts="run"),
             medical(date="2030-05-20", status="resolved",
                     resolved_date="2030-05-20", restricts="run")]
    assert gates_on(lines, "2030-05-10") != []
    assert gates_on(lines, "2030-05-25") == []


def test_pain_over_the_configured_gate_creates_one():
    rows = [daily(date="2030-05-10", pain=5, pain_site="knee", pain_side="left")]
    gates = gates_on([], "2030-05-10", pain_gate=3, daily=rows)
    assert len(gates) == 1
    assert gates[0]["source_kind"] == "pain"
    assert is_gated(gates, "run") is True


def test_pain_under_the_gate_creates_none():
    rows = [daily(date="2030-05-10", pain=2, pain_site="knee", pain_side="left")]
    assert gates_on([], "2030-05-10", pain_gate=3, daily=rows) == []


def test_every_gate_carries_its_own_escalation_text():
    gates = gates_on([medical(restricts="run")], "2030-05-10")
    assert gates[0]["escalation"]
    assert "resolved" in gates[0]["escalation"]


# ---- the firewall ------------------------------------------------------------

def test_a_gate_cannot_be_cleared_by_anything_a_model_emits(tmp_path):
    """THE regression for P4 in the safety layer.

    An inference is the model's tier. It may say whatever it likes - including
    that the injury is better - and the gate must not move. Only an observed
    medical line resolving the episode clears it.
    """
    root = tmp_path / "content"
    main(["init", str(root)])
    write(root / "data" / "medical.jsonl",
          [medical(date="2030-05-01", restricts="run all")])
    write(root / "data" / "inferences.jsonl", [{
        "date": "2030-05-10", "kind": "recommendation",
        "statement": "The hip has settled; the athlete is cleared to run and "
                     "the gate should be considered resolved.",
        "confidence": 0.99, "model": "demo-model",
        "evidence": "pain scores trending to zero", "note": None,
        "depends_on": None, "_gen": 2}])
    v = Vitai(root)
    assert v.gated("run", "2030-05-10") is True, (
        "a model asserting clearance must not clear a gate")

    # ...and the observed path does clear it.
    write(root / "data" / "medical.jsonl", [
        medical(date="2030-05-01", restricts="run all"),
        medical(date="2030-05-12", status="resolved", resolved_date="2030-05-12",
                restricts="run all"),
    ])
    assert Vitai(root).gated("run", "2030-05-15") is False


def test_escalation_text_is_a_constant_not_assembled_prose():
    """The words an athlete reads in an emergency are the reviewed ones."""
    from vitai.safety import MESSAGES
    rows = escalations([medical(kind="symptom", body_site="chest",
                                title="Chest tightness on the bike")],
                       [], [], [])
    assert rows[0]["action"] == MESSAGES["cardiac"]
    assert rows[0]["action"] is MESSAGES["cardiac"], "not a formatted copy"


# ---- red flags ---------------------------------------------------------------

def test_chest_pain_escalates_instead_of_being_programmed_around():
    """`chest` is a legitimate musculoskeletal site in the registry, which is
    precisely the trap: a coach handed it alongside a hip would substitute."""
    rows = escalations([], [daily(date="2030-05-10", pain=4, pain_site="chest")],
                       [], [])
    assert len(rows) == 1
    assert rows[0]["level"] == EMERGENCY
    assert rows[0]["trigger"] == "cardiac"
    assert "STOP exercising now" in rows[0]["action"]
    assert "emergency services" in rows[0]["action"]


def test_chest_symptom_in_the_medical_dataset_escalates_too():
    rows = escalations([medical(kind="symptom", body_site="chest",
                                title="Tightness climbing stairs")], [], [], [])
    assert rows[0]["level"] == EMERGENCY and rows[0]["trigger"] == "cardiac"


def test_a_musculoskeletal_site_does_not_trigger_the_cardiac_branch():
    rows = escalations([], [daily(date="2030-05-10", pain=4, pain_site="knee",
                                  pain_side="left")], [], [])
    assert rows == []


def test_a_declared_red_flag_is_honoured_whoever_wrote_it():
    """A skill may RAISE an escalation; the asymmetry is that it can never
    lower one."""
    rows = escalations([medical(severity="red_flag", title="Fainted after a run")],
                       [], [], [])
    assert len(rows) == 1 and rows[0]["level"] == URGENT
    assert rows[0]["trigger"] == "red_flag_declared"


# ---- absolute thresholds -----------------------------------------------------

def test_absolute_rhr_fires_without_any_relative_drift():
    """The relative tripwire is baseline+5; an athlete whose baseline drifted
    up over months never trips it however high the number gets."""
    rows = escalations([], [daily(date="2030-05-10", rhr=RHR_ABSOLUTE_MAX + 5)],
                       [], [])
    assert len(rows) == 1
    assert rows[0]["level"] == EMERGENCY and rows[0]["trigger"] == "rhr_absolute"


def test_a_trained_athletes_genuinely_low_resting_rate_does_not_fire():
    """Mid-30s is normal for a trained endurance athlete and must not
    escalate, or the safety layer trains people to ignore it."""
    rows = escalations([], [daily(date="2030-05-10", rhr=36)], [], [])
    assert rows == []


def test_a_rate_below_any_physiological_floor_fires():
    rows = escalations([], [daily(date="2030-05-10", rhr=RHR_ABSOLUTE_MIN - 5)],
                       [], [])
    assert rows and rows[0]["trigger"] == "rhr_absolute"


def test_extreme_pain_escalates_regardless_of_the_configured_gate():
    rows = escalations([], [daily(date="2030-05-10", pain=PAIN_ABSOLUTE,
                                  pain_site="knee", pain_side="left")], [], [])
    assert len(rows) == 1
    assert rows[0]["level"] == URGENT and rows[0]["trigger"] == "severe_pain"


# ---- RED-S -------------------------------------------------------------------

def _red_s_record(deficit=-1400, kg_start=70.0, kg_end=68.6, minutes=60):
    days = [daily(date=f"2030-05-{d:02d}", kcal_in=2000,
                  kcal_out=2000 - deficit) for d in range(1, 15)]
    weight = [{"date": "2030-05-01", "kg": kg_start, "source": "scale",
               "note": None},
              {"date": "2030-05-14", "kg": kg_end, "source": "scale",
               "note": None}]
    sessions = [session(date=f"2030-05-{d:02d}", duration_s=minutes * 60)
                for d in (2, 4, 6, 9, 11, 13)]
    return days, weight, sessions


def test_red_s_fires_on_deep_deficit_plus_fast_loss_plus_load():
    days, weight, sessions = _red_s_record()
    rows = escalations([], days, weight, sessions)
    red_s = [r for r in rows if r["trigger"] == "red_s"]
    assert len(red_s) == 1
    assert red_s[0]["level"] == URGENT
    assert "RED-S" in red_s[0]["action"]
    assert "not as a target met" in red_s[0]["action"], (
        "the syndrome this tool's own coaching can cause is never a win")


def test_red_s_does_not_fire_on_a_deficit_alone():
    """A deep deficit is a choice; it is the combination that is the pattern."""
    days, weight, sessions = _red_s_record(kg_end=69.9, minutes=5)
    rows = escalations([], days, weight, sessions)
    assert [r for r in rows if r["trigger"] == "red_s"] == []


def test_red_s_does_not_fire_without_training_load():
    days, weight, _ = _red_s_record()
    rows = escalations([], days, weight, [])
    assert [r for r in rows if r["trigger"] == "red_s"] == []


def test_red_s_does_not_screen_on_a_nearly_empty_window():
    days = [daily(date="2030-05-01", kcal_in=1000, kcal_out=3000)]
    weight = [{"date": "2030-05-01", "kg": 70.0, "source": "scale", "note": None},
              {"date": "2030-05-02", "kg": 68.0, "source": "scale", "note": None}]
    assert escalations([], days, weight, []) == []


def test_red_s_is_the_cut_first_item_and_can_be_disabled():
    days, weight, sessions = _red_s_record()
    rows = escalations([], days, weight, sessions, include_red_s=False)
    assert [r for r in rows if r["trigger"] == "red_s"] == []


# ---- the fast path -----------------------------------------------------------

def test_the_fast_path_surfaces_a_same_day_entry():
    rows = escalations([], [daily(date="2030-05-10", pain=4, pain_site="chest")],
                       [], [])
    assert urgent_now(rows, on="2030-05-10") == rows


def test_the_fast_path_does_not_resurface_old_history():
    """An escalation from March is history, not today's alarm."""
    rows = escalations([], [daily(date="2030-03-01", pain=4, pain_site="chest")],
                       [], [])
    assert rows != []
    assert urgent_now(rows, on="2030-05-10") == []


def test_the_fast_path_ignores_advisory_noise():
    rows = [{"date": "2030-05-10", "level": "advisory", "trigger": "x",
             "detail": "d", "action": "a"}]
    assert urgent_now(rows, on="2030-05-10") == []


def test_escalations_are_ordered_most_urgent_first():
    rows = escalations(
        [medical(date="2030-05-10", severity="red_flag", title="Declared")],
        [daily(date="2030-05-10", pain=4, pain_site="chest")], [], [])
    assert [r["level"] for r in rows] == [EMERGENCY, URGENT]


def test_the_banner_is_empty_when_clear():
    assert banner([]) == ""


def test_the_banner_says_it_is_not_a_diagnosis():
    rows = escalations([], [daily(date="2030-05-10", pain=4, pain_site="chest")],
                       [], [])
    text = banner(rows)
    assert "not a diagnosis" in text
    assert "clinician" in text


# ---- surfaces: CLI, API, read model -----------------------------------------

def _repo_with_a_gate(tmp_path: Path) -> Path:
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "vitai.toml").write_text(
        "[tripwires]\npain_gate = 3\n", encoding="utf-8")
    write(root / "data" / "medical.jsonl", [
        medical(date="2030-05-01", slug="achilles", kind="injury",
                title="Achilles tendinopathy", body_site="achilles",
                restricts="run impact", provider_type="physio"),
        medical(date="2030-04-01", slug="calf", kind="injury",
                title="Calf strain", status="resolved",
                resolved_date="2030-04-20", restricts="run"),
    ])
    return root


def test_api_exposes_gates_and_escalations(tmp_path):
    v = Vitai(_repo_with_a_gate(tmp_path))
    assert v.gated("run", "2030-05-10") is True
    assert v.gated("walk", "2030-05-10") is False
    assert len(v.episodes("2030-05-10")) == 1, "the resolved one is closed"
    assert len(v.episodes("2030-04-10")) == 1


def test_build_projects_the_safety_tables(tmp_path):
    root = _repo_with_a_gate(tmp_path)
    write(root / "data" / "daily.jsonl",
          [daily(date="2030-05-10", pain=4, pain_site="chest")])
    db = Vitai(root).build(today=None)
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM medical").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM escalations").fetchone()[0] >= 1
        assert con.execute(
            "SELECT trigger FROM escalations WHERE level='emergency'"
        ).fetchone()[0] == "cardiac"
        assert con.execute(
            "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "5"
    finally:
        con.close()


def test_cli_safety_exits_two_while_something_is_urgent(tmp_path, capsys):
    root = _repo_with_a_gate(tmp_path)
    write(root / "data" / "daily.jsonl",
          [daily(date="2030-05-10", pain=4, pain_site="chest")])
    with pytest.raises(SystemExit) as exc:
        main(["safety", "--root", str(root), "--on", "2030-05-10"])
    assert exc.value.code == 2
    assert "STOP exercising now" in capsys.readouterr().out


def test_cli_safety_is_quiet_when_clear(tmp_path, capsys):
    root = _repo_with_a_gate(tmp_path)
    main(["safety", "--root", str(root), "--on", "2030-05-10"])
    out = capsys.readouterr().out
    assert "no active safety escalations" in out
    assert "blocks impact run" in out, "a gate still reports even with no alarm"


def test_the_rollup_carries_a_gates_line(tmp_path):
    v = Vitai(_repo_with_a_gate(tmp_path))
    text = v.rollup(today=date(2030, 5, 10))
    assert "## Gates" in text
    assert "blocked" in text
    assert "not by argument" in text, "the gate says it cannot be talked away"


def test_the_rollup_shows_no_gate_before_the_episode_existed(tmp_path):
    """An episode dated in the future gates nothing - P2, not a special case."""
    v = Vitai(_repo_with_a_gate(tmp_path))
    assert "Nothing gated." in v.rollup(today=date(2030, 1, 1))


def test_the_rollup_says_nothing_gated_when_clear():
    text = build_report(Config(), [], [], [], today=None)
    assert "Nothing gated." in text


# ---- regression: the increment changes nothing it did not intend to ---------

def test_a_record_with_no_medical_data_is_unaffected(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "vitai.toml").write_text(
        "[targets]\nphases = [[80.0, 70.0, 0.7]]\n"
        "[tripwires]\nsteps_floor = 8000\n", encoding="utf-8")
    write(root / "data" / "daily.jsonl",
          [daily(date=f"2030-05-{d:02d}", steps=9000 + d, rhr=52)
           for d in range(1, 15)])
    v = Vitai(root)
    assert v.safety() == []
    assert v.gates() == []
    assert v.urgent() == []
    db = v.build()
    first = db.read_bytes()
    v.build()
    assert db.read_bytes() == first, "two builds differ"


# ==========================================================================
# Issue #19: gate mechanics - preconditions and the onset/recorded-at split
# ==========================================================================

def check(date="2030-05-10", slug="hop-test", result="pass", **kw):
    rec = {"date": date, "slug": slug, "result": result, "value": None,
           "source": "athlete", "note": None}
    rec.update(kw)
    return rec


# ---- onset vs recorded-at ----------------------------------------------------

def test_a_historical_episode_can_be_entered_today(tmp_path):
    """Backfilling a 2025 injury today used to be rejected outright:
    `resolved_date 2025-12-01 precedes onset 2026-07-27`. The row date was
    doing double duty as when-written and when-it-began."""
    rec = medical(date="2030-07-27", onset_date="2029-09-01",
                  status="resolved", resolved_date="2029-12-01")
    assert validate_record("medical", rec) == []


def test_resolved_date_is_still_checked_against_onset():
    """The rule is not dropped, only pointed at the right field."""
    rec = medical(date="2030-07-27", onset_date="2030-06-01",
                  status="resolved", resolved_date="2030-05-01")
    assert any("precedes onset" in p for p in validate_record("medical", rec))


def test_onset_defaults_to_the_row_date_so_nothing_existing_moves():
    from vitai.schema import onset_of
    assert onset_of({"date": "2030-05-01"}) == "2030-05-01"
    assert onset_of({"date": "2030-05-01",
                     "onset_date": "2029-01-01"}) == "2029-01-01"


def test_the_episode_window_opens_at_onset_not_at_entry():
    """A 2029 injury recorded in 2030 was open through 2029 - which is the
    whole point of being able to backfill it."""
    episode = medical(date="2030-07-27", onset_date="2029-09-01",
                      status="resolved", resolved_date="2029-12-01")
    assert is_open(episode, "2029-10-01") is True
    assert is_open(episode, "2029-08-01") is False, "before it began"
    assert is_open(episode, "2030-01-01") is False, "after it closed"


def test_head_selection_still_reads_the_entry_date():
    """P2 is a question about KNOWLEDGE: what was known last Tuesday. Onset
    says when it began; `date` says when the record learned of it."""
    lines = [medical(date="2030-07-27", slug="old-injury",
                     onset_date="2029-09-01")]
    assert episodes_on(lines, "2030-01-01") == [], "not yet known in January"
    assert len(episodes_on(lines, "2030-08-01")) == 1


def test_an_achievement_can_record_when_it_actually_happened():
    from vitai.schema import occurred_of
    rec = {"date": "2030-07-27", "title": "Ran a half marathon",
           "goal": None, "source": "athlete", "note": None,
           "occurred_date": "2030-03-15"}
    assert validate_record("achievements", rec) == []
    assert occurred_of(rec) == "2030-03-15"
    assert any("occurred_date" in p for p in validate_record(
        "achievements", {**rec, "occurred_date": "last spring"}))


# ---- preconditions -----------------------------------------------------------

def _hop_test_episode():
    """The real instruction: 5 gentle hops before each run; pain means no run
    that day. A gate CONDITIONAL on a test performed that morning."""
    return [medical(date="2030-05-01", slug="groin", title="Groin strain",
                    body_site="groin", restricts="run impact",
                    precondition="hop-test")]


def test_a_passed_check_lifts_the_gate_for_today():
    gates = gates_on(_hop_test_episode(), "2030-05-10",
                     checks=[check(result="pass")])
    assert len(gates) == 1
    assert gates[0]["status"] == "cleared"
    assert is_gated(gates, "run") is False
    assert "FOR TODAY" in gates[0]["escalation"], "it returns tomorrow"


def test_a_failed_check_blocks():
    gates = gates_on(_hop_test_episode(), "2030-05-10",
                     checks=[check(result="fail")])
    assert gates[0]["status"] == "blocked"
    assert is_gated(gates, "run") is True


def test_no_check_recorded_is_reported_distinctly_and_still_blocks():
    """THE acceptance criterion. Not-done is not pass: an athlete who never
    ran the check is not cleared by silence."""
    gates = gates_on(_hop_test_episode(), "2030-05-10", checks=[])
    assert gates[0]["status"] == "check_not_done"
    assert gates[0]["status"] not in ("cleared", "blocked"), "a third state"
    assert is_gated(gates, "run") is True, "silence does not clear a gate"
    assert "not the same as passing" in gates[0]["escalation"]


def test_an_explicit_not_done_reads_the_same_as_silence():
    gates = gates_on(_hop_test_episode(), "2030-05-10",
                     checks=[check(result="not_done")])
    assert gates[0]["status"] == "check_not_done"


def test_yesterdays_pass_does_not_clear_today():
    """The check is DAILY. A pass on Monday says nothing about Tuesday."""
    gates = gates_on(_hop_test_episode(), "2030-05-10",
                     checks=[check(date="2030-05-09", result="pass")])
    assert gates[0]["status"] == "check_not_done"
    assert is_gated(gates, "run") is True


def test_a_check_for_a_different_gate_does_not_clear_this_one():
    gates = gates_on(_hop_test_episode(), "2030-05-10",
                     checks=[check(slug="calf-raise", result="pass")])
    assert gates[0]["status"] == "check_not_done"


def test_a_gate_without_a_precondition_is_unchanged():
    gates = gates_on([medical(restricts="run")], "2030-05-10", checks=[])
    assert gates[0]["status"] == "blocked"
    assert gates[0]["precondition"] is None


def test_a_precondition_that_gates_nothing_is_rejected():
    """A check that lifts no restriction is just a note."""
    problems = validate_record("medical", medical(precondition="hop-test"))
    assert any("gates nothing" in p for p in problems)


def test_check_results_are_a_closed_vocabulary():
    assert validate_record("checks", check()) == []
    assert any("result" in p for p in validate_record(
        "checks", check(result="sort of")))
    assert any("slug" in p for p in validate_record("checks", check(slug="")))


def test_the_api_lists_what_has_not_been_checked_today(tmp_path):
    """So a coach can say "you have not done the hop test today" rather than
    assuming either outcome."""
    root = tmp_path / "content"
    main(["init", str(root)])
    write(root / "data" / "medical.jsonl", _hop_test_episode())
    v = Vitai(root)
    pending = v.pending_checks("2030-05-10")
    assert len(pending) == 1 and pending[0]["precondition"] == "hop-test"

    write(root / "data" / "checks.jsonl", [check(result="pass")])
    assert Vitai(root).pending_checks("2030-05-10") == []
