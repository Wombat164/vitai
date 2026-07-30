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

from .clocks import weigh_in_timing
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
                     thresholds: list[dict] | None = None,
                     medical: list[dict] | None = None) -> list[dict]:
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
    by_week_rows: dict[str, list[dict]] = defaultdict(list)
    for w in weight:
        if w.get("kg") is not None:
            by_week_kg[_week_key(w["date"])].append(w["kg"])
            by_week_rows[_week_key(w["date"])].append(w)
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
        # #37: a rate whose weigh-in times are spread widely enough to
        # account for it is not a rate, and this is the machine-readable
        # contract - a consumer reading AHEAD or BEHIND here will render it as
        # fact. Reporting the number with NODATA says "here is what the scale
        # did, and no, we cannot judge it", which is the honest pair. The same
        # shape as `_drops_rate_verdict` for a medical contraindication: the
        # engine already knows how to decline to score something.
        timing = weigh_in_timing(by_week_rows.get(wk, [])
                                 + by_week_rows.get(prev_wk, []))
        if timing["known"] and not timing["unknown"] and (
                timing["drift_kg"] >= abs(rate)):
            rows.append(_row(wk, "weight_rate", rate, target, NODATA, goal))
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
            # `pain` after the gen-2 generalization; old lines arrive here
            # already mapped from `hip_pain` by resolution.canonical_daily.
            pains = [d.get("pain") if d.get("pain") is not None else d.get("hip_pain")
                     for d in days
                     if d.get("pain") is not None or d.get("hip_pain") is not None]
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

    # Safety floors that need no configuration (G68). Every rule above is
    # opt-in: it produces nothing until the athlete sets a threshold. That is
    # right for coaching preferences and wrong for danger, and it meant an
    # athlete who had configured nothing - the state every new user is in -
    # got `tripwires: none` while eating 1200 kcal a day and losing a kilo a
    # week. These rows fire from defaults, like the absolute RHR band.
    rows += _default_floor_rows(weight, daily, sessions, medical or [])

    # G72: when a declared medication makes rapid loss the EXPECTED outcome,
    # the rate verdict is meaningless and actively harmful - it tells someone
    # for whom the treatment is working that she is failing a target nobody
    # set for her. Drop the row rather than dress it up; the nutrition floors
    # and the lean-mass composite carry the real risk on this pathway.
    if _drops_rate_verdict(medical or [], weeks):
        rows = [r for r in rows if r["metric"] != "weight_rate"]

    # G33, last: a suppressed metric is still RECORDED, just not scored. The
    # data keeps accumulating for the day the athlete wants it back; what
    # stops is the judging.
    if cfg.suppressed_metrics:
        rows = [r for r in rows if r["metric"] not in cfg.suppressed_metrics]
    rows.sort(key=lambda r: (r["week"], r["metric"]))
    return rows


def _drops_rate_verdict(medical: list[dict], weeks: list[str]) -> bool:
    """Is rapid loss the declared, expected outcome of a treatment?

    Deliberately narrow: only a medication or state line that SAYS so does
    this, and it removes one verdict rather than quietening the safety layer.
    Every absolute floor still fires.
    """
    from .safety import _expectations, _as_date

    if not weeks:
        return False
    last = _as_date(weeks[-1])
    return last is not None and "rapid_loss" in _expectations(medical, last)


def _default_floor_rows(weight: list[dict], daily: list[dict],
                        sessions: list[dict], medical: list[dict]) -> list[dict]:
    """Verdict rows for the absolute nutrition floors and energy availability.

    These live in `verdicts` as well as in the escalation surface because a
    verdict is what a dashboard, a game and the weekly rollup already read. A
    safety finding that only exists in a channel nobody renders is a safety
    finding nobody sees.
    """
    from .safety import (
        EA_LOW_THRESHOLD, INTAKE_FLOOR_KCAL, PROTEIN_FLOOR_G_PER_KG,
        RED_S_WINDOW_DAYS, _expectations, _latest_weight, _window,
        energy_availability,
    )

    window, _, end = _window(daily, RED_S_WINDOW_DAYS)
    if not window:
        return []
    wk = _week_key(end.isoformat())
    out: list[dict] = []

    floor = INTAKE_FLOOR_KCAL
    if "elevated_requirement" in _expectations(medical, end):
        floor += 500.0
    intakes = [float(r["kcal_in"]) for r in window if r.get("kcal_in") is not None]
    if len(intakes) >= 7:
        mean_intake = sum(intakes) / len(intakes)
        out.append(_row(wk, "intake_floor", mean_intake, floor,
                        BEHIND if mean_intake <= floor else ON))

    kg = _latest_weight(weight, end)
    proteins = [float(r["protein_g"]) for r in window
                if r.get("protein_g") is not None]
    if kg and len(proteins) >= 7:
        per_kg = (sum(proteins) / len(proteins)) / kg
        out.append(_row(wk, "protein_floor", per_kg, PROTEIN_FLOOR_G_PER_KG,
                        BEHIND if per_kg < PROTEIN_FLOOR_G_PER_KG else ON))

    ea, _terms = energy_availability(daily, weight, sessions)
    if ea is not None:
        out.append(_row(wk, "energy_availability", ea, EA_LOW_THRESHOLD,
                        BEHIND if ea < EA_LOW_THRESHOLD else ON))
    out += _symptom_rows(weight, daily, sessions, medical)
    return out


# Red-flag symptom classes, and the verdict metric each is counted under. A
# recurrent symptom is the most important thing about an athlete's week, so it
# belongs in the row set a dashboard already renders - not only in an
# escalation channel a consumer has to know to ask for.
SYMPTOM_METRICS = {"cardiac": "symptom_chest_pain", "syncope": "symptom_syncope"}


def _symptom_rows(weight: list[dict], daily: list[dict], sessions: list[dict],
                  medical: list[dict]) -> list[dict]:
    """One row per (week, symptom class): how many were reported, against zero."""
    from .safety import escalations

    counts: dict[tuple[str, str], int] = {}
    for row in escalations(medical, daily, weight, sessions,
                           include_red_s=False):
        metric = SYMPTOM_METRICS.get(str(row.get("trigger")))
        if metric and row.get("date"):
            key = (_week_key(str(row["date"])), metric)
            counts[key] = counts.get(key, 0) + 1
    return [_row(wk, metric, float(n), 0.0, BEHIND)
            for (wk, metric), n in sorted(counts.items())]
