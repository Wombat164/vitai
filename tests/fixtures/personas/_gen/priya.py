"""Generator for the priya persona (seed 101).

Leeds, UK. 34, ICU nurse, rotating 4-on-4-off shifts including nights, no
wearable and no intention of getting one. The record runs eight weeks, short
and beginner-shaped: one binary skill goal (a single strict pull-up, never
achieved in the record) and a "show up three times a week" habit goal. See
`PROFILE.md`, `LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md` alongside
this file for the prose this generator's numbers have to agree with. Entirely
synthetic; any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself - `generate.py` decides
whether that content lands on disk or is compared against what is already
committed.

Written and verified against installed `vitai 0.2.3` (see `_gen/common.py`'s
schema pin). Re-verify this generator against the handbook before trusting
its output once that version changes.
"""

from __future__ import annotations

import random
from datetime import date

from . import common

SEED = 101
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# The record's own calendar - a fixed piece of her history, not a window that
# slides with wherever the corpus currently ends.
START = date(2030, 5, 5)
DEFAULT_END = date(2030, 6, 30)

# Her rota: a 16-day macro-cycle of 4 day-shifts, 4 off, 4 nights, 4 off -
# "4-on-4-off", rotating between a day block and a night block. One date is
# hand-overridden below: a colleague's shift picked up at short notice, which
# is what turns four ordinary day-shifts into the five-in-a-row that empties
# week 3 of any training at all. No lie there, just a hole.
BRUTAL_EXTRA_SHIFT = date(2030, 5, 20)


def _shift_kind(d: date) -> str:
    """'day', 'night', or 'off', from the rota cycle plus the one override."""
    if d == BRUTAL_EXTRA_SHIFT:
        return "day"
    offset = (d - START).days % 16
    if 0 <= offset <= 3:
        return "day"
    if 8 <= offset <= 11:
        return "night"
    return "off"


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    daily_stamper = common.Stamper(base_hour=20)
    sessions_stamper = common.Stamper(base_hour=21)
    checks_stamper = common.Stamper(base_hour=18)
    goals_stamper = common.Stamper(base_hour=9)
    journal_stamper = common.Stamper(base_hour=22)

    daily = _daily(rng, daily_stamper, end)
    sessions, backfill_expectations, backfill_note = _sessions(rng, sessions_stamper)
    checks = _checks(checks_stamper)
    goals = _goals(goals_stamper)
    journal = _journal(journal_stamper)

    expectations = backfill_expectations + [
        _e_clustering(backfill_note),
        _e_adherence_claim(),
        _e_deviceless(),
        _e_skill_goal(),
        _e_subjective_day(),
    ]

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/checks.jsonl": common.jsonl_text(common.sort_rows(checks)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
    return files


# --- daily -------------------------------------------------------------------


def _daily(rng: random.Random, stamper: common.Stamper, end: date) -> list[dict]:
    """Sleep only, on about 40% of days. No steps ever - there is no
    wearable in this life, and there never will be (PROFILE.md, WORLD.md).
    """
    rows = []
    all_days = list(common.daterange(START, end))
    n_logged = round(len(all_days) * 0.4)
    logged = sorted(rng.sample(all_days, n_logged))
    for d in logged:
        kind = _shift_kind(d)
        if kind in ("night",):
            sleep_h = round(rng.uniform(3.5, 5.5), 1)
        elif kind == "day":
            sleep_h = round(rng.uniform(5.5, 7.0), 1)
        else:
            sleep_h = round(rng.uniform(6.5, 8.5), 1)
        note = None
        if kind == "night" and rng.random() < 0.35:
            note = "slept in the afternoon, never feels like real sleep"
        fields = {
            "date": d.isoformat(), "sleep_h": sleep_h, "source": "hand",
            "coverage": "manual", "capture": "manual_entry", "note": note,
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("daily", **fields))
    return rows


# --- sessions ------------------------------------------------------------------

