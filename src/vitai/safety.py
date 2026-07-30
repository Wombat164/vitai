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
# HOLD sits between them because it is not a louder message - it is a different
# ACT. An escalation tells the athlete something; a hold changes what the system
# is allowed to do: algorithmic progression suspends and the coach may not issue
# training advice at all. Printing a warning and then carrying on prescribing is
# exactly the failure a hold exists to make impossible.
EMERGENCY, HOLD, URGENT, ADVISORY = "emergency", "hold", "urgent", "advisory"
LEVEL_ORDER = {EMERGENCY: 0, HOLD: 1, URGENT: 2, ADVISORY: 3}
BLOCKING_LEVELS = (EMERGENCY, HOLD)

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
    "clinical_hold": (
        "TRAINING IS ON HOLD. This is not a suggestion to take it easy: no "
        "plan, progression or session will be issued until a clinician has "
        "reviewed you. The pattern in your record - low energy availability "
        "alongside other findings - is associated with bone, hormonal and "
        "cardiac harm, and continuing to train through it is how that harm "
        "happens. Take this record to a doctor or a sports physician."),
    "intake_floor": (
        "Your logged intake is below the level a body needs to run on, "
        "sustained over more than a week. Eat more today, and contact a "
        "doctor or a registered dietitian. If your intake is low because "
        "eating is hard right now, that is a reason to get support, not a "
        "reason to wait."),
    "protein_floor": (
        "Your protein intake is far below what is needed during weight loss. "
        "Losing weight on inadequate protein without resistance training "
        "takes the weight off muscle as well as fat, and that loss is hard to "
        "reverse. Raise protein and add resistance work - and if a medication "
        "is suppressing your appetite, tell the prescriber it is this low."),
    "syncope": (
        "Stop training and contact a doctor. Losing consciousness, or nearly "
        "losing it, during or around exercise is never something to train "
        "through and is never explained by being unfit. It needs looking at "
        "before your next session, not after it."),
    "prose_symptom": (
        "Something you wrote in a note describes a symptom that should be "
        "checked rather than trained through. Contact a doctor. If the note "
        "did not mean what it sounds like, record the entry properly so the "
        "record stops guessing."),
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

# --- the prose net (G59) ------------------------------------------------------
# The escalation path above only works for an athlete who files structured
# entries. The finding that produced this: five exertional chest-pain episodes
# of increasing duration, every one of them written into a free-text note and
# downplayed - "twinge on the stairs, few seconds, gone" - and the engine saw
# none of them, because frightened people do not fill in a `pain_site` field.
# They write "it's nothing, not really worth going on about".
#
# This is a NET, not a parser. It matches fixed phrases, it can only ever ADD
# an escalation, and the structured path remains primary. It exists because
# under-triage is the failure that matters, and a symptom nobody structured is
# still a symptom.
CARDIAC_PHRASES = ("chest pain", "chest tightness", "chest twinge",
                   "tight chest", "chest pressure", "pain in my chest",
                   "chest hurts")
SYNCOPE_PHRASES = ("blacked out", "black out", "blackout", "passed out",
                   "fainted", "syncope", "lost consciousness")
AMENORRHOEA_PHRASES = ("period still absent", "periods stopped",
                       "period stopped", "no period", "periods have stopped",
                       "amenorrh", "missed period")
BONE_STRESS_PHRASES = ("stress fracture", "stress fractures",
                       "stress reaction", "bone stress")
PROSE_TRIGGERS = {"cardiac": CARDIAC_PHRASES, "syncope": SYNCOPE_PHRASES}

# A phrase preceded by one of these is a denial, not a report. Five lines of
# guard rather than none, because escalating "no chest pain" to an emergency
# is exactly the crying-wolf that teaches people to ignore the alarm.
NEGATIONS = ("no ", "not ", "never ", "without ", "denies ", "wasn't ",
             "was not ", "didn't ", "did not ")

