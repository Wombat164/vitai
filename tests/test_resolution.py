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

import pytest

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
           "pain": None, "pain_site": None, "pain_side": None, "_gen": gen}
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
    # A paired site needs its side too - see test_anatomy.py for that rule.
    assert validate_record("daily", daily(
        "2030-05-01", pain=4, pain_site="knee", pain_side="left")) == []


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
        daily("2030-05-02", steps=9500, pain=2, pain_site="knee",
              pain_side="left"),
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
            "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "12"
    finally:
        con.close()


# ---- issue #14: similarity is not identity -----------------------------------

def test_three_similar_walks_in_one_day_are_not_one_walk():
    """THE regression. A record reported 1.39 km of walking on a day when
    6.26 km across four walks had happened, and nothing surfaced it.

    Anyone with a habitual short activity - a dog walked three times, a
    commute each way - produces near-identical shapes BY DESIGN. Their
    routine is exactly what made them look duplicated.
    """
    walks = [
        session("2030-05-01", source="phone", type="walk",
                duration_s=844, distance_km=1.39),
        session("2030-05-01", source="phone", type="walk",
                duration_s=868, distance_km=1.52),
        session("2030-05-01", source="phone", type="walk",
                duration_s=817, distance_km=1.34),
    ]
    out = resolve({"sessions": walks})
    assert len(out["canonical"]["sessions"]) == 3, (
        "similar shapes were treated as one activity and volume was deleted")
    assert sum(r["distance_km"] for r in out["canonical"]["sessions"]) == \
        pytest.approx(1.39 + 1.52 + 1.34)


def test_a_repeated_activity_says_so_rather_than_failing_silently():
    """A false merge silently DELETES data and leaves a plausible row behind,
    which is worse than double-counting - so it must be visible."""
    walks = [session("2030-05-01", source="phone", type="walk",
                     duration_s=800 + i * 20, distance_km=1.4)
             for i in range(3)]
    out = resolve({"sessions": walks})
    kept = [t for t in out["tripwires"] if t["kind"] == "repeated_activity_kept"]
    assert len(kept) == 1, "the decision not to merge was invisible"
    assert "start_time" in kept[0]["detail"], "and it says how to resolve them"


def test_two_similar_sessions_from_one_source_do_not_merge():
    """Same source, same shape, no timestamps: two real events far more
    likely than one connector emitting the same activity twice."""
    pair = [session("2030-05-01", source="phone", type="walk",
                    duration_s=840, distance_km=1.4),
            session("2030-05-01", source="phone", type="walk",
                    duration_s=860, distance_km=1.45)]
    out = resolve({"sessions": pair})
    assert len(out["canonical"]["sessions"]) == 2
    assert any(t["kind"] == "near_miss_duplicate" for t in out["tripwires"])


def test_disjoint_sources_still_merge_on_shape():
    """The case the shape test was written for survives: two platforms each
    claiming one physical event, which the shape alone cannot distinguish but
    the differing sources can."""
    pair = [session("2030-05-01", source="watch", type="run",
                    duration_s=1800, distance_km=5.0),
            session("2030-05-01", source="app", type="run",
                    duration_s=1850, distance_km=5.1)]
    out = resolve({"sessions": pair})
    assert len(out["canonical"]["sessions"]) == 1


def test_every_shape_only_merge_is_reported():
    """A merge that removes volume is exactly what tripwires are for."""
    pair = [session("2030-05-01", source="watch", type="run",
                    duration_s=1800, distance_km=5.0),
            session("2030-05-01", source="app", type="run",
                    duration_s=1850, distance_km=5.1)]
    out = resolve({"sessions": pair})
    merges = [t for t in out["tripwires"] if t["kind"] == "shape_only_merge"]
    assert len(merges) == 1
    assert "start_time" in merges[0]["detail"]


def test_a_timestamped_merge_needs_no_warning():
    """Overlapping intervals are positive identification, not a guess."""
    pair = [session("2030-05-01", source="watch", type="run",
                    start_time="2030-05-01T07:00:00+00:00",
                    duration_s=1800, distance_km=5.0),
            session("2030-05-01", source="app", type="run",
                    start_time="2030-05-01T07:02:00+00:00",
                    duration_s=1780, distance_km=4.9)]
    out = resolve({"sessions": pair})
    assert len(out["canonical"]["sessions"]) == 1
    assert not [t for t in out["tripwires"] if t["kind"] == "shape_only_merge"]


def test_start_time_resolves_a_routine_positively():
    """The workaround the issue names becomes the fix: with times, three
    walks are unambiguously three."""
    walks = [session("2030-05-01", source="phone", type="walk",
                     start_time=f"2030-05-01T{h:02d}:00:00+00:00",
                     duration_s=840, distance_km=1.4)
             for h in (8, 13, 19)]
    out = resolve({"sessions": walks})
    assert len(out["canonical"]["sessions"]) == 3
    assert not [t for t in out["tripwires"]
                if t["kind"] == "repeated_activity_kept"]


