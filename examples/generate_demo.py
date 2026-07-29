#!/usr/bin/env python3
"""Generate the synthetic demo content repo at examples/demo/.

Deterministic (seeded) so the committed data is reproducible and CI can prove
it - the demo is the plan's visibility substrate ("demo or it didn't happen").
A fictional athlete, ~12 weeks: a weight cut on an on-target rate, Tue/Thu runs
with an easy-HR story, weekend gym sessions, daily steps/sleep/rhr, two
inferences. Writes only current-schema (generation-1) fields.

Increment 1 adds the goal story the contribution model exists to show:
- a MONOTONIC steps goal, where every step counts;
- a GUARDED running goal, where volume beyond a 10% weekly ramp does not;
- one big unplanned long run near the end, which advances the steps goal,
  is refused by the running goal, and mints no milestone;
- a goal edit and a threshold change, so the record has an audit trail to
  reconstruct - including one loosening timed right after a missed week.

    python examples/generate_demo.py          # (re)write examples/demo/
    python examples/generate_demo.py --check  # fail if committed data drifts

NO real person's data is ever in this repo.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"
END = date(2030, 6, 30)
DAYS = 84
# Day offsets of the travel week (the ISO week beginning 2030-05-27), which the
# athlete misses and then responds to by lowering the floor on 2030-06-06.
TRAVEL_WEEK = (49, 55)
# Day offset from which the athlete's lines carry generation-2 provenance and
# context fields. Before it they are founding-shape lines - deliberately, so
# the committed demo proves both shapes coexist in one file.
GEN2_FROM = 42

TOML = (
    "# Demo athlete thresholds (synthetic).\n"
    "[targets]\n"
    "phases = [[80.0, 76.0, 0.35], [76.0, 74.0, 0.25]]\n\n"
    "[tripwires]\n"
    "easy_hr_cap = 152\n"
    "rhr_baseline = 51\n"
    "steps_floor = 9000\n"
    "sleep_floor_h = 7.0\n"
    "pain_gate = 3\n\n"
    "# Which source wins which quantity when two of them describe one day.\n"
    "# The watch measures burn; the calorie app only models it. The app owns\n"
    "# intake, which the watch never sees at all.\n"
    "[resolution]\n"
    'source_order = ["scale", "watch", "app"]\n\n'
    "[resolution.precedence]\n"
    'kcal_out = ["watch", "app"]\n'
    'kcal_in = ["app"]\n'
    'protein_g = ["app"]\n'
    'steps = ["watch", "app"]\n'
)


def _jsonl(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def _build(target: Path) -> None:
    """Write the demo content repo into `target` (deterministic)."""
    rng = random.Random(42)
    (target / "data").mkdir(parents=True, exist_ok=True)
    (target / "vitai.toml").write_text(TOML, encoding="utf-8", newline="\n")

    start = END - timedelta(days=DAYS - 1)
    weight, daily, sessions = [], [], []
    kg = 80.2
    for i in range(DAYS):
        d = (start + timedelta(days=i)).isoformat()
        dow = (start + timedelta(days=i)).weekday()
        gen2 = i >= GEN2_FROM
        kg -= 0.05 * (0.7 + 0.6 * rng.random())            # ~0.24-0.45 kg/wk
        # No scale during the travel week - the weigh-ins are genuinely absent,
        # and context.jsonl says why. An engine that flagged that as a lapse
        # would be punishing the athlete for being away from their bathroom.
        weighed = rng.random() < 0.8 and not TRAVEL_WEEK[0] <= i <= TRAVEL_WEEK[1]
        if weighed:
            weight.append({"date": d, "kg": round(kg + rng.gauss(0, 0.25), 1),
                           "source": "scale", "note": None})
        steps = int(rng.gauss(11500 if dow < 5 else 8300, 2100))
        if TRAVEL_WEEK[0] <= i <= TRAVEL_WEEK[1]:
            # A travel week: the steps floor is missed outright. This is the
            # week the athlete reacts to by lowering the floor a few days
            # later - the sequence the suspicious-edit flag exists to catch.
            steps = int(rng.gauss(5600, 900))
        row = {"date": d, "steps": max(2500, steps),
               "distance_km": round(max(2.5, steps) * 0.00075, 1),
               "active_min": int(max(60, rng.gauss(300, 70))),
               "kcal_out": int(rng.gauss(2850, 220)),
               "kcal_in": int(rng.gauss(2150, 260)),
               "protein_g": int(rng.gauss(145, 25)),
               "sleep_h": round(max(4.5, rng.gauss(7.3, 0.7)), 1),
               "rhr": int(rng.gauss(51, 2.2)),
               "alcohol": rng.random() < 0.12, "note": None}
        pain = rng.choice([0] * 10 + [1, 1, 2])
        if gen2:
            # The athlete's tracker gained provenance mid-block. Both shapes
            # live in one file from here on, which is the point: the migration
            # is additive, and the old lines never had to be rewritten.
            row.update({"_gen": 2, "source": "watch", "pain": pain,
                        "pain_site": "hip" if pain else None,
                        # `hip` is a paired structure, so the side is required
                        # for the entry to be actionable: which hip.
                        "pain_side": "right" if pain else None,
                        "mood": max(1, min(10, int(rng.gauss(7, 1.5)))),
                        "feel": rng.choice(["fun", "neutral", "neutral", "chore"]),
                        "coverage": "full"})
        else:
            row["hip_pain"] = pain
        daily.append(row)
        if dow in (1, 3):                                   # Tue/Thu runs
            hard = rng.random() < 0.3
            km = round(max(3.0, rng.gauss(6.5 if not hard else 5.0, 1.0)), 2)
            run = {"date": d, "type": "run", "distance_km": km,
                   "duration_s": int(km * rng.gauss(390, 25)),
                   "avg_hr": int(rng.gauss(166 if hard else 147, 5)),
                   "max_hr": None, "cadence": int(rng.gauss(168, 4)),
                   "kcal": int(km * 61), "rpe": 7 if hard else 4, "note": None}
            if gen2:
                run.update({"_gen": 2, "source": "watch",
                            "start_time": f"{d}T18:10:00+02:00",
                            "elevation_m": round(max(0.0, rng.gauss(35, 15)), 1),
                            "setting": "outdoor", "route": "canal-loop",
                            "place": "home", "with": None, "context": "solo",
                            "planned": "running",
                            "weather": rng.choice(["dry", "dry", "rain", "wind"])})
            else:
                run["location"] = None
            sessions.append(run)
        if dow in (5, 6) and rng.random() < 0.8:            # weekend gym
            gym = {"date": d, "type": rng.choice(["gym_a", "gym_b"]),
                   "distance_km": None,
                   "duration_s": int(rng.gauss(3300, 400)),
                   "avg_hr": None, "max_hr": None, "cadence": None,
                   "kcal": None, "rpe": rng.choice([5, 6]), "note": None}
            if gen2:
                gym.update({"_gen": 2, "source": "watch",
                            "start_time": f"{d}T10:30:00+02:00",
                            "elevation_m": None, "setting": "indoor",
                            "route": None, "place": "home", "with": None,
                            "context": "solo", "planned": None, "weather": None})
            else:
                gym["location"] = None
            sessions.append(gym)
    inferences = [
        {"date": (END - timedelta(days=9)).isoformat(), "kind": "pattern",
         "statement": "Easy-run heart rate drifts over the cap in weeks where "
                      "average sleep is under 7h.",
         "confidence": 0.7, "model": "demo-model",
         "evidence": "sessions+daily, weeks of 2030-05-20 and 2030-06-03",
         "note": None},
        {"date": (END - timedelta(days=2)).isoformat(), "kind": "observation",
         "statement": "Weekend step counts run about 3k below weekdays; the "
                      "floor is carried by commute days.",
         "confidence": 0.85, "model": "demo-model",
         "evidence": "daily.steps by weekday, full range", "note": None},
    ]
    # The unplanned long run: a Saturday late in the block, after that week's
    # Tue/Thu runs have already spent the ramp budget. This is the event the
    # split verdict is built to explain.
    big_run_day = END - timedelta(days=7)
    sessions.append({"date": big_run_day.isoformat(), "type": "run",
                     "distance_km": 21.1,
                     "duration_s": int(21.1 * 402), "avg_hr": 158,
                     "max_hr": None, "cadence": 166, "kcal": int(21.1 * 61),
                     "location": None, "rpe": 8,
                     "note": "unplanned - joined a group long run"})
    # A richly-contextful day: a rainy Sunday walk with a partner on a route
    # the athlete has a name for. None of it is a number, and all of it is
    # what makes the day legible six months later.
    context_day = (END - timedelta(days=14)).isoformat()
    sessions.append({
        "date": context_day, "type": "walk", "distance_km": 6.4,
        "duration_s": 4920, "avg_hr": 104, "max_hr": None, "cadence": None,
        "kcal": 290, "rpe": 2, "note": None, "_gen": 2, "source": "watch",
        "start_time": f"{context_day}T14:05:00+02:00", "elevation_m": 18.0,
        "setting": "outdoor", "route": "canal-loop", "place": "home",
        "with": "partner", "context": "family", "planned": None,
        "weather": "rain"})
    for row in daily:
        if row["date"] == context_day:
            row.update({"mood": 9, "feel": "fun", "coverage": "full"})

    # A two-source day: the calorie app disagrees with the watch about burn,
    # and owns intake the watch never sees. Field-wise precedence takes the
    # best witness per quantity - it does not add 2,443 to 2,844.
    two_source_day = (END - timedelta(days=21)).isoformat()
    app_claim = {"date": two_source_day, "steps": None, "distance_km": None,
                 "active_min": None, "kcal_out": 2844, "kcal_in": 2210,
                 "protein_g": 152, "sleep_h": None, "rhr": None,
                 "alcohol": None, "note": "logged in the calorie app",
                 "_gen": 2, "source": "app", "mood": None, "feel": None,
                 "coverage": "manual", "pain": None, "pain_site": None,
                 "pain_side": None}
    daily.append(app_claim)
    daily.sort(key=lambda r: (r["date"], r.get("source") or ""))
    sessions.sort(key=lambda s: (s["date"], s["type"], s.get("source") or ""))

    goals, thresholds, achievements = _policy(start)
    context, measurements = _situational(start, END)
    medical = _medical(start, END)

    for name, rows in (("weight", weight), ("daily", daily),
                       ("sessions", sessions), ("inferences", inferences),
                       ("goals", goals), ("thresholds", thresholds),
                       ("achievements", achievements), ("context", context),
                       ("measurements", measurements), ("medical", medical)):
        (target / "data" / f"{name}.jsonl").write_text(
            _jsonl(rows), encoding="utf-8", newline="\n")


def _goal(date: str, slug: str, title: str, metric: str, target, policy: str,
          **kw) -> dict:
    """A goals.jsonl line with every key present (null for unknown)."""
    rec = {"date": date, "slug": slug, "title": title, "metric": metric,
           "dataset": None, "session_type": None, "tracker": None,
           "target": target, "policy": policy, "guard_pct": None,
           "period": "weekly", "on_period_end": "reset", "deadline": None,
           "status": "active", "motivator": None, "rationale": None,
           "on_success": None, "on_miss": None, "accountability": None,
           "set_by": "onboard", "reason": None, "note": None}
    rec.update(kw)
    return rec


def _policy(start: date) -> tuple[list[dict], list[dict], list[dict]]:
    """The demo's dated policy: goals, threshold changes, one achievement."""
    d0 = start.isoformat()
    goals = [
        _goal(d0, "steps", "Walk 70k steps a week", "steps", 70000,
              "monotonic", dataset="daily",
              motivator="Keep the desk job from winning",
              rationale="10k a day, averaged - a floor that survives a bad day",
              on_success="hold", on_miss="reflect"),
        _goal(d0, "running", "Build to 30 km a week, injury-free", "distance_km",
              30, "guarded", guard_pct=0.1, dataset="sessions",
              session_type="run", deadline="2030-08-31",
              motivator="Finish the autumn half without limping",
              rationale="10% weekly ramp is the ceiling my hip tolerated last time",
              on_success="escalate", on_miss="hold"),
        # A goal that lives in another app entirely: vitai tracks and asks
        # about it, but never invents a verdict for it (G19).
        _goal((start + timedelta(days=21)).isoformat(), "segment",
              "Take back the riverside segment", "external", None, "monotonic",
              tracker="a public segment leaderboard", period="none",
              on_period_end=None,
              motivator="Losing it to a neighbour stung more than expected"),
        # The steps goal is raised once, mid-block, and explained.
        _goal((start + timedelta(days=42)).isoformat(), "steps",
              "Walk 77k steps a week", "steps", 77000, "monotonic",
              dataset="daily", set_by="athlete",
              reason="the 70k weeks stopped feeling like effort",
              motivator="Keep the desk job from winning",
              rationale="10k a day, averaged - a floor that survives a bad day",
              on_success="hold", on_miss="reflect"),
    ]
    thresholds = [
        {"date": d0, "key": "steps_floor", "value": 9000,
         "change_kind": "change", "set_by": "onboard",
         "reason": "starting floor from the onboarding interview", "note": None},
        {"date": d0, "key": "kcal_target", "value": 2150,
         "change_kind": "change", "set_by": "onboard",
         "reason": "deficit sized for the phase-1 rate", "note": None},
        {"date": d0, "key": "protein_g_target", "value": 145,
         "change_kind": "change", "set_by": "onboard",
         "reason": "1.8 g/kg at target weight", "note": None},
        # A deliberate loosening, three days after a missed steps week. The
        # engine flags the TIMING; the stated reason is what makes it readable
        # as a deload rather than a retreat.
        {"date": (start + timedelta(days=59)).isoformat(), "key": "steps_floor",
         "value": 8000, "change_kind": "change", "set_by": "athlete",
         "reason": "travel week, protecting the run block instead", "note": None},
    ]
    achievements = [
        {"date": (start + timedelta(days=77)).isoformat(),
         "title": "First 21 km in one run", "goal": "running",
         "source": "athlete",
         "note": "unplanned, and the hip held - but it was not budgeted"},
    ]
    return goals, thresholds, achievements


