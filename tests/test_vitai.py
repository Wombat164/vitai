"""Engine tests - synthetic data only (public repo: no real measurements)."""

import json
from datetime import date
from pathlib import Path

import pytest

from vitai.cli import main
from vitai.config import Config, load_config, phase_rate_for
from vitai.jsonl import DataError, load, read_lines
from vitai.report import build_report
from vitai.schema import validate_record

TODAY = date(2030, 6, 1)


def write(p: Path, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


# ---- jsonl: append-only + supersedes ----------------------------------------

def test_supersedes_drops_original(tmp_path):
    write(tmp_path / "weight.jsonl", [
        {"date": "2030-05-01", "kg": 80.0, "source": "app", "note": None},
        {"date": "2030-05-01", "kg": 80.4, "source": "scale",
         "supersedes": "2030-05-01/app", "note": "recalibrated"},
    ])
    recs = load(tmp_path, "weight")
    assert len(recs) == 1
    assert recs[0]["kg"] == 80.4


def test_comment_and_blank_lines_skipped(tmp_path):
    (tmp_path / "weight.jsonl").write_text(
        "// comment\n\n" + json.dumps({"date": "2030-05-01", "kg": 80.0,
                                       "source": "app", "note": None}) + "\n",
        encoding="utf-8")
    assert len(load(tmp_path, "weight")) == 1


def test_malformed_line_reports_position(tmp_path):
    (tmp_path / "weight.jsonl").write_text('{"date": broken\n', encoding="utf-8")
    with pytest.raises(DataError, match="line 1"):
        read_lines(tmp_path / "weight.jsonl")


def test_missing_file_is_empty(tmp_path):
    assert load(tmp_path, "weight") == []


# ---- schema ------------------------------------------------------------------

def test_validate_catches_missing_and_unknown_keys():
    problems = validate_record("weight", {"date": "2030-05-01", "kg": 80.0,
                                          "source": "app", "extra": 1})
    assert any("missing key 'note'" in p for p in problems)
    assert any("unknown key 'extra'" in p for p in problems)


def test_validate_types_and_enums():
    rec = {"date": "not-a-date", "type": "swim", "distance_km": "far",
           "duration_s": None, "avg_hr": None, "max_hr": None, "cadence": None,
           "kcal": None, "location": None, "rpe": None, "note": None}
    problems = validate_record("sessions", rec)
    assert any("bad date" in p for p in problems)
    assert any("'type' must be one of" in p for p in problems)
    assert any("'distance_km'" in p for p in problems)


def test_validate_supersedes_key_is_legal():
    rec = {"date": "2030-05-01", "kg": 80.0, "source": "app", "note": None,
           "supersedes": "2030-04-30/app"}
    assert validate_record("weight", rec) == []


# ---- config ------------------------------------------------------------------

def test_config_defaults_when_absent(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.phases == () and cfg.easy_hr_cap is None


def test_phase_rate_selection(tmp_path):
    (tmp_path / "vitai.toml").write_text(
        "[targets]\nphases = [[80.0, 76.0, 0.7], [76.0, 73.0, 0.5]]\n"
        "[tripwires]\neasy_hr_cap = 150\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert phase_rate_for(cfg, 78.0) == 0.7
    assert phase_rate_for(cfg, 74.0) == 0.5
    assert phase_rate_for(cfg, 60.0) == 0.5  # below all phases -> last rate
    assert cfg.easy_hr_cap == 150
    assert phase_rate_for(Config(), 78.0) is None


# ---- report ------------------------------------------------------------------

def _weights(kgs, start_day=1):
    return [{"date": f"2030-05-{start_day + i:02d}", "kg": kg, "source": "app",
             "note": None} for i, kg in enumerate(kgs)]


def test_report_rate_verdict_on_target():
    cfg = Config(phases=((80.0, 70.0, 0.7),))
    # ~0.1 kg/day fall -> 0.7 kg/week
    weight = _weights([round(78.0 - 0.1 * i, 1) for i in range(10)])
    out = build_report(cfg, weight, [], [], today=TODAY)
    assert "ON TARGET" in out


def test_report_easy_cap_flag():
    cfg = Config(easy_hr_cap=150)
    sessions = [{"date": "2030-05-05", "type": "run", "distance_km": 5.0,
                 "duration_s": 1800, "avg_hr": 168, "max_hr": None,
                 "cadence": None, "kcal": None, "location": None, "rpe": None,
                 "note": None}]
    out = build_report(cfg, [], [], sessions, today=TODAY)
    assert "OVER +18" in out


def test_report_tripwires_disabled_without_config():
    daily = [{"date": "2030-05-05", "steps": 3000, "distance_km": None,
              "active_min": None, "kcal_out": None, "kcal_in": None,
              "protein_g": None, "sleep_h": 5.0, "rhr": 70, "hip_pain": 9,
              "alcohol": False, "note": None}] * 3
    out = build_report(Config(), [], daily, [], today=TODAY)
    assert "Nothing firing." in out


def test_report_pain_gate_fires():
    cfg = Config(pain_gate=3)
    daily = [{"date": "2030-05-05", "steps": None, "distance_km": None,
              "active_min": None, "kcal_out": None, "kcal_in": None,
              "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": 6,
              "alcohol": None, "note": None}]
    out = build_report(cfg, [], daily, [], today=TODAY)
    assert "gate fired" in out


def test_report_deterministic():
    cfg = Config(phases=((80.0, 70.0, 0.7),), easy_hr_cap=150)
    weight = _weights([78.0, 77.9, 77.8])
    a = build_report(cfg, weight, [], [], today=TODAY)
    b = build_report(cfg, weight, [], [], today=TODAY)
    assert a == b


# ---- cli end-to-end ----------------------------------------------------------

def test_init_build_validate_status(tmp_path, capsys):
    root = tmp_path / "content"
    main(["init", str(root)])
    assert (root / "vitai.toml").exists()
    assert (root / "profile.md").exists()
    assert (root / "data" / "weight.jsonl").exists()

    write(root / "data" / "weight.jsonl",
          [{"date": "2030-05-01", "kg": 80.0, "source": "app", "note": None}])
    main(["validate", "--root", str(root)])
    main(["build", "--root", str(root)])
    assert (root / "derived" / "health.db").exists()
    weekly = (root / "derived" / "weekly.md").read_text(encoding="utf-8")
    assert "80.0" in weekly

    main(["status", "--root", str(root)])
    out = capsys.readouterr().out
    assert "80.0 kg" in out


def test_init_refuses_nonempty(tmp_path):
    target = tmp_path / "content"
    target.mkdir()
    (target / "something.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["init", str(target)])


def test_validate_fails_on_bad_line(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    write(root / "data" / "weight.jsonl",
          [{"date": "2030-05-01", "kg": "heavy", "source": "app", "note": None}])
    with pytest.raises(SystemExit):
        main(["validate", "--root", str(root)])
