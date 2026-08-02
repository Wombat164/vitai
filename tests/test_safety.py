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
    AMENORRHOEA_EXCLUDES, AMENORRHOEA_PHRASES, EMERGENCY, HOLD, PAIN_ABSOLUTE, RHR_ABSOLUTE_MAX,
    RHR_ABSOLUTE_MIN, URGENT, _asserted, active_episodes, banner,
    energy_availability, escalations, gates_on, is_gated, is_open,
    episodes_on, scan_prose, session_classes, urgent_now,
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


def weight(date, kg, **kw):
    rec = {"date": date, "kg": kg, "source": "scale", "note": None,
           "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
           "body_fat_lo": None, "body_fat_hi": None, "_gen": 2}
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
    declared = [r for r in rows if r["trigger"] == "red_flag_declared"]
    assert len(declared) == 1 and declared[0]["level"] == URGENT
    # The prose net independently catches the same title (issue #12). Two
    # routes to one finding is the design, not a duplicate bug: neither path
    # can suppress the other.
    assert any(r["trigger"] == "syncope" for r in rows)


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

def _low_energy_record(deficit=-1400, kg_start=70.0, kg_end=68.6, minutes=60):
    days = [daily(date=f"2030-05-{d:02d}", kcal_in=2000,
                  kcal_out=2000 - deficit) for d in range(1, 15)]
    weight = [{"date": "2030-05-01", "kg": kg_start, "source": "scale",
               "note": None},
              {"date": "2030-05-14", "kg": kg_end, "source": "scale",
               "note": None}]
    sessions = [session(date=f"2030-05-{d:02d}", duration_s=minutes * 60)
                for d in (2, 4, 6, 9, 11, 13)]
    return days, weight, sessions


def test_low_energy_fires_on_deep_deficit_plus_fast_loss_plus_load():
    days, weight, sessions = _low_energy_record()
    rows = escalations([], days, weight, sessions)
    low_energy = [r for r in rows if r["trigger"] == "clinical_hold"]
    assert len(low_energy) == 1
    # Issue #12 raised this from a message to a HOLD: the correct response is
    # to suspend progression, not to add a line to the rollup. #110 removed
    # the second half of that - "and refer" - so what is asserted now is the
    # ACT and an exit the record owner can reach, rather than an addressee.
    assert low_energy[0]["level"] == HOLD
    assert "TRAINING IS ON HOLD" in low_energy[0]["action"]
    assert "no plan, progression or session is issued" in low_energy[0]["action"]
    assert "The hold lifts when the record shows" in low_energy[0]["action"]


def test_low_energy_does_not_fire_on_a_deficit_alone():
    """A deep deficit is a choice; it is the combination that is the pattern."""
    days, weight, sessions = _low_energy_record(kg_end=69.9, minutes=5)
    rows = escalations([], days, weight, sessions)
    assert [r for r in rows if r["trigger"] == "clinical_hold"] == []


def test_low_energy_does_not_fire_without_training_load():
    days, weight, _ = _low_energy_record()
    rows = escalations([], days, weight, [])
    assert [r for r in rows if r["trigger"] == "clinical_hold"] == []


def test_low_energy_does_not_screen_on_a_nearly_empty_window():
    days = [daily(date="2030-05-01", kcal_in=1000, kcal_out=3000)]
    weight = [{"date": "2030-05-01", "kg": 70.0, "source": "scale", "note": None},
              {"date": "2030-05-02", "kg": 68.0, "source": "scale", "note": None}]
    assert escalations([], days, weight, []) == []


def test_low_energy_is_the_cut_first_item_and_can_be_disabled():
    days, weight, sessions = _low_energy_record()
    rows = escalations([], days, weight, sessions, include_low_energy_availability=False)
    assert [r for r in rows if r["trigger"] == "clinical_hold"] == []


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


def test_the_banner_carries_the_standing_disclaimer_and_routes_nobody():
    """It used to end "vitai routes to a clinician and stops" - the removed
    claim, live on every escalation surface, asserting exactly the medical
    purpose #110 exists to disclaim."""
    from vitai.safety import DISCLAIMER
    rows = escalations([], [daily(date="2030-05-10", pain=4, pain_site="chest")],
                       [], [])
    text = banner(rows)
    assert DISCLAIMER in text
    assert "not a medical device" in text
    assert "routes to a clinician" not in text


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
            "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "18"
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
# Issue #12: the persona sweeps. Everything below exists because a simulated
# real user walked into a gap the design did not know it had.
# ===================================================================

