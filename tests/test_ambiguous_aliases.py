"""A word that names more than one measurand, published as a question (#400).

`field_types()` published `pulse` as an alias of `avg_hr` - a session average,
heart rate while training. vitai-lens had it on `rhr`. Two clients, one
question, two different metrics, and neither marked the choice as a choice.

The issue asked which of three shapes was right: move `pulse` to `rhr`, drop it
from both, or publish the ambiguity. Measuring the registry answered a
different question first, and it is the one these tests are built on:
`test_no_alias_collides_with_another_field` already exists, already says "a
word that routes to two fields routes to neither, and it would do so silently",
and compares whole strings - so it could not see `pulse` beside `resting
pulse`, and six words were in that state rather than one.

`pulse` is not the worst of the six. `calories` resolved to what was EATEN
while `session calories` resolves to what was BURNED; `fat` resolved to grams
of dietary fat while `body fat` resolves to a body-composition percentage.
"""

import pytest

from vitai.api import field_types, schema
from vitai.schema import KEYS, aliases_for, ambiguous_aliases
from vitai.vocab import registry

# THE REGISTER, and it is deliberate rather than a snapshot nobody meant.
#
# The derivation is mechanical, so a NEW colliding alias would be moved out of
# `aliases` automatically and the gate in `test_units.py` would stay green
# while a word silently stopped being recognised. That is the same shape as
# the defect being fixed: a change nobody sees.
#
# So the set is pinned. Adding a word here is a DECISION - somebody chose to
# publish a bare form beside a qualified one and accepted that it resolves to
# neither. Removing one is a decision too: it means a qualified sibling went
# away and the bare form is now unambiguous.
AMBIGUOUS = {
    "calories": ["kcal", "kcal_in"],
    "duration": ["duration_s", "sleep_h"],
    "fat": ["body_fat_pct", "fat_g"],
    "heart rate": ["avg_hr", "max_hr", "rhr"],
    "hr": ["avg_hr", "max_hr", "rhr"],
    "pulse": ["avg_hr", "rhr"],
}


def test_the_ambiguous_set_is_exactly_what_was_decided():
    assert ambiguous_aliases() == AMBIGUOUS, (
        "the derived ambiguity changed. That is a decision, not a diff: a "
        "word appearing here stops being an alias of anything, and a word "
        "leaving here starts resolving to one field again")


def test_every_ambiguous_word_names_at_least_two_distinct_measurands():
    """One candidate is not an ambiguity, it is an alias with extra steps."""
    for word, fields in ambiguous_aliases().items():
        assert len(set(fields)) >= 2, f"{word!r} names {fields}"


def test_every_candidate_is_a_real_field():
    """A refusal naming a field that does not exist is worse than no refusal:
    a client renders the candidates and one of them is a typo."""
    every = {f for fields in KEYS.values() for f in fields}
    for word, fields in ambiguous_aliases().items():
        for field in fields:
            assert field in every, f"{word!r} names {field!r}, not a field"


def test_an_ambiguous_word_is_never_also_published_as_an_alias():
    """THE PROPERTY A CLIENT'S RESOLVER RESTS ON. Look the word up in the
    ambiguity map, refuse if it is there, otherwise match `aliases`. If a word
    could be in both, that resolver answers confidently for a word the engine
    just said it could not answer for, and the order of two lookups decides
    which behaviour a client gets."""
    ambiguous = set(ambiguous_aliases())
    for dataset, fields in field_types().items():
        for name, spec in fields.items():
            overlap = ambiguous & set(spec["aliases"])
            assert not overlap, f"{dataset}.{name} publishes {sorted(overlap)}"


def test_the_published_payload_carries_the_map():
    """A refusal a client cannot reach is one every client reinvents - #350's
    defect, which is why the alias list is published at all."""
    assert schema()["ambiguous_aliases"] == ambiguous_aliases()


# ---- the case the issue was filed for ---------------------------------------

def test_pulse_resolves_to_neither_field_and_says_which_two():
    assert ambiguous_aliases()["pulse"] == ["avg_hr", "rhr"]
    assert "pulse" not in aliases_for("avg_hr")
    assert "pulse" not in aliases_for("rhr")


def test_the_qualified_form_still_answers():
    """DROPPING THE WORD WAS THE SHAPE THIS REJECTED. `resting pulse` carries
    the disambiguator, names one field, and is unaffected - so the athlete's
    question is still recognised in the form that has an answer."""
    assert "resting pulse" in aliases_for("rhr")
    assert "resting pulse" not in ambiguous_aliases()


def test_the_engines_own_prose_disagreed_with_its_own_data():
    """Recorded because it is the sharpest evidence that `avg_hr` was wrong.

    `session_types`' docstring justifies publishing this vocabulary with: a
    client hand-maintaining `rhr` and `resting` missed "pulse", so an athlete
    typing "pulse 52" matched nothing. 52 is a resting reading - nobody
    averages 52 over a tempo run - so the engine's own argument for shipping
    the word puts it with `rhr`, while the registry shipped it on `avg_hr`.

    The contradiction was inside the engine, not between the engine and a
    client, and neither field is the answer: `capabilities` in the demo
    already declares `rhr` from a scale a proxy for "a daytime spot statistic,
    not the nightly minimum".
    """
    import vitai.api as api

    doc = api.session_types.__doc__
    assert "pulse 52" in doc
    assert "avg_hr" not in doc


def test_a_two_step_resolver_refuses_the_bare_word_and_answers_the_qualified():
    """The end-to-end contract, written as a client would use it."""
    payload = schema()
    ambiguous = payload["ambiguous_aliases"]

    def resolve(word):
        if word in ambiguous:
            return ("refuse", ambiguous[word])
        for dataset, fields in payload["fields"].items():
            for name, spec in fields.items():
                if word in spec["aliases"]:
                    return ("answer", f"{dataset}.{name}")
        return ("unknown", None)

    assert resolve("pulse") == ("refuse", ["avg_hr", "rhr"])
    assert resolve("resting pulse") == ("answer", "daily.rhr")
    assert resolve("calories") == ("refuse", ["kcal", "kcal_in"])
    assert resolve("calories eaten") == ("answer", "daily.kcal_in")
    assert resolve("nonsense word") == ("unknown", None)


@pytest.mark.parametrize("word", sorted(AMBIGUOUS))
def test_no_ambiguous_word_was_lost_from_the_registry(word):
    """The fix removes words from `aliases`; it may not remove them from the
    vocabulary. An athlete can still say "pulse" and something must know the
    word exists in order to refuse for it."""
    kept = {a for entry in registry("units")["unit"].values()
            for a in entry.get("aliases") or []}
    assert word in kept
