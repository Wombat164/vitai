"""Which side an episode is on, and what became of a fixture (#145, #139).

Both found by the persona corpus rather than by reading the schema, and both
are the same shape: a fact the record could not hold, so it was smuggled into
prose or lost entirely.

`daily` has carried `pain_side` since generation 2, added so laterality
post-coordinates rather than being baked into a site name. `medical` had no
equivalent, so a left-knee episode and a right-knee episode were the same
episode - and gating "the knee" bans a movement the athlete performs perfectly
well on the other leg.

A confirmed, immovable race passed with no session row and its status stayed
`confirmed` forever, so three different things read identically: a race that
happened and produced no data, one the athlete did not attend, and one that
never took place. The first is the common one, because a race day is exactly
when logging is least likely.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai, init
from vitai.schema import (CURRENT_GENERATION, EVENT_OUTCOME_FHIR,
                          EVENT_OUTCOMES, KEYS, validate_record)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _episode(**kw) -> dict:
    rec = {k: None for k in KEYS["medical"]}
    rec.update({"date": "2030-05-01", "slug": "knee", "kind": "injury",
                "title": "an episode", "severity": "mild", "status": "active",
                "source": "athlete", "_gen": CURRENT_GENERATION["medical"]})
    rec.update(kw)
    return rec


def _event(**kw) -> dict:
    rec = {k: None for k in KEYS["events"]}
    rec.update({"date": "2030-07-01", "slug": "race", "title": "a race",
                "kind": "competition", "event_date": "2030-06-20",
                "status": "confirmed", "_gen": CURRENT_GENERATION["events"]})
    rec.update(kw)
    return rec


# --- which side (#145) -------------------------------------------------------

def test_an_episode_can_say_which_side_it_is_on():
    assert validate_record(
        "medical", _episode(body_site="knee", body_side="left")) == []


def test_the_two_knees_are_no_longer_the_same_episode(tmp_path):
    """The point of the field, through the surface that gates."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for side in ("left", "right"):
        v.append("medical", {"date": "2030-05-01", "slug": f"{side}-knee",
                             "kind": "injury", "title": "an episode",
                             "body_site": "knee", "body_side": side,
                             "severity": "mild", "status": "active",
                             "restricts": "impact", "source": "athlete"})

    reasons = " ".join(g["reason"] for g in v.gates("2030-05-02"))

    assert "left knee" in reasons and "right knee" in reasons


def test_a_gate_names_the_side_so_the_athlete_need_not_guess(tmp_path):
    """A gate reading "the calf" leaves an athlete to guess which leg, and
    guessing in the cautious direction rests a limb that is fine."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "calf", "kind": "injury",
                         "title": "a strain", "body_site": "calf",
                         "body_side": "right", "severity": "mild",
                         "status": "active", "restricts": "impact",
                         "source": "athlete"})

    gate, = v.gates("2030-05-02")

    assert "right calf" in gate["reason"]


def test_bilateral_reads_as_both_rather_than_as_a_side(tmp_path):
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "shins",
                         "kind": "injury", "title": "shin pain",
                         "body_site": "shin", "body_side": "bilateral",
                         "severity": "mild", "status": "active",
                         "restricts": "impact", "source": "athlete"})

    gate, = v.gates("2030-05-02")

    assert "both sides" in gate["reason"]


def test_a_gate_says_nothing_where_no_side_was_recorded(tmp_path):
    """Naming a side the record does not hold would be worse than saying
    less, and every episode written before this field has none."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "calf", "kind": "injury",
                         "title": "a strain", "body_site": "calf",
                         "severity": "mild", "status": "active",
                         "restricts": "impact", "source": "athlete"})

    gate, = v.gates("2030-05-02")

    assert "calf" not in gate["reason"].split(" - ")[-1]
    assert gate["reason"] == "a strain (active)"


def test_a_midline_site_takes_no_side():
    """Claiming one would be a false precision, which is the rule `daily`
    already applies - called here rather than copied."""
    problems = validate_record(
        "medical", _episode(body_site="abdomen", body_side="left"))

    assert any("midline" in p for p in problems)


def test_an_episode_written_before_the_field_still_validates():
    """Old lines keep validating. Requiring a side would have refused every
    episode already in every record."""
    rec = _episode(body_site="knee")
    rec.pop("body_side")
    rec["_gen"] = 5

    assert validate_record("medical", rec) == []


def test_an_unknown_side_is_refused():
    problems = validate_record(
        "medical", _episode(body_site="knee", body_side="port"))

    assert problems and any("body_side" in p for p in problems)


# --- what became of a fixture (#139) -----------------------------------------

def test_a_fixture_can_say_what_became_of_it():
    for outcome in EVENT_OUTCOMES:
        assert validate_record("events", _event(outcome=outcome)) == [], outcome


def test_took_place_is_distinguishable_from_not_attended():
    """The three states that read identically before: happened-and-logged-
    nothing, did-not-attend, and never-took-place. The first is the common
    one, because a race day is when logging is least likely."""
    assert EVENT_OUTCOMES == {"took_place", "did_not_attend"}
    # And the third is `status: cancelled`, which was always expressible - the
    # axis that had no home is what happened when a date ARRIVED.
    assert validate_record("events", _event(status="cancelled")) == []


def test_an_outcome_is_a_second_axis_and_not_more_statuses():
    """The split #235 made for goals: `status` is what the fixture IS,
    `outcome` is what became of it. A cancelled fixture did not take place, so
    saying it took place is the two axes contradicting each other."""
    problems = validate_record(
        "events", _event(status="cancelled", outcome="took_place"))

    assert any("cancelled" in p for p in problems)


