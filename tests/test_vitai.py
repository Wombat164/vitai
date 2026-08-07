"""Engine tests - synthetic data only (public repo: no real measurements)."""

import json
from datetime import date
from pathlib import Path

import pytest

from vitai.cli import main
from vitai.config import Config, load_config, phase_rate_for
from vitai.db import CONTRACT_VERSION
from vitai.jsonl import load, load_report, read_lines
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
    # G26: read_lines quarantines the bad line and reports it, never raises.
    (tmp_path / "weight.jsonl").write_text('{"date": broken\n', encoding="utf-8")
    rows, errors = read_lines(tmp_path / "weight.jsonl")
    assert rows == []
    assert len(errors) == 1 and "line 1" in errors[0]


def test_one_bad_line_does_not_abort_the_rest(tmp_path):
    # G26: one bad byte must not silence the whole build - good rows survive.
    (tmp_path / "weight.jsonl").write_text(
        json.dumps({"date": "2030-05-01", "kg": 80.0, "source": "a", "note": None})
        + "\n{ this is not json\n"
        + json.dumps({"date": "2030-05-02", "kg": 79.9, "source": "a", "note": None})
        + "\n", encoding="utf-8")
    records, errors = load_report(tmp_path, "weight")
    assert [r["kg"] for r in records] == [80.0, 79.9]  # both good rows kept
    assert len(errors) == 1  # the bad line quarantined, reported


def test_missing_file_is_empty(tmp_path):
    assert load(tmp_path, "weight") == []


# ---- schema ------------------------------------------------------------------

def test_validate_catches_missing_and_unknown_keys():
    problems = validate_record("weight", {"date": "2030-05-01", "kg": 80.0,
                                          "source": "app", "extra": 1})
    assert any("missing key 'note'" in p for p in problems)
    assert any("unknown key 'extra'" in p for p in problems)


def test_validate_types_and_enums():
    # `swim` used to be the invalid example here, which was the defect: an
    # engine whose session vocabulary rejects swimming is a sample of one
    # athlete, not a taxonomy (G85). It is valid now, so the invalid case has
    # to be something genuinely outside the registry.
    rec = {"date": "not-a-date", "type": "interpretive dance",
           "distance_km": "far",
           "duration_s": None, "avg_hr": None, "max_hr": None, "cadence": None,
           "kcal": None, "location": None, "rpe": None, "note": None}
    problems = validate_record("sessions", rec)
    assert any("bad date" in p for p in problems)
    assert any("'type' must be one of" in p for p in problems)
    assert any("'distance_km'" in p for p in problems)


def test_the_session_vocabulary_covers_sports_the_author_does_not_do():
    """The G85 regression: cycling, swimming, rowing and climbing collapsed to
    `other` because the author did not do them."""
    ok = {"date": "2030-05-01", "distance_km": None, "duration_s": None,
          "avg_hr": None, "max_hr": None, "cadence": None, "kcal": None,
          "location": None, "rpe": None, "note": None}
    for kind in ("cycle", "swim", "row", "climb", "sport", "paddle",
                 "wintersport", "mobility", "strength"):
        assert validate_record("sessions", {**ok, "type": kind}) == [], kind


def test_validate_supersedes_key_is_legal():
    rec = {"date": "2030-05-01", "kg": 80.0, "source": "app", "note": None,
           "supersedes": "2030-04-30/app"}
    assert validate_record("weight", rec) == []


# ---- schema generations (G25) - the shape-history-stability regression ------

def test_additive_field_does_not_invalidate_old_lines():
    """THE bug the whole-model redteam found: adding a nullable field in a
    later generation must NOT make every pre-existing line fail validation.

    Increment 2 made this real rather than simulated - `mood` and the rest of
    the gen-2 daily fields are now in the live schema, so this asserts against
    it directly.
    """
    old_line = {"date": "2030-05-01", "steps": 8000, "distance_km": None,
                "active_min": None, "kcal_out": None, "kcal_in": None,
                "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": None,
                "alcohol": None, "note": None}  # gen 1, no gen-2 keys at all
    assert validate_record("daily", old_line) == []  # NOT "missing key 'mood'"

    new_line = {**old_line, "_gen": 2, "source": None, "mood": 7, "feel": None,
                "coverage": None, "pain": None, "pain_site": None,
                "pain_side": None}
    del new_line["hip_pain"]  # retired at gen 2; a new line need not carry it
    assert validate_record("daily", new_line) == []

    # A gen-2 line that OMITS a gen-2 key IS flagged (the rule still bites for
    # keys that existed at the line's own generation).
    missing = {**old_line, "_gen": 2}
    assert any("mood" in p for p in validate_record("daily", missing))


def test_retired_key_stays_legal_but_stops_being_required():
    """`hip_pain` was replaced by `pain`+`pain_site`, not deleted: a line that
    still carries it is history, not an error."""
    gen1 = {"date": "2030-05-01", "steps": 8000, "distance_km": None,
            "active_min": None, "kcal_out": None, "kcal_in": None,
            "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": 2,
            "alcohol": None, "note": None}
    assert validate_record("daily", gen1) == []
    # ...and a gen-2 line may still carry it without complaint.
    gen2 = {**gen1, "_gen": 2, "source": None, "mood": None, "feel": None,
            "coverage": None, "pain": None, "pain_site": None,
            "pain_side": None}
    assert validate_record("daily", gen2) == []


def test_gen_marker_must_be_positive_int():
    rec = {"date": "2030-05-01", "kg": 80.0, "source": "app", "note": None,
           "_gen": "two"}
    assert any("_gen" in p for p in validate_record("weight", rec))


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


def test_rolling_window_is_calendar_days_not_entries():
    """G30: a '7d avg' must average the last 7 CALENDAR days, not the last 7
    weigh-ins. Sparse logging (one entry every 5 days) must NOT reach back weeks."""
    from vitai.report import _rolling
    # entries 10 days apart: a 7-day window catches ONLY the point itself,
    # never an earlier entry - so each rolling avg equals that day's value.
    pts = [("2030-05-01", 80.0), ("2030-05-11", 79.0),
           ("2030-05-21", 78.0), ("2030-05-31", 77.0)]
    roll = dict(_rolling(pts, window=7))
    assert roll["2030-05-31"] == 77.0            # itself alone in the 7d window
    assert roll["2030-05-21"] == 78.0
    # entry-count slicing (last <=7 entries = all 4) would give 78.5 here
    assert roll["2030-05-31"] != 78.5


def test_rate_ignores_stale_gap():
    """G30: with a long logging gap, the rate compares calendar-separated
    windows, not the 8th-from-last entry (which could be a month back)."""
    cfg = Config(phases=((80.0, 70.0, 0.5),))
    # a dense recent week losing ~0.5/wk, preceded by a stale cluster 40 days back
    stale = [{"date": f"2030-04-0{i}", "kg": 80.0, "source": "a", "note": None}
             for i in range(1, 4)]
    recent = [{"date": f"2030-05-{10 + i:02d}", "kg": round(78.0 - 0.07 * i, 2),
               "source": "a", "note": None} for i in range(8)]
    out = build_report(cfg, stale + recent, [], [], today=date(2030, 5, 20))
    # the old code would span 05-17 back to 04-03 (44 days) and mangle the rate;
    # the calendar version anchors ~7 days back and produces a sane weekly rate line
    assert "**Rate:**" in out


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


