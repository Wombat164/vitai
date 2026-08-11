"""Generator for the otto persona (seed 112).

Leipzig, Germany. 58, masters rower and cyclist, trains at a club with shared
equipment. Eleven months, from 2029-08-01 to 2030-06-30.

THE AXIS HE STRESSES IS EVIDENCE. Every other persona's numbers arrive by
connector or by hand, and the record either has a value or it does not. Otto
photographs the rowing-machine console at the end of a piece, so a figure in
his record can be looked at again: `capture: photo`, an `artifact` reference,
and a stored content address. He is the first record in this corpus with any
artifacts at all.

That distinction is load-bearing and the corpus could not exercise it. A
photo-read and a connector-read of one console on one evening are two claims
with one origin and two different error modes: the photo passed through an act
of reading and can be misread, and the evidence SURVIVES and can be re-read.
Nothing else here demonstrates either half.

Three more things he carries that the corpus did not have.

A SHARED INSTRUMENT. The club ergometer is not his. Its console is not
calibrated to anything, several people use it, and a figure off it is not
comparable with a figure off the one at home even in the same week. Both are
registered, both are named on the rows that came off them, and the capability
rows say which is which.

BODY MEASUREMENTS THAT ARE NOT WEIGHT. A tape measure four times a year and
one DEXA scan, so the sparse-anchor path has a record with more than one
instrument in it and a stated procedure on every row.

REMOVED EVIDENCE. One photo is deleted, with a reason. Deleting evidence is a
decision worth recording and it is what distinguishes a removal from data
loss; the record keeps the row and marks it, which is the only way a reader
can tell the two apart later.

See `PROFILE.md`, `LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md`
alongside this file for the prose these numbers have to agree with. Entirely
synthetic; any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself.
"""

from __future__ import annotations

import hashlib
import random
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

from . import common

SEED = 112
PERSONA_VERSION: int = 1

START = date(2029, 8, 1)
DEFAULT_END = date(2030, 6, 30)

_TOML = """# otto - Leipzig. A masters rower who photographs the console.
[athlete]
timezone = "Europe/Berlin"

[targets]
phases = [[84.0, 82.0, 0.15]]

[tripwires]
steps_floor = 5000
sleep_floor_h = 6.5

[resolution]
source_order = ["scale", "watch", "console", "hand"]
"""


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() + 1) % 7)


def _offset(local: datetime) -> str:
    """Central European time, decided on the instant rather than the date."""
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


def _address(label: str) -> str:
    """A content address for a photo that does not exist.

    SYNTHETIC AND DETERMINISTIC. The bytes are never shipped - this corpus
    holds no images - so the address is the hash of a label rather than of a
    file. It is a real content address in shape, which is what the validator
    and any consumer of the store care about, and it is stable across
    regeneration, which is what the corpus cares about.
    """
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


# --- data ----------------------------------------------------------------------

def _daily(rng: random.Random, stamp: common.Stamper, end: date) -> list[dict]:
    rows = []
    for d in common.daterange(START, end):
        steps = max(3000, int(rng.gauss(8600, 2100)))
        hours = round(max(5.0, min(9.0, rng.gauss(7.1, 0.7))), 1)
        began = (datetime.combine(d, dtime()) - timedelta(days=1)
                 + timedelta(hours=22, minutes=rng.randrange(0, 75, 5)))
        start, ended = _interval(began, hours)
        rows.append(common.record(
            "daily", date=d.isoformat(), steps=steps, sleep_h=hours,
            sleep_start=start, sleep_end=ended,
            source="watch", capture="connector", origin="watch",
            coverage="full", recorded_at=stamp.stamp(d)))
    return rows


def _interval(local_start: datetime, hours: float) -> tuple[str, str]:
    began = local_start.replace(tzinfo=timezone(_delta(local_start)))
    instant = began + timedelta(hours=hours)
    naive_end = instant.replace(tzinfo=None) + _delta(local_start)
    ended = instant.astimezone(timezone(_delta(naive_end)))
    return began.isoformat(), ended.isoformat()


