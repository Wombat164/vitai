"""Generator for the rachel persona (seed 108).

Cork, Ireland. 39, BMI 45 at baseline, knee osteoarthritis in both knees (the
right one worse), five months into a GP-prescribed GLP-1 agonist. The record
runs fourteen months: nine of a flat pre-medication baseline, then five of a
genuine, involuntary decline in both weight and appetite. See `PROFILE.md`,
`LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md` alongside this file for
the prose this generator's numbers have to agree with. Entirely synthetic;
any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself - `generate.py` decides
whether that content lands on disk or is compared against what is already
committed.

Written and verified against installed `vitai 0.2.3`
(`common.AUTHORED_AGAINST_VITAI_VERSION` / `AUTHORED_AGAINST_GENERATIONS`
carry the exact figures; `generate.py` prints a drift warning if the
installed vitai has since moved past them). Re-verify this generator against
the handbook before trusting its output once that version changes.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 108
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# The record's own calendar. These are prose facts (PROFILE.md, WORLD.md),
# not derived from the CLI's `--end`, because the story - nine months flat,
# then five months on medication - is a fixed piece of her history rather
# than a window that slides with wherever the corpus currently ends.
START = date(2029, 5, 1)
MED_START = date(2030, 2, 3)
DEFAULT_END = date(2030, 6, 30)

# The route catalog from WORLD.md: her graduation ladder, in kilometres.
ROUTES = {
    "school-gate": 0.7,
    "estate-loop": 1.6,
    "park-loop": 3.1,
}

# Walking-day-of-week sets per capacity stage (Monday=0 .. Sunday=6).
STAGE_A_END = date(2030, 2, 28)   # school-gate, short, twice a week
STAGE_B_END = date(2030, 4, 30)   # estate-loop, three times a week
WALK_DAYS_A = {1, 5}              # Tuesday, Saturday
WALK_DAYS_B = {1, 3, 5}           # Tuesday, Thursday, Saturday
WALK_DAYS_C = {1, 3, 5, 6}        # + Sunday, when Niall and Fionn's match allow

# The eleven R1 lies (LIES.md) sit on estate-loop walks from March onward.
LIE_WINDOW_START = date(2030, 3, 1)
LIE_COUNT = 11
TRACKED_LIE_COUNT = 3             # "a few" of the eleven carry a stored GPX


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper()
    daily_stamper = common.Stamper()
    sessions_stamper = common.Stamper()
    medical_stamper = common.Stamper()
    checks_stamper = common.Stamper()
    goals_stamper = common.Stamper()

    weight = _weight(rng, weight_stamper, end)
    daily, logged_pre_dates = _daily(rng, daily_stamper, end)
    sessions, lie_expectations, tracks = _sessions(rng, sessions_stamper, end)
    medical, check_dates = _medical_and_checks_dates(medical_stamper)
    checks = _checks(checks_stamper)
    goals, goal_date = _goals(goals_stamper)

    expectations = lie_expectations + [
        _e2(logged_pre_dates),
        _e3(end),
        _e4(),
        _e5(check_dates),
        _e6(goal_date),
    ]

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/medical.jsonl": common.jsonl_text(common.sort_rows(medical)),
        "data/checks.jsonl": common.jsonl_text(common.sort_rows(checks)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
    for rel_path, text in tracks.items():
        files[rel_path] = text
    return files


# --- weight ------------------------------------------------------------------


def _weight(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Twice a week, from a connected smart scale. Flat 121-123 kg until the
    medication starts, then a noisy but steady descent toward 112 kg."""
    rows = []
    total_post_days = max(1, (end - MED_START).days)
    for d in common.daterange(START, end):
        if d.weekday() not in (0, 3):          # Monday and Thursday
            continue
        if d < MED_START:
            kg = 122.0 + rng.uniform(-1.3, 1.3)
        else:
            frac = min(1.0, (d - MED_START).days / total_post_days)
            target = 122.0 - 10.0 * frac
            kg = target + rng.gauss(0, 0.35)
        measured_at = f"{7:02d}:{rng.randrange(0, 45):02d}"
        fields = {
            "date": d.isoformat(), "kg": round(kg, 1), "source": "withings-scale",
            "measured_at": measured_at, "origin": "withings-scale",
            "capture": "connector", "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("weight", **fields))
    return rows


# --- daily ---------------------------------------------------------------------


def _daily(rng: random.Random, stamper: common.Stamper,
           end: date) -> tuple[list[dict], list[date]]:
    """22 flattering pre-medication days, then daily involuntary low intake.

    No steps, no sleep, no heart rate anywhere - she has no wearable, only a
    food-logging app, per PROFILE.md and WORLD.md.
    """
    rows: list[dict] = []
    pre_med_days = list(common.daterange(START, MED_START - timedelta(days=1)))
    logged_pre_dates = sorted(rng.sample(pre_med_days, 22))
    for d in logged_pre_dates:
        kcal = max(1300, min(1500, int(rng.gauss(1400, 50))))
        fields = {
            "date": d.isoformat(), "kcal_in": kcal, "source": "myfitnesspal",
            "coverage": "manual", "capture": "manual_entry",
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("daily", **fields))
    for d in common.daterange(MED_START, end):
        kcal = max(1030, min(1220, int(rng.gauss(1120, 45))))
        fields = {
            "date": d.isoformat(), "kcal_in": kcal, "source": "myfitnesspal",
            "coverage": "manual", "capture": "manual_entry",
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("daily", **fields))
    return rows, logged_pre_dates


# --- sessions ------------------------------------------------------------------


def _sessions(rng: random.Random, stamper: common.Stamper,
              end: date) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Aqua fit every Wednesday, honest phone-tracked walks that climb the
    route catalog, and the eleven R1 duration-inflation pairs layered on top
    of the true estate-loop walks."""
    rows: list[dict] = []
    estate_candidates: list[tuple[date, dict]] = []

    for d in common.daterange(START, end):
        if d.weekday() == 2:                    # Wednesday, every week
            rows.append(_aqua_fit(rng, stamper, d))

    stage_c_counter = 0
    for d in common.daterange(MED_START, end):
        wd = d.weekday()
        if d <= STAGE_A_END:
            if wd not in WALK_DAYS_A:
                continue
            route, minutes, family = "school-gate", rng.uniform(8, 10), False
        elif d <= STAGE_B_END:
            if wd not in WALK_DAYS_B:
                continue
            route, minutes, family = "estate-loop", rng.uniform(12, 16), False
        else:
            if wd not in WALK_DAYS_C:
                continue
            if wd == 6:
                if rng.random() >= 0.7:          # not every Sunday holds
                    continue
                route, minutes, family = "park-loop", rng.uniform(20, 25), True
            else:
                stage_c_counter += 1
                if stage_c_counter % 4 == 0:
                    route, minutes, family = "estate-loop", rng.uniform(12, 16), False
                else:
                    route, minutes, family = "park-loop", rng.uniform(20, 25), False
        row = _device_walk(rng, stamper, d, route, minutes, family)
        rows.append(row)
        if route == "estate-loop" and d >= LIE_WINDOW_START:
            estate_candidates.append((d, row))

    chosen = sorted(rng.sample(estate_candidates, LIE_COUNT), key=lambda x: x[0])
    lie_expectations: list[dict] = []
    tracks: dict[str, str] = {}
    for idx, (d, device_row) in enumerate(chosen):
        manual_row = _manual_lie(rng, stamper, d, device_row)
        rows.append(manual_row)
        if idx < TRACKED_LIE_COUNT:
            track_rel = f"tracks/rachel-estate-loop-{d.isoformat()}.gpx"
            device_row["track"] = track_rel
            start_hhmm = device_row["start_time"][11:16]
            tracks[track_rel] = common.gpx_text(
                d.isoformat(), start_hhmm, device_row["duration_s"],
                base_lat=51.90 + idx * 0.01, base_lon=-8.50 - idx * 0.01,
                name="estate-loop")
        true_minutes = round(device_row["duration_s"] / 60)
        lie_expectations.append({
            "id": f"rachel-E1-{idx + 1:02d}",
            "kind": "lie",
            "dataset": "sessions",
            "dates": [d.isoformat()],
            "claim": "walk logged by hand as 30 minutes on the park loop (3.1 km)",
            "truth": (f"the phone app recorded the same walk, starting at the "
                      f"same time, as {true_minutes} minutes on the estate "
                      "loop (1.6 km)"),
            "expect": ("the resolution ladder should treat these two rows as "
                       "one activity (their start times overlap), pick the "
                       "device-recorded duration and distance over the "
                       "athlete-stated claim, never average the two, and "
                       "explain the choice"),
            "gap": "none",
        })
    return rows, lie_expectations, tracks


def _aqua_fit(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    duration_s = int(rng.gauss(45 * 60, 3 * 60))
    fields = {
        "date": d.isoformat(), "type": "swim", "duration_s": duration_s,
        "rpe": rng.choice([4, 5, 5, 6]),
        "note": "aqua fitness class, Glenbrook Leisure Centre",
        "source": "athlete",
        "start_time": f"{d.isoformat()}T19:00:00{common.irish_offset(d)}",
        "setting": "indoor", "place": "Glenbrook Leisure Centre",
        "with": "Deirdre", "context": "social",
        "type_source": "athlete-stated", "capture": "manual_entry",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _device_walk(rng: random.Random, stamper: common.Stamper, d: date,
                  route: str, minutes: float, family: bool) -> dict:
    duration_s = max(60, int(minutes * 60 + rng.uniform(-15, 15)))
    if family:
        start_time = f"{d.isoformat()}T09:30:00{common.irish_offset(d)}"
    else:
        start_time = (f"{d.isoformat()}T09:{rng.randrange(0, 30):02d}:00"
                       f"{common.irish_offset(d)}")
    fields = {
        "date": d.isoformat(), "type": "walk", "distance_km": ROUTES[route],
        "duration_s": duration_s, "rpe": rng.choice([2, 3, 3, 4]),
        "source": "phone", "start_time": start_time, "setting": "outdoor",
        "route": route, "place": "estate" if family else "home",
        "with": "Niall" if family else None,
        "context": "family" if family else "solo",
        "weather": rng.choice(["dry", "dry", "rain", "wind", "cold"]),
        "type_source": "vendor-classified", "capture": "connector",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _manual_lie(rng: random.Random, stamper: common.Stamper, d: date,
                device_row: dict) -> dict:
    fields = {
        "date": d.isoformat(), "type": "walk", "distance_km": ROUTES["park-loop"],
        "duration_s": 1800, "rpe": rng.choice([4, 5]),
        "source": "athlete", "start_time": device_row["start_time"],
        "setting": "outdoor", "route": "park-loop", "place": "home",
        "context": "solo", "type_source": "athlete-stated",
        "capture": "manual_entry", "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


# --- medical + checks ------------------------------------------------------------


_VISIT_DATES = [date(2030, 2, 4), date(2030, 3, 4), date(2030, 4, 1),
                date(2030, 5, 6), date(2030, 6, 3)]

_CHECK_DATES = [date(2030, 2, 6), date(2030, 2, 20), date(2030, 3, 6),
                date(2030, 3, 20), date(2030, 4, 3), date(2030, 4, 17),
                date(2030, 5, 1), date(2030, 5, 15), date(2030, 5, 29),
                date(2030, 6, 12), date(2030, 6, 26)]
_CHECK_NUMERATORS = [8, 8, 9, 9, 10, 10, 11, 11, 11, 12, 12]


def _medical_and_checks_dates(stamper: common.Stamper) -> tuple[list[dict], list[date]]:
    rows = []
    knee_fields = {
        "date": START.isoformat(), "slug": "knee-osteoarthritis", "kind": "state",
        "title": "Knee osteoarthritis, both knees, right worse",
        "body_site": "knee", "severity": "moderate", "status": "active",
        "restricts": "impact", "restriction": "pattern=jump region=knee load=loaded",
        "provider_type": "gp", "source": "athlete",
        "note": ("both knees ache, the right one worse; stairs and anything "
                 "high-impact flare it; her GP calls it wear and tear"),
        "onset_date": "2024-06-01", "recorded_at": stamper.stamp(START),
    }
    rows.append(common.record("medical", **knee_fields))

    med_fields = {
        "date": MED_START.isoformat(), "slug": "glp1-medication", "kind": "medication",
        "title": "Started a GLP-1 agonist injection, GP-prescribed",
        "severity": "none", "status": "active", "provider_type": "gp",
        "source": "athlete",
        "note": "appetite dropped almost at once; not something she is doing on purpose",
        "expects": "appetite_suppression", "onset_date": MED_START.isoformat(),
        "recorded_at": stamper.stamp(MED_START),
    }
    rows.append(common.record("medical", **med_fields))

    for vd in _VISIT_DATES:
        entry_date = vd + timedelta(days=2)
        fields = {
            "date": entry_date.isoformat(), "slug": "glp1-medication", "kind": "visit",
            "title": "GLP-1 review, GP surgery", "severity": "none",
            "status": "active", "provider_type": "gp", "source": "athlete",
            "note": "routine titration check", "onset_date": vd.isoformat(),
            "recorded_at": stamper.stamp(entry_date),
        }
        rows.append(common.record("medical", **fields))
    return rows, _CHECK_DATES


def _checks(stamper: common.Stamper) -> list[dict]:
    rows = []
    for i, (cd, num) in enumerate(zip(_CHECK_DATES, _CHECK_NUMERATORS)):
        note = f"{num} of 14"
        if i == len(_CHECK_DATES) - 1:
            note = "12 of 14, twice this week"
        fields = {
            "date": cd.isoformat(), "slug": "stairs-check", "result": "fail",
            "value": num, "source": "athlete", "note": note,
            "recorded_at": stamper.stamp(cd),
        }
        rows.append(common.record("checks", **fields))
    return rows


# --- goals ---------------------------------------------------------------------


_GOAL_DATE = date(2030, 2, 10)


def _goals(stamper: common.Stamper) -> tuple[list[dict], date]:
    fields = {
        "date": _GOAL_DATE.isoformat(), "slug": "school-gate-walk",
        "title": "Walk to the school gate and back without stopping",
        "policy": "monotonic", "period": "none", "status": "active",
        "motivator": "Do the walk without needing to stop halfway",
        "rationale": "a capacity marker, not a number the medication gets credit for",
        "set_by": "athlete", "verification": "attested",
        "recorded_at": stamper.stamp(_GOAL_DATE),
    }
    return [common.record("goals", **fields)], _GOAL_DATE


# --- expectations (non-lie rows) --------------------------------------------------


def _e2(logged_pre_dates: list[date]) -> dict:
    return {
        "id": "rachel-E2", "kind": "gap", "dataset": "daily",
        "dates": [d.isoformat() for d in logged_pre_dates],
        "claim": ("pre-medication intake is logged on 22 days out of about "
                  "270, always around 1400 kcal"),
        "truth": ("a typical unlogged pre-medication day ran about 2600 "
                  "kcal; the 22 logged days are not a random sample, they "
                  "are the days she chose to log"),
        "expect": ("the engine should read 22 of about 270 days as "
                   "insufficient intake coverage for the pre-medication "
                   "period and refuse to compute any pre/post-medication "
                   "intake comparison from it, rather than treating the 22 "
                   "rows as the period's average"),
        "gap": ("coverage exists in the schema; the refusal wiring for a "
               "coverage-gated comparison is not fully built"),
    }


def _e3(end: date) -> dict:
    return {
        "id": "rachel-E3", "kind": "behavior", "dataset": "daily",
        "dates": [MED_START.isoformat(), end.isoformat()],
        "claim": ("daily intake runs about 1050 to 1200 kcal every day from "
                  "2030-02-03 onward"),
        "truth": ("this is the declared, involuntary effect of the "
                  "medication row (expects=appetite_suppression), not a "
                  "diet she is running or a lapse in adherence"),
        "expect": ("the engine should read post-medication intake against "
                   "the medication row's declared expectation, and neither "
                   "raise an intake-collapse tripwire nor credit the low "
                   "figure as willpower"),
        "gap": ("intake FLOOR semantics for an involuntary low intake are "
               "not modelled; the schema's low-intake machinery assumes a "
               "ceiling, not a floor to protect"),
    }


def _e4() -> dict:
    return {
        "id": "rachel-E4", "kind": "behavior", "dataset": "medical",
        "dates": [START.isoformat()],
        "claim": ("the knee restriction (no high-impact, stairs limited) "
                  "stands for the whole record, athlete-stated"),
        "truth": ("the restriction is real and never lifts in this record; "
                  "no check or precondition retires it"),
        "expect": ("nothing high-impact should ever be programmed or "
                   "suggested while this restriction stands, and any "
                   "explanation must cite the restriction row (class b), "
                   "never a diagnosis of what is wrong with her knee"),
        "gap": "none",
    }


def _e5(check_dates: list[date]) -> dict:
    return {
        "id": "rachel-E5", "kind": "gap", "dataset": "checks",
        "dates": [d.isoformat() for d in check_dates],
        "claim": "every stairs-check row reads result=fail",
        "truth": ("the real result is a fraction, '8 of 14' rising to '12 "
                  "of 14', which the schema cannot hold as a value; the "
                  "fraction survives only in the note"),
        "expect": ("the engine should read the fraction from the note "
                   "rather than inventing one, and must not treat an "
                   "unbroken run of fail results as evidence she is not "
                   "improving"),
        "gap": ("G79: a fractional check result has no schema-native home, "
               "only pass/fail plus prose"),
    }


def _e6(goal_date: date) -> dict:
    return {
        "id": "rachel-E6", "kind": "behavior", "dataset": "goals",
        "dates": [goal_date.isoformat()],
        "claim": ("her only goal is 'walk to the school gate and back "
                  "without stopping', verification attested"),
        "truth": ("there is no weight goal anywhere in the record; the "
                  "goal she set is capacity-based and binary"),
        "expect": ("the engine should hold this goal without inventing a "
                   "metric, a target or a percentage for it, and must "
                   "never substitute a weight-based target she explicitly "
                   "declined to set"),
        "gap": "none",
    }


_TOML = """# rachel: synthetic persona corpus, thresholds tuned to her record.
[targets]
phases = [[123.0, 112.0, 0.45]]

[tripwires]
pain_gate = 3

# Only four sources appear anywhere in this record; every one of them is
# listed here. Once [resolution] exists at all, an unlisted source is a hard
# validate failure, not a warning (handbook pitfall 4).
[resolution]
source_order = ["withings-scale", "phone", "myfitnesspal", "athlete"]

[resolution.precedence]
# The cleanest resolution-ladder test in the corpus (R1, see LIES.md): the
# phone recorded the walk directly; her own later, generous retelling of it
# never outranks that.
duration_s = ["phone", "athlete"]
distance_km = ["phone", "athlete"]
route = ["phone", "athlete"]
kcal_in = ["myfitnesspal"]
kg = ["withings-scale"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
