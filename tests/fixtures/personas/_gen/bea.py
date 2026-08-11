"""Generator for the bea persona (seed 111).

Ghent, Belgium. 34, intensive-care nurse on a rotating roster: three or four
twelve-hour nights, then days off, then a stretch of days. Ten months, from
2029-09-03 to 2030-06-30. She swims and lifts, both fitted around whichever
half of the clock she is currently living in.

THE AXIS SHE STRESSES IS THAT HER DAY DOES NOT START AT MIDNIGHT. Every other
persona in this corpus sleeps at night, so an engine anchoring a day to the
calendar and an engine anchoring it to sleep agree on all of them, and the
corpus cannot tell the two apart. After a night shift bea sleeps from about
09:00 to 16:00. Her main meal is at 17:00, her session is at 18:30, and the
day she would call "the morning" begins in the afternoon.

Three consequences the corpus could not previously demonstrate:

A SESSION AT 18:30 IS NOT AN EVENING SESSION. The clock says evening; her own
day says it is the first thing she did after waking. Any part-of-day label
derived from the wall clock is wrong for her on every shift night, and right
for every other persona, which is exactly the shape that makes a wrong default
survive review.

ONE NIGHT'S SLEEP LANDS ON TWO DATES, OR ON NEITHER. Sleeping 09:00 to 16:00
happens entirely inside one calendar day; a `daily` row keyed on the date of
waking then holds a sleep that started the same morning, and the convention
that a night belongs to the day it ends on stops distinguishing anything.

SLEEP IS LOGGED MOST DAYS AND NOT ALL. She takes the watch off for the shift
itself - hand hygiene, and it sets the alarms off - so on the days she sleeps
in fragments around a shift there is no interval at all. The corpus had no
record where sleep timing was present on some days and absent on others, which
is the only shape in which a silent fall back to the clock can hide: a record
with the field everywhere never exercises the fallback, and a record without
it anywhere never reaches the code.

She also carries the first REGIMES rows in the corpus and the first PROTOCOLS,
because a rotating roster is the honest case for both: a stretch of nights is
a period during which a figure means something different, and her weighing
procedure changes with the shift rather than staying fixed.

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

SEED = 111
# A SECOND STREAM FOR THE ROSTER, so the shift pattern can change without
# moving every step count behind it. Not `SEED + 1`, which is the next
# persona's seed in a directory of consecutive numbers.
ROSTER_SEED = 10111
PERSONA_VERSION: int = 1

START = date(2029, 9, 3)
DEFAULT_END = date(2030, 6, 30)

_TOML = """# bea - Ghent. An intensive-care nurse on a rotating night roster.
[athlete]
timezone = "Europe/Brussels"

[targets]
phases = [[68.0, 66.0, 0.15]]

[tripwires]
steps_floor = 5000
sleep_floor_h = 6.0

