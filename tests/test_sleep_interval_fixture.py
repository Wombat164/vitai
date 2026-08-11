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
    assert len(nights) == len([r for r in _rows() if r.get("sleep_h")])


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

    def bedtime(row: dict) -> float:
        t = datetime.fromisoformat(row["sleep_start"])
        hour = t.hour + t.minute / 60
        # Past midnight reads as 24+, or a 00:30 bedtime averages as early.
        return hour if hour > 12 else hour + 24

    school, free = [], []
    for row in nights:
        day = datetime.fromisoformat(row["date"]).date()
        (school if day.weekday() < 5 and not is_holiday(day) else free
         ).append(bedtime(row))

    assert school and free
    assert sum(free) / len(free) - sum(school) / len(school) > 0.5


def test_four_nights_cross_a_clock_change(nights):
    """The edge the corpus did not have. A reader subtracting local times gets
    an hour wrong on exactly these; one comparing instants does not."""
    crossing = [r for r in nights
                if datetime.fromisoformat(r["sleep_start"]).utcoffset()
                != datetime.fromisoformat(r["sleep_end"]).utcoffset()]
    assert len(crossing) == 4, [r["date"] for r in crossing]
    for row in crossing:
        began = datetime.fromisoformat(row["sleep_start"])
        ended = datetime.fromisoformat(row["sleep_end"])
        # The wall clock moves and the elapsed time does not.
        wall = (ended.replace(tzinfo=None) - began.replace(tzinfo=None))
        assert abs(wall.total_seconds() / 3600 - row["sleep_h"]) == \
            pytest.approx(1.0, abs=1e-9), row["date"]


def test_the_findings_record_what_the_version_added():
    text = (MARCUS / "FINDINGS.md").read_text(encoding="utf-8")
    assert "marcus@2" in text
    assert "clock change" in text