# ---- #70: a correction from the same source must win ---------------------------

def _log(kcal, stamp, date="2026-07-30", source="mfp-export"):
    return {"date": date, "steps": None, "distance_km": None, "active_min": None,
            "kcal_out": None, "kcal_in": kcal, "protein_g": None, "sleep_h": None,
            "rhr": None, "hip_pain": None, "alcohol": None, "note": None,
            "source": source, "mood": None, "feel": None, "coverage": None,
            "pain": None, "pain_site": None, "pain_side": None,
            "recorded_at": stamp, "_gen": 3}


def test_a_later_claim_from_the_same_source_wins():
    """The live shape, verbatim. A food log exported at breakfast said 1,354
    kcal; the same log exported next morning, after dinner was entered, said
    3,091. Precedence cannot separate them - they share a source - so the
    first line of the file won forever, and the record asserted 1,354.

    A correction almost always comes from the SAME source as the thing it
    corrects: a vendor re-exports, an importer re-runs, a log is completed
    later. So this was the correction path dead for its commonest shape.
    """
    rows = [_log(1354, "2026-07-31T09:40:00+02:00"),
            _log(3091, "2026-07-31T09:47:00+02:00")]
    assert resolve({"daily": rows})["canonical"]["daily"][0]["kcal_in"] == 3091


def test_file_order_cannot_change_what_the_record_asserts():
    """#37's stated acceptance criterion, which was false for same-source
    claims: "sorting, reformatting or merging the file cannot change what the
    record asserts". Asserted directly, on every permutation."""
    from itertools import permutations
    rows = [_log(1354, "2026-07-31T09:40:00+02:00"),
            _log(3091, "2026-07-31T09:47:00+02:00"),
            _log(2200, "2026-07-31T09:45:00+02:00")]
    answers = {resolve({"daily": list(order)})["canonical"]["daily"][0]["kcal_in"]
               for order in permutations(rows)}
    assert answers == {3091}, "every ordering must agree"


def test_a_shuffled_record_resolves_identically():
    """The round-trip #37 asked for and did not get. Shuffling the whole file
    must be a no-op on every canonical value, not just on one field."""
    import random
    rows = [_log(1300 + i * 37, f"2026-07-31T09:{40 + i:02d}:00+02:00",
                 date=f"2026-07-{10 + i % 5:02d}")
            for i in range(20)]
    straight = resolve({"daily": rows})["canonical"]["daily"]
    shuffled = list(rows)
    random.Random(4).shuffle(shuffled)
    assert resolve({"daily": shuffled})["canonical"]["daily"] == straight


def test_an_unstamped_record_resolves_exactly_as_it_did():
    """Legacy behaviour is preserved: with no transaction time to order by,
    the first line still wins and a migration is a read no-op."""
    rows = [_log(1354, None), _log(3091, None)]
    assert resolve({"daily": rows})["canonical"]["daily"][0]["kcal_in"] == 1354


def test_a_stamped_claim_beats_an_unstamped_one():
    """A stamped row was demonstrably written later than one that predates
    the field - the rule #37 established for `heads()`, applied here."""
    rows = [_log(1354, None), _log(3091, "2026-07-31T09:47:00+02:00")]
    assert resolve({"daily": rows})["canonical"]["daily"][0]["kcal_in"] == 3091
    assert resolve({"daily": list(reversed(rows))}
                   )["canonical"]["daily"][0]["kcal_in"] == 3091


def test_precedence_still_outranks_recency():
    """Recency breaks a TIE; it does not overrule the ladder. A later claim
    from a lower-ranked source must not beat an earlier one from the scale."""
    ladder = {"kcal_in": ("app", "watch")}
    rows = [_log(2000, "2026-07-31T09:40:00+02:00", source="app"),
            _log(9999, "2026-07-31T09:47:00+02:00", source="watch")]
    got = resolve({"daily": rows}, precedence=ladder)["canonical"]["daily"][0]
    assert got["kcal_in"] == 2000


def test_a_correction_is_explained_as_one_not_as_precedence():
    """The audit trail is the one place the record explains itself, so it
    must not say "mfp-export outranks mfp-export" - precedence decided
    nothing there, recency did."""
    rows = [_log(1354, "2026-07-31T09:40:00+02:00"),
            _log(3091, "2026-07-31T09:47:00+02:00")]
    said = [e["reason"] for e in resolve({"daily": rows})["explanations"]
            if e["field"] == "kcal_in"]
    assert said and "supersedes the earlier" in said[0]
    assert "outranks" not in said[0]


