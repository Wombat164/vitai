"""Weekly goal-attainment verdicts: the machine-readable contract.

One row per (ISO week, metric): value, target, verdict. This is what a game
economy, dashboard, or coaching skill consumes - deterministic, rebuilt on
every build, projected into the `verdicts` table of the read model.

Verdict vocabulary (closed): on_target | ahead | behind | no_data.
"ahead"/"behind" are metric-relative (for weight rate, faster than the
phase target counts as "ahead" only in the arithmetic sense - the coaching
layer decides whether ahead is good; the engine does not moralise).

Each week is judged against the thresholds IN FORCE ON ITS MONDAY (G14/G20).
Two consequences worth stating plainly: lowering the steps floor today cannot
turn last March's misses into hits on the next rebuild, and a threshold edited
mid-week does not re-score the days already lived under the old number.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from .config import Config, overlay, phase_rate_for
from .policy import state
from .schema import EXTERNAL_METRIC

ON, AHEAD, BEHIND, NODATA = "on_target", "ahead", "behind", "no_data"


def _week_key(d: str) -> str:
    dt = datetime.fromisoformat(d).date()
    return (dt - timedelta(days=dt.weekday())).isoformat()


def _weeks_covered(*datasets: list[dict]) -> list[str]:
    weeks = {_week_key(r["date"]) for ds in datasets for r in ds if r.get("date")}
    return sorted(weeks)


def _row(week: str, metric: str, value: float | None, target: float | None,
         verdict: str, goal: str | None = None) -> dict:
    return {"week": week, "metric": metric,
            "value": round(value, 3) if value is not None else None,
            "target": target, "verdict": verdict, "goal": goal}


def _goal_for(goals_in_force: tuple[dict, ...], metric: str) -> str | None:
    """The active goal this metric serves, if any - the verdict's goal linkage.

    First match by declaration order wins. Two active goals on one metric is a
    modelling smell the coach should raise, not something the engine resolves.
    """
    for g in goals_in_force:
        if g.get("metric") == metric and g.get("metric") != EXTERNAL_METRIC:
            return g.get("slug")
    return None


def compute_verdicts(cfg: Config, weight: list[dict], daily: list[dict],
                     sessions: list[dict], today: date | None = None,
                     goals: list[dict] | None = None,
                     thresholds: list[dict] | None = None) -> list[dict]:
    """Deterministic weekly verdict rows across all configured metrics."""
    rows: list[dict] = []
    weeks = _weeks_covered(weight, daily, sessions)
    if not weeks:
        return rows

    # Policy as of each week's Monday: thresholds overlaid on vitai.toml, and
    # the goals that were active then (for the `goal` linkage column).
    as_of = {wk: state(goals or [], thresholds or [], wk) for wk in weeks}
    cfg_for = {wk: overlay(cfg, as_of[wk].thresholds) for wk in weeks}
    goals_for = {wk: as_of[wk].active_goals() for wk in weeks}

    # --- weight rate: mean(kg) this week vs previous week, vs phase target ---
    by_week_kg: dict[str, list[float]] = defaultdict(list)
    for w in weight:
        if w.get("kg") is not None:
            by_week_kg[_week_key(w["date"])].append(w["kg"])
    for wk in weeks:
        vals = by_week_kg.get(wk)
        prev_wk = (datetime.fromisoformat(wk).date() - timedelta(days=7)).isoformat()
        prev = by_week_kg.get(prev_wk)
        if not vals or not prev:
            if vals or prev:
                rows.append(_row(wk, "weight_rate", None, None, NODATA))
            continue
        rate = mean(prev) - mean(vals)  # positive = losing
        target = phase_rate_for(cfg_for[wk], mean(vals))
        goal = _goal_for(goals_for[wk], "weight_rate")
        if target is None:
            rows.append(_row(wk, "weight_rate", rate, None, NODATA, goal))
            continue
        if abs(rate - target) <= 0.25:
            verdict = ON
        else:
            verdict = AHEAD if rate > target else BEHIND
        rows.append(_row(wk, "weight_rate", rate, target, verdict, goal))

    # --- easy-run HR discipline: weekly avg of run avg_hr vs cap ------------
    by_week_hr: dict[str, list[int]] = defaultdict(list)
    for s in sessions:
        if s.get("type") == "run" and s.get("avg_hr"):
            by_week_hr[_week_key(s["date"])].append(s["avg_hr"])
    for wk in weeks:
        cap = cfg_for[wk].easy_hr_cap
        hrs = by_week_hr.get(wk)
        if cap is None or not hrs:
            continue
        avg = mean(hrs)
        rows.append(_row(wk, "easy_hr", avg, float(cap),
                         ON if avg <= cap else BEHIND,
                         _goal_for(goals_for[wk], "easy_hr")))

    # --- daily floors/gates, weekly aggregated ------------------------------
    daily_by_week: dict[str, list[dict]] = defaultdict(list)
    for d in daily:
        daily_by_week[_week_key(d["date"])].append(d)

    for wk in weeks:
        days = daily_by_week.get(wk, [])
        if not days:
            continue
        eff = cfg_for[wk]
        active = goals_for[wk]
        if eff.steps_floor is not None:
            steps = [d["steps"] for d in days if d.get("steps") is not None]
            if steps:
                avg = mean(steps)
                rows.append(_row(wk, "steps", avg, float(eff.steps_floor),
                                 ON if avg >= eff.steps_floor else BEHIND,
                                 _goal_for(active, "steps")))
        if eff.sleep_floor_h is not None:
            sleeps = [d["sleep_h"] for d in days if d.get("sleep_h") is not None]
            if sleeps:
                avg = mean(sleeps)
                rows.append(_row(wk, "sleep", avg, eff.sleep_floor_h,
                                 ON if avg >= eff.sleep_floor_h else BEHIND,
                                 _goal_for(active, "sleep_h")))
        if eff.pain_gate is not None:
            pains = [d["hip_pain"] for d in days if d.get("hip_pain") is not None]
            if pains:
                worst = max(pains)
                rows.append(_row(wk, "pain_gate", float(worst), float(eff.pain_gate),
                                 ON if worst <= eff.pain_gate else BEHIND,
                                 _goal_for(active, "hip_pain")))
        if eff.rhr_baseline is not None:
            rhrs = [d["rhr"] for d in days if d.get("rhr") is not None]
            if rhrs:
                avg = mean(rhrs)
                rows.append(_row(wk, "rhr", avg, float(eff.rhr_baseline + 5),
                                 ON if avg <= eff.rhr_baseline + 5 else BEHIND,
                                 _goal_for(active, "rhr")))

    return rows