def _pain_day(date, score):
    return {"date": date, "steps": None, "distance_km": None,
            "active_min": None, "kcal_out": None, "kcal_in": None,
            "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": score,
            "alcohol": None, "note": None}


def test_report_pain_gate_fires():
    """Dated INSIDE the window. This fixture used to sit 27 days before
    `TODAY` and fired anyway, because the tripwire took the last seven rows
    that happened to carry pain rather than the last seven days (#68)."""
    cfg = Config(pain_gate=3)
    out = build_report(cfg, [], [_pain_day("2030-05-30", 6)], [], today=TODAY)
    assert "gate fired" in out


def test_report_pain_gate_does_not_fire_on_a_stale_reading():
    """A pain score from four weeks ago is not a fact about this week. The
    persistent case is what `medical` gates are for; this tripwire reports
    RECENT pain, and reporting an old reading as current is the same defect
    as a 170-day rate."""
    cfg = Config(pain_gate=3)
    out = build_report(cfg, [], [_pain_day("2030-05-05", 6)], [], today=TODAY)
    assert "gate fired" not in out


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
    assert {"weight", "daily", "sessions", "inferences", "verdicts", "meta",
            "goals", "thresholds", "achievements", "contributions",
            "milestones", "plan_churn", "goal_progress",
            "measurements", "context", "claims", "resolution",
            "justifications", "conservation", "retractions",
            "medical", "gates", "escalations", "checks"} <= tables
    assert con.execute("SELECT COUNT(*) FROM inferences").fetchone()[0] == 1
    assert con.execute(
        "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == CONTRACT_VERSION
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


# ---- journal: what the athlete SAID (G43 capture) ---------------------------

def _journal(**kw):
    rec = {k: None for k in ["date", "kind", "text", "about", "source",
                             "confidence", "status", "note"]}
    rec.update(kw)
    return rec


def test_journal_entry_validates():
    rec = _journal(date="2030-05-01", kind="worry", text="hip not assessed",
                   about="hip-gate", source="stated-in-chat", confidence=1.0,
                   status="open")
    assert validate_record("journal", rec) == []


def test_journal_text_may_not_be_empty():
    """An entry with no words is not an entry - the text IS the datum."""
    rec = _journal(date="2030-05-01", kind="note", text="   ")
    assert any("text" in p for p in validate_record("journal", rec))


def test_journal_kind_is_a_closed_vocabulary():
    rec = _journal(date="2030-05-01", kind="rant", text="something")
    assert any("kind" in p for p in validate_record("journal", rec))


def test_journal_confidence_is_firmness_not_truth():
    """0-1, and out of range is an error - it records how firmly a thing was
    said, never how likely it is to be true."""
    rec = _journal(date="2030-05-01", kind="idea", text="maybe a half marathon",
                   confidence=1.4)
    assert any("confidence" in p for p in validate_record("journal", rec))


def test_a_goal_may_be_proposed_but_not_committed():
    """A grain of a goal. Without this status a musing has nowhere to live but
    prose, and the coach cannot tell an aspiration from a decision."""
    from vitai.schema import GOAL_STATUSES
    assert "proposed" in GOAL_STATUSES


def test_journal_reads_back_through_the_api(tmp_path):
    """P9: the capability exists on the API, not only in the CLI."""
    from vitai.api import Vitai
    (tmp_path / "data").mkdir()
    (tmp_path / "vitai.toml").write_text('[athlete]\nname = "t"\n', encoding="utf-8")
    rows = [
        _journal(date="2030-05-01", kind="worry", text="knee twinge",
                 about="knee", status="open"),
        _journal(date="2030-05-02", kind="idea", text="try a 10k", status="open"),
        _journal(date="2030-05-03", kind="worry", text="old worry",
                 status="resolved"),
    ]
    (tmp_path / "data" / "journal.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    v = Vitai(tmp_path)
    assert len(v.journal()) == 3
    assert len(v.journal(kind="worry")) == 2
    assert len(v.journal(about="knee")) == 1
    # a resolved worry is not an open one
    assert [r["text"] for r in v.open_worries()] == ["knee twinge"]


# ---- #68: a span is not a week, and a slice is not a window --------------------

def _kg(date, kg):
    return {"date": date, "kg": kg, "source": "scale", "note": None}


def test_a_rate_across_a_multi_month_hole_is_refused():
    """Live: the rollup printed "gaining 0.28 kg/week" from two readings 170
    days apart, to an athlete in a cut - who would reasonably conclude the cut
    had failed. The right output is not a different number, it is a refusal
    that says why."""
    weights = [_kg("2026-02-07", 82.0), _kg("2026-07-27", 82.5)]
    out = build_report(Config(), weights, [], [], today=date(2026, 7, 27))
    assert "NOT READABLE" in out
    assert "170 days apart" in out
    for word in ("gaining", "losing"):
        assert f"**Rate:** {word}" not in out


def test_a_rate_over_a_real_week_is_unqualified():
    weights = [_kg(f"2026-07-{d:02d}", 83.0 - 0.05 * d) for d in range(14, 28)]
    out = build_report(Config(), weights, [], [], today=date(2026, 7, 27))
    assert "**Rate:** losing" in out
    assert "NOT READABLE" not in out
    assert "thin sample" not in out


def test_a_stretched_but_usable_span_declares_itself():
    """G27's maturity signal, applied to the line the athlete actually reads
    rather than only to `ramp`."""
    weights = [_kg("2026-07-16", 83.0), _kg("2026-07-27", 82.5)]
    out = build_report(Config(), weights, [], [], today=date(2026, 7, 27))
    assert "over 11 days" in out and "thin sample" in out


def test_step_average_is_a_calendar_window_not_a_row_slice():
    """With three step rows in eighteen months, "the last 14 logged days"
    spanned January 2025 to July 2026 and printed as a current average."""
    daily = [{"date": d, "steps": s, "distance_km": None, "active_min": None,
              "kcal_out": None, "kcal_in": None, "protein_g": None,
              "sleep_h": None, "rhr": None, "hip_pain": None, "alcohol": None,
              "note": None}
             for d, s in [("2025-01-10", 20000), ("2025-06-02", 18000),
                          ("2026-07-26", 4000)]]
    out = build_report(Config(), [], daily, [], today=date(2026, 7, 27))
    assert "4,000/day average" in out, "only the in-window row may count"
    assert "3 days logged in total" in out, "the total is still the total"


def test_an_empty_window_says_so_rather_than_averaging_old_rows():
    daily = [{"date": "2025-01-10", "steps": 20000, "distance_km": None,
              "active_min": None, "kcal_out": None, "kcal_in": None,
              "protein_g": None, "sleep_h": None, "rhr": None,
              "hip_pain": None, "alcohol": None, "note": None}]
    out = build_report(Config(), [], daily, [], today=date(2026, 7, 27))
    assert "nothing logged in the last 14 days" in out
    assert "20,000" not in out


def test_a_stale_rhr_does_not_raise_a_current_tripwire():
    old = [{"date": f"2025-01-{d:02d}", "steps": None, "distance_km": None,
            "active_min": None, "kcal_out": None, "kcal_in": None,
            "protein_g": None, "sleep_h": None, "rhr": 70, "hip_pain": None,
            "alcohol": None, "note": None} for d in range(1, 5)]
    out = build_report(Config(rhr_baseline=50), [], old, [],
                       today=date(2026, 7, 27))
    assert "Resting HR" not in out


def test_an_unresolved_pain_reading_does_not_go_silent():
    """A calendar window is right for "is this current", and wrong as a way
    to make an unresolved reading disappear. Someone who logs pain only when
    it happens would have had an 8/10 vanish on day eight with no trace."""
    out = build_report(Config(pain_gate=3), [], [_pain_day("2030-05-05", 8)],
                       [], today=TODAY)
    assert "gate fired" not in out, "27 days ago is not a current gate"
    assert "last logged 27 days ago" in out
    assert "never recorded as resolved" in out


def test_a_row_dated_after_the_report_is_reported_not_dropped():
    """A device with a skewed clock writing tomorrow's date would have taken
    a reading out of every window it belongs to, silently."""
    future = _pain_day("2030-06-05", 8)
    out = build_report(Config(pain_gate=3), [], [future], [], today=TODAY)
    assert "check the source's clock" in out


def test_an_unparseable_date_is_reported_not_dropped():
    out = build_report(Config(rhr_baseline=50), [],
                       [{"date": "not-a-date", "steps": None,
                         "distance_km": None, "active_min": None,
                         "kcal_out": None, "kcal_in": None, "protein_g": None,
                         "sleep_h": None, "rhr": 70, "hip_pain": None,
                         "alcohol": None, "note": None}], [], today=TODAY)
    assert "cannot read" in out


def test_an_unranked_source_term_is_a_validation_finding(tmp_path):
    """The second live instance: `context.jsonl` wrote `source:
    "stated-in-chat"`, the daily ladder had never heard of it, so it fell to
    last place and a 20,336-step day resolved its burn to a vendor's figure
    over the athlete's own. That day flipped from a reported surplus to a
    deficit.

    An unranked term is almost always a typo or a term missing from config,
    not a deliberate demotion to worst-in-the-record.
    """
    from vitai.schema import unranked_source_problems
    rows = [(1, {"date": "2026-07-28", "kg": 80.0, "source": "stated-in-chat"}),
            (2, {"date": "2026-07-29", "kg": 79.9, "source": "scale"})]
    found = unranked_source_problems("weight", rows, {"scale", "watch"})
    assert len(found) == 1
    assert "stated-in-chat" in found[0] and "sorts below" in found[0]


def test_a_ranked_source_is_not_a_finding():
    from vitai.schema import unranked_source_problems
    rows = [(1, {"date": "2026-07-28", "kg": 80.0, "source": "scale"})]
    assert unranked_source_problems("weight", rows, {"scale"}) == []


def test_no_ladder_configured_means_no_finding():
    """An unconfigured record is not misconfigured - it has simply not made
    the choice yet, and shouting at it on every line would be noise."""
    from vitai.schema import unranked_source_problems
    rows = [(1, {"date": "2026-07-28", "kg": 80.0, "source": "anything"})]
    assert unranked_source_problems("weight", rows, set()) == []
def test_an_impossible_claim_is_a_validation_finding():
    """A scale reporting distance is not a contest to adjudicate - it is a
    row that cannot be true as written, and `source` being free text meant
    nothing knew a scale from a watch (#79)."""
    from vitai.schema import impossible_claim_problems
    rows = [(1, {"date": "2030-05-01", "kg": 80.0, "source": "fitbit aria"}),
            (2, {"date": "2030-05-02", "kg": 80.0, "source": "fitbit aria",
                 "steps": 9000})]
    found = impossible_claim_problems("weight", rows)
    assert len(found) == 0, "weight carries no steps column to claim"
    daily = [(1, {"date": "2030-05-01", "steps": 9000, "distance_km": 4.2,
                  "source": "fitbit aria"})]
    found = impossible_claim_problems("daily", daily)
    assert len(found) == 1
    assert "cannot observe" in found[0] and "fitbit-scale" in found[0]


def test_a_plausible_claim_is_not_a_finding():
    from vitai.schema import impossible_claim_problems
    rows = [(1, {"date": "2030-05-01", "steps": 9000, "source": "polar"})]
    assert impossible_claim_problems("daily", rows) == []


# ---- the contract tables cannot drift from the contract ---------------------

def _documented_contracts() -> set[int]:
    """Every contract `db.py` documents beside CONTRACT_VERSION."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "vitai" / "db.py").read_text(encoding="utf-8")
    block = src[src.index("# Bump when a table/column changes shape"):
                src.index("CONTRACT_VERSION =")]
    # Contract 1 is the founding shape and predates the comment block.
    return {1} | {int(m) for m in re.findall(r"^# (\d+): ", block, re.M)}


def _table_contracts(path: str) -> set[int]:
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8")
    return {int(m) for m in re.findall(r"^\| (\d+) \| ", text, re.M)}


def test_db_documents_every_contract_up_to_the_current_one():
    from vitai.db import CONTRACT_VERSION
    documented = _documented_contracts()
    assert max(documented) == int(CONTRACT_VERSION)
    assert documented == set(range(1, int(CONTRACT_VERSION) + 1))


def test_both_public_contract_tables_cover_every_contract():
    """The README's migration table and the wiki's consumer contract are what
    an integrator actually reads. Both had silently stopped being maintained -
    the wiki at contract 4 and the README at 8, while the engine was at 16 -
    and a consumer contract nobody maintains is one nobody can rely on.

    Mechanical because the drift was invisible: nothing failed, nothing
    warned, and each new contract widened the gap by one.
    """
    documented = _documented_contracts()
    for path in ("README.md", "wiki/content/explanation/platform.md"):
        missing = documented - _table_contracts(path)
        assert not missing, f"{path} is missing contracts {sorted(missing)}"


def _table_versions(path: str) -> dict[int, str]:
    """contract number -> the release version the table says shipped it."""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8")
    return {int(n): v.strip()
            for n, v in re.findall(r"^\| (\d+) \| ([^|]+) \|", text, re.M)}


def test_both_tables_agree_on_which_release_shipped_each_contract():
    """Coverage was checked and AGREEMENT was not, so the two tables could say
    different things about the same contract with nothing failing.

    They did. #184 recorded it while it was live: the README said `0.4.0` for
    contracts 16 to 19 and the wiki still said `unreleased`, because the wiki
    was missed in main's release commit. An integrator reading one table
    learned the shape was shipped and reading the other learned it was not.

    The existing coverage test could not see it - both tables HAD the rows.
    This checks the column that carried the disagreement, which is the half a
    derivation was missing.
    """
    readme = _table_versions("README.md")
    wiki = _table_versions("wiki/content/explanation/platform.md")
    shared = set(readme) & set(wiki)
    assert shared, "the two contract tables share no rows to compare"
    disagree = {n: (readme[n], wiki[n]) for n in sorted(shared)
                if readme[n] != wiki[n]}
    assert not disagree, (
        f"the README and the wiki disagree about which release shipped these "
        f"contracts (README, wiki): {disagree}"
    )


def test_no_contract_is_documented_as_shipping_after_the_current_release():
    """A row naming a release that does not exist yet tells an integrator to
    wait for something already in their hands."""
    from vitai import __version__
    readme = _table_versions("README.md")
    ahead = {n: v for n, v in readme.items()
             if v[0].isdigit() and tuple(int(p) for p in v.split(".")) >
             tuple(int(p) for p in __version__.split("."))}
    assert not ahead, f"contracts documented against an unreleased version: {ahead}"


def test_neither_table_invents_a_contract():
    """A row for a contract the engine never shipped is worse than a missing
    one: it tells an integrator to handle a shape that does not exist."""
    documented = _documented_contracts()
    for path in ("README.md", "wiki/content/explanation/platform.md"):
        extra = _table_contracts(path) - documented
        assert not extra, f"{path} documents contracts that do not exist: {sorted(extra)}"


# ---- #158: the CLI is a harness over the API, and stays one ----------------
#
# P9 is doctrine: "the CLI is a thin harness over the same `vitai.api` the
# platform consumes, never a separate code path". It was not true. `cmd_status`
# loaded the datasets itself and derived a rate and a trend word the API had no
# way to produce; `validate` and `infer` existed only in the CLI; `cmd_build`
# reimplemented the load-and-validate loop.
#
# That mattered beyond tidiness. An agent had exactly two options - shell out
# and parse prose, or read the JSONL and reimplement the engine's own reading
# rules - and the CLI's copy of `status` had DIVERGED, still opening with "no
# weight data yet" on an empty record, which is the weight-first behaviour the
# API was rewritten to remove (G62/G64).
#
# Mechanical, because prose did not hold it: this regressed silently for
# months while the principle sat in `docs/model.md` being agreed with.

# What the CLI may import from the engine, and why each one is not logic.
#
# `Vitai` is the surface. `KEYS` is the list of dataset NAMES, which argparse
# needs to build its choices before any engine call happens. `DataError` is an
# exception type to catch. Anything else is a capability, and a capability the
# CLI can reach directly is one an agent cannot.
CLI_MAY_IMPORT = {
    # `Vitai` is the record-scoped door. `schema` is the ENGINE-scoped one: it
    # reports the contract and the dataset generations, which are properties of
    # the installed engine rather than of anyone's record, so it takes no root
    # and cannot hang off a class that represents one (#147).
    #
    # Widening this entry is safe in a way widening the others is not, and the
    # reason is worth stating: the property #158 wants is that a capability the
    # CLI can reach, an agent can reach. Anything in `api` satisfies that by
    # construction. The entries below are different, because `jsonl` and
    # `schema` are engine internals where reachability is exactly what is in
    # question.
    #
    # Still listed by name rather than wildcarded, so each addition stays a
    # decision. A blanket "anything from api" would let CLI-shaped logic be
    # parked in api.py to get past this test, which is the failure one layer
    # along.
    "api": {"Vitai", "init", "schema"},
    # `mcp` is a second HARNESS, not engine logic, which is the distinction
    # this table exists to police. It is allowed for the same reason `api` is
    # and `jsonl` is not: it structurally cannot exceed the API, because its
    # tool table names methods on `Vitai` and raises at import if one is
    # missing. A capability the MCP server can reach, an agent can reach by
    # definition, since the MCP server is what the agent is talking to.
    "mcp": {"serve"},
    "jsonl": {"DataError"},
    "schema": {"KEYS"},
    # The NAME LIST of the read model's derived tables, for argparse
    # `choices` and NOTHING ELSE, allowed for the reason `schema.KEYS` is: it
    # is the engine's own inventory rather than logic, and taking it from the
    # engine is what stops the CLI's list going stale the day a table is
    # added. An agent reaches the same list through the `derived` tool's enum.
    #
    # The first cut also read the dict's VALUES, to print "N of M columns".
    # That was the rule breaking quietly: no permitted door gives an agent a
    # derived table's declared column list, so the CLI could answer a
    # question MCP could not. The summary now counts only what the rows
    # carry, which any consumer can do for itself.
    "db": {"DERIVED_TABLES"},
    "": {"__version__"},          # `from . import __version__`
}


def _cli_engine_imports():
    """Every way cli.py can name an engine module.

    RELATIVE AND ABSOLUTE, and plain `import` as well as `from`. The first cut
    inspected only relative `ImportFrom`, which is the house style here and so
    catches a copy-paste regression - but `from vitai.resolution import
    resolve` and `import vitai.safety` both sailed through, and the absolute
    form is exactly what an IDE auto-import emits. A guard that misses the
    likeliest accidental regression is worth very little.
    """
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "vitai" / "cli.py").read_text(encoding="utf-8")
    out = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                key = mod
            elif mod == "vitai" or mod.startswith("vitai."):
                key = mod[len("vitai."):] if mod != "vitai" else ""
            else:
                continue  # a third-party or stdlib import is not our business
            out.setdefault(key, set()).update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "vitai" or alias.name.startswith("vitai."):
                    # `import vitai.safety` binds the whole package, so every
                    # module under it is reachable. Reported under its own
                    # name so the message says which one.
                    key = alias.name[len("vitai."):]
                    out.setdefault(key, set()).add("<module>")
    return out


def test_the_cli_reaches_the_engine_only_through_the_api():
    """A capability the CLI can reach directly is one an agent cannot.

    This is the acceptance criterion of #158 stated as a test: "No CLI command
    contains logic absent from `vitai.api`." Import surface is the mechanical
    proxy - a command cannot reimplement `resolution` or `safety` without
    importing them.
    """
    got = _cli_engine_imports()
    for module, names in sorted(got.items()):
        allowed = CLI_MAY_IMPORT.get(module)
        assert allowed is not None, (
            f"cli.py imports from `{module}`, which is engine logic. Add the "
            f"capability to vitai.api and harness it, or justify it in "
            f"CLI_MAY_IMPORT with the reason it is not logic.")
        extra = names - allowed
        assert not extra, (
            f"cli.py imports {sorted(extra)} from `{module}`. Those are "
            f"capabilities an agent cannot reach; move them to vitai.api.")


def test_the_guard_sees_every_way_of_naming_an_engine_module():
    """The holes the first cut had, each demonstrated against the detector
    rather than argued about."""
    import ast
    import textwrap

    def detect(src):
        out = {}
        for node in ast.walk(ast.parse(textwrap.dedent(src))):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level:
                    key = mod
                elif mod == "vitai" or mod.startswith("vitai."):
                    key = mod[len("vitai."):] if mod != "vitai" else ""
                else:
                    continue
                out.setdefault(key, set()).update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("vitai."):
                        out.setdefault(alias.name[len("vitai."):],
                                       set()).add("<module>")
        return out

    assert "resolution" in detect("from .resolution import resolve")
    assert "resolution" in detect("from vitai.resolution import resolve")
    assert "safety" in detect("import vitai.safety")
    assert "policy" in detect("""
        def f():
            from vitai.policy import state
    """)
    # A genuinely unrelated import must not be reported, or the guard cries
    # wolf and gets an allowlist entry per stdlib module.
    assert detect("import json\nfrom pathlib import Path") == {}


def test_every_capability_the_cli_prints_exists_on_the_api():
    """The four that were missing, asserted by name so a deletion is loud."""
    from vitai.api import Vitai
    for capability in ("status", "validate", "infer", "accept_inferences",
                       "load_report", "conform", "implementation", "manifest",
                       "why_absent", "safety_banner", "status_line", "build"):
        assert callable(getattr(Vitai, capability, None)), capability


def test_status_is_the_same_answer_through_both_doors(tmp_path, capsys):
    """The CLI's copy had diverged from the API's, which is the failure P9
    exists to prevent, and it stayed invisible because nothing compared them.
    """
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2026-05-{n:02d}", "kg": 80.0 - n * 0.1, "source": "scale",
         "note": None}) for n in range(1, 20)) + "\n", encoding="utf-8")

    capsys.readouterr()
    main(["status", "--root", str(root)])
    printed = capsys.readouterr().out
    assert Vitai(root).status()["line"] in printed


def test_an_empty_record_is_not_told_it_failed_to_weigh_itself(tmp_path,
                                                               capsys):
    """The concrete divergence. An athlete who had refused a weight goal was
    told at every session that she had failed to weigh herself (G62/G64); the
    API was rewritten and the CLI's copy was not."""
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    capsys.readouterr()
    main(["status", "--root", str(root)])
    out = capsys.readouterr().out
    assert "no weight data yet" not in out
    assert "nothing logged yet" in out


def test_validate_returns_a_report_rather_than_exiting(tmp_path):
    """A library that calls `sys.exit` cannot be used by one. Deciding what a
    problem MEANS is the caller's."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text(
        json.dumps({"date": "2026-05-01", "kg": 80.0}) + "\n", encoding="utf-8")
    report = Vitai(root).validate()
    assert report["ok"] is False
    assert report["problems"]
    assert isinstance(report["advisories"], list)


# ---- the schema accessor (#147) ----------------------------------------------

def test_the_accessor_reports_the_constants_it_claims_to():
    """The point of #147 is that pinning code stopped reaching into private
    surface. That only holds if the public answer IS the private one: an
    accessor that drifts from `db.CONTRACT_VERSION` is worse than none,
    because a pin built on it fails silently, which is the exact failure a pin
    exists to prevent."""
    from vitai.api import schema
    from vitai.db import CONTRACT_VERSION
    from vitai.schema import CURRENT_GENERATION
    s = schema()
    assert s["contract"] == CONTRACT_VERSION
    assert s["generations"] == CURRENT_GENERATION


def test_the_generations_are_a_copy_a_caller_cannot_corrupt():
    """`CURRENT_GENERATION` is module state the whole engine reads. Handing a
    caller the live dict means one careless consumer can silently change what
    generation every subsequent row is stamped with."""
    from vitai.api import schema
    from vitai.schema import CURRENT_GENERATION
    schema()["generations"]["daily"] = 999
    assert CURRENT_GENERATION["daily"] != 999


def test_every_dataset_has_a_generation():
    """A dataset missing from the map is one a pin cannot check, and it would
    be missing silently."""
    from vitai.api import schema
    from vitai.schema import KEYS
    assert set(schema()["generations"]) == set(KEYS)


def test_the_engine_version_is_not_offered_as_a_gate():
    """Provenance only. `__version__` rises for a docs fix with no schema
    change and stands still while the schema moves: both directions have
    happened in this project. A pin gating on it tells itself a comforting
    lie, so the docstring says so and this test pins the docstring."""
    from vitai.api import schema
    assert "never a gate" in (schema.__doc__ or "") or "NOT a gate" in (schema.__doc__ or "")


def test_schema_is_reachable_through_both_doors(capsys):
    """P9: every capability ships as CLI and API together."""
    import json as _json

    from vitai.api import schema
    from vitai.cli import main
    main(["schema", "--json"])
    printed = _json.loads(capsys.readouterr().out)
    assert printed == schema()


# ---- #158 rung 2: the situation, in one call ------------------------------
#
# The alternative this replaces is fifteen calls a consumer stitches together,
# which is fifteen chances to stitch it wrong. The stitching is the work that
# must not be duplicated per consumer, because each one gets it subtly
# differently and none of them is the engine.

def test_the_situation_carries_what_a_decision_needs(tmp_path):
    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    got = Vitai(root).situation()
    for key in ("schema", "policy", "on", "gates", "escalations", "banner",
                "worries", "status", "goals", "context", "sessions", "rollup",
                "unresolved"):
        assert key in got, key


def test_it_gates_on_the_two_numbers_before_anything_else(tmp_path):
    """A consumer that trusts the body without checking the contract is a
    consumer that will misread it after the next bump. Both numbers travel
    with the brief so there is no second call to forget."""
    from vitai.api import Vitai, schema
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    got = Vitai(root).situation()
    assert got["schema"] == schema()
    assert got["policy"] == Vitai(root).policy


def test_unresolved_is_present_even_when_empty(tmp_path):
    """Absence is a claim everywhere else in this engine, and it is one here:
    a consumer rendering an empty section knows it asked, where a missing key
    only tells it nothing was said."""
    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    unresolved = Vitai(root).situation()["unresolved"]
    for key in ("problems", "advisories", "last_seen", "duplicate_captures",
                "conservation", "retracted"):
        assert key in unresolved, key


def test_it_computes_nothing_a_caller_could_not_have_asked_for(tmp_path):
    """Every value is an existing surface, assembled. If this ever grows a
    number of its own, the deterministic path has sprouted a second
    implementation, which is the whole subject of #158."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    engine = Vitai(root)
    got = engine.situation()
    assert got["status"] == engine.status()
    assert got["goals"] == engine.goals()
    assert got["gates"] == engine.gates()
    assert got["rollup"] == engine.rollup(engine.on)
    assert got["unresolved"]["advisories"] == engine.validate()["advisories"]
    # Serialisable, because the only consumer that matters is not in Python.
    assert json.loads(json.dumps(got, default=str))


def test_a_refusal_travels_with_the_brief(tmp_path):
    """It leads with what would STOP a decision. A brief that opens with a
    rate line and mentions the gate further down has already failed the one
    job it has, because the reader may act on the first paragraph."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "medical.jsonl").write_text(json.dumps(
        {"date": "2026-05-01", "slug": "chest", "kind": "symptom",
         "title": "chest tightness", "body_site": "chest",
         "severity": "red_flag", "status": "open", "resolved_date": None,
         "restricts": "all", "provider_type": None, "source": "athlete",
         "note": None, "expects": None, "onset_date": "2026-05-01",
         "precondition": None, "restriction": None}) + "\n", encoding="utf-8")
    got = Vitai(root, on="2026-05-02").situation()
    assert got["gates"], "a gated record must say so in the brief"
    assert got["escalations"], "an escalation must be in the brief"
    # The engine's own sentence, not a paraphrase.
    assert got["banner"]


def test_the_viewpoint_argument_reaches_the_numbers_not_just_the_label(tmp_path):
    """`status` took no viewpoint at all, so a brief pinned to May carried a
    rate computed over June weigh-ins and reported `on` twice with two
    different answers in one document."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2026-05-{n:02d}", "kg": 80.0 - n * 0.1, "source": "scale",
         "note": None}) for n in range(1, 25)) + "\n", encoding="utf-8")
    got = Vitai(root, on="2026-06-01").situation(on="2026-05-10")
    assert got["on"] == "2026-05-10"
    assert got["status"]["on"] == got["on"], "the brief reported two dates"
    # And the numbers moved with it, rather than only the label.
    early = Vitai(root).situation(on="2026-05-10")["status"]
    late = Vitai(root).situation(on="2026-05-24")["status"]
    assert early["mean_kg_7d"] != late["mean_kg_7d"]