def _stable_low_energy(**kw):
    """The weight-STABLE presentation: the one the first composite missed.

    57 kg and unchanged, energy availability far below threshold, real load,
    amenorrhoea in a note. Nothing about the scale is abnormal, which is the
    entire point.
    """
    days = [daily(date=f"2030-06-{d:02d}", kcal_in=1600, rhr=50,
                  note="period still absent, 5th month" if d % 7 == 3 else None)
            for d in range(1, 29)]
    weight = [{"date": "2030-06-01", "kg": 57.0, "source": "scale",
               "note": None, "body_fat_pct": 17.0, "kg_lo": None, "kg_hi": None,
               "body_fat_lo": None, "body_fat_hi": None, "_gen": 2},
              {"date": "2030-06-28", "kg": 57.0, "source": "scale",
               "note": None, "body_fat_pct": 17.0, "kg_lo": None, "kg_hi": None,
               "body_fat_lo": None, "body_fat_hi": None, "_gen": 2}]
    sessions = [session(date=f"2030-06-{d:02d}", type="other", duration_s=13800,
                        kcal=2650) for d in (6, 13, 20, 27)]
    return days, weight, sessions


def test_low_energy_fires_while_the_athlete_is_weight_stable():
    """THE finding of issue #12.

    RED-S commonly presents weight-stable - the body downregulates instead of
    losing. Requiring rate of loss made stability EXONERATING when it is
    often the finding itself.
    """
    days, weight, sessions = _stable_low_energy()
    rows = escalations([], days, weight, sessions)
    holds = [r for r in rows if r["trigger"] == "clinical_hold"]
    assert len(holds) == 1, "a textbook weight-stable presentation was missed"
    assert holds[0]["level"] == HOLD
    assert "energy availability" in holds[0]["detail"]
    assert "menstrual" in holds[0]["detail"], "the corroborating marker is named"


def test_low_energy_availability_alone_is_not_enough():
    """Still a composite: low EA plus load plus at least one marker. A hard
    training block with no other finding is training, not a syndrome."""
    days, weight, sessions = _stable_low_energy()
    quiet = [dict(r, note=None) for r in days]      # no amenorrhoea, no drift
    rows = escalations([], quiet, weight, sessions)
    assert [r for r in rows if r["trigger"] == "clinical_hold"] == []


def test_energy_availability_is_not_guessed_without_body_composition():
    """No body-fat read means no EA - never an estimated one. A manufactured
    input to a clinical decision is worse than no decision."""
    days, weight, sessions = _stable_low_energy()
    no_comp = [dict(w, body_fat_pct=None) for w in weight]
    ea, terms = energy_availability(days, no_comp, sessions)
    assert ea is None and terms == {}


def test_a_hold_blocks_training_rather_than_only_warning(tmp_path):
    """G73: a hold is an ACT, not a louder message. It must reach the gate
    mechanism, which is the thing a coach cannot talk around."""
    root = tmp_path / "content"
    main(["init", str(root)])
    days, weight, sessions = _stable_low_energy()
    write(root / "data" / "daily.jsonl", days)
    write(root / "data" / "weight.jsonl", weight)
    write(root / "data" / "sessions.jsonl", sessions)
    v = Vitai(root)
    assert v.gated("run", "2030-06-28") is True
    assert v.gated("gym_a", "2030-06-28") is True, "a hold suspends everything"
    hold = [g for g in v.gates("2030-06-28") if g["source_kind"] == "hold"]
    assert hold and "TRAINING IS ON HOLD" in hold[0]["escalation"]


# ---- the prose net (G59) -----------------------------------------------------

def test_a_symptom_buried_in_prose_still_escalates():
    """Frightened people write "it's nothing, not really worth going on
    about" - not a structured pain_site."""
    rows = escalations([], [daily(date="2030-06-01",
                                  note="chest twinge going up the stairs, few "
                                       "seconds, gone")], [], [])
    assert len(rows) == 1
    assert rows[0]["trigger"] == "cardiac" and rows[0]["level"] == EMERGENCY


def test_the_prose_net_does_not_cry_wolf_at_a_denial():
    """Escalating "no chest pain" would teach the athlete to ignore the alarm,
    which costs more than the case it catches."""
    for note in ("no chest pain today", "denies chest pain",
                 "was not chest pain, just a stitch"):
        assert escalations([], [daily(date="2030-06-01", note=note)],
                           [], []) == [], note


def test_the_prose_net_reads_sessions_and_medical_notes_too():
    assert escalations([], [], [], [session(date="2030-06-01",
                                            note="passed out after")]) != []
    assert escalations([medical(date="2030-06-01", title="Odd episode",
                                note="blacked out briefly")], [], [], []) != []


def test_prose_findings_reach_the_verdict_rows(tmp_path):
    """A safety finding only in a channel nobody renders is one nobody sees."""
    root = tmp_path / "content"
    main(["init", str(root)])
    write(root / "data" / "daily.jsonl",
          [daily(date="2030-06-01", note="chest tightness on the stairs")])
    metrics = {r["metric"] for r in Vitai(root).verdicts()}
    assert "symptom_chest_pain" in metrics


# ---- absolute nutrition floors (G68) -----------------------------------------

def _sustained(kcal_in, protein_g=None, days=14):
    return [daily(date=f"2030-06-{d:02d}", kcal_in=kcal_in, protein_g=protein_g)
            for d in range(1, days + 1)]


