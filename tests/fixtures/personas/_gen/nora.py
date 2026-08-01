"""Generator for the nora persona (seed 104).

Aarhus, Denmark. 27, age-group triathlete, AGF-Tri club. The record runs
three years (2027-07-01 to 2030-06-30): a year of ascent, a peak with
several personal bests, then eighteen months of quiet regression that the
record only shows in arithmetic, never in a word. See PROFILE.md, LIES.md,
METRICS.md, FINDINGS.md and WORLD.md alongside this file for the prose this
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
string this generator writes, and this persona is its hardest case in the
whole corpus. Two different things happen to her body over these three
years. One of them - a foot stress reaction - is diagnosed at a clinic and
is perfectly nameable in the record, because it is what a clinician told
her: that is ordinary logging, not a boundary problem. The other one she
never names, not once, not to a coach, not to herself in a private journal
line. Nothing in this file, in the data it writes, or in the prose docs
beside it ever writes that second word. The only trace it leaves in the
record is a single journal line with no noun in it at all, and the correct
engine behaviour is to hold that line exactly as unresolved as she left it:
never interpreted, never upgraded, never connected to anything else in the
record. That is deliberate and it is the sharpest fixture here.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 104
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# --- the record's own calendar (prose facts, not derived from --end) ---------

START = date(2027, 7, 1)
DEFAULT_END = date(2030, 6, 30)

ASCEND_END = date(2028, 6, 30)          # yr1: ascend
PEAK_END = date(2028, 12, 31)           # yr2 first half: peak
DECLINE_START = date(2029, 1, 1)        # 18 months of quiet regression from here
GEN2_FROM = date(2028, 7, 1)            # sessions.jsonl migrates founding shape -> full provenance

BREAKUP_DATE = date(2029, 3, 15)        # Emil stops appearing in `with`; never written as a
# breakup anywhere

LIE1_FROM = date(2028, 10, 1)           # N1: ground truth starts diverging from the logged
# figure here
GHOST_START = date(2029, 11, 1)         # N2 window
GHOST_END = date(2030, 1, 31)
GHOST_COUNT = 14

INJURY_ENTRY_DATE = date(2030, 2, 6)    # medical row date: the clinic visit
INJURY_ONSET = date(2030, 1, 20)        # onset_date: when the ache actually started
NO_RUN_UNTIL = date(2030, 3, 15)        # complete run rest
RUN_TEST_UNTIL = date(2030, 4, 15)      # short return-to-run test jogs only
MONITORING_DATE = date(2030, 4, 20)     # medical status active -> monitoring
RECOVERY_START = date(2030, 4, 16)

MALLORCA_2028 = (date(2028, 3, 3), date(2028, 3, 10))
MALLORCA_2029 = (date(2029, 3, 2), date(2029, 3, 9))
# No 2030 camp row anywhere in context.jsonl. That absence is the point
# (see FINDINGS.md and expectation nora-E5): the record shows two camps and
# then simply does not show a third one, and nothing built today reads a
# missing recurring fixture as worth a flag.

NEVER_NAMED_DATE = date(2029, 12, 15)   # the sharpest fixture in the corpus

PB_RACE = date(2028, 6, 18)
FTP_TEST_DATE = date(2028, 7, 5)
OPENWATER_RACE = date(2028, 8, 15)
QUALIFIER_RACE = date(2029, 5, 19)
WORLDS_EVENT = date(2030, 9, 14)        # a future fixture, outside the record's own span

# WORLD.md route catalog (run routes only; bike and swim use plain places -
# a named loop catalog for every sport would be more scaffolding than the
# story needs, and only the run routes carry narrative weight here).
ROUTES = {"forest": 5.2, "coast": 10.4}

GOAL_SLUG_QUALIFYING = "70-3-qualifying-slot"
GOAL_SLUG_FTP = "ftp-target"
GOAL_SLUG_PACE = "threshold-pace-target"
GOAL_SLUG_VOLUME = "weekly-training-volume"


def danish_offset(d: date) -> str:
    """UTC offset for Denmark, kept as simple as `common.irish_offset`:
    Central European Summer Time runs from the last Sunday of March to the
    last Sunday of October; this approximates that window with fixed
    calendar dates (25 March to 25 October) rather than the exact Sunday,
    which is accurate enough for a synthetic record. Winter is +01:00,
    summer +02:00 - the reverse of Ireland's +00:00/+01:00, and the reason
    this persona needs its own offset function rather than reusing the
    shared one."""
    if date(d.year, 3, 25) <= d <= date(d.year, 10, 25):
        return "+02:00"
    return "+01:00"


def fitness_frac(d: date) -> float:
    """A single number in (0, 1] standing in for "how well today's training
    is converting into output", used to derive pace, speed and heart-rate
    drift so every sport fades together rather than independently. It rises
    through the ascend year, plateaus across the peak, then declines for
    the rest of the record - never derived from `--end`, because the arc is
    a fixed fact about her three years, not a window that moves.
    """
    if d <= ASCEND_END:
        span = (ASCEND_END - START).days
        return 0.35 + 0.65 * ((d - START).days / span)
    if d <= PEAK_END:
        return 1.0
    span2 = (DEFAULT_END - PEAK_END).days
    frac = (d - PEAK_END).days / span2
    return max(0.15, 1.0 - 0.85 * frac)


def run_pace_min_km(d: date, rng: random.Random) -> float:
    """Minutes per kilometre at her steady aerobic effort. The heart rate
    that produces this pace stays roughly flat across the whole record
    (see `run_hr`); the pace fading while the effort does not is the
    fingerprint the decline leaves in sessions.jsonl."""
    base = 6.0 - 1.2 * fitness_frac(d)
    if d >= RECOVERY_START:
        recov_frac = min(1.0, (d - RECOVERY_START).days / 60)
        base += (1.0 - recov_frac) * 0.9
    return round(base + rng.uniform(-0.15, 0.15), 2)


def bike_speed_kmh(d: date, rng: random.Random, kind: str) -> float:
    if kind == "commute":
        return round(19.0 + rng.uniform(-1.5, 1.5), 1)
    base = 22.0 + 10.0 * fitness_frac(d)
    return round(base + rng.uniform(-1.2, 1.2), 1)


def swim_pace_min100(d: date, rng: random.Random) -> float:
    base = 1.95 - 0.28 * fitness_frac(d)
    return base + rng.uniform(-0.05, 0.05)


def run_hr(rng: random.Random) -> int:
    return round(150 + rng.uniform(-6, 6))


def bike_hr(rng: random.Random) -> int:
    return round(139 + rng.uniform(-7, 7))


def swim_hr(rng: random.Random) -> int:
    return round(131 + rng.uniform(-6, 6))


class _IdCounter:
    """Deterministic, collision-free activity ids: a Strava/Garmin-shaped
    opaque string, never coerced to a number, built from the date plus a
    running index rather than drawn from the RNG (which would risk a
    collision across 1000+ rows for no benefit)."""

    def __init__(self) -> None:
        self._n = 0

    def next(self, d: date) -> str:
        self._n += 1
        return f"{d.strftime('%Y%m%d')}{self._n:05d}"


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper(offset=danish_offset)
    daily_stamper = common.Stamper(offset=danish_offset)
    sessions_stamper = common.Stamper(offset=danish_offset)
    medical_stamper = common.Stamper(offset=danish_offset)
    checks_stamper = common.Stamper(offset=danish_offset)
    goals_stamper = common.Stamper(offset=danish_offset)
    achievements_stamper = common.Stamper(offset=danish_offset)
    events_stamper = common.Stamper(offset=danish_offset)
    journal_stamper = common.Stamper(offset=danish_offset)
    context_stamper = common.Stamper(offset=danish_offset)

    weight = _weight(rng, weight_stamper, end)
    sessions, tracks, sess_stats = _sessions(rng, sessions_stamper, end)
    daily = _daily(rng, daily_stamper, end, sess_stats["kcal_by_date"])
    medical, check_dates = _medical(medical_stamper)
    checks = _checks(checks_stamper)
    goals = _goals(goals_stamper)
    achievements = _achievements(achievements_stamper)
    events = _events(events_stamper)
    journal = _journal(journal_stamper)
    context = _context(context_stamper)

    expectations = [
        _e1_intake(sess_stats),
        _e2_ghost_sessions(sess_stats),
        _e3_never_named(),
        _e4_metatarsal(),
        _e5_camp_gap(),
        _e6_goal_schema_gap(),
        _e7_generation_migration(),
        _e8_emil_disappearance(sess_stats),
    ]

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/medical.jsonl": common.jsonl_text(common.sort_rows(medical)),
        "data/checks.jsonl": common.jsonl_text(common.sort_rows(checks)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/achievements.jsonl": common.jsonl_text(common.sort_rows(achievements)),
        "data/events.jsonl": common.jsonl_text(common.sort_rows(events)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "data/context.jsonl": common.jsonl_text(common.sort_rows(context)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
    for rel_path, text in tracks.items():
        files[rel_path] = text
    return files


# --- weight ------------------------------------------------------------------


def _weight(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Daily, from a connected scale. Rises gently across the ascend year
    (55.5 -> 58.0 kg, the ordinary weight of building training-year
    conditioning), holds at the peak, then slides 58.0 -> 51.0 kg across the
    eighteen-month decline (DECLINE_START to the record's end)."""
    rows = []
    for d in common.daterange(START, end):
        if d < date(2028, 10, 1):
            span = (date(2028, 10, 1) - START).days
            base = 55.5 + 2.5 * ((d - START).days / span)
        elif d < DECLINE_START:
            base = 58.0
        else:
            span = (end - DECLINE_START).days
            frac = min(1.0, (d - DECLINE_START).days / span) if span else 1.0
            base = 58.0 - 7.0 * frac
        kg = round(base + rng.gauss(0, 0.35), 1)
        fields = {
            "date": d.isoformat(), "kg": kg, "source": "withings-scale",
            "origin": "withings-scale", "capture": "connector",
            "measured_at": f"07:{rng.randrange(0, 40):02d}",
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("weight", **fields))
    return rows


