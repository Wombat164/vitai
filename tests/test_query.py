"""Factual query verbs: check, day, window, ramp.

Synthetic data only (public repo: no real measurements).

`check` is the load-bearing one. It exists because an LLM's narration is as
untrustworthy a source as any vendor estimate, and P1 says sources are claims
the engine adjudicates - a rule that had never been applied to the coach's own
sentences.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.query import CONFIRMED, NOT_IN_RECORD, REFUTED, check, ramp, window


def write(p: Path, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def session(date, type="run", **kw):
    rec = {"date": date, "type": type, "distance_km": None, "duration_s": None,
           "avg_hr": None, "max_hr": None, "cadence": None, "kcal": None,
           "rpe": None, "note": None, "source": "watch", "start_time": None,
           "elevation_m": None, "setting": None, "route": None, "place": None,
           "with": None, "context": None, "planned": None, "weather": None,
           "_gen": 2}
    rec.update(kw)
    return rec


def daily(date, **kw):
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "alcohol": None, "note": None, "source": "watch",
           "mood": None, "feel": None, "coverage": None, "pain": None,
           "pain_site": None, "pain_side": None, "_gen": 2}
    rec.update(kw)
    return rec


def _data(sessions=(), days=()):
    return {"sessions": list(sessions), "daily": list(days)}


# ---- check -------------------------------------------------------------------

def test_a_true_claim_is_confirmed():
    data = _data([session("2030-06-01", distance_km=8.01)])
    out = check(data, "2030-06-01", "distance_km", 8.0, type="run")
    assert out["verdict"] == CONFIRMED


def test_a_false_claim_is_refuted_with_the_delta():
    """The private tool's first run refuted two claims asserted narratively
    minutes earlier."""
    data = _data([session("2030-06-01", distance_km=8.01)])
    out = check(data, "2030-06-01", "distance_km", 9.0, type="run")
    assert out["verdict"] == REFUTED
    assert out["sum"] == 8.01
    assert out["delta"] == pytest.approx(0.99)
    assert out["delta_pct"] == pytest.approx(12.4, abs=0.1)


def test_absence_cannot_refute():
    """NOT-IN-RECORD is a distinct verdict. A day with nothing logged does not
    prove the run did not happen, and saying REFUTED there would be the engine
    overreaching in exactly the way it accuses the model of."""
    out = check(_data(), "2030-06-01", "distance_km", 8.0)
    assert out["verdict"] == NOT_IN_RECORD
    assert out["sum"] is None and out["delta"] is None


def test_a_claim_may_be_true_of_the_sum_or_of_one_row():
    """"I ran 8k" may mean one 8 km run or two 4 km runs, and the answer
    should say which reading makes it true."""
    two = _data([session("2030-06-01", distance_km=4.0),
                 session("2030-06-01", distance_km=4.0)])
    out = check(two, "2030-06-01", "distance_km", 8.0, type="run")
    assert out["verdict"] == CONFIRMED and out["matched"] == "sum"

    out = check(two, "2030-06-01", "distance_km", 4.0, type="run")
    assert out["verdict"] == CONFIRMED
    assert out["matched"] == "row 1 of 2", "it names the reading that holds"


def test_tolerance_is_configurable_not_a_law(tmp_path):
    data = _data([session("2030-06-01", distance_km=10.0)])
    assert check(data, "2030-06-01", "distance_km", 10.5)["verdict"] == REFUTED
    assert check(data, "2030-06-01", "distance_km", 10.5,
                 tolerance=0.10)["verdict"] == CONFIRMED


def test_check_can_scope_to_a_session_type():
    data = _data([session("2030-06-01", type="run", distance_km=5.0),
                  session("2030-06-01", type="walk", distance_km=3.0)])
    assert check(data, "2030-06-01", "distance_km",
                 5.0, type="run")["verdict"] == CONFIRMED
    # Unscoped, the day's distance is both together.
    assert check(data, "2030-06-01", "distance_km",
                 8.0)["verdict"] == CONFIRMED


def test_check_reads_daily_metrics_too():
    data = _data(days=[daily("2030-06-01", steps=9500)])
    assert check(data, "2030-06-01", "steps", 9500)["verdict"] == CONFIRMED
    assert check(data, "2030-06-01", "steps", 12000)["verdict"] == REFUTED


# ---- the API and CLI surfaces (P9) -------------------------------------------

def _repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    write(root / "data" / "sessions.jsonl", [
        session("2030-06-01", distance_km=8.01, duration_s=2400, kcal=500),
        session("2030-06-03", distance_km=5.0, duration_s=1500, kcal=310),
        session("2030-06-08", distance_km=6.0, duration_s=1800, kcal=370),
        session("2030-06-10", type="walk", distance_km=2.0, duration_s=1500),
    ])
    write(root / "data" / "daily.jsonl",
          [daily(f"2030-06-{d:02d}", steps=9000 + d) for d in range(1, 11)])
    return root


def test_api_check_uses_the_configured_tolerance(tmp_path):
    root = _repo(tmp_path)
    (root / "vitai.toml").write_text(
        "[preferences]\ncheck_tolerance = 0.2\n", encoding="utf-8")
    assert Vitai(root).check("2030-06-01", "distance_km", 9.0,
                             type="run")["verdict"] == CONFIRMED


def test_cli_check_exits_one_on_a_refutation(tmp_path, capsys):
    root = _repo(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["check", "--root", str(root), "--date", "2030-06-01",
              "--metric", "distance_km", "--type", "run", "--says", "9"])
    assert exc.value.code == 1
    assert "REFUTED" in capsys.readouterr().out


def test_cli_check_is_quiet_when_confirmed(tmp_path, capsys):
    root = _repo(tmp_path)
    main(["check", "--root", str(root), "--date", "2030-06-01",
          "--metric", "distance_km", "--type", "run", "--says", "8.01"])
    assert "CONFIRMED" in capsys.readouterr().out


def test_cli_check_does_not_exit_nonzero_on_absence(tmp_path, capsys):
    """A missing record is not a failed assertion."""
    root = _repo(tmp_path)
    main(["check", "--root", str(root), "--date", "2030-06-30",
          "--metric", "distance_km", "--says", "8"])
    assert "NOT-IN-RECORD" in capsys.readouterr().out


# ---- day ---------------------------------------------------------------------

def test_day_shows_what_the_canonical_row_is_hiding(tmp_path):
    """The point of a factual dump is that merged claims are visible."""
    root = _repo(tmp_path)
    write(root / "data" / "sessions.jsonl", [
        session("2030-06-01", source="watch", distance_km=5.0, duration_s=1800,
                start_time="2030-06-01T07:00:00+00:00"),
        session("2030-06-01", source="app", distance_km=5.1, duration_s=1810,
                start_time="2030-06-01T07:01:00+00:00"),
    ])
    out = Vitai(root).day("2030-06-01")
    assert len(out["datasets"]["sessions"]) == 1, "canonical collapsed them"
    assert len(out["merged_claims"]) == 1, "and the dump says one was merged"


def test_day_is_empty_but_valid_for_a_date_with_nothing(tmp_path):
    out = Vitai(_repo(tmp_path)).day("2029-01-01")
    assert out["datasets"] == {} and out["merged_claims"] == []


# ---- window ------------------------------------------------------------------

def test_window_totals_by_session_type(tmp_path):
    out = Vitai(_repo(tmp_path)).window(10, on="2030-06-10")
    assert out["by_type"]["run"]["sessions"] == 3
    assert out["by_type"]["run"]["distance_km"] == pytest.approx(19.01)
    assert out["by_type"]["walk"]["sessions"] == 1


def test_window_counts_calendar_days_not_logged_days():
    """A window that skipped empty days would report a fortnight as a week."""
    data = _data([session("2030-06-01", distance_km=5.0),
                  session("2030-06-14", distance_km=5.0)])
    out = window(data, 7, on="2030-06-14")
    assert out["from"] == "2030-06-08"
    assert out["by_type"]["run"]["sessions"] == 1, "the older run is outside"


# ---- ramp --------------------------------------------------------------------

def test_ramp_reports_week_on_week_change():
    data = _data([session("2030-06-03", distance_km=10.0),
                  session("2030-06-10", distance_km=12.0)])
    out = ramp(data)
    assert [w["value"] for w in out["weeks"]] == [10.0, 12.0]
    assert out["weeks"][1]["change_pct"] == pytest.approx(20.0)


def test_ramp_carries_the_base_size_caveat_on_a_thin_record():
    """A ramp % over a one-week base is not a trend, and the engine says so -
    this stopped a misleading percentage being quoted."""
    out = ramp(_data([session("2030-06-03", distance_km=10.0)]))
    assert out["maturity"] == "cold"
    assert "not" in out["caveat"] and "trend" in out["caveat"]
    assert "weeks with data: 1" in out["caveat"]


def test_ramp_matures_as_the_record_grows():
    weeks = [session(f"2030-06-{d:02d}", distance_km=10.0)
             for d in (3, 10, 17, 24)]
    assert ramp(_data(weeks))["maturity"] == "stable"
    assert ramp(_data(weeks[:2]))["maturity"] == "warming"


def test_cli_ramp_always_prints_the_caveat_last(tmp_path, capsys):
    main(["ramp", "--root", str(_repo(tmp_path))])
    out = capsys.readouterr().out.strip().splitlines()
    assert "weeks with data" in out[-1], "the caveat is the last word"


def test_the_verbs_interpret_nothing(tmp_path):
    """P4: these report, the coach interprets. No verdict beyond the closed
    set, no advice, no adjectives."""
    v = Vitai(_repo(tmp_path))
    assert v.check("2030-06-01", "distance_km", 8.01,
                   type="run")["verdict"] in (CONFIRMED, REFUTED, NOT_IN_RECORD)
    assert set(v.window(7, on=date(2030, 6, 10))) == {
        "from", "to", "days", "days_logged", "by_type"}
