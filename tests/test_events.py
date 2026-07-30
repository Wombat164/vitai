"""Events: the dated real-world fixtures a plan is built backwards from (G86).

Synthetic data only (public repo), fictional athlete, 2030 dates.

The distinction under test is that an EVENT is not a MILESTONE. A milestone is
a fraction of a target the engine derives from progress already made; an event
happens whether the athlete is ready or not, is owned by somebody else, and is
the thing periodisation is planned backwards FROM. Two concepts had one word.
"""

from vitai.policy import days_between, deadline_of, events_on
from vitai.schema import EVENT_KINDS, validate_record
from vitai.vocab import resolve_event_kind, resolve_event_priority


def event(slug="spring-10k", date="2030-01-15", event_date="2030-06-01",
          kind="competition", **kw):
    rec = {"date": date, "slug": slug, "title": f"{slug} fixture", "kind": kind,
           "event_date": event_date, "priority": None, "immovable": True,
           "place": None, "status": "confirmed", "set_by": "athlete",
           "reason": None, "note": None}
    rec.update(kw)
    return rec


# ---- schema ------------------------------------------------------------------

def test_valid_event_line_passes():
    assert validate_record("events", event()) == []


def test_an_event_needs_the_day_it_falls_on():
    """`date` is when the line was written; `event_date` is the fixture.

    Collapsing them would make a race declared today invisible until the day
    it happened, which defeats the entire purpose of declaring it.
    """
    problems = validate_record("events", event(event_date=None))
    assert any("event_date" in p for p in problems)
    assert validate_record("events", event(date="2030-01-15",
                                           event_date="2030-06-01")) == []


def test_event_vocabularies_are_enforced():
    assert any("kind" in p for p in validate_record("events", event(kind="thing")))
    assert any("priority" in p
               for p in validate_record("events", event(priority="urgent")))
    assert any("status" in p
               for p in validate_record("events", event(status="maybe")))


def test_immovable_is_a_boolean_not_a_word():
    problems = validate_record("events", event(immovable="yes"))
    assert any("immovable" in p for p in problems)


# ---- the registry (G85: not a Python set) -------------------------------------

def test_event_kinds_come_from_the_registry():
    """The axis lives in semantics/events.toml so an athlete whose fixture we
    never imagined can have it added without a code change."""
    assert "competition" in EVENT_KINDS
    assert "clinical" in EVENT_KINDS
    # The athlete's own words reach the vocabulary through aliases.
    assert resolve_event_kind("race") == "competition"
    assert resolve_event_kind("Wedding") == "life"
    assert resolve_event_kind("scan") == "clinical"
    assert resolve_event_kind("parkrun") == "commitment"
    assert resolve_event_kind("nonsense") is None


def test_priority_is_a_separate_axis_from_kind():
    """Friel A/B/C. Post-coordinated: a B-priority race and an A-priority
    medical procedure are both coherent, and pre-coordinating them would
    multiply the vocabulary and hide the second axis."""
    assert resolve_event_priority("a") == "a"
    assert resolve_event_priority("primary") == "a"
    assert resolve_event_priority("trained through") is None
    assert resolve_event_priority("workout") == "c"


# ---- as-of behaviour -----------------------------------------------------------

def test_events_are_effective_dated_like_all_policy():
    events = [event(slug="race", date="2030-03-01", event_date="2030-09-01")]
    assert events_on(events, "2030-02-28") == ()
    assert len(events_on(events, "2030-03-01")) == 1


def test_a_moved_fixture_supersedes_by_slug():
    events = [event(slug="race", date="2030-03-01", event_date="2030-09-01"),
              event(slug="race", date="2030-04-01", event_date="2030-10-01")]
    assert events_on(events, "2030-03-15")[0]["event_date"] == "2030-09-01"
    assert events_on(events, "2030-05-01")[0]["event_date"] == "2030-10-01"


def test_a_cancelled_event_leaves_the_plan_but_stays_on_the_record():
    events = [event(slug="race", date="2030-03-01"),
              event(slug="race", date="2030-04-01", status="cancelled")]
    assert events_on(events, "2030-05-01") == ()
    assert len(events) == 2, "the line is history; nothing is deleted"


