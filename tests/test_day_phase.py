"""Which part of WHOSE day a time fell in (#212).

The coarse tier of a two-tier temporal identity. The precise tier exists and
is nearly complete - `weight.measured_at` is 97% populated in the shipped
corpus and `sessions.start_time` 99% - and the coarse one did not exist at
all, so "morning weigh-in" went in a note as prose.

THE ANCHOR IS THE ATHLETE, NOT THE CLOCK, which is the whole decision. Quarters
of the day are clock-defined right up until somebody works nights, at which
point "morning" and 07:00 come apart. Every persona in this corpus but one
sleeps at night, so a clock-derived phase and a sleep-derived one agree on
almost all of them - which is exactly the shape that lets a wrong default
survive review.

The decision on this issue: the athlete's own timestamps propose, and sleep
confirms. A session start and a weigh-in time are the measured data that
exists; the sleep interval is what says whose day they belong to.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from vitai.api import Vitai, schema
from vitai.clocks import day_phase, phase_rule

ROOT = Path(__file__).resolve().parents[1]
MARCUS = ROOT / "tests" / "fixtures" / "personas" / "marcus"


# --- the rule -----------------------------------------------------------------

def test_an_ordinary_riser_lands_where_the_clock_would_put_them():
    """The check that the rule is not merely DIFFERENT. Anchored on waking at
    07:00 it reproduces the ordinary reading of the day almost exactly, which
    is what makes it safe to apply to everybody."""
    up = "2030-06-01T07:00:00"
    for at, want in (("07:30", "morning"), ("11:00", "morning"),
                     ("12:30", "afternoon"), ("16:00", "afternoon"),
                     ("18:00", "evening"), ("21:30", "evening"),
                     ("23:30", "night")):
        assert day_phase(f"2030-06-01T{at}:00", up) == want, at


def test_a_night_worker_does_not_get_the_clock_s_answer():
    """The case the rule exists for, and the one no fixture could demonstrate
    until a persona worked nights. She wakes at 16:00; half past six in the
    evening is the first thing she does that day."""
    up = "2030-06-01T16:00:00"
    assert day_phase("2030-06-01T18:30:00", up) == "morning"
    assert day_phase("2030-06-01T22:00:00", up) == "afternoon"
    assert day_phase("2030-06-02T02:00:00", up) == "evening"


def test_a_time_before_waking_is_night():
    """Not morning. The small hours of a day that has not started are a
    different fact from the same clock time sixteen hours after getting up."""
    assert day_phase("2030-06-01T03:00:00", "2030-06-01T07:00:00") == "night"


def test_no_anchor_means_no_phase():
    """THE DISCIPLINE. A weigh-in with no sleep row behind it is not "probably
    morning" because most of them are: absent stays absent, or the coarse tier
    becomes exactly the fabrication a two-tier identity exists to prevent."""
    assert day_phase("2030-06-01T09:00:00", None) is None
    assert day_phase("2030-06-01T09:00:00", "") is None
    assert day_phase(None, "2030-06-01T07:00:00") is None


def test_an_uncomparable_pair_has_no_phase_rather_than_a_guessed_one():
    """Naive against aware. The engine refuses to invent the missing offset
    (#38), so the phase is unavailable rather than approximated."""
    assert day_phase("2030-06-01T09:00:00", "2030-06-01T07:00:00+02:00") is None
    assert day_phase("2030-06-01T09:00:00+02:00", "2030-06-01T07:00:00") is None


def test_it_never_reads_anything_but_a_time_and_a_waking():
    """Not the dataset, not the athlete's habits, not the other rows that day.
    Two calls with the same pair must agree whatever else is true."""
    assert day_phase("2030-06-01T18:30:00", "2030-06-01T16:00:00") == \
        day_phase("2030-06-01T18:30:00", "2030-06-01T16:00:00")


# --- the rule is published, not left to be reinvented -------------------------

def test_the_rule_is_data():
    rule = phase_rule()
    assert rule["anchor"] == "sleep_end"
    assert rule["unanchored"] is None
    assert [b["phase"] for b in rule["boundaries"]] == \
        ["morning", "afternoon", "evening"]
    assert rule["beyond"] == "night"


def test_the_published_rule_describes_the_function_that_runs():
    """A published rule a client implements and an implementation that
    disagrees with it is worse than publishing nothing (#308's lesson)."""
    rule = phase_rule()
    up = "2030-06-01T06:00:00"
    for bound in rule["boundaries"]:
        inside = f"2030-06-01T{6 + bound['under'] - 1:02d}:00:00"
        assert day_phase(inside, up) == bound["phase"], bound
    beyond = f"2030-06-01T{6 + rule['boundaries'][-1]['under']:02d}:00:00"
    assert day_phase(beyond, up) == rule["beyond"]


def test_every_phase_it_can_return_is_in_the_published_vocabulary():
    """#346 adopted Open mHealth's part-of-day rather than inventing one. A
    derivation that returned a fifth value would be inventing one anyway."""
    from vitai.schema import day_phases

    vocabulary = set(day_phases())
    up = "2030-06-01T06:00:00"
    got = {day_phase(f"2030-06-0{d}T{h:02d}:00:00", up)
           for d in (1, 2) for h in range(24)}
    assert got - {None} <= vocabulary


# --- against a real record ----------------------------------------------------

def test_marcus_has_a_phase_on_every_timed_row():
    """He logs a sleep interval every night, so nothing of his is unanchored -
    which is the populated case. The unanchored case is the one a corpus
    without sleep timing could not previously show at all."""
    rows = Vitai(MARCUS).phases()
    assert rows
    assert all(r["phase"] for r in rows)
    assert {r["dataset"] for r in rows} == {"weight", "sessions"}


def test_a_bare_local_time_is_placed_against_the_same_local_clock():
    """`measured_at` is HH:MM and `sleep_end` is offset-aware, and comparing
    them as instants is refused - correctly, since the offset of the bare one
    is unknown. Reading the anchor's WALL CLOCK puts both in one frame by
    construction, which is the case the engine already sanctions for two naive
    stamps. Without it every weigh-in in the corpus is unanchored, which is
    260 of marcus's 700 timed rows and the whole dataset this issue was raised
    about."""
    weights = [r for r in Vitai(MARCUS).phases(dataset="weight")]
    assert weights
    assert all(r["phase"] for r in weights)
    assert all(len(str(r["at"])) == 5 for r in weights)


def test_a_row_with_no_sleep_behind_it_comes_back_unanchored(tmp_path):
    """It comes BACK, rather than being filtered out. A consumer given only
    the answerable rows reads an absence as a small number."""
    root = tmp_path / "content"
    from vitai.api import init
    v = Vitai(init(root))
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch",
                          "start_time": "2030-05-01T18:30:00"})
    got = v.phases()
    assert len(got) == 1
    assert got[0]["phase"] is None
    assert got[0]["anchored_on"] is None


