"""Generator for the maja persona (seed 113).

Ljubljana, Slovenia. 29, trains for hypertrophy four days a week, almost
entirely on machines. Nine months, from 2029-10-01 to 2030-06-30.

THE AXIS SHE STRESSES IS THAT A SETTING IS PART OF THE MEASUREMENT. The other
strength records in this corpus log an exercise, a load and some reps, which
is enough for a barbell and not enough for a machine: the same stack pin at
seat position 3 and seat position 5 is a different exercise on the same
frame, and a leg press at 45 degrees is not a leg press at 30. Her sets carry
the seat, the pad, the lever, the angle and the resistance level, so the
corpus finally contains a record where "the same lift" is a question with an
answer rather than an assumption.

Two more things she carries that the corpus did not have.

FOOD READ OFF A PACKET. She logs from the label, so her `meals` rows hold what
the label states per hundred grams - energy, protein, fat, carbohydrate, and
also fibre, sugar and sodium, which no other record has. The label is the
source and it is often rounded, sometimes to the nearest gram on a 30 g
portion, which is a real error mode that arrives with the packaging rather
than with her.

A GOAL THAT IS A BAND. Her protein target is 130 to 160 g, not "at least 130".
A range has an upper bound that is not a failure, which is a different shape
from a floor with a ceiling stacked on it, and nothing else in this corpus
declares one.

She also carries the corpus's only `plans` rows outside the demo, and the only
`events` row that says why it was cancelled.

See `PROFILE.md`, `LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md`
alongside this file for the prose these numbers have to agree with. Entirely
synthetic; any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself.
"""

from __future__ import annotations

import random
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

from . import common

SEED = 113
PERSONA_VERSION: int = 1

START = date(2029, 10, 1)
DEFAULT_END = date(2030, 6, 30)

_TOML = """# maja - Ljubljana. Machines, labels, and a protein band.
[athlete]
timezone = "Europe/Ljubljana"

[targets]
phases = [[61.0, 62.5, 0.15]]

[tripwires]
steps_floor = 4000
sleep_floor_h = 7.0

[resolution]
source_order = ["scale", "app", "watch", "hand"]
"""

# The four sessions she rotates, and the settings that make each one the same
# movement week to week. A seat position is not a preference: it decides which
# part of the range the load sits in, so a set logged without it cannot be
# compared with the same set next month.
MACHINES = {
    "leg-press": {"exercise": "leg_press", "machine": "plate-loaded sled",
                  "angle_class": "incline", "angle_deg": 45,
                  "seat_pos": 3, "pad_pos": None, "lever_pos": 2},
    "chest-press": {"exercise": "chest_press", "machine": "selectorised",
                    "angle_class": "flat", "angle_deg": None,
                    "seat_pos": 4, "pad_pos": 2, "lever_pos": None},
    "row": {"exercise": "seated_row", "machine": "selectorised",
            "angle_class": "flat", "angle_deg": None,
            "seat_pos": 2, "pad_pos": 3, "lever_pos": None},
    "leg-curl": {"exercise": "leg_curl", "machine": "selectorised",
                 "angle_class": None, "angle_deg": None,
                 "seat_pos": None, "pad_pos": 4, "lever_pos": 3},
}

ROTATION = [["leg-press", "leg-curl"], ["chest-press", "row"]]


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _offset(local: datetime) -> str:
    march, october = _last_sunday(local.year, 3), _last_sunday(local.year, 10)
    day = local.date()
    if day < march or day > october:
        return "+01:00"
    if day == march:
        return "+01:00" if local.hour < 2 else "+02:00"
    if day == october:
        return "+02:00" if local.hour < 3 else "+01:00"
    return "+02:00"


def _delta(local: datetime) -> timedelta:
    return timedelta(hours=2) if _offset(local) == "+02:00" else timedelta(hours=1)


def _aware(local: datetime) -> str:
    return local.replace(tzinfo=timezone(_delta(local))).isoformat()


def _interval(local_start: datetime, hours: float) -> tuple[str, str]:
    began = local_start.replace(tzinfo=timezone(_delta(local_start)))
    instant = began + timedelta(hours=hours)
    naive_end = instant.replace(tzinfo=None) + _delta(local_start)
    ended = instant.astimezone(timezone(_delta(naive_end)))
    return began.isoformat(), ended.isoformat()


