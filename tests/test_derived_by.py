"""Who computed a value the engine did not (#280).

`derived_external` says the value was not computed by this engine and stops
there, which was enough when there was one consumer. #158 settled that several
clients read one record on the same terms, and any of them may derive: two
clients computing a pace from `duration_s` and `distance_km` agree when both
are right and differ when one has a bug, and nothing in the record could tell
them apart - nor a figure from version 0.1 from the same field after 0.2 fixed
the bug.

The engine already takes this seriously where it controls it: `inferences`
carries `model`, because which model produced an inference is part of what the
inference IS.

ONE CORRECTION TO THE ISSUE, and it changed the shape. It asks for a field
"naming the software rather than the person". The single `derived_external`
row in every fixture this repo ships is an athlete taking a mean of two
weigh-ins ON PAPER - so a field that could only name software would have had
nothing to put there, and its absence would then have meant both "a person did
it" and "software did it and did not say".
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import (CURRENT_GENERATION, DERIVED_BY_HAND, KEYS,
                          key_generation, validate_record)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
LINEAGE_DATASETS = ("weight", "daily", "sessions", "measurements", "sets",
                    "meals")


def _derived(**kw) -> dict:
    rec = {k: None for k in KEYS["weight"]}
    rec.update({"date": "2030-05-01", "kg": 80.0, "source": "notebook",
                "capture": "derived_external",
                "derived_from": ["weight:2030-04-30:scale"],
                "derived_op": "a mean of two",
                "_gen": CURRENT_GENERATION["weight"]})
    rec.update(kw)
    return rec


def test_a_derived_external_value_must_say_what_computed_it():
    """Without it a consumer cannot tell one client's figure from another's,
    or from a bug fixed two versions ago.

    Asserting on the REQUIREMENT's own words rather than on the field name:
    with the requirement removed, the slug check fires on `None` instead and
    its message also contains "derived_by", so the obvious assertion passed
    with the rule deleted. Found by mutating the rule this test exists for.
    """
    problems = validate_record("weight", _derived())

    assert any("has to say what" in p for p in problems), problems


def test_a_person_with_a_pen_is_a_legal_answer():
    """The one such row in every shipped fixture. A field naming only software
    would have had nothing to put here."""
    assert validate_record(
        "weight", _derived(derived_by=DERIVED_BY_HAND)) == []


def test_a_person_has_no_build():
    """Inventing a version for a notebook would be the field asserting a fact
    about a piece of paper."""
    problems = validate_record(
        "weight", _derived(derived_by=DERIVED_BY_HAND, derived_build="1.2"))

    assert any("no build" in p for p in problems)


def test_named_software_must_say_which_build():
    """THE HALF THAT MAKES A DERIVATION AUDITABLE. The same field computed
    before and after a fix are different facts, and a name alone cannot tell
    them apart - which is the whole complaint."""
    problems = validate_record("weight", _derived(derived_by="a-client"))

    assert any("derived_build" in p for p in problems)
    assert validate_record(
        "weight", _derived(derived_by="a-client", derived_build="0.4.1")) == []


def test_the_two_facts_are_two_fields_and_not_one_parsed_slug():
    """`client-0.1.0-a3f2` crams orthogonal facts into an identifier a
    consumer then has to parse, which is the pre-coordination this schema
    refuses everywhere else."""
    for dataset in LINEAGE_DATASETS:
        assert "derived_by" in KEYS[dataset], dataset
        assert "derived_build" in KEYS[dataset], dataset


def test_no_install_identifier_exists():
    """A DECISION, NOT AN OMISSION. The issue raises a per-install id and
    answers itself: it is useful to the record and is also a tracking key. It
    answers no question a coach is asked, `device` already names the machine
    that wrote a line down, and admitting one needs a rule about where it may
    travel - which is #205's work rather than a field added in passing.

    Pinned so that adding one later is a deliberate act.
    """
    for dataset in LINEAGE_DATASETS:
        assert not [k for k in KEYS[dataset]
                    if "install" in k or "instance_id" in k], dataset


def test_an_older_line_never_owed_either_field():
    """G25. The fields arrive at a generation; a row written before it is not
    missing them."""
    old = _derived(_gen=key_generation("weight", "derived_by") - 1)
    old.pop("derived_by", None)

    assert validate_record("weight", old) == []


def test_the_requirement_survives_the_capture_alias():
    """`athlete-derived` resolves to `derived_external` through the registry,
    and a raw string comparison would have let it past the rule."""
    problems = validate_record(
        "weight", _derived(capture="athlete-derived"))

    assert any("derived_by" in p for p in problems)


def test_an_engine_derived_value_needs_neither():
    """`derived` means THIS engine computed it, and the engine knows what it
    computed. Requiring a name there would be the record telling itself
    something it already knows."""
    assert validate_record("weight", _derived(
        capture="derived", derived_by=None, derived_build=None)) == []


def test_the_demo_exercises_both_kinds_of_deriver():
    """#204's corollary: a fixture holding one value of a vocabulary proves
    nothing about the distinction the field exists to draw - and this field's
    whole point is that a person and a program are different derivers."""
    rows = []
    for dataset in LINEAGE_DATASETS:
        rows += [r for r in Vitai(DEMO).dataset(dataset)
                 if r.get("derived_by")]

    kinds = {r["derived_by"] for r in rows}

    assert DERIVED_BY_HAND in kinds, "the paper case"
    assert kinds - {DERIVED_BY_HAND}, "and a named piece of software"
    for row in rows:
        assert (row["derived_build"] is None) == (
            row["derived_by"] == DERIVED_BY_HAND), row


def test_the_shipped_record_still_validates():
    """The rule is required, so a fixture carrying a derived row that predates
    it would fail the build rather than the test."""
    assert not Vitai(DEMO).validate()["problems"]


def test_a_client_can_read_who_derived_a_value():
    """The consumer the field exists for. It reaches a client through the
    supported read path rather than through a private attribute."""
    derived = [r for r in Vitai(DEMO).dataset("daily") if r.get("derived_by")]

    assert derived
    row = derived[0]
    assert row["derived_by"] and row["derived_build"]
    assert json.dumps(row)
