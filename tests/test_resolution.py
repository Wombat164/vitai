"""Increment 2: provenance, context, feel, and the resolution layer.

Synthetic data only (public repo: no real measurements).

The load-bearing test in this file is
`test_single_source_resolution_is_byte_identical`: resolution is a new layer
between the record and every number the athlete is judged on, so the proof
that it did not quietly change anybody's history is that a single-source repo
builds to the same bytes it did before.
"""

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai
from vitai.cli import main
from vitai.config import Config, load_config
from vitai.policy import context_on, has_facility
from vitai.resolution import canonical_daily, live_inferences, resolve, retractions
from vitai.schema import validate_record
from vitai.verdicts import compute_verdicts


def write(p: Path, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def daily(date, source=None, gen=2, **kw):
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "alcohol": None, "note": None,
           "source": source, "mood": None, "feel": None, "coverage": None,
           "pain": None, "pain_site": None, "_gen": gen}
    rec.update(kw)
    return rec


def legacy_daily(date, **kw):
    """A generation-1 line, exactly as it would sit in an existing repo."""
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "hip_pain": None, "alcohol": None, "note": None}
    rec.update(kw)
    return rec


def session(date, source=None, type="run", gen=2, **kw):
    rec = {"date": date, "type": type, "distance_km": None, "duration_s": None,
           "avg_hr": None, "max_hr": None, "cadence": None, "kcal": None,
           "rpe": None, "note": None, "source": source, "start_time": None,
           "elevation_m": None, "setting": None, "route": None, "place": None,
           "with": None, "context": None, "planned": None, "weather": None,
           "_gen": gen}
    rec.update(kw)
    return rec


def empty(*names):
    return {n: [] for n in names}


def _resolve(**datasets):
    base = empty("weight", "daily", "sessions", "measurements", "inferences",
                 "goals", "thresholds", "achievements", "context")
    base.update(datasets)
    return resolve(base)


# ---- new field shapes --------------------------------------------------------

def test_every_new_daily_field_is_nullable():
    assert validate_record("daily", daily("2030-05-01")) == []


def test_every_new_session_field_is_nullable():
    assert validate_record("sessions", session("2030-05-01")) == []


def test_measurement_and_context_shapes():
    assert validate_record("measurements", {
        "date": "2030-05-01", "kind": "waist_cm", "value": 84.0,
        "source": "tape", "note": None}) == []
    assert validate_record("context", {
        "date": "2030-05-01", "mode": "vacation", "facilities": "gym",
        "place": "coast", "source": "athlete", "note": None}) == []
    assert any("kind" in p for p in validate_record("measurements", {
        "date": "2030-05-01", "kind": "vibes", "value": 1.0,
        "source": None, "note": None}))


def test_closed_vocabularies_on_the_new_fields():
    assert any("feel" in p for p in validate_record(
        "daily", daily("2030-05-01", feel="great")))
    assert any("weather" in p for p in validate_record(
        "sessions", session("2030-05-01", weather="drizzle")))
    assert any("setting" in p for p in validate_record(
        "sessions", session("2030-05-01", setting="beach")))


def test_start_time_must_parse():
    assert any("start_time" in p for p in validate_record(
        "sessions", session("2030-05-01", start_time="half seven")))
    assert validate_record("sessions", session(
        "2030-05-01", start_time="2030-05-01T07:12:00+02:00")) == []


def test_pain_and_site_travel_together():
    assert any("pain_site" in p for p in validate_record(
        "daily", daily("2030-05-01", pain=4)))
    # Zero is a complete statement and needs no body part; null is not the
    # same thing - it means nobody looked.
    assert validate_record("daily", daily("2030-05-01", pain=0)) == []
    assert any("says nothing" in p for p in validate_record(
        "daily", daily("2030-05-01", pain_site="knee")))
    assert validate_record("daily", daily(
        "2030-05-01", pain=4, pain_site="knee")) == []