# --- data ----------------------------------------------------------------------

def _daily(rng: random.Random, stamp: common.Stamper, end: date) -> list[dict]:
    """Steps, sleep and the whole macro row.

    THE MACROS ARE THE FIXTURE HALF NOBODY ELSE HAS. Other records carry energy
    and protein; hers carries carbohydrate, fat, fibre, sugar and sodium as
    well, because she logs off labels and the label states them. A consumer
    that only ever met `kcal_in` and `protein_g` has never had to decide what
    to do with the rest.
    """
    rows = []
    for d in common.daterange(START, end):
        hours = round(max(5.5, min(9.5, rng.gauss(7.6, 0.7))), 1)
        began = (datetime.combine(d, dtime()) - timedelta(days=1)
                 + timedelta(hours=23, minutes=rng.randrange(-40, 50, 5)))
        start, ended = _interval(began, hours)
        protein = round(rng.gauss(142, 16))
        carb = round(rng.gauss(210, 40))
        fat = round(rng.gauss(66, 12))
        rows.append(common.record(
            "daily", date=d.isoformat(),
            steps=max(2000, int(rng.gauss(7400, 2000))),
            sleep_h=hours, sleep_start=start, sleep_end=ended,
            kcal_in=round(protein * 4 + carb * 4 + fat * 9),
            protein_g=protein, carb_g=carb, fat_g=fat,
            fibre_g=round(rng.gauss(27, 6)),
            sugar_g=round(rng.gauss(58, 18)),
            sodium_mg=round(rng.gauss(2400, 500)),
            source="app", capture="manual_entry", origin="app",
            coverage="full", recorded_at=stamp.stamp(d)))
    return rows


def _sessions(rng: random.Random, stamp: common.Stamper,
              end: date) -> list[dict]:
    rows = []
    for d in common.daterange(START, end):
        if d.weekday() not in (0, 1, 3, 4):
            continue
        if rng.random() > 0.88:
            continue
        began = datetime.combine(d, dtime(hour=17, minute=45))
        rows.append(common.record(
            "sessions", date=d.isoformat(), type="strength",
            duration_s=rng.randrange(45, 80, 5) * 60,
            start_time=_aware(began), place="gym", setting="indoor",
            source="app", capture="manual_entry", origin="app",
            rpe=rng.randrange(5, 9), rpe_scale="borg-cr10",
            recorded_at=stamp.stamp(d)))
    return rows


def _sets(rng: random.Random, stamp: common.Stamper,
          sessions: list[dict]) -> list[dict]:
    """Three working sets per machine, with the settings that identify them.

    THE SETTINGS TRAVEL WITH EVERY SET, not with the exercise. She writes them
    down because she has been given the wrong seat height by a well-meaning
    stranger more than once and could not tell afterwards whether a bad session
    was her or the chair. A record that holds the load and not the seat cannot
    answer that question either.

    `side` is `bilateral` throughout except the leg curl, which she works one
    leg at a time after an old imbalance - so the corpus finally has a set
    where laterality is a real fact rather than an unused column.
    """
    rows = []
    for i, session in enumerate(sessions):
        d = date.fromisoformat(session["date"])
        for slot, key in enumerate(ROTATION[i % 2]):
            m = MACHINES[key]
            base = {"leg-press": 120, "chest-press": 45, "row": 52,
                    "leg-curl": 38}[key]
            drift = base * 0.0006 * (d - START).days
            for index in range(3):
                load = round((base + drift) * (1 - 0.05 * index) / 2.5) * 2.5
                reps = rng.randrange(8, 13)
                rows.append(common.record(
                    "sets", date=d.isoformat(),
                    session_start=session["start_time"],
                    exercise=m["exercise"], block=1, round=slot + 1,
                    set_index=index + 1,
                    reps_completed=reps, reps_attempted=reps,
                    load=load,
                    # A PLATE-LOADED SLED CARRIES A MASS; A SELECTORISED
                    # STACK CARRIES A PIN. The sled takes discs she can weigh,
                    # so its number is kilograms. The stack's number is the
                    # position of a pin in a column, and calling that
                    # kilograms would say the two machines' numbers can be
                    # added up. They cannot, and the schema refuses it.
                    load_type=("external" if m["machine"] == "plate-loaded sled"
                               else "machine_stack"),
                    load_unit=("kg" if m["machine"] == "plate-loaded sled"
                               else None),
                    machine=m["machine"], set_type="working",
                    failure=None, rir=rng.randrange(1, 4),
                    rest_s=rng.choice([90, 120, 150]),
                    tempo="3-1-1-0", duration_s=reps * 5,
                    side="left" if key == "leg-curl" and index % 2 == 0
                         else ("right" if key == "leg-curl" else "bilateral"),
                    equipment="machine", angle_class=m["angle_class"],
                    angle_deg=m["angle_deg"], resistance_level=None,
                    seat_pos=m["seat_pos"], pad_pos=m["pad_pos"],
                    lever_pos=m["lever_pos"],
                    source="app", capture="manual_entry", origin="app",
                    read_by=None,
                    recorded_at=stamp.stamp(d)))
    return rows