# --- RED-S / low energy availability -----------------------------------------
# The syndrome a tool that coaches deficits can itself cause, which is why it
# is the engine's job to watch for it rather than the athlete's.
#
# THE CORRECTION (issue #12). The first version required deficit AND rate of
# loss AND load - all three. That reasoning holds for an athlete who is losing,
# and it is wrong for the syndrome, because RED-S very commonly presents
# WEIGHT-STABLE: the body downregulates instead of shedding. Resting heart rate
# drifts, periods stop, resting metabolic rate falls, recovery degrades, and
# the scale says nothing at all.
#
# Requiring loss therefore made weight stability EXONERATING, when in this
# syndrome stability is frequently the finding itself. The validation persona
# who exposed it - stable at 57 kg for months, RHR drifted 42 -> 51, five
# months amenorrhoeic, two prior stress fractures - is textbook, and the old
# composite could not see her.
#
# So rate of loss is now SUFFICIENT BUT NOT NECESSARY: low energy availability
# plus load plus ANY ONE corroborating marker fires. Fast loss is one such
# marker. It is no longer the only door in.
RED_S_WINDOW_DAYS = 14
RED_S_DEFICIT_KCAL = -1000.0      # mean daily energy balance over the window
RED_S_LOSS_PCT_PER_WEEK = 1.0     # % of bodyweight per week
RED_S_LOAD_MIN_PER_WEEK = 180.0   # minutes of logged sessions per week
RED_S_MIN_DAYS = 10               # do not screen on a nearly-empty window

# Energy availability = (intake - exercise energy) / fat-free mass, in kcal per
# kg FFM per day. Below ~30 is the threshold the sports-medicine literature
# uses for low energy availability; below ~45 is where adaptations begin. This
# is the measure the syndrome is actually defined by, and it needs no weight
# TREND at all - which is exactly why it sees the stable presentation.
EA_LOW_THRESHOLD = 30.0
# Fat-free mass needs a body-composition read. Without one, EA is not computed
# rather than guessed: inventing a body-fat percentage to feed a safety rule
# would be manufacturing the input to a clinical decision.

# Absolute floors, applying to everyone with no configuration at all - the same
# pattern as the absolute resting-heart-rate band. A safety net that has to be
# switched on protects only the people who already knew they needed it, and
# the athlete this caught had configured nothing, as new users have not.
INTAKE_FLOOR_KCAL = 1200.0        # sustained mean intake at or below this
INTAKE_FLOOR_MIN_DAYS = 7
PROTEIN_FLOOR_G_PER_KG = 0.8      # below the general adult minimum
RAPID_LOSS_PCT_PER_WEEK = 1.0     # for the lean-mass composite


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


def hold_gates(escalation_rows: list[dict], on: str | date) -> list[dict]:
    """A clinical hold expressed as a gate (G73).

    This is what makes a hold an ACT rather than a message. A gate is the
    thing the coach is structurally unable to talk around, so routing the hold
    through it means "no training advice" is enforced by the same mechanism
    that already blocks a gated activity - not by asking the coach nicely.
    """
    when = _as_date(on)
    if when is None:
        return []
    out = []
    for row in escalation_rows:
        if row.get("level") not in BLOCKING_LEVELS:
            continue
        if (raised := _as_date(row.get("date"))) is None or raised > when:
            continue
        out.append({
            "date": when.isoformat(),
            "source_kind": "hold",
            "slug": f"hold:{row['trigger']}",
            "restricts": "all",
            "reason": f"{row['level']}: {row['detail']}",
            "severity": "red_flag",
            "escalation": row["action"],
        })
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
    out += _prose_symptoms(daily, sessions, medical)
    out += _intake_and_protein_floors(daily, weight, medical, sessions)
    if include_red_s:
        out += _red_s(daily, weight, sessions, medical)

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


def _negated(text: str, index: int) -> bool:
    """Is the phrase at `index` preceded by a denial within a short window?"""
    lead = text[max(0, index - 24):index]
    return any(neg in lead for neg in NEGATIONS)