# --- sessions ------------------------------------------------------------------


def _sessions(rng: random.Random, stamper: common.Stamper,
              end: date) -> tuple[list[dict], dict[str, str], dict]:
    """~8-10 swim/bike/run sessions a week, watch-connector. Rows before
    GEN2_FROM carry only the founding key set (no provenance/context
    fields, `_gen` = 1); rows from GEN2_FROM onward carry the full current
    shape, exactly the shift `examples/generate_demo.py` models for its own
    weight rows, applied here to sessions across a much longer record."""
    ids = _IdCounter()
    rows: list[dict] = []
    tracks: dict[str, str] = {}
    kcal_by_date: dict[str, int] = {}
    emil_last_date: date | None = None
    signature_dates: dict[str, date] = {}

    for d in common.daterange(START, end):
        emil_active = d < BREAKUP_DATE
        for slot in _day_slots(d, rng, emil_active):
            if emil_active and slot.get("with") == "Emil":
                emil_last_date = d
            row = _slot_to_row(d, slot, rng, stamper, ids)
            rows.append(row)
            kcal_by_date[d.isoformat()] = kcal_by_date.get(d.isoformat(), 0) + (row["kcal"] or 0)

            # One weekly-loop GPX per signature route (forest, coast,
            # track), attached the first time that route appears with a
            # full gen-2+ shape (route/start_time both populated).
            key = slot.get("signature")
            if key and d >= GEN2_FROM and key not in signature_dates:
                signature_dates[key] = d
                track_rel = f"tracks/nora-weekly-{key}-{d.isoformat()}.gpx"
                row["track"] = track_rel
                tracks[track_rel] = common.gpx_text(
                    d.isoformat(), row["start_time"][11:16], row["duration_s"],
                    base_lat=56.15 + 0.01 * len(key), base_lon=10.20 - 0.01 * len(key),
                    name=key)

    # Race day: three legs for each of the three signature races, so the
    # achievements and events have a session to point at. The PB run leg
    # carries the one race GPX in the corpus.
    for race_date, race_name, distances in (
        (PB_RACE, "olympic-distance-pb-race", (1.5, 40.0, 10.0)),
        (OPENWATER_RACE, "open-water-1500-race", (1.5,)),
        (QUALIFIER_RACE, "70-3-qualifier-race", (1.9, 90.0, 21.1)),
    ):
        for row, track_rel, track_text in _race_legs(
                race_date, race_name, distances, rng, stamper, ids):
            rows.append(row)
            kcal_by_date[race_date.isoformat()] = (
                kcal_by_date.get(race_date.isoformat(), 0) + (row["kcal"] or 0))
            if track_rel:
                tracks[track_rel] = track_text

    ghost_runs = _ghost_runs(rng)

    stats = {
        "kcal_by_date": kcal_by_date,
        "ghost_runs": ghost_runs,
        "emil_last_date": emil_last_date,
        "signature_dates": signature_dates,
    }
    return rows, tracks, stats