def test_recent_sessions_are_at_or_before_the_viewpoint(tmp_path):
    """"Recent sessions" in a brief pinned to May must not contain June."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    rows = [{"date": d, "type": "run", "distance_km": 5.0, "duration_min": 30,
             "avg_hr": None, "note": None, "source": "watch", "rpe": None,
             "start_time": None, "place": None, "route": None}
            for d in ("2026-05-01", "2026-06-15")]
    (root / "data" / "sessions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    got = Vitai(root).situation(on="2026-05-02")
    assert [r["date"] for r in got["sessions"]] == ["2026-05-01"]
    assert got["unresolved"]["last_seen"]["sessions"] == "2026-05-01"


def test_asking_for_no_sessions_returns_none_of_them(tmp_path):
    """`[-0:]` is the whole list, not an empty one."""
    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    assert Vitai(root).situation(recent=0)["sessions"] == []


def test_a_datetime_is_refused_at_this_door_too(tmp_path):
    """The constructor rejects a `datetime` for a stated reason, and this
    normalised its own viewpoint inline without that guard - the same value
    refused at one door and taken at the next."""
    from datetime import datetime

    import pytest

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    with pytest.raises(TypeError, match="as_of"):
        Vitai(root).situation(on=datetime(2026, 5, 2, 13, 0))


def test_the_brief_survives_a_record_it_has_just_diagnosed(tmp_path):
    """`validate()` was deliberately made non-raising. A brief that crashed
    while formatting the same bad value would be withholding the diagnosis it
    is holding, on exactly the record that needs it."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {"date": "2026-05-01", "kg": "eighty", "source": "manual"}) + "\n",
        encoding="utf-8")
    got = Vitai(root).situation()
    assert got["unresolved"]["problems"], "the diagnosis must survive"
    # Named, never swallowed: a consumer can tell "could not answer" from
    # "the answer is empty".
    assert "status" in got["unresolved"]["unavailable"]


