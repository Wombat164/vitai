"""Factual query verbs: never state a number from memory.

These exist because of a specific failure mode. An LLM coach narrates numbers,
and **its narration is as untrustworthy a source as any vendor estimate**. The
model already treats a watch and a calorie app as claims to be adjudicated
(P1); a sentence a language model just produced deserves exactly the same
treatment, and until now it got none.

`check` adjudicates a stated value against the record and answers CONFIRMED,
REFUTED or NOT-IN-RECORD. On its first private run it refuted two claims that
had been asserted narratively minutes earlier, and surfaced the false-merge
bug in issue #14.

The rest - `day`, `window`, `ramp` - are read-only dumps that exist so a
number never has to be recalled. They interpret nothing. Interpretation is the
coach's job, over what these printed (P4).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .provenance import is_modelled

CONFIRMED, REFUTED, NOT_IN_RECORD = "CONFIRMED", "REFUTED", "NOT-IN-RECORD"

# Where a metric can be found. A metric on `sessions` is per-activity and can
# legitimately be scoped by type; one on `daily` is already a daily total.
SESSION_METRICS = {"distance_km", "duration_s", "kcal", "avg_hr", "max_hr",
                   "elevation_m", "cadence", "rpe"}
DAILY_METRICS = {"steps", "distance_km", "active_min", "kcal_out", "kcal_in",
                 "protein_g", "sleep_h", "rhr", "mood", "pain"}

# G27 maturity: how many weeks of data before a week-on-week change is a trend
# rather than an anecdote with a percentage attached.
COLD_WEEKS, WARMING_WEEKS = 2, 4


def _numeric(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _as_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def _week_key(d: str | date) -> str:
    dt = _as_date(d)
    return (dt - timedelta(days=dt.weekday())).isoformat() if dt else ""


def _close(a: float, b: float, tolerance: float) -> bool:
    scale = max(abs(a), abs(b))
    return abs(a - b) <= tolerance * scale if scale else a == b


def collect(datasets: dict[str, list[dict]], on: str, metric: str,
            type: str | None = None) -> list[dict]:
    """Every recorded value of `metric` on `on`, with where it came from."""
    out: list[dict] = []
    if metric in SESSION_METRICS:
        for rec in datasets.get("sessions") or []:
            if str(rec.get("date")) != on or not _numeric(rec.get(metric)):
                continue
            if type and rec.get("type") != type:
                continue
            out.append({"dataset": "sessions", "type": rec.get("type"),
                        "source": rec.get("source"),
                        "modelled": is_modelled(rec, metric),
                        "value": float(rec[metric])})
    if metric in DAILY_METRICS and not type:
        for rec in datasets.get("daily") or []:
            if str(rec.get("date")) == on and _numeric(rec.get(metric)):
                out.append({"dataset": "daily", "type": None,
                            "source": rec.get("source"),
                            # Carried, not filtered (#49). A caller asking
                            # what the record holds should SEE the estimate
                            # and be told it is one; silently dropping it
                            # would answer a different question.
                            "modelled": is_modelled(rec, metric),
                            "value": float(rec[metric])})
    return out


def check(datasets: dict[str, list[dict]], on: str, metric: str, says: float,
          type: str | None = None, tolerance: float = 0.02) -> dict:
    """Adjudicate a stated value against the record.

    Checks the claim against BOTH the day's total and each individual row,
    because "I ran 8k" may mean one 8 km run or two 4 km runs - and the answer
    should say which reading makes it true rather than picking one and being
    confidently wrong about the other.

    NOT-IN-RECORD is deliberately a distinct verdict from REFUTED. Absence
    cannot refute a claim: a day with nothing logged does not prove the run
    did not happen, and saying "REFUTED" there would be the engine
    overreaching in exactly the way it accuses the model of.
    """
    values = collect(datasets, on, metric, type)
    if not values:
        return {"verdict": NOT_IN_RECORD, "date": on, "metric": metric,
                "type": type, "says": says, "values": [], "sum": None,
                "delta": None, "delta_pct": None, "matched": None}

    numbers = [v["value"] for v in values]
    total = sum(numbers)
    matched = None
    if _close(says, total, tolerance):
        matched = "sum" if len(numbers) > 1 else "single"
    else:
        for i, value in enumerate(numbers):
            if _close(says, value, tolerance):
                matched = f"row {i + 1} of {len(numbers)}"
                break

    delta = says - total
    return {
        "verdict": CONFIRMED if matched else REFUTED,
        "date": on, "metric": metric, "type": type, "says": says,
        "values": values, "sum": round(total, 3),
        "delta": round(delta, 3),
        "delta_pct": round(100.0 * delta / total, 1) if total else None,
        "matched": matched,
    }


def day(datasets: dict[str, list[dict]], on: str, claims: list[dict] | None = None,
        gates: list[dict] | None = None) -> dict:
    """Everything the record holds for one date.

    Includes the claims that were MERGED away, because the whole point of a
    factual dump is that it shows what the canonical row is hiding.
    """
    rows = {name: [r for r in recs if str(r.get("date")) == on]
            for name, recs in datasets.items()}
    merged = [c for c in claims or []
              if str(c.get("date")) == on and c.get("merged_into")]
    return {"date": on,
            "datasets": {k: v for k, v in sorted(rows.items()) if v},
            "merged_claims": merged,
            "gates": [g for g in gates or []]}


def window(datasets: dict[str, list[dict]], days: int,
           on: str | date | None = None,
           fallback: date | None = None) -> dict:
    """Totals over the last N CALENDAR days, grouped by session type.

    Calendar days, not logged days: a window that silently skipped the empty
    ones would report a fortnight of training as if it were a week.

    `fallback` is the end date for a record with NO sessions, where there is
    nothing to anchor to. Without it this reached for the wall clock, so a
    caller that had pinned a viewpoint still got today's real week back.
    """
    sessions = datasets.get("sessions") or []
    end = _as_date(on) or max(
        (d for d in (_as_date(r.get("date")) for r in sessions) if d),
        default=fallback or date.today())
    start = end - timedelta(days=days - 1)

    by_type: dict[str, dict] = {}
    for rec in sessions:
        when = _as_date(rec.get("date"))
        if when is None or not start <= when <= end:
            continue
        slot = by_type.setdefault(str(rec.get("type")),
                                  {"sessions": 0, "distance_km": 0.0,
                                   "duration_s": 0.0, "kcal": 0.0})
        slot["sessions"] += 1
        for field in ("distance_km", "duration_s", "kcal"):
            if _numeric(rec.get(field)):
                slot[field] += float(rec[field])

    logged = {str(r.get("date")) for r in datasets.get("daily") or []
              if (d := _as_date(r.get("date"))) and start <= d <= end}
    return {"from": start.isoformat(), "to": end.isoformat(), "days": days,
            "days_logged": len(logged),
            "by_type": {k: {m: round(v, 3) if isinstance(v, float) else v
                            for m, v in sorted(slot.items())}
                        for k, slot in sorted(by_type.items())}}


def ramp(datasets: dict[str, list[dict]], type: str = "run",
         metric: str = "distance_km") -> dict:
    """Week-on-week volume, WITH the base-size caveat attached.

    A ramp percentage over a one-week base is not a trend, and printing it
    without saying so is how a misleading number gets quoted. The maturity
    signal is engine-owned (G27) precisely so no caller has to remember to add
    the caveat themselves.
    """
    weeks: dict[str, float] = {}
    for rec in datasets.get("sessions") or []:
        if rec.get("type") != type or not _numeric(rec.get(metric)):
            continue
        if wk := _week_key(rec.get("date")):
            weeks[wk] = weeks.get(wk, 0.0) + float(rec[metric])

    ordered = [{"week": wk, "value": round(weeks[wk], 3)} for wk in sorted(weeks)]
    for prev, cur in zip(ordered, ordered[1:]):
        cur["change_pct"] = (round(100.0 * (cur["value"] - prev["value"])
                                   / prev["value"], 1) if prev["value"] else None)

    n = len(ordered)
    maturity = ("cold" if n < COLD_WEEKS else
                "warming" if n < WARMING_WEEKS else "stable")
    caveat = {
        "cold": (f"weeks with data: {n} - a ramp % over a {n}-week base is not "
                 "a trend, say so"),
        "warming": (f"weeks with data: {n} - early, treat a single week's "
                    "change as noise"),
        "stable": f"weeks with data: {n}",
    }[maturity]
    return {"type": type, "metric": metric, "weeks": ordered,
            "maturity": maturity, "caveat": caveat}