def test_a_future_fixture_has_no_outcome():
    """Asserting what became of something that has not happened."""
    problems = validate_record(
        "events", _event(event_date="2030-09-01", outcome="took_place"))

    assert any("later than the day" in p for p in problems)


def test_an_unanswered_outcome_is_not_a_miss():
    """ABSENT MEANS NOBODY HAS SAID, which is the ordinary state of a fixture.
    A consumer rendering it as a miss accuses an athlete of skipping a race
    the record knows nothing about."""
    assert validate_record("events", _event()) == []

    rows = Vitai(DEMO).events("2030-06-30")
    unanswered = [r for r in rows if r.get("outcome") is None]

    assert unanswered, "the demo must hold a fixture nobody has reported on"


def test_the_outcome_reaches_the_surface_a_consumer_reads():
    """Written and never read is half a field (#204)."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "events", "--root", str(DEMO),
         "--on", "2030-06-30"], capture_output=True, text=True, check=True)

    assert "took place" in out.stdout


def test_the_borrowed_terms_are_named_rather_than_implied():
    """Our slugs are spelled for a reader of this record; `fhir` records the
    term they map to. A mapping stated in a field can be checked, one implied
    by a slug cannot - the same reasoning `semantics/statistics.toml` uses."""
    assert set(EVENT_OUTCOME_FHIR) == EVENT_OUTCOMES
    assert EVENT_OUTCOME_FHIR["took_place"] == "fulfilled"
    assert EVENT_OUTCOME_FHIR["did_not_attend"] == "noshow"


def test_the_demo_records_a_race_that_happened_and_logged_nothing():
    """The common case, and the one the fixture could not previously show."""
    lines = [json.loads(ln) for ln
             in (DEMO / "data" / "events.jsonl").read_text(
                 encoding="utf-8").splitlines() if ln.strip()]
    ran = [e for e in lines if e.get("outcome") == "took_place"]

    assert ran
    sessions = [s for s in Vitai(DEMO).dataset("sessions")
                if s.get("date") == ran[0]["event_date"]]
    assert not sessions, (
        "the point of the row is a race with no session beside it")


def test_the_date_check_survives_the_other_iso_spellings():
    """`date.fromisoformat` accepts basic form and week dates, so comparing
    the two as TEXT let a future outcome through (`'-' < '0'`) and refused a
    past one written the other way."""
    basic_line = _event(date="20300408", event_date="2030-09-15",
                        outcome="took_place")
    assert any("later than the day" in p
               for p in validate_record("events", basic_line))

    past_in_basic = _event(date="2030-05-18", event_date="20300401",
                           outcome="took_place")
    assert validate_record("events", past_in_basic) == []


def test_a_fixture_recorded_on_the_day_it_happened_is_accepted():
    """Same-day recording is the ordinary case, so the comparison is strict."""
    assert validate_record(
        "events", _event(date="2030-06-20", event_date="2030-06-20",
                         outcome="took_place")) == []


def test_an_open_gating_episode_with_no_side_draws_an_advisory(tmp_path):
    """The advisory that was CLAIMED in two comments while nothing did it.

    Optional stays optional - requiring a side would refuse every episode
    already written - but an open episode on a paired site with no side is
    exactly #145's case: a gate on "the knee" bans the limb that is fine.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "knee", "kind": "injury",
                         "title": "an episode", "body_site": "knee",
                         "severity": "mild", "status": "active",
                         "restricts": "impact", "source": "athlete"})

    advisories = " ".join(v.validate()["advisories"])

    assert "both sides" in advisories and "knee" in advisories
    assert not v.validate()["problems"]


def test_a_resolved_episode_draws_no_advisory(tmp_path):
    """It restricts nothing, so naming its side changes no answer - and
    repeating the note for a decision already taken is noise."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "knee", "kind": "injury",
                         "title": "an episode", "body_site": "knee",
                         "severity": "none", "status": "resolved",
                         "resolved_date": "2030-05-20",
                         "restricts": "impact", "source": "athlete"})

    assert not [a for a in v.validate()["advisories"] if "both sides" in a]


def test_an_episode_that_gates_nothing_draws_no_advisory(tmp_path):
    """An open episode restricting nothing gates nothing, so a side changes
    no answer and the advisory would be noise."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "knee",
                         "kind": "symptom", "title": "some stiffness",
                         "body_site": "knee", "severity": "mild",
                         "status": "monitoring", "source": "athlete"})

    assert not [a for a in v.validate()["advisories"] if "both sides" in a]


def test_the_refactor_did_not_tighten_the_rule_daily_already_had():
    """The shared validator has to be semantics-preserving for its first
    caller, and my first cut was not.

    The midline check sat INSIDE `if site and pain`, so a daily row naming a
    midline site and a side with no pain score was legal. Hoisting it made
    every such line fail forever, in an append-only record, with no remedy but
    a correction - a silent tightening of a rule on data already written.
    """
    rec = {k: None for k in KEYS["daily"]}
    rec.update({"date": "2030-05-01", "source": "phone",
                "pain_site": "abdomen", "pain_side": "left",
                "_gen": CURRENT_GENERATION["daily"]})

    problems = validate_record("daily", rec)

    assert not [p for p in problems if "midline" in p]
    # And WITH a score it still refuses, which is the behaviour that stays.
    scored = dict(rec, pain=3)
    assert any("midline" in p for p in validate_record("daily", scored))


def test_both_columns_are_text_in_the_read_model():
    """`column_affinity` is the accessor #257 published so consumers stop
    guessing. `pain_side` was already declared TEXT and its own mirror was
    not, so it answered REAL for columns holding "left" and "took_place"."""
    from vitai.db import column_affinity

    for column in ("body_side", "outcome", "pain_side"):
        assert column_affinity(column) == "TEXT", column
