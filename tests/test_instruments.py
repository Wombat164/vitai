"""An instrument change looks exactly like a physiological one (#311).

`origin` said which instrument observed a value. Nothing said what that
instrument IS, or for which stretch of time it was the thing reporting under
that name - so a step in a number had two readings and the record could not
separate them.

The corpus already contained the confound before the register existed. ines
weighs 65.80 kg at the gym on 2030-05-30, against 64.14 kg at home the same
morning and 64.06 kg four days later: a 1.66 kg step and a 1.74 kg step back,
entirely instrumental.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.policy import instrument as resolve
from vitai.schema import (KEYS, overlapping_instrument_problems,
                          validate_record)

ROOT = Path(__file__).resolve().parents[1]
INES = ROOT / "tests" / "fixtures" / "personas" / "ines"
DEMO = ROOT / "examples" / "demo"


# A watch replaced mid-record, which no fixture has: the case the interval
# exists for, supplied as data rather than asserted from a file.
REPLACED = [
    {"origin": "garmin-watch", "from_date": "2026-01-01",
     "to_date": "2029-12-31", "name": "the old watch"},
    {"origin": "garmin-watch", "from_date": "2030-01-01",
     "to_date": None, "name": "the new watch"},
    {"origin": "withings-scale", "from_date": "2028-01-01",
     "to_date": None, "name": "the scale"},
]


# --- the join is (origin, date), never origin ---------------------------------

def test_one_identity_resolves_to_different_instruments_over_time():
    """The whole point. A lookup on the identity alone attributes every
    historical reading to whatever reports under that name now - silently
    confident, wrong at the edges, and invisible until somebody checks an old
    figure."""
    assert resolve(REPLACED, "garmin-watch", "2027-06-01")["name"] == "the old watch"
    assert resolve(REPLACED, "garmin-watch", "2030-06-01")["name"] == "the new watch"


def test_the_boundaries_are_inclusive_at_both_ends():
    for on, want in (("2029-12-31", "the old watch"),
                     ("2030-01-01", "the new watch")):
        assert resolve(REPLACED, "garmin-watch", on)["name"] == want


def test_a_date_before_anything_was_registered_resolves_to_nothing():
    """Not to the earliest interval. A reading from before the register knew
    of any instrument is unregistered, and saying otherwise would date a watch
    to before it was owned."""
    assert resolve(REPLACED, "garmin-watch", "2025-06-01") is None


def test_a_closed_interval_does_not_run_on():
    """`_in_force` answers "the last statement on or before this date", which
    is right for a policy that stays in force until replaced and wrong here:
    the watch sold in 2029 did not keep reporting into 2030 merely because no
    line replaced it."""
    only_closed = [REPLACED[0]]
    assert resolve(only_closed, "garmin-watch", "2029-12-31") is not None
    assert resolve(only_closed, "garmin-watch", "2030-01-01") is None


def test_an_open_interval_has_not_ended():
    assert resolve(REPLACED, "withings-scale", "2099-01-01")["name"] == "the scale"


def test_an_unregistered_origin_resolves_to_nothing():
    """And that is an answer, not a gap. The register adds a name to an
    identity that already works without one, so an empty register must not
    read as a populated one."""
    assert resolve(REPLACED, "phone", "2030-06-01") is None
    assert resolve([], "garmin-watch", "2030-06-01") is None


def test_it_never_resolves_on_source():
    """The issue proposed `(source or origin, date)`. That `or` crosses the
    line contract 40 drew: `source` is the CHANNEL a value arrived by,
    `origin` is the INSTRUMENT that observed it. Under the fallback a
    re-export - a channel change - would resolve to a different instrument and
    read as an instrument change, which is the confound this exists to
    remove."""
    rows = [dict(REPLACED[2], source="withings-api")]
    assert resolve(rows, "withings-api", "2030-06-01") is None
    assert resolve(rows, "withings-scale", "2030-06-01") is not None


# --- overlap is refused, or a reading belongs to two instruments -------------

def test_two_intervals_claiming_one_origin_are_a_problem():
    bad = [{"origin": "watch", "from_date": "2026-01-01", "to_date": None},
           {"origin": "watch", "from_date": "2030-01-01", "to_date": None}]
    assert overlapping_instrument_problems(bad)


def test_touching_intervals_overlap_on_the_shared_day():
    """A `to_date` is inclusive - the instrument reported ON that day - so an
    interval ending the day the next one starts claims one day twice."""
    touching = [
        {"origin": "watch", "from_date": "2026-01-01", "to_date": "2029-12-31"},
        {"origin": "watch", "from_date": "2029-12-31", "to_date": None}]
    assert overlapping_instrument_problems(touching)


def test_disjoint_intervals_and_different_origins_are_fine():
    assert overlapping_instrument_problems(REPLACED) == []


def test_a_retired_line_does_not_overlap_its_replacement():
    """`supersedes` withdraws a statement rather than adding a second one, so
    a corrected interval is compared as one interval and not as two."""
    from vitai.jsonl import line_key

    first = {"date": "2030-01-01", "origin": "watch",
             "from_date": "2030-01-01", "to_date": None}
    fixed = {"date": "2030-02-01", "origin": "watch",
             "from_date": "2029-06-01", "to_date": None,
             "supersedes": line_key("instruments", first)}
    assert overlapping_instrument_problems([first, fixed]) == []


# --- and the check is DISPATCHED, which for five contracts it was not (#418) --
#
# Every test above calls the function directly. That is what made the defect
# invisible: the check passed its own tests, in five places, and `api.validate`
# had never called it, so no record had ever been asked the question. The tests
# below go through `Vitai.validate` and `vitai validate` instead, so they fail
# if the dispatch is removed and the function is left standing.

def _row(**values) -> dict:
    """An `instruments` line carrying the whole registered shape.

    Filled from `KEYS` rather than hand-written, because a row missing a
    registered key is a validation PROBLEM in its own right - and a test that
    wants to prove the overlap is only an advisory cannot afford to be
    carrying eleven unrelated problems while it says so.
    """
    return {key: values.get(key) for key in KEYS["instruments"]} | values


def _record_with(tmp_path, instruments: list[dict], name: str = "rec") -> Path:
    """A record carrying exactly these instrument rows."""
    root = tmp_path / name
    (root / "data").mkdir(parents=True)
    (root / "data" / "instruments.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in instruments), encoding="utf-8")
    return root


OVERLAPPING = [
    _row(date="2026-01-01", origin="watch", from_date="2026-01-01",
         to_date=None, name="the first watch"),
    _row(date="2030-01-01", origin="watch", from_date="2030-01-01",
         to_date=None, name="the second watch"),
]


def test_validate_reports_an_overlap_rather_than_calling_the_record_sound(tmp_path):
    """The issue's evidence, turned into a test.

    Before this dispatch, this exact record got `all data lines valid` out of
    `vitai validate` while the function reported the ambiguity to anyone who
    called it by hand.
    """
    report = Vitai(_record_with(tmp_path, OVERLAPPING)).validate()
    assert any("claimed by two intervals at once" in a
               for a in report["advisories"]), report


def test_the_overlap_is_an_advisory_and_the_record_still_builds(tmp_path):
    """#38: both lines are legal, already on disk, and unaeditable, and the
    repair is an APPEND. Refusing the build would leave a record whose only
    fault is a shape the engine handles with no legal path to green."""
    report = Vitai(_record_with(tmp_path, OVERLAPPING)).validate()
    assert report["ok"] is True
    assert not any("claimed by two intervals" in p for p in report["problems"])


def test_appending_the_correction_clears_the_advisory(tmp_path):
    """The legal path to green, walked. This is the half that makes the
    advisory fair rather than permanent noise."""
    from vitai.jsonl import line_key

    fixed = OVERLAPPING[0] | {
        "date": "2030-02-01", "to_date": "2029-12-31",
        "supersedes": line_key("instruments", OVERLAPPING[0])}
    report = Vitai(_record_with(tmp_path, OVERLAPPING + [fixed])).validate()
    assert not any("claimed by two intervals" in a
                   for a in report["advisories"]), report


def test_it_reads_the_union_of_every_device_file(tmp_path):
    """Per-device files and a union merge (#105), so the two rows that collide
    can be in two files - which is when a shared origin is LIKELIEST, and is
    the case reading only `instruments.jsonl` would miss."""
    root = tmp_path / "rec"
    (root / "data").mkdir(parents=True)
    (root / "data" / "instruments.jsonl").write_text(
        json.dumps(OVERLAPPING[0]) + "\n", encoding="utf-8")
    (root / "data" / "instruments.laptop.jsonl").write_text(
        json.dumps(OVERLAPPING[1]) + "\n", encoding="utf-8")
    report = Vitai(root).validate()
    assert any("claimed by two intervals at once" in a
               for a in report["advisories"]), report


def test_the_shipped_corpus_produces_none(tmp_path):
    """The number this change is worth, stated rather than implied: zero.

    Dispatching a check that has never run is only news if something turns
    red, so the answer belongs in the suite where it can stop being true. Every
    record this repo ships - the demo and all sixteen persona fixtures - passes
    the check that had never been asked, and if a future fixture stops doing
    so this is where it says so.
    """
    import shutil

    roots = [DEMO] + sorted(
        p for p in (ROOT / "tests" / "fixtures" / "personas").iterdir()
        if (p / "data").is_dir())
    found = {}
    for src in roots:
        root = tmp_path / src.name
        shutil.copytree(src, root)
        found[src.name] = [a for a in Vitai(root).validate()["advisories"]
                           if "claimed by two intervals" in a]
    assert found and not any(found.values()), found


# --- what a row must say ------------------------------------------------------

@pytest.mark.parametrize("bad,expected", [
    ({"origin": "", "from_date": "2030-01-01"}, "'origin'"),
    ({"origin": "watch", "from_date": "not-a-date"}, "'from_date'"),
    ({"origin": "watch", "from_date": "2030-01-01", "to_date": "nope"},
     "'to_date'"),
    ({"origin": "watch", "from_date": "2030-06-01", "to_date": "2030-01-01"},
     "before 'from_date'"),
])
def test_a_row_that_registers_nothing_is_refused(bad, expected):
    from vitai.schema import _instrument_problems

    assert any(expected in p for p in _instrument_problems(bad)), bad


def test_an_absent_to_date_is_legal_and_means_still_in_use():
    """Not defaulted to today. A register that stamps an end date on
    everything still in service reads, a year later, as a shelf of retired
    equipment."""
    from vitai.schema import _instrument_problems

    assert _instrument_problems(
        {"origin": "watch", "from_date": "2030-01-01", "to_date": None}) == []


def test_a_malformed_start_is_reported_once():
    """Comparing `to_date` against a `from_date` already reported as malformed
    adds a second complaint about the first one's consequences, which reads as
    two defects."""
    from vitai.schema import _instrument_problems

    found = _instrument_problems({"origin": "watch", "from_date": "nope",
                                  "to_date": "2020-01-01"})
    assert len([p for p in found if "before 'from_date'" in p]) == 0


# --- it is not the other kind of device ---------------------------------------

def test_it_does_not_touch_the_field_that_says_who_wrote_the_line():
    """`device` is on every dataset and names the MACHINE THAT WROTE THE LINE
    DOWN (#105). Conflating it with the instrument that observed the value is
    the false-corroboration defect #35 exists to prevent, which is why this
    dataset is `instruments` and not the `devices` the issue proposed."""
    assert "device" in KEYS["instruments"]
    assert "origin" in KEYS["instruments"]
    from vitai.schema import sensitivity
    assert sensitivity("instruments", "device") == "provenance"
    assert sensitivity("instruments", "origin") == "provenance"


# --- the fixtures carry it ----------------------------------------------------

def test_ines_registers_the_two_scales_behind_her_own_confound():
    v = Vitai(INES)
    home = v.instrument("bathroom-scale", "2030-05-30")
    gym = v.instrument("gym-scale", "2030-05-30")
    assert home and gym
    assert home["name"] != gym["name"]
    # The gym scale was used once, so it is closed on the day it opened.
    assert gym["from_date"] == gym["to_date"] == "2030-05-30"
    assert v.instrument("gym-scale", "2030-06-03") is None


def test_the_step_the_register_explains_is_really_in_her_record():
    """Measured, not asserted. A fixture comment claiming a confound that the
    data does not contain would be worse than no fixture."""
    rows = [json.loads(line) for line
            in (INES / "data" / "weight.jsonl").read_text().splitlines()
            if line.strip()]
    by = {(r["date"], r.get("origin")): r["kg"] for r in rows if r.get("kg")}
    assert by[("2030-05-30", "gym-scale")] - by[("2030-05-30", "bathroom-scale")] \
        == pytest.approx(1.66, abs=0.01)


def test_the_demo_registers_its_instruments_and_they_validate():
    rows = [json.loads(line) for line
            in (DEMO / "data" / "instruments.jsonl").read_text().splitlines()
            if line.strip()]
    assert rows
    assert overlapping_instrument_problems(rows) == []
    for row in rows:
        assert validate_record("instruments", row) == []


def test_the_register_is_dated_when_it_is_listed():
    """Asking for "my instruments" on a date in 2027 must not list a watch
    bought in 2030, which is the same rule the resolver enforces - and listing
    them undated would be the way round it."""
    v = Vitai(DEMO)
    assert {r["origin"] for r in v.instruments("2030-04-21")} == {"scale"}
    assert "gym-console" in {r["origin"] for r in v.instruments("2030-06-30")}


# --- P9 -----------------------------------------------------------------------

def test_it_reaches_the_cli_and_the_agent_surface(tmp_path):
    import contextlib
    import io

    from vitai.cli import main
    from vitai.mcp import call

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["instruments", "--root", str(DEMO), "--json"])
    rows = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert {r["origin"] for r in rows} >= {"scale", "dexa"}

    assert call(DEMO, "instrument", {"origin": "scale"})["name"]
    assert call(DEMO, "instruments", {})


def test_the_cli_says_an_unregistered_origin_is_not_an_error(tmp_path):
    import contextlib
    import io

    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["instruments", "--root", str(DEMO), "--origin", "nothing-here"])
    out = buf.getvalue()
    assert "nothing is lost" in out