def test_the_same_time_gets_different_phases_for_different_wakings(tmp_path):
    """The whole point, on a record rather than in the abstract. One session
    at 18:30; two athletes; two answers."""
    from vitai.api import init

    out = []
    for woke in ("06:30", "16:00"):
        root = init(tmp_path / f"c{woke[:2]}")
        v = Vitai(root)
        v.append("daily", {"date": "2030-05-01", "sleep_h": 7.0,
                           "sleep_start": "2030-04-30T23:30:00",
                           "sleep_end": f"2030-05-01T{woke}:00",
                           "source": "watch"})
        v.append("sessions", {"date": "2030-05-01", "type": "run",
                              "distance_km": 5.0, "source": "watch",
                              "start_time": "2030-05-01T18:30:00"})
        out.append(v.phases()[0]["phase"])
    assert out == ["evening", "morning"], out


# --- P9 -----------------------------------------------------------------------

def test_the_rule_reaches_the_published_schema():
    assert schema()["phase_rule"] == phase_rule()


def test_it_reaches_the_cli_and_the_agent_surface(tmp_path):
    from vitai.cli import main
    from vitai.mcp import call

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["phases", "--root", str(MARCUS), "--on", "2028-01-04", "--json"])
    rows = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert rows and all(r["phase"] for r in rows)
    assert call(MARCUS, "phases", {"on": "2028-01-04"}) == rows


def test_the_cli_says_how_much_is_unanchored(tmp_path):
    """A consumer that has to notice the dashes is one that will read them as
    a small number."""
    from vitai.api import init
    from vitai.cli import main

    root = init(tmp_path / "content")
    Vitai(root).append("sessions", {"date": "2030-05-01", "type": "run",
                                    "distance_km": 5.0, "source": "watch",
                                    "start_time": "2030-05-01T18:30:00"})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["phases", "--root", str(root)])
    out = buf.getvalue()
    assert "1 of 1 have no phase" in out
    assert "the clock is not an answer" in out


# --- what it deliberately does not do -----------------------------------------

def test_nothing_is_stored(tmp_path):
    """NOT WRITTEN DOWN, and this is a decision rather than an omission. The
    governing decision is that the athlete's timestamps PROPOSE and sleep
    CONFIRMS, so an unconfirmed phase is not a fact to record - and confirming
    the rest needs a channel to ask, which is #224. Until then the record
    claims no phase it cannot support."""
    from vitai.schema import KEYS

    assert "phase" not in KEYS["weight"]
    assert "phase" not in KEYS["sessions"]
    assert "for_phase" in KEYS["plans"]  # the one that was already there