def _sessions(rng: random.Random, stamp: common.Stamper,
              end: date) -> tuple[list[dict], list[dict]]:
    """Rows, and the artifacts some of them point at.

    THE PHOTOGRAPHED PIECES ARE THE POINT. A club erg session is read off the
    console by eye and photographed, so it carries `capture: photo`, a
    `read_by`, and an `artifact` reference to a row in the artifacts dataset.
    A ride comes off the watch by connector and carries none of that. Both are
    in the record, which is what lets a consumer tell them apart.
    """
    rows: list[dict] = []
    artifacts: list[dict] = []
    art_stamp = common.Stamper(base_hour=21)
    for d in common.daterange(START, end):
        if d.weekday() in (1, 3) and rng.random() < 0.8:
            # Club erg, read off the console and photographed.
            minutes = rng.choice([30, 40, 45, 60])
            began = datetime.combine(d, dtime(hour=18, minute=30))
            label = f"otto-erg-{d.isoformat()}"
            ref = _address(label)
            artifacts.append(common.record(
                "artifacts", date=d.isoformat(), sha256=ref,
                media_type="image/jpeg", bytes=rng.randrange(180_000, 620_000),
                captured_at=_aware(began + timedelta(minutes=minutes)),
                origin="club-erg", kind="photo",
                note="the console at the end of the piece",
                removed=None, reason=None,
                recorded_at=art_stamp.stamp(d)))
            rows.append(common.record(
                "sessions", date=d.isoformat(), type="row",
                duration_s=minutes * 60,
                distance_km=round(minutes * rng.uniform(0.21, 0.25), 2),
                start_time=_aware(began), place="club",
                source="console", capture="photo", origin="club-erg",
                read_by="athlete", artifact=ref,
                context="club", rpe=rng.randrange(5, 9), rpe_scale="borg-cr10",
                note=None, recorded_at=stamp.stamp(d)))
        if d.weekday() in (5, 6) and rng.random() < 0.7:
            began = datetime.combine(d, dtime(hour=9, minute=15))
            minutes = rng.randrange(60, 180, 15)
            rows.append(common.record(
                "sessions", date=d.isoformat(), type="cycle",
                duration_s=minutes * 60,
                distance_km=round(minutes * rng.uniform(0.30, 0.38), 1),
                elevation_m=rng.randrange(80, 640, 10),
                avg_hr=rng.randrange(118, 142),
                cadence=rng.randrange(76, 92),
                start_time=_aware(began), place="away",
                weather="dry" if rng.random() < 0.7 else "rain",
                source="watch", capture="connector", origin="watch",
                context="club" if rng.random() < 0.4 else "solo",
                rpe=rng.randrange(3, 7), rpe_scale="borg-cr10",
                recorded_at=stamp.stamp(d)))
    return rows, artifacts


def _weight(rng: random.Random, stamp: common.Stamper, end: date,
            woke: dict[str, datetime]) -> list[dict]:
    """Sunday mornings, fasted - and after he is actually up.

    A FIXED TIME CONTRADICTS THE SLEEP ROW. This stamped every weigh-in at
    07:20 while the sleep draw put some Sunday wakes after 08:00, so the record
    had him on the scale before he woke, under a protocol whose text is
    "first thing, after the bathroom, before anything to drink". The same
    defect bea had; found here by the check written for hers.
    """
    rows = []
    for d in common.daterange(START, end):
        if d.weekday() != 6:
            continue
        base = 84.0 - 0.0035 * (d - START).days
        up = woke.get(d.isoformat())
        at = (up.replace(tzinfo=None) + timedelta(minutes=15)) if up else None
        rows.append(common.record(
            "weight", date=d.isoformat(),
            kg=round(base + rng.gauss(0, 0.5), 1),
            measured_at=(f"{at.hour:02d}:{at.minute:02d}" if at else "07:20"),
            source="scale", capture="ble",
            origin="bathroom-scale", protocol="fasted-post-void",
            recorded_at=stamp.stamp(d)))
    return rows