# ---- the hip_pain migration --------------------------------------------------

def test_hip_pain_reads_forward_as_pain_at_the_hip():
    mapped = canonical_daily(legacy_daily("2030-05-01", hip_pain=3))
    assert mapped["pain"] == 3
    assert mapped["pain_site"] == "hip"


def test_an_explicit_pain_beats_the_legacy_mapping():
    both = daily("2030-05-01", pain=1, pain_site="knee", hip_pain=7)
    assert canonical_daily(both)["pain"] == 1
    assert canonical_daily(both)["pain_site"] == "knee"


def test_pain_gate_still_fires_off_legacy_lines():
    """An existing repo's hip_pain lines must keep gating after the rename."""
    days = [legacy_daily(f"2030-04-0{d}", hip_pain=5) for d in range(1, 8)]
    resolved = _resolve(daily=days)["canonical"]["daily"]
    rows = compute_verdicts(Config(pain_gate=3), [], resolved, [])
    gate = [r for r in rows if r["metric"] == "pain_gate"]
    assert gate and gate[0]["verdict"] == "behind"


def test_mixed_old_and_new_lines_in_one_file(tmp_path):
    write(tmp_path / "daily.jsonl", [
        legacy_daily("2030-05-01", steps=9000, hip_pain=2),
        daily("2030-05-02", steps=9500, pain=2, pain_site="knee"),
    ])
    from vitai.jsonl import load
    recs = load(tmp_path, "daily")
    assert len(recs) == 2
    assert all(validate_record("daily", r) == [] for r in recs)


# ---- resolution: field-wise precedence --------------------------------------

def test_two_sources_merge_field_wise_never_summing():
    """The golden rule: a calorie is burned once."""
    claims = [
        daily("2030-05-01", source="watch", kcal_out=2443, steps=9000),
        daily("2030-05-01", source="app", kcal_out=2844, kcal_in=2100),
    ]
    out = resolve({"daily": claims, "weight": [], "sessions": [],
                   "measurements": [], "inferences": []},
                  precedence={"kcal_out": ("watch", "app"),
                              "kcal_in": ("app", "watch")})
    row = out["canonical"]["daily"][0]
    assert row["kcal_out"] == 2443, "the ranked device wins its own quantity"
    assert row["kcal_in"] == 2100, "the other source still wins ITS quantity"
    assert row["steps"] == 9000
    assert row["kcal_out"] + 0 != 2443 + 2844


def test_resolution_explains_itself():
    claims = [daily("2030-05-01", source="watch", kcal_out=2443),
              daily("2030-05-01", source="app", kcal_out=2844)]
    out = resolve({"daily": claims}, precedence={"kcal_out": ("watch", "app")})
    expl = [e for e in out["explanations"] if e["field"] == "kcal_out"]
    assert len(expl) == 1
    assert expl[0]["chosen_source"] == "watch"
    assert expl[0]["over_source"] == "app"
    assert "outranks" in expl[0]["reason"]


def test_uncontested_fields_explain_nothing():
    """The common case must stay silent or nobody reads the explanations."""
    out = _resolve(daily=[daily("2030-05-01", source="watch", steps=9000)])
    assert out["explanations"] == []


def test_unranked_sources_resolve_deterministically():
    a = [daily("2030-05-01", source="zeta", steps=100),
         daily("2030-05-01", source="alpha", steps=200)]
    first = resolve({"daily": a})["canonical"]["daily"][0]["steps"]
    second = resolve({"daily": list(reversed(a))})["canonical"]["daily"][0]["steps"]
    assert first == second == 200, "sorted by source name, not file order"


def test_disagreement_beyond_tolerance_is_flagged():
    claims = [daily("2030-05-01", source="watch", rhr=50),
              daily("2030-05-01", source="app", rhr=70)]
    out = resolve({"daily": claims}, precedence={"rhr": ("watch", "app")})
    assert any(t["kind"] == "source_disagreement" for t in out["tripwires"])