def _day_slots(d: date, rng: random.Random, emil_active: bool) -> list[dict]:
    """Every session slot for one calendar day, as plain descriptive dicts
    (not yet schema rows). Density and composition shift with
    `fitness_frac` and with the three run-restriction windows around the
    2030 foot injury."""
    wd = d.weekday()
    ff = fitness_frac(d)
    no_run_at_all = NO_RUN_UNTIL <= d <= (RUN_TEST_UNTIL - timedelta(days=1))
    test_run_window = NO_RUN_UNTIL <= d <= RUN_TEST_UNTIL
    run_ok = d < NO_RUN_UNTIL or d > RUN_TEST_UNTIL

    slots: list[dict] = []

    if wd in (0, 3):  # club pool, Monday and Thursday, 06:00
        slots.append(_swim_slot(d, rng, kind="club", emil_active=False))

    commute_prob = 0.5 + 0.35 * ff
    if wd in (0, 1, 2, 3, 4) and rng.random() < commute_prob:
        slots.append(_bike_slot(d, rng, kind="commute", emil_active=False))

    if wd == 1:  # Tuesday: track intervals
        if run_ok:
            slots.append(_run_slot(d, rng, route="track", emil_active=False))
        elif test_run_window and rng.random() < 0.3:
            slots.append(_test_run_slot(d, rng))

    if wd == 3 and ff > 0.5 and run_ok and rng.random() < 0.7:
        slots.append(_run_slot(d, rng, route="forest", emil_active=False))

    if wd == 5:  # Saturday long ride
        slots.append(_bike_slot(d, rng, kind="long", emil_active=emil_active))

    if wd == 6:  # Sunday long run, or a substitute while running is off
        if run_ok:
            slots.append(_run_slot(d, rng, route="coast", emil_active=emil_active, long=True))
        elif test_run_window and rng.random() < 0.4:
            slots.append(_test_run_slot(d, rng))
        else:
            kind = "harbour" if d.month in (6, 7, 8) else "club"
            slots.append(_swim_slot(d, rng, kind=kind, emil_active=emil_active))

    if wd == 2 and d.month in (6, 7, 8) and rng.random() < 0.6:
        slots.append(_swim_slot(d, rng, kind="harbour", emil_active=False))

    if no_run_at_all and not slots:
        # A short recovery spin so an acute rest week is not a total blank.
        if wd in (2, 4) and rng.random() < 0.4:
            slots.append(_bike_slot(d, rng, kind="commute", emil_active=False))

    return slots


def _swim_slot(d: date, rng: random.Random, kind: str, emil_active: bool) -> dict:
    pace = swim_pace_min100(d, rng)
    if kind == "club":
        distance_km = round(rng.uniform(2.5, 3.5), 2)
        place, context, setting = "AGF-Tri club pool", "club", "indoor"
        with_person = rng.choice(["Freja", "Lasse", None, None])
        start_hour, start_min = 6, 0
        weather = None
    elif kind == "harbour":
        distance_km = round(rng.uniform(1.5, 2.5), 2)
        place, setting = "the harbour", "outdoor"
        with_person = "Emil" if emil_active and rng.random() < 0.6 else (
            rng.choice(["Freja", "Lasse", None]) if not emil_active else None)
        if with_person in ("Freja", "Lasse"):
            context = "club"
        elif with_person == "Emil":
            context = "social"
        else:
            context = "solo"
        start_hour, start_min = 18, rng.randrange(0, 30)
        weather = rng.choice(["dry", "hot", "wind"])
    else:
        distance_km = round(rng.uniform(2.0, 3.0), 2)
        place, context, setting = "AGF-Tri club pool", "solo", "indoor"
        with_person = None
        start_hour, start_min = 9, rng.randrange(0, 30)
        weather = None
    duration_s = round(distance_km * 10 * pace * 60)
    return {
        "type": "swim", "distance_km": distance_km, "duration_s": duration_s,
        "avg_hr": swim_hr(rng), "max_hr": swim_hr(rng) + 12, "cadence": None,
        "rpe": rng.choice([3, 4, 4, 5]), "setting": setting, "route": None,
        "place": place, "context": context, "with": with_person,
        "weather": weather, "elevation_m": None, "note": None,
        "start_hour": start_hour, "start_min": start_min,
        "kcal_per_min": 8,
    }


def _bike_slot(d: date, rng: random.Random, kind: str, emil_active: bool) -> dict:
    speed = bike_speed_kmh(d, rng, kind)
    if kind == "commute":
        distance_km = round(rng.uniform(8.0, 13.0), 1)
        place, context, setting = "commute", "commute", "outdoor"
        with_person = None
        start_hour, start_min = 7, rng.randrange(15, 45)
        weather = rng.choice(["dry", "dry", "cold", "rain", "wind"])
        elevation_m = round(rng.uniform(2, 10), 1)
    else:
        distance_km = round(45.0 + 35.0 * fitness_frac(d) + rng.uniform(-6, 6), 1)
        place, context, setting = "the coast road", "solo", "outdoor"
        with_person = "Emil" if emil_active and rng.random() < 0.6 else (
            rng.choice(["Freja", "Lasse", None, None]) if not emil_active else None)
        if with_person in ("Freja", "Lasse"):
            context = "club"
        elif with_person == "Emil":
            context = "social"
        start_hour, start_min = 8, rng.randrange(0, 30)
        weather = rng.choice(["dry", "dry", "cold", "rain", "wind"])
        elevation_m = round(rng.uniform(80, 260), 1)
    duration_s = round(distance_km / speed * 3600)
    return {
        "type": "cycle", "distance_km": distance_km, "duration_s": duration_s,
        "avg_hr": bike_hr(rng), "max_hr": bike_hr(rng) + 18,
        "cadence": round(85 + rng.uniform(-5, 5)),
        "rpe": rng.choice([3, 4, 5, 6]), "setting": setting, "route": None,
        "place": place, "context": context, "with": with_person,
        "weather": weather, "elevation_m": elevation_m, "note": None,
        "start_hour": start_hour, "start_min": start_min,
        "kcal_per_min": 9,
    }