def test_the_situation_is_reachable_through_both_doors(tmp_path, capsys):
    """P9. The CLI door was untested, and it was the door with the defect:
    it built the engine at today's viewpoint and passed the date only to
    `situation()`, so every surface reading `self.on` answered as today."""
    import json

    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    capsys.readouterr()
    main(["situation", "--root", str(root), "--on", "2026-05-02",
          "--recent", "3"])
    got = json.loads(capsys.readouterr().out)
    assert got["on"] == "2026-05-02"
    assert got["status"]["on"] == "2026-05-02"


def test_the_viewpoint_reaches_the_whole_brief(tmp_path):
    """One `on` for the entire answer. A brief assembled from calls made at
    two different viewpoints is a brief that contradicts itself."""
    import json
    from datetime import date

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "events.jsonl").write_text(json.dumps(
        {"date": "2026-05-01", "slug": "spring-10k", "title": "a 10k",
         "kind": "race", "event_date": "2026-07-01", "priority": "a",
         "immovable": True, "place": None, "status": "planned",
         "set_by": "athlete", "reason": None, "note": None}) + "\n",
        encoding="utf-8")
    early = Vitai(root, on=date(2026, 5, 2)).situation()
    late = Vitai(root, on=date(2026, 6, 2)).situation()
    assert early["on"] == "2026-05-02" and late["on"] == "2026-06-02"
    assert early["rollup"] != late["rollup"]