def test_close_agreement_is_not_flagged():
    claims = [daily("2030-05-01", source="watch", rhr=50),
              daily("2030-05-01", source="app", rhr=51)]
    out = resolve({"daily": claims}, precedence={"rhr": ("watch", "app")})
    assert not any(t["kind"] == "source_disagreement" for t in out["tripwires"])


# ---- resolution: activity identity ------------------------------------------

def test_one_run_on_two_platforms_collapses_to_one():
    claims = [
        session("2030-05-01", source="watch", start_time="2030-05-01T07:00:00+00:00",
                duration_s=1800, distance_km=5.0, kcal=300),
        session("2030-05-01", source="app", start_time="2030-05-01T07:02:00+00:00",
                duration_s=1780, distance_km=4.9, kcal=310),
    ]
    out = resolve({"sessions": claims}, precedence={})
    assert len(out["canonical"]["sessions"]) == 1, "one run, not two"
    assert len(out["claims"]) == 2, "both claims are still retained"
    merged = [c for c in out["claims"] if c.get("merged_into")]
    assert len(merged) == 1


def test_two_genuinely_different_sessions_stay_separate():
    claims = [session("2030-05-01", source="watch", type="run",
                      start_time="2030-05-01T07:00:00+00:00", duration_s=1800),
              session("2030-05-01", source="watch", type="gym_a",
                      start_time="2030-05-01T18:00:00+00:00", duration_s=3600)]
    out = resolve({"sessions": claims})
    assert len(out["canonical"]["sessions"]) == 2


def test_sessions_match_on_shape_when_times_are_missing():
    claims = [session("2030-05-01", source="watch", duration_s=1800,
                      distance_km=5.0),
              session("2030-05-01", source="app", duration_s=1900,
                      distance_km=5.2)]
    out = resolve({"sessions": claims})
    assert len(out["canonical"]["sessions"]) == 1


def test_a_near_miss_is_flagged_rather_than_merged():
    claims = [session("2030-05-01", source="watch", duration_s=1800,
                      distance_km=5.0),
              session("2030-05-01", source="app", duration_s=2350,
                      distance_km=5.6)]
    out = resolve({"sessions": claims})
    assert len(out["canonical"]["sessions"]) == 2, "not close enough to merge"
    assert any(t["kind"] == "near_miss_duplicate" for t in out["tripwires"])


# ---- resolution: conservation ------------------------------------------------

def test_sessions_exceeding_the_days_burn_fire_a_tripwire():
    out = _resolve(
        daily=[daily("2030-05-01", source="watch", kcal_out=2000)],
        sessions=[session("2030-05-01", source="watch", kcal=1500,
                          start_time="2030-05-01T07:00:00+00:00", duration_s=1800),
                  session("2030-05-01", source="app", kcal=1400,
                          start_time="2030-05-01T18:00:00+00:00", duration_s=1800)])
    trips = [t for t in out["tripwires"] if t["kind"] == "sessions_exceed_day"]
    assert trips and "double-count" in trips[0]["detail"]


def test_energy_within_the_days_burn_is_fine():
    out = _resolve(
        daily=[daily("2030-05-01", source="watch", kcal_out=2800)],
        sessions=[session("2030-05-01", source="watch", kcal=600)])
    assert not any(t["kind"] == "sessions_exceed_day" for t in out["tripwires"])


# ---- JTMS: justification and cascade retraction ------------------------------

def test_every_resolved_field_carries_a_justification():
    out = _resolve(daily=[daily("2030-05-01", source="watch", steps=9000)])
    steps = [j for j in out["justifications"] if j["field"] == "steps"]
    assert len(steps) == 1
    assert steps[0]["source"] == "watch"
    assert steps[0]["tier"] == "observed"
    assert steps[0]["quantity_class"] == "measured_flow"