def _run_slot(d: date, rng: random.Random, route: str, emil_active: bool,
              long: bool = False) -> dict:
    pace = run_pace_min_km(d, rng)
    signature = None
    if route == "track":
        distance_km = round(rng.uniform(6.0, 9.0), 1)
        place, elevation_m = "the stadium track", 0.0
        with_person = rng.choice(["Freja", "Lasse", None])
        context = "club"
        signature = "track"
    elif route == "forest":
        distance_km = ROUTES["forest"]
        place, elevation_m = "the forest loop", 35.0
        with_person = None
        context = "solo"
        signature = "forest"
    else:  # coast, the Sunday long run
        laps = 2 if fitness_frac(d) > 0.6 else 1
        distance_km = round(ROUTES["coast"] * laps, 1)
        place, elevation_m = "the coast loop", 6.0
        with_person = "Emil" if emil_active and rng.random() < 0.7 else (
            rng.choice(["Freja", "Lasse", None, None]) if not emil_active else None)
        if with_person in ("Freja", "Lasse"):
            context = "club"
        elif with_person == "Emil":
            context = "social"
        else:
            context = "solo"
        signature = "coast"
    duration_s = round(distance_km * pace * 60)
    return {
        "type": "run", "distance_km": distance_km, "duration_s": duration_s,
        "avg_hr": run_hr(rng), "max_hr": run_hr(rng) + 16,
        "cadence": round(172 + rng.uniform(-4, 4)),
        "rpe": rng.choice([4, 5, 5, 6, 7] if long else [3, 4, 4, 5]),
        "setting": "outdoor", "route": route, "place": place, "context": context,
        "with": with_person, "weather": rng.choice(["dry", "dry", "cold", "rain", "wind"]),
        "elevation_m": elevation_m, "note": None,
        "start_hour": 8 if wd_is_weekend(d) else 17,
        "start_min": rng.randrange(0, 45),
        "kcal_per_min": 11, "signature": signature,
    }


def wd_is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _test_run_slot(d: date, rng: random.Random) -> dict:
    """A short, deliberately easy return-to-run test jog during the
    RUN_TEST_UNTIL window: low distance, low effort, timed to the checks
    that gate her return."""
    distance_km = round(rng.uniform(1.5, 3.0), 1)
    pace = 6.5 + rng.uniform(-0.2, 0.2)
    duration_s = round(distance_km * pace * 60)
    return {
        "type": "run", "distance_km": distance_km, "duration_s": duration_s,
        "avg_hr": round(135 + rng.uniform(-5, 5)), "max_hr": round(150 + rng.uniform(-5, 5)),
        "cadence": round(168 + rng.uniform(-4, 4)), "rpe": rng.choice([2, 3]),
        "setting": "outdoor", "route": "forest", "place": "the forest loop",
        "context": "solo", "with": None, "weather": rng.choice(["dry", "cold"]),
        "elevation_m": 10.0, "note": "return-to-run test jog, easy pace only",
        "start_hour": 9, "start_min": rng.randrange(0, 30),
        "kcal_per_min": 10,
    }


def _slot_to_row(d: date, slot: dict, rng: random.Random,
                  stamper: common.Stamper, ids: _IdCounter) -> dict:
    duration_s = slot["duration_s"]
    kcal = round(duration_s / 60 * slot["kcal_per_min"])
    start_time = (f"{d.isoformat()}T{slot['start_hour']:02d}:"
                  f"{slot['start_min']:02d}:00{danish_offset(d)}")
    base = {
        "date": d.isoformat(), "type": slot["type"], "distance_km": slot["distance_km"],
        "duration_s": duration_s, "avg_hr": slot["avg_hr"], "max_hr": slot["max_hr"],
        "cadence": slot["cadence"], "kcal": kcal, "rpe": slot["rpe"],
        "note": slot["note"], "source": "garmin-watch", "start_time": start_time,
        "elevation_m": slot["elevation_m"], "recorded_at": stamper.stamp(d),
    }
    if d < GEN2_FROM:
        base["_gen"] = 1
        return common.record("sessions", **base)
    activity_id = ids.next(d)
    base.update({
        "setting": slot["setting"], "route": slot["route"], "place": slot["place"],
        "with": slot["with"], "context": slot["context"], "weather": slot["weather"],
        "origin": "garmin-watch", "path": "garmin-watch>garmin-connect",
        "capture": "connector", "type_source": "device-recorded",
        "activity_id": activity_id, "activity_source": "garmin-connect",
    })
    return common.record("sessions", **base)


def _race_legs(race_date: date, race_name: str, distances: tuple[float, ...],
               rng: random.Random, stamper: common.Stamper, ids: _IdCounter,
               ) -> list[tuple[dict, str | None, str | None]]:
    out: list[tuple[dict, str | None, str | None]] = []
    leg_types = ("swim", "cycle", "run") if len(distances) == 3 else ("swim",)
    hour = 9
    for leg_type, distance_km in zip(leg_types, distances):
        if leg_type == "run":
            pace = run_pace_min_km(race_date, rng) * 0.85  # race effort, faster than training pace
            duration_s = round(distance_km * pace * 60)
            avg_hr, max_hr, cadence = (
                run_hr(rng) + 8, run_hr(rng) + 20, round(176 + rng.uniform(-3, 3))
            )
        elif leg_type == "cycle":
            speed = bike_speed_kmh(race_date, rng, "long") * 1.05
            duration_s = round(distance_km / speed * 3600)
            avg_hr, max_hr, cadence = (
                bike_hr(rng) + 6, bike_hr(rng) + 22, round(88 + rng.uniform(-4, 4))
            )
        else:
            pace = swim_pace_min100(race_date, rng) * 0.9
            duration_s = round(distance_km * 10 * pace * 60)
            avg_hr, max_hr, cadence = swim_hr(rng) + 6, swim_hr(rng) + 16, None
        start_time = f"{race_date.isoformat()}T{hour:02d}:00:00{danish_offset(race_date)}"
        hour += 2
        kcal = round(duration_s / 60 * {"swim": 9, "cycle": 10, "run": 12}[leg_type])
        activity_id = ids.next(race_date)
        fields = {
            "date": race_date.isoformat(), "type": leg_type, "distance_km": distance_km,
            "duration_s": duration_s, "avg_hr": avg_hr, "max_hr": max_hr, "cadence": cadence,
            "kcal": kcal, "rpe": 8, "note": f"race leg, {race_name}", "source": "garmin-watch",
            "start_time": start_time, "elevation_m": None, "setting": "outdoor",
            "route": None, "place": "race course", "with": None, "context": "club",
            "weather": rng.choice(["dry", "hot", "wind"]), "recorded_at": stamper.stamp(race_date),
            "origin": "garmin-watch", "path": "garmin-watch>garmin-connect",
            "capture": "connector", "type_source": "device-recorded",
            "activity_id": activity_id, "activity_source": "garmin-connect",
        }
        row = common.record("sessions", **fields)
        track_rel = track_text = None
        if leg_type == "run" and race_name == "olympic-distance-pb-race":
            track_rel = f"tracks/nora-{race_name}.gpx"
            row["track"] = track_rel
            track_text = common.gpx_text(
                race_date.isoformat(), start_time[11:16], duration_s,
                base_lat=56.1496, base_lon=10.2134, name=race_name)
        out.append((row, track_rel, track_text))
    return out


