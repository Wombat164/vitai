"""Deterministic severity-to-action. The one loud exception to never-shame.

G28, and the highest-stakes thing in the model. Everything else vitai computes
is a coaching input; this decides whether to tell someone to stop and see a
clinician. Until now that decision lived as prose in a skill file, which means
a coach optimising for adherence could reason around it, soften it, or simply
not reach it. Prose can be argued with. A branch cannot.

So the rules here are code, the messages here are constants, and no part of
either is generated. An LLM may EXPLAIN an escalation and must never author,
soften, defer, or re-derive one.

## The asymmetry that makes this safe

The engine has its own triggers that do not depend on anything a model judged:
a body site that is never musculoskeletal, thresholds outside physiological
range, and a composite over numbers the athlete already logs. It ALSO honours
an explicit `severity: red_flag` written by a skill.

That combination is deliberate and one-directional: a model can only ever ADD
an escalation, never remove one. If the coach fails to recognise something,
the engine still fires. If the coach over-calls it, the worst case is an
unnecessary "get this looked at", which is the cheap direction of the trade.

## What this is not

It is not diagnosis, and it never names a condition. Every escalation routes
to a human clinician. The thresholds below are deliberately conservative
SCREENING bounds - wide enough that a trained endurance athlete's genuinely
low resting heart rate does not trip them, narrow enough to catch a number
that should not occur in a person who is fine. Over-triage is the accepted
cost; under-triage is not.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .schema import IDENTITY_KEY, _restriction_classes

# --- escalation levels --------------------------------------------------------
# EMERGENCY: same day, do not wait for the weekly review.
# URGENT: contact a clinician; stop the gated activity now.
# ADVISORY: worth raising at the next check-in.
EMERGENCY, URGENT, ADVISORY = "emergency", "urgent", "advisory"
LEVEL_ORDER = {EMERGENCY: 0, URGENT: 1, ADVISORY: 2}

# --- hardcoded messages -------------------------------------------------------
# These strings are the product. They are constants so that what the athlete
# reads in a genuine emergency is exactly what was reviewed and tested, not
# something assembled at runtime by a model optimising for tone.
MESSAGES: dict[str, str] = {
    "cardiac": (
        "STOP exercising now. Chest pain, pressure or tightness is not a "
        "training problem and must not be worked around. If it is severe, "
        "spreading to the arm, neck or jaw, or comes with breathlessness, "
        "sweating, nausea or fainting, call emergency services. Otherwise "
        "contact a doctor today. Do not train again until a clinician has "
        "cleared you."),
    "rhr_absolute": (
        "STOP training and contact a doctor today. Your recorded resting "
        "heart rate is outside the range seen in healthy people at rest, "
        "including trained athletes. This may be a measurement error - check "
        "the device - but it must be ruled out rather than assumed."),
    "severe_pain": (
        "Stop the activity that provokes this and contact a clinician. Pain "
        "at this level is not something to train through, and no plan here "
        "will suggest working around it."),
    "red_s": (
        "Contact a doctor or a sports dietitian. Your logged intake, rate of "
        "loss and training load together match a low-energy-availability "
        "pattern (RED-S), which carries real risk to bone, hormonal and "
        "cardiac health. This is the syndrome that a deficit plus hard "
        "training can cause, so treat it as a reason to eat more and train "
        "less until someone qualified has looked at it - not as a target met."),
    "red_flag_declared": (
        "This was recorded as a red flag. Stop the affected activity and "
        "contact a clinician. Nothing in this record substitutes for that."),
    "gate": (
        "This activity is gated by an active entry in your record. The gate "
        "clears when the episode is resolved in the data, not by explaining "
        "it away."),
}

# --- engine-owned triggers ----------------------------------------------------

# Body sites where pain is never assumed musculoskeletal. `chest` is a valid
# musculoskeletal site in the body-site registry (sternum, ribs, costochondral
# pain are all real), and that is exactly the trap: a coach handed "chest pain"
# alongside a hip and a knee will happily suggest a substitution. It does not
# get to. Chest pain routes to a clinician first, every time, and the athlete
# can tell the doctor it was the rib.
RED_FLAG_SITES: dict[str, str] = {"chest": "cardiac"}

# Resting heart rate outside this band is not "drifted from baseline" - it is
# outside the range of a healthy person at rest. The floor sits below the
# genuinely low resting rates of trained endurance athletes (mid-30s is normal
# for them and must not fire); the ceiling sits well above anxiety, caffeine,
# illness or a bad reading. Both are screening bounds, not diagnosis.
RHR_ABSOLUTE_MIN = 30
RHR_ABSOLUTE_MAX = 120

# 0-10 self-reported pain at or above this is not trainable through.
PAIN_ABSOLUTE = 9

# --- RED-S / low energy availability -----------------------------------------
# The syndrome a tool that coaches deficits can itself cause, which is why it
# is the engine's job to watch for it rather than the athlete's. Screened as a
# composite because no single one of these is alarming on its own: a deep
# deficit is a choice, fast loss is sometimes water, and high load is training.
# Together, sustained, they are the pattern.
RED_S_WINDOW_DAYS = 14
RED_S_DEFICIT_KCAL = -1000.0      # mean daily energy balance over the window
RED_S_LOSS_PCT_PER_WEEK = 1.0     # % of bodyweight per week
RED_S_LOAD_MIN_PER_WEEK = 180.0   # minutes of logged sessions per week
RED_S_MIN_DAYS = 10               # do not screen on a nearly-empty window


def _as_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def _numeric(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# --- episodes -----------------------------------------------------------------

def episodes_on(medical: list[dict], on: str | date) -> list[dict]:
    """The state of every medical episode as it stood on `on`.

    One line per slug: the latest one dated on or before `on`. A line dated
    after `on` is invisible, so last Tuesday is judged by what was known last
    Tuesday (P2) - a resolution recorded today does not retroactively un-gate
    the week the athlete was actually injured.
    """
    when = _as_date(on)
    if when is None:
        return []
    ident = IDENTITY_KEY["medical"]
    heads: dict[str, dict] = {}
    for rec in sorted((r for r in medical if _as_date(r.get("date"))),
                      key=lambda r: str(r.get("date"))):
        if _as_date(rec["date"]) <= when and (slug := rec.get(ident)):
            heads[str(slug)] = rec
    return [heads[s] for s in sorted(heads)]


def is_open(episode: dict, on: str | date) -> bool:
    """Is this episode still open on `on`?

    Open means: not resolved, or resolved with a closing date that has not yet
    passed. The window is what streak forgiveness will be computed from in a
    later increment, so it has to be a date range and not a boolean.
    """
    when = _as_date(on)
    if when is None:
        return False
    if episode.get("status") in (None, "resolved"):
        closed = _as_date(episode.get("resolved_date"))
        return bool(closed and when <= closed)
    return True


def active_episodes(medical: list[dict], on: str | date) -> list[dict]:
    return [e for e in episodes_on(medical, on) if is_open(e, on)]


# --- gates --------------------------------------------------------------------

# Which gate classes a session type falls under. A run is also an impact
# activity, so an impact gate stops it without anyone having to remember to
# list both.
SESSION_CLASSES: dict[str, set[str]] = {
    "run": {"run", "impact"},
    "test": {"run", "impact"},
    "walk": {"walk"},
    "gym_a": {"gym", "upper_body", "lower_body"},
    "gym_b": {"gym", "upper_body", "lower_body"},
    "other": set(),
}


def gates_on(medical: list[dict], on: str | date,
             pain_gate: int | None = None,
             daily: list[dict] | None = None) -> list[dict]:
    """Every gate in force on `on`, as data.

    A gate is a deterministic fact about a date, derived from the record: an
    open episode that restricts something, or pain at or above the athlete's
    configured gate. It carries its own escalation text so that whatever
    surfaces it - CLI, rollup, a coach - says the same thing.
    """
    when = _as_date(on)
    if when is None:
        return []
    out: list[dict] = []
    for episode in active_episodes(medical, on):
        classes = _restriction_classes(episode)
        if not classes:
            continue
        out.append({
            "date": when.isoformat(),
            "source_kind": "episode",
            "slug": episode.get("slug"),
            "restricts": " ".join(sorted(classes)),
            "reason": f"{episode.get('title')} ({episode.get('status')})",
            "severity": episode.get("severity"),
            "escalation": MESSAGES["gate"],
        })

    if pain_gate is not None:
        for row in daily or []:
            if _as_date(row.get("date")) != when:
                continue
            score = row.get("pain")
            if score is None:
                score = row.get("hip_pain")
            if _numeric(score) and score > pain_gate:
                site = row.get("pain_site") or "unspecified site"
                out.append({
                    "date": when.isoformat(),
                    "source_kind": "pain",
                    "slug": f"pain:{site}",
                    "restricts": "all",
                    "reason": f"pain {score} at {site} is over the gate ({pain_gate})",
                    "severity": "severe" if score >= PAIN_ABSOLUTE else "moderate",
                    "escalation": MESSAGES["gate"],
                })
    out.sort(key=lambda g: (g["source_kind"], str(g["slug"])))
    return out


def is_gated(gates: list[dict], activity: str) -> bool:
    """Is this activity class or session type blocked by any gate?

    Deliberately takes the computed gates rather than the record, so a caller
    cannot accidentally ask a question that skips the gate computation.
    """
    classes = SESSION_CLASSES.get(activity, {activity})
    for gate in gates:
        blocked = set(str(gate.get("restricts", "")).split())
        if "all" in blocked or blocked & classes:
            return True
    return False


# --- escalations --------------------------------------------------------------

def _escalation(when: str, level: str, trigger: str, detail: str) -> dict:
    return {"date": when, "level": level, "trigger": trigger,
            "detail": detail, "action": MESSAGES[trigger]}


def escalations(medical: list[dict], daily: list[dict], weight: list[dict],
                sessions: list[dict], on: str | date | None = None,
                include_red_s: bool = True) -> list[dict]:
    """Every safety escalation the record justifies, most urgent first.

    Computed over the whole record rather than the current week: an escalation
    is not a weekly summary item, and burying a chest-pain entry because it
    landed on a Tuesday would defeat the point.
    """
    out: list[dict] = []
    out += _declared_red_flags(medical)
    out += _red_flag_sites(medical, daily)
    out += _absolute_thresholds(daily)
    if include_red_s:
        out += _red_s(daily, weight, sessions)

    if (limit := _as_date(on)) is not None:
        out = [e for e in out if (d := _as_date(e["date"])) and d <= limit]
    out.sort(key=lambda e: (LEVEL_ORDER.get(e["level"], 9), e["date"], e["trigger"]))
    return out


def _declared_red_flags(medical: list[dict]) -> list[dict]:
    """Honour an explicit `severity: red_flag`, whoever wrote it.

    A skill that recognises something dangerous can raise this, and the engine
    acts on it without re-adjudicating. The asymmetry holds: this path can only
    add an escalation.
    """
    out = []
    for rec in medical:
        if rec.get("severity") == "red_flag" and rec.get("date"):
            out.append(_escalation(
                str(rec["date"]), URGENT, "red_flag_declared",
                f"{rec.get('title')} ({rec.get('slug')})"))
    return out


def _red_flag_sites(medical: list[dict], daily: list[dict]) -> list[dict]:
    """Sites that are never assumed musculoskeletal, from EITHER dataset.

    Both paths matter. A chest symptom logged as a medical line is obvious; a
    chest entry in the daily pain field is the one that would otherwise slide
    past as an ordinary sore spot to program around.
    """
    out = []
    for rec in medical:
        site = rec.get("body_site")
        if site in RED_FLAG_SITES and rec.get("date"):
            out.append(_escalation(
                str(rec["date"]), EMERGENCY, RED_FLAG_SITES[site],
                f"{rec.get('title')} recorded at {site}"))
    for row in daily:
        site = row.get("pain_site")
        score = row.get("pain")
        if site in RED_FLAG_SITES and _numeric(score) and score > 0 and row.get("date"):
            out.append(_escalation(
                str(row["date"]), EMERGENCY, RED_FLAG_SITES[site],
                f"pain {score} recorded at {site}"))
    return out


def _absolute_thresholds(daily: list[dict]) -> list[dict]:
    """Values outside physiological range, judged with no reference to baseline.

    The existing rhr tripwire is relative (baseline + 5), which is the right
    tool for detecting fatigue and the wrong one for detecting danger: an
    athlete whose baseline drifted upward over months never trips it, however
    high the number gets.
    """
    out = []
    for row in daily:
        when = row.get("date")
        if not when:
            continue
        rhr = row.get("rhr")
        if _numeric(rhr) and not RHR_ABSOLUTE_MIN <= rhr <= RHR_ABSOLUTE_MAX:
            out.append(_escalation(
                str(when), EMERGENCY, "rhr_absolute",
                f"resting heart rate {rhr} is outside "
                f"{RHR_ABSOLUTE_MIN}-{RHR_ABSOLUTE_MAX}"))
        score = row.get("pain") if row.get("pain") is not None else row.get("hip_pain")
        if _numeric(score) and score >= PAIN_ABSOLUTE:
            out.append(_escalation(
                str(when), URGENT, "severe_pain",
                f"pain {score} at {row.get('pain_site') or 'unspecified site'}"))
    return out


def _red_s(daily: list[dict], weight: list[dict],
           sessions: list[dict]) -> list[dict]:
    """Low-energy-availability screening over the most recent window.

    Three conditions, all required: a sustained deep energy deficit, weight
    coming off faster than a percent of bodyweight a week, and real training
    load on top. Any one alone is unremarkable; together and sustained they are
    the pattern that damages bone and hormonal health.

    Screened over one trailing window rather than every historical window, so
    the escalation says "this is happening now" instead of producing a wall of
    identical rows about last spring.
    """
    days = sorted((r for r in daily if _as_date(r.get("date"))),
                  key=lambda r: str(r["date"]))
    if not days:
        return []
    end = _as_date(days[-1]["date"])
    start = end - timedelta(days=RED_S_WINDOW_DAYS - 1)
    window = [r for r in days if start <= _as_date(r["date"]) <= end]

    balances = [float(r["kcal_in"]) - float(r["kcal_out"]) for r in window
                if _numeric(r.get("kcal_in")) and _numeric(r.get("kcal_out"))]
    if len(balances) < RED_S_MIN_DAYS:
        return []
    mean_balance = sum(balances) / len(balances)
    if mean_balance > RED_S_DEFICIT_KCAL:
        return []

    pts = sorted((str(w["date"]), float(w["kg"])) for w in weight
                 if _numeric(w.get("kg")) and _as_date(w.get("date"))
                 and start <= _as_date(w["date"]) <= end)
    if len(pts) < 2:
        return []
    span_days = (_as_date(pts[-1][0]) - _as_date(pts[0][0])).days
    if span_days <= 0:
        return []
    lost = pts[0][1] - pts[-1][1]
    pct_per_week = (lost / pts[0][1]) * 100.0 * 7.0 / span_days
    if pct_per_week < RED_S_LOSS_PCT_PER_WEEK:
        return []

    minutes = sum(float(s["duration_s"]) / 60.0 for s in sessions
                  if _numeric(s.get("duration_s")) and _as_date(s.get("date"))
                  and start <= _as_date(s["date"]) <= end)
    per_week = minutes * 7.0 / RED_S_WINDOW_DAYS
    if per_week < RED_S_LOAD_MIN_PER_WEEK:
        return []

    return [_escalation(
        end.isoformat(), URGENT, "red_s",
        f"mean energy balance {mean_balance:.0f} kcal/day, losing "
        f"{pct_per_week:.1f}% bodyweight/week, {per_week:.0f} min/week of "
        f"training over {RED_S_WINDOW_DAYS} days")]


# --- the fast path ------------------------------------------------------------

def urgent_now(escalations_rows: list[dict], on: str | date | None = None,
               within_days: int = 1) -> list[dict]:
    """Escalations that must not wait for the weekly rollup.

    The cadence of this tool is weekly by design, and for coaching that is
    correct. For a dangerous entry it is not: something logged on a Tuesday
    cannot sit unread until Sunday. Anything at emergency or urgent level dated
    within `within_days` of `on` surfaces the moment the record is built.
    """
    today = _as_date(on) or date.today()
    out = []
    for row in escalations_rows:
        when = _as_date(row.get("date"))
        if when is None or row["level"] not in (EMERGENCY, URGENT):
            continue
        if 0 <= (today - when).days <= within_days:
            out.append(row)
    return out


def banner(rows: list[dict]) -> str:
    """The fixed-format block shown for an escalation. Never model-authored."""
    if not rows:
        return ""
    lines = ["", "=" * 68, "SAFETY: this needs attention before any training decision.",
             "=" * 68]
    for row in rows:
        lines += ["", f"[{row['level'].upper()}] {row['date']} - {row['detail']}",
                  "", row["action"]]
    lines += ["", "This is not a diagnosis. vitai routes to a clinician and stops.",
              "=" * 68, ""]
    return "\n".join(lines)
