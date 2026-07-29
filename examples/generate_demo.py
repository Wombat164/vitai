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

TOML = (
    "# Demo athlete thresholds (synthetic).\n"
    "[targets]\n"
    "phases = [[80.0, 76.0, 0.35], [76.0, 74.0, 0.25]]\n\n"
    "[tripwires]\n"
    "easy_hr_cap = 152\n"
    "rhr_baseline = 51\n"
    "steps_floor = 9000\n"
    "sleep_floor_h = 7.0\n"
    "pain_gate = 3\n"
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
        kg -= 0.05 * (0.7 + 0.6 * rng.random())            # ~0.24-0.45 kg/wk
        if rng.random() < 0.8:
            weight.append({"date": d, "kg": round(kg + rng.gauss(0, 0.25), 1),
                           "source": "scale", "note": None})
        steps = int(rng.gauss(11500 if dow < 5 else 8300, 2100))
        if TRAVEL_WEEK[0] <= i <= TRAVEL_WEEK[1]:
            # A travel week: the steps floor is missed outright. This is the
            # week the athlete reacts to by lowering the floor a few days
            # later - the sequence the suspicious-edit flag exists to catch.
            steps = int(rng.gauss(5600, 900))
        daily.append({"date": d, "steps": max(2500, steps),
                      "distance_km": round(max(2.5, steps) * 0.00075, 1),
                      "active_min": int(max(60, rng.gauss(300, 70))),
                      "kcal_out": int(rng.gauss(2850, 220)),
                      "kcal_in": int(rng.gauss(2150, 260)),
                      "protein_g": int(rng.gauss(145, 25)),
                      "sleep_h": round(max(4.5, rng.gauss(7.3, 0.7)), 1),
                      "rhr": int(rng.gauss(51, 2.2)),
                      "hip_pain": rng.choice([0] * 10 + [1, 1, 2]),
                      "alcohol": rng.random() < 0.12, "note": None})
        if dow in (1, 3):                                   # Tue/Thu runs
            hard = rng.random() < 0.3
            km = round(max(3.0, rng.gauss(6.5 if not hard else 5.0, 1.0)), 2)
            sessions.append({"date": d, "type": "run", "distance_km": km,
                             "duration_s": int(km * rng.gauss(390, 25)),
                             "avg_hr": int(rng.gauss(166 if hard else 147, 5)),
                             "max_hr": None, "cadence": int(rng.gauss(168, 4)),
                             "kcal": int(km * 61), "location": None,
                             "rpe": 7 if hard else 4, "note": None})
        if dow in (5, 6) and rng.random() < 0.8:            # weekend gym
            sessions.append({"date": d, "type": rng.choice(["gym_a", "gym_b"]),
                             "distance_km": None,
                             "duration_s": int(rng.gauss(3300, 400)),
                             "avg_hr": None, "max_hr": None, "cadence": None,
                             "kcal": None, "location": None,
                             "rpe": rng.choice([5, 6]), "note": None})
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
    sessions.sort(key=lambda s: (s["date"], s["type"]))

    goals, thresholds, achievements = _policy(start)

    for name, rows in (("weight", weight), ("daily", daily),
                       ("sessions", sessions), ("inferences", inferences),
                       ("goals", goals), ("thresholds", thresholds),
                       ("achievements", achievements)):
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