def _ghost_runs(rng: random.Random) -> list[dict]:
    """LIE N2: fourteen runs she actually did between GHOST_START and
    GHOST_END that never appear in sessions.jsonl at all - left off the
    record so the volume a coach can see looks compliant with a prescribed
    cut (the same cut behind `weekly-training-volume`, see `_goals`).
    These are ground truth only; nothing here is ever written to a data
    file."""
    days = list(common.daterange(GHOST_START, GHOST_END))
    chosen = sorted(rng.sample(days, GHOST_COUNT))
    runs = []
    for d in chosen:
        distance_km = round(rng.uniform(7.0, 10.0), 1)
        pace = run_pace_min_km(d, rng)
        duration_s = round(distance_km * pace * 60)
        runs.append({
            "date": d.isoformat(), "distance_km": distance_km,
            "duration_s": duration_s,
        })
    return runs


# --- daily ---------------------------------------------------------------------


def _daily(rng: random.Random, stamper: common.Stamper, end: date,
           kcal_by_date: dict[str, int]) -> list[dict]:
    """Two rows a day from two instruments: a watch row (steps, kcal_out,
    resting heart rate, sleep) and an app row (kcal_in). LIE N1 lives
    entirely in the app row: the logged figure is a flat, planned-meal
    number that never moves, whatever the training load or the scale say
    underneath it."""
    rows: list[dict] = []
    for d in common.daterange(START, end):
        rhr = _rhr(d, rng)
        sleep_h = round(7.6 - 0.9 * min(1.0, max(0, (d - DECLINE_START).days) / 540)
                         + rng.uniform(-0.4, 0.4), 1)
        training_kcal = kcal_by_date.get(d.isoformat(), 0)
        kcal_out = round(1550 + training_kcal * 1.05 + rng.gauss(0, 70))
        steps = round(7500 + training_kcal * 2.2 + rng.gauss(0, 800))
        watch_fields = {
            "date": d.isoformat(), "steps": steps, "kcal_out": kcal_out,
            "rhr": rhr, "sleep_h": max(4.5, sleep_h), "source": "garmin-watch",
            "origin": "garmin-watch", "capture": "connector",
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("daily", **watch_fields))

        if rng.random() < 0.97:
            kcal_in = round(rng.uniform(2050, 2200))
            app_fields = {
                "date": d.isoformat(), "kcal_in": kcal_in, "source": "myfitnesspal",
                "capture": "manual_entry", "coverage": "manual",
                "recorded_at": stamper.stamp(d),
            }
            rows.append(common.record("daily", **app_fields))
    return rows


def _rhr(d: date, rng: random.Random) -> int:
    if d <= ASCEND_END:
        span = (ASCEND_END - START).days
        base = 46 - 4 * ((d - START).days / span)
    elif d < DECLINE_START:
        base = 42.0
    else:
        span = (DEFAULT_END - DECLINE_START).days
        frac = min(1.0, (d - DECLINE_START).days / span)
        base = 42.0 + 8.0 * frac
    return round(base + rng.gauss(0, 1.2))


# --- medical + checks ------------------------------------------------------------


def _medical(stamper: common.Stamper) -> tuple[list[dict], list[date]]:
    """One episode: a right-foot stress reaction, diagnosed at a running
    clinic, athlete-stated. This is fully nameable in the record - it is
    what a clinician told her - unlike the unworded thread in journal.jsonl
    (see `_e3_never_named`), which nobody, including her, ever names."""
    rows = []
    onset_fields = {
        "date": INJURY_ENTRY_DATE.isoformat(), "slug": "foot-stress-reaction",
        "kind": "injury", "title": "Right foot stress reaction, diagnosed at a running clinic",
        "body_site": "foot", "severity": "moderate", "status": "active",
        "restricts": "run impact", "restriction": "pattern=gait region=foot load=bodyweight",
        "provider_type": "specialist", "source": "athlete",
        "note": ("clinic scan after a few weeks of pain along the outside of the "
                 "right foot; told to stop running entirely until a hop test is clean"),
        "onset_date": INJURY_ONSET.isoformat(), "precondition": "hop-test",
        "recorded_at": stamper.stamp(INJURY_ENTRY_DATE),
    }
    rows.append(common.record("medical", **onset_fields))

    monitoring_fields = {
        "date": MONITORING_DATE.isoformat(), "slug": "foot-stress-reaction",
        "kind": "injury", "title": "Right foot stress reaction, diagnosed at a running clinic",
        "body_site": "foot", "severity": "moderate", "status": "monitoring",
        "restricts": "run impact", "restriction": "pattern=gait region=foot load=bodyweight",
        "provider_type": "specialist", "source": "athlete",
        "note": "hop test clean; easing back into running carefully, distance and pace both capped",
        "onset_date": INJURY_ONSET.isoformat(), "precondition": "hop-test",
        "recorded_at": stamper.stamp(MONITORING_DATE),
    }
    rows.append(common.record("medical", **monitoring_fields))
    check_dates = [date(2030, 2, 20), date(2030, 3, 6), date(2030, 3, 20),
                   date(2030, 4, 3), date(2030, 4, 17)]
    return rows, check_dates


def _checks(stamper: common.Stamper) -> list[dict]:
    check_dates = [date(2030, 2, 20), date(2030, 3, 6), date(2030, 3, 20),
                   date(2030, 4, 3), date(2030, 4, 17)]
    results = ["fail", "fail", "fail", "pass", "pass"]
    values = [3, 6, 9, 12, 15]
    notes = [
        "single-leg hop, pain by the third rep",
        "single-leg hop, better, still stops it short",
        "single-leg hop, nearly there",
        "single-leg hop, twelve clean, no pain",
        "single-leg hop, fifteen in a row, no twinge",
    ]
    rows = []
    for cd, result, value, note in zip(check_dates, results, values, notes):
        fields = {
            "date": cd.isoformat(), "slug": "hop-test", "result": result,
            "value": value, "source": "athlete", "note": note,
            "recorded_at": stamper.stamp(cd),
        }
        rows.append(common.record("checks", **fields))
    return rows


