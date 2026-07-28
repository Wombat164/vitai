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


# ---- inferences schema (third data tier) ------------------------------------

def _inf(**over):
    rec = {"date": "2030-05-01", "kind": "pattern", "statement": "x correlates y",
           "confidence": 0.7, "model": "test-model", "evidence": "2030-04/daily",
           "note": None}
    rec.update(over)
    return rec


def test_inference_record_valid():
    assert validate_record("inferences", _inf()) == []


def test_inference_record_rejects_bad_kind_and_confidence():
    problems = validate_record("inferences", _inf(kind="prophecy", confidence=3))
    assert any("'kind'" in p for p in problems)
    assert any("'confidence'" in p for p in problems)


def test_inference_record_requires_statement_and_model():
    problems = validate_record("inferences", _inf(statement="", model=None))
    assert any("'statement'" in p for p in problems)
    assert any("'model'" in p for p in problems)


# ---- verdicts (the platform contract) ---------------------------------------

def test_verdicts_weight_rate_on_target():
    from vitai.verdicts import compute_verdicts
    cfg = Config(phases=((80.0, 70.0, 0.7),))
    # week 1 mean 78.0, week 2 mean 77.3 -> rate 0.7 => on_target
    weight = ([{"date": f"2030-05-0{i}", "kg": 78.0, "source": "a", "note": None}
               for i in range(1, 6)] +
              [{"date": f"2030-05-0{i}", "kg": 77.3, "source": "a", "note": None}
               for i in range(8, 10)])
    rows = compute_verdicts(cfg, weight, [], [], today=TODAY)
    rate_rows = [r for r in rows if r["metric"] == "weight_rate" and r["verdict"] != "no_data"]
    assert rate_rows and rate_rows[-1]["verdict"] == "on_target"
    assert rate_rows[-1]["target"] == 0.7


def test_verdicts_easy_hr_and_steps():
    from vitai.verdicts import compute_verdicts
    cfg = Config(easy_hr_cap=150, steps_floor=10000)
    sessions = [{"date": "2030-05-06", "type": "run", "distance_km": 5.0,
                 "duration_s": 1800, "avg_hr": 160, "max_hr": None, "cadence": None,
                 "kcal": None, "location": None, "rpe": None, "note": None}]
    daily = [{"date": "2030-05-06", "steps": 12000, "distance_km": None,
              "active_min": None, "kcal_out": None, "kcal_in": None,
              "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": None,
              "alcohol": None, "note": None}]
    rows = compute_verdicts(cfg, [], daily, sessions, today=TODAY)
    by_metric = {r["metric"]: r for r in rows}
    assert by_metric["easy_hr"]["verdict"] == "behind"
    assert by_metric["steps"]["verdict"] == "on_target"


def test_verdicts_deterministic():
    from vitai.verdicts import compute_verdicts
    cfg = Config(phases=((80.0, 70.0, 0.7),), steps_floor=8000)
    weight = _weights([78.0, 77.9, 77.8])
    assert (compute_verdicts(cfg, weight, [], [], today=TODAY)
            == compute_verdicts(cfg, weight, [], [], today=TODAY))


# ---- library API + verdicts table in the read model -------------------------

def test_api_build_projects_verdicts_and_contract(tmp_path):
    import sqlite3

    from vitai.api import Vitai
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "vitai.toml").write_text(
        "[targets]\nphases = [[80.0, 70.0, 0.7]]\n[tripwires]\nsteps_floor = 8000\n",
        encoding="utf-8")
    write(root / "data" / "weight.jsonl",
          [{"date": "2030-05-01", "kg": 78.0, "source": "a", "note": None},
           {"date": "2030-05-08", "kg": 77.3, "source": "a", "note": None}])
    write(root / "data" / "inferences.jsonl", [_inf()])
    v = Vitai(root)
    db = v.build()
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"weight", "daily", "sessions", "inferences", "verdicts", "meta"} <= tables
    assert con.execute("SELECT COUNT(*) FROM inferences").fetchone()[0] == 1
    assert con.execute("SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "1"
    con.close()
    assert v.status_line().startswith("77.3 kg")
    assert isinstance(v.verdicts(), list)


def test_api_rejects_non_repo(tmp_path):
    from vitai.api import Vitai
    with pytest.raises(FileNotFoundError):
        Vitai(tmp_path / "nowhere")


# ---- inference runner (fake backend, no network) ----------------------------

def test_run_inference_validates_and_rejects(tmp_path):
    from datetime import date as _date

    from vitai.inference import parse_inferences, run_inference

    class FakeBackend:
        name = "fake"

        def complete(self, prompt):
            assert "WEEKLY ROLLUP" in prompt
            good = json.dumps(_inf(model="fake"))
            bad = json.dumps({"date": "2030-05-01", "kind": "prophecy",
                              "statement": "doom", "confidence": 9,
                              "model": "fake", "evidence": None, "note": None})
            return good + "\nnot json at all\n" + bad

    valid, errors = run_inference(tmp_path, FakeBackend(), "rollup text", [], [],
                                  [], _date(2030, 5, 1))
    assert len(valid) == 1 and valid[0]["kind"] == "pattern"
    assert len(errors) == 1  # bad record; the non-JSON prose line is skipped silently

    # defaults fill date/model/note
    v2, _ = parse_inferences(
        '{"kind":"question","statement":"why","confidence":null,"evidence":null}',
        "2030-05-02", "fake")
    assert v2 and v2[0]["date"] == "2030-05-02" and v2[0]["model"] == "fake"


def test_infer_cli_requires_optin(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    with pytest.raises(SystemExit, match="opt-in"):
        main(["infer", "--root", str(root)])