def test_the_intake_floor_fires_with_no_configuration_at_all():
    """The athlete who exposed this had configured nothing, as new users have
    not, and the engine reported `tripwires: none`."""
    rows = escalations([], _sustained(1200), [], [])
    assert [r for r in rows if r["trigger"] == "intake_floor"]


def test_a_normal_intake_does_not_fire_the_floor():
    assert escalations([], _sustained(2100), [], []) == []


def test_a_declared_state_raises_the_floor_but_never_removes_it():
    """G57: nursing raises energy requirements, so an intake that would be
    merely low becomes a floor breach - the modifier can only tighten."""
    nursing = [medical(date="2030-05-01", slug="breastfeeding", kind="state",
                       title="Exclusively breastfeeding", severity="none",
                       status="active", expects="elevated_requirement")]
    rows = escalations(nursing, _sustained(1600), [], [])
    assert [r for r in rows if r["trigger"] == "intake_floor"], (
        "1600 kcal while nursing is below the raised floor")
    assert not [r for r in escalations([], _sustained(1600), [], [])
                if r["trigger"] == "intake_floor"], (
        "...and is above the unmodified floor")


def test_the_protein_floor_names_lean_mass_risk_during_rapid_loss():
    weight = [{"date": "2030-06-01", "kg": 126.0, "source": "clinic",
               "note": None, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
               "body_fat_lo": None, "body_fat_hi": None, "_gen": 2},
              {"date": "2030-06-14", "kg": 122.0, "source": "clinic",
               "note": None, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
               "body_fat_lo": None, "body_fat_hi": None, "_gen": 2}]
    rows = escalations([], _sustained(1400, protein_g=30), weight, [])
    protein = [r for r in rows if r["trigger"] == "protein_floor"]
    assert protein and "lean-mass loss risk" in protein[0]["detail"]
    assert "resistance" in protein[0]["action"]


# ---- medication as a modifier (G72) ------------------------------------------

def test_expected_rapid_loss_suppresses_the_rate_verdict_only():
    """Firing the wrong rule is worse than silence: it tells a succeeding
    athlete she is failing. The floors must still fire."""
    from vitai.verdicts import compute_verdicts
    weight = [{"date": f"2030-06-{d:02d}", "kg": 126.0 - d * 0.3,
               "source": "clinic", "note": None, "body_fat_pct": None,
               "kg_lo": None, "kg_hi": None, "body_fat_lo": None,
               "body_fat_hi": None, "_gen": 2} for d in range(1, 15)]
    days = _sustained(900, protein_g=28)
    med = [medical(date="2030-05-01", slug="glp1", kind="medication",
                   title="GLP-1 agonist", severity="none", status="active",
                   expects="rapid_loss appetite_suppression")]

    unmedicated = compute_verdicts(Config(phases=((130.0, 100.0, 0.7),)),
                                   weight, days, [], medical=[])
    medicated = compute_verdicts(Config(phases=((130.0, 100.0, 0.7),)),
                                 weight, days, [], medical=med)
    assert any(r["metric"] == "weight_rate" and r["verdict"] != "no_data"
               for r in unmedicated)
    # LABELLED, not deleted (#177), and the reason matters most here: a
    # contraindicated verdict that simply vanished was indistinguishable from
    # one never computed, so nothing could say WHY this athlete is not being
    # scored on a rate. Judged is still what it must not be.
    medicated_rate = [r for r in medicated if r["metric"] == "weight_rate"]
    assert medicated_rate, "the row must say it was withheld, not disappear"
    assert all(r["verdict"] == "no_data" for r in medicated_rate), (
        "expected medicated loss was judged against a lifestyle target")
    assert all(r["reason"] == "contraindicated" for r in medicated_rate)
    assert any(r["metric"] == "intake_floor" and r["verdict"] == "behind"
               for r in medicated), "a modifier must never silence a floor"


def test_the_expects_vocabulary_is_closed():
    assert any("expects" in p for p in validate_record(
        "medical", medical(expects="makes_you_taller")))
    assert validate_record("medical", medical(expects="rapid_loss")) == []


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


# ---- #66: the prose net and the register frightened people use -----------------

HEDGED_REPORTS = [
    "not sure why but chest pain on the stairs again",
    "wasn't expecting it: chest pain mid-run",
    "no chest pain at rest, but chest pain going up the stairs",
]


@pytest.mark.parametrize("note", HEDGED_REPORTS)
def test_a_hedged_report_still_escalates(note):
    """Verbatim from the issue. The net exists because "frightened people do
    not fill in a pain_site field" - and it was defeated by the exact register
    frightened people use.

    The third is the worst: no pain at rest, pain on exertion is a textbook
    presentation, and scanning only the FIRST occurrence meant the more
    precisely an athlete described exertional angina, the more certain the
    miss.
    """
    assert "cardiac" in scan_prose(note), note


def test_a_negation_governs_its_clause_not_a_character_window():
    """"not sure why but chest pain" - the "not" governs "sure why". A
    24-character proximity window cannot tell those apart, because proximity
    is not a question about meaning."""
    assert scan_prose("not sure why but chest pain") == ["cardiac"]
    assert scan_prose("not chest pain") == []


