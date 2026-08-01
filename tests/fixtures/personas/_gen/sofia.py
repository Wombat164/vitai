"""Generator for the sofia persona (seed 102).

Valencia, Spain. 31, five months into a caesarean recovery, exclusively
breastfeeding baby Ines, on maternity leave from a lab-tech job. The record
runs six months, starting about four weeks after the birth. See `PROFILE.md`,
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

SEED = 102
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# The record's own calendar. Prose facts (PROFILE.md, WORLD.md), not derived
# from the CLI's `--end`: the story - four weeks postpartum through the
# medicated... no, non-medicated, physiologically-driven six months - is a
# fixed piece of her history, not a window that slides with wherever the
# corpus currently ends.
BIRTH = date(2029, 12, 4)
START = date(2030, 1, 2)                    # about four weeks postpartum
DEFAULT_END = date(2030, 6, 30)
CAESAREAN_RESOLVED = date(2030, 2, 12)       # about week 10 post-birth
PELVIC_CLEARED = date(2030, 4, 15)           # her own declaration, not a check

# The two stays at her mother's in Cuenca - no scale there, and the setting
# for lie S2 (LIES.md). Recorded_at lands on the day she travels home and
# catches the whole week's log up in one sitting - days after the earliest
# dates in the stay, which is the back-fill fingerprint itself. (It cannot
# land any LATER than the stay's own last day: `common.sort_rows` sorts the
# file primarily by the row's `date`, not by `recorded_at`, so a catch-up
# stamped after the very next ordinary same-day weigh-in would sort AHEAD of
# it in the file while carrying a LATER instant - an out-of-order
# `recorded_at`, which `vitai validate` rejects outright.)
CUENCA_STAYS = [
    (date(2030, 2, 14), date(2030, 2, 23), date(2030, 2, 23)),
    (date(2030, 5, 23), date(2030, 6, 1), date(2030, 6, 1)),
]
CUENCA_DATES_STAY1 = [date(2030, 2, 16), date(2030, 2, 18),
                      date(2030, 2, 20), date(2030, 2, 22), date(2030, 2, 23)]
CUENCA_DATES_STAY2 = [date(2030, 5, 25), date(2030, 5, 27),
                      date(2030, 5, 29), date(2030, 6, 1)]

# The route catalog from WORLD.md: two loops along the river park, the
# distances her pram walks (and later runs) repeat all record long.
ROUTES = {"riverpark-short": 2.4, "riverpark-long": 4.1}

# Weekly shape. Monday=0 .. Sunday=6.
CLASS_DAY = 1                     # Tuesday, postnatal class, all six months
WALK_DAYS = {0, 2, 4, 5}          # Monday, Wednesday, Friday, Saturday
FAMILY_SUNDAY_RATE = 0.4          # Sundays Marta joins, roughly two a month
RUN_FROM = date(2030, 5, 1)       # short runs ease in once clearance has held


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper()
    daily_stamper = common.Stamper()
    sessions_stamper = common.Stamper()
    medical_stamper = common.Stamper()
    goals_stamper = common.Stamper()
    context_stamper = common.Stamper()

    weight, cuenca_dates = _weight(rng, weight_stamper, end)
    daily = _daily(rng, daily_stamper, end)
    sessions = _sessions(rng, sessions_stamper, end)
    medical = _medical(medical_stamper)
    goals, weight_goal_date, kcal_goal_date = _goals(goals_stamper)
    context = _context(context_stamper)

    expectations = [
        _e1_underreported_intake(),
        _e2_memory_scale(cuenca_dates),
        _e3_unsafe_kcal_goal(kcal_goal_date),
        _e4_breastfeeding_state_unconsumed(),
        _e5_breastfeeding_energy_cost_gap(),
        _e6_pelvic_restriction_self_cleared(),
        _e7_weight_goal_shortfall(weight_goal_date, end),
    ]

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/medical.jsonl": common.jsonl_text(common.sort_rows(medical)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/context.jsonl": common.jsonl_text(common.sort_rows(context)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
    return files


# --- clock -------------------------------------------------------------------


def _spain_offset(d: date) -> str:
    """UTC offset for mainland Spain on a given date, approximated the same
    deliberately-simple way `common.irish_offset` approximates Irish Summer
    Time: fixed calendar dates (25 March to 25 October) rather than the exact
    last Sunday of the month. Winter is CET, `+01:00`; summer is CEST,
    `+02:00` - the numbers differ from Ireland's even though the window
    shape (EU-wide DST) does not.
    """
    if date(d.year, 3, 25) <= d <= date(d.year, 10, 25):
        return "+02:00"
    return "+01:00"


# --- weight --------------------------------------------------------------------


_WEIGHT_MILESTONES = [
    (date(2030, 1, 2), 76.0),
    (date(2030, 1, 31), 74.6),
    (date(2030, 2, 28), 74.5),   # Feb-Apr flat: the LIE S1 fingerprint
    (date(2030, 3, 31), 74.4),   # a claimed 1200-1350 kcal deficit would
    (date(2030, 4, 30), 74.3),   # imply roughly -0.6 kg/week; the measured
    (date(2030, 5, 31), 73.3),   # trend those months is about -0.1 kg/month
    (date(2030, 6, 30), 72.0),
]


def _target_kg(d: date) -> float:
    pts = _WEIGHT_MILESTONES
    for (d0, k0), (d1, k1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            frac = (d - d0).days / max(1, (d1 - d0).days)
            return k0 + (k1 - k0) * frac
    return pts[-1][1] if d > pts[-1][0] else pts[0][1]


def _in_cuenca(d: date) -> bool:
    return any(s <= d <= e for s, e, _ in CUENCA_STAYS)


def _weight(rng: random.Random, stamper: common.Stamper,
            end: date) -> tuple[list[dict], list[date]]:
    """Twice or three times a week from her own bathroom scale at home - a
    plain one, no app, no connector. During the two stays at her mother's in
    Cuenca the usual Monday/Thursday/Saturday rhythm stops (there is no scale
    there); nine rows for those weeks are entered later from memory instead
    (lie S2, see LIES.md).
    """
    rows: list[dict] = []
    for d in common.daterange(START, end):
        if d.weekday() not in (0, 3, 5):        # Monday, Thursday, Saturday
            continue
        if _in_cuenca(d):
            continue
        kg = _target_kg(d) + rng.gauss(0, 0.25)
        measured_at = f"07:{rng.randrange(10, 50):02d}"
        fields = {
            "date": d.isoformat(), "kg": round(kg, 1), "source": "scale",
            "measured_at": measured_at, "origin": "scale",
            "capture": "manual_entry", "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("weight", **fields))

    cuenca_dates: list[date] = []
    for stay_dates, (_, _, logged_at) in (
        (CUENCA_DATES_STAY1, CUENCA_STAYS[0]),
        (CUENCA_DATES_STAY2, CUENCA_STAYS[1]),
    ):
        for d in stay_dates:
            true_kg = _target_kg(d) + rng.gauss(0, 0.15)
            recalled_kg = true_kg - 0.8               # recalled low, LIES.md S2
            fields = {
                "date": d.isoformat(), "kg": round(recalled_kg, 1),
                "source": "scale", "origin": None,
                "capture": "narrative", "read_by": "athlete",
                "note": "from memory, logged the day we travelled home; no scale at Mama's",
                "recorded_at": stamper.stamp(logged_at),
            }
            rows.append(common.record("weight", **fields))
            cuenca_dates.append(d)
    return rows, cuenca_dates


# --- daily ---------------------------------------------------------------------


def _daily(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """kcal_in from an app, logged every single day (LIE S1: coverage looks
    perfect, the figure is not). Sleep, fragmented, self-estimated on about
    seven days in ten - no wearable, so there is nothing else in this file.
    """
    rows: list[dict] = []
    for d in common.daterange(START, end):
        kcal = max(1200, min(1350, int(rng.gauss(1270, 40))))
        fields = {
            "date": d.isoformat(), "kcal_in": kcal, "source": "myfitnesspal",
            "coverage": "full", "capture": "manual_entry",
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("daily", **fields))
        if rng.random() < 0.7:
            sleep_h = round(rng.uniform(3.0, 5.0), 1)
            sfields = {
                "date": d.isoformat(), "sleep_h": sleep_h, "source": "athlete",
                "coverage": "partial", "capture": "manual_entry",
                "recorded_at": stamper.stamp(d),
            }
            rows.append(common.record("daily", **sfields))
    return rows


# --- sessions ------------------------------------------------------------------


def _sessions(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Postnatal class every Tuesday all record long (low-impact, so it
    never conflicts with the impact restriction), pram walks tracked by
    phone, and - once the pelvic-floor clearance has held for a couple of
    weeks - short runs on the same phone-tracked routes. No pool session
    anywhere: the swimmer identity she means to return to never quite
    happens in this record (see FINDINGS.md, PROFILE.md).
    """
    rows: list[dict] = []
    for d in common.daterange(START, end):
        if d.weekday() == CLASS_DAY:
            rows.append(_postnatal_class(rng, stamper, d))
        if d.weekday() in WALK_DAYS:
            rows.append(_pram_or_run(rng, stamper, d))
        elif d.weekday() == 6 and rng.random() < FAMILY_SUNDAY_RATE:
            rows.append(_family_sunday_walk(rng, stamper, d))
    return rows


