"""Generator for the hana persona (seed 127).

Galway, Ireland. 41, walks and lifts, keeps the record herself. Six months,
2030-01-07 to 2030-06-30, plus an archive that reaches back to the summer
before.

THE AXIS SHE STRESSES IS THE LIFE OF AN INSTRUMENT. Every other record in this
corpus has channels that simply exist: they start at the beginning and run to
the end, so nothing in the fixtures ever asked what a channel STOPPING means.
Hers carries four, and the difference between them is the whole point, because
three of the four are quiet at the horizon and only one of those is a question.

  `phone-app` is alive. It writes most days and is learned the same evening.
  Nothing to ask.

  `old-band` is an ARCHIVE, AND IT IS ALSO THE ONE INSTRUMENT IN THIS CORPUS
  THAT LIED. Its last row carries a zero step count on the day its strap
  perished, which is what a dying step counter writes and what
  `false_zero_questions` exists to ask about - a rule whose true-positive path
  no record could run until this one (#435). She replaced a fitness band in the
  autumn and
  pulled its history off the old device once, months later, to recover the
  months before she started keeping this record. Ninety-odd dates spanning
  seven months of valid time, and ONE transaction day. It never had a rhythm
  to break, so it cannot have broken one. It is deliberately UNDECLARED - see
  `_instruments` - because the record that found this defect had no
  `instruments.jsonl` at all, and a fixture where the declared layer catches
  everything would prove nothing about the layer underneath it.

  `club-treadmill` STOPPED, and she said so. The gym membership ended in
  February and the instrument row closes on the day of her last session.
  Silence from a declared end is the expected state.

  `chest-strap` STOPPED and she did NOT say so. It reported every couple of
  days until the middle of April and then nothing, with an open instrument row
  still asserting it is hers. That is the one real question in this record.

WHY THE ARCHIVE IS ITS OWN FILE. `recorded_at` is monotonic in FILE order, and
an import written months after the readings it recovers cannot be interleaved
by date into a file whose other rows were stamped as they happened. A separate
writer writes a separate file, which is what #105's per-device streams are
for, and `daily.old-band.jsonl` is what a one-time import honestly looks like
on disk.

NOTHING HERE IS COPIED FROM ANYWHERE. The shape came from a report; every date,
count, source name and value below is invented for this fixture.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 127
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
# 2 at #435: the band's last row now carries a zero step count, which is a
# HISTORY change rather than a schema one - it makes the engine emit a
# `false_zero` question that no record in this corpus produced before.
PERSONA_VERSION: int = 2

START = date(2030, 1, 7)
DEFAULT_END = date(2030, 6, 30)

# The band's own history, recovered later. It ends before the record starts,
# which is why she never wrote an instruments row for it: by the time she was
# keeping one, the band was in a drawer.
BAND_FROM = date(2029, 6, 3)
BAND_TO = date(2029, 12, 30)
# The evening she sat down and pulled the archive off it. ONE day, and that is
# the entire signal that separates an import from a channel.
#
# AT THE END OF THE BLOCK, NOT THE MIDDLE, AND THE ENGINE REQUIRES IT. A
# dataset's files are read as one stream - `daily.jsonl` then `daily.*.jsonl` -
# and `recorded_at` must be monotonic across that concatenation, so an import
# living in its own file has to be stamped after everything the main file
# holds. Dating the sitting earlier is not a narrative choice this fixture can
# make; `validate` refuses it, which is the rule doing its job.
BAND_IMPORTED = date(2030, 6, 30)

STRAP_LAST = date(2030, 4, 14)
TREADMILL_LAST = date(2030, 2, 26)

_TOML = """# hana - Galway. Four channels, three of them quiet, one of them a question.
[athlete]
timezone = "Europe/Dublin"

[targets]
phases = [[71.0, 68.0, 0.2]]

[tripwires]
steps_floor = 7000
sleep_floor_h = 6.5

[resolution]
source_order = ["bathroom-scale", "phone-app", "chest-strap",
                "club-treadmill", "old-band"]
"""


def _weight(rng: random.Random, stamp: common.Stamper,
            end: date) -> list[dict]:
    """Twice a week, at home, before breakfast. Unremarkable on purpose: the
    weight series exists so the rollup has something to render and is not
    where this persona's interest lies."""
    rows = []
    kg = 71.4
    for day in common.daterange(START, end):
        if day.weekday() not in (0, 4):
            continue
        kg = round(kg - rng.uniform(0.0, 0.09), 2)
        rows.append(common.record(
            "weight", date=day.isoformat(), kg=kg, source="bathroom-scale",
            origin="bathroom-scale", measured_at="07:10",
            capture="manual_entry", read_by="athlete",
            recorded_at=stamp.stamp(day)))
    return rows


def _phone_app(rng: random.Random, stamp: common.Stamper,
               end: date) -> list[dict]:
    """The live channel: steps and sleep, logged the evening of the day."""
    rows = []
    for day in common.daterange(START, end):
        if rng.random() < 0.08:      # the odd evening she forgets
            continue
        rows.append(common.record(
            "daily", date=day.isoformat(),
            steps=rng.randrange(6200, 12400),
            sleep_h=round(rng.uniform(6.1, 8.0), 1),
            source="phone-app", origin="phone-app",
            capture="manual_entry", read_by="athlete",
            recorded_at=stamp.stamp(day)))
    return rows


