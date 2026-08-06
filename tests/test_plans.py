"""What a day was meant to be, as its own row (#221).

The state work can explain why training did not happen and there was nothing to
attach the explanation to. An absence is not an object: a gap in a session list
is a shape in the negative space, and no state can point at it.

A PLAN IS NOT A SESSION, and that is the whole reason for a dataset rather than
a flag. `sessions` means this happened, and every count, weekly total and load
figure depends on it - a skipped row there sums to zero and counts as one,
corrupting all of them silently.

Which is also why `sessions.planned` was null on 1692 of 1692 rows in a live
record and 0 of 2698 persona rows. That reads as neglect and is not: the field
lives on a session row, a session that did not happen has none, and the only
case it exists to serve is the one case it structurally cannot represent.
"""

from __future__ import annotations

from pathlib import Path

from vitai.api import Vitai, init
from vitai.schema import (CURRENT_GENERATION, KEYS, PLAN_OUTCOMES,
                          PLAN_REASONS, PLAN_TIERS, IDENTITY_KEY,
                          key_retirement, validate_record)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _plan(**kw) -> dict:
    rec = {k: None for k in KEYS["plans"]}
    rec.update({"date": "2030-05-01", "slug": "tue-run",
                "for_date": "2030-05-02", "activity": "run",
                "tier": "committed", "outcome": "unresolved",
                "_gen": CURRENT_GENERATION["plans"]})
    rec.update(kw)
    return rec


def test_a_plan_is_its_own_row_and_not_a_session():
    """Skipped rows in `sessions` would corrupt every count silently."""
    assert "plans" in KEYS
    assert "plans" not in ("sessions",)
    assert IDENTITY_KEY["plans"] == "slug"


def test_identity_survives_the_outcome_moving():
    """A plan is RESOLVED LATER, which in an append-only record is a second
    row about the same plan - so identity has to be stable while `outcome`
    changes, and a composite of attributes cannot be, because the attribute
    that moves is the one being recorded."""
    made = _plan()
    resolved = _plan(date="2030-05-03", outcome="completed",
                     session_ref="2030-05-02")

    assert validate_record("plans", made) == []
    assert validate_record("plans", resolved) == []
    assert made["slug"] == resolved["slug"]


def test_two_plans_for_one_day_are_distinguishable():
    """Two 5 km runs planned the same day for the same day, one morning and
    one evening, are identical on every other field."""
    morning = _plan(slug="am-run", for_phase="morning")
    evening = _plan(slug="pm-run", for_phase="evening")

    assert validate_record("plans", morning) == []
    assert validate_record("plans", evening) == []
    assert morning["slug"] != evening["slug"]


def test_a_programme_plan_must_name_what_it_serves():
    """The tier is decided by WHAT A PLAN SERVES rather than by how committed
    it felt - feeling is not recoverable later and a link to a goal is - so a
    programme plan naming nothing has thrown away the evidence for its tier."""
    problems = validate_record("plans", _plan(tier="programme"))

    assert any("serves" in p for p in problems)
    assert validate_record(
        "plans", _plan(tier="programme", serves="running")) == []


def test_did_not_activate_needs_a_condition_that_could_have_held():
    """"I would run if it were not raining; it rained" is not skipped - the
    plan never became live. Without a condition the value is `skipped` wearing
    a kinder word, and the point of it is that a cautious athlete who writes a
    condition down is not punished for the forecast."""
    problems = validate_record("plans", _plan(outcome="did_not_activate"))

    assert any("requires" in p for p in problems)
    assert validate_record("plans", _plan(
        outcome="did_not_activate", requires="dry-forecast")) == []


def test_an_unanswered_plan_carries_no_reason():
    """SILENCE IS NOT A LAPSE. An athlete who has not answered has said
    nothing, and a record that explains a non-event has invented it."""
    problems = validate_record(
        "plans", _plan(reason="motivation_automatic"))

    assert any("has none yet" in p for p in problems)


def test_an_ABSENT_outcome_is_unanswered_too():
    """The rule covers TWO shapes and only one of them was pinned.

    `outcome: unresolved` and `outcome: null` both mean nobody has answered,
    and the code refuses a reason beside either. Only the first had a test, so
    mutating the check from `in (None, "unresolved")` to `in ("unresolved",)`
    left the whole suite green while a plan carrying a null outcome and an
    explanation for it became legal.

    The engine writes null for a key it does not know rather than omitting it,
    so the null shape is the one a real row is likelier to carry.
    """
    problems = validate_record(
        "plans", _plan(outcome=None, reason="motivation_automatic"))

    assert any("has none yet" in p for p in problems)


