"""How a set was configured, and the numbers that mean nothing off one machine
(#99, increment 3 of #59).

Synthetic data only (public repo), fictional athlete, 2030 dates. The two
motivating cases are represented by their SHAPE - a machine ordinal that
dominated a session, and a bench angle that kept vanishing into prose.
"""

import json

import pytest

from vitai.cli import main
from vitai.modifiers import (CATEGORICAL, MACHINE_SCOPED, PORTABLE, comparable,
                             configuration, is_machine_scoped,
                             resolve_modifier, values)
from vitai.schema import KEYS, CURRENT_GENERATION, key_generation, validate_record


def a_set(**kw):
    row = {"date": "2030-05-01", "session_start": "2030-05-01T07:10:00+02:00",
           "exercise": "bench-press", "block": 1, "round": None, "set_index": 1,
           "reps_completed": 8, "reps_attempted": 8,
           "load": 60, "load_type": "external", "load_unit": "kg",
           "machine": None, "set_type": "working", "failure": None,
           "rir": None, "rpe": None, "rest_s": 90, "tempo": None,
           "duration_s": None, "side": None, "note": None,
           "source": "stated-in-chat", "recorded_at": None,
           "origin": "athlete", "path": None, "origin_evidence": None,
           "capture": "narrative", "read_by": "athlete",
           "equipment": None, "angle_class": None, "angle_deg": None,
           "resistance_level": None, "seat_pos": None, "pad_pos": None,
           "lever_pos": None, "device": None,
           "_gen": CURRENT_GENERATION["sets"]}
    row.update(kw)
    return row


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, rows):
    (root / "data" / "sets.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# The crosstrainer case: the variable that dominated the session.
CROSSTRAINER = [
    a_set(date="2030-05-01", exercise="crosstrainer", set_index=1,
          reps_completed=None, reps_attempted=None, duration_s=1800,
          load=None, load_type=None, load_unit=None,
          equipment="machine", machine="crosstrainer-b", resistance_level=13),
    a_set(date="2030-05-08", session_start="2030-05-08T07:10:00+02:00",
          exercise="crosstrainer", set_index=1,
          reps_completed=None, reps_attempted=None, duration_s=1800,
          load=None, load_type=None, load_unit=None,
          equipment="machine", machine="crosstrainer-b", resistance_level=15),
]


# ---- the axes an exercise name must not absorb -----------------------------------

def test_a_bench_press_takes_its_incline_as_a_modifier():
    """The #59 post-coordination test, this issue's half. `bench-press` plus
    `dumbbell` plus `incline` is fully representable and no fused token
    exists anywhere."""
    row = a_set(equipment="dumbbell", angle_class="incline", angle_deg=30)
    assert validate_record("sets", row) == []
    assert configuration(row) == {"equipment": "dumbbell",
                                  "angle_class": "incline", "angle_deg": 30}


def test_the_equipment_axis_is_the_one_settings_toml_retired_treadmill_into():
    """`settings.toml` retired `treadmill` with the note that it is "a piece
    of equipment, not a setting", and the axis it pointed at was never
    built."""
    assert "equipment" in CATEGORICAL
    assert resolve_modifier("equipment", "smith machine") == "smith"
    assert resolve_modifier("equipment", "hex bar") == "trap_bar"


def test_an_unfamiliar_implement_is_a_finding_not_an_error():
    assert resolve_modifier("equipment", "some new contraption") == "unknown"
    found = validate_record("sets", a_set(equipment="some new contraption"))
    assert len(found) == 1 and "unknown equipment" in found[0]


def test_the_angle_class_is_a_class_and_the_degrees_are_a_number():
    """"Incline" on one bench is not "incline" on another, and a class cannot
    be subtracted - so the two are different fields rather than one."""
    assert set(values("angle_class")) == {"flat", "incline", "decline"}
    assert "angle_deg" in PORTABLE
    assert "angle_class" in CATEGORICAL


def test_a_bench_angle_past_vertical_is_rejected():
    assert any("behind the athlete" in p for p in validate_record(
        "sets", a_set(angle_deg=120)))


# ---- machine-scoped values are not quantities -------------------------------------

def test_a_machine_ordinal_needs_the_machine_it_came_from():
    """THE rule (#60). Level 15 here is not level 15 there, and a number
    that cannot say which machine it came from is a confident wrong answer
    waiting for a consumer."""
    bare = a_set(exercise="crosstrainer", resistance_level=15, machine=None,
                 reps_completed=None, reps_attempted=None, duration_s=1800,
                 load=None, load_type=None, load_unit=None)
    assert any("number about" in p for p in validate_record("sets", bare))
    named = {**bare, "machine": "crosstrainer-b"}
    assert validate_record("sets", named) == []


@pytest.mark.parametrize("field", MACHINE_SCOPED)
def test_every_machine_scoped_field_carries_the_same_requirement(field):
    row = a_set(**{field: 7}, machine=None)
    assert any(field in p and "machine" in p
               for p in validate_record("sets", row)), field
    assert is_machine_scoped(field)


def test_two_levels_on_one_machine_may_be_compared_and_across_machines_may_not():
    """"Level 15 is 15/13 of level 13" is not a valid inference even where
    the arithmetic looks proportional - the scale is not established to be
    linear, or to have a zero."""
    a, b = CROSSTRAINER
    assert comparable(a, b, "resistance_level") is True
    other = {**b, "machine": "crosstrainer-a"}
    assert comparable(a, other, "resistance_level") is False


def test_two_unnamed_machines_are_not_evidence_of_one_machine():
    a = a_set(resistance_level=13, machine=None)
    b = a_set(resistance_level=15, machine=None)
    assert comparable(a, b, "resistance_level") is False


def test_a_portable_quantity_is_always_comparable():
    """The whole difference: degrees mean the same thing on every bench."""
    a = a_set(angle_deg=30, machine=None)
    b = a_set(angle_deg=45, machine="bench-c")
    assert comparable(a, b, "angle_deg") is True


def test_the_crosstrainer_progression_is_representable_end_to_end():
    """Level 15 on this machine, level 13 on the same machine a session
    earlier, and the pair queryable as a within-machine progression."""
    earlier, later = CROSSTRAINER
    assert all(validate_record("sets", r) == [] for r in CROSSTRAINER)
    assert comparable(earlier, later, "resistance_level")
    assert configuration(later)["resistance_level"] == 15
    assert configuration(earlier)["resistance_level"] == 13


# ---- absent is absent ---------------------------------------------------------------

def test_no_modifier_is_ever_defaulted():
    """An unstated equipment is unknown, not `barbell`; an unstated angle is
    unknown, not `flat`. A default puts a claim nobody made into a field a
    query will later trust."""
    bare = a_set()
    assert validate_record("sets", bare) == []
    assert configuration(bare) == {}


def test_an_unstated_axis_is_absent_rather_than_unknown():
    """Nobody said, versus said something nobody catalogued - two different
    facts, and a caller must be able to tell them apart."""
    assert "equipment" not in configuration(a_set())
    assert configuration(a_set(equipment="a new contraption")) == {
        "equipment": "unknown"}


# ---- the record's shape ---------------------------------------------------------------

def test_a_line_written_before_modifiers_existed_still_validates():
    """G25, the whole reason these are nullable additive columns."""
    previous = key_generation("sets", "equipment") - 1
    row = {k: None for k in KEYS["sets"]
           if key_generation("sets", k) <= previous}
    row.update({"date": "2030-05-01", "exercise": "push-up", "set_index": 1,
                "reps_completed": 10, "reps_attempted": 10, "_gen": previous})
    assert validate_record("sets", row) == []


def test_the_modifier_columns_share_one_generation_of_their_own():
    landed = key_generation("sets", "equipment")
    for k in ("angle_class", "angle_deg", *MACHINE_SCOPED):
        assert key_generation("sets", k) == landed, k
    assert key_generation("sets", "set_index") < landed


def test_there_is_no_second_laterality_axis():
    """#59's spec listed laterality BOTH as a modifier axis and as a core
    `side` field. Two must not land, and the core one wins because unilateral
    work is not a niche modifier."""
    assert "laterality" not in KEYS["sets"]
    assert "laterality" not in CATEGORICAL
    assert "side" in KEYS["sets"]


def test_there_is_no_variant_free_text_field():
    """"It is where every one of these axes goes to die"."""
    assert "variant" not in KEYS["sets"]


def test_the_stack_number_did_not_ship_twice():
    """#99's spec listed `stack_kg` among the parametric modifiers, and #97
    already owns that quantity as `load` plus `load_type: machine_stack`.
    Implementing it twice would let the same kilogram-that-is-not-a-kilogram
    live in two places with two rules."""
    assert "stack_kg" not in KEYS["sets"]
    assert "stack_kg" not in MACHINE_SCOPED


def test_the_modifiers_reach_the_read_model(tmp_path):
    import sqlite3
    root = repo(tmp_path)
    write(root, CROSSTRAINER)
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        rows = con.execute("SELECT resistance_level, machine, equipment "
                           "FROM sets ORDER BY date").fetchall()
    finally:
        con.close()
    assert rows == [(13.0, "crosstrainer-b", "machine"),
                    (15.0, "crosstrainer-b", "machine")]


# ---- the surface ------------------------------------------------------------------------

def test_a_machine_ordinal_never_prints_without_its_machine(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, CROSSTRAINER)
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if "resistance level" in ln]
    assert len(lines) == 2, "the loop below would have passed vacuously"
    for line in lines:
        assert "crosstrainer-b" in line, line
    # And the branch for a row already on disk with no machine, which
    # `validate` reports but does not stop loading. It must still not read as
    # a bare comparable ordinal.
    from vitai.cli import _config
    assert "an unnamed machine" in _config(
        a_set(resistance_level=15, machine=None))