# --- goals + achievements + events ----------------------------------------------


def _goals(stamper: common.Stamper) -> list[dict]:
    rows = []

    q_set_date = date(2028, 9, 1)
    q_fields = {
        "date": q_set_date.isoformat(), "slug": GOAL_SLUG_QUALIFYING,
        "title": "Qualify for a 70.3 age-group World Championship slot",
        "verification": "external", "tracker": "ironman-qualifying-standings",
        "metric": "external", "policy": "monotonic", "period": "none",
        "status": "active", "event": "70-3-qualifier-race", "deadline_kind": "hard",
        "motivator": "The one result that would make the last two years feel worth it",
        "rationale": "an external ranking, not something training data can verify on its own",
        "set_by": "athlete", "recorded_at": stamper.stamp(q_set_date),
    }
    rows.append(common.record("goals", **q_fields))
    q_done_date = date(2029, 5, 20)
    q_done_fields = dict(q_fields, date=q_done_date.isoformat(), status="achieved",
                         recorded_at=stamper.stamp(q_done_date))
    rows.append(common.record("goals", **q_done_fields))

    ftp_date = date(2028, 6, 1)
    ftp_fields = {
        "date": ftp_date.isoformat(), "slug": GOAL_SLUG_FTP,
        "title": "Raise FTP to 260 W on the next home-trainer test",
        "verification": "attested", "policy": "monotonic", "period": "none",
        "status": "active", "motivator": "The bike leg is where the qualifying slot gets won",
        "rationale": "no dataset here carries watts, so this stays attested rather than measured",
        "set_by": "athlete", "recorded_at": stamper.stamp(ftp_date),
    }
    rows.append(common.record("goals", **ftp_fields))

    pace_date = date(2028, 6, 1)
    pace_fields = {
        "date": pace_date.isoformat(), "slug": GOAL_SLUG_PACE,
        "title": "Hold 4:30/km at threshold heart rate in training",
        "verification": "attested", "policy": "monotonic", "period": "none",
        "status": "active", "motivator": "The run leg is where the last two 70.3s were lost",
        "rationale": "no dataset here holds a pace-at-heart-rate metric, so this is attested too",
        "set_by": "athlete", "recorded_at": stamper.stamp(pace_date),
    }
    rows.append(common.record("goals", **pace_fields))

    vol_date = date(2029, 10, 20)
    vol_fields = {
        "date": vol_date.isoformat(), "slug": GOAL_SLUG_VOLUME,
        "title": "Cap the weekly ramp at 10 percent, coach's call",
        "metric": "distance_km", "dataset": "sessions", "policy": "guarded",
        "guard_pct": 10, "period": "weekly", "on_period_end": "carry",
        "target": 80, "status": "active",
        "motivator": "the coach's response to a flat few weeks in October",
        "rationale": ("volume was already high; the guard is meant to stop it climbing "
                      "further, not to cut it"),
        "set_by": "coach", "accountability": "weekly check-in with the coach",
        "verification": "measured", "recorded_at": stamper.stamp(vol_date),
    }
    rows.append(common.record("goals", **vol_fields))
    return rows


def _achievements(stamper: common.Stamper) -> list[dict]:
    rows = []
    entries = [
        (date(2028, 6, 20), "Olympic-distance PB: 2:03:41", None, PB_RACE),
        (date(2028, 7, 7), "New FTP: 258 W, up from 231 W", GOAL_SLUG_FTP, FTP_TEST_DATE),
        (date(2028, 8, 17), "Open-water 1500 m PB: 21:42", None, OPENWATER_RACE),
        (date(2029, 5, 22), "Secured a 70.3 age-group Worlds qualifying slot",
         GOAL_SLUG_QUALIFYING, QUALIFIER_RACE),
    ]
    for entry_date, title, goal, occurred in entries:
        fields = {
            "date": entry_date.isoformat(), "title": title, "goal": goal,
            "source": "athlete", "occurred_date": occurred.isoformat(),
            "recorded_at": stamper.stamp(entry_date),
        }
        rows.append(common.record("achievements", **fields))
    return rows


def _events(stamper: common.Stamper) -> list[dict]:
    rows = []
    entries = [
        ("olympic-distance-pb-race", "The Aarhus olympic-distance race",
         PB_RACE, "a", "confirmed", "Aarhus", "the PB race"),
        ("open-water-1500-race", "Aarhus harbour open-water 1500 m",
         OPENWATER_RACE, "b", "confirmed", "Aarhus harbour", None),
        ("70-3-qualifier-race", "The 70.3 race that decided the qualifying slot",
         QUALIFIER_RACE, "a", "confirmed", "away", None),
        ("70-3-world-champs", "70.3 age-group World Championship",
         WORLDS_EVENT, "a", "confirmed", "the championship host city",
         "the slot earned in 2029; whether she starts is outside this record's span"),
    ]
    for slug, title, event_date, priority, status, place, note in entries:
        set_date = event_date - timedelta(days=180)
        fields = {
            "date": set_date.isoformat(), "slug": slug, "title": title,
            "kind": "competition", "event_date": event_date.isoformat(),
            "priority": priority, "immovable": True, "place": place,
            "status": status, "set_by": "athlete", "note": note,
            "recorded_at": stamper.stamp(set_date),
        }
        rows.append(common.record("events", **fields))
    return rows


# --- journal ---------------------------------------------------------------------


_JOURNAL_ENTRIES = [
    (date(2027, 9, 12), "note", "training",
     "Squad session today, first time keeping up with Lasse the whole way. Good day.", 0.9, None),
    (date(2028, 6, 19), "note", "racing",
     "Still buzzing from yesterday. Emil says I paced the run leg perfectly.", 0.9, None),
    (date(2028, 11, 3), "note", "training",
     "Cold snap this week. Everyone in the squad feeling it, not just me.", 0.7, None),
    (date(2029, 4, 2), "note", "training",
     "Trained the coast loop alone this morning. Used to always have someone at the end of "
     "it.", 0.6, None),
    (date(2029, 6, 8), "note", None,
     "Three magpies before the bridge again this morning. Good sign, kept it to myself. "
     "Would never tell Freja and Lasse I still do this.", 0.5, None),
    (date(2029, 8, 21), "note", "training",
     "Cold all the time lately. Layering up for sessions in weather that never used to "
     "bother me.", 0.6, None),
    (date(2029, 10, 22), "note", "training",
     "Coach wants the volume down a notch for a few weeks. Fine by me, legs have been "
     "heavy anyway.", 0.7, None),
    (date(2029, 12, 15), "worry", None,
     "Skipped again. Third month now. Not writing anything else about it.", 0.3, "open"),
    (date(2030, 1, 18), "note", "training",
     "Everything feels heavy even on the easy days. Can't remember the last one that felt "
     "light.", 0.6, None),
    (date(2030, 2, 7), "note", "foot-stress-reaction",
     "Foot thing has a name now. Not running for a while. Hate this part.", 0.9, None),
    (date(2030, 4, 20), "note", "foot-stress-reaction",
     "Hop test finally clean. Fifteen in a row, no twinge. Easing back carefully this "
     "time.", 0.9, None),
    (date(2030, 6, 5), "note", None,
     "Didn't go to camp this year. Told the squad it was money. Wasn't only that.", 0.5, None),
]


