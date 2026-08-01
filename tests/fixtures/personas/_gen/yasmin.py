"""Generator for the yasmin persona (seed 106).

Ottawa, Canada. 46, perimenopausal, divorced, city planning office, two kids
on a week-on/week-off custody schedule that is the record's real clock. The
record runs three years and holds three restarts at getting back into some
kind of shape: 18 weeks in 2027, a six-month hole, 14 weeks in 2028, a
fourteen-month hole, then an attempt starting 2029-10 that is still running
on the corpus's last day. See `PROFILE.md`, `LIES.md`, `METRICS.md`,
`FINDINGS.md` and `WORLD.md` alongside this file for the prose this
generator's numbers have to agree with. Entirely synthetic; any resemblance
to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself - `generate.py` decides
whether that content lands on disk or is compared against what is already
committed.

Written and verified against installed `vitai 0.2.3`
(`common.AUTHORED_AGAINST_GENERATIONS` carries the exact figures;
`generate.py` prints a drift warning if the installed vitai has since moved
past them). Re-verify this generator against the handbook before trusting
its output once that version changes.

The medical boundary (`docs/medical-boundary.md`) governs every expectation
string this generator writes. Perimenopause is named once, as ordinary scene
setting, in `PROFILE.md` and `WORLD.md` - the same way rachel's PROFILE.md
opens on osteoarthritis and derek's on type 2 diabetes - but there is no
`medical.jsonl` row for it anywhere in this record (yasmin's Data list in
`.scratch/ARCS.md` never names one), and no expectation "expect" string ever
names it. The only trace it leaves in the data is a numeric one: a cluster of
low `sleep_h` values on nights the corpus author knows are disrupted nights.
The engine only ever gets to see the numbers.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 106
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# The record's own calendar: three restarts and two holes, a fixed piece of
# her history rather than a window that slides with wherever the corpus
# currently ends. Attempt 1 opens the whole record (2027-07-02); attempt 3
# is still running on the corpus's last day (2030-06-30) - the one that
# sticks, and it is not over.
ATTEMPT1_START = date(2027, 7, 2)
ATTEMPT1_END = date(2027, 11, 4)      # 18 weeks
ATTEMPT2_START = date(2028, 5, 7)
ATTEMPT2_END = date(2028, 8, 12)      # 14 weeks
ATTEMPT3_START = date(2029, 10, 1)    # ongoing
DEFAULT_END = date(2030, 6, 30)

# The custody calendar IS the cadence: one anchor Monday, alternating
# on/off weeks from there, gating weight, sessions and daily alike for
# attempts 1 and 2. Attempt 3 logs both weeks (WORLD.md, ARCS breaks: F5).
CUSTODY_ANCHOR = date(2027, 6, 28)   # a Monday

WEIGH_DAYS = {0, 2, 4}                # Monday, Wednesday, Friday
SESSION_DAYS_ON = {0, 1, 3, 4, 5}     # Monday, Tuesday, Thursday, Friday, Saturday
SESSION_DAYS_OFF3 = {0, 5}            # attempt 3 off-week only: Monday, Saturday
SESSION_ROLL = 0.85                   # chance a candidate on-week day gets a session
SESSION_ROLL_OFF3 = 0.5               # chance a candidate off-week (attempt 3) day does

# The three Y1 weight deltas across the two holes (LIES.md, kg). The first is
# the ARCS-specified fingerprint; the second is this generator's own choice,
# consistent with the longer, 14-month hole doing more damage than the
# six-month one.
ATTEMPT1_TO_2_JUMP_KG = 4.1
ATTEMPT2_TO_3_JUMP_KG = 6.3
WEIGHT_NOISE_SD = 0.65

# The Y2 journal claim: "this time I have not missed a single on-week
# session." It lands partway through attempt 3, well after the record could
# already have contradicted it.
Y2_CLAIM_DATE = date(2030, 3, 15)


def ottawa_offset(d: date) -> str:
    """UTC offset for Eastern Canada, deliberately simple in the same way
    `common.irish_offset` is: fixed calendar dates standing in for the
    actual second-Sunday-of-March / first-Sunday-of-November DST rule.
    EDT (`-04:00`) runs 10 March to 3 November; EST (`-05:00`) is the rest.
    """
    if date(d.year, 3, 10) <= d <= date(d.year, 11, 3):
        return "-04:00"
    return "-05:00"


def on_week(d: date) -> bool:
    """True on her custody on-week (Zara and Sami are home), False on the
    alternating off-week. One function gates weight, sessions and daily
    logging alike for attempts 1 and 2; attempt 3 logs on both, with a
    thinner off-week schedule rather than none at all.
    """
    return ((d - CUSTODY_ANCHOR).days // 7) % 2 == 0


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper(offset=ottawa_offset)
    daily_stamper = common.Stamper(offset=ottawa_offset)
    sessions_stamper = common.Stamper(offset=ottawa_offset)
    goals_stamper = common.Stamper(offset=ottawa_offset)
    journal_stamper = common.Stamper(offset=ottawa_offset)

    weight, jumps = _weight(rng, weight_stamper)
    daily = _daily(rng, daily_stamper)
    sessions, missed_dates = _sessions(rng, sessions_stamper)
    goals, goal_dates = _goals(goals_stamper)
    journal = _journal(journal_stamper)

    expectations = [
        _e1_biased_weighing(jumps),
        _e2_holes_break_trend(jumps),
        _e3_adherence_claim(missed_dates),
        _e4_two_week_cadence(),
        _e5_goal_period_enum(goal_dates),
        _e6_re_entry_pattern(goal_dates),
    ]

    return {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }


# --- weight ------------------------------------------------------------------


def _weight_attempt(rng: random.Random, stamper: common.Stamper,
                     start: date, end: date, start_val: float, end_val: float,
                     on_week_only: bool, restart_note: str | None
                     ) -> tuple[list[dict], float]:
    """One attempt's weight rows: logged only on a candidate weigh-in day
    (Monday/Wednesday/Friday, on-week only for attempts 1 and 2) AND only
    when the true value that day is BELOW every value logged so far this
    attempt (LIES.md Y1 - she steps off silently otherwise). The true value
    follows its own slow trend from `start_val` to `end_val` plus noise; it
    never resets or cares what got logged. The first candidate day always
    logs unconditionally at exactly `start_val` - this is what lets the next
    attempt's opening row sit at a known, exact distance above this one's
    last logged value (the Y1 fingerprint).
    """
    rows: list[dict] = []
    total_days = max(1, (end - start).days)
    last_logged: float | None = None
    for d in common.daterange(start, end):
        if d.weekday() not in WEIGH_DAYS:
            continue
        if on_week_only and not on_week(d):
            continue
        if last_logged is None:
            true_kg = start_val
        else:
            day_frac = (d - start).days / total_days
            base = start_val + (end_val - start_val) * day_frac
            true_kg = base + rng.gauss(0, WEIGHT_NOISE_SD)
        logged = round(true_kg, 1)
        if last_logged is not None and logged >= last_logged:
            continue
        measured_at = f"07:{rng.randrange(5, 40):02d}"
        fields = {
            "date": d.isoformat(), "kg": logged, "source": "mechanical-scale",
            "origin": "mechanical-scale", "capture": "manual_entry",
            "measured_at": measured_at,
            "note": restart_note if last_logged is None else None,
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("weight", **fields))
        last_logged = logged
    assert last_logged is not None, "an attempt logged no weight at all"
    return rows, last_logged


def _weight(rng: random.Random, stamper: common.Stamper) -> tuple[list[dict], dict]:
    rows: list[dict] = []

    a1_rows, a1_last = _weight_attempt(
        rng, stamper, ATTEMPT1_START, ATTEMPT1_END,
        start_val=82.0, end_val=79.0, on_week_only=True, restart_note=None)
    rows += a1_rows

    a2_first = round(a1_last + ATTEMPT1_TO_2_JUMP_KG, 1)
    a2_rows, a2_last = _weight_attempt(
        rng, stamper, ATTEMPT2_START, ATTEMPT2_END,
        start_val=a2_first, end_val=round(a2_first - 3.4, 1),
        on_week_only=True,
        restart_note="back on the scale, first time since the spring")
    rows += a2_rows

    a3_first = round(a2_last + ATTEMPT2_TO_3_JUMP_KG, 1)
    a3_rows, a3_last = _weight_attempt(
        rng, stamper, ATTEMPT3_START, DEFAULT_END,
        start_val=a3_first, end_val=round(a3_first - 5.8, 1),
        on_week_only=False,
        restart_note="starting again, for real this time")
    rows += a3_rows

    jumps = {
        "a1_last": a1_last, "a2_first": a2_first,
        "a2_jump": round(a2_first - a1_last, 1),
        "a2_last": a2_last, "a3_first": a3_first,
        "a3_jump": round(a3_first - a2_last, 1),
        "a1_rows": len(a1_rows), "a2_rows": len(a2_rows), "a3_rows": len(a3_rows),
    }
    return rows, jumps


# --- daily ---------------------------------------------------------------------


def _daily(rng: random.Random, stamper: common.Stamper) -> list[dict]:
    """`sleep_h` only, self-estimated, sparse, custody-gated like everything
    else. About three logged nights in ten read as a 4-to-5-hour cluster -
    the disrupted nights (WORLD.md, PROFILE.md) - against a 6-to-7.5-hour
    baseline the rest of the time. Nothing here, or anywhere in this
    persona's data, names why.
    """
    rows: list[dict] = []
    windows = [
        (ATTEMPT1_START, ATTEMPT1_END, True),
        (ATTEMPT2_START, ATTEMPT2_END, True),
        (ATTEMPT3_START, DEFAULT_END, False),
    ]
    for start, end, on_week_only in windows:
        for d in common.daterange(start, end):
            if on_week_only and not on_week(d):
                continue
            if rng.random() >= 0.45:
                continue
            disrupted = rng.random() < 0.3
            sleep_h = (round(rng.uniform(4.0, 5.0), 1) if disrupted
                       else round(rng.uniform(6.0, 7.5), 1))
            fields = {
                "date": d.isoformat(), "sleep_h": sleep_h, "source": "athlete",
                "coverage": "partial", "capture": "manual_entry",
                "recorded_at": stamper.stamp(d),
            }
            rows.append(common.record("daily", **fields))
    return rows


# --- sessions ------------------------------------------------------------------


def _session_row(rng: random.Random, stamper: common.Stamper, d: date,
                  gym_ok: bool) -> dict:
    kids_home = on_week(d)
    hour = rng.randrange(6, 8)
    start_time = (f"{d.isoformat()}T{hour:02d}:{rng.randrange(0, 59):02d}:00"
                   f"{ottawa_offset(d)}")
    if d.weekday() in (0, 3) or (d.weekday() == 5 and rng.random() < 0.35):
        use_gym = gym_ok and rng.random() < 0.4
        fields = {
            "date": d.isoformat(), "type": "strength",
            "duration_s": int(rng.uniform(28, 42) * 60),
            "rpe": rng.choice([3, 4, 4, 5]),
            "note": "gym circuit, drop-in visit" if use_gym else "home strength video",
            "source": "athlete", "start_time": start_time, "setting": "indoor",
            "place": "gym" if use_gym else "home",
            "route": "gym-circuit" if use_gym else None,
            "with": None, "context": "solo",
            "type_source": "athlete-stated", "capture": "manual_entry",
            "recorded_at": stamper.stamp(d),
        }
    else:
        family = kids_home and rng.random() < 0.25
        fields = {
            "date": d.isoformat(), "type": "walk", "distance_km": 3.2,
            "duration_s": int(rng.uniform(30, 40) * 60),
            "rpe": rng.choice([2, 2, 3]), "note": None, "source": "athlete",
            "start_time": start_time, "setting": "outdoor",
            "route": "river-path", "place": "river path",
            "with": rng.choice(["Zara", "Sami"]) if family else None,
            "context": "family" if family else "solo",
            "weather": rng.choice(["dry", "dry", "cold", "wind", "rain"]),
            "type_source": "athlete-stated", "capture": "manual_entry",
            "recorded_at": stamper.stamp(d),
        }
    return common.record("sessions", **fields)


def _sessions(rng: random.Random, stamper: common.Stamper
              ) -> tuple[list[dict], list[date]]:
    """Home strength video and the river path walk, home strength adding a
    gym-circuit variant once attempt 3's membership exists (WORLD.md). Zero
    off-week sessions in attempts 1 and 2 (ARCS: "attempts 1-2: zero");
    attempt 3 logs a thinner off-week schedule instead of none. The three
    Y2 missed on-week sessions (LIES.md) are chosen by index into attempt
    3's own on-week candidate calendar before the journal claim date, so
    they always land on an ordinary would-be session day.
    """
    rows: list[dict] = []

    for start, end in ((ATTEMPT1_START, ATTEMPT1_END),
                       (ATTEMPT2_START, ATTEMPT2_END)):
        for d in common.daterange(start, end):
            if not on_week(d) or d.weekday() not in SESSION_DAYS_ON:
                continue
            if rng.random() < SESSION_ROLL:
                rows.append(_session_row(rng, stamper, d, gym_ok=False))

    a3_on_candidates = [
        d for d in common.daterange(ATTEMPT3_START, Y2_CLAIM_DATE - timedelta(days=1))
        if on_week(d) and d.weekday() in SESSION_DAYS_ON
    ]
    n = len(a3_on_candidates)
    missed_idx = sorted({int(n * 0.2), int(n * 0.5), int(n * 0.8)})
    missed_dates = sorted(a3_on_candidates[i] for i in missed_idx)
    missed_set = set(missed_dates)

    for d in common.daterange(ATTEMPT3_START, DEFAULT_END):
        if on_week(d):
            if d.weekday() not in SESSION_DAYS_ON or d in missed_set:
                continue
            if rng.random() < SESSION_ROLL:
                rows.append(_session_row(rng, stamper, d, gym_ok=True))
        else:
            if d.weekday() not in SESSION_DAYS_OFF3:
                continue
            if rng.random() < SESSION_ROLL_OFF3:
                rows.append(_session_row(rng, stamper, d, gym_ok=True))

    return rows, missed_dates


# --- goals ---------------------------------------------------------------------


def _goal_pair(stamper: common.Stamper, slug: str, active_date: date,
               abandon_date: date, reason: str) -> list[dict]:
    active = common.record("goals")
    active.update({
        "date": active_date.isoformat(), "slug": slug,
        "title": "Four sessions a week, home strength and the river path",
        "metric": "session_count", "dataset": "sessions", "target": 4,
        "policy": "monotonic", "period": "weekly", "status": "active",
        "motivator": "feel like herself again before the kids are grown",
        "rationale": "a floor she can actually hit on an on-week",
        "set_by": "athlete", "recorded_at": stamper.stamp(active_date),
    })
    abandoned = common.record("goals")
    abandoned.update({
        "date": abandon_date.isoformat(), "slug": slug,
        "title": "Four sessions a week, home strength and the river path",
        "metric": "session_count", "dataset": "sessions", "target": 4,
        "policy": "monotonic", "period": "weekly", "status": "abandoned",
        "motivator": "feel like herself again before the kids are grown",
        "rationale": "a floor she can actually hit on an on-week",
        "set_by": "athlete", "reason": reason,
        "recorded_at": stamper.stamp(abandon_date),
    })
    return [active, abandoned]


def _goals(stamper: common.Stamper) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    g1_active = ATTEMPT1_START + timedelta(days=3)
    g1_abandoned = ATTEMPT1_END + timedelta(days=16)
    rows += _goal_pair(
        stamper, "attempt1-consistency", g1_active, g1_abandoned,
        "the routine fell apart once the gap started; never a decision, just stopped")

    g2_active = ATTEMPT2_START + timedelta(days=5)
    g2_abandoned = ATTEMPT2_END + timedelta(days=20)
    rows += _goal_pair(
        stamper, "attempt2-consistency", g2_active, g2_abandoned,
        "the after-school routine slipped again; the pause outlasted the plan, same as before")

    g3_active = ATTEMPT3_START + timedelta(days=7)
    g3 = common.record("goals")
    g3.update({
        "date": g3_active.isoformat(), "slug": "attempt3-consistency",
        "title": "Four sessions a week, most weeks, on or off",
        "metric": "session_count", "dataset": "sessions", "target": 4,
        "policy": "monotonic", "period": "weekly", "on_period_end": "carry",
        "status": "active",
        "motivator": "this is the one that has to stick",
        "rationale": ("carry a short week forward instead of resetting it to "
                      "zero - the two-week custody rhythm never fit a weekly "
                      "count anyway"),
        "set_by": "athlete", "recorded_at": stamper.stamp(g3_active),
    })
    rows.append(g3)

    dates = {
        "g1_active": g1_active, "g1_abandoned": g1_abandoned,
        "g2_active": g2_active, "g2_abandoned": g2_abandoned,
        "g3_active": g3_active,
    }
    return rows, dates


# --- journal -----------------------------------------------------------------


def _journal_row(stamper: common.Stamper, d: date, kind: str, text: str,
                 about: str, confidence: float | None, status: str | None) -> dict:
    fields = {
        "date": d.isoformat(), "kind": kind, "text": text, "about": about,
        "source": "athlete", "confidence": confidence, "status": status,
        "recorded_at": stamper.stamp(d),
    }
    return common.record("journal", **fields)


def _journal(stamper: common.Stamper) -> list[dict]:
    return [
        _journal_row(
            stamper, Y2_CLAIM_DATE, "claim",
            "This time I have not missed a single on-week session.",
            about="attempt3-consistency", confidence=0.9, status="open"),
        _journal_row(
            stamper, date(2029, 12, 20), "note",
            ("Forty-three months until Sami turns eighteen. Some weeks this "
             "feels like time with them. This week it just felt like the "
             "countdown."),
            about="custody", confidence=None, status=None),
        _journal_row(
            stamper, date(2030, 2, 2), "note",
            ("Opened the reunion page again tonight. Closed it without "
             "doing anything. Third time this year, maybe fourth."),
            about="reunion", confidence=None, status=None),
    ]


# --- expectations --------------------------------------------------------------


def _e1_biased_weighing(jumps: dict) -> dict:
    total_rows = jumps["a1_rows"] + jumps["a2_rows"] + jumps["a3_rows"]
    return {
        "id": "yasmin-E1", "kind": "lie", "dataset": "weight",
        "dates": [ATTEMPT1_START.isoformat(), ATTEMPT1_END.isoformat(),
                 ATTEMPT2_START.isoformat(), ATTEMPT2_END.isoformat(),
                 ATTEMPT3_START.isoformat(), DEFAULT_END.isoformat()],
        "claim": (
            f"across all three attempts, {total_rows} weight rows are "
            "logged and every single logged delta within an attempt is "
            "negative - a smooth, unbroken descent inside attempt 1, "
            "another inside attempt 2, another inside attempt 3"
        ),
        "truth": (
            "she weighs herself often and logs only the days the number is "
            "below the last one she wrote down; every other day she steps "
            "off silently. The true series oscillates day to day (water, "
            "hormones, an ordinary bad night) around a much gentler trend "
            "than the logged rows suggest, and it drifts UP across both "
            "holes rather than pausing: attempt 1's last logged row is "
            f"{jumps['a1_last']:.1f} kg; attempt 2's first logged row, with "
            f"zero weight rows in between, is {jumps['a2_first']:.1f} kg - "
            f"{jumps['a2_jump']:.1f} kg higher. The same shape repeats "
            f"across the second, longer hole: attempt 2's last logged row "
            f"is {jumps['a2_last']:.1f} kg, attempt 3's first is "
            f"{jumps['a3_first']:.1f} kg, {jumps['a3_jump']:.1f} kg higher"
        ),
        "expect": (
            "a record where every logged weight delta within an attempt is "
            "negative is not what honest, unselected daily weighing looks "
            "like (the probability of an unbroken run that long under "
            "honest sampling is vanishingly small); the engine should "
            "state that a one-sided logging pattern like this makes any "
            "rate-of-loss estimate from the record untrustworthy, and "
            "should decline to state a rate, or state it only with an "
            "explicit low-confidence widening, rather than reporting the "
            "logged slope at face value (class a+b)"
        ),
        "gap": (
            "no sampling-bias or selection-on-outcome check exists in the "
            "engine today; nothing reads 'every delta negative' as a "
            "distributional oddity, and nothing distinguishes a smooth "
            "logged descent that IS the truth from one that is a symptom "
            "of one-sided recording"
        ),
    }


def _e2_holes_break_trend(jumps: dict) -> dict:
    return {
        "id": "yasmin-E2", "kind": "behavior", "dataset": "weight",
        "dates": [ATTEMPT1_END.isoformat(), ATTEMPT2_START.isoformat(),
                 ATTEMPT2_END.isoformat(), ATTEMPT3_START.isoformat()],
        "claim": (
            "weight.jsonl has a roughly six-month gap with zero rows "
            f"between {ATTEMPT1_END.isoformat()} and "
            f"{ATTEMPT2_START.isoformat()}, and a roughly fourteen-month "
            f"gap with zero rows between {ATTEMPT2_END.isoformat()} and "
            f"{ATTEMPT3_START.isoformat()}"
        ),
        "truth": (
            "both gaps are real: she was not weighing herself at all, not "
            "logging selectively - there is nothing to select from. The "
            "jump in the logged value across each gap "
            f"({jumps['a2_jump']:.1f} kg and {jumps['a3_jump']:.1f} kg) is "
            "a true change over an unmeasured span, not a data point on a "
            "continuous trend"
        ),
        "expect": (
            "the engine must not draw a trend line, interpolate, or "
            "compute a rate across either gap - a fourteen-month span with "
            "zero rows is not a slow week and must never be smoothed over "
            "as if it were one. The correct behaviour is to treat each "
            "attempt as its own bounded window and state plainly that the "
            "record has nothing to say about what happened between them"
        ),
        "gap": (
            "an long unlogged span is visible as a large date gap between "
            "consecutive rows, but nothing in the engine today explicitly "
            "refuses to fit a trend across a gap past some threshold - the "
            "correct behaviour here rests on the same missing capability "
            "as yasmin-E1"
        ),
    }


def _e3_adherence_claim(missed_dates: list[date]) -> dict:
    return {
        "id": "yasmin-E3", "kind": "gap", "dataset": "journal",
        "dates": [Y2_CLAIM_DATE.isoformat()] + [d.isoformat() for d in missed_dates],
        "claim": (
            f"journal, {Y2_CLAIM_DATE.isoformat()}: 'This time I have not "
            "missed a single on-week session.'"
        ),
        "truth": (
            "three on-week days that would ordinarily carry a session - "
            + ", ".join(d.isoformat() for d in missed_dates) +
            " - carry none in sessions.jsonl, all before the claim was written"
        ),
        "expect": (
            "nothing in the engine today compares a journal claim against "
            "the sessions record. If it did, the correct output is an "
            "observation contrasting the claim with the three missed "
            "on-week days, never an adjudication of her honesty or "
            "character - the same class-(a) treatment as any other "
            "record-vs-record mismatch"
        ),
        "gap": "no journal-claim-vs-record cross-check exists today",
    }


def _e4_two_week_cadence() -> dict:
    return {
        "id": "yasmin-E4", "kind": "behavior", "dataset": "sessions",
        "dates": [ATTEMPT1_START.isoformat(), ATTEMPT3_START.isoformat(),
                 DEFAULT_END.isoformat()],
        "claim": (
            "in attempts 1 and 2, every week with zero session rows is "
            "immediately followed or preceded by a week with four or five"
        ),
        "truth": (
            "this is the custody calendar, not inconsistency: the on-week "
            "carries four to five sessions, the off-week carries none at "
            "all in attempts 1 and 2 (a thinner but nonzero schedule in "
            "attempt 3). A rollup keyed to the calendar week will read "
            "every other week as a total lapse"
        ),
        "expect": (
            "any weekly rollup or streak computed over this record should "
            "be read against her two-week cadence, not the calendar week; "
            "an off-week with zero sessions is not itself evidence of "
            "reduced adherence and should not be reported as one"
        ),
        "gap": (
            "F5/G60: the engine has no notion of a custody or roster "
            "cadence distinct from the calendar week; every built-in "
            "weekly aggregate assumes a seven-day period means the same "
            "thing every time it repeats"
        ),
    }


def _e5_goal_period_enum(goal_dates: dict) -> dict:
    return {
        "id": "yasmin-E5", "kind": "gap", "dataset": "goals",
        "dates": [goal_dates["g3_active"].isoformat()],
        "claim": (
            "the attempt-3 goal ('attempt3-consistency') is recorded with "
            "period='weekly' and on_period_end='carry'"
        ),
        "truth": (
            "her actual practiced rhythm is two-week, not weekly - the "
            "custody calendar; 'weekly' is the closest value the enum "
            "offers, not an accurate description of her cadence"
        ),
        "expect": (
            "the engine should read this goal's weekly period as a "
            "structural approximation of a two-week reality, not as her "
            "stated intent to be judged every single week; on_period_end="
            "'carry' softens a short week but does not fully correct a "
            "period boundary drawn in the wrong place"
        ),
        "gap": (
            "GOAL_PERIODS has no 'biweekly' or custody-cycle value "
            "(monthly, none, quarterly, weekly, yearly only), so a goal "
            "tracking a two-week-cadence life has no exact-fitting period "
            "to declare"
        ),
    }


def _e6_re_entry_pattern(goal_dates: dict) -> dict:
    return {
        "id": "yasmin-E6", "kind": "behavior", "dataset": "goals",
        "dates": [goal_dates["g1_active"].isoformat(), goal_dates["g1_abandoned"].isoformat(),
                 goal_dates["g2_active"].isoformat(), goal_dates["g2_abandoned"].isoformat(),
                 goal_dates["g3_active"].isoformat()],
        "claim": (
            "goals.jsonl carries three separate slugs across the record - "
            "'attempt1-consistency' (active, then abandoned), "
            "'attempt2-consistency' (active, then abandoned), and "
            "'attempt3-consistency' (active, still open) - rather than one "
            "goal reopened three times"
        ),
        "truth": (
            "each attempt is a genuine restart, not a continuation: a new "
            "goal, a new slug, its own short life. This is the dominant "
            "real pattern in her record, not a falsehood - re-entry after "
            "a long stop is normal, and three honest restarts are not "
            "three failures of the same programme"
        ),
        "expect": (
            "the engine should read the abandoned/abandoned/active "
            "sequence as three distinct attempts rather than one "
            "continuously failing goal, and should not carry any penalty, "
            "streak, or rate assumption from an abandoned era's goal into "
            "the currently active one"
        ),
        "gap": (
            "F8/G63: nothing in the engine models a life-goal as a series "
            "of attempts; each active/abandoned goal pair validates fine "
            "on its own, but there is no read that groups three same-shape "
            "goals into one re-entry history"
        ),
    }


_TOML = """# yasmin: synthetic persona corpus, thresholds tuned to her record.
#
# The weight record's own selection bias (LIES.md Y1) means any [targets]
# phase or rate-based verdict here would be evaluated against a series the
# corpus itself documents as untrustworthy for rate claims. The phases below
# exist for realism (the band her logged weight actually occupies), never as
# an endorsement that a rate estimate from this record is safe to state.
[targets]
phases = [[95.0, 74.0, 0.30]]

[tripwires]
sleep_floor_h = 6.0

# Only two sources appear anywhere in this record; both are listed here.
# Once [resolution] exists at all, an unlisted source is a hard validate
# failure, not a warning (handbook pitfall 4).
[resolution]
source_order = ["mechanical-scale", "athlete"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
