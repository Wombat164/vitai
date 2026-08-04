"""What a subjective number is out of (#246).

`rpe`, `mood` and `pain` validated as bare numerics and nothing else. A bare
number with no declared scale is not interpretable, and for RPE it is
ambiguous between two standard scales both in common use: a stored `rpe: 7` is
"quite light" on Borg's 6-20 and "very hard" on CR10, and the difference is
the whole signal.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.schema import CURRENT_GENERATION, KEYS, scales, validate_record


def a_session(**kw):
    r = {k: None for k in KEYS["sessions"]}
    r.update({"date": "2030-06-01", "type": "run", "source": "watch",
              "_gen": CURRENT_GENERATION["sessions"]})
    r.update(kw)
    return r


def a_day(**kw):
    r = {k: None for k in KEYS["daily"]}
    r.update({"date": "2030-06-01", "source": "watch",
              "_gen": CURRENT_GENERATION["daily"]})
    r.update(kw)
    return r


# --- absent means unstated ---------------------------------------------------

def test_a_bare_number_is_still_legal():
    """Every row written before this existed carries one, and an athlete who
    never says which scale he means is not making an error."""
    assert validate_record("sessions", a_session(rpe=7)) == []
    assert validate_record("daily", a_day(mood=8, pain=2, pain_site="hip", pain_side="right")) == []


def test_the_same_number_is_legal_on_both_scales():
    """Which is the defect: nothing in the record distinguished them."""
    for scale in ("borg-cr10", "borg-rpe-6-20"):
        assert validate_record("sessions",
                               a_session(rpe=7, rpe_scale=scale)) == []


# --- declaring one means something -------------------------------------------

def test_a_value_its_own_scale_cannot_hold_is_refused():
    """The point of declaring. A 3 on a scale that starts at 6 means one of
    the two is wrong and the engine cannot tell which."""
    problems = validate_record("sessions",
                               a_session(rpe=3, rpe_scale="borg-rpe-6-20"))
    assert problems and "outside borg-rpe-6-20" in problems[0]
    assert validate_record("sessions",
                           a_session(rpe=3, rpe_scale="borg-cr10")) == []


def test_an_unregistered_scale_is_refused():
    """A scale that bounds nothing is worse than none: it reads as though the
    question was settled."""
    problems = validate_record("sessions",
                               a_session(rpe=7, rpe_scale="vibes"))
    assert problems and "not a scale this engine knows" in problems[0]


def test_a_scale_with_nothing_to_scale_is_refused():
    problems = validate_record("sessions", a_session(rpe_scale="borg-cr10"))
    assert problems and "there is no 'rpe'" in problems[0]


def test_pain_and_mood_are_scaled_separately():
    """One row carries both, so one column could not serve them."""
    assert validate_record("daily", a_day(mood=8, mood_scale="nrs-0-10", pain=2,
                                          pain_scale="nrs-0-10", pain_site="hip",
                                          pain_side="right")) == []
    bad = validate_record("daily", a_day(mood=44, mood_scale="nrs-0-10", pain=2,
                                         pain_scale="nrs-0-10", pain_site="hip",
                                         pain_side="right"))
    assert bad and "'mood' is 44" in bad[0]


# --- the registry is prior art, not invention --------------------------------

def test_every_scale_carries_a_citation():
    """A record that needs a scale nobody published is describing something
    this registry should not be guessing at."""
    for slug, spec in scales().items():
        assert spec.get("citation"), f"{slug} has no citation"
        assert spec["min"] < spec["max"]


def test_both_borg_scales_are_present_and_differ():
    known = scales()
    assert known["borg-cr10"]["min"] == 0 and known["borg-cr10"]["max"] == 10
    assert known["borg-rpe-6-20"]["min"] == 6


# --- and the fixtures hold both states ---------------------------------------

def test_the_fixtures_show_a_declared_scale_and_an_undeclared_one():
    """A fixture that only held the declared case would prove nothing about
    the one a consumer actually has to handle."""
    root = Path(__file__).resolve().parents[1]
    demo = [json.loads(x) for x in
            (root / "examples/demo/data/sessions.jsonl").read_text().splitlines()
            if x.strip()]
    assert any(r.get("rpe_scale") for r in demo)
    personas = [json.loads(x) for x in
                (root / "tests/fixtures/personas/marcus/data/sessions.jsonl")
                .read_text().splitlines() if x.strip()]
    assert personas and not any(r.get("rpe_scale") for r in personas)
