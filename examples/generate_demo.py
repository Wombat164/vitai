#!/usr/bin/env python3
"""Generate the synthetic demo content repo at examples/demo/.

Deterministic (seeded) so the committed data is reproducible and CI can prove
it - the demo is the plan's visibility substrate ("demo or it didn't happen").
A fictional athlete, ~12 weeks: a weight cut on an on-target rate, Tue/Thu runs
with an easy-HR story, weekend gym sessions, daily steps/sleep/rhr, two
inferences. Writes only current-schema (generation-1) fields.

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
    (target / "data" / "weight.jsonl").write_text(_jsonl(weight), encoding="utf-8", newline="\n")
    (target / "data" / "daily.jsonl").write_text(_jsonl(daily), encoding="utf-8", newline="\n")
    (target / "data" / "sessions.jsonl").write_text(_jsonl(sessions), encoding="utf-8", newline="\n")
    (target / "data" / "inferences.jsonl").write_text(_jsonl(inferences), encoding="utf-8", newline="\n")


def _read_all(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*")) if p.is_file()}


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