def test_a_denial_is_still_a_denial():
    """The guard must survive the fix, or the alarm gets ignored - which is
    the failure mode the negation check was written for."""
    for denied in ("no chest pain", "denies chest pain", "never had chest pain",
                   "no chest pain and no dizziness",
                   "felt great, no chest pain at all"):
        assert scan_prose(denied) == [], denied


def test_every_occurrence_is_examined_not_the_first():
    """A phrase denied once and asserted later is asserted."""
    assert "cardiac" in scan_prose(
        "no chest pain warming up. chest pain on the second hill.")


def test_a_marker_phrase_is_negation_guarded_too():
    """`_corroborating_markers` scanned all history with no negation guard at
    all, and no window - a marker once matched was permanent."""
    assert _asserted(["periods stopped months ago"], AMENORRHOEA_PHRASES) is True
    assert _asserted(["no amenorrhoea"], AMENORRHOEA_PHRASES) is False


def test_a_trigger_phrase_whose_meaning_turns_on_the_next_word():
    """`no period` reports absent MENSTRUATION; "no period pains" reports
    absent PAIN, and matched too. Negation cannot help - the denial is inside
    the trigger - so what distinguishes them is the word that FOLLOWS.

    Dropping the phrase was the first fix and it was under-triage: it lost
    "no period", "no period this month", "no period yet" and "still no
    period", in a marker that gates a clinical hold.
    """
    for false_alarm in ("no period pains", "no period cramps",
                        "no period discomfort"):
        assert _asserted([false_alarm], AMENORRHOEA_PHRASES,
                         AMENORRHOEA_EXCLUDES) is False, false_alarm
    for real in ("no period", "no period this month", "no period yet",
                 "still no period", "no periods since March",
                 "haven't had a period in months"):
        assert _asserted([real], AMENORRHOEA_PHRASES,
                         AMENORRHOEA_EXCLUDES) is True, real


def test_a_persistent_marker_does_not_age_out_of_the_window_it_gates():
    """Amenorrhoea and a bone-stress history are persistent, and they gate
    the RED-S hold entirely. Restricting markers to the analysis window meant
    a report from last month aged out of the thing it is evidence for."""
    from vitai.safety import _corroborating_markers
    old_note = daily("2030-01-05", note="periods stopped months ago")
    days = [old_note] + [daily(f"2030-05-{d:02d}") for d in range(1, 15)]
    weights = [weight(f"2030-05-{d:02d}", 55.0) for d in range(1, 15)]
    markers = _corroborating_markers(days, weights, [], date(2030, 5, 1),
                                     date(2030, 5, 14))
    assert "menstrual function reported absent" in markers


def test_a_marker_written_after_the_date_under_examination_is_not_used():
    """`end` is still respected: a note from next month cannot corroborate
    today, or an as-of reconstruction sees the future."""
    from vitai.safety import _corroborating_markers
    future = daily("2030-09-01", note="periods stopped months ago")
    days = [future] + [daily(f"2030-05-{d:02d}") for d in range(1, 15)]
    weights = [weight(f"2030-05-{d:02d}", 55.0) for d in range(1, 15)]
    markers = _corroborating_markers(days, weights, [], date(2030, 5, 1),
                                     date(2030, 5, 14))
    assert markers == []


# ---- #63: resistance training, via the registry -------------------------------

def test_the_canonical_strength_type_counts_as_resistance():
    """`startswith("gym")` counted only the two labels retired precisely
    because they were one athlete's programme names. Everyone on the public
    vocabulary was asserted to do no resistance work, always."""
    for lifting in ("strength", "crossfit", "pilates", "gym_a", "gym_b"):
        assert "strength" in session_classes(lifting), lifting
    for not_lifting in ("run", "walk", "swim", "cycle"):
        assert "strength" not in session_classes(not_lifting), not_lifting


def test_a_retired_and_a_current_label_behave_identically():
    """They are the same thing under two names, and the safety layer must not
    be able to tell them apart."""
    assert session_classes("gym_a") == session_classes("strength")


def test_lifting_suppresses_the_no_resistance_clause():
    """The false statement about the athlete's own record: an escalation that
    read "with no resistance training" to someone who had lifted that week."""
    days = [daily(f"2030-05-{d:02d}", kcal_in=1500, protein_g=40)
            for d in range(1, 15)]
    weights = [weight(f"2030-05-{d:02d}", 80.0 - d * 0.12) for d in range(1, 15)]
    lifted = [session("2030-05-10", type="strength")]
    with_lifting = escalations([], days, weights, lifted,
                               on=date(2030, 5, 14))
    without = escalations([], days, weights, [], on=date(2030, 5, 14))
    said_with = " ".join(e["detail"] for e in with_lifting)
    said_without = " ".join(e["detail"] for e in without)
    assert "no resistance training" not in said_with
    assert "no resistance training" in said_without