def test_events_sort_soonest_first():
    events = [event(slug="late", event_date="2030-09-01"),
              event(slug="soon", event_date="2030-02-01")]
    assert [e["slug"] for e in events_on(events, "2030-01-20")] == ["soon", "late"]


def test_days_between_counts_forwards_and_backwards():
    assert days_between("2030-06-01", "2030-06-11") == 10
    assert days_between("2030-06-11", "2030-06-01") == -10
    assert days_between("2030-06-01", None) is None
    assert days_between("2030-06-01", "not a date") is None


# ---- anchoring a goal to a fixture ---------------------------------------------

def test_anchoring_a_goal_to_an_immovable_event_makes_its_deadline_hard():
    """An organiser's date is not the athlete's to move, so the hardness is
    DERIVED from the fixture rather than re-declared on the goal."""
    index = {"race": event(slug="race", event_date="2030-06-01", immovable=True)}
    when, hardness, anchor = deadline_of(
        {"event": "race", "deadline": None, "deadline_kind": None}, index)
    assert (when, hardness, anchor) == ("2030-06-01", "hard", "race")


def test_a_movable_fixture_does_not_force_hardness():
    index = {"meetup": event(slug="meetup", kind="commitment",
                             event_date="2030-06-01", immovable=False)}
    _, hardness, _ = deadline_of({"event": "meetup", "deadline": None,
                                  "deadline_kind": None}, index)
    assert hardness is None, "unknown, not hard - the engine does not guess"


def test_an_explicit_deadline_kind_wins_over_the_derived_one():
    """The athlete may hold themselves to a soft reading of a fixed date, and
    saying so is exactly what the field is for."""
    index = {"race": event(slug="race", event_date="2030-06-01", immovable=True)}
    _, hardness, _ = deadline_of({"event": "race", "deadline": None,
                                  "deadline_kind": "soft"}, index)
    assert hardness == "soft"


def test_an_unanchored_goal_keeps_its_own_deadline():
    when, hardness, anchor = deadline_of(
        {"event": None, "deadline": "2030-07-01", "deadline_kind": "soft"}, {})
    assert (when, hardness, anchor) == ("2030-07-01", "soft", None)


# ---- surfaces (P9: CLI and API land together) ----------------------------------

def _repo(tmp_path):
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def _write(root, name, rows):
    import json
    (root / "data" / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_events_reach_both_the_api_and_the_cli(tmp_path, capsys):
    from vitai.api import Vitai
    from vitai.cli import main
    root = _repo(tmp_path)
    _write(root, "events", [event(slug="race", date="2030-01-01",
                                  event_date="2030-06-01", title="Spring race")])

    rows = Vitai(root).events("2030-05-22")
    assert [r["slug"] for r in rows] == ["race"]
    assert rows[0]["days_away"] == 10

    main(["events", "--root", str(root), "--on", "2030-05-22"])
    out = capsys.readouterr().out
    assert "race" in out and "in 10 day(s)" in out and "fixed date" in out


def test_an_empty_events_file_says_what_to_do(tmp_path, capsys):
    from vitai.cli import main
    root = _repo(tmp_path)
    main(["events", "--root", str(root), "--on", "2030-05-22"])
    assert "no events" in capsys.readouterr().out


def test_the_rollup_counts_down_to_a_fixture(tmp_path):
    from vitai.api import Vitai
    root = _repo(tmp_path)
    _write(root, "events", [
        event(slug="race", date="2030-01-01", event_date="2030-06-01",
              title="Spring race"),
        # A fixture already past is history, not a plan, and must not appear.
        event(slug="old", date="2030-01-01", event_date="2030-02-01",
              title="Last winter's test", kind="assessment"),
    ])
    from datetime import date as _date
    text = Vitai(root).rollup(today=_date(2030, 5, 22))
    assert "## Coming up" in text
    assert "Spring race" in text and "in 10 days" in text
    assert "Last winter's test" not in text
