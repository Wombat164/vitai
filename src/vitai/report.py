"""The weekly rollup: weight trend + rate verdict, training by week, tripwires.

Every threshold comes from vitai.toml (see config.py); an absent threshold
silently disables its section rather than guessing a default. The rollup is
the interface between the engine and the intelligence layer: the LLM judges
on these lines and never recomputes them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from .config import Config, phase_rate_for


def _rolling(points: list[tuple[str, float]], window: int = 7) -> list[tuple[str, float | None]]:
    out = []
    for i, (d, _) in enumerate(points):
        vals = [v for _, v in points[max(0, i - window + 1):i + 1] if v is not None]
        out.append((d, mean(vals) if vals else None))
    return out


def _week_key(d: str) -> str:
    dt = datetime.fromisoformat(d).date()
    return (dt - timedelta(days=dt.weekday())).isoformat()


def build_report(cfg: Config, weight: list[dict], daily: list[dict],
                 sessions: list[dict], today: date | None = None) -> str:
    today = today or date.today()
    L = ["# Weekly rollup", "",
         f"Generated {today.isoformat()} - derived, do not edit.",
         "", "## Weight", ""]

    if weight:
        pts = sorted((w["date"], w["kg"]) for w in weight if w.get("kg") is not None)
        roll = dict(_rolling(pts))
        L += ["| Date | kg | 7d avg |", "|---|---|---|"]
        for d, kg in pts[-14:]:
            r = roll.get(d)
            L.append(f"| {d} | {kg:.1f} | {r:.1f} |" if r else f"| {d} | {kg:.1f} | - |")
        if len(pts) >= 8:
            (d0, _), (d1, _) = pts[-8], pts[-1]
            v0, v1 = roll[d0], roll[d1]
            days = (datetime.fromisoformat(d1) - datetime.fromisoformat(d0)).days
            if v0 and v1 and days:
                rate = (v0 - v1) / days * 7
                target = phase_rate_for(cfg, v1)
                if target is not None:
                    verdict = ("ON TARGET" if abs(rate - target) <= 0.25
                               else "FAST - raise intake" if rate > target
                               else "SLOW - check logging")
                    L += ["", f"**Rate:** {rate:+.2f} kg/week vs target {target:.2f} - "
                              f"**{verdict}**",
                          "", "> Judge on this line, never a single morning."]
                else:
                    L += ["", f"**Rate:** {rate:+.2f} kg/week (no phase targets configured)"]
    else:
        L.append("_No weight data._")

    L += ["", "## Training by week", ""]
    by_week: dict[str, dict] = defaultdict(lambda: {"km": 0.0, "runs": 0, "gym": 0, "hr": []})
    for s in sessions:
        w = by_week[_week_key(s["date"])]
        if s.get("type") in ("run", "test"):
            w["km"] += s.get("distance_km") or 0
            w["runs"] += 1
            if s.get("type") == "run" and s.get("avg_hr"):
                w["hr"].append(s["avg_hr"])
        elif str(s.get("type", "")).startswith("gym"):
            w["gym"] += 1
    if by_week:
        L += ["| Week of | km | Runs | Gym | Avg HR | Easy-cap? |", "|---|---|---|---|---|---|"]
        for wk in sorted(by_week):
            v = by_week[wk]
            hr = round(mean(v["hr"])) if v["hr"] else None
            if hr is None or cfg.easy_hr_cap is None:
                flag = "-"
            else:
                flag = "OK" if hr <= cfg.easy_hr_cap else f"OVER +{hr - cfg.easy_hr_cap}"
            L.append(f"| {wk} | {v['km']:.1f} | {v['runs']} | {v['gym']} | "
                     f"{hr or '-'} | {flag} |")
    else:
        L.append("_No sessions._")

    L += ["", "## Tripwires", ""]
    alerts: list[str] = []
    if cfg.rhr_baseline is not None:
        rhrs = [(d["date"], d["rhr"]) for d in daily if d.get("rhr")]
        if len(rhrs) >= 3:
            recent = mean(v for _, v in rhrs[-7:])
            if recent > cfg.rhr_baseline + 5:
                alerts.append(f"**Resting HR {recent:.0f}** - more than 5 over "
                              f"baseline {cfg.rhr_baseline}")
    if cfg.pain_gate is not None:
        pains = [d["hip_pain"] for d in daily if d.get("hip_pain") is not None][-7:]
        if pains and max(pains) > cfg.pain_gate:
            alerts.append(f"**Hip pain {max(pains)}/10** - gate fired: no loaded hip work")
    if cfg.sleep_floor_h is not None:
        sleeps = [d["sleep_h"] for d in daily if d.get("sleep_h")][-7:]
        if sleeps and mean(sleeps) < cfg.sleep_floor_h:
            alerts.append(f"**Sleep {mean(sleeps):.1f}h avg** - under the "
                          f"{cfg.sleep_floor_h:.0f}h floor")
    if cfg.steps_floor is not None:
        steps = [d["steps"] for d in daily if d.get("steps")][-7:]
        if steps:
            avg = mean(steps)
            alerts.append(f"Steps {avg:,.0f}/day avg - "
                          f"{'floor met' if avg >= cfg.steps_floor else f'below the {cfg.steps_floor:,} floor'}")
    L += [f"- {a}" for a in alerts] or ["- Nothing firing."]

    L += ["", "## Coverage", "",
          f"- weight: {len(weight)} - daily: {len(daily)} - sessions: {len(sessions)}",
          "", "> Sparse and continuous beats rich and abandoned."]
    return "\n".join(L) + "\n"