def _measurements(stamp: common.Stamper) -> list[dict]:
    """A tape four times a year and one scan, both saying how they were taken.

    TWO INSTRUMENTS FOR ONE MEASURAND is the case: his waist is measured by
    tape at home and by the clinic's scan, and the two are not interchangeable
    even when they agree. Each row names its origin and its protocol, so the
    record can say which is which without anyone inferring it from the value.
    """
    out = []
    tape = [("2029-08-05", 96.0), ("2029-11-04", 95.0),
            ("2030-02-03", 94.5), ("2030-05-05", 93.5)]
    for day, cm in tape:
        out.append(common.record(
            "measurements", date=day, kind="waist_cm", value=cm,
            source="hand", capture="typed", origin="tape-measure",
            read_by="athlete", protocol="fasted-post-void",
            note="standing, at the navel, breathing out",
            recorded_at=stamp.stamp(date.fromisoformat(day))))
    out.append(common.record(
        "measurements", date="2030-01-15", kind="body_fat_pct", value=24.8,
        source="clinic", capture="file_export", origin="dexa",
        protocol="clinic-dexa",
        note="one scan; a second would be needed before a trend is a trend",
        recorded_at=stamp.stamp(date(2030, 1, 15))))
    return out


def _instruments(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "instruments", date=START.isoformat(), origin="club-erg",
            from_date=START.isoformat(), to_date=None,
            name="the club ergometer", maker=None, model=None,
            source="athlete",
            note="not his, several people use it, and its console is not "
                 "calibrated to anything",
            recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=START.isoformat(), origin="bathroom-scale",
            from_date=START.isoformat(), to_date=None,
            name="the scale at home", maker=None, model=None,
            source="athlete", note=None, recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=START.isoformat(), origin="tape-measure",
            from_date=START.isoformat(), to_date=None,
            name="a cloth tape", maker=None, model=None, source="athlete",
            note=None, recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date="2030-01-15", origin="dexa",
            from_date="2030-01-15", to_date="2030-01-15",
            name="the clinic scanner", maker=None, model=None,
            source="athlete", note="one visit",
            recorded_at=stamp.stamp(date(2030, 1, 15))),
    ]


def _capabilities(stamp: common.Stamper) -> list[dict]:
    d0 = START.isoformat()
    return [
        common.record(
            "capabilities", date=d0, origin="club-erg", measures="distance_km",
            competence="proxy",
            construct="whatever the drag factor was set to that evening",
            condition=None, basis="stated", set_by="athlete",
            note="a shared machine nobody calibrates",
            recorded_at=stamp.stamp(START)),
        common.record(
            # `measures` NAMES A FIELD, which is what the validator checks.
            # A measurements row's quantity lives in `value`, so that is what
            # the tape measures - `waist_cm` is a KIND of measurement rather
            # than a column.
            "capabilities", date=d0,
            origin="tape-measure", measures="value",
            competence="measures", construct=None,
            condition="taken to the stated protocol", basis="stated",
            set_by="athlete", note=None, recorded_at=stamp.stamp(START)),
        common.record(
            "capabilities", date="2030-01-15", origin="dexa",
            measures="body_fat_pct", competence="measures", construct=None,
            condition=None, basis="stated", set_by="athlete",
            note="one scan is a point, not a trend",
            recorded_at=stamp.stamp(date(2030, 1, 15))),
    ]


def _protocols(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "protocols", date=START.isoformat(), slug="fasted-post-void",
            text="First thing, after the bathroom, before anything to drink. "
                 "The tape is taken standing, at the navel, breathing out.",
            recorded_at=stamp.stamp(START)),
        common.record(
            "protocols", date="2030-01-15", slug="clinic-dexa",
            text="A whole-body scan at the clinic, fasted, in the morning. "
                 "Their machine and their procedure, neither of which he "
                 "controls or can repeat at home.",
            recorded_at=stamp.stamp(date(2030, 1, 15))),
    ]


def _artifact_removal(stamp: common.Stamper) -> list[dict]:
    """One photo deleted, with a reason.

    A REMOVAL IS NOT DATA LOSS, and the only thing that distinguishes them
    later is that somebody said why. The row stays and is marked; the bytes do
    not.
    """
    return [
        common.record(
            "artifacts", date="2030-04-16",
            sha256=_address("otto-erg-2030-04-16-second"),
            media_type="image/jpeg", bytes=311_000,
            captured_at=_aware(datetime(2030, 4, 16, 19, 20)),
            origin="club-erg", kind="photo",
            note="a second shot of the same console reading",
            removed=True,
            reason="somebody else was in the frame and had not been asked",
            recorded_at=stamp.stamp(date(2030, 4, 16))),
    ]