def test_the_reason_axis_can_tell_a_shut_gym_from_a_flat_mood():
    """COM-B, adopted because `gated | chosen` collapsed three axes into two
    and `chosen` swallowed both motivation subtypes plus half of capability -
    which have opposite coaching consequences."""
    for reason in ("opportunity_physical", "motivation_automatic",
                   "motivation_reflective", "capability_physical"):
        assert validate_record(
            "plans", _plan(outcome="skipped", reason=reason)) == [], reason

    assert len(PLAN_REASONS) == 9
    assert "declined" in PLAN_REASONS, (
        "G82: not telling you is a permanent and legitimate answer, and an "
        "axis without it forces a reason out of someone who declined to give "
        "one")


def test_a_deliberate_rest_is_not_the_same_fact_as_could_not_face_it():
    """The model already holds that deliberate omission can be the
    achievement rather than the failure. The two-value axis called both
    `chosen`."""
    assert "motivation_reflective" in PLAN_REASONS
    assert "motivation_automatic" in PLAN_REASONS


def test_tier_is_not_authorship():
    """`set_by` carries authorship on the same row, with the vocabulary
    `goals`, `events` and `thresholds` already use. FHIR's `CarePlan.intent`
    was proposed for this axis and declined for exactly this reason: it is an
    authorisation hierarchy, which is what `set_by` already says."""
    assert PLAN_TIERS == {"programme", "committed", "provisional"}
    assert "set_by" in KEYS["plans"]

    coach_set = _plan(tier="programme", serves="running", set_by="coach")
    self_set = _plan(tier="programme", serves="running", set_by="athlete")

    assert validate_record("plans", coach_set) == []
    assert validate_record("plans", self_set) == []


def test_sessions_planned_is_retired_and_still_legal():
    """G25: an old line keeps validating. The field stops being EXPECTED, not
    legal - every value it ever held describes a plan that was followed."""
    assert key_retirement("sessions", "planned") is not None

    old = {k: None for k in KEYS["sessions"]}
    old.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "planned": "running", "_gen": 2})

    assert validate_record("sessions", old) == []


def test_the_demo_exercises_every_outcome_that_matters():
    """#204's corollary: a fixture holding one value of a vocabulary proves
    nothing about the distinction the field exists to draw - and this
    vocabulary's whole purpose is that skipped, unactivated and unanswered are
    three different facts."""
    outcomes = {p["outcome"] for p in Vitai(DEMO).plans()}

    assert {"completed", "skipped", "did_not_activate", "unresolved"} <= outcomes
    assert outcomes <= PLAN_OUTCOMES


def test_the_engine_never_resolves_a_plan_itself(tmp_path):
    """`unresolved` is the default and the engine must never fill it in. A
    plan whose day has passed is OVERDUE - a question outstanding, which is a
    fact about the record - and never missed, which would be a fact about the
    athlete."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("plans", {"date": "2030-05-01", "slug": "a-run",
                       "for_date": "2030-05-02", "activity": "run",
                       "tier": "committed", "outcome": "unresolved"})

    row, = v.plans("2030-06-01")

    assert row["outcome"] == "unresolved"
    assert row["overdue"] is True
    assert row["reason"] is None


def test_a_plan_still_ahead_is_not_overdue(tmp_path):
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("plans", {"date": "2030-05-01", "slug": "a-run",
                       "for_date": "2030-05-20", "activity": "run",
                       "tier": "committed", "outcome": "unresolved"})

    row, = v.plans("2030-05-02")

    assert row["overdue"] is False


def test_a_resolved_plan_is_never_overdue(tmp_path):
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("plans", {"date": "2030-05-01", "slug": "a-run",
                       "for_date": "2030-05-02", "activity": "run",
                       "tier": "committed", "outcome": "skipped",
                       "reason": "opportunity_physical"})

    row, = v.plans("2030-06-01")

    assert row["overdue"] is False


def test_the_session_is_reachable_from_the_plan_that_named_it():
    """The plan cites the session, which is where FHIR arrived in R5 when it
    replaced `activity.detail` with `plannedActivityReference` and
    `performedActivity` - a plan and the thing that happened are separate
    objects."""
    v = Vitai(DEMO)
    fulfilled = [p for p in v.plans() if p["session_ref"]]

    assert fulfilled
    for plan in fulfilled:
        matching = [s for s in v.dataset("sessions")
                    if s.get("date") == plan["session_ref"]]
        assert matching, plan["session_ref"]
        assert v.plan_for(matching[0])["slug"] == plan["slug"]


def test_plans_are_ordered_by_the_day_they_are_for():
    """Not by the day they were made, which is the axis a reader is asking
    about - and the two are deliberately separate fields, because a plan made
    a week ahead and one made that morning are different commitments."""
    rows = Vitai(DEMO).plans()

    assert [r["for_date"] for r in rows] == sorted(r["for_date"] for r in rows)