# ---- #67: the hold tier must not fire on a healthy athlete ---------------------

def _fortnight(**kw):
    return [daily(f"2030-05-{d:02d}", **kw) for d in range(1, 15)]


def test_a_healthy_energy_availability_suppresses_the_balance_fallback():
    """The fallback is documented as covering "no body-composition read". It
    ran whenever the EA branch did not RETURN - including when EA had been
    computed and was fine - so a large measured deficit held an athlete who
    is eating enough (#67).

    The hold tier stops training. An engine that halts a healthy athlete gets
    overridden, and once overridden the tier is dead for the case it exists
    for - which is the real cost, not the false alarm.
    """
    fed = _fortnight(kcal_in=2500, kcal_out=3600)
    body = [weight(f"2030-05-{d:02d}", 75.0, body_fat_pct=20.0)
            for d in range(1, 15)]
    training = [session(f"2030-05-{d:02d}", type="run", duration_s=3600,
                        kcal=700) for d in range(1, 15)]
    stress_note = [medical("2030-05-02", slug="work", kind="symptom",
                           title="Work stress flare-up", body_site=None)]
    rows = escalations(stress_note, fed, body, training, on=date(2030, 5, 14))
    assert [e for e in rows if e["level"] == HOLD] == []


def test_a_genuine_low_energy_presentation_still_holds():
    """The guard must not silence the case the tier exists for."""
    starved = _fortnight(kcal_in=1200, kcal_out=3600)
    body = [weight(f"2030-05-{d:02d}", 55.0, body_fat_pct=14.0)
            for d in range(1, 15)]
    training = [session(f"2030-05-{d:02d}", type="run", duration_s=5400,
                        kcal=900) for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    rows = escalations(injury, starved, body, training, on=date(2030, 5, 14))
    assert any(e["level"] == HOLD for e in rows)


def test_a_null_body_site_does_not_make_every_stress_a_bone_stress():
    """`str(None)` is the string "None", which is truthy - so the body-site
    guard passed for every medical row that omitted a site, and the marker
    collapsed to "stress" in the title."""
    from vitai.safety import _corroborating_markers
    body = [weight(f"2030-05-{d:02d}", 75.0) for d in range(1, 15)]
    days = _fortnight()
    work = [medical("2030-05-02", slug="work", kind="symptom",
                    title="Work stress flare-up", body_site=None)]
    assert _corroborating_markers(days, body, work, date(2030, 5, 1),
                                  date(2030, 5, 14)) == []


def test_a_real_bone_stress_injury_is_still_a_marker():
    from vitai.safety import _corroborating_markers
    body = [weight(f"2030-05-{d:02d}", 75.0) for d in range(1, 15)]
    real = [medical("2030-05-02", slug="tib", kind="injury",
                    title="Tibial stress reaction", body_site="shin")]
    assert "bone-stress injury history" in _corroborating_markers(
        _fortnight(), body, real, date(2030, 5, 1), date(2030, 5, 14))


def test_the_balance_fallback_still_runs_without_a_composition_read():
    """It exists because a record with no body-fat reading would otherwise be
    screened for nothing at all."""
    starved = _fortnight(kcal_in=1200, kcal_out=3600)
    no_composition = [weight(f"2030-05-{d:02d}", 55.0) for d in range(1, 15)]
    training = [session(f"2030-05-{d:02d}", type="run", duration_s=5400,
                        kcal=900) for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    rows = escalations(injury, starved, no_composition, training,
                       on=date(2030, 5, 14))
    assert any(e["level"] == HOLD and "energy balance" in e["detail"]
               for e in rows)


def test_a_healthy_ea_with_a_real_marker_still_clears():
    """This is the test that catches a revert of the EA-branch fix on its own.

    The earlier fixtures could not: with the body-site bug also fixed, the
    marker vanished and the fallback returned empty for that reason instead.
    A genuine marker plus a genuinely healthy EA is the shape that separates
    the two fixes.
    """
    fed = _fortnight(kcal_in=2500, kcal_out=3600)
    body = [weight(f"2030-05-{d:02d}", 75.0, body_fat_pct=20.0)
            for d in range(1, 15)]
    priced = [session(f"2030-05-{d:02d}", type="run", duration_s=3600,
                      kcal=700) for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    rows = escalations(injury, fed, body, priced, on=date(2030, 5, 14))
    assert [e for e in rows if e["level"] == HOLD] == []


def test_ea_does_not_clear_a_hold_when_the_exercise_term_is_incomplete():
    """A session logged with a duration but no energy cost drops out of the
    exercise term, so EA reads healthy when the true one may be far below.

    The first version of the #67 fix cleared on any computable EA, which
    silently stopped holding an athlete who logs how long but not how hard -
    under-triage introduced while fixing over-triage.
    """
    starved = _fortnight(kcal_in=1600, kcal_out=3600)
    body = [weight(f"2030-05-{d:02d}", 55.0, body_fat_pct=14.0)
            for d in range(1, 15)]
    unpriced = [session(f"2030-05-{d:02d}", type="run", duration_s=5400)
                for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    rows = escalations(injury, starved, body, unpriced, on=date(2030, 5, 14))
    assert any(e["level"] == HOLD for e in rows), (
        "an incomplete exercise term must not read as a clean bill of health")


def test_a_modelled_burn_declares_itself_rather_than_being_dropped():
    """#49's harm is an inflated estimate reaching a deficit and reading ON
    TARGET while the scale goes up. But REFUSING to screen when the burn is
    estimated silences RED-S detection for every athlete whose tracker models
    their burn, which is most of them - removing a false positive by creating
    a silence, in the tier where silence is the dangerous direction.

    So it states the basis, which is what #37 and #68 already established.
    """
    starved = _fortnight(kcal_in=1200, kcal_out=3600)
    modelled = [dict(r, modelled="kcal_out") for r in starved]
    body = [weight(f"2030-05-{d:02d}", 55.0) for d in range(1, 15)]
    training = [session(f"2030-05-{d:02d}", type="run", duration_s=5400,
                        kcal=900) for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    rows = escalations(injury, modelled, body, training, on=date(2030, 5, 14))
    held = [e for e in rows if e["level"] == HOLD]
    assert held, "an estimated burn must not silence the screen"
    assert "MODELLED on 14 of 14 days" in held[0]["detail"]


def test_a_measured_burn_carries_no_caveat():
    starved = _fortnight(kcal_in=1200, kcal_out=3600)
    body = [weight(f"2030-05-{d:02d}", 55.0) for d in range(1, 15)]
    training = [session(f"2030-05-{d:02d}", type="run", duration_s=5400,
                        kcal=900) for d in range(1, 15)]
    injury = [medical("2030-05-02", slug="tib", kind="injury",
                      title="Tibial stress reaction", body_site="shin")]
    held = [e for e in escalations(injury, starved, body, training,
                                   on=date(2030, 5, 14)) if e["level"] == HOLD]
    assert held and "MODELLED" not in held[0]["detail"]


# ---- the medical boundary (#110) ------------------------------------------------

# The acute tier, pinned. Changing a byte of either string changes this, so the
# emergency path cannot be edited as a side effect of tidying the others - and
# this issue cannot be used later to argue the acute path away.
ACUTE_DIGEST = "1f2b8100422cea5a4aaeca93a79b0ee56ebc68b98f0752f969d5367311b3fe65"


def test_the_acute_tier_is_unchanged():
    """The carve-out, hash-pinned.

    Calling emergency services is not an appointment: it is an act the person
    can perform immediately, alone, at any hour, with no gatekeeper. That is
    what makes it different from "contact a doctor", and it is why these two
    keep an imperative when nothing else does.

    A test that merely asserted the strings were non-empty would let a future
    tidy-up soften them one word at a time.
    """
    import hashlib

    from vitai.safety import ACUTE, MESSAGES
    # Hashed off MESSAGES, which is what the runtime actually reads
    # (`_escalation` looks up `MESSAGES[trigger]`). Pinning `ACUTE` alone left
    # the hole open: `MESSAGES = {**ACUTE, ...}`, so a softened `"cardiac"`
    # entry later in that literal would change what athletes see while `ACUTE`
    # and the digest stayed byte-identical.
    got = hashlib.sha256(
        "\n".join(f"{k}={MESSAGES[k]}" for k in sorted(ACUTE)).encode()).hexdigest()
    assert got == ACUTE_DIGEST, (
        "the acute tier changed. That is a decision, not a tidy-up - if it is "
        "deliberate, update ACUTE_DIGEST in the same commit and say why")
    assert set(ACUTE) == {"cardiac", "syncope"}
    for key in ACUTE:
        assert MESSAGES[key] == ACUTE[key], (
            f"{key} is overridden after ACUTE is spread into MESSAGES")
        assert "emergency services" in MESSAGES[key]


def test_no_string_outside_the_acute_tier_directs_the_reader_to_care():
    """The acceptance criterion, asserted over the module rather than over
    the constants I happened to think of.

    Nine of thirteen `MESSAGES` used to end by naming an addressee - a doctor,
    a sports physician, a dietitian. That is care NAVIGATION, and it is both
    an open item the record owner cannot close inside the tool and the
    strongest evidence that vitai asserts a medical purpose. Under FDA general
    wellness and MDCG 2019-11 the trigger is the CLAIM, not the technology.

    The earlier version of this test iterated `MESSAGES` only, which is
    exactly why `banner()` kept printing "vitai routes to a clinician and
    stops" through a green build: the removed claim was live on every
    escalation surface and no assertion could see it. So this reads the
    MODULE - every string literal, docstring and comment in safety.py - and
    the acute tier is carved out by VALUE rather than by key name.
    """
    import ast
    import io
    import tokenize
    from pathlib import Path as _P

    from vitai.safety import ACUTE
    directives = ("contact a doctor", "contact a clinician", "contact your",
                  "see a doctor", "see a clinician", "consult a",
                  "get assessed", "get checked", "take this record to",
                  "book an appointment", "tell your clinician",
                  "until a clinician", "dietitian", "sports physician",
                  "referral", "refer to", "routes to a clinician",
                  "route to a clinician", "and see a clinician")
    source = (_P(__file__).resolve().parents[1] / "src" / "vitai"
              / "safety.py").read_text()

    spared = set(ACUTE.values())
    chunks = [node.value for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    chunks += [tok.string for tok in
               tokenize.generate_tokens(io.StringIO(source).readline)
               if tok.type == tokenize.COMMENT]
    for chunk in chunks:
        if chunk in spared:
            continue
        lowered = chunk.lower()
        for phrase in directives:
            assert phrase not in lowered, (
                f"a string in safety.py directs the reader ({phrase!r}): "
                f"{' '.join(chunk.split())[:90]}")


def test_every_message_says_what_vitai_will_not_do():
    """Observation PLUS refusal. An observation alone is a warning that
    leaves the reader to guess what changed; the refusal is the part that is
    about vitai's own behaviour, which is the only thing it can speak to.

    A refusal names something vitai will NOT do. "This restriction is lifted"
    is a permission and used to satisfy this test, which made it satisfiable
    by a message that refused nothing.
    """
    from vitai.safety import ACUTE, MESSAGES
    refusals = ("no training is programmed", "no progression is issued",
                "no plan, progression or session is issued",
                "no plan here will suggest", "is gated", "stays gated",
                "treated as unresolved", "the gate stands")
    for key, text in MESSAGES.items():
        if key in ACUTE:
            continue
        if key == "check_passed":
            # The one message that is legitimately a permission: it announces
            # that a restriction lifted today. Named rather than matched by a
            # loose phrase, so the exception stays visible.
            assert "lifted FOR TODAY" in text
            continue
        assert any(r in text.lower() for r in refusals), (
            f"{key} observes something and never says what vitai will not do")


def test_every_level_has_an_exit_the_record_owner_can_reach():
    """A gate whose exit is "a clinician has reviewed you" is a wall: the
    record owner cannot reach it through the tool, so the state is permanent
    as far as anything here can tell - and a permanent warning is one that
    gets dismissed.

    Asserted over `LEVEL_ORDER` so a new level cannot be added without
    answering the question.
    """
    from vitai.safety import LEVEL_EXITS, LEVEL_ORDER
    assert set(LEVEL_EXITS) == set(LEVEL_ORDER)
    for level, exit_condition in LEVEL_EXITS.items():
        assert exit_condition, level
        assert "clinician has reviewed" not in exit_condition, level


def test_recording_a_resolution_actually_exits_the_state():
    """The prose above promises "the episode is recorded as resolved" exits
    both blocking levels. It did not: both red-flag paths and the prose
    scanner iterated the RAW medical rows, so a flag recorded once fired
    forever and the athlete had no exit through the record at all.

    Asserted as BEHAVIOUR, because the previous test proves only that a
    sentence exists.
    """
    episode = {"date": "2030-01-01", "slug": "chest", "title": "chest pain",
               "kind": "symptom", "status": "active", "resolved_date": None,
               "severity": "red_flag", "body_site": "chest",
               "restricts": None, "provider_type": None, "source": None,
               "note": None, "onset_date": None, "precondition": None}
    while_open = escalations([episode], [], [], [], on="2030-01-03")
    assert {r["level"] for r in while_open} & {EMERGENCY, URGENT}

    resolved = {**episode, "status": "resolved",
                "resolved_date": "2030-01-05"}
    assert escalations([resolved], [], [], [], on="2030-12-31") == [], (
        "recording the resolution exited nothing - the state is a wall")
    # And it still fires for the days it was genuinely open.
    assert escalations([resolved], [], [], [], on="2030-01-03")


def test_a_note_the_athlete_wrote_does_not_stop_having_been_written():
    """The counterpart, so the fix above cannot be widened into silence: a
    `daily` or `sessions` note is not an episode and has no resolution to
    read. Closing an episode must not retract a symptom described elsewhere.
    """
    rows = escalations([], [daily(date="2030-05-10", note="chest pain on the "
                                  "stairs today")], [], [], on="2030-12-31")
    assert any(r["trigger"] == "cardiac" for r in rows)


def test_a_visit_dated_after_it_was_written_is_an_appointment():
    """A `visit` records a visit that HAPPENED. A row dated later than the
    line was written is an appointment, which is a plan - and vitai does not
    own the record owner's plans for their own body.

    Measured against the record's OWN clocks, not against today: comparing to
    `date.today()` would make a row valid this morning and invalid tomorrow,
    which breaks determinism and would fail every 2030-dated fixture here for
    being prescient.
    """
    from vitai.schema import validate_record
    base = {"slug": "gp", "title": "GP", "kind": "visit", "status": "active",
            "severity": "mild", "note": None, "body_site": None,
            "restricts": None, "resolved_date": None, "provider_type": None,
            "source": None}
    appointment = {**base, "date": "2030-06-01",
                   "recorded_at": "2030-05-01T10:00:00+02:00"}
    assert any("appointment" in p for p in
               validate_record("medical", appointment))

    happened = {**base, "date": "2030-05-01",
                "recorded_at": "2030-05-01T18:00:00+02:00"}
    assert not any("appointment" in p for p in
                   validate_record("medical", happened))

    # A row predating the clocks cannot be judged, and guessing would
    # retroactively invalidate history.
    legacy = {**base, "date": "2030-06-01", "recorded_at": None}
    assert not any("appointment" in p for p in validate_record("medical", legacy))


def test_the_standing_disclaimer_is_present_and_never_fires(tmp_path, capsys):
    """Tier 1: it carries the legal weight precisely BECAUSE it never
    interrupts. A disclaimer that fires gets dismissed."""
    from vitai.cli import main
    from vitai.safety import DISCLAIMER
    assert "not a medical device" in DISCLAIMER
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text(
        '{"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": null}\n',
        encoding="utf-8")
    capsys.readouterr()
    main(["status", "--root", str(root)])
    assert DISCLAIMER in capsys.readouterr().out


def test_no_message_the_athlete_reads_names_a_condition():
    """Class (c) of the boundary doctrine, which had no guard until now.

    #133 asserted class (d), care directives, across the whole module and that
    test worked. `MESSAGES["red_s"]` still sat there naming a syndrome outright
    ("a low-energy-availability pattern (RED-S) ... this is the syndrome") and
    passed, because it contained no addressee. Two things hid it: the test
    looked for the wrong class, and the string was UNREACHABLE, since nothing
    ever emitted `trigger == "red_s"`, so no behavioural test could see it
    either. Dead code in a constants table is not inert; it is a claim waiting
    for someone to wire it up.

    Scoped to what the athlete READS, deliberately. Describing an observable
    state is fine and `clinical_hold` does it: "low energy availability
    alongside other findings" is a pattern in the record. Naming the syndrome
    is a diagnosis whoever says it. Source comments citing the literature to
    justify a threshold are engineering rationale and are covered by the
    capability test below instead, because the problem with a comment is never
    that it names a condition, it is that it claims the engine chases one.
    """
    from vitai.safety import ACUTE, MESSAGES
    named = ("red-s", "relative energy deficiency", "the syndrome",
             "a syndrome", "osteoporosis", "anorexia", "bulimia",
             "atrial fibrillation", "diabetes", "hypertension",
             "anaemia", "anemia")
    for key, text in {**MESSAGES, **ACUTE}.items():
        lowered = text.lower()
        for phrase in named:
            assert phrase not in lowered, (
                f"{key} names a condition ({phrase!r}). Describe what the "
                "record shows; naming it is a diagnosis.")


def test_the_module_never_claims_to_watch_for_anything():
    """Class (e), capability claims, over every string AND comment.

    Found live by the class (c) guard above: a section header read "it is the
    engine's job to watch for it rather than the athlete's". Monitoring for a
    named condition is the strongest single assertion of a medical purpose a
    file can make, and it is worse in a comment than in a message, because a
    comment reads as the authors describing what they built.

    The engine does not watch for anything. It states what the record shows
    and declines to issue a plan.
    """
    import io
    import tokenize
    from pathlib import Path as _P

    claims = ("job to watch for", "watch for it", "watches for", "we detect",
              "detects ", "screens for", "screening for", "monitors ",
              "owes a duty", "duty to watch")
    source = (_P(__file__).resolve().parents[1] / "src" / "vitai"
              / "safety.py").read_text(encoding="utf-8")
    comments = [t.string for t in
                tokenize.generate_tokens(io.StringIO(source).readline)
                if t.type == tokenize.COMMENT]
    for chunk in comments + [source]:
        lowered = chunk.lower()
        for phrase in claims:
            assert phrase not in lowered, (
                f"safety.py claims a capability: {phrase!r}. The engine "
                "states what the record shows and declines to program.")


def test_every_message_is_reachable():
    """The structural half, and the reason the above went unnoticed for so long.

    `_escalation` looks up `MESSAGES[trigger]`, so a key no trigger emits can
    never be read. An unreachable entry looks like coverage in review and is
    worth nothing at runtime, which is the worst combination available.
    """
    import re
    from pathlib import Path as _P

    from vitai.safety import MESSAGES
    source = (_P(__file__).resolve().parents[1] / "src" / "vitai"
              / "safety.py").read_text(encoding="utf-8")
    quoted = set(re.findall(r"[\"'](\w+)[\"']", source))
    for key in MESSAGES:
        # Every live key is named somewhere other than its own definition:
        # emitted as a trigger, or looked up explicitly.
        uses = len(re.findall(rf"[\"']{re.escape(key)}[\"']", source))
        assert uses > 1 or key in quoted, f"{key!r} is defined and never used"