def scan_prose(text: str | None) -> list[str]:
    """Red-flag triggers named by a free-text note. Deterministic, additive."""
    if not text:
        return []
    low = str(text).lower()
    found: list[str] = []
    for trigger, phrases in PROSE_TRIGGERS.items():
        for phrase in phrases:
            idx = low.find(phrase)
            if idx >= 0 and not _negated(low, idx):
                found.append(trigger)
                break
    return found


def _prose_symptoms(daily: list[dict], sessions: list[dict],
                    medical: list[dict]) -> list[dict]:
    """Escalate red-flag language wherever the athlete actually wrote it.

    One mention is enough. Waiting for a pattern would mean waiting for the
    fifth episode, which is what happened to the persona this rule exists for.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    sources = ([(r.get("date"), r.get("note")) for r in daily]
               + [(r.get("date"), r.get("note")) for r in sessions]
               + [(r.get("date"), f"{r.get('title') or ''} {r.get('note') or ''}")
                  for r in medical])
    for when, note in sources:
        if not when:
            continue
        for trigger in scan_prose(note):
            if (str(when), trigger) in seen:
                continue
            seen.add((str(when), trigger))
            quoted = " ".join(str(note).split())[:90]
            level = EMERGENCY if trigger == "cardiac" else URGENT
            # Keyed by the SPECIFIC trigger, not by the fact it came from
            # prose: a chest symptom is the same clinical fact however it was
            # written down, and downstream should not have to care which
            # field it arrived in.
            row = _escalation(str(when), level, trigger,
                              f"a note reports {trigger}: \"{quoted}\"")
            row["action"] = MESSAGES.get(trigger, MESSAGES["prose_symptom"])
            out.append(row)
    return out


def _intake_and_protein_floors(daily: list[dict], weight: list[dict],
                               medical: list[dict],
                               sessions: list[dict]) -> list[dict]:
    """Absolute nutrition floors that fire with no configuration at all (G68).

    The athlete who exposed this had configured nothing - as new users have
    not - and was eating ~1200 kcal a day while exclusively breastfeeding and
    losing a kilo a week. The engine said `tripwires: none`, because every
    rule it had needed a threshold somebody had set.
    """
    window, start, end = _window(daily, RED_S_WINDOW_DAYS)
    if not window:
        return []
    out: list[dict] = []
    expects = _expectations(medical, end)
    floor = INTAKE_FLOOR_KCAL
    if "elevated_requirement" in expects:
        # A declared state raises the floor; it can never remove it (G57).
        floor += 500.0

    intakes = [float(r["kcal_in"]) for r in window if _numeric(r.get("kcal_in"))]
    if len(intakes) >= INTAKE_FLOOR_MIN_DAYS:
        mean_intake = sum(intakes) / len(intakes)
        if mean_intake <= floor:
            detail = (f"mean intake {mean_intake:.0f} kcal/day over "
                      f"{len(intakes)} days, at or below the {floor:.0f} floor")
            if "elevated_requirement" in expects:
                detail += " (raised for a declared physiological state)"
            out.append(_escalation(end.isoformat(), URGENT, "intake_floor", detail))

    # Protein against bodyweight, and the lean-mass composite that matters
    # during rapid loss (G72): weight coming off fast, protein far too low, and
    # no resistance training to defend muscle.
    kg = _latest_weight(weight, end)
    proteins = [float(r["protein_g"]) for r in window
                if _numeric(r.get("protein_g"))]
    if kg and len(proteins) >= INTAKE_FLOOR_MIN_DAYS:
        per_kg = (sum(proteins) / len(proteins)) / kg
        if per_kg < PROTEIN_FLOOR_G_PER_KG:
            loss = _loss_pct_per_week(weight, start, end) or 0.0
            resistance = any(str(s.get("type", "")).startswith("gym")
                             for s in sessions
                             if _as_date(s.get("date"))
                             and start <= _as_date(s["date"]) <= end)
            detail = (f"protein {per_kg:.2f} g/kg bodyweight/day, below the "
                      f"{PROTEIN_FLOOR_G_PER_KG} g/kg minimum")
            if loss >= RAPID_LOSS_PCT_PER_WEEK and not resistance:
                detail += (f"; losing {loss:.1f}%/week with no resistance "
                           "training - lean-mass loss risk")
            out.append(_escalation(end.isoformat(), URGENT, "protein_floor",
                                   detail))
    return out


def _latest_weight(weight: list[dict], end: date) -> float | None:
    pts = sorted((str(w["date"]), float(w["kg"])) for w in weight
                 if _numeric(w.get("kg")) and _as_date(w.get("date"))
                 and _as_date(w["date"]) <= end)
    return pts[-1][1] if pts else None


def _expectations(medical: list[dict], on: date) -> set[str]:
    """What open states and medications tell the engine to expect (G57/G72)."""
    out: set[str] = set()
    for episode in active_episodes(medical, on):
        raw = episode.get("expects")
        if not raw:
            continue
        tokens = (raw if isinstance(raw, list)
                  else str(raw).replace(",", " ").split())
        out.update(str(t).strip() for t in tokens if str(t).strip())
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


def _window(daily: list[dict], days_back: int) -> tuple[list[dict], date, date]:
    """The trailing window of daily rows, and its bounds."""
    days = sorted((r for r in daily if _as_date(r.get("date"))),
                  key=lambda r: str(r["date"]))
    if not days:
        return [], date.min, date.min
    end = _as_date(days[-1]["date"])
    start = end - timedelta(days=days_back - 1)
    return [r for r in days if start <= _as_date(r["date"]) <= end], start, end


def _loss_pct_per_week(weight: list[dict], start: date, end: date) -> float | None:
    pts = sorted((str(w["date"]), float(w["kg"])) for w in weight
                 if _numeric(w.get("kg")) and _as_date(w.get("date"))
                 and start <= _as_date(w["date"]) <= end)
    if len(pts) < 2:
        return None
    span = (_as_date(pts[-1][0]) - _as_date(pts[0][0])).days
    if span <= 0 or not pts[0][1]:
        return None
    return ((pts[0][1] - pts[-1][1]) / pts[0][1]) * 100.0 * 7.0 / span


def _fat_free_mass(weight: list[dict], end: date) -> float | None:
    """Fat-free mass from the most recent body-composition read, or None.

    Never estimated. A guessed body-fat percentage would be a manufactured
    input to a clinical decision, and the honest answer to "we do not know the
    athlete's composition" is to not compute the metric that needs it.
    """
    reads = sorted((str(w["date"]), float(w["kg"]), float(w["body_fat_pct"]))
                   for w in weight
                   if _numeric(w.get("kg")) and _numeric(w.get("body_fat_pct"))
                   and _as_date(w.get("date")) and _as_date(w["date"]) <= end)
    if not reads:
        return None
    _, kg, bf = reads[-1]
    return kg * (1.0 - bf / 100.0) if 0 < bf < 100 else None


def _session_minutes(sessions: list[dict], start: date, end: date) -> float:
    return sum(float(s["duration_s"]) / 60.0 for s in sessions
               if _numeric(s.get("duration_s")) and _as_date(s.get("date"))
               and start <= _as_date(s["date"]) <= end)


def energy_availability(daily: list[dict], weight: list[dict],
                        sessions: list[dict]) -> tuple[float | None, dict]:
    """EA in kcal per kg fat-free mass per day, plus the terms behind it.

    This is the measure the syndrome is defined by, and it needs no weight
    trend - which is why it sees the weight-stable presentation the first
    version of this composite was blind to.
    """
    window, start, end = _window(daily, RED_S_WINDOW_DAYS)
    intakes = [float(r["kcal_in"]) for r in window if _numeric(r.get("kcal_in"))]
    ffm = _fat_free_mass(weight, end) if window else None
    if len(intakes) < RED_S_MIN_DAYS or not ffm:
        return None, {}
    exercise = sum(float(s["kcal"]) for s in sessions
                   if _numeric(s.get("kcal")) and _as_date(s.get("date"))
                   and start <= _as_date(s["date"]) <= end)
    mean_intake = sum(intakes) / len(intakes)
    per_day_exercise = exercise / RED_S_WINDOW_DAYS
    ea = (mean_intake - per_day_exercise) / ffm
    return ea, {"intake": mean_intake, "exercise": per_day_exercise,
                "ffm": ffm, "end": end.isoformat()}


def _corroborating_markers(daily: list[dict], weight: list[dict],
                           medical: list[dict], start: date,
                           end: date) -> list[str]:
    """Findings that, with low EA and load, are enough on their own.

    Each of these is a recognised consequence of chronic low energy
    availability. Any ONE alongside low EA is the pattern; requiring the scale
    to move as well is what made the syndrome invisible when it presents
    weight-stable.
    """
    markers: list[str] = []

    loss = _loss_pct_per_week(weight, start, end)
    if loss is not None and loss >= RED_S_LOSS_PCT_PER_WEEK:
        markers.append(f"losing {loss:.1f}% bodyweight/week")

    # Resting heart rate drifting UP over the window against the record's own
    # earlier baseline - the autonomic cost of underfuelling.
    history = sorted((str(r["date"]), float(r["rhr"])) for r in daily
                     if _numeric(r.get("rhr")) and _as_date(r.get("date")))
    recent = [v for d, v in history if start <= _as_date(d) <= end]
    earlier = [v for d, v in history if _as_date(d) < start]
    if len(recent) >= 3 and len(earlier) >= 3:
        drift = sum(recent) / len(recent) - sum(earlier) / len(earlier)
        if drift >= 5.0:
            markers.append(f"resting heart rate drifted +{drift:.0f}")

    prose = " ".join(str(r.get("note") or "") for r in daily).lower()
    prose += " " + " ".join(f"{m.get('title')} {m.get('note')}".lower()
                            for m in medical)
    if any(p in prose for p in AMENORRHOEA_PHRASES):
        markers.append("menstrual function reported absent")
    if any(p in prose for p in BONE_STRESS_PHRASES) or any(
            str(m.get("body_site")) and "stress" in str(m.get("title", "")).lower()
            for m in medical):
        markers.append("bone-stress injury history")
    return markers


def _red_s(daily: list[dict], weight: list[dict], sessions: list[dict],
           medical: list[dict]) -> list[dict]:
    """Low-energy-availability screening over the most recent window.

    Fires on low EA + real training load + ANY ONE corroborating marker. Rate
    of loss is one marker among several rather than a gate, because the
    syndrome does not require the scale to move.

    Falls back to the energy-BALANCE form when body composition is unknown, so
    an athlete who logs intake and expenditure but never a body-fat read is
    still screened - just by the cruder measure, which does need the trend.
    """
    window, start, end = _window(daily, RED_S_WINDOW_DAYS)
    if not window:
        return []

    per_week = _session_minutes(sessions, start, end) * 7.0 / RED_S_WINDOW_DAYS
    if per_week < RED_S_LOAD_MIN_PER_WEEK:
        return []

    markers = _corroborating_markers(daily, weight, medical, start, end)
    ea, terms = energy_availability(daily, weight, sessions)

    if ea is not None and ea < EA_LOW_THRESHOLD:
        if not markers:
            return []
        return [_escalation(
            end.isoformat(), HOLD, "clinical_hold",
            f"energy availability {ea:.0f} kcal/kg FFM/day (below "
            f"{EA_LOW_THRESHOLD:.0f}), {per_week:.0f} min/week of training, "
            f"and: {'; '.join(markers)}")]

    # No body-composition read: fall back to energy balance, which cannot see
    # the weight-stable presentation but is better than screening nothing.
    balances = [float(r["kcal_in"]) - float(r["kcal_out"]) for r in window
                if _numeric(r.get("kcal_in")) and _numeric(r.get("kcal_out"))]
    if len(balances) < RED_S_MIN_DAYS:
        return []
    mean_balance = sum(balances) / len(balances)
    if mean_balance > RED_S_DEFICIT_KCAL or not markers:
        return []
    return [_escalation(
        end.isoformat(), HOLD, "clinical_hold",
        f"mean energy balance {mean_balance:.0f} kcal/day, {per_week:.0f} "
        f"min/week of training, and: {'; '.join(markers)}")]


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
