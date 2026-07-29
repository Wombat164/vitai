"""Load the athlete's thresholds from the content repo's vitai.toml.

Everything is optional: an absent threshold disables the corresponding
verdict/tripwire rather than failing the build. The engine is the same for
everyone; the numbers are the athlete's.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
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


def load_inference_config(root: Path) -> dict:
    """The raw [inference] table from vitai.toml (empty dict if absent).
    Kept separate from Config: inference is the opt-in intelligence layer,
    not an engine threshold."""
    path = root / "vitai.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8")).get("inference", {})


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


# Threshold names that `thresholds.jsonl` can carry, and the type each takes.
# A dated threshold OVERRIDES the vitai.toml value: the toml is the starting
# point an athlete is handed, the dataset is the history they accumulate.
# `kcal_target` and `protein_g_target` live only in the dataset - they were
# never in Config, because a target you edit weekly must be dated (G20).
THRESHOLD_TYPES: dict[str, type] = {
    "easy_hr_cap": int,
    "rhr_baseline": int,
    "steps_floor": int,
    "sleep_floor_h": float,
    "pain_gate": int,
}


def overlay(cfg: Config, thresholds: dict[str, float]) -> Config:
    """`cfg` with any dated thresholds applied on top.

    Used with `policy.state(d).thresholds` so a week is judged against the
    numbers in force THEN, not the ones in vitai.toml today - the G14 fix.
    """
    if not thresholds:
        return cfg
    values = {}
    for key, caster in THRESHOLD_TYPES.items():
        if (v := thresholds.get(key)) is not None:
            try:
                values[key] = caster(v)
            except (TypeError, ValueError):
                continue
    return replace(cfg, **values) if values else cfg


def phase_rate_for(cfg: Config, kg: float) -> float | None:
    """Target rate (kg/week) for the phase containing this weight, else None."""
    for hi, lo, rate in cfg.phases:
        if lo < kg <= hi:
            return rate
    return cfg.phases[-1][2] if cfg.phases else None