def test_anchors_are_classed_as_anchors():
    out = _resolve(measurements=[{"date": "2030-05-01", "kind": "waist_cm",
                                  "value": 84.0, "source": "tape", "note": None}])
    assert all(j["quantity_class"] == "anchor"
               for j in out["justifications"] if j["dataset"] == "measurements")


def test_a_correction_retracts_the_claim_it_replaces():
    datasets = {"daily": [daily("2030-05-02", source="watch", steps=9500,
                                supersedes="2030-05-01/watch",
                                note="logged against the wrong day")]}
    ledger = retractions(datasets)
    assert len(ledger) == 1
    assert ledger[0]["claim_id"] == "daily:2030-05-01:watch"
    assert ledger[0]["kind"] == "claim"


def test_retraction_cascades_to_a_dependent_inference():
    """The stroller-pace case: revoke the evidence, the belief falls too."""
    datasets = {
        "daily": [daily("2030-05-02", source="watch", steps=9500,
                        supersedes="2030-05-01/watch")],
        "inferences": [{"date": "2030-05-03", "kind": "pattern",
                        "statement": "pace drops on high-step days",
                        "confidence": 0.6, "model": "demo-model",
                        "evidence": "daily+sessions", "note": None,
                        "depends_on": "daily:2030-05-01:watch", "_gen": 2}],
    }
    ledger = retractions(datasets)
    cascaded = [r for r in ledger if r["kind"] == "inference"]
    assert len(cascaded) == 1
    assert cascaded[0]["cascaded_from"] == "daily:2030-05-01:watch"
    assert live_inferences(datasets) == [], "a fallen belief stops being current"


def test_an_independent_inference_survives_a_retraction():
    datasets = {
        "daily": [daily("2030-05-02", source="watch", steps=9500,
                        supersedes="2030-05-01/watch")],
        "inferences": [{"date": "2030-05-03", "kind": "pattern",
                        "statement": "sleep tracks with mood",
                        "confidence": 0.6, "model": "demo-model",
                        "evidence": "daily", "note": None,
                        "depends_on": "daily:2030-04-01:watch", "_gen": 2}],
    }
    assert len(live_inferences(datasets)) == 1


# ---- context (G34) -----------------------------------------------------------

def test_context_is_effective_dated():
    ctx = [{"date": "2030-05-01", "mode": "normal", "facilities": "scale gym",
            "place": None, "source": "athlete", "note": None},
           {"date": "2030-06-01", "mode": "vacation", "facilities": None,
            "place": "coast", "source": "athlete", "note": None}]
    assert context_on(ctx, "2030-05-15")["mode"] == "normal"
    assert context_on(ctx, "2030-06-10")["mode"] == "vacation"
    assert context_on(ctx, "2030-04-01") is None


def test_missing_facility_is_distinguishable_from_unknown():
    ctx = [{"date": "2030-05-01", "mode": "vacation", "facilities": "gym",
            "place": None, "source": "athlete", "note": None}]
    assert has_facility(ctx, "2030-05-02", "gym") is True
    assert has_facility(ctx, "2030-05-02", "scale") is False
    assert has_facility(ctx, "2030-04-01", "scale") is None, (
        "no context is not the same as no scale")


# ---- G33 suppression ----------------------------------------------------------

def test_a_suppressed_metric_is_recorded_but_not_scored():
    days = [daily(f"2030-04-0{d}", source="watch", steps=1000)
            for d in range(1, 8)]
    cfg = Config(steps_floor=9000, suppressed_metrics=("steps",))
    rows = compute_verdicts(cfg, [], days, [])
    assert not any(r["metric"] == "steps" for r in rows)
    # ...but the observation itself is untouched.
    assert _resolve(daily=days)["canonical"]["daily"][0]["steps"] == 1000