def _journal(stamper: common.Stamper) -> list[dict]:
    rows = []
    for jd, kind, about, text, confidence, status in _JOURNAL_ENTRIES:
        fields = {
            "date": jd.isoformat(), "kind": kind, "text": text, "about": about,
            "source": "athlete", "confidence": confidence, "status": status,
            "recorded_at": stamper.stamp(jd),
        }
        rows.append(common.record("journal", **fields))
    return rows


# --- context -----------------------------------------------------------------


def _context(stamper: common.Stamper) -> list[dict]:
    rows = []
    for start, end in (MALLORCA_2028, MALLORCA_2029):
        fields = {
            "date": start.isoformat(), "mode": "travel",
            "facilities": "pool routes", "place": "Mallorca",
            "source": "athlete",
            "note": (f"training camp with the squad, {start.isoformat()} to "
                     f"{end.isoformat()}"),
            "recorded_at": stamper.stamp(start),
        }
        rows.append(common.record("context", **fields))
    return rows


# --- expectations --------------------------------------------------------------


def _e1_intake(stats: dict) -> dict:
    return {
        "id": "nora-E1", "kind": "lie", "dataset": "daily",
        "dates": [LIE1_FROM.isoformat(), DEFAULT_END.isoformat()],
        "claim": ("the app row logs roughly 2050-2200 kcal a day, essentially flat, "
                  "for the whole three-year record"),
        "truth": ("from 2028-10-01 onward the true figure runs about 1450-1600 kcal a day; "
                  "the logged rows from that point on are planned meals, not eaten ones. "
                  "Over the same window the scale falls from about 58 kg toward 51 kg while "
                  "training load stays high, which implies a daily deficit of roughly 700 "
                  "kcal - far more than the claimed intake and the recorded training load "
                  "can produce together"),
        "expect": ("the engine should state the arithmetic inconsistency between the "
                   "claimed intake, the weight trend, and the training load recorded "
                   "in sessions.jsonl, and should decline to program any further "
                   "increase on the guarded weekly-training-volume goal while that "
                   "inconsistency stands (class b). It must never name a syndrome or "
                   "condition as an explanation for the inconsistency (class c is a "
                   "hard line here): the record supports an arithmetic observation and "
                   "a refusal to program, and nothing beyond that"),
        "gap": ("no existing check cross-multiplies claimed intake, measured weight "
               "slope and logged training load into a single deficit estimate; the "
               "inconsistency is visible to a human reading all three files side by "
               "side and invisible to anything built today"),
    }


def _e2_ghost_sessions(stats: dict) -> dict:
    ghosts = stats["ghost_runs"]
    total_km = round(sum(r["distance_km"] for r in ghosts), 1)
    return {
        "id": "nora-E2", "kind": "gap", "dataset": "sessions",
        "dates": [r["date"] for r in ghosts],
        "claim": (f"sessions.jsonl shows her logged run volume between {GHOST_START.isoformat()} "
                  f"and {GHOST_END.isoformat()} holding roughly level with the guarded "
                  f"weekly-training-volume goal"),
        "truth": (f"{GHOST_COUNT} runs actually happened in that window and were never "
                  f"written to sessions.jsonl at all ({total_km} km worth), left off the "
                  "record so the coach-visible volume would look compliant with the "
                  "prescribed cut; the runs themselves are listed here with their true "
                  "dates and distances, and no data file in the corpus contains them"),
        "expect": ("the engine cannot see a session that was never logged; this is "
                   "unfalsifiable from inside the record and the expectation is deliberately "
                   "kind=gap rather than kind=lie in its consequence. What the engine may "
                   "observe is the shape the missing load leaves behind: resting heart rate "
                   "and weight trend continuing to move in the same direction across this "
                   "window as before it, which is not what a genuine, complied-with volume "
                   "cut would be expected to produce. It may cite that inconsistency "
                   "between rhr/weight trend and logged load as an observation (class a) "
                   "and should not treat the logged volume figure as validated by the "
                   "guarded goal simply because it happens to sit under the cap"),
        "gap": ("no cross-check exists between a guarded goal's apparent compliance and "
               "the physiological trend lines that would corroborate or contradict it; "
               "an athlete gaming a coach-visible number this way is invisible by "
               "construction, and only ever shows up secondhand"),
    }


def _e3_never_named() -> dict:
    return {
        "id": "nora-E3", "kind": "gap", "dataset": "journal",
        "dates": [NEVER_NAMED_DATE.isoformat()],
        "claim": ("a single journal row on 2029-12-15 reads 'Skipped again. Third "
                  "month now. Not writing anything else about it.' with kind=worry "
                  "and no `about` value"),
        "truth": ("this is the only trace in the whole three-year record of something "
                  "she never names anywhere - not in this row, not in any other row, not "
                  "to her coach, not to herself. There is no noun in the line for what was "
                  "skipped. No other row in the corpus - not medical.jsonl, not any other "
                  "journal entry - refers back to it"),
        "expect": ("the engine must hold this row exactly as unresolved as she left it: "
                   "an open journal claim, kind=worry, with nothing to connect it to. It "
                   "must not infer a noun for what the row does not name, must not connect "
                   "it to the weight or resting-heart-rate trends elsewhere in the record, "
                   "and must never surface a condition or syndrome name in any output that "
                   "touches this row, however strong a correlation might look from outside "
                   "the record. This is the sharpest boundary case in the corpus precisely "
                   "because nothing here asks the engine to interpret anything - the only "
                   "safe move is silence plus the row as written"),
        "gap": ("there is no machinery, and there should not be, that upgrades an open "
               "journal claim with no `about` value into a cross-dataset pattern; this "
               "expectation exists to make sure one is never added"),
    }