# Strength sessions that count toward "show up 3x/wk": (date, HH:MM).
_STRENGTH_DATES = [
    (date(2030, 5, 9), "17:00"), (date(2030, 5, 10), "10:30"),
    (date(2030, 5, 11), "10:00"),
    (date(2030, 5, 12), "11:00"), (date(2030, 5, 15), "02:50"),
    (date(2030, 5, 17), "10:00"),
    # week 3: none - the brutal five-in-a-row stretch, see BRUTAL_EXTRA_SHIFT.
    (date(2030, 5, 26), "10:00"), (date(2030, 5, 29), "03:40"),
    (date(2030, 5, 31), "04:10"),
    (date(2030, 6, 2), "10:00"), (date(2030, 6, 4), "15:00"),
    (date(2030, 6, 5), "11:00"),
    # week 6: the six-row Sunday back-fill, handled separately below.
    (date(2030, 6, 18), "10:00"), (date(2030, 6, 20), "15:00"),
    (date(2030, 6, 21), "10:30"),
    (date(2030, 6, 26), "10:00"), (date(2030, 6, 28), "15:00"),
    (date(2030, 6, 29), "11:00"),
]

# Easy recovery walks along the canal towpath - never counted toward the
# strength goal (it filters on session_type), just her life outside the gym.
_WALK_DATES = [date(2030, 5, 18), date(2030, 5, 28), date(2030, 6, 3),
               date(2030, 6, 19), date(2030, 6, 27)]

# The six-row Sunday back-fill (LIES.md P1). All six dates fall in the week
# of 2030-06-09..06-15; she copies the week's plan into the log in one
# sitting on the evening of 2030-06-16, before clocking in for a night shift.
# Two of the six never happened - which two is chosen once below, seeded, so
# a rerun always picks the same pair.
_BACKFILL_PLAN = [
    (date(2030, 6, 9), "06:15"), (date(2030, 6, 10), "10:30"),
    (date(2030, 6, 12), "17:00"), (date(2030, 6, 13), "10:00"),
    (date(2030, 6, 14), "03:40"), (date(2030, 6, 15), "03:40"),
]
_BACKFILL_RECORDED_DATE = date(2030, 6, 16)
_BACKFILL_RECORDED_TIME = (19, 12)  # HH:MM of the first stamped row
_BACKFILL_STEP_S = 45

# The subjective-day case (F6/G61): a session at 02:50 during the second of
# four consecutive nights. The shift started the evening before
# (2030-05-14, a Tuesday); by the clock the set happens on 2030-05-15, a
# Wednesday, and the `date` field must say so - but nothing in the schema
# carries the fact that, to her, it was still "Tuesday's shift".
_SUBJECTIVE_DAY_DATE = date(2030, 5, 15)
_SUBJECTIVE_DAY_TIME = "02:50"