# ---- #158 rung 4: write parity --------------------------------------------
#
# The vocabulary already existed and was in live use. What was missing is that
# a consumer could reach it without hand-writing JSONL, which meant every
# agent re-implemented the provenance stamping and each one got a slightly
# different answer about what a spoken number IS.

def _repo(tmp_path):
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def test_a_stated_value_carries_provenance_the_engine_set(tmp_path):
    from vitai.api import Vitai
    row = Vitai(_repo(tmp_path)).claim(
        "weight", {"kg": 80.4}, said="about eighty and a half this morning")
    assert row["capture"] == "narrative"
    assert row["source"] == "stated-in-chat"
    assert row["read_by"] == "athlete"
    assert row["note"] == "about eighty and a half this morning"
    assert row["recorded_at"], "the engine stamps transaction time"


def test_a_caller_cannot_stamp_its_own_provenance(tmp_path):
    """The acceptance criterion of #158, and the reason behind it: a caller
    that could set these could file a recollection as a device reading, and
    the ladder ranks `stated-in-chat` ABOVE a connector export."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    for field, value in (("recorded_at", "2026-01-01T00:00:00+00:00"),
                         ("device", "someone-elses-phone"),
                         ("capture", "ble"),
                         ("source", "scale")):
        with pytest.raises(ValueError, match="not a quantity"):
            engine.claim("weight", {"kg": 80.0, field: value})


def test_read_by_is_refused_in_values_rather_than_overridden(tmp_path):
    """It was silently overwritten by the default, so a caller naming the
    wrong reader got no error and no effect. Refusing with a pointer to the
    parameter is the honest version."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="read_by. parameter"):
        engine.claim("weight", {"kg": 80.0, "read_by": "model"})
    assert engine.claim("weight", {"kg": 80.0}, read_by="model")["read_by"] \
        == "model"