def _chest_strap(rng: random.Random, stamp: common.Stamper) -> list[dict]:
    """THE ONE REAL QUESTION. Every second morning, then nothing after the
    middle of April, with no instrument row closing and nothing said. It is
    still declared hers, so the record's own position is that this channel
    should be reporting."""
    rows = []
    day = START + timedelta(days=1)
    while day <= STRAP_LAST:
        rows.append(common.record(
            "daily", date=day.isoformat(),
            rhr=rng.randrange(51, 59),
            source="chest-strap", origin="chest-strap",
            capture="ble", read_by=None,
            recorded_at=stamp.stamp(day)))
        day += timedelta(days=2)
    return rows


def _club_treadmill(rng: random.Random, stamp: common.Stamper) -> list[dict]:
    """Stopped, and DECLARED stopped. The membership ended in February and the
    instrument row closes on the day of the last session, so the silence after
    it is the record working rather than a channel failing."""
    rows = []
    day = START + timedelta(days=2)
    while day <= TREADMILL_LAST:
        rows.append(common.record(
            "daily", date=day.isoformat(),
            active_min=rng.randrange(28, 46),
            distance_km=round(rng.uniform(3.1, 5.4), 2),
            source="club-treadmill", origin="club-treadmill",
            capture="ble", read_by=None,
            recorded_at=stamp.stamp(day)))
        day += timedelta(days=3)
    return rows


