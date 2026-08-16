"""What a protocol DECLARES it controls for (#404).

A `protocols` row is a slug, a date and prose. It says WHICH procedure was
followed and never what that procedure controls FOR, so a reading either named
a protocol or did not, and nothing downstream could say which conditions were
left free. The model is binary and real mornings are not: "I voided but I had
coffee" matches no declared slug and is not the same as nothing known.

`docs/proposals/uncertainty/01-schema.md` section 7 already frames a
protocol-anchored measurement as an ANCHOR and says the unprotocolled row
carries the measurand's FULL definitional uncertainty. `controls` is the
missing half of that sentence - which part of it a NAMED protocol removes.

THE RULE THIS FILE EXISTS TO HOLD: no magnitude, anywhere. #404 lists rough
masses for these conditions to argue the problem is real, and #402's rule with
#264's rewording both say a band comes from a measured overlap, a per-reading
`u_obs` or an athlete-stated range and from nowhere else. So the vocabulary
carries no number, the column carries no number, and a test below asserts it of
the registry file rather than trusting anybody to remember.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vitai.db import LIST_COLS, column_affinity  # noqa: E402
from vitai.schema import (  # noqa: E402
    CURRENT_GENERATION,
    KEYS,
    body_state_alias,
    body_state_conditions,
    key_generation,
    validate_record,
)

REGISTRY = (Path(__file__).resolve().parents[1]
            / "src" / "vitai" / "semantics" / "body_state.toml")


def row(controls=None, **over):
    rec = {"date": "2030-01-01", "slug": "morning-fasted",
           "text": "up, void, underwear, before food or drink",
           "supersedes": None, "recorded_at": None, "device": None,
           "controls": controls, "_gen": 2}
    rec.update(over)
    return rec


# --- the declaration -----------------------------------------------------


def test_a_protocol_can_declare_what_it_fixes():
    assert validate_record("protocols", row(["bladder", "fed"])) == []


def test_the_vocabulary_is_closed():
    """Deliberately unlike the slug beside it, which is open.

    A protocol slug is the athlete's own name for their own procedure and
    nobody else has to read it. A condition exists ONLY to be compared, so an
    open vocabulary gives one record `bladder` and the next `bladder_full`
    with nothing able to tell they are one fact - which is the whole value of
    declaring it.
    """
    problems = validate_record("protocols", row(["mood"]))
    assert any("body_state" in p for p in problems), problems
    # And the refusal names the legal values rather than making the author
    # go and find them.
    assert any("bladder" in p for p in problems), problems


def test_the_athletes_own_words_resolve_through_aliases():
    """A closed vocabulary that refused "shoes off" would teach the athlete
    that declaring anything costs an argument, which ends with nobody
    declaring anything."""
    assert validate_record("protocols", row(["shoes off", "wee"])) == []
    assert body_state_alias("barefoot") == "footwear"
    assert body_state_alias("coffee") == "hydration"
    assert body_state_alias("not a condition") is None


def test_absent_and_empty_are_different_facts():
    """Null is a protocol written before this field existed, or one whose
    author has not said. An empty list asserts that a procedure somebody
    bothered to write down fixes NOTHING, which is almost certainly a
    serialiser rather than a statement."""
    assert validate_record("protocols", row(None)) == []
    assert any("empty" in p for p in validate_record("protocols", row([])))


def test_one_declaration_per_condition_counting_aliases():
    """`footwear` and `barefoot` are one condition, and a row carrying both
    looks like two declarations and is one."""
    problems = validate_record("protocols", row(["footwear", "barefoot"]))
    assert any("more than once" in p for p in problems), problems


def test_a_non_list_is_refused():
    assert validate_record("protocols", row("bladder")) != []


# --- the rule that makes it honest ---------------------------------------


def test_no_magnitude_reaches_the_registry():
    """THE ISSUE'S CENTRAL RISK, enforced against the file rather than by a
    rule somebody has to remember.

    #404's table of rough masses - clothing 0.3 to 1 kg, sweat 0.5 to 2 kg -
    is there to argue the problem is real. If one of those figures were
    recorded here it would eventually be multiplied, and a band assembled from
    general knowledge is a confident wrong number about confidence.

    So: no numeric value anywhere in the registry except its own `version`,
    and no key that could hold one.
    """
    raw = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    banned = {"kg", "mass", "grams", "g", "u", "uncertainty", "band",
              "lo", "hi", "spread", "magnitude", "weight", "typical"}
    for slug, meta in raw["condition"].items():
        assert not (set(meta) & banned), (slug, sorted(set(meta) & banned))
        for key, value in meta.items():
            assert not isinstance(value, (int, float)), (slug, key, value)


def test_the_registry_carries_the_conditions_the_athlete_named():
    assert set(body_state_conditions()) == {
        "bladder", "bowel", "fed", "hydration", "clothing", "footwear",
        "post_exertion"}


def test_hydration_is_not_fed():
    """They come apart on the case that prompted the issue: coffee on an
    otherwise fasted morning is drink without food, and a protocol may fix one
    and leave the other free. Folding them together would make "I voided but I
    had coffee" unsayable, which is the sentence the feature exists for."""
    assert body_state_alias("coffee") == "hydration"
    assert body_state_alias("breakfast") == "fed"


# --- the schema plumbing -------------------------------------------------


def test_it_is_additive_under_g25():
    """Old lines keep validating: a founding-generation row carries no
    `controls` and owes none."""
    assert key_generation("protocols", "controls") == 2
    assert CURRENT_GENERATION["protocols"] == 2
    old = {"date": "2030-01-01", "slug": "morning", "text": "as before",
           "supersedes": None, "recorded_at": None, "device": None, "_gen": 1}
    assert validate_record("protocols", old) == []


def test_it_is_a_declared_container():
    """A consumer reading the read model has to know this TEXT column is JSON,
    and #257's whole point is that it should not have to guess."""
    assert "controls" in KEYS["protocols"]
    assert "controls" in LIST_COLS
    assert column_affinity("controls") == "TEXT"


def test_there_is_no_companion_free_list():
    """Contract 44's rule, one dataset over: silence resolves to `unknown`
    rather than to a default. A `free` list would co-vary with `controls`
    forever, and "declared free" would be read as "measured to be irrelevant",
    which is a claim nobody has made about a condition nobody has weighed."""
    assert "free" not in KEYS["protocols"]
    assert not any(k.endswith("_free") for k in KEYS["protocols"])


@pytest.mark.parametrize("field", ["u", "u_obs", "band", "kg", "mass"])
def test_the_row_has_nowhere_to_put_a_number(field):
    """Enforced by the column set. The arithmetic that would consume this is
    #402's and is blocked on evidence no record holds yet, so the schema does
    not offer a slot that would invite it early."""
    assert field not in KEYS["protocols"]