def test_an_agent_transcribing_can_say_so(tmp_path):
    """Recording WHO read is not ranking who read. #140 declined to rank
    people and deliberately kept the field."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    assert engine.claim("weight", {"kg": 79.9},
                        read_by="model")["read_by"] == "model"
    with pytest.raises(ValueError, match="athlete, model, human-other"):
        engine.claim("weight", {"kg": 79.9}, read_by="nobody")


def test_the_engine_refuses_the_ambiguity_rather_than_each_agent(tmp_path):
    """"Some push-ups" is not a rep count, and the place to decide that once
    is the engine: an agent that validates for itself is an agent that will
    eventually decide "some" means three."""
    import pytest

    from vitai.api import Vitai
    from vitai.jsonl import DataError
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(DataError) as caught:
        engine.claim("sets", {"exercise": "pushup", "set_index": 1,
                              "reps_completed": "some"})
    # The WHOLE-NUMBER rule specifically. Asserting only "reps" passed
    # against a different refusal in the same message ("a set needs reps or a
    # duration"), so deleting the whole-number check left this green while
    # `{"reps_completed": "some", "duration_s": 60}` would have appended.
    assert "whole number" in str(caught.value)
    with pytest.raises(DataError):
        engine.claim("sets", {"exercise": "pushup", "set_index": 1,
                              "reps_completed": "some", "duration_s": 60})


def test_an_utterance_with_no_number_still_appends_exactly_one_line(tmp_path):
    """Zero guessed numbers, but always exactly one appended claim. A rule
    that answers "I did some push-ups" by writing nothing hands the record to
    whichever tool is willing to write the sentence down."""
    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    row = engine.said("did some push-ups after work")
    assert row["text"] == "did some push-ups after work"
    assert row["source"] == "stated-in-chat"
    assert row["recorded_at"]
    assert len(engine.dataset("journal")) == 1


def test_saying_nothing_appends_nothing(tmp_path):
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    for empty in ("", "   ", None):
        with pytest.raises(ValueError, match="nothing was said"):
            engine.said(empty)
    assert engine.dataset("journal") == []


def test_the_destructive_field_needs_a_deliberate_parameter(tmp_path):
    """`supersedes` retires the line it names on every future load. It rode
    through the first cut inside `values`, so a narrative claim could
    permanently retire a device reading with provenance saying the athlete
    stated it - and a caller that reached it by putting a key in a dict would
    not have decided to."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="corrects"):
        engine.claim("weight", {"kg": 75.0,
                                "supersedes": "2026-07-01/scale"})
    row = engine.claim("weight", {"kg": 75.0}, corrects="2026-07-01/scale")
    assert row["supersedes"] == "2026-07-01/scale"