[resolution]
source_order = ["scale", "watch", "app", "hand"]
"""


# --- the roster ----------------------------------------------------------------
#
# A block of nights, then days off, then a block of days. Twelve-hour shifts,
# 20:00 to 08:00 on nights. The pattern is the fixture: everything else here
# is downstream of which half of the clock she is living in.

NIGHT, OFF, DAY = "night", "off", "day"


def _roster(end: date) -> dict[date, str]:
    """One label per day. Deterministic, and its own stream."""
    rng = random.Random(ROSTER_SEED)
    out: dict[date, str] = {}
    day = START
    while day <= end:
        block = rng.choice([
            [NIGHT] * 3 + [OFF] * 3 + [DAY] * 4 + [OFF] * 2,
            [NIGHT] * 4 + [OFF] * 4 + [DAY] * 3 + [OFF] * 2,
            [NIGHT] * 3 + [OFF] * 4 + [DAY] * 5 + [OFF] * 2,
        ])
        for label in block:
            if day > end:
                break
            out[day] = label
            day += timedelta(days=1)
    return out


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _offset(local: datetime) -> str:
    """The offset in force in Belgium at a LOCAL wall-clock time.

    Central European time: CEST from 01:00 UTC on the last Sunday in March to
    01:00 UTC on the last Sunday in October, which is 02:00 and 03:00 local.
    Decided on the INSTANT rather than the date, because she is asleep across
    the changeover more often than anyone here - a night worker's sleep sits
    exactly where a date-granular rule is wrong.
    """
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
    """A lights-out and a duration, as two aware stamps sharing one instant.

    The end is computed on the INSTANT and then expressed in the offset in
    force when she woke, so the pair never disagrees with the duration beside
    them even across a clock change.
    """
    began = local_start.replace(tzinfo=timezone(_delta(local_start)))
    instant = began + timedelta(hours=hours)
    naive_end = instant.replace(tzinfo=None) + _delta(local_start)
    ended = instant.astimezone(timezone(_delta(naive_end)))
    return began.isoformat(), ended.isoformat()


# --- data ----------------------------------------------------------------------

def _daily(rng: random.Random, stamp: common.Stamper, roster: dict[date, str],
           end: date) -> list[dict]:
    """Steps and sleep, with the night worker's two awkward cases in it.

    AFTER A NIGHT SHIFT she sleeps from mid-morning to late afternoon, so the
    interval sits wholly inside the calendar day the row is keyed on - not
    before it, the way every other record in this corpus has it.

    ON A SHIFT DAY THERE IS NO INTERVAL AT ALL. The watch is off for the
    twelve hours she is working and she sleeps in pieces around it, so the
    duration is her own estimate typed in afterwards and the boundaries are
    absent. `sleep_h` present with `sleep_start` absent is the mixed case: a
    consumer that falls back to the clock when timing is missing will do it
    here and nowhere else in the corpus.
    """
    rows = []
    for d in common.daterange(START, end):
        shift = roster.get(d, OFF)
        if shift == NIGHT:
            steps = max(4000, int(rng.gauss(11500, 1800)))
        elif shift == DAY:
            steps = max(4000, int(rng.gauss(10500, 1900)))
        else:
            steps = max(2500, int(rng.gauss(7200, 2400)))

        fields = {
            "date": d.isoformat(), "steps": steps,
            "source": "watch", "capture": "connector", "origin": "watch",
            "coverage": "full",
            "recorded_at": stamp.stamp(d),
        }

        yesterday = roster.get(d - timedelta(days=1), OFF)
        if shift == NIGHT:
            # Working tonight, and she slept in fragments today. The watch was
            # off for the shift; the number is hers, the boundaries are not.
            fields.update({
                "sleep_h": round(max(3.0, min(7.5, rng.gauss(5.4, 0.9))), 1),
                "source": "hand", "capture": "typed", "origin": "athlete",
                "coverage": "partial",
            })
        elif yesterday == NIGHT:
            # Came off a night at 08:00 and slept through the day.
            hours = round(max(4.0, min(8.5, rng.gauss(6.6, 0.8))), 1)
            began = datetime.combine(d, dtime(hour=9)) + timedelta(
                minutes=rng.randrange(0, 70, 5))
            start, endstamp = _interval(began, hours)
            fields.update({"sleep_h": hours, "sleep_start": start,
                           "sleep_end": endstamp})
        else:
            hours = round(max(5.0, min(9.5, rng.gauss(7.4, 0.8))), 1)
            began = (datetime.combine(d, dtime()) - timedelta(days=1)
                     + timedelta(hours=23) + timedelta(
                         minutes=rng.randrange(-45, 60, 5)))
            start, endstamp = _interval(began, hours)
            fields.update({"sleep_h": hours, "sleep_start": start,
                           "sleep_end": endstamp})
        rows.append(common.record("daily", **fields))
    return rows


def _sessions(rng: random.Random, stamp: common.Stamper,
              roster: dict[date, str], end: date) -> list[dict]:
    """Swims and lifts, placed by her waking day rather than by the clock.

    THE 18:30 SESSION IS THE FIXTURE. On a day after a night shift she wakes
    around 16:00 and trains at 18:30, which every clock-derived part-of-day
    reads as evening and her own day reads as first-thing. A label taken off
    the wall clock is wrong here and right for everyone else in the corpus.
    """
    rows = []
    for d in common.daterange(START, end):
        shift = roster.get(d, OFF)
        if shift == NIGHT:
            continue
        after_night = roster.get(d - timedelta(days=1), OFF) == NIGHT
        if rng.random() > (0.45 if after_night else 0.6):
            continue
        kind = "swim" if rng.random() < 0.55 else "strength"
        hour = 18 if after_night else (7 if shift == DAY else 10)
        began = datetime.combine(d, dtime(hour=hour)) + timedelta(
            minutes=rng.randrange(0, 55, 5))
        minutes = rng.randrange(35, 75, 5)
        fields = {
            "date": d.isoformat(), "type": kind,
            "duration_s": minutes * 60,
            "start_time": _aware(began),
            "source": "watch", "capture": "connector", "origin": "watch",
            "rpe": rng.randrange(4, 8), "rpe_scale": "borg-cr10",
            "recorded_at": stamp.stamp(d),
        }
        if kind == "swim":
            fields["distance_km"] = round(rng.randrange(12, 26) * 0.1, 1)
            fields["place"] = "pool"
        else:
            fields["place"] = "gym"
        if after_night:
            fields["note"] = "first thing after waking"
        rows.append(common.record("sessions", **fields))
    return rows


def _weight(rng: random.Random, stamp: common.Stamper,
            roster: dict[date, str], end: date) -> list[dict]:
    """Weighs on days off, because the procedure is not available otherwise.

    A weigh-in after a twelve-hour night is not the same measurement as one
    after a normal sleep, and she knows it - so she does not take them. The
    gap is a decision rather than an omission, which `protocol` records.
    """
    rows = []
    for d in common.daterange(START, end):
        if roster.get(d) != OFF or d.weekday() not in (0, 4):
            continue
        base = 68.0 - 0.0022 * (d - START).days
        rows.append(common.record(
            "weight", date=d.isoformat(),
            kg=round(base + rng.gauss(0, 0.45), 1),
            measured_at="16:40" if roster.get(
                d - timedelta(days=1)) == NIGHT else "08:10",
            source="scale", capture="ble", origin="bathroom-scale",
            protocol="fasted-post-waking",
            recorded_at=stamp.stamp(d)))
    return rows


def _instruments(stamp: common.Stamper) -> list[dict]:
    """Her kit, and one replacement mid-record."""
    return [
        common.record(
            "instruments", date=START.isoformat(), origin="watch",
            from_date=START.isoformat(), to_date="2030-02-14",
            name="the old watch", maker=None, model=None, source="athlete",
            note="died in February; the replacement reports under the same "
                 "name, which is the whole reason the interval matters",
            recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date="2030-02-15", origin="watch",
            from_date="2030-02-15", to_date=None,
            name="the new watch", maker=None, model=None, source="athlete",
            note=None, recorded_at=stamp.stamp(date(2030, 2, 15))),
        common.record(
            "instruments", date=START.isoformat(), origin="bathroom-scale",
            from_date=START.isoformat(), to_date=None,
            name="the scale in the hall", maker=None, model=None,
            source="athlete", note=None, recorded_at=stamp.stamp(START)),
    ]


def _capabilities(stamp: common.Stamper) -> list[dict]:
    """What each instrument is competent at, in her hands.

    The watch is a PROXY for sleep and says so: it cannot see the fragments
    she takes around a shift, which is the case a wrist sensor is worst at and
    the one she is in most weeks.
    """
    d0 = START.isoformat()
    return [
        common.record(
            "capabilities", date=d0, origin="watch", measures="steps",
            competence="measures", construct=None, condition=None,
            basis="stated", set_by="athlete", note=None,
            recorded_at=stamp.stamp(START)),
        common.record(
            "capabilities", date=d0, origin="watch", measures="sleep_h",
            competence="proxy",
            construct="continuous nightly rest, which is not what she gets",
            condition="on a shift week", basis="observed", set_by="athlete",
            note="it scores a broken day as a bad night",
            recorded_at=stamp.stamp(START)),
        common.record(
            "capabilities", date=d0, origin="bathroom-scale", measures="kg",
            competence="measures", construct=None, condition=None,
            basis="stated", set_by="athlete", note=None,
            recorded_at=stamp.stamp(START)),
    ]


def _regimes(stamp: common.Stamper) -> list[dict]:
    """A bounded interval in which a figure means something else.

    THE FIRST REGIMES ROWS IN THE CORPUS, and a rotating roster is the honest
    case for one: across a block of nights her step count is a fact about a
    ward floor rather than about training, and her sleep total is a sum of
    fragments rather than a night. Both are real numbers and neither answers
    the question the goal is asking.
    """
    return [
        common.record(
            "regimes", date="2029-11-19", from_date="2029-11-19",
            to_date="2029-11-22", dataset="daily", field="steps",
            kind="unanchored", source="athlete",
            text="four nights on the unit. The steps are the ward, not "
                 "training, and reading them as activity flatters the week",
            recorded_at=stamp.stamp(date(2029, 11, 19))),
        common.record(
            "regimes", date="2030-03-04", from_date="2030-03-04",
            to_date="2030-03-10", dataset="daily", field="sleep_h",
            kind="unanchored", source="athlete",
            text="the new watch scored every daytime sleep as a nap and the "
                 "totals are short; the hours are hers, the scoring is not",
            recorded_at=stamp.stamp(date(2030, 3, 4))),
    ]


def _protocols(stamp: common.Stamper) -> list[dict]:
    """How a measurement is taken, so a change in procedure is visible."""
    return [
        common.record(
            "protocols", date=START.isoformat(), slug="fasted-post-waking",
            text="After waking and before eating, on the hall scale - "
                 "whichever end of the clock waking happens to be. Never on a "
                 "shift day: a weigh-in after twelve hours on the unit is not "
                 "the same measurement, and skipping it is a decision rather "
                 "than an omission.",
            recorded_at=stamp.stamp(START)),
    ]


def _thresholds(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "thresholds", date=START.isoformat(), key="sleep_floor_h",
            value=6.0, change_kind="change", set_by="athlete",
            reason="a shift-week floor, not a healthy-adult one",
            note=None, recorded_at=stamp.stamp(START)),
    ]


def _goals(stamp: common.Stamper) -> list[dict]:
    d0 = START.isoformat()
    return [
        common.record(
            "goals", date=d0, slug="swim-weekly",
            title="Swim twice in a week that has a day off in it",
            metric="sessions", dataset="sessions", target=2,
            polarity="floor", period="weekly", policy="monotonic",
            tracker="count", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="it is the only thing that survives a run of nights",
            rationale="two is what fits, not what is ideal",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START)),
        common.record(
            "goals", date=d0, slug="sleep-floor",
            title="Six hours, counting the fragments",
            metric="sleep_h", dataset="daily", target=6.0,
            polarity="floor", period="daily", policy="monotonic",
            tracker="mean", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="I stop being safe at work below it",
            rationale="the number is a floor for a shift week",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START)),
    ]


def _journal(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "journal", date="2029-10-15", kind="claim",
            text="I sleep fine on nights, it is just at the wrong time",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2029, 10, 15))),
        common.record(
            "journal", date="2030-01-08", kind="preference",
            text="do not tell me a session at half six in the evening is a "
                 "late session. It is the first thing I did that day",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2030, 1, 8))),
        common.record(
            "journal", date="2030-03-05", kind="worry",
            text="the new watch thinks I am napping",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2030, 3, 5))),
    ]


def _context(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "context", date="2029-11-19", mode="work", facilities="none",
            place="away", source="athlete",
            note="four nights running; the unit was short and nothing else "
                 "happened that week",
            recorded_at=stamp.stamp(date(2029, 11, 19))),
        common.record(
            "context", date="2030-02-15", mode="normal", facilities="full",
            place="home", source="athlete",
            note="new watch, reporting under the same name in the app",
            recorded_at=stamp.stamp(date(2030, 2, 15))),
    ]


def _expectations() -> list[dict]:
    return [
        {"id": "bea-B-01", "kind": "behavior",
         "expect": "A part-of-day label for her 18:30 sessions is derived from "
                   "her own sleep interval, or it is not stated. The engine "
                   "must not read the wall clock as her day.",
         "truth": "On days following a night shift she wakes about 16:00 and "
                  "trains at 18:30. The clock calls it evening; it is the "
                  "first thing she did after waking."},
        {"id": "bea-B-02", "kind": "behavior",
         "expect": "A day whose sleep interval is absent is reported as having "
                   "no timing, never silently anchored to midnight.",
         "truth": "On the 128 shift days the watch is off and only her own "
                  "estimate of the total exists. `sleep_h` is present and both "
                  "boundaries are absent."},
        {"id": "bea-G-01", "kind": "gap",
         "expect": "A sleep interval lying wholly inside the calendar day of "
                   "its row is handled without special-casing.",
         "truth": "After a night shift she sleeps 09:00 to 16:00, so the night "
                  "starts and ends on the row's own date - the convention that "
                  "a night belongs to the day it ends on stops separating "
                  "anything."},
        {"id": "bea-G-02", "kind": "gap",
         "expect": "Steps inside a declared regime are not read as training "
                   "volume.",
         "truth": "Across a block of nights her step count is a fact about a "
                  "ward floor. The record says so in a regimes row rather than "
                  "leaving it to be inferred."},
        {"id": "bea-L-01", "kind": "lie",
         "expect": "The engine observes the contradiction and does not resolve "
                   "it. Two athlete statements disagreeing is an observation.",
         "truth": "Her journal claim of 2029-10-15 that she sleeps fine on "
                  "nights is contradicted by her own numbers: the shift-day "
                  "mean is 5.4 h against 7.4 h on ordinary days, and her own "
                  "stated floor is 6.0."},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)
    roster = _roster(end)

    daily = _daily(rng, common.Stamper(base_hour=20), roster, end)
    sessions = _sessions(rng, common.Stamper(base_hour=19), roster, end)
    weight = _weight(rng, common.Stamper(base_hour=9), roster, end)

    return {
        "vitai.toml": _TOML,
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/instruments.jsonl": common.jsonl_text(common.sort_rows(
            _instruments(common.Stamper(base_hour=10)))),
        "data/capabilities.jsonl": common.jsonl_text(common.sort_rows(
            _capabilities(common.Stamper(base_hour=10)))),
        "data/regimes.jsonl": common.jsonl_text(common.sort_rows(
            _regimes(common.Stamper(base_hour=11)))),
        "data/protocols.jsonl": common.jsonl_text(common.sort_rows(
            _protocols(common.Stamper(base_hour=10)))),
        "data/thresholds.jsonl": common.jsonl_text(common.sort_rows(
            _thresholds(common.Stamper(base_hour=10)))),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(
            _goals(common.Stamper(base_hour=10)))),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(
            _journal(common.Stamper(base_hour=22)))),
        "data/context.jsonl": common.jsonl_text(common.sort_rows(
            _context(common.Stamper(base_hour=12)))),
        "expectations.jsonl": common.jsonl_text(_expectations()),
        "persona.toml": common.persona_toml(
            "bea", PERSONA_VERSION, SEED,
            (START.isoformat(), end.isoformat())),
    }
