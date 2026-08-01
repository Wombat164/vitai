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
    # [resolution] which source wins which quantity (G15). `source_order` is
    # the fallback ladder; `precedence` overrides it per field.
    source_order: tuple[str, ...] = field(default_factory=tuple)
    precedence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # [preferences]
    # G33, the subtractive primitive: metrics the athlete has asked the engine
    # to LEAVE ALONE. They keep being recorded - the record stays complete -
    # but they produce no verdict and no tripwire. Someone recovering from a
    # disordered relationship with a number needs to be able to stop being
    # scored on it without deleting their history.
    suppressed_metrics: tuple[str, ...] = field(default_factory=tuple)
    # G7: whether proactive nudges are welcome at all. Default False - a coach
    # that has to be invited to interrupt is the safer default.
    nudge_ok: bool = False
    # How close a stated value must be to the record before `vitai check`
    # calls it confirmed. A fraction, not a law: 2% is a starting point, and
    # an athlete who rounds every number in conversation wants it looser.
    check_tolerance: float = 0.02
    # #96. A stated margin on estimated intake, in percent. Under-counting
    # intake is the error that stalls a deficit while looking like adherence,
    # so an athlete may choose to carry one - but it belongs HERE, applied to
    # every estimated meal or to none. A buffer added by judgement on some
    # meals and not others corrupts every comparison in the series, and a
    # number the athlete cannot decompose back into estimate and policy is a
    # number they cannot check. None means no buffer, which is the default.
    intake_buffer_pct: float | None = None


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
    res = raw.get("resolution", {})
    prefs = raw.get("preferences", {})
    phases = tuple(
        (float(p[0]), float(p[1]), float(p[2])) for p in targets.get("phases", [])
    )
    precedence = {
        str(k): tuple(str(s) for s in v)
        for k, v in (res.get("precedence") or {}).items()
        if isinstance(v, (list, tuple))
    }
    return Config(
        phases=phases,
        easy_hr_cap=trip.get("easy_hr_cap"),
        rhr_baseline=trip.get("rhr_baseline"),
        steps_floor=trip.get("steps_floor"),
        sleep_floor_h=trip.get("sleep_floor_h"),
        pain_gate=trip.get("pain_gate"),
        source_order=tuple(str(s) for s in res.get("source_order", [])),
        precedence=precedence,
        suppressed_metrics=tuple(str(m) for m in prefs.get("suppressed_metrics", [])),
        nudge_ok=bool(prefs.get("nudge_ok", False)),
        check_tolerance=float(prefs.get("check_tolerance", 0.02)),
        intake_buffer_pct=(None if prefs.get("intake_buffer_pct") is None
                           else float(prefs["intake_buffer_pct"])),
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