def test_a_chat_claim_cannot_manufacture_a_witness(tmp_path):
    """Setting `origin` made a narrative claim count as an INDEPENDENT
    witness, which is corroboration built out of nothing - exactly what
    `provenance.py` exists to prevent."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    for field in ("origin", "path", "origin_evidence", "artifact",
                  "modelled", "_gen", "type_source"):
        with pytest.raises(ValueError, match="not a quantity"):
            engine.claim("weight", {"kg": 70.0, field: "anything"})


def test_a_claim_with_no_quantity_is_refused(tmp_path):
    """An all-null observation row is permanent junk in an append-only
    record, and it is the likeliest agent slip: the number went into `said`
    instead of into a field."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    for empty in ({}, {"kg": None}, {"date": "2026-05-01"}):
        with pytest.raises(ValueError, match="no quantity was stated"):
            engine.claim("weight", empty)


def test_the_allowlist_covers_a_field_nobody_has_added_yet(tmp_path):
    """The point of inverting it. A denylist fails silently every time the
    schema grows; this refuses anything that is not a field of the dataset."""
    import pytest

    from vitai.api import Vitai
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="no field"):
        engine.claim("weight", {"kg": 80.0, "trustworthiness": 11})


def test_forgetting_the_dataset_does_not_silently_drop_the_number(tmp_path):
    """It discarded the quantities and exited 0: the number the athlete
    stated vanished while the tool reported success, which for an agent is
    the worst available shape of failure."""
    import pytest

    from vitai.cli import main
    root = _repo(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["claim", "--root", str(root), "--said", "80.4 today", "kg=80.4"])
    assert "no --dataset" in str(caught.value)


def test_the_utterance_surface_is_reachable_from_the_cli(tmp_path, capsys):
    """P9 inside the P9 change: `kind` and `about` were API-only, so an agent
    on the CLI tier could not file a worry."""
    import json

    from vitai.cli import main
    root = _repo(tmp_path)
    capsys.readouterr()
    main(["claim", "--root", str(root), "--said", "knee feels off",
          "--kind", "worry"])
    assert json.loads(capsys.readouterr().out)["kind"] == "worry"


def test_a_claim_is_reachable_through_both_doors(tmp_path, capsys):
    """P9."""
    import json

    from vitai.api import Vitai
    from vitai.cli import main
    root = _repo(tmp_path)
    capsys.readouterr()
    main(["claim", "--root", str(root), "--dataset", "weight",
          "--said", "about eighty", "kg=80.4"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["kg"] == 80.4 and printed["capture"] == "narrative"
    main(["claim", "--root", str(root), "--said", "some push-ups"])
    assert len(Vitai(root).dataset("journal")) == 1


def test_the_cli_relays_the_engines_refusal_verbatim(tmp_path, capsys):
    """An agent driving the CLI needs the reason, not an exit code. A code
    would have to be interpreted, and every interpreter would differ."""
    import pytest

    from vitai.cli import main
    root = _repo(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["claim", "--root", str(root), "--dataset", "weight",
              "kg=80", "source=scale"])
    assert "not a quantity" in str(caught.value)


# ---- #158 rung 5: the MCP adapter is a harness, not a second surface -------

def test_every_mcp_tool_resolves_to_the_api():
    """The acceptance criterion of #158, and it is enforced at IMPORT rather
    than asserted here: an adapter that could name a missing capability is one
    that will, silently, the first time a method is renamed."""
    from vitai.api import Vitai
    from vitai.mcp import TOOLS
    for name, spec in TOOLS.items():
        method = spec["method"]
        if method is None:
            continue          # a module-level function of the same name
        assert hasattr(Vitai, method), f"{name} names Vitai.{method}"


def test_a_tool_naming_a_missing_method_fails_at_import():
    """The premise. If this could be added quietly, the check above is
    decoration."""
    import pytest

    from vitai.api import Vitai
    from vitai.mcp import TOOLS
    assert not hasattr(Vitai, "definitely_not_a_method")
    with pytest.raises(AttributeError):
        # the same guard the module runs over its own table
        for spec in list(TOOLS.values()) + [{"method": "definitely_not_a_method"}]:
            m = spec["method"]
            if m is not None and not hasattr(Vitai, m):
                raise AttributeError(m)


def test_tool_descriptions_come_from_the_methods_own_docstring():
    """So the adapter cannot document a capability differently from the API.
    Two descriptions of one method is two chances to be wrong."""
    from vitai.api import Vitai
    from vitai.mcp import tool_list
    for tool in tool_list():
        assert tool["description"], tool["name"]
        method = getattr(Vitai, tool["name"], None)
        if method is not None and method.__doc__:
            assert tool["description"] == \
                method.__doc__.strip().splitlines()[0]


def test_it_speaks_the_protocol(tmp_path):
    """Newline-delimited JSON-RPC 2.0 on stdio, initialize through a call."""
    import io
    import json

    from vitai.cli import main
    from vitai.mcp import serve
    root = tmp_path / "content"
    main(["init", str(root)])
    stdin = io.StringIO("\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "schema", "arguments": {}}}),
    ]) + "\n")
    import contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        serve(root, stdin=stdin)
    replies = [json.loads(ln) for ln in out.getvalue().splitlines() if ln]
    assert replies[0]["result"]["protocolVersion"]
    assert {t["name"] for t in replies[1]["result"]["tools"]} == \
        {"situation", "schema", "validate", "status", "day", "window",
         "goals", "safety", "claim", "said", "dataset", "derived", "may",
         "project", "corrections", "questions"}
    payload = json.loads(replies[2]["result"]["content"][0]["text"])
    assert payload["contract"]


def test_a_refusal_is_relayed_as_the_engines_sentence(tmp_path):
    """An agent can act on a sentence. A code has to be interpreted, and
    every interpreter differs."""
    import contextlib
    import io
    import json

    from vitai.cli import main
    from vitai.mcp import serve
    root = tmp_path / "content"
    main(["init", str(root)])
    stdin = io.StringIO(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "claim",
                   "arguments": {"dataset": "weight",
                                 "values": {"kg": 80.0, "source": "scale"}}},
    }) + "\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        serve(root, stdin=stdin)
    reply = json.loads(out.getvalue().strip())
    assert "not a quantity" in reply["error"]["message"]


def test_an_unknown_tool_is_refused_by_name(tmp_path):
    import contextlib
    import io
    import json

    from vitai.cli import main
    from vitai.mcp import serve
    root = tmp_path / "content"
    main(["init", str(root)])
    stdin = io.StringIO(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "drop_everything", "arguments": {}},
    }) + "\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        serve(root, stdin=stdin)
    assert "no such tool" in json.loads(out.getvalue())["error"]["message"]