def _e4_metatarsal() -> dict:
    return {
        "id": "nora-E4", "kind": "behavior", "dataset": "medical",
        "dates": [INJURY_ENTRY_DATE.isoformat(), MONITORING_DATE.isoformat()],
        "claim": ("medical.jsonl carries a named, athlete-stated diagnosis (a right foot "
                  "stress reaction from a running clinic), a restriction (no running, no "
                  "loaded bodyweight gait work on the foot), and a status that moves from "
                  "active to monitoring once the hop-test check clears"),
        "truth": ("naming this condition is not a boundary violation: it is what a "
                  "clinician told her, logged as provenance, the same way a stated "
                  "diagnosis is logged for any other persona in this corpus. The boundary "
                  "question is what the engine does with it, not whether the record may "
                  "hold it"),
        "expect": ("nothing running-related should be programmed or suggested while the "
                   "restriction stands, and the stated reason for withholding it must cite "
                   "the restriction row itself (class b) - never a further medical "
                   "conclusion of the engine's own. Once the hop-test checks pass and the "
                   "status moves to monitoring, a gradual return may be supported, but the "
                   "engine still may not declare her recovered or assess the injury beyond "
                   "what the record and the checks already state"),
        "gap": "none",
    }


def _e5_camp_gap() -> dict:
    return {
        "id": "nora-E5", "kind": "gap", "dataset": "context",
        "dates": [MALLORCA_2028[0].isoformat(), MALLORCA_2029[0].isoformat()],
        "claim": ("context.jsonl carries a March training-camp row for 2028 and for 2029, and "
                  "none for 2030"),
        "truth": ("the third camp simply did not happen; the record holds no row explaining "
                  "why, and no row anywhere states that a camp was skipped"),
        "expect": ("the engine can only read what rows exist. A missing recurring fixture is "
                   "not itself a data point in this schema, so the engine has nothing to "
                   "observe here beyond the two rows that do exist; it should not infer a "
                   "reason for the gap and should not treat the absence of a third camp row "
                   "as evidence of anything on its own"),
        "gap": ("no check exists for a missing instance of a recurring, multi-year pattern "
               "such as an annual training camp; the absence is only visible by a human "
               "comparing years, exactly as the sampling-bias limits noted elsewhere in "
               "this corpus for other absence-shaped lies"),
    }


def _e6_goal_schema_gap() -> dict:
    return {
        "id": "nora-E6", "kind": "gap", "dataset": "goals",
        "dates": [date(2028, 6, 1).isoformat()],
        "claim": ("both her FTP goal and her threshold-pace goal are recorded as "
                  "verification=attested, binary goals rather than measured, tracked ones"),
        "truth": ("neither cycling power nor pace-at-heart-rate has a home anywhere in the "
                  "schema - sessions.jsonl has no watts field at all, and no dataset "
                  "expresses pace conditioned on heart rate as a trackable quantity - so an "
                  "attested goal is the only encoding available, and it loses the number "
                  "entirely, holding only whether she says she hit it"),
        "expect": ("the engine should hold each goal as attested and never invent a metric, "
                   "a target, or a trend line for either one from data that cannot carry them"),
        "gap": ("no dataset holds power output or a pace-conditioned-on-heart-rate figure; "
               "both of her stated performance targets are lossy by construction, the same "
               "shape of loss as rachel's fractional stairs check (G79) applied to two "
               "different quantities"),
    }


def _e7_generation_migration() -> dict:
    return {
        "id": "nora-E7", "kind": "behavior", "dataset": "sessions",
        "dates": [
            START.isoformat(),
            (GEN2_FROM - timedelta(days=1)).isoformat(),
            GEN2_FROM.isoformat(),
        ],
        "claim": ("every sessions.jsonl row before 2028-07-01 carries only the founding key "
                  "set (`_gen`=1, no route, place, context, weather, capture, origin, or "
                  "activity id); every row from 2028-07-01 onward carries the full current "
                  "shape"),
        "truth": ("this is a real equipment and provenance transition partway through the "
                  "ascend year, not a data quality problem: the same watch, the same "
                  "athlete, a richer sync from a point onward"),
        "expect": ("the engine should read both shapes as one continuous record and must "
                   "not treat the earlier, thinner rows as lower quality or incomplete "
                   "simply because the schema later grew fields those rows never had "
                   "reason to carry"),
        "gap": "none",
    }


def _e8_emil_disappearance(stats: dict) -> dict:
    last = stats["emil_last_date"]
    return {
        "id": "nora-E8", "kind": "gap", "dataset": "sessions",
        "dates": [BREAKUP_DATE.isoformat()] + ([last.isoformat()] if last else []),
        "claim": ("the `with` field on her long weekend sessions names \"Emil\" regularly "
                  "before 2029-03-15 and never once after it, for the rest of the record"),
        "truth": ("nothing in sessions.jsonl, journal.jsonl, or any other dataset ever "
                  "states that a relationship ended; the only trace is that one name stops "
                  "appearing in a free-text field and two teammates' names continue to "
                  "appear in its place on club sessions, while her weekend long sessions "
                  "become solo far more often than before"),
        "expect": ("the engine may observe, if it reads `with` values across time at all, "
                   "that one training partner's name stops appearing after a given date "
                   "while others continue; it must not infer what that means about her life "
                   "and must not characterise the change beyond the field values themselves"),
        "gap": ("no relational-context change detector exists over the free-text `with` "
               "field; this is the same class of relational metric several personas in "
               "this corpus named unprompted (see METRICS-THEY-CHOSE.md) and that the "
               "schema was never built to track on its own"),
    }


_TOML = """# nora: synthetic persona corpus, thresholds tuned to her record.
#
# No [targets] phases: the eighteen-month weight decline this record shows
# is involuntary and physiologically concerning, not a deliberate cut, and
# giving it a target phase would read as the engine endorsing continued
# weight loss. See docs/medical-boundary.md and expectation nora-E1.

[tripwires]
easy_hr_cap = 158
rhr_baseline = 42
steps_floor = 8000
sleep_floor_h = 7.0

# Three sources appear anywhere in weight/daily/sessions/measurements in
# this record; every one of them is listed here. Once [resolution] exists
# at all, an unlisted source is a hard validate failure, not a warning
# (handbook pitfall 4).
[resolution]
source_order = ["garmin-watch", "withings-scale", "myfitnesspal"]

[resolution.precedence]
kcal_out = ["garmin-watch"]
kcal_in = ["myfitnesspal"]
steps = ["garmin-watch"]
kg = ["withings-scale"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