def _medical(start: date, end: date) -> list[dict]:
    """Two episodes: one closed, one still gating (G11).

    The resolved calf strain shows a complete lifecycle - onset, physio visit,
    resolution - so the episode window is visible with both ends. The achilles
    episode is deliberately left open at the end of the block so the demo
    always renders an ACTIVE gate: the state a consumer most needs to handle
    correctly, and the one that is easiest to forget to test against.

    Nothing here is a diagnosis and no clinician is named - `provider_type` is
    as specific as the record gets about who was seen.
    """
    return [
        {"date": (start + timedelta(days=9)).isoformat(), "slug": "calf-strain",
         "kind": "injury", "title": "Left calf strain on a hill rep",
         "body_site": "calf", "severity": "moderate", "status": "active",
         "resolved_date": None, "restricts": "run impact",
         "provider_type": None, "source": "athlete",
         "note": "pulled up mid-session, walked home"},
        {"date": (start + timedelta(days=14)).isoformat(), "slug": "calf-strain",
         "kind": "visit", "title": "Physio assessment - left calf",
         "body_site": "calf", "severity": "mild", "status": "monitoring",
         "resolved_date": None, "restricts": "impact",
         "provider_type": "physio", "source": "athlete",
         "note": "cleared to walk and cycle; graded return to running"},
        {"date": (start + timedelta(days=31)).isoformat(), "slug": "calf-strain",
         "kind": "injury", "title": "Left calf strain resolved",
         "body_site": "calf", "severity": "none", "status": "resolved",
         "resolved_date": (start + timedelta(days=31)).isoformat(),
         "restricts": None, "provider_type": "physio", "source": "athlete",
         "note": "full sessions with no symptoms for two weeks"},
        # Still open at the end of the block: the demo always has a live gate.
        {"date": (end - timedelta(days=4)).isoformat(), "slug": "achilles",
         "kind": "symptom", "title": "Right achilles soreness after the long run",
         "body_site": "achilles", "severity": "mild", "status": "monitoring",
         "resolved_date": None, "restricts": "impact", "provider_type": None,
         "source": "athlete",
         "note": "stiff first thing; eases once warm - watching it"},
    ]