# ---- #177: no_data was one word for four states ---------------------------
#
# The distinction already existed in the data and was recoverable only by
# inspecting which fields were null. Every consumer would have
# reverse-engineered it from row shape, each slightly differently, and none of
# them is the engine.

def _verdict_rows(**kw):
    from vitai.config import Config
    from vitai.verdicts import compute_verdicts
    return compute_verdicts(kw.pop("cfg", Config()), kw.pop("weight", []),
                            kw.pop("daily", []), kw.pop("sessions", []), **kw)


def test_a_refusal_cannot_ship_without_a_reason():
    """The totality the issue asks for, held where every row is BUILT rather
    than at each caller, so a new refusal site cannot ship unlabelled."""
    import pytest

    from vitai.verdicts import NODATA, _row
    with pytest.raises(ValueError, match="needs a reason"):
        _row("2030-04-01", "weight_rate", None, None, NODATA)
    with pytest.raises(ValueError, match="needs a reason"):
        _row("2030-04-01", "weight_rate", None, None, NODATA, reason="made up")


def test_a_judgement_carries_no_reason():
    """The other half. A reason on a judged row would mean the field answers
    two different questions depending on the verdict beside it."""
    import pytest

    from vitai.verdicts import ON, _row
    with pytest.raises(ValueError, match="not a refusal"):
        _row("2030-04-01", "steps", 9000, 8000, ON, reason="no_input")


def test_the_reason_is_readable_without_inspecting_null_fields():
    """The complaint in one sentence: a consumer had to reverse-engineer why
    from the shape of the row."""
    from vitai.config import Config
    weight = [{"date": "2030-04-01", "kg": 80.0, "source": "scale",
               "note": None, "body_fat_pct": None, "kg_lo": None,
               "kg_hi": None, "body_fat_lo": None, "body_fat_hi": None}]
    # A rate with no phase configured: the rate is real, the policy is not.
    rows = _verdict_rows(cfg=Config(), weight=weight * 2)
    refusals = [r for r in rows if r["verdict"] == "no_data"]
    for row in refusals:
        assert row["reason"], row
        assert row["reason"] in {"no_input", "no_policy", "not_supported",
                                 "contraindicated", "suppressed", "pending"}


def test_a_consumer_ignoring_the_reason_sees_the_previous_behaviour():
    """Additive and appended, so a reader by name is unaffected and one
    reading positionally sees the new columns last.

    The RULE rather than a snapshot of it: what a positional reader needs is
    that the columns it already knew keep their places, not that the list ends
    on any particular word. Pinning the final name made every later addition
    look like a breach of a promise it actually keeps - `due` arrived after
    `reason` (#202) and the invariant held throughout.
    """
    from vitai.db import VERDICT_KEYS
    ORIGINAL = ["week", "metric", "value", "target", "verdict", "goal"]
    assert VERDICT_KEYS[:len(ORIGINAL)] == ORIGINAL
    # And the appended ones are known, so a column cannot arrive unnoticed.
    assert VERDICT_KEYS[len(ORIGINAL):] == ["reason", "due", "statistic",
                                            "window_days", "answers"]


def test_the_reason_reaches_the_read_model(tmp_path):
    import json
    import sqlite3

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2026-04-{d:02d}", "kg": 80.0, "source": "scale",
         "note": None, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "measured_at": None})
        for d in range(1, 15)) + "\n", encoding="utf-8")
    con = sqlite3.connect(Vitai(root).build())
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(verdicts)")]
        # Present, not last: `due` was appended after it (#202). What this
        # test is about is that the reason survives the projection.
        assert "reason" in cols
        rows = con.execute(
            "SELECT verdict, reason FROM verdicts WHERE verdict='no_data'"
        ).fetchall()
    finally:
        con.close()
    assert rows, "premise: this record produces refusals"
    assert all(reason for _, reason in rows), "a refusal reached the read model bare"


def test_mcp_refuses_an_argument_its_schema_does_not_declare(tmp_path):
    """The declared surface is the WHOLE surface.

    `inputSchema` is advisory to the client, so before this was enforced a
    caller that ignored it reached every remaining parameter of the underlying
    method. `claim` does not offer `corrects`, which retires a line, and that
    is a decision about what the tool IS rather than a hint to well-behaved
    callers. An adapter whose real surface is wider than its described one
    cannot be audited from its description.
    """
    import pytest

    from vitai.cli import main
    from vitai.mcp import call, tool_list

    root = tmp_path / "r"
    main(["init", str(root)])

    advertised = {t["name"]: set(t["inputSchema"]["properties"])
                  for t in tool_list()}
    assert "corrects" not in advertised["claim"]

    with pytest.raises(KeyError) as caught:
        call(root, "claim", {"dataset": "weight", "values": {"kg": 80},
                             "said": "x", "corrects": "weight:2020-01-01:manual"})
    assert "corrects" in str(caught.value)

    # and the advertised ones still work
    row = call(root, "claim", {"dataset": "weight", "values": {"kg": 80},
                               "said": "about eighty"})
    assert row["kg"] == 80


def _door_calls(fn) -> set:
    """Door names this function actually CALLS.

    Calls, not mentions. The first cut asked whether the body named a door
    anywhere, and that is satisfied by a return annotation, by a local
    variable that happens to be spelled `init`, and by naming `Vitai` once
    beside arbitrary engine work - none of which is delegation. A guard that a
    comment can satisfy is not a guard.
    """
    import ast

    def root(node):
        while isinstance(node, ast.Attribute):
            node = node.value
        if isinstance(node, ast.Call):
            return root(node.func)
        return node.id if isinstance(node, ast.Name) else None

    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and (name := root(node.func)):
            out.add(name)
    return out


def test_every_cli_command_delegates_to_the_api():
    """The import guard above is a PROXY, and `init` walked past it.

    A command cannot reimplement `resolution` without importing it, which is
    what that test catches. But `cmd_init` scaffolded a whole content repo out
    of `shutil` and `importlib.resources` - no engine import, nothing tripped,
    and it was the one capability a caller could not reach without a
    subprocess. Creating a record is where a client STARTS, so needing to
    shell out for it is tier 1 failing at the first step.

    So this asks the other question: does the command CALL into the API? A
    `cmd_*` that never does is doing the work itself, and whatever it does, a
    consumer of the API cannot.

    What it does NOT check, so nobody reads more into a green run than is
    there: that the command does nothing BESIDE the call. Presence of a
    delegation is mechanical; absence of logic beside it is not, and a test
    claiming to prove the second would be the overstatement this replaced.
    """
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / "src" / "vitai"
                      / "cli.py").read_text(encoding="utf-8"))
    # The imported NAMES, plus the module names themselves: `api.init(...)` is
    # delegation just as much as `init(...)` is, and a guard that only accepts
    # the house `from .api import` style would fail the day someone writes the
    # other one correctly. `jsonl` and `schema` are deliberately NOT doors -
    # reachability is exactly what is in question for those two.
    doors = CLI_MAY_IMPORT["api"] | CLI_MAY_IMPORT["mcp"] | {"api", "mcp"}
    commands = [n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("cmd_")]
    assert len(commands) > 20, "the walk stopped finding the commands"
    for fn in commands:
        assert _door_calls(fn) & doors, (
            f"{fn.name} calls nothing from the API, so whatever it does, a "
            f"consumer of the API cannot. Move the capability into vitai.api "
            f"and harness it.")
