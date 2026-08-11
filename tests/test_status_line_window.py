"""A retrospective import must not move a current figure (#33 item 5, G30).

The issue's acceptance is that "a 2020 smartphone step count must never be able
to move a 2026 verdict". Measured after #171 landed, which is when the item was
due a re-read:

VERDICTS ALREADY SATISFY IT. They key on the ISO week, so a 2020 row lands in a
2020 week and cannot reach a 2026 one. Constructed and checked below: adding a
seven-day 2020 import to a 2026 record leaves the 2026 steps verdict identical
in value and word, and only adds its own weeks.

`status_line` DID NOT. It took `steps[-7:]` - "the seven most recent rows that
happen to carry steps" - which on a sparse record spans years. G30 states the
rule in as many words: "an entry-count slice is not a window", and its own
docstring records the same defect found once already, with three step rows over
eighteen months printing as a current average.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import KEYS

ON = date(2026, 8, 11)


def day(when: str, steps: int) -> dict:
    return {**{k: None for k in KEYS["daily"]}, "date": when, "steps": steps,
            "source": "phone"}


def record(tmp_path: Path, rows: list[dict], on: date = ON) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsteps_floor = 8000\n',
        encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root, on=on)


SPARSE = [day("2020-03-01", 1200), day("2020-06-01", 1400),
          day("2021-01-01", 1500), day("2024-05-01", 1800),
          day("2026-08-05", 9000), day("2026-08-06", 9200),
          day("2026-08-07", 9100)]


# --- the surface that carried the defect ---------------------------------------

def test_years_old_rows_do_not_enter_a_current_average(tmp_path):
    """The measured case. This line read

        4,743 steps/day over the last 7 logged days (2026-08-07)

    which is half the athlete's actual figure, dated three days ago so it reads
    as current, and dragged there by a phone they stopped using six years
    earlier."""
    got = record(tmp_path, SPARSE).status_line()
    assert got.startswith("9,100 steps/day"), got
    assert "4,743" not in got


def test_it_says_how_much_of_the_window_was_logged(tmp_path):
    """A mean with no stated population reads as a claim about the whole
    window - the argument `over_days` already exists for."""
    assert "over 3 of the last 7 days" in record(tmp_path, SPARSE).status_line()


def test_a_complete_window_says_nothing_extra(tmp_path):
    rows = [day(f"2026-08-{n:02d}", 9000) for n in range(5, 12)]
    got = record(tmp_path, rows).status_line()
    assert got == "9,000 steps/day", got


def test_a_stale_record_says_so_rather_than_averaging_across_the_gap(tmp_path):
    """Nothing in the window is its own answer, and a better one than a
    six-year mean. Saying when the record last held a step count is a fact;
    averaging across the gap is the defect above, relabelled."""
    got = record(tmp_path, SPARSE[:4]).status_line()
    assert got == "no steps logged in the last 7 days (last was 2024-05-01)"


def test_an_empty_record_is_untouched(tmp_path):
    assert "nothing logged yet" in record(tmp_path, []).status_line()


def test_weight_still_leads_where_the_athlete_tracks_it(tmp_path):
    """G62/G64: the record reports what is in it. The steps path is the
    fallback and this change must not promote it."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in SPARSE), encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["weight"]}, "date": "2026-08-10", "kg": 74.2,
         "source": "scale"}) + "\n", encoding="utf-8")
    assert Vitai(root, on=ON).status_line().startswith("74.2 kg")


# --- and the half that was already right ---------------------------------------

def test_a_retrospective_import_does_not_move_a_current_verdict(tmp_path):
    """The issue's actual acceptance, checked rather than assumed. Verdicts key
    on the ISO week, so a 2020 row lands in a 2020 week."""
    now = [day(f"2026-08-{n:02d}", 9000) for n in range(5, 12)]
    old = [day(f"2020-03-{n:02d}", 1200) for n in range(1, 8)]

    def steps_weeks(rows):
        return {r["week"]: (r["value"], r["verdict"])
                for r in record(tmp_path / str(len(rows)), rows).verdicts()
                if r["metric"] == "steps"}

    without, with_old = steps_weeks(now), steps_weeks(old + now)
    current = max(without)
    assert without[current] == with_old[current], (without, with_old)
    assert len(with_old) > len(without), "the old weeks appear as their own"
