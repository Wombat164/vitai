"""Generator for the marcus persona (seed 105).

York, England. 41, secondary school teacher, five marathons over two and a
half years: 3:29, 3:21, a 3:17 PB, a DNF, then a 3:26 regression. An achilles
he first mentions in passing in June 2029 and does not let anyone call an
injury until November, after the DNF forces the point. See `PROFILE.md`,
`LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md` alongside this file for
the prose this generator's numbers have to agree with. Entirely synthetic;
any resemblance to a real person is accidental and unintended.

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
string this generator writes: observation and self-constraint only, never a
condition name, never a care instruction. Marcus's own journal and medical
rows DO name his achilles plainly - that is his own self-report, exactly as
legitimate as rachel naming her knee osteoarthritis - the boundary constrains
what the ENGINE may conclude, not what the athlete says about himself.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

from . import common

SEED = 105
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 2

START = date(2028, 1, 3)
DEFAULT_END = date(2030, 6, 30)

# --- WORLD.md route catalog --------------------------------------------------

ROUTES = {"canal": 8.1, "park": 5.0, "long": 21.5}

# Monday=0 .. Sunday=6. Term-time: three runs a week. Holiday: five.
TERM_DAYS = {1, 3, 5}              # Tuesday, Thursday, Saturday
HOLIDAY_DAYS = {0, 1, 2, 3, 5}     # Monday, Tuesday, Wednesday, Thursday, Saturday

# WORLD.md calendar: Easter, summer and Christmas blocks, the summer and
# Easter ones spent partly at the cottage in Whitby. Half-terms are real but
# do not change the running cadence enough to model separately.
HOLIDAYS = [
    (date(2028, 4, 14), date(2028, 4, 28)),   # Easter 2028 (Whitby)
    (date(2028, 7, 22), date(2028, 9, 2)),    # summer 2028 (Whitby)
    (date(2028, 12, 18), date(2029, 1, 3)),   # Christmas 2028/29
    (date(2029, 4, 13), date(2029, 4, 27)),   # Easter 2029 (Whitby)
    (date(2029, 7, 21), date(2029, 9, 1)),    # summer 2029 (Whitby)
    (date(2029, 12, 18), date(2030, 1, 2)),   # Christmas 2029/30
    (date(2030, 4, 12), date(2030, 4, 26)),   # Easter 2030 (Whitby)
]


def is_holiday(d: date) -> bool:
    return any(a <= d <= b for a, b in HOLIDAYS)


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_is_holiday(wk: date) -> bool:
    """Whether the WHOLE week (Monday to Sunday) counts as holiday, decided
    once from the Monday alone. A holiday window that starts mid-week (the
    common case - term ends on a Wednesday, say) would otherwise let
    `is_holiday` classify some days of one calendar week as term and others
    as holiday, which reintroduces the exact recorded_at monotonicity trap
    the per-row bug did (handbook lesson 2): a Monday backfilled to that
    week's Sunday, immediately followed in file order by a Tuesday inside
    the holiday window logging same-day, decreases. Scheduling and back-fill
    both key off this single per-week decision instead."""
    return is_holiday(wk)


# --- the marathon calendar (events.jsonl + the arc) ---------------------------
#
# Same fictional race, run twice a year: the Ainsford Marathon, spring and
# autumn editions. 3:29 -> 3:21 -> 3:17 PB -> DNF -> 3:26. The PB is only
# interesting because something later regresses (ARCS: "the canonical case").

RACES = [
    {"slug": "ainsford-marathon-2028-spring", "date": date(2028, 4, 9),
     "edition": "spring", "result": "finish", "time_s": 12540,
     "time_str": "3:29:00"},
    {"slug": "ainsford-marathon-2028-autumn", "date": date(2028, 10, 8),
     "edition": "autumn", "result": "finish", "time_s": 12060,
     "time_str": "3:21:00"},
    {"slug": "ainsford-marathon-2029-spring", "date": date(2029, 4, 8),
     "edition": "spring", "result": "finish", "time_s": 11823,
     "time_str": "3:17:03"},
    {"slug": "ainsford-marathon-2029-autumn", "date": date(2029, 10, 7),
     "edition": "autumn", "result": "dnf", "partial_km": 30.4,
     "partial_s": 9840},
    {"slug": "ainsford-marathon-2030-spring", "date": date(2030, 4, 7),
     "edition": "spring", "result": "finish", "time_s": 12398,
     "time_str": "3:26:38"},
]
RACE_DATES = {r["date"] for r in RACES}

# 13-week (12 down to 0) long-run ramp used ahead of every race, the same
# shape each time - real training blocks repeat, which is the point of a
# route/plan catalog (WORLD LAYER convention). Week 0 is race week itself:
# a short shakeout, not a long run.
LONG_RUN_KM = {
    12: 14.0, 11: 16.0, 10: 16.0, 9: 19.0, 8: 21.5, 7: 24.0, 6: 21.5,
    5: 27.0, 4: 29.0, 3: 32.0, 2: 21.5, 1: 13.0, 0: 4.8,
}


def _block_long_run_km(d: date) -> float | None:
    """Which race's build-up (if any) this Saturday belongs to, and the
    long-run distance the ramp table assigns it. `None` outside any block."""
    for r in RACES:
        weeks_before = (r["date"] - d).days // 7
        if 0 <= weeks_before <= 12 and week_monday(d) + timedelta(days=5) < r["date"]:
            return LONG_RUN_KM[weeks_before]
    return None


# --- the M2 lie week: 2029-08-06 .. 2029-08-12 --------------------------------
#
# True week: 92 km (21.5 + 14 + 19.0 + 16.0 + 21.5). The 14 km Tuesday run is
# never logged at all (its GPX survives in tracks/). The Thursday 16 km run
# IS logged, then two days later corrected down to 9 km, "mismapped", via
# supersedes. Friday and Saturday are left as rest days on purpose - not
# realism, but to keep the correction's late recorded_at from landing between
# two other dated rows and breaking file-order monotonicity (handbook lesson
# 2). The previous week's true volume was 68 km, the guarded ramp's baseline.
M2_WEEK_MONDAY = date(2029, 8, 6)
M2_OMITTED_DATE = date(2029, 8, 7)          # true 14 km, no sessions row
M2_OMITTED_DURATION_S = 4200                # 70 min
M2_CORRECTED_DATE = date(2029, 8, 9)        # logged 16 km, corrected to 9 km
M2_CORRECTION_RECORDED = date(2029, 8, 11)  # two days later
M2_ACTIVITY_ID = "gar-20290809-6483"

# --- the achilles episode -----------------------------------------------------

ACHILLES_SLUG = "achilles"
ACHILLES_FIRST_SYMPTOM = date(2029, 6, 10)
ACHILLES_OPENED = date(2029, 11, 4)

# The M1 window: daily.pain logged low (0 or 1) while journal, same week,
# describes real trouble. Both athlete-stated; both true accounts of what he
# said, at odds with each other. All fall before the episode formally opens.
M1_DATES = [
    date(2029, 6, 12), date(2029, 6, 24), date(2029, 7, 8),
    date(2029, 7, 28), date(2029, 8, 19), date(2029, 9, 17),
    date(2029, 10, 1), date(2029, 10, 20),
]
M1_JOURNAL_TEXT = {
    date(2029, 6, 12): ("Achilles was barking again on the long hill rep on the canal path, "
                         "didn't say anything, didn't stop."),
    date(2029, 6, 24): ("Hobbling on the stairs before school again this morning. Told Claire "
                         "it was just stiff from sleeping funny."),
    date(2029, 7, 8): "Barking on the hills on the canal loop, same spot every time now.",
    date(2029, 7, 28): ("Even on the flat stuff up here at the cottage it's grumbling a bit. "
                         "Said nothing to Claire."),
    date(2029, 8, 19): ("Properly barking after Saturday's long one. Telling myself it's just "
                         "tightness."),
    date(2029, 9, 17): ("Hobbling on the stairs before school again. Alfie asked why I was "
                         "walking funny. Said I banged my foot on the car."),
    date(2029, 10, 1): ("Right achilles barking on the taper run. Nearly said something to "
                         "Claire. Didn't."),
    date(2029, 10, 20): ("Hobbling properly since the race. Can't pretend it's nothing any "
                          "more, but haven't told anyone officially yet."),
}
M1_PAIN_VALUE = {
    date(2029, 6, 12): 1, date(2029, 6, 24): 0, date(2029, 7, 8): 1,
    date(2029, 7, 28): 0, date(2029, 8, 19): 1, date(2029, 9, 17): 0,
    date(2029, 10, 1): 1, date(2029, 10, 20): 1,
}


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper(base_hour=21)
    daily_stamper = common.Stamper(base_hour=21)
    sessions_stamper = common.Stamper(base_hour=21)
    journal_stamper = common.Stamper(base_hour=22)
    medical_stamper = common.Stamper(base_hour=20)
    checks_stamper = common.Stamper(base_hour=19)
    goals_stamper = common.Stamper(base_hour=20)
    events_stamper = common.Stamper(base_hour=20)
    achievements_stamper = common.Stamper(base_hour=21)

    weight = _weight(rng, weight_stamper, end)
    daily = _daily(rng, daily_stamper, end)
    sessions, tracks = _sessions(rng, sessions_stamper, end)
    journal = _journal(journal_stamper)
    medical = _medical(medical_stamper)
    checks = _checks(checks_stamper)
    goals = _goals(goals_stamper)
    events = _events(events_stamper)
    achievements = _achievements(achievements_stamper)

    expectations = (
        _m1_rows() + _m2_rows() + [_m3_row()] +
        [_e_goal_gap(), _e_medical_laterality_gap(), _e_restriction_behavior(),
         _e_spectator_gap()]
    )

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "data/medical.jsonl": common.jsonl_text(common.sort_rows(medical)),
        "data/checks.jsonl": common.jsonl_text(common.sort_rows(checks)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/events.jsonl": common.jsonl_text(common.sort_rows(events)),
        "data/achievements.jsonl": common.jsonl_text(common.sort_rows(achievements)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
    for rel_path, text in tracks.items():
        files[rel_path] = text
    return files


# --- back-fill: the shared M3 mechanism ---------------------------------------


def _is_backfill_week(wk: date) -> bool:
    """Deterministic per-WEEK coin flip (not per-row), so every dataset -
    weight, daily, sessions - agrees on whether a given week was backfilled.
    A per-row decision would let one day in a week land its recorded_at on
    the week's Sunday while a neighbouring day in the SAME week logs
    same-day, which reintroduces the exact file-order monotonicity trap the
    handbook warns about (lesson 2): the Sunday-stamped row would sort
    before the same-day row by date, but after it in real time."""
    local = random.Random(SEED * 1_000_003 + wk.toordinal())
    return local.random() < 0.70


def _recorded_date_for(d: date) -> date:
    """M3: during term time, about 70% of weeks he does his logging admin
    in one sitting on the Sunday evening, regardless of which day the thing
    actually happened; the rest of term-time weeks, and every holiday week,
    are logged the same evening. Every row this produces is TRUE - only the
    recorded_at is late, never the content (contrast priya's P1, where the
    back-filled rows themselves were phantom)."""
    wk = week_monday(d)
    if _week_is_holiday(wk):
        return d
    if _is_backfill_week(wk):
        return wk + timedelta(days=6)
    return d


# --- weight --------------------------------------------------------------


def _weight(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Twice a week (Monday, Friday), a connected scale. Baseline 78 kg with
    mild seasonal drift; nothing here is a lie, just a body carrying marathon
    training across two and a half years."""
    rows = []
    d = START
    while d.weekday() != 0:
        d += timedelta(days=1)
    total_days = max(1, (end - START).days)
    while d <= end:
        for offset in (0, 4):  # Monday, Friday
            wd = d + timedelta(days=offset)
            if wd > end:
                continue
            frac = (wd - START).days / total_days
            season = 0.6 * (1 if is_holiday(wd) else -0.2)
            kg = round(78.0 - 0.8 * frac + season + rng.gauss(0, 0.5), 1)
            recorded_day = _recorded_date_for(wd)
            fields = {
                "date": wd.isoformat(), "kg": kg, "source": "garmin-scale",
                "origin": "garmin-scale", "capture": "connector",
                "measured_at": f"07:{rng.randrange(0, 40):02d}",
                "recorded_at": stamper.stamp(recorded_day),
            }
            rows.append(common.record("weight", **fields))
        d += timedelta(days=7)
    return rows


