"""Load the athlete's thresholds from the content repo's vitai.toml.

Everything is optional: an absent threshold disables the corresponding
verdict/tripwire rather than failing the build. The engine is the same for
everyone; the numbers are the athlete's.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field, fields, replace
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
    # How many weeks of the training table the rollup prints. A weekly
    # document is read weekly, and the full series reached 267 rows on
    # the record #76 was measured against. 0 means all of them.
    rollup_weeks: int = 12
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
    # #105. This machine's slug, and the ONLY thing that decides which file
    # this instance appends to. Set it per device and no two devices ever
    # write the same file, which is what makes a merge a set union rather
    # than a conflict to resolve. None keeps the single-file record every
    # existing athlete already has.
    device: str | None = None


def load_inference_config(root: Path) -> dict:
    """The raw [inference] table from vitai.toml (empty dict if absent).
    Kept separate from Config: inference is the opt-in intelligence layer,
    not an engine threshold."""
    path = root / "vitai.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8")).get("inference", {})


def _typed(key: str, value):
    """A threshold cast to its declared type, or left alone if it will not go.

    Left alone rather than dropped: a garbage value should reach the athlete
    as the wrong number they typed, not disappear into a default that looks
    deliberate.
    """
    if value is None:
        return None
    try:
        return THRESHOLD_TYPES[key](value)
    except (KeyError, TypeError, ValueError):
        return value


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
    # CAST to the declared type, the same way `overlay` casts a dated row.
    # These five arrived uncast while every other number here went through
    # `float()`, so `steps_floor = 8000` and `steps_floor = 8000.0` built two
    # Configs that judge identically and hash differently - a formatter
    # normalising the toml marked every later reconstruction incomparable
    # with every earlier one, which is noise in the one signal
    # `policy_digest` exists to carry.
    return Config(
        phases=phases,
        easy_hr_cap=_typed("easy_hr_cap", trip.get("easy_hr_cap")),
        rhr_baseline=_typed("rhr_baseline", trip.get("rhr_baseline")),
        steps_floor=_typed("steps_floor", trip.get("steps_floor")),
        sleep_floor_h=_typed("sleep_floor_h", trip.get("sleep_floor_h")),
        pain_gate=_typed("pain_gate", trip.get("pain_gate")),
        source_order=tuple(str(s) for s in res.get("source_order", [])),
        precedence=precedence,
        suppressed_metrics=tuple(str(m) for m in prefs.get("suppressed_metrics", [])),
        nudge_ok=bool(prefs.get("nudge_ok", False)),
        rollup_weeks=int(prefs.get("rollup_weeks", 12)),
        check_tolerance=float(prefs.get("check_tolerance", 0.02)),
        intake_buffer_pct=(None if prefs.get("intake_buffer_pct") is None
                           else float(prefs["intake_buffer_pct"])),
        device=(str(raw["device"]["slug"])
                if isinstance(raw.get("device"), dict)
                and raw["device"].get("slug") else None),
    )


# NOT policy: the machine writing the file. The test is whether the field is
# a property of the RECORD or of the reader - readers union every device's
# file, so two machines over one record must digest the same or every
# cross-device comparison reports a policy change that never happened.
#
# Not "does the engine read it": `nudge_ok` has no consumer in the engine at
# all (only skill prose honours it), and it stays IN the digest anyway.
# Include-by-default is the safe direction - a field wrongly included says
# "incomparable" about two things that were comparable, and a field wrongly
# excluded says "comparable" about two things that were not. Only the second
# is the failure this row exists to prevent.
NOT_POLICY = ("device",)


def policy_digest(cfg: Config) -> str:
    """A content hash over the policy that is NOT in the record (#148).

    `as_of` reconstructs the record at an instant by filtering `recorded_at`.
    That is right for everything the record holds and wrong for everything it
    does not, and threshold baselines are in the second category: they live in
    `vitai.toml`, a mutable file with no history, and `thresholds.jsonl` only
    overlays the five keys in `THRESHOLD_TYPES`. Every other field here -
    phases, the resolution ladder, suppressed metrics, the check tolerance,
    the intake buffer - has no dated history at all.

    So editing a rate threshold in September silently re-judges every
    historical week that carried no dated row. A reconstruction of March does
    not return what the engine would have said in March; it returns March's
    data under September's policy.

    This does not fix that. It makes it DETECTABLE: a reconstruction that
    records this digest can be compared against one taken under a different
    policy and known to be incomparable, rather than quietly differing. Build
    systems put the environment in an action's identity for the same reason -
    an untracked input silently poisons every claim downstream of it.

    Stable across runs and machines: canonical JSON, sorted keys, and no
    reliance on dict or dataclass ordering.
    """
    payload = {f.name: _canonical(getattr(cfg, f.name))
               for f in fields(cfg) if f.name not in NOT_POLICY}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()


def _canonical(value):
    """Tuples to lists and dict values likewise, so JSON round-trips.

    `asdict` would do this too, but it deep-copies and it would silently
    include a field added to `Config` later without anyone deciding whether
    it is policy - the loop above is explicit about that.
    """
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    return value


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

    PARTIAL, and the gap is #148. This covers a key only for a week that
    carries a dated row for it; a week without one still falls through to
    whatever the toml says today. And it covers only the five keys in
    `THRESHOLD_TYPES` - the rest of `Config` has no dated history to overlay
    at all. `policy_digest` makes the difference detectable until the toml
    gets the append-only history the data already has.
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