def _situational(start: date, end: date) -> tuple[list[dict], list[dict]]:
    """Context timeline (G34) + the sparse anchor reads (G16)."""
    context = [
        {"date": start.isoformat(), "mode": "normal",
         "facilities": "scale gym routes", "place": "home",
         "source": "onboard", "note": "baseline setup"},
        # The travel week, declared. This is what turns a missing weigh-in
        # from a lapse into a circumstance the engine can account for.
        {"date": (start + timedelta(days=49)).isoformat(), "mode": "travel",
         "facilities": "routes", "place": "away", "source": "athlete",
         "note": "work trip - no scale, no gym, hotel treadmill only"},
        {"date": (start + timedelta(days=56)).isoformat(), "mode": "normal",
         "facilities": "scale gym routes", "place": "home",
         "source": "athlete", "note": "home again"},
    ]
    measurements = [
        {"date": start.isoformat(), "kind": "waist_cm", "value": 92.0,
         "source": "tape", "note": "morning, unfasted"},
        {"date": (start + timedelta(days=42)).isoformat(), "kind": "waist_cm",
         "value": 89.5, "source": "tape", "note": None},
        {"date": end.isoformat(), "kind": "waist_cm", "value": 88.0,
         "source": "tape", "note": None},
        # An anchor-class read the scale cannot produce.
        {"date": (start + timedelta(days=42)).isoformat(), "kind": "body_fat_pct",
         "value": 22.4, "source": "dexa", "note": "clinic scan"},
    ]
    return context, measurements


def _read_all(root: Path) -> dict[str, str]:
    """The generated INPUTS only.

    Deliberately skips derived/: it is gitignored and holds a binary SQLite
    file, so a local `vitai build` before `--check` would otherwise blow up on
    a UTF-8 decode rather than reporting drift.
    """
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file() and "derived" not in p.parts
            and p.suffix in (".jsonl", ".toml")}


def main() -> int:
    if "--check" in sys.argv[1:]:
        tmp = Path(tempfile.mkdtemp()) / "demo"
        _build(tmp)
        want, got = _read_all(tmp), _read_all(DEMO)
        # compare only the generated inputs (vitai.toml + data/), not derived/
        keys = {k for k in want} | {k for k in got if k.endswith((".jsonl", ".toml"))}
        drift = [k for k in sorted(keys) if want.get(k) != got.get(k)]
        if drift:
            print(f"demo data DRIFTED from generator: {drift}", file=sys.stderr)
            print("run `python examples/generate_demo.py` and commit.", file=sys.stderr)
            return 1
        print("demo data matches the generator")
        return 0
    _build(DEMO)
    print(f"wrote {DEMO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