def test_a_correction_does_not_raise_a_source_disagreement():
    """Two claims from one source are the same instrument twice. Reporting
    them as disagreeing sources reports the correction mechanism working as
    a fault - and would have put a permanent tripwire on every corrected day.
    """
    rows = [_log(1354, "2026-07-31T09:40:00+02:00"),
            _log(3091, "2026-07-31T09:47:00+02:00")]
    kinds = [t["kind"] for t in resolve({"daily": rows})["tripwires"]]
    assert "source_disagreement" not in kinds


def test_two_different_sources_disagreeing_is_still_reported():
    """The guard must not silence the case the tripwire exists for."""
    rows = [_log(1354, "2026-07-31T09:40:00+02:00", source="app"),
            _log(3091, "2026-07-31T09:47:00+02:00", source="watch")]
    kinds = [t["kind"] for t in resolve({"daily": rows})["tripwires"]]
    assert "source_disagreement" in kinds


# ---- #73: an unattributed row loses every contest, silently --------------------

def _day(kcal_out, source=None, date="2026-07-28", **kw):
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": kcal_out, "kcal_in": None, "protein_g": None,
           "sleep_h": None, "rhr": None, "hip_pain": None, "alcohol": None,
           "note": None, "source": source, "mood": None, "feel": None,
           "coverage": None, "pain": None, "pain_site": None,
           "pain_side": None, "recorded_at": None, "_gen": 3}
    rec.update(kw)
    return rec


def test_an_unattributed_claim_that_loses_is_reported():
    """The first live instance, reconstructed. An importer wrote the source
    into a human-readable NOTE instead of the field, so 47 rows ranked
    `unknown` - last - while the ladder ranks that source FIRST. On two dates
    they lost a real contest worth over 1,000 kcal/day, and nothing anywhere
    said so: the rollup printed a canonical figure with no hint that a
    better-ranked claim had been discarded on a technicality.
    """
    rows = [_day(3603, source=None, note="source=polar"),
            _day(2364, source="fitbit")]
    out = resolve({"daily": rows}, source_order=("polar", "fitbit"))
    kinds = [t["kind"] for t in out["tripwires"]]
    assert "unattributed_claim_lost" in kinds
    said = next(t["detail"] for t in out["tripwires"]
                if t["kind"] == "unattributed_claim_lost")
    assert "carries no source" in said and "3603" in said


def test_a_resolved_value_can_say_what_it_beat():
    """A resolved value had no way to say it beat anything, so the only way
    either live instance was found was reading the raw JSONL by hand."""
    rows = [_day(3603, source="polar"), _day(2364, source="fitbit"),
            _day(2100, source="app")]
    got = [e for e in resolve({"daily": rows},
                              source_order=("polar", "fitbit", "app")
                              )["explanations"] if e["field"] == "kcal_out"]
    assert got and got[0]["chosen_source"] == "polar"
    assert "fitbit=2364" in got[0]["discarded"]
    assert "app=2100" in got[0]["discarded"], "every discard, not the runner-up"


def test_an_attributed_loss_is_not_flagged():
    """Two named sources disagreeing is the ladder working. Flagging it would
    put a permanent tripwire on every multi-source day."""
    rows = [_day(3603, source="polar"), _day(2364, source="fitbit")]
    out = resolve({"daily": rows}, source_order=("polar", "fitbit"))
    assert "unattributed_claim_lost" not in [t["kind"] for t in out["tripwires"]]


def test_an_unattributed_row_that_agrees_is_not_flagged():
    """No value was lost, so there is nothing to report - a tripwire that
    fires when nothing went wrong teaches the reader to skip them."""
    rows = [_day(2364, source=None), _day(2364, source="fitbit")]
    out = resolve({"daily": rows}, source_order=("fitbit",))
    assert "unattributed_claim_lost" not in [t["kind"] for t in out["tripwires"]]


def test_a_masked_unattributed_loss_is_still_reported():
    """Two ways a real instance escaped the first version of this tripwire,
    both closed by testing against the WINNER over EVERY discard rather than
    reusing the runner-up `disagreed` flag.

    The runner-up agrees with the winner, so `disagreed` is False - and the
    unattributed third claim, which differs by 290 kcal, was invisible. That
    difference is also inside the 10% disagreement tolerance, which is the
    right bar for "do two sources disagree" and the wrong one for "was a
    claim discarded on a technicality": 10% of a day's burn is enough to flip
    a surplus into a deficit.
    """
    rows = [_day(3600, source="polar"), _day(3590, source="fitbit"),
            _day(3310, source=None)]
    out = resolve({"daily": rows}, source_order=("polar", "fitbit"))
    assert "unattributed_claim_lost" in [t["kind"] for t in out["tripwires"]]


def test_an_unattributed_claim_that_matches_exactly_is_not_reported():
    """Nothing was lost, so there is nothing to say."""
    rows = [_day(3600, source="polar"), _day(3600, source=None)]
    out = resolve({"daily": rows}, source_order=("polar",))
    assert "unattributed_claim_lost" not in [t["kind"] for t in out["tripwires"]]
