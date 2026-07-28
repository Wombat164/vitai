"""Load the athlete's thresholds from the content repo's vitai.toml.

Everything is optional: an absent threshold disables the corresponding
verdict/tripwire rather than failing the build. The engine is the same for
everyone; the numbers are the athlete's.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # [targets] phases: list of (from_kg, to_kg, kg_per_week), evaluated in order.
    phases: tuple[tuple[float, float, float], ...] = field(default_factory=tuple)
    # [tripwires]
    easy_hr_cap: int | None = None       # avg HR cap for easy runs (Z2 discipline)
    rhr_baseline: int | None = None      # resting HR baseline; alert at baseline + 5
    steps_floor: int | None = None       # daily steps floor
    sleep_floor_h: float | None = None   # 7-day average sleep floor
    pain_gate: int | None = None         # pain score (0-10) above which the gate fires


def load_config(root: Path) -> Config:
    path = root / "vitai.toml"
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    targets = raw.get("targets", {})
    trip = raw.get("tripwires", {})
    phases = tuple(
        (float(p[0]), float(p[1]), float(p[2])) for p in targets.get("phases", [])
    )
    return Config(
        phases=phases,
        easy_hr_cap=trip.get("easy_hr_cap"),
        rhr_baseline=trip.get("rhr_baseline"),
        steps_floor=trip.get("steps_floor"),
        sleep_floor_h=trip.get("sleep_floor_h"),
        pain_gate=trip.get("pain_gate"),
    )


def phase_rate_for(cfg: Config, kg: float) -> float | None:
    """Target rate (kg/week) for the phase containing this weight, else None."""
    for hi, lo, rate in cfg.phases:
        if lo < kg <= hi:
            return rate
    return cfg.phases[-1][2] if cfg.phases else None