def _backfill(rng: random.Random) -> list[dict]:
    """THE ARCHIVE, AND THE SHAPE THIS PERSONA EXISTS FOR.

    Many dates, ONE transaction day. The stamps are written by hand rather
    than by a `Stamper`, because a Stamper derives the instant from the row's
    own date - which is exactly right for a channel logging as it goes and
    exactly wrong for an import, where every row was learned at the same
    sitting. They advance by a second per row so the file stays strictly
    increasing with no ties, which is what a serial writer produces and what
    `recorded_at_problems` checks.
    """
    rows = []
    offset = common.irish_offset(BAND_IMPORTED)
    second = 0
    day = BAND_FROM
    while day <= BAND_TO:
        hh = 22 + second // 3600
        mm = (second // 60) % 60
        ss = second % 60
        # THE DAY THE STRAP PERISHED, AND THE BAND SAID SO WRONGLY (#435).
        # `WORLD.md` has always said the band was worn "until the end of
        # December, when the strap perished". Its last row now carries the
        # zero a dying step counter writes: not a day she did not walk - she
        # walks the long way to everything, which is the first line of her
        # profile - but a day the device reported a count it did not have.
        #
        # THE ENGINE CLAIMS TO DETECT EXACTLY THIS and no record contained it.
        # `false_zero_questions` asks about the first exact zero a source has
        # never written before, and `false_zero_questions`' own docstring
        # recorded that it "produced no true positive anywhere, because no
        # corpus record contains the shape this kind exists for". A rule
        # tightened twice against a corpus that cannot exercise it is a rule
        # whose true-positive path has never run.
        #
        # WHY THIS BAND AND NOT A WATCH. The rule fires on a source
        # contradicting ITSELF, so it needs a channel with a long unbroken
        # habit of non-zero counts: this one has 105 of them before this day,
        # and it counted steps and nothing else, which is the pure case for a
        # register that holds exactly `steps`. The dying-watch shape the
        # docstring describes - a zero step count beside a near-floor
        # `kcal_out` - is NOT here and is not claimed to be, because this band
        # never wrote a `kcal_out` to sit at the floor.
        #
        # THE DRAW STILL HAPPENS AND IS THEN DISCARDED. Skipping it would
        # shift every value in the seeded stream after it; there is nothing
        # after it, and doing it this way keeps that true whoever extends the
        # block next.
        drawn = rng.randrange(5400, 11800)
        rows.append(common.record(
            "daily", date=day.isoformat(),
            steps=0 if day == BAND_TO else drawn,
            source="old-band", origin="old-band",
            # `file_export` is what an archive pull IS, and it is the
            # capture value that says so rather than a sync that never
            # happened.
            capture="file_export", read_by=None,
            device="laptop",
            recorded_at=(f"{BAND_IMPORTED.isoformat()}"
                         f"T{hh:02d}:{mm:02d}:{ss:02d}{offset}")))
        second += 1
        day += timedelta(days=2)
    return rows


def _instruments(stamp: common.Stamper) -> list[dict]:
    """What the record SAYS about its own hardware, and what it does not.

    `old-band` IS ABSENT ON PURPOSE. She started keeping instrument rows when
    she started this record, months after the band went in a drawer, so there
    was never an occasion to write one. That is the case the reporting record
    was in - no `instruments.jsonl` at all - and it is why the transaction-time
    layer has to stand on its own: a fixture where every channel is declared
    would let the declared layer answer everything and leave the other one
    untested.
    """
    return [
        common.record(
            "instruments", date=START.isoformat(), origin="bathroom-scale",
            from_date=START.isoformat(), name="the scale in the bathroom",
            source="athlete", recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=(START + timedelta(days=1)).isoformat(),
            origin="chest-strap", from_date=(START + timedelta(days=1)).isoformat(),
            name="the chest strap", source="athlete",
            note="still hers; the record has never said otherwise",
            recorded_at=stamp.stamp(START + timedelta(days=1))),
        common.record(
            "instruments", date=(START + timedelta(days=2)).isoformat(),
            origin="club-treadmill",
            from_date=(START + timedelta(days=2)).isoformat(),
            to_date=TREADMILL_LAST.isoformat(),
            name="the treadmill at the club",
            source="athlete",
            note="membership ended; the interval closes on the last session",
            recorded_at=stamp.stamp(START + timedelta(days=2))),
    ]


def _expectations() -> list[dict]:
    return [
        {"id": "hana-E1", "kind": "behavior", "dataset": "daily",
         "dates": [BAND_FROM.isoformat(), BAND_TO.isoformat(),
                   BAND_IMPORTED.isoformat()],
         "claim": "`old-band` writes many dates at one `recorded_at`",
         "truth": "the archive covers seven months of valid time and was "
                  "learned in a single sitting, so its transaction-time "
                  "footprint is one day however long its date span is",
         "expect": "no `outage` question names `old-band`. It never had a "
                   "transaction cadence, so it cannot have broken one - and "
                   "measured on `date` instead it would look like the most "
                   "established channel in the record and then like one that "
                   "died, which is the defect this row exists to hold shut",
         "gap": "none"},
        {"id": "hana-E5", "kind": "behavior", "dataset": "daily",
         "dates": [BAND_TO.isoformat()],
         "claim": "`old-band` writes a zero step count on the day its strap "
                  "perished",
         "truth": "she walks the long way to everything and walked that day "
                  "as she walked every other; the band had counted 105 "
                  "non-zero days and then reported a count it did not have. "
                  "The zero is the device failing, not the day being empty",
         "expect": "a `false_zero` question names `old-band` for that date "
                   "and resolves `steps`. It is the only such question in the "
                   "corpus, and before this record carried it the rule's "
                   "true-positive path had never run against anything",
         "gap": "the zero is the whole signal. The dying-instrument shape the "
                "engine describes also has a near-floor `kcal_out` beside it, "
                "and this band never wrote one - it counted steps and nothing "
                "else - so the uncatchable half of that shape is absent here "
                "rather than exercised"},
        {"id": "hana-E2", "kind": "behavior", "dataset": "daily",
         "dates": [TREADMILL_LAST.isoformat()],
         "claim": "`club-treadmill` stops in February and its instrument row "
                  "closes on the same day",
         "truth": "the membership ended; the silence after it is declared",
         "expect": "no `outage` question names `club-treadmill`. A closed "
                   "`instruments.to_date` is the record saying this channel "
                   "finished, and silence from a declared end is the expected "
                   "state rather than an anomaly",
         "gap": "none"},
        {"id": "hana-E3", "kind": "behavior", "dataset": "daily",
         "dates": [STRAP_LAST.isoformat()],
         "claim": "`chest-strap` reports every second day and then stops "
                  "without explanation",
         "truth": "nothing closes its instrument row and nothing in the "
                  "record accounts for the silence",
         "expect": "exactly one `outage` question, naming `chest-strap`, "
                   "from the day after its last reading through the viewpoint. "
                   "This is the only channel here the engine should ask about, "
                   "and a corpus where all three quiet channels were suppressed "
                   "would pass every refusal and prove the rule cannot fire",
         "gap": "none"},
        {"id": "hana-E4", "kind": "behavior", "dataset": "daily",
         "dates": [DEFAULT_END.isoformat()],
         "claim": "`phone-app` is still reporting at the horizon",
         "truth": "a live channel logged the evening of the day it covers",
         "expect": "no question about it, and the contrast that makes the "
                   "other three readable: few dates and many transaction days "
                   "is a channel, many dates and one transaction day is an "
                   "import",
         "gap": "none"},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight = _weight(rng, common.Stamper(base_hour=7), end)
    daily_stamp = common.Stamper(base_hour=21)
    daily = (_phone_app(rng, daily_stamp, end)
             + _chest_strap(rng, common.Stamper(base_hour=7))
             + _club_treadmill(rng, common.Stamper(base_hour=19)))
    backfill = _backfill(rng)
    instruments = _instruments(common.Stamper(base_hour=20))

    return {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        # ITS OWN STREAM (#105). A one-time import is a second writer, and its
        # stamps cannot be interleaved by date into a file the athlete's own
        # devices were writing as they went.
        "data/daily.old-band.jsonl": common.jsonl_text(
            common.sort_rows(backfill)),
        "data/instruments.jsonl": common.jsonl_text(
            common.sort_rows(instruments)),
        "expectations.jsonl": common.jsonl_text(_expectations()),
    }