def test_the_configuration_reads_the_way_it_would_be_said(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [a_set(equipment="dumbbell", angle_class="incline",
                       angle_deg=30, failure="muscular")])
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    out = capsys.readouterr().out
    assert "dumbbell" in out and "incline" in out and "30 deg" in out


def test_a_set_with_no_modifiers_says_nothing_extra(tmp_path, capsys):
    """Asserting `"unknown" not in out` proved nothing: a `_config` that
    defaulted absent equipment to `barbell`, or printed `equipment None`,
    passed it unchanged. This pins the segment's absence instead.
    """
    from vitai.cli import _config
    assert _config(a_set()) == ""
    root = repo(tmp_path)
    write(root, [a_set()])
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    line = capsys.readouterr().out.strip()
    assert line.endswith("[block 1, set 1]")
    assert "equipment" not in line and "None" not in line


# ---- what the review of this feature found ------------------------------------------

def test_the_modifier_generation_is_later_than_everything_that_predates_it():
    """The G25 test could not catch the regression it exists for.

    Deriving `previous` from `key_generation("sets", "equipment")` means
    deleting the `CURRENT_GENERATION["sets"] += 1` still passes: `previous`
    just becomes one lower. Every test would stay green while modifiers
    landed on a generation already in the wild, and every `_gen: 2` row
    suddenly owed seven keys - the exact time bomb.

    So this asserts the registration against the DATASET's state instead.
    """
    landed = key_generation("sets", "equipment")
    # NOT `== CURRENT_GENERATION`. That was a moving target - the same trap
    # this test was written to close, one level up: #105's `device` landed
    # afterwards and made "modifiers are the newest" false without anything
    # being wrong. What has to hold is that modifiers came AFTER everything
    # that predates them, which is what a reused generation would break.
    for older in ("set_index", "exercise", "recorded_at", "load_type"):
        assert key_generation("sets", older) < landed, older
    assert landed <= CURRENT_GENERATION["sets"]
    for sibling in ("angle_class", "angle_deg", *MACHINE_SCOPED):
        assert key_generation("sets", sibling) == landed, sibling