# --- daily -----------------------------------------------------------------


def _uk_offset(d: date) -> str:
    """`+01:00` under British Summer Time, `+00:00` otherwise.

    Written out rather than taken from a tz database, because the engine is
    stdlib-only and `zoneinfo` needs system data this build cannot assume. BST
    runs from the last Sunday in March to the last Sunday in October; the
    01:00 UTC changeover instant is not modelled, since no night here starts
    inside that hour.
    """
    def last_sunday(year: int, month: int) -> date:
        d = date(year, month, 31) if month == 3 else date(year, month, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    return ("+01:00" if last_sunday(d.year, 3) <= d < last_sunday(d.year, 10)
            else "+00:00")


def _uk_delta(d: date) -> timedelta:
    return timedelta(hours=1) if _uk_offset(d) == "+01:00" else timedelta(0)


def _sleep_interval(clock: random.Random, d: date,
                    sleep_h: float) -> tuple[str, str]:
    """When the night that ENDED on `d` began and ended.

    DERIVED FROM THE WORK PATTERN, not sampled from nothing. He teaches, so
    the night before a school day is the constrained one: he is up for a
    07:20 start whatever time he got in. The night before a Saturday, a Sunday
    or a school holiday has nothing pulling it forward, and it runs about an
    hour later.

    A SEPARATE CLOCK from the caller's `rng`, deliberately. Drawing these from
    the same generator would shift every subsequent number in the sequence -
    every step count, every sleep duration, three years of them - and the
    whole corpus would change to add a field. The night is a new fact about
    the same days, so it gets its own stream.

    `sleep_end` is `sleep_start` plus the duration already in the row, exactly.
    The interval and the duration are two statements about one night, and a
    fixture whose own two fields disagree teaches a reader to trust neither.
    """
    school_night = d.weekday() < 5 and not is_holiday(d)
    centre = 22.85 if school_night else 23.85
    spread = 0.28 if school_night else 0.55
    start_h = min(max(centre + clock.gauss(0, spread), 21.5), 25.5)
    local = (datetime.combine(d, dtime()) - timedelta(days=1)
             + timedelta(hours=start_h))
    local = local.replace(second=0, microsecond=0, minute=(local.minute // 5) * 5)

    # AWARE ARITHMETIC, and the naive version was wrong on exactly four nights
    # in three years. Adding the duration to a naive clock and stamping each
    # end with its own date's offset made the two fields disagree by an hour
    # across a DST changeover - the interval saying one thing and `sleep_h`
    # another, on the four nights a reader would most want to trust them.
    # Adding to an INSTANT and then expressing the result in the offset in
    # force when he woke keeps them consistent, and the hour really does move
    # on the wall clock, which is a fact about the night rather than an error.
    began = local.replace(tzinfo=timezone(_uk_delta(local.date())))
    instant = began + timedelta(hours=sleep_h)
    ended = instant.astimezone(timezone(_uk_delta(instant.date())))
    return began.isoformat(), ended.isoformat()


def _daily(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Steps and sleep from the watch, most days. The M1 window additionally
    carries a low `pain` scalar on eight specific dates - see M1_DATES."""
    rows = []
    clock = random.Random(SEED + 1)
    for d in common.daterange(START, end):
        base_steps = 13500 if is_holiday(d) else 10500
        steps = max(3000, int(rng.gauss(base_steps, 2200)))
        sleep_h = round(max(4.5, min(9.0, rng.gauss(7.0, 0.8))), 1)
        began, ended = _sleep_interval(clock, d, sleep_h)
        fields = {
            "date": d.isoformat(), "steps": steps, "sleep_h": sleep_h,
            "sleep_start": began, "sleep_end": ended,
            "source": "garmin-watch", "capture": "connector",
            "coverage": "full",
            "recorded_at": stamper.stamp(_recorded_date_for(d)),
        }
        if d in M1_PAIN_VALUE:
            fields.update({
                "pain": M1_PAIN_VALUE[d], "pain_site": "achilles",
                "pain_side": "right",
            })
        rows.append(common.record("daily", **fields))
    return rows


# --- sessions ------------------------------------------------------------------


def _sessions(rng: random.Random, stamper: common.Stamper,
              end: date) -> tuple[list[dict], dict[str, str]]:
    rows: list[dict] = []
    tracks: dict[str, str] = {}

    for d in common.daterange(START, end):
        if week_monday(d) == M2_WEEK_MONDAY:
            continue  # handled separately below
        if d in RACE_DATES:
            rows.append(_race_session(rng, stamper, d))
            continue
        wd = d.weekday()
        active_days = HOLIDAY_DAYS if _week_is_holiday(week_monday(d)) else TERM_DAYS
        if wd not in active_days:
            continue
        if wd == 5:
            long_km = _block_long_run_km(d)
            if long_km is not None:
                rows.append(_long_run(rng, stamper, d, long_km))
            else:
                rows.append(_parkrun(rng, stamper, d))
        elif wd == 1:
            rows.append(_track_session(rng, stamper, d))
        elif wd == 3:
            rows.append(_canal_run(rng, stamper, d))
        elif wd == 0:
            rows.append(_canal_run(rng, stamper, d))
        elif wd == 2:
            rows.append(_park_easy(rng, stamper, d))

    m2_rows, m2_tracks = _m2_week(rng, stamper)
    rows.extend(m2_rows)
    tracks.update(m2_tracks)
    return rows, tracks


def _base_fields(rng: random.Random, stamper: common.Stamper, d: date,
                  distance_km: float, pace_s_per_km: float, route: str,
                  **extra) -> dict:
    duration_s = max(300, int(distance_km * pace_s_per_km + rng.uniform(-60, 60)))
    start_hh = rng.randrange(6, 8) if not is_holiday(d) else rng.randrange(7, 10)
    start_mm = rng.randrange(0, 60)
    start_time = (f"{d.isoformat()}T{start_hh:02d}:{start_mm:02d}:00"
                  f"{_offset(d)}")
    fields = {
        "date": d.isoformat(), "type": "run", "distance_km": round(distance_km, 1),
        "duration_s": duration_s, "source": "garmin-watch",
        "start_time": start_time, "setting": "outdoor", "route": route,
        "place": "home", "context": "solo", "type_source": "device-recorded",
        "capture": "connector",
        "recorded_at": stamper.stamp(_recorded_date_for(d)),
    }
    fields.update(extra)
    return common.record("sessions", **fields)


def _offset(d: date) -> str:
    """British clock offsets: BST late March to late October, else UTC."""
    if date(d.year, 3, 25) <= d <= date(d.year, 10, 25):
        return "+01:00"
    return "+00:00"


def _canal_run(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    return _base_fields(rng, stamper, d, ROUTES["canal"], 300, "canal")


def _park_easy(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    return _base_fields(rng, stamper, d, ROUTES["park"], 320, "park")


def _track_session(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    distance = round(rng.uniform(8.0, 10.0), 1)
    row = _base_fields(rng, stamper, d, distance, 280, "track")
    row["rpe"] = rng.choice([7, 8, 8, 9])
    return row


def _parkrun(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    with_kid = rng.random() < 0.35
    companion = rng.choice(["Alfie", "Rosie"]) if with_kid else None
    note = ("parkrun with Alfie, slow and proud of it" if companion == "Alfie"
            else ("parkrun with Rosie, her fastest yet" if companion == "Rosie" else None))
    extra = {"context": "family" if with_kid else "solo", "with": companion,
             "note": note}
    row = _base_fields(rng, stamper, d, ROUTES["park"], 330, "park", **extra)
    return row


def _long_run(rng: random.Random, stamper: common.Stamper, d: date,
              distance_km: float) -> dict:
    pace = 330 if distance_km >= 20 else 300
    return _base_fields(rng, stamper, d, distance_km, pace, "long")


def _race_session(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    race = next(r for r in RACES if r["date"] == d)
    if race["result"] == "finish":
        distance_km, duration_s = 42.2, race["time_s"]
        note = f"the Ainsford Marathon, {race['edition']} {d.year} - {race['time_str']}"
    else:
        distance_km, duration_s = race["partial_km"], race["partial_s"]
        note = ("the Ainsford Marathon, autumn 2029 - DNF, pulled at the next "
                "marshal point after the right achilles gave way around 30k")
    start_time = f"{d.isoformat()}T09:00:00{_offset(d)}"
    fields = {
        "date": d.isoformat(), "type": "run", "distance_km": distance_km,
        "duration_s": duration_s, "source": "garmin-watch",
        "start_time": start_time, "setting": "outdoor", "route": "long",
        "place": "away", "context": "solo", "weather": rng.choice(["dry", "cold", "wind"]),
        "type_source": "device-recorded", "capture": "connector", "note": note,
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _m2_week(rng: random.Random, stamper: common.Stamper
             ) -> tuple[list[dict], dict[str, str]]:
    """The hidden 92 km week. True total: 21.5 (Mon) + 14 (Tue, omitted) +
    19.0 (Wed) + 16.0->9.0 (Thu, corrected) + 21.5 (Sun) = 92.0. Logged at
    the time (excluding the omission, including Thursday's true 16 km):
    78.0 - the figure the guarded ramp goal actually evaluates against a
    68 km baseline. Friday and Saturday are rest days by construction, so the
    correction's late recorded_at (two days after the original) never lands
    between two other dated rows - see the module docstring on M2 and
    handbook lesson 2."""
    rows: list[dict] = []
    tracks: dict[str, str] = {}
    mon = M2_WEEK_MONDAY

    rows.append(_base_fields(rng, stamper, mon, 21.5, 330, "long"))

    # Tuesday: true, omitted entirely. Only the GPX survives.
    track_rel = "tracks/marcus-2029-08-07-omitted.gpx"
    tracks[track_rel] = common.gpx_text(
        M2_OMITTED_DATE.isoformat(), "06:40", M2_OMITTED_DURATION_S,
        base_lat=53.97, base_lon=-1.08, name="long-loop-extension")

    rows.append(_base_fields(rng, stamper, mon + timedelta(days=2), 19.0, 300, "canal",
                              note="canal loop, extended out and back"))

    # Thursday: logged true (16 km), then corrected false (9 km) two days later.
    original = _base_fields(
        rng, stamper, M2_CORRECTED_DATE, 16.0, 300, "canal",
        note="canal loop, extended out and back",
        activity_id=M2_ACTIVITY_ID, activity_source="garmin-watch",
    )
    rows.append(original)
    correction = common.record(
        "sessions",
        date=M2_CORRECTED_DATE.isoformat(), type="run", distance_km=9.0,
        duration_s=original["duration_s"], source="athlete",
        start_time=original["start_time"], setting="outdoor", route="canal",
        place="home", context="solo", type_source="athlete-stated",
        capture="manual_entry", note="mismapped - just the canal loop, not the extension",
        activity_id=M2_ACTIVITY_ID, activity_source="garmin-watch",
        supersedes=f"{M2_ACTIVITY_ID}@{M2_CORRECTED_DATE.isoformat()}",
        recorded_at=stamper.stamp(M2_CORRECTION_RECORDED),
    )
    rows.append(correction)

    rows.append(_base_fields(rng, stamper, mon + timedelta(days=6), 21.5, 330, "long"))
    return rows, tracks


# --- journal -----------------------------------------------------------------


def _journal(stamper: common.Stamper) -> list[dict]:
    rows = []
    for jd in sorted(M1_JOURNAL_TEXT):
        fields = {
            "date": jd.isoformat(), "kind": "note", "text": M1_JOURNAL_TEXT[jd],
            "about": "achilles", "source": "athlete", "confidence": 0.9,
            "recorded_at": stamper.stamp(jd),
        }
        rows.append(common.record("journal", **fields))
    return rows


# --- medical -----------------------------------------------------------------


def _medical(stamper: common.Stamper) -> list[dict]:
    """One slug, `achilles`, whose whole lifecycle is these dated rows: mild
    symptom notes from June 2029, escalating to a formally opened, active,
    never-resolved episode in November - after the DNF, not before it."""
    rows = []

    def row(d: date, **kw) -> dict:
        base = {
            "date": d.isoformat(), "slug": ACHILLES_SLUG, "body_site": "achilles",
            "provider_type": None, "source": "athlete",
            "recorded_at": stamper.stamp(d),
        }
        base.update(kw)
        return common.record("medical", **base)

    rows.append(row(
        ACHILLES_FIRST_SYMPTOM, kind="symptom", severity="mild", status="monitoring",
        title="Right achilles tightness after the long run",
        note="stiff first thing, eases once warm - not saying anything to Claire yet",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        date(2029, 7, 15), kind="symptom", severity="mild", status="monitoring",
        title="Right achilles, still there",
        note="still niggling on the longer efforts, same spot",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        date(2029, 8, 20), kind="symptom", severity="mild", status="monitoring",
        title="Right achilles, more noticeable",
        note="more noticeable now, even on the easy days",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        date(2029, 9, 10), kind="symptom", severity="mild", status="monitoring",
        title="Right achilles, decided to run through it",
        note="decided to just get through the race and see how it is after",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        ACHILLES_OPENED, kind="injury", severity="moderate", status="active",
        title="Right achilles tendinopathy, ongoing since June, worse since the autumn DNF",
        note="finally admitting this needs managing, not just running through",
        restricts="run impact",
        restriction="pattern=jump region=achilles load=loaded",
        precondition="calf-raise-check",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        date(2030, 1, 15), kind="injury", severity="moderate", status="active",
        title="Right achilles, managing through the base phase",
        note="still there, better on the days he does the garage calf raises",
        restricts="run impact",
        restriction="pattern=jump region=achilles load=loaded",
        precondition="calf-raise-check",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    rows.append(row(
        date(2030, 4, 10), kind="injury", severity="moderate", status="active",
        title="Right achilles, flared during the spring marathon",
        note="flared badly around 30k on the 2030-04-07 race, gutted it through to the finish",
        restricts="run impact",
        restriction="pattern=jump region=achilles load=loaded",
        precondition="calf-raise-check",
        onset_date=ACHILLES_FIRST_SYMPTOM.isoformat(),
    ))
    return rows


# --- checks ------------------------------------------------------------------


def _checks(stamper: common.Stamper) -> list[dict]:
    rows = []
    entries = [
        (date(2029, 11, 20), "fail", 8, "pain past 8 reps on the right, stopped there"),
        (date(2030, 1, 10), "fail", 14,
         "better, but still gives out past 14 on the right, nowhere near matching the left"),
        (date(2030, 3, 1), "pass", 25,
         "25 clean reps each side, pain-free - though the right is noticeably more "
         "tired than the left by the end"),
    ]
    for d, result, value, note in entries:
        fields = {
            "date": d.isoformat(), "slug": "calf-raise-check", "result": result,
            "value": value, "source": "athlete", "note": note,
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("checks", **fields))
    return rows


# --- goals ---------------------------------------------------------------------


def _goals(stamper: common.Stamper) -> list[dict]:
    """Every dated row is a full, self-contained snapshot - policy/period/
    title etc are all required on EVERY line, not only the one that first
    set them (a lesson this generator lost time to: schema.py has no notion
    of a row inheriting fields from an earlier one with the same slug)."""
    rows = []

    # An ATTESTED goal, deliberately - see FINDINGS.md and expectation
    # marcus-E-goal-01: the contribution engine only knows how to ACCUMULATE
    # a metric over a period, and a marathon finish time is a single-event
    # threshold, not a volume to sum. 3:20 and 3:15 are real numbers; they
    # live in the title and rationale, never in a `target` field the engine
    # would try to add training-run durations into.
    time_state: dict = {
        "slug": "marathon-time", "title": "Break 3:20 for the marathon",
        "verification": "attested", "policy": "monotonic", "period": "none",
        "status": "active", "set_by": "athlete",
        "motivator": "Get under 3:20, then think about what's next",
        "rationale": "the number that's felt achievable for two years",
        "event": "ainsford-marathon-2028-spring", "deadline_kind": "hard",
        "on_success": "escalate", "on_miss": "reflect",
    }

    def emit_time(d: date, note: str | None = None,
                  change_kind: str | None = None, **changes) -> dict:
        time_state.update(changes)
        fields = dict(time_state)
        fields.update({
            "date": d.isoformat(), "note": note, "change_kind": change_kind,
            "recorded_at": stamper.stamp(d),
        })
        return common.record("goals", **fields)

    rows.append(emit_time(date(2028, 1, 10)))
    rows.append(emit_time(
        date(2028, 4, 11), change_kind="change",
        rationale="missed by nine minutes in April, no wobble in the plan",
        event="ainsford-marathon-2028-autumn",
    ))
    rows.append(emit_time(
        date(2028, 10, 10), change_kind="change",
        rationale="one minute off in October - the taper needs adjusting, not the target",
        event="ainsford-marathon-2029-spring",
    ))
    rows.append(emit_time(
        date(2029, 4, 9), change_kind="change", status="achieved",
        note="3:17:03 - the 3:20 goal is done",
    ))
    rows.append(emit_time(
        date(2029, 4, 12), change_kind="change", status="active",
        title="Break 3:15 for the marathon",
        motivator="3:17 says 3:15 is in the legs",
        rationale="the next crack is the October one",
        event="ainsford-marathon-2029-autumn",
    ))
    rows.append(emit_time(
        date(2029, 10, 9), change_kind="change", status="active",
        note="DNF in October - not letting go of the number, re-aiming at spring",
        rationale="the achilles picked October to make its point; the target stands",
        event="ainsford-marathon-2030-spring",
    ))
    rows.append(emit_time(
        date(2030, 4, 9), change_kind="change",
        note="3:26:38 - a regression, not a result; still not changing the number",
        rationale="the legs are willing; the tendon isn't voting yet",
    ))

    # The guarded weekly-volume ramp goal: the vehicle for M2. One goal,
    # created ahead of the autumn 2029 block so the guard has a real trailing
    # baseline by the time the hidden overreach week arrives, paused after
    # the DNF, reactivated for the spring 2030 block.
    vol_state: dict = {
        "slug": "weekly-volume",
        "title": "Build weekly volume without breaking anything",
        "metric": "distance_km", "dataset": "sessions", "session_type": "run",
        "policy": "guarded", "guard_pct": 0.10, "period": "weekly",
        "on_period_end": "reset", "set_by": "athlete", "status": "active",
        "target": 95,
        "motivator": "Peak the autumn block without the achilles getting a vote",
        "rationale": "10% a week is the ceiling; go carefully around the achilles",
    }

    def emit_vol(d: date, note: str | None = None,
                 change_kind: str | None = None, **changes) -> dict:
        vol_state.update(changes)
        fields = dict(vol_state)
        fields.update({
            "date": d.isoformat(), "note": note, "change_kind": change_kind,
            "recorded_at": stamper.stamp(d),
        })
        return common.record("goals", **fields)

    rows.append(emit_vol(date(2029, 6, 1)))
    rows.append(emit_vol(
        date(2029, 10, 9), change_kind="change", status="paused",
        note="pausing the ramp after the DNF - the achilles is not a training variable any more",
    ))
    rows.append(emit_vol(
        date(2030, 1, 6), change_kind="change", status="active", target=90,
        note="restarting the ramp, lower ceiling, for the spring block",
        rationale="not chasing the same peak week again",
    ))
    return rows


# --- events ----------------------------------------------------------------


def _events(stamper: common.Stamper) -> list[dict]:
    rows = []
    for r in RACES:
        entry_date = r["date"] - timedelta(days=100)
        fields = {
            "date": entry_date.isoformat(), "slug": r["slug"],
            "title": f"The Ainsford Marathon, {r['edition']} {r['date'].year}",
            "kind": "competition", "event_date": r["date"].isoformat(),
            "priority": "a", "immovable": True, "place": "a cathedral city",
            "status": "confirmed", "set_by": "athlete",
            "recorded_at": stamper.stamp(entry_date),
        }
        rows.append(common.record("events", **fields))
    return rows


# --- achievements ------------------------------------------------------------


def _achievements(stamper: common.Stamper) -> list[dict]:
    rows = []
    fields1 = {
        "date": "2029-03-05", "title": "First sub-40 10k",
        "occurred_date": "2029-03-04", "source": "athlete",
        "note": "10k time trial on the track, 39:42",
        "recorded_at": stamper.stamp(date(2029, 3, 5)),
    }
    rows.append(common.record("achievements", **fields1))
    fields2 = {
        "date": "2029-04-09", "title": "Marathon PB, 3:17:03",
        "goal": "marathon-time", "occurred_date": "2029-04-08",
        "source": "athlete", "note": "the Ainsford Marathon, spring 2029",
        "recorded_at": stamper.stamp(date(2029, 4, 9)),
    }
    rows.append(common.record("achievements", **fields2))
    return rows


# --- expectations --------------------------------------------------------------


def _m1_rows() -> list[dict]:
    rows = []
    for idx, d in enumerate(M1_DATES, start=1):
        rows.append({
            "id": f"marcus-E-M1-{idx:02d}", "kind": "lie", "dataset": "daily",
            "dates": [d.isoformat()],
            "claim": (
                f"daily.pain reads {M1_PAIN_VALUE[d]} (site achilles, side "
                f"right) on {d.isoformat()}"
            ),
            "truth": (
                "the same week's journal entry, athlete-stated exactly like "
                f"the pain scalar, says: \"{M1_JOURNAL_TEXT[d]}\" - ground "
                "truth pain that week ran 4-6 on a 0-10 scale, not 0-1; both "
                "the scalar and the prose are what he actually said, and "
                "they disagree with each other"
            ),
            "expect": (
                "before the achilles episode exists in medical.jsonl (it "
                "opens 2029-11-04), the engine has nothing to gate on. The "
                "contradiction between a low daily.pain scalar and a "
                "same-week journal note describing real trouble is an "
                "observation about the record - both rows are athlete-"
                "stated, neither outranks the other, and the engine must "
                "not average them into a single number or infer what the "
                "pain 'really' was. Once the episode opens, the medical "
                "gate applies to what is programmed next; it does not "
                "retroactively resolve what these two rows say"
            ),
            "gap": (
                "no check today reads a daily.pain value against the same "
                "week's journal text at all; the contradiction is visible "
                "only by reading two datasets side by side, exactly as in "
                "derek's D1"
            ),
        })
    return rows


def _m2_rows() -> list[dict]:
    return [
        {
            "id": "marcus-E-M2-01", "kind": "lie", "dataset": "sessions",
            "dates": [d.isoformat() for d in common.daterange(
                M2_WEEK_MONDAY, M2_WEEK_MONDAY + timedelta(days=6))],
            "claim": (
                "the week of 2029-08-06..12 shows 78.0 km logged against "
                "the weekly-volume goal (guard_pct 0.10, prior week's true "
                "baseline 68 km)"
            ),
            "truth": (
                "true volume that week was 92.0 km; a 14 km run on "
                "2029-08-07 was never entered as a sessions row at all "
                "(its GPX survives at tracks/marcus-2029-08-07-omitted.gpx, "
                "referenced here and in LIES.md)"
            ),
            "expect": (
                "the guarded weekly-volume goal evaluates only what the "
                "record contains. Against 78 km and a recent baseline near "
                "68 km the guard correctly stays quiet or credits only the "
                "budgeted share (class a: a statement about the engine's "
                "own inputs) - it cannot see a run that was never logged, "
                "and that is the guard being defeated by its input, not a "
                "failure of the guard itself"
            ),
            "gap": ("none - this is the guard behaving exactly as it should on the data it was "
                    "given"),
        },
        {
            "id": "marcus-E-M2-02", "kind": "lie", "dataset": "sessions",
            "dates": [M2_CORRECTED_DATE.isoformat(), M2_CORRECTION_RECORDED.isoformat()],
            "claim": (
                "the 2029-08-09 run resolves to 9.0 km, source athlete, "
                "reason 'mismapped', superseding the original device row"
            ),
            "truth": (
                "the original, device-recorded row was true: 16.0 km. The "
                "correction, entered two days later, is false - nothing "
                "was mismapped"
            ),
            "expect": (
                "supersedes is append-only-sacred: for any current-state "
                "read the engine takes the correcting row at face value "
                "(class a), and the superseded original stays in the file, "
                "quotable in full. Nothing here gives the engine a way to "
                "doubt a correction it has no independent evidence against"
            ),
            "gap": "none for this row alone - see marcus-E-M2-03 for the pattern across both edits",
        },
        {
            "id": "marcus-E-M2-03", "kind": "gap", "dataset": "sessions",
            "dates": [M2_CORRECTED_DATE.isoformat(), M2_CORRECTION_RECORDED.isoformat()],
            "claim": (
                "in one week, an entire run is omitted AND a separate run "
                "is corrected downward two days after the fact, both "
                "during an active guarded-ramp goal"
            ),
            "truth": (
                "both edits point the same direction: hiding volume during "
                "exactly the week a ramp guard would matter most"
            ),
            "expect": (
                "no existing check flags a downward-correcting supersedes "
                "landing during an active guarded goal as a pattern worth a "
                "second look; this is the same shape as tom's T3 (a "
                "correction at a trend inflection is auditable) applied to "
                "a volume ramp instead of a weight trend, and is why the "
                "two are paired in FINDINGS"
            ),
            "gap": (
                "correction-provenance auditing for guarded goals does not "
                "exist today; pairs with tom T3"
            ),
        },
    ]


def _m3_row() -> dict:
    return {
        "id": "marcus-E-M3", "kind": "behavior", "dataset": "sessions",
        "dates": [START.isoformat(), DEFAULT_END.isoformat()],
        "claim": (
            "roughly 70% of term-time sessions/daily/weight rows carry a "
            "recorded_at on the Sunday evening of their week, regardless "
            "of which weekday the thing actually happened on"
        ),
        "truth": (
            "every one of these rows is true. He does his logging admin in "
            "one Sunday-evening sitting during school terms and logs the "
            "same evening during holidays; only the timing is late, never "
            "the content"
        ),
        "expect": (
            "a recorded_at cluster on one weekday is, by itself, only an "
            "observation about when data enters the record, never evidence "
            "of falsification. Contrast marcus's true back-fill here with "
            "priya's phantom one (P1): the identical fingerprint sits on "
            "opposite ground truth, which is exactly why any future "
            "back-fill heuristic must stay an observation and never become "
            "an accusation"
        ),
        "gap": (
            "no back-fill detector exists today; if one is built, the "
            "priya-P1/marcus-M3 pair is the fixture that keeps it honest"
        ),
    }


def _e_goal_gap() -> dict:
    return {
        "id": "marcus-E-goal-01", "kind": "gap", "dataset": "goals",
        "dates": ["2028-01-10"],
        "claim": (
            "the marathon-time goal is authored with verification=attested "
            "and no metric, target, dataset or session_type, even though "
            "3:20 and then 3:15 are exact, well-defined numbers"
        ),
        "truth": (
            "the numbers are real; they live only in the title and "
            "rationale text"
        ),
        "expect": (
            "no engine behaviour is asked of this row beyond holding it as "
            "the athlete's stated aim (class a)"
        ),
        "gap": (
            "contributions.py's own contribution model only accumulates a "
            "metric across a period (MONOTONIC: more always counts; "
            "GUARDED: a ramp ceiling) - it has no goal KIND for a "
            "single-event performance threshold. Had this goal been "
            "authored as measured with metric=duration_s, every training "
            "run's duration would sum into the same bucket as a marathon "
            "finish time, which is meaningless; contributions.py names the "
            "missing piece itself, as 'goal KINDS of G62 (quantity | skill "
            "| maintenance)' - a threshold/skill goal needs its own "
            "contribution model, distinct from the volume accumulator this "
            "file implements today"
        ),
    }


def _e_medical_laterality_gap() -> dict:
    return {
        "id": "marcus-E-medical-laterality", "kind": "gap", "dataset": "medical",
        "dates": [ACHILLES_FIRST_SYMPTOM.isoformat()],
        "claim": "every achilles medical.jsonl row names body_site=achilles with no side field",
        "truth": ("it is consistently the right achilles throughout, stated only in title and "
                  "note prose"),
        "expect": (
            "the engine should read body_site as which structure, and must "
            "not invent a side where none is recorded"
        ),
        "gap": (
            "medical.jsonl has no laterality axis; daily.pain_side is a "
            "structured field for exactly this question on the exact same "
            "paired site, but medical carries no equivalent - the side "
            "survives only as prose"
        ),
    }


def _e_restriction_behavior() -> dict:
    return {
        "id": "marcus-E-restriction", "kind": "behavior", "dataset": "sessions",
        "dates": [ACHILLES_OPENED.isoformat(), date(2030, 4, 7).isoformat()],
        "claim": (
            "the achilles restriction (pattern=jump region=achilles "
            "load=loaded) stands from 2029-11-04 onward, athlete-stated, "
            "never lifted"
        ),
        "truth": (
            "he ran the 2030-04-07 marathon anyway - 42.2 km of impact "
            "loading, five months after the restriction was recorded. This "
            "is a real, voluntary choice he made; nothing in this record "
            "shows the engine recommending, scheduling, or being asked "
            "about that race"
        ),
        "expect": (
            "the engine's self-constraint is scoped to what IT programs. "
            "It correctly never issues or suggests impact training against "
            "an open restriction, and this record shows exactly that "
            "boundary holding; the athlete's own decision to race anyway "
            "is outside anything the gate is responsible for, and the gate "
            "should keep withholding its own output regardless of what he "
            "actually does elsewhere"
        ),
        "gap": (
            "none - recorded to show the boundary is scoped to what vitai "
            "programs, not to what the athlete does, which a corpus that "
            "only shows a restriction being respected could never test"
        ),
    }


def _e_spectator_gap() -> dict:
    return {
        "id": "marcus-E-spectator", "kind": "gap", "dataset": "sessions",
        "dates": ["2029-04-08", "2029-10-07"],
        "claim": (
            "sessions.context can read 'family' when a child runs "
            "alongside him (with=Alfie or with=Rosie at parkrun), but has "
            "no value for a child watching a race he runs alone"
        ),
        "truth": (
            "in this world, Claire and the kids came to watch both the "
            "2029-04 PB and the 2029-10 DNF; which child stood where has "
            "no schema home at all"
        ),
        "expect": "nothing to observe or withhold here; recorded as a schema-gap illustration only",
        "gap": (
            "'with' describes co-participation, not spectatorship; a race "
            "day's own session row cannot express who came to watch, which "
            "is exactly the metric he named unprompted in sweep 3 ('did "
            "the kids come and watch, and which one')"
        ),
    }


_TOML = """# marcus: synthetic persona corpus, thresholds tuned to his record.
[targets]
phases = [[79.0, 76.0, 0.2]]

[tripwires]
easy_hr_cap = 158
steps_floor = 8000
sleep_floor_h = 6.5
pain_gate = 3

# Every source that appears anywhere in this record is listed here. Once
# [resolution] exists at all, an unlisted source is a hard validate failure,
# not a warning (handbook pitfall 4).
[resolution]
source_order = ["garmin-watch", "garmin-scale", "athlete"]

[resolution.precedence]
kg = ["garmin-scale"]
steps = ["garmin-watch"]
sleep_h = ["garmin-watch"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