def _postnatal_class(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    duration_s = int(rng.gauss(50 * 60, 4 * 60))
    fields = {
        "date": d.isoformat(), "type": "mobility", "duration_s": duration_s,
        "rpe": rng.choice([2, 3, 3, 4]),
        "note": "postnatal class, civic centre",
        "source": "athlete",
        "start_time": f"{d.isoformat()}T10:30:00{_spain_offset(d)}",
        "setting": "indoor", "place": "civic centre",
        "with": "Lucia", "context": "social",
        "type_source": "athlete-stated", "capture": "manual_entry",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _pram_or_run(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    running = d >= RUN_FROM and rng.random() < 0.4
    if running:
        route, kmh = "riverpark-short", rng.uniform(7.5, 9.0)
        distance = ROUTES[route]
        duration_s = int(distance / kmh * 3600 + rng.uniform(-30, 30))
        session_type = "run"
        rpe = rng.choice([4, 5, 5, 6])
    else:
        route = rng.choice(["riverpark-short", "riverpark-long"])
        distance = ROUTES[route]
        pace_min_per_km = rng.uniform(13.0, 16.0)     # pram pace, unhurried
        duration_s = int(distance * pace_min_per_km * 60 + rng.uniform(-60, 60))
        session_type = "walk"
        rpe = rng.choice([2, 2, 3])
    start_time = (f"{d.isoformat()}T{rng.randrange(9, 12):02d}"
                  f":{rng.randrange(0, 59):02d}:00{_spain_offset(d)}")
    fields = {
        "date": d.isoformat(), "type": session_type, "distance_km": round(distance, 1),
        "duration_s": max(60, duration_s), "rpe": rpe,
        "source": "phone", "start_time": start_time, "setting": "outdoor",
        "route": route, "place": "home", "with": None, "context": "solo",
        "weather": rng.choice(["dry", "dry", "hot", "wind", "rain"]),
        "type_source": "vendor-classified", "capture": "connector",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _family_sunday_walk(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    route = "riverpark-long"
    distance = ROUTES[route]
    pace_min_per_km = rng.uniform(14.0, 17.0)
    duration_s = int(distance * pace_min_per_km * 60 + rng.uniform(-60, 60))
    fields = {
        "date": d.isoformat(), "type": "walk", "distance_km": round(distance, 1),
        "duration_s": max(60, duration_s), "rpe": rng.choice([2, 3]),
        "source": "phone", "start_time": f"{d.isoformat()}T11:00:00{_spain_offset(d)}",
        "setting": "outdoor", "route": route, "place": "home", "with": "Marta",
        "context": "family", "weather": rng.choice(["dry", "hot", "wind"]),
        "type_source": "vendor-classified", "capture": "connector",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


# --- medical -------------------------------------------------------------------


def _medical(stamper: common.Stamper) -> list[dict]:
    rows = []

    onset = BIRTH
    fields = {
        "date": START.isoformat(), "slug": "caesarean-section", "kind": "injury",
        "title": "Caesarean section, healing", "body_site": "abdomen",
        "severity": "moderate", "status": "active", "restricts": "impact",
        "restriction": "pattern=carry region=abdomen load=loaded",
        "provider_type": "gp", "source": "athlete",
        "note": "wound checked at the postnatal review, healing as expected",
        "onset_date": onset.isoformat(), "recorded_at": stamper.stamp(START),
    }
    rows.append(common.record("medical", **fields))
    fields2 = {
        "date": (CAESAREAN_RESOLVED + timedelta(days=1)).isoformat(),
        "slug": "caesarean-section", "kind": "injury",
        "title": "Caesarean section, healing", "body_site": "abdomen",
        "severity": "moderate", "status": "resolved",
        "resolved_date": CAESAREAN_RESOLVED.isoformat(),
        "restricts": "impact",
        "restriction": "pattern=carry region=abdomen load=loaded",
        "provider_type": "gp", "source": "athlete",
        "note": "GP happy with the scar at the ten-week check",
        "onset_date": onset.isoformat(),
        "recorded_at": stamper.stamp(CAESAREAN_RESOLVED + timedelta(days=1)),
    }
    rows.append(common.record("medical", **fields2))

    fields3 = {
        "date": (START + timedelta(days=3)).isoformat(),
        "slug": "pelvic-floor-restriction", "kind": "restriction",
        "title": "No high-impact activity until the pelvic floor feels solid",
        "body_site": "pelvis", "severity": "mild", "status": "active",
        "restricts": "impact", "restriction": "activity=impact region=pelvis",
        "provider_type": None, "source": "athlete",
        "note": "her own precaution, nobody told her to; no check attached, she will say when",
        "onset_date": BIRTH.isoformat(),
        "recorded_at": stamper.stamp(START + timedelta(days=3)),
    }
    rows.append(common.record("medical", **fields3))
    fields4 = {
        "date": PELVIC_CLEARED.isoformat(), "slug": "pelvic-floor-restriction",
        "kind": "restriction",
        "title": "No high-impact activity until the pelvic floor feels solid",
        "body_site": "pelvis", "severity": "mild", "status": "resolved",
        "resolved_date": PELVIC_CLEARED.isoformat(), "restricts": "impact",
        "restriction": "activity=impact region=pelvis", "provider_type": None,
        "source": "athlete",
        "note": "she says she is ready; nobody checked, nobody needed to",
        "onset_date": BIRTH.isoformat(),
        "recorded_at": stamper.stamp(PELVIC_CLEARED),
    }
    rows.append(common.record("medical", **fields4))

    fields5 = {
        "date": (START + timedelta(days=1)).isoformat(), "slug": "breastfeeding",
        "kind": "state", "title": "Exclusively breastfeeding",
        "severity": "none", "status": "active", "source": "athlete",
        "note": "feeding on demand; appetite is relentless and she knows it",
        "expects": "elevated_requirement", "onset_date": BIRTH.isoformat(),
        "recorded_at": stamper.stamp(START + timedelta(days=1)),
    }
    rows.append(common.record("medical", **fields5))
    return rows


# --- goals ---------------------------------------------------------------------


_WEIGHT_GOAL_DATE = date(2030, 1, 10)
_KCAL_GOAL_DATE = date(2030, 1, 10)


def _goals(stamper: common.Stamper) -> tuple[list[dict], date, date]:
    # `goals` has its own `dataset` field (which vitai dataset the metric
    # reads from), and it collides by name with `common.record`'s own
    # `dataset` positional argument (which vitai dataset this ROW belongs
    # to). Passing `dataset=...` through `**kw` to `common.record("goals",
    # **fields)` raises "got multiple values for argument 'dataset'" - build
    # the skeleton first, then update it, instead of routing the goal's own
    # `dataset` key through the call that picks the schema table.
    weight_fields = {
        "date": _WEIGHT_GOAL_DATE.isoformat(), "slug": "lose-10kg-by-summer",
        "title": "Lose 10 kg by summer", "metric": "kg", "dataset": "weight",
        "target": 66.0, "policy": "monotonic", "period": "none",
        "deadline": "2030-06-21", "deadline_kind": "soft", "status": "active",
        "motivator": "feel like herself again before the summer",
        "rationale": "a round number, picked before she had any sense of the pace",
        "on_success": "hold", "on_miss": "reassess", "set_by": "athlete",
        "recorded_at": stamper.stamp(_WEIGHT_GOAL_DATE),
    }
    kcal_fields = {
        "date": _KCAL_GOAL_DATE.isoformat(), "slug": "kcal-1200-breastfeeding",
        "title": "Cap daily intake at 1200 kcal", "metric": "kcal_in",
        "dataset": "daily", "target": 1200, "policy": "monotonic",
        "period": "none", "status": "proposed",
        "motivator": "get back into her pre-pregnancy jeans faster",
        "rationale": "cut hard while she still has the will for it",
        "set_by": "athlete",
        "note": "self-set while exclusively breastfeeding; never promoted past proposed",
        "recorded_at": stamper.stamp(_KCAL_GOAL_DATE),
    }
    weight_row = common.record("goals")
    weight_row.update(weight_fields)
    kcal_row = common.record("goals")
    kcal_row.update(kcal_fields)
    rows = [weight_row, kcal_row]
    return rows, _WEIGHT_GOAL_DATE, _KCAL_GOAL_DATE


# --- context ---------------------------------------------------------------------


def _context(stamper: common.Stamper) -> list[dict]:
    rows = []
    for start, endd, logged_at in CUENCA_STAYS:
        fields = {
            "date": start.isoformat(), "mode": "travel",
            "facilities": "none",
            "place": "Cuenca, her mother's",
            "source": "athlete",
            "note": "no scale there; the walk routine stops too",
            "recorded_at": stamper.stamp(logged_at),
        }
        rows.append(common.record("context", **fields))
    return rows


# --- expectations ------------------------------------------------------------


def _e1_underreported_intake() -> dict:
    return {
        "id": "sofia-E1", "kind": "lie", "dataset": "daily",
        "dates": [START.isoformat(), "2030-02-28", "2030-04-30"],
        "claim": ("daily intake logged every day, 2030-01-02 through "
                  "2030-06-30, consistently about 1200 to 1350 kcal"),
        "truth": ("a typical actual day ran about 1750 to 1900 kcal "
                  "(untracked grazing while feeding); the logged figure is "
                  "not what she eats, it is what she means to eat. The "
                  "fingerprint sits in the weight record, not the intake "
                  "record: weight is essentially flat from February through "
                  "April (about -0.1 kg/month), while the claimed intake "
                  "implies a deficit of roughly -0.6 kg/week over the same "
                  "months"),
        "expect": ("the engine should state the arithmetic inconsistency "
                   "between reported intake and measured weight trend as an "
                   "observation about the record - claimed intake and "
                   "measured weight are not consistent with each other, and "
                   "the record does not say which figure is wrong - and "
                   "refuse to tighten any intake target on the strength of "
                   "the claimed figure. It must never accuse her of "
                   "under-reporting; it has no basis to conclude that "
                   "either, only that the two series disagree"),
        "gap": ("no automated energy-balance cross-check between reported "
               "kcal_in and the measured weight trend exists in the engine "
               "today; this expectation documents what one should conclude "
               "once it does"),
    }


def _e2_memory_scale(cuenca_dates: list[date]) -> dict:
    return {
        "id": "sofia-E2", "kind": "lie", "dataset": "weight",
        "dates": [d.isoformat() for d in cuenca_dates],
        "claim": ("nine weight rows during two stays at her mother's in "
                  "Cuenca, source 'scale' like every other row, recorded "
                  "several days after the stay ends"),
        "truth": ("there was no scale at her mother's; the values are "
                  "remembered, not measured, and run about 0.8 kg low "
                  "against what the ordinary weekly trend implies for those "
                  "dates"),
        "expect": ("capture=narrative plus a recorded_at several days after "
                   "date should rank these rows below the ordinary "
                   "capture=manual_entry home-scale rows, and the trend "
                   "engine should not anchor on them; a rate estimate that "
                   "reads through a Cuenca window as a sudden dip should be "
                   "treated as low-confidence, not as progress"),
        "gap": ("the resolution ladder in vitai.toml ranks by source string "
               "(section 3 of the handbook); here every row, true and "
               "recalled alike, carries the identical source 'scale', so a "
               "source-keyed ladder cannot separate them - only the capture "
               "field can, and nothing in the engine ranks weight rows by "
               "capture today. There is also no same-day conflict to force "
               "supersedes or a resolution decision: these are simply extra "
               "points on the trend line the engine has no reason to "
               "distrust"),
    }


def _e3_unsafe_kcal_goal(kcal_goal_date: date) -> dict:
    return {
        "id": "sofia-E3", "kind": "behavior", "dataset": "goals",
        "dates": [kcal_goal_date.isoformat()],
        "claim": ("she self-set a 1200 kcal/day intake target "
                  "('kcal-1200-breastfeeding'), status 'proposed'"),
        "truth": ("she is exclusively breastfeeding for the whole record "
                  "(medical.jsonl, expects=elevated_requirement); a further "
                  "deficit on top of an already under-reported intake is "
                  "not something anything here should encourage"),
        "expect": ("the engine must refuse to program a deficit toward this "
                   "target and say only that: a self-constraint, not a "
                   "judgement of her plan. The goal stays at status "
                   "'proposed' in the record and the engine must never "
                   "promote it toward 'active' or generate a programme "
                   "aimed at it while breastfeeding is declared"),
        "gap": "none",
    }


def _e4_breastfeeding_state_unconsumed() -> dict:
    return {
        "id": "sofia-E4", "kind": "gap", "dataset": "medical",
        "dates": [(START + timedelta(days=1)).isoformat()],
        "claim": ("a medical row declares kind=state, "
                  "expects=elevated_requirement, for the whole record"),
        "truth": ("the declaration is present in the record from the second "
                  "day onward and never lifts"),
        "expect": ("nothing that reads intake or weight tripwires should "
                   "treat her low or flat numbers as noncompliance while "
                   "this state stands; any verdict touching kcal_in or "
                   "weight rate should read this row first"),
        "gap": ("G57: the state exists as a value the schema can hold "
               "(kind=state plus an expects token) but nothing in the "
               "engine's verdict path currently reads it - it is written, "
               "not consumed. The declaration is a physiological state, not "
               "a condition, and citing it is class (b): what the engine "
               "will not do given what was declared, never a comment on "
               "her physiology"),
    }


def _e5_breastfeeding_energy_cost_gap() -> dict:
    return {
        "id": "sofia-E5", "kind": "gap", "dataset": "medical",
        "dates": [(START + timedelta(days=1)).isoformat()],
        "claim": "expects=elevated_requirement names the effect, not its size",
        "truth": ("breastfeeding adds a real, roughly-known energy cost "
                  "(commonly estimated at several hundred kcal a day) that "
                  "nothing in this record can express as a number"),
        "expect": ("even a hypothetical future energy-balance cross-check "
                   "(see sofia-E1) could never fully correct for this term: "
                   "it can know a state is declared, never by how much it "
                   "changes the arithmetic. Any such check must stop at "
                   "'these figures are inconsistent' and go no further, "
                   "because it structurally cannot separate the "
                   "under-report from a real, unmeasured elevated need"),
        "gap": ("the EXPECTATIONS vocabulary (elevated_requirement, "
               "rapid_loss, appetite_suppression, lean_mass_risk) is "
               "qualitative only; there is no schema field for a "
               "declared or estimated kcal delta a physiological state "
               "adds or removes from an energy-balance calculation"),
    }


def _e6_pelvic_restriction_self_cleared() -> dict:
    return {
        "id": "sofia-E6", "kind": "behavior", "dataset": "medical",
        "dates": [(START + timedelta(days=3)).isoformat(),
                 PELVIC_CLEARED.isoformat()],
        "claim": ("the pelvic-floor restriction (no high-impact activity) "
                  "opens on her own say-so and closes on her own say-so, "
                  "2029-12-04 to 2030-04-15"),
        "truth": ("no clinician sign-off and no check or precondition row "
                  "appears anywhere in the record for this restriction; "
                  "both the opening and the closing declaration are "
                  "source=athlete. The record itself shows the gate "
                  "working: every session before 2030-04-15 is a walk or "
                  "the low-impact postnatal class, type=mobility, never a "
                  "run; the first run in the record falls in May, weeks "
                  "after the restriction resolves"),
        "expect": ("nothing high-impact should ever be programmed or "
                   "suggested while restricts=impact stands on an active "
                   "row, and the restriction should lift exactly when she "
                   "declares it, with no external verification demanded. "
                   "Any explanation must cite the restriction row (class "
                   "b), never a diagnosis of why her pelvic floor needed "
                   "the caution"),
        "gap": "none",
    }


def _e7_weight_goal_shortfall(weight_goal_date: date, end: date) -> dict:
    return {
        "id": "sofia-E7", "kind": "behavior", "dataset": "goals",
        "dates": [weight_goal_date.isoformat(), end.isoformat()],
        "claim": "goal 'lose-10kg-by-summer' targets 66.0 kg by 2030-06-21",
        "truth": ("measured weight reaches about 72.0 kg by 2030-06-30, "
                  "roughly 6 kg short of the target and past its deadline; "
                  "the 10 kg figure was picked before she had any sense of "
                  "the pace (rationale field says so directly)"),
        "expect": ("the engine may report the goal as missed against the "
                   "measured record (an observation), but must not use the "
                   "shortfall to justify tightening intake or programming a "
                   "larger deficit while the breastfeeding state and the "
                   "still-proposed kcal goal both stand"),
        "gap": "none",
    }


_TOML = """# sofia: synthetic persona corpus, thresholds tuned to her record.
[targets]
phases = [[76.0, 66.0, 0.35]]

[tripwires]
sleep_floor_h = 5.0

# Only four sources appear anywhere in this record; every one of them is
# listed here. Once [resolution] exists at all, an unlisted source is a hard
# validate failure, not a warning (handbook pitfall 4).
[resolution]
source_order = ["scale", "myfitnesspal", "phone", "athlete"]

[resolution.precedence]
kg = ["scale"]
kcal_in = ["myfitnesspal"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
