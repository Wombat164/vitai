"""A night has an interval, not just a length (marcus@2).

`sleep_h` was 61.8% populated across the ten personas and the demo, and
`sleep_start` and `sleep_end` were 0%. A design that has to say when a day
begins (#203), or which part of the day a session fell in (#212), cannot be
confirmed against a corpus with no sleep timing in it at all - so both were
being decided on an anchor nothing could check.

This pins what the fixture CLAIMS about itself. A generator's docstring is a
checkable claim like any other, and a corpus that quietly stopped matching its
own description would be worse than no corpus.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MARCUS = ROOT / "tests" / "fixtures" / "personas" / "marcus"


# The gap the generator is designed to produce, and a band rather than a
# floor. A one-sided `> 0.5` was calibrated to pass rather than to
# discriminate: the real gap is about 0.9 h, so flattening the design by 40%
# still cleared the bar and nothing said the pattern had gone. A band fails in
# both directions, which is what pins a shape rather than a minimum.
DESIGNED_GAP_H = 1.0
GAP_TOLERANCE_H = 0.25


def _assert_gap(observed: float) -> None:
    assert abs(observed - DESIGNED_GAP_H) <= GAP_TOLERANCE_H, observed


def _bedtime(row: dict) -> float:
    """Lights-out as a number, with past-midnight reading as 24+ - or a 00:30
    bedtime averages in as early evening."""
    t = datetime.fromisoformat(row["sleep_start"])
    hour = t.hour + t.minute / 60
    return hour if hour > 12 else hour + 24


def _rows() -> list[dict]:
    return [json.loads(line) for line
            in (MARCUS / "data" / "daily.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def nights() -> list[dict]:
    got = [r for r in _rows() if r.get("sleep_start")]
    assert got, "marcus logs no sleep intervals; the whole fixture is the point"
    return got


def test_every_night_with_a_length_also_has_an_interval(nights):
    assert len(nights) == len(
        [r for r in _rows() if r.get("sleep_h") is not None])


def test_the_interval_and_the_length_agree_to_the_second(nights):
    """Two fields describing one night that disagree would teach a reader to
    trust neither. This caught a real defect: the first cut did the arithmetic
    on naive clocks and stamped each end with its own date's offset, which put
    the two fields an hour apart on every night that crossed a DST boundary."""
    for row in nights:
        began = datetime.fromisoformat(row["sleep_start"])
        ended = datetime.fromisoformat(row["sleep_end"])
        assert (ended - began).total_seconds() / 3600 == pytest.approx(
            row["sleep_h"], abs=1e-9), row["date"]


def test_every_boundary_is_offset_aware(nights):
    """A naive boundary would be a different fact from an aware one, and the
    engine refuses to guess which (#38). The fixture must not make it."""
    for row in nights:
        for key in ("sleep_start", "sleep_end"):
            assert datetime.fromisoformat(row[key]).tzinfo is not None, row


def test_the_night_ends_on_the_day_the_row_is_dated(nights):
    """A `daily` row for D describes the night that ENDED on the morning of D.
    Getting this backwards would put every night on the wrong day, which is
    invisible in aggregate and wrong in every single-day reading."""
    for row in nights:
        assert datetime.fromisoformat(row["sleep_end"]).date().isoformat() \
            == row["date"], row["date"]
        # NOT strictly the day before: a bedtime past midnight starts on the
        # row's own date, which is the honest reading of a 00:20 lights-out
        # and is common here on a Friday or in the holidays.
        began = datetime.fromisoformat(row["sleep_start"]).date().isoformat()
        assert began <= row["date"], row["date"]


def test_a_school_night_runs_earlier_than_a_free_one(nights):
    """The claim the generator makes about him: he teaches, so the night
    before a school day is the constrained one. Checked as a POPULATION rather
    than per row - any single night can run late - because the claim is about
    a pattern and a per-row assertion would be false by design."""
    from tests.fixtures.personas._gen.marcus import is_holiday

    school, free = [], []
    for row in nights:
        day = datetime.fromisoformat(row["date"]).date()
        (school if day.weekday() < 5 and not is_holiday(day) else free
         ).append(_bedtime(row))

    assert school and free
    _assert_gap(sum(free) / len(free) - sum(school) / len(school))


def test_a_holiday_weekday_is_a_free_night_not_a_school_one(nights):
    """SEPARATELY, because blending them hides the term calendar entirely. The
    first version compared weekdays-in-term against everything else, and
    deleting `is_holiday` from the bedtime rule left it green - so the claim
    the fixture rests on, that his school terms shape his nights, was pinned
    by nothing. A weekday in the holidays has the same weekday and none of the
    constraint, which is the only comparison that isolates the calendar."""
    from tests.fixtures.personas._gen.marcus import is_holiday

    term, holiday = [], []
    for row in nights:
        day = datetime.fromisoformat(row["date"]).date()
        if day.weekday() >= 5:
            continue
        (holiday if is_holiday(day) else term).append(_bedtime(row))

    assert term and holiday
    _assert_gap(sum(holiday) / len(holiday) - sum(term) / len(term))


# The nights that cross a British Summer Time change, written out. Verified
# against the real UK calendar - BST runs from the last Sunday in March to the
# last Sunday in October - rather than counted off the generator's output. The
# first version of this test asserted a COUNT of four, taken from what the
# generator happened to produce, and the generator was wrong: it decided the
# offset from a date rather than an instant, so 00:30 on the October Sunday
# was stamped GMT when it was still BST, and the night ending 2029-10-28 lost
# its crossing. A control read off the thing it polices certifies the defect
# and then resists the fix.
CLOCK_CHANGE_NIGHTS = {
    "2028-03-26",   # BST begins, 2028
    "2028-10-29",   # BST ends, 2028
    "2029-03-25",   # BST begins, 2029
    "2029-10-28",   # BST ends, 2029 - he goes to bed at 00:30, still BST
    "2030-03-31",   # BST begins, 2030
    # BST 2030 ends on 2030-10-27, past the end of his record.
}


def test_exactly_the_right_nights_cross_a_clock_change(nights):
    """A reader subtracting local times is wrong on exactly these; one
    comparing instants is not."""
    crossing = {r["date"] for r in nights
                if datetime.fromisoformat(r["sleep_start"]).utcoffset()
                != datetime.fromisoformat(r["sleep_end"]).utcoffset()}
    assert crossing == CLOCK_CHANGE_NIGHTS


def test_the_wall_clock_moves_and_the_elapsed_time_does_not(nights):
    for row in (r for r in nights if r["date"] in CLOCK_CHANGE_NIGHTS):
        began = datetime.fromisoformat(row["sleep_start"])
        ended = datetime.fromisoformat(row["sleep_end"])
        wall = ended.replace(tzinfo=None) - began.replace(tzinfo=None)
        assert abs(wall.total_seconds() / 3600 - row["sleep_h"]) == \
            pytest.approx(1.0, abs=1e-9), row["date"]


def test_one_definition_of_british_summer_time(nights):
    """The file had two: a fixed-date approximation stamping sessions and
    weigh-ins, and the real last-Sunday rule stamping sleep. They disagreed on
    twelve days a year, and on 2029-10-27 that put a run twelve minutes before
    a wake by the wall clock and forty-eight minutes after it by the instant -
    two readers, opposite orderings, one morning."""
    from tests.fixtures.personas._gen.marcus import _offset, _uk_offset

    for row in nights:
        day = datetime.fromisoformat(row["date"]).date()
        assert _offset(day) == _uk_offset(
            datetime.combine(day, datetime.min.time()).replace(hour=7))


def test_nothing_is_logged_before_he_wakes(nights):
    """The night has to bound the day it is dated to. Drawing it from its own
    stream put 73 sessions and 33 weigh-ins inside the recorded night - a
    contradiction no reader could take as anything but signal, produced by two
    uncorrelated generators."""
    woke = {r["date"]: datetime.fromisoformat(r["sleep_end"]) for r in nights}

    sessions = [json.loads(line) for line
                in (MARCUS / "data" / "sessions.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]
    early = [r for r in sessions if r.get("start_time") and r["date"] in woke
             and datetime.fromisoformat(r["start_time"]) < woke[r["date"]]]
    assert not early, [r["date"] for r in early[:5]]

    weights = [json.loads(line) for line
               in (MARCUS / "data" / "weight.jsonl").read_text(
                   encoding="utf-8").splitlines() if line.strip()]
    for row in weights:
        if not row.get("measured_at") or row["date"] not in woke:
            continue
        when = woke[row["date"]]
        hour, minute = (int(x) for x in row["measured_at"].split(":"))
        assert when.replace(hour=hour, minute=minute) >= when, row["date"]


def test_the_findings_record_what_the_version_added():
    text = (MARCUS / "FINDINGS.md").read_text(encoding="utf-8")
    assert "marcus@2" in text
    assert "clock change" in text