def test_one_machine_typed_two_ways_is_one_machine():
    """The live progression is 13 to 15 on one crosstrainer. Letting a
    capital letter or a trailing space split the pair drops exactly the
    comparison this exists to make visible."""
    a = a_set(resistance_level=13, machine="Crosstrainer-B ")
    b = a_set(resistance_level=15, machine="crosstrainer-b")
    assert comparable(a, b, "resistance_level") is True


def test_an_incline_and_a_decline_of_the_same_degrees_are_not_comparable():
    """`angle_deg` is a magnitude and `angle_class` carries the sign, so 30
    on an incline and 30 on a decline are sixty degrees apart while storing
    the same number."""
    up = a_set(angle_class="incline", angle_deg=30)
    down = a_set(angle_class="decline", angle_deg=30)
    assert comparable(up, down, "angle_deg") is False
    assert comparable(up, a_set(angle_class="incline", angle_deg=45),
                      "angle_deg") is True


def test_a_field_this_module_does_not_own_raises():
    """A misspelling and a legitimate refusal must not look alike. Returning
    False told a caller the comparison was considered and declined."""
    with pytest.raises(ValueError, match="not a modifier"):
        comparable(a_set(), a_set(), "resistence_level")
    with pytest.raises(ValueError, match="not a modifier"):
        comparable(a_set(), a_set(), "duration_s")


def test_matching_machines_do_not_make_absent_values_comparable():
    """A consumer that subtracts after a True would find a None."""
    a = a_set(resistance_level=None, machine="crosstrainer-b")
    b = a_set(resistance_level=None, machine="crosstrainer-b")
    assert comparable(a, b, "resistance_level") is False


def test_unknown_is_not_a_storable_value():
    """The registry carried an `unknown` entry that nothing could reach -
    `resolve` returns None for an unfamiliar value and the fallback supplies
    the placeholder. Its only effect was to make a row storing the literal
    indistinguishable from one nobody catalogued, with advice that could not
    be satisfied.
    """
    assert "unknown" not in values("equipment")
    assert "unknown" not in values("angle_class")
    found = validate_record("sets", a_set(equipment="unknown"))
    assert len(found) == 1 and "null if nobody said" in found[0]


def test_a_bad_modifier_does_not_take_down_the_whole_listing(tmp_path):
    """`validate` reports a modifier of the wrong type but does not stop the
    file loading, so `:g` on a string raised. A bool was worse than a crash:
    `True` formatted as an ordinal printed "level 1"."""
    from vitai.cli import _config
    assert "not a number" in _config(a_set(resistance_level="15",
                                           machine="crosstrainer-b"))
    assert "level 1 on" not in _config(a_set(resistance_level=True,
                                             machine="crosstrainer-b"))