def _meals(stamp: common.Stamper) -> list[dict]:
    """A week of logging off packaging, with what the label actually states.

    THE LABEL IS THE SOURCE and it is rounded. A 30 g portion of something
    stated to the nearest gram per hundred carries an error the athlete did
    not make and cannot remove, which is a different kind of wrongness from a
    guess - and `food_table` says which label it came off.
    """
    day = date(2030, 3, 11)
    items = [
        ("breakfast", "skyr, plain", 200, 63, 11.0, 0.2, 4.0, 0.0, 4.0, 50),
        ("breakfast", "oats", 80, 372, 13.0, 7.0, 59.0, 10.0, 1.0, 8),
        ("lunch", "rye bread", 120, 240, 8.0, 1.5, 44.0, 7.0, 2.0, 480),
        ("lunch", "tinned mackerel", 110, 205, 19.0, 14.0, 0.0, 0.0, 0.0, 380),
        ("dinner", "chicken thigh", 180, 177, 24.0, 9.0, 0.0, 0.0, 0.0, 82),
        ("dinner", "rice, dry", 90, 349, 7.0, 1.0, 78.0, 1.4, 0.1, 5),
        ("snack", "protein bar", 60, 348, 32.0, 11.0, 30.0, 9.0, 1.6, 260),
    ]
    out = []
    for meal, item, grams, kcal, pro, fat, carb, fibre, sugar, sodium in items:
        out.append(common.record(
            "meals", date=day.isoformat(), meal=meal, item=item,
            grams=grams, kcal_100g=kcal, protein_100g=pro, fat_100g=fat,
            carb_100g=carb, fibre_100g=fibre, sugar_100g=sugar,
            sodium_mg_100g=sodium, food_table="packaging",
            source="app", capture="manual_entry", origin="app",
            read_by="athlete",
            note="off the packet; the label rounds and she does not",
            recorded_at=stamp.stamp(day)))
    return out


def _goals(stamp: common.Stamper) -> list[dict]:
    """One of them is a BAND, which nothing else in the corpus declares."""
    d0 = START.isoformat()
    return [
        common.record(
            "goals", date=d0, slug="protein-band",
            title="Between 130 and 160 g of protein",
            metric="protein_g", dataset="daily", target=130, target_hi=160,
            polarity="band", period="daily", policy="monotonic",
            tracker="mean", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="enough to build on and not so much it crowds out food "
                      "I like",
            rationale="a range, because the top of it is not a failure",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START)),
        common.record(
            "goals", date=d0, slug="four-sessions",
            title="Four gym days a week",
            metric="sessions", dataset="sessions", session_type="strength",
            target=4, polarity="floor", period="weekly", policy="monotonic",
            tracker="count", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="the programme only works if it is all of it",
            rationale="four is what the split needs",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START)),
    ]


def _plans(stamp: common.Stamper) -> list[dict]:
    """A plan made, and one that did not survive contact with the week."""
    return [
        common.record(
            "plans", date="2030-02-24", slug="week-of-24-feb",
            for_date="2030-02-26", activity="strength", setting="indoor",
            tier="programme", serves="four-sessions", set_by="athlete",
            requires="gym", outcome="completed", reason=None,
            session_ref=None, note=None,
            recorded_at=stamp.stamp(date(2030, 2, 24))),
        common.record(
            "plans", date="2030-02-24", slug="week-of-24-feb-thu",
            for_date="2030-02-28", activity="strength", setting="indoor",
            tier="programme", serves="four-sessions", set_by="athlete",
            requires="gym", outcome="skipped",
            reason="opportunity_physical",
            session_ref=None,
            note="the gym shut early for a burst pipe",
            recorded_at=stamp.stamp(date(2030, 2, 24))),
    ]