def _strength_row(rng: random.Random, stamper: common.Stamper, d: date,
                   hhmm: str, note: str | None = None) -> dict:
    duration_s = int(rng.uniform(18, 32) * 60)
    fields = {
        "date": d.isoformat(), "type": "strength", "duration_s": duration_s,
        "rpe": rng.choice([5, 6, 6, 7, 8]), "note": note, "source": "hand",
        "start_time": f"{d.isoformat()}T{hhmm}:00{common.irish_offset(d)}",
        "setting": "indoor",
        "place": "hospital gym" if _shift_kind(d) in ("day", "night") else "home",
        "context": "solo", "type_source": "athlete-stated",
        "capture": "manual_entry", "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _walk_row(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    duration_s = int(rng.uniform(25, 40) * 60)
    fields = {
        "date": d.isoformat(), "type": "walk", "duration_s": duration_s,
        "rpe": rng.choice([2, 2, 3]), "note": "canal towpath, easy legs",
        "source": "hand",
        "start_time": f"{d.isoformat()}T11:00:00{common.irish_offset(d)}",
        "setting": "outdoor", "place": "canal towpath", "context": "solo",
        "weather": rng.choice(["dry", "dry", "rain", "wind", "cold"]),
        "type_source": "athlete-stated", "capture": "manual_entry",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _sessions(rng: random.Random, stamper: common.Stamper
              ) -> tuple[list[dict], list[dict], str]:
    rows: list[dict] = []

    for d, hhmm in _STRENGTH_DATES:
        note = None
        if d == _SUBJECTIVE_DAY_DATE and hhmm == _SUBJECTIVE_DAY_TIME:
            note = ("second night in a row, quick set by the stairwell - "
                     "still feels like Tuesday's shift to me")
        rows.append(_strength_row(rng, stamper, d, hhmm, note=note))

    for d in _WALK_DATES:
        rows.append(_walk_row(rng, stamper, d))

    # --- the P1 back-fill --------------------------------------------------
    phantom_idx = set(sorted(rng.sample(range(len(_BACKFILL_PLAN)), 2)))
    backfill_recorded_at = []
    hh, mm = _BACKFILL_RECORDED_TIME
    for i in range(len(_BACKFILL_PLAN)):
        total_s = i * _BACKFILL_STEP_S
        rhh = hh + (mm * 60 + total_s) // 3600
        rmm = ((mm * 60 + total_s) // 60) % 60
        rss = total_s % 60
        backfill_recorded_at.append(
            f"{_BACKFILL_RECORDED_DATE.isoformat()}T{rhh:02d}:{rmm:02d}:"
            f"{rss:02d}{common.irish_offset(_BACKFILL_RECORDED_DATE)}")

    lie_expectations: list[dict] = []
    phantom_dates: list[str] = []
    for i, (d, hhmm) in enumerate(_BACKFILL_PLAN):
        duration_s = int(rng.uniform(18, 32) * 60)
        fields = {
            "date": d.isoformat(), "type": "strength", "duration_s": duration_s,
            "rpe": rng.choice([5, 6, 6, 7, 8]), "note": None, "source": "hand",
            "start_time": f"{d.isoformat()}T{hhmm}:00{common.irish_offset(d)}",
            "setting": "indoor",
            "place": "hospital gym" if _shift_kind(d) in ("day", "night") else "home",
            "context": "solo", "type_source": "athlete-stated",
            "capture": "manual_entry", "recorded_at": backfill_recorded_at[i],
        }
        rows.append(common.record("sessions", **fields))
        if i in phantom_idx:
            phantom_dates.append(d.isoformat())
            lie_expectations.append({
                "id": f"priya-E1-{len(phantom_dates):02d}",
                "kind": "lie",
                "dataset": "sessions",
                "dates": [d.isoformat()],
                "claim": (f"a {duration_s // 60}-minute strength session "
                          f"happened on {d.isoformat()} at {hhmm}"),
                "truth": "this session never happened",
                "expect": ("the engine has no back-fill detector today and "
                           "must not invent one from a single row; it may "
                           "note, as an observation about the record, that "
                           "six sessions.jsonl rows dated across "
                           f"{_BACKFILL_PLAN[0][0].isoformat()}.."
                           f"{_BACKFILL_PLAN[-1][0].isoformat()} were all "
                           f"recorded_at within a few minutes of each other "
                           f"on {_BACKFILL_RECORDED_DATE.isoformat()} "
                           "evening, but that observation alone can never "
                           "single out this row as false - it is symmetric "
                           "with the four true rows in the same cluster"),
                "gap": ("new: no back-fill/batch-entry detector exists; "
                        "recorded_at clustering across many claimed dates "
                        "is observable but not evaluated, and could not "
                        "distinguish this row from a true one even if it "
                        "were"),
            })

    backfill_note = (
        f"six sessions.jsonl rows dated {_BACKFILL_PLAN[0][0].isoformat()} "
        f"through {_BACKFILL_PLAN[-1][0].isoformat()} (skipping "
        f"2030-06-11) share recorded_at values within "
        f"{(len(_BACKFILL_PLAN) - 1) * _BACKFILL_STEP_S} seconds of each "
        f"other, all on the evening of "
        f"{_BACKFILL_RECORDED_DATE.isoformat()}; two of the six "
        f"({', '.join(phantom_dates)}) never happened, the other four did")
    return rows, lie_expectations, backfill_note


# --- checks --------------------------------------------------------------------

_CHECKS = [
    (date(2030, 5, 9), 0, "dead hang only - can hold the bar, zero pull"),
    (date(2030, 5, 17), 20, "20 second flexed-arm hang from a box, no pull-up"),
    (date(2030, 5, 26), 3, "3 second controlled negative from standing on a box"),
    (date(2030, 6, 12), 1, "1 rep with the thick band, unassisted still zero"),
    (date(2030, 6, 27), 2, "2 second chin-over hold, could not lock out - "
                           "still not a strict rep"),
]


def _checks(stamper: common.Stamper) -> list[dict]:
    rows = []
    for d, value, note in _CHECKS:
        fields = {
            "date": d.isoformat(), "slug": "strict-pullup-check",
            "result": "fail", "value": value, "source": "athlete",
            "note": note, "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("checks", **fields))
    return rows


# --- goals ---------------------------------------------------------------------


def _goals(stamper: common.Stamper) -> list[dict]:
    d = START
    skill = {
        "date": d.isoformat(), "slug": "strict-pullup",
        "title": "One strict pull-up",
        "policy": "monotonic", "period": "none", "status": "active",
        "motivator": "Get one full dead-hang pull-up, no band, no jump",
        "rationale": ("the arms are already long; this is the one specific "
                      "thing worth chasing on its own"),
        "set_by": "athlete", "verification": "attested",
        "recorded_at": stamper.stamp(d),
    }
    show_up = {
        "date": d.isoformat(), "slug": "show-up-3x-week",
        "title": "Show up for strength three times a week",
        "metric": "session_count",
        "session_type": "strength", "target": 3, "policy": "monotonic",
        "period": "weekly", "on_period_end": "reset", "status": "active",
        "motivator": "the rota already runs her life; this is the one thing "
                     "she gets to decide",
        "rationale": ("three is enough to matter and small enough to "
                      "survive a bad week"),
        "on_success": "hold", "on_miss": "reflect", "set_by": "athlete",
        "verification": "measured", "recorded_at": stamper.stamp(d),
    }
    # `dataset` collides with `common.record`'s own first positional
    # parameter (also named `dataset`, for the table); it cannot be passed
    # as a keyword into the skeleton builder, so it is set afterward on the
    # plain dict instead.
    show_up_rec = common.record("goals", **show_up)
    show_up_rec["dataset"] = "sessions"
    return [common.record("goals", **skill), show_up_rec]


# --- journal ---------------------------------------------------------------------


_JOURNAL = [
    (date(2030, 5, 6), "note",
     "starting to actually write this down instead of just carrying it "
     "around in my head. Dev thinks I'm mad to add one more thing to track."),
    (date(2030, 5, 15), "note",
     "second night done, quick set of negatives in the stairwell at 3 - "
     "brain still thinks it's Tuesday even though the form says the 15th."),
    (date(2030, 5, 24), "note",
     "five in a row this week, picked up Grace's shift on top of my own "
     "because nobody else could. Nothing happened on the bar this week and "
     "that's apparently fine, but it doesn't feel fine."),
    (date(2030, 5, 30), "worry",
     "starting to wonder if arms this long are ever going to get a chin "
     "over that bar, or if I've just picked the one thing built against me."),
    (date(2030, 6, 16), "note",
     "caught up the whole week's log in one go before clocking in tonight - "
     "easier to do it all at once than try to remember which night was "
     "which afterwards."),
    (date(2030, 6, 19), "claim",
     "I have not missed a single planned session since I started this."),
    (date(2030, 6, 27), "note",
     "two seconds isn't nothing. Dev says it's not nothing. I keep telling "
     "myself that on the walk home."),
]


def _journal(stamper: common.Stamper) -> list[dict]:
    rows = []
    for d, kind, text in _JOURNAL:
        fields = {
            "date": d.isoformat(), "kind": kind, "text": text,
            "source": "athlete",
            "about": "show-up-3x-week" if kind == "claim" else None,
            "confidence": 0.85 if kind == "claim" else None,
            "status": "open" if kind == "claim" else None,
            "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("journal", **fields))
    return rows


# --- expectations (non-lie rows) --------------------------------------------------


def _e_clustering(backfill_note: str) -> dict:
    return {
        "id": "priya-E2", "kind": "gap", "dataset": "sessions",
        "dates": [d.isoformat() for d, _ in _BACKFILL_PLAN],
        "claim": "six planned strength sessions for the week of 2030-06-09 "
                 "appear in the record, spread across six different dates",
        "truth": backfill_note,
        "expect": ("the engine may surface the clustering itself as a "
                   "plain observation ('N rows recorded within a few "
                   "minutes of each other, spanning M calendar dates') - "
                   "this is available from `recorded_at` alone - but must "
                   "never treat a back-filled cluster as evidence of "
                   "fraud, and must never single out any one row in the "
                   "cluster over another. Compare marcus M3: a habitual "
                   "Sunday back-fill of TRUE data must trigger the exact "
                   "same observation with no different conclusion"),
        "gap": "new: no back-fill/batch-entry detector exists today",
    }


def _e_adherence_claim() -> dict:
    return {
        "id": "priya-E3", "kind": "gap", "dataset": "journal",
        "dates": ["2030-06-19", "2030-05-19", "2030-05-25"],
        "claim": "journal, 2030-06-19: 'I have not missed a single planned "
                 "session since I started this.'",
        "truth": "the week of 2030-05-19..2030-05-25 has zero sessions.jsonl "
                 "rows - the five-shift stretch that emptied week 3",
        "expect": ("nothing in the engine today compares a journal claim "
                   "against the sessions record. If it did, the correct "
                   "output is an observation contrasting the claim with "
                   "the week-3 gap, never an adjudication of her honesty "
                   "or character - the same class-(a) treatment as any "
                   "other record-vs-record mismatch"),
        "gap": "no journal-claim-vs-record cross-check exists today",
    }


def _e_deviceless() -> dict:
    return {
        "id": "priya-E4", "kind": "behavior", "dataset": "daily",
        "dates": [START.isoformat(), DEFAULT_END.isoformat()],
        "claim": "daily.jsonl carries zero steps rows across the whole "
                 "eight-week record, and sleep_h on well under half the "
                 "days",
        "truth": ("there is no wearable anywhere in this life and there "
                  "will not be one; this is a complete record for who she "
                  "is, not an incomplete import of who a device-wearing "
                  "athlete would be"),
        "expect": ("status output and the rollup must not read the "
                   "absence of steps as missing data to chase, and must "
                   "stay useful from sleep_h plus the session log plus the "
                   "pull-up goal alone (G64 low-data mode)"),
        "gap": "G64: deviceless / low-data mode is not fully built",
    }


def _e_skill_goal() -> dict:
    return {
        "id": "priya-E5", "kind": "behavior", "dataset": "goals",
        "dates": [c[0].isoformat() for c in _CHECKS],
        "claim": "the strict-pullup goal has no numeric target or "
                 "progress series; five checks over eight weeks all read "
                 "result=fail",
        "truth": ("the true progression is visible only in the checks' "
                  "`value`/`note` fields: 0 -> a 20 second hang hold -> a "
                  "3 second negative -> a 1 rep band-assisted set -> a 2 "
                  "second chin-over hold, each still short of a strict "
                  "unassisted rep"),
        "expect": ("the engine must read progress from the checks series "
                   "(a skill goal's proxy indicators), not treat five "
                   "consecutive fail results as a stalled goal, and must "
                   "never invent a percentage-complete figure for an "
                   "attested binary goal that structurally has none"),
        "gap": "G62: goal kind (quantity/skill/maintenance) and "
               "proxy/leading indicators for skill goals are not modelled",
    }


def _e_subjective_day() -> dict:
    return {
        "id": "priya-E6", "kind": "gap", "dataset": "sessions",
        "dates": [_SUBJECTIVE_DAY_DATE.isoformat()],
        "claim": f"the {_SUBJECTIVE_DAY_DATE.isoformat()} 02:50 session's "
                 "own note calls it part of a shift that, by the note's "
                 "own words, feels like the day before",
        "truth": "the night shift she was on started the evening of "
                 "2030-05-14 (a Tuesday) and ran past midnight; the row's "
                 "`date` field correctly names 2030-05-15 (a Wednesday), "
                 "the calendar day the clock read at the moment of the set",
        "expect": ("the engine must treat the stored `date` field as "
                   "authoritative and never re-derive a different day "
                   "from note text. A future cadence/day-anchor feature "
                   "could recognise a night shift straddling midnight as "
                   "one subjective day rather than an error; today there "
                   "is no such concept and the mismatch is invisible "
                   "except in prose"),
        "gap": "G61: the subjective day (wake-to-wake, not midnight-to-"
               "midnight) is not modelled",
    }


_TOML = """# priya: synthetic persona corpus, thresholds tuned to her record.
[tripwires]
sleep_floor_h = 6.0

# Exactly one source appears anywhere in this record: hand-typed, no
# wearable, ever. Once [resolution] exists at all, an unlisted source is a
# hard validate failure, not a warning (handbook pitfall 4).
[resolution]
source_order = ["hand"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""