def _goals(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "goals", date=START.isoformat(), slug="erg-twice",
            title="Two ergs a week through the winter",
            metric="sessions", dataset="sessions", session_type="row",
            target=2, polarity="floor", period="weekly", policy="monotonic",
            tracker="count", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="the water is closed and the club is warm",
            rationale="two is what the roster of the boathouse allows",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START)),
    ]


def _journal(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "journal", date="2029-09-12", kind="preference",
            text="I photograph the console because I do not trust myself to "
                 "remember the split by the time I am home",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2029, 9, 12))),
        common.record(
            "journal", date="2030-02-20", kind="claim",
            text="the erg at the club reads long. Same effort, better numbers "
                 "than the one at the boathouse",
            status="open", source="athlete",
            recorded_at=stamp.stamp(date(2030, 2, 20))),
    ]


def _expectations() -> list[dict]:
    return [
        {"id": "otto-B-01", "kind": "behavior",
         "expect": "A value read off a photographed console is distinguishable "
                   "from one delivered by a connector, and the artifact it "
                   "rests on is reachable from the row.",
         "truth": "Erg sessions carry capture photo, a read_by, and an "
                  "artifact reference; rides carry capture connector and no "
                  "artifact. Both are in the record."},
        {"id": "otto-B-02", "kind": "behavior",
         "expect": "A removed artifact is reported as removed with its reason, "
                   "never as missing.",
         "truth": "The photo of 2030-04-16 was deleted because a bystander was "
                  "in it. The row survives and says so."},
        {"id": "otto-G-01", "kind": "gap",
         "expect": "Figures off the shared club ergometer are not treated as "
                   "comparable with figures off any other machine.",
         "truth": "The club erg is used by several people, nobody calibrates "
                  "it, and its capability row says its distance is a proxy for "
                  "whatever the drag factor was that evening."},
        {"id": "otto-G-02", "kind": "gap",
         "expect": "One DEXA scan is reported as a point and not as a trend.",
         "truth": "There is exactly one scan, on 2030-01-15. A second would be "
                  "needed before a direction exists."},
        {"id": "otto-L-01", "kind": "lie",
         "expect": "The engine observes that the record cannot settle the "
                   "claim, and says so rather than adjudicating it.",
         "truth": "His journal claim of 2030-02-20 that the club erg reads "
                  "long is untestable from this record: every erg row in it "
                  "came off that one machine, so there is nothing to compare "
                  "against."},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    daily = _daily(rng, common.Stamper(base_hour=21), end)
    sessions, artifacts = _sessions(rng, common.Stamper(base_hour=20), end)
    woke = {r["date"]: datetime.fromisoformat(r["sleep_end"])
            for r in daily if r.get("sleep_end")}
    weight = _weight(rng, common.Stamper(base_hour=8), end, woke)
    artifacts = artifacts + _artifact_removal(common.Stamper(base_hour=22))

    return {
        "vitai.toml": _TOML,
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/artifacts.jsonl": common.jsonl_text(common.sort_rows(artifacts)),
        "data/measurements.jsonl": common.jsonl_text(common.sort_rows(
            _measurements(common.Stamper(base_hour=9)))),
        "data/instruments.jsonl": common.jsonl_text(common.sort_rows(
            _instruments(common.Stamper(base_hour=10)))),
        "data/capabilities.jsonl": common.jsonl_text(common.sort_rows(
            _capabilities(common.Stamper(base_hour=10)))),
        "data/protocols.jsonl": common.jsonl_text(common.sort_rows(
            _protocols(common.Stamper(base_hour=10)))),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(
            _goals(common.Stamper(base_hour=10)))),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(
            _journal(common.Stamper(base_hour=22)))),
        "expectations.jsonl": common.jsonl_text(_expectations()),
        "persona.toml": common.persona_toml(
            "otto", PERSONA_VERSION, SEED,
            (START.isoformat(), end.isoformat())),
    }
