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
from .vocab import session_classes


def _rolling(points: list[tuple[str, float]], window: int = 7) -> list[tuple[str, float | None]]:
    """Trailing mean over a CALENDAR-DAY window (G30/G27): each point averages
    values dated within the last `window` days, NOT the last `window` list
    entries. With irregular logging a "7d avg" must mean 7 real days, not 7
    weigh-ins that might span three weeks - otherwise every "the trend, not a
    single point" number is silently mis-scoped."""
    out = []
    dated = [(datetime.fromisoformat(d).date(), v) for d, v in points]
    for d_iso, _ in points:
        d = datetime.fromisoformat(d_iso).date()
        lo = d - timedelta(days=window - 1)
        vals = [v for dd, v in dated if lo <= dd <= d and v is not None]
        out.append((d_iso, mean(vals) if vals else None))
    return out


def _avg_on_or_before(roll: dict[str, float | None], iso: str, target_day: date) -> float | None:
    """The rolling average as of the latest point on/before target_day - so the
    rate compares two calendar-separated windows, not two Nth-from-last entries."""
    best = None
    for d_iso, v in roll.items():
        d = datetime.fromisoformat(d_iso).date()
        if d <= target_day and v is not None:
            if best is None or d > best[0]:
                best = (d, v)
    return best[1] if best else None


def _week_key(d: str) -> str:
    dt = datetime.fromisoformat(d).date()
    return (dt - timedelta(days=dt.weekday())).isoformat()


def build_report(cfg: Config, weight: list[dict], daily: list[dict],
                 sessions: list[dict], today: date | None = None,
                 gates: list[dict] | None = None,
                 escalations: list[dict] | None = None) -> str:
    today = today or date.today()
    gates = gates or []
    escalations = escalations or []
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
        # Rate over a CALENDAR week (G30): compare the rolling avg now against
        # the rolling avg ~7 days ago, not the 8th-from-last entry (which under
        # irregular logging could be a month back).
        last_day = datetime.fromisoformat(pts[-1][0]).date()
        week_ago = last_day - timedelta(days=7)
        v1 = roll[pts[-1][0]]
        v0 = _avg_on_or_before(roll, pts[-1][0], week_ago)
        if v0 is not None and v1 is not None:
            # actual calendar days between the two anchor points (>=1)
            anchor0 = max((datetime.fromisoformat(d).date()
                           for d, v in roll.items()
                           if datetime.fromisoformat(d).date() <= week_ago and v is not None),
                          default=None)
            days = (last_day - anchor0).days if anchor0 else 0
            if days:
                rate = (v0 - v1) / days * 7
                target = phase_rate_for(cfg, v1)
                # G69: never render a bare signed quantity whose plain reading
                # inverts its meaning. This line showed `+1.10 kg/week` to an
                # athlete who had LOST 1.5 kg, because positive means losing
                # here. For a scale-anxious under-eater that misreading is
                # actively dangerous, so the direction is stated in words and
                # the sign is a detail rather than the message.
                direction = ("losing" if rate > 0 else
                             "gaining" if rate < 0 else "holding")
                magnitude = f"{abs(rate):.2f} kg/week"
                phrase = (f"{direction} {magnitude}" if rate
                          else "holding steady")
                if target is not None:
                    verdict = ("ON TARGET" if abs(rate - target) <= 0.25
                               else "FAST - raise intake" if rate > target
                               else "SLOW - check logging")
                    L += ["", f"**Rate:** {phrase} (target: losing "
                              f"{target:.2f} kg/week) - **{verdict}**",
                          "", "> Judge on this line, never a single morning."]
                else:
                    L += ["", f"**Rate:** {phrase} (no phase targets configured)"]
    else:
        L.append("_No weight data - and that is a valid way to use this._")

    # G64: an athlete whose only real data is a phone step count had fourteen
    # days of it render precisely nowhere. What someone actually logs is what
    # the rollup should be about.
    step_days = [(d["date"], d["steps"]) for d in daily
                 if d.get("steps") is not None]
    if step_days:
        recent = step_days[-14:]
        avg = mean(s for _, s in recent)
        best = max(recent, key=lambda p: p[1])
        L += ["", "## Steps", "",
              f"- {avg:,.0f}/day average over the last {len(recent)} logged days",
              f"- best day {best[1]:,} on {best[0]}",
              f"- {len(step_days)} days logged in total"]

    L += ["", "## Training by week", ""]
    by_week: dict[str, dict] = defaultdict(lambda: {"km": 0.0, "runs": 0, "gym": 0, "hr": []})
    for s in sessions:
        w = by_week[_week_key(s["date"])]
        if s.get("type") in ("run", "test"):
            w["km"] += s.get("distance_km") or 0
            w["runs"] += 1
            if s.get("type") == "run" and s.get("avg_hr"):
                w["hr"].append(s["avg_hr"])
        elif "strength" in session_classes(s.get("type")):
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
        # Reads `pain` after the gen-2 generalization, falling back to the
        # retired `hip_pain` so an older record still trips its own gate.
        scored = [(d.get("pain") if d.get("pain") is not None else d.get("hip_pain"),
                   d.get("pain_site") or "hip")
                  for d in daily
                  if d.get("pain") is not None or d.get("hip_pain") is not None][-7:]
        if scored and max(p for p, _ in scored) > cfg.pain_gate:
            worst, site = max(scored, key=lambda s: s[0])
            alerts.append(f"**Pain {worst}/10 at {site}** - gate fired: "
                          "no loaded work at that site")
    if cfg.sleep_floor_h is not None:
        sleeps = [d["sleep_h"] for d in daily if d.get("sleep_h")][-7:]
        if sleeps and mean(sleeps) < cfg.sleep_floor_h:
            alerts.append(f"**Sleep {mean(sleeps):.1f}h avg** - under the "
                          f"{cfg.sleep_floor_h:.0f}h floor")
    if cfg.steps_floor is not None:
        steps = [d["steps"] for d in daily if d.get("steps")][-7:]
        if steps:
            avg = mean(steps)
            met = avg >= cfg.steps_floor
            verdict = "floor met" if met else f"below the {cfg.steps_floor:,} floor"
            alerts.append(f"Steps {avg:,.0f}/day avg - {verdict}")
    L += [f"- {a}" for a in alerts] or ["- Nothing firing."]

    # Gates outrank tripwires and sit above them in the reader's eye for a
    # reason: a tripwire is something to discuss, a gate is something that is
    # already decided. The coach may explain one; it may not talk one away.
    L += ["", "## Gates", ""]
    if gates:
        for g in gates:
            L.append(f"- **{g['restricts']} blocked** - {g['reason']}")
        L += ["", "> A gate clears when the record says the episode resolved, "
                  "not by argument."]
    else:
        L.append("- Nothing gated.")

    if escalations:
        L += ["", "## Safety", ""]
        for e in escalations:
            L.append(f"- **{e['level'].upper()}** {e['date']} - {e['detail']}")
        L += ["", "> " + escalations[0]["action"]]

    L += ["", "## Coverage", "",
          f"- weight: {len(weight)} - daily: {len(daily)} - sessions: {len(sessions)}",
          "", "> Sparse and continuous beats rich and abandoned."]
    return "\n".join(L) + "\n"