def _events(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "events", date="2030-01-06", slug="gym-closure",
            title="Gym closed for refurbishment", kind="life",
            event_date="2030-04-07", priority="b", immovable=True,
            place="gym", status="cancelled", set_by="athlete",
            reason="the works were postponed to the autumn and the week ran "
                   "as normal",
            note=None, outcome=None,
            recorded_at=stamp.stamp(date(2030, 1, 6))),
    ]


def _thresholds(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "thresholds", date=START.isoformat(), key="sleep_floor_h",
            value=7.0, change_kind="change", set_by="athlete",
            reason="she recovers badly under it and can tell by Wednesday",
            note="stated at the start rather than discovered, so there is no "
                 "period of this record judged by the toml",
            recorded_at=stamp.stamp(START)),
    ]


def _journal(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "journal", date="2029-10-02", kind="preference",
            text="write down the seat number. I have been put on the wrong "
                 "one twice and could not tell afterwards whether the session "
                 "was bad or the chair was",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2029, 10, 2))),
        common.record(
            "journal", date="2030-03-11", kind="claim",
            text="I hit my protein every single day this week",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2030, 3, 11))),
    ]


def _expectations() -> list[dict]:
    return [
        {"id": "maja-B-01", "kind": "behavior",
         "expect": "Two sets of the same exercise at different seat, pad or "
                   "lever positions are not compared as the same movement "
                   "without the difference being visible.",
         "truth": "Every set carries the settings that identify it. The corpus "
                  "had no record in which a machine position was written down "
                  "at all, so nothing could distinguish them."},
        {"id": "maja-B-02", "kind": "behavior",
         "expect": "The upper bound of a band goal is not reported as a "
                   "failure when it is reached.",
         "truth": "Her protein goal is 130 to 160 g, declared with both bounds. "
                  "A range is a different shape from a floor with a ceiling "
                  "stacked on it and nothing else in the corpus declares one."},
        {"id": "maja-G-01", "kind": "gap",
         "expect": "A rounded label value is not reported as a precise "
                   "measurement.",
         "truth": "Her meals come off packaging, where per-hundred-gram figures "
                  "are rounded before she ever sees them. The error arrives "
                  "with the packet and cannot be removed by logging carefully."},
        {"id": "maja-G-02", "kind": "gap",
         "expect": "A cancelled event with a stated reason is distinguishable "
                   "from one that simply passed.",
         "truth": "The April gym closure was cancelled because the works moved "
                  "to the autumn. The row says so."},
        {"id": "maja-L-01", "kind": "lie",
         "expect": "The engine observes the record and reports what it holds, "
                   "without correcting her.",
         "truth": "Her claim of 2030-03-11 that she hit her protein every day "
                  "that week is not supported by her own rows: the logged "
                  "week has days below the lower bound of her band."},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    daily = _daily(rng, common.Stamper(base_hour=22), end)
    sessions = _sessions(rng, common.Stamper(base_hour=19), end)
    sets = _sets(rng, common.Stamper(base_hour=19), sessions)

    return {
        "vitai.toml": _TOML,
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/sets.jsonl": common.jsonl_text(common.sort_rows(sets)),
        "data/meals.jsonl": common.jsonl_text(common.sort_rows(
            _meals(common.Stamper(base_hour=21)))),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(
            _goals(common.Stamper(base_hour=10)))),
        "data/plans.jsonl": common.jsonl_text(common.sort_rows(
            _plans(common.Stamper(base_hour=9)))),
        "data/events.jsonl": common.jsonl_text(common.sort_rows(
            _events(common.Stamper(base_hour=9)))),
        "data/thresholds.jsonl": common.jsonl_text(common.sort_rows(
            _thresholds(common.Stamper(base_hour=10)))),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(
            _journal(common.Stamper(base_hour=22)))),
        "expectations.jsonl": common.jsonl_text(_expectations()),
        "persona.toml": common.persona_toml(
            "maja", PERSONA_VERSION, SEED,
            (START.isoformat(), end.isoformat())),
    }