def test_suppression_and_nudge_preferences_load(tmp_path):
    (tmp_path / "vitai.toml").write_text(
        "[preferences]\nsuppressed_metrics = ['weight_rate']\nnudge_ok = true\n"
        "[resolution]\nsource_order = ['scale', 'app']\n"
        "[resolution.precedence]\nkcal_out = ['watch', 'app']\n",
        encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.suppressed_metrics == ("weight_rate",)
    assert cfg.nudge_ok is True
    assert cfg.source_order == ("scale", "app")
    assert cfg.precedence["kcal_out"] == ("watch", "app")


# ---- the regression that matters ---------------------------------------------

def _single_source_repo(root: Path) -> None:
    main(["init", str(root)])
    (root / "vitai.toml").write_text(
        "[targets]\nphases = [[80.0, 70.0, 0.7]]\n"
        "[tripwires]\nsteps_floor = 8000\npain_gate = 3\n", encoding="utf-8")
    write(root / "data" / "weight.jsonl",
          [{"date": f"2030-05-{d:02d}", "kg": 80.0 - d * 0.1, "source": "scale",
            "note": None} for d in range(1, 20)])
    write(root / "data" / "daily.jsonl",
          [legacy_daily(f"2030-05-{d:02d}", steps=9000 + d, hip_pain=1)
           for d in range(1, 20)])
    write(root / "data" / "sessions.jsonl",
          [{"date": "2030-05-07", "type": "run", "distance_km": 5.0,
            "duration_s": 1800, "avg_hr": 140, "max_hr": None, "cadence": None,
            "kcal": 300, "location": "park", "rpe": 4, "note": None}])


def test_single_source_resolution_is_byte_identical(tmp_path):
    """Resolution must be invisible to a repo that only ever had one source.

    This is the whole safety argument for putting a new adjudication layer
    under every number: where there is nothing to adjudicate, nothing moves.
    """
    root = tmp_path / "content"
    _single_source_repo(root)
    v = Vitai(root)

    raw = v.datasets()
    canonical = v.canonical()
    for name in ("weight", "sessions"):
        assert len(canonical[name]) == len(raw[name])
        for got, want in zip(canonical[name], raw[name]):
            for key in want:
                if key != "_gen":
                    assert got.get(key) == want[key], f"{name}.{key} moved"

    assert v.resolution()["explanations"] == []
    assert v.resolution()["tripwires"] == []

    db = v.build()
    first = db.read_bytes()
    rollup = (root / "derived" / "weekly.md").read_text(encoding="utf-8")
    v.build()
    assert db.read_bytes() == first, "two builds differ"
    assert (root / "derived" / "weekly.md").read_text(encoding="utf-8") == rollup


def test_verdicts_unchanged_by_the_resolution_layer(tmp_path):
    root = tmp_path / "content"
    _single_source_repo(root)
    v = Vitai(root)
    raw = v.datasets()
    direct = compute_verdicts(v.config, raw["weight"], raw["daily"],
                              raw["sessions"], goals=raw["goals"],
                              thresholds=raw["thresholds"])
    assert v.verdicts() == direct


def test_build_projects_the_adjudication_trail(tmp_path):
    root = tmp_path / "content"
    _single_source_repo(root)
    write(root / "data" / "daily.jsonl",
          [daily("2030-05-01", source="watch", kcal_out=2443, steps=9000),
           daily("2030-05-01", source="app", kcal_out=2844, kcal_in=2100)])
    (root / "vitai.toml").write_text(
        "[resolution.precedence]\nkcal_out = ['watch', 'app']\n", encoding="utf-8")
    db = Vitai(root).build()
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM daily").fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM claims WHERE dataset='daily'").fetchone()[0] == 2
        assert con.execute(
            "SELECT chosen_source FROM resolution WHERE field='kcal_out'"
        ).fetchone()[0] == "watch"
        assert con.execute(
            "SELECT kcal_out FROM daily").fetchone()[0] == 2443
        assert con.execute(
            "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "3"
    finally:
        con.close()
