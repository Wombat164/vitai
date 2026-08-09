"""One published display name per field (#331).

A client that wants to show a field to a person had nothing canonical to show.
`aliases` is published per field and arrives alphabetically sorted, because it
is for RECOGNITION - it is what makes "resting heart rate" verify against
`rhr`, and it is excellent at that. It is not a display name, and its first
entry is not a candidate for one: `kcal_out` renders as "burned" and `sleep_h`
as "hours slept".

`units[...]["label"]` is not one either, though the issue proposed it as the
precedent. That label names the UNIT. `kcal_in` and `kcal_out` both answer
"kilocalories", so a consumer using it shows two different fields the same
word - and 306 of the engine's 382 dataset fields have no units entry at all.

So the client softened the field name's underscores and rendered "kcal in",
which invents nothing and is obviously the same token, and is not what a
person calls the thing.

DERIVED WHERE DERIVATION IS HONEST. Softening underscores is right for most of
the 189 distinct field names - `pain_site` really is "pain site" - and
hand-writing those would be a second copy of the field list that goes stale.
What derivation cannot do is expand an abbreviation or a unit suffix, so those
33 are registry data, and the gate at the bottom of this file refuses a new
abbreviated field that has no entry.
"""

from __future__ import annotations

from vitai.api import field_types
from vitai.schema import ABBREVIATIONS, KEYS, aliases_for, display_name, units


def test_the_fields_the_issue_names_read_as_a_person_would_say_them():
    assert display_name("daily", "kcal_in") == "energy in"
    assert display_name("daily", "kcal_out") == "energy out"
    assert display_name("daily", "sleep_h") == "sleep"
    assert display_name("daily", "rhr") == "resting heart rate"


def test_it_is_not_the_first_alias():
    """The thing the issue rules out, asserted rather than described.

    SORTED, which is the form a consumer receives - `emit_artifact` publishes
    `sorted(aliases_for(field))`, so the head is an accident of the alphabet.
    `aliases_for` itself returns registry order, and taking ITS head would
    have made this test pass for `sleep_h` by luck: the registry happens to
    list "sleep" first, and the published head is "hours slept"."""
    for field in ("kcal_out", "sleep_h", "kcal_in"):
        published = sorted(aliases_for(field))
        assert display_name("daily", field) != published[0], field
    assert sorted(aliases_for("kcal_out"))[0] == "burned"
    assert sorted(aliases_for("sleep_h"))[0] == "hours slept"


def test_the_name_is_still_a_word_people_use_for_it():
    """Not a licence to invent. The display name should be IN the recognition
    set where that set exists - it is the one the engine would use in its own
    prose, not a new coinage nobody would say."""
    for dataset, field in (("daily", "kcal_in"), ("daily", "kcal_out"),
                           ("daily", "sleep_h"), ("daily", "rhr")):
        known = aliases_for(field)
        assert display_name(dataset, field) in known, (field, known)


def test_it_is_not_the_unit_label():
    """`label` names the unit, and two different fields share one - which is
    exactly why a consumer cannot use it as a name."""
    assert units("daily", "kcal_in")["label"] == units("daily", "kcal_out")["label"]
    assert display_name("daily", "kcal_in") != display_name("daily", "kcal_out")


def test_a_plain_field_name_is_derived_rather_than_hand_written():
    """The other 150. A registry entry per field would be a second copy of the
    field list, and the copy is what goes stale."""
    from vitai.vocab import registry

    assert display_name("daily", "pain_site") == "pain site"
    assert display_name("sessions", "start_time") == "start time"
    assert "pain_site" not in registry("units").get("name", {})


def test_every_field_of_every_dataset_has_one():
    for dataset in KEYS:
        for field in KEYS[dataset]:
            got = display_name(dataset, field)
            assert got and got.strip() == got, f"{dataset}.{field}"
            assert "_" not in got, f"{dataset}.{field} -> {got!r}"


def test_it_reaches_the_published_surface():
    got = field_types("daily")["daily"]
    assert got["kcal_in"]["display_name"] == "energy in"
    assert got["pain_site"]["display_name"] == "pain site"


# --- the gate ------------------------------------------------------------------

def test_a_field_carrying_an_abbreviation_has_a_curated_name():
    """THE CONTROL THAT MATTERS, because everything above is about today's
    fields and this is about tomorrow's.

    A new field called `power_w` or `vo2_max` would derive to "power w", ship,
    and read as a typo on the client's screen - the exact failure this issue
    reports, one field later. So a name carrying a token a person does not say
    out loud must be in the registry.

    The check is on the DERIVED form, not on the registry: an entry that
    happens to restate the derivation still passes, and what fails is a field
    reaching a person with an abbreviation in it."""
    from vitai.vocab import registry

    curated = registry("units").get("name", {})
    offenders = []
    for dataset in KEYS:
        for field in KEYS[dataset]:
            if field in curated:
                continue
            if set(field.split("_")) & ABBREVIATIONS:
                offenders.append(f"{dataset}.{field} -> {display_name(dataset, field)!r}")
    assert not offenders, (
        "these would render an abbreviation at a person; add a [name] entry "
        f"in semantics/units.toml: {sorted(set(offenders))}")


def test_the_registry_names_no_field_the_engine_does_not_have():
    """The other direction: an entry for a retired field is a name nothing
    will ever ask for, and it hides that the field is gone."""
    from vitai.vocab import registry

    known = {f for ds in KEYS for f in KEYS[ds]}
    named = set(registry("units").get("name", {}))
    assert not (named - known), sorted(named - known)


def test_a_plain_word_field_is_not_replaced_by_a_colloquial_alias():
    """The fallback that must NOT exist, pinned on the nine fields where it
    would be observable.

    `pain`, `mood`, `load` and `steps` all carry aliases and need no curated
    name, so a display name that fell back to the alias list would publish
    "how much it hurt", "feeling", "how heavy" and "step count". Those are
    recognition phrases - the words someone might TYPE - and a column heading
    is not a question. Mutating `display_name` to fall back to the first alias
    passed every other test in this file."""
    assert display_name("daily", "pain") == "pain"
    assert display_name("daily", "mood") == "mood"
    assert display_name("sets", "load") == "load"
    assert display_name("daily", "steps") == "steps"
    # And each of those really does have a colloquial alias to be tempted by.
    for field in ("pain", "mood", "load", "steps"):
        assert aliases_for(field), field
        assert display_name("daily", field) != sorted(aliases_for(field))[0], field


def test_the_abbreviation_list_was_built_by_audit_not_by_memory():
    """A regression guard on the nine tokens the eyeballed list missed. Each
    was published at a person before the audit found it."""
    for token in ("rir", "mg", "pos", "seq", "ref", "op", "deg", "100g", "asof"):
        assert token in ABBREVIATIONS, token
    assert display_name("sets", "rir") == "reps in reserve"
    assert display_name("meals", "sodium_mg") == "sodium"


def test_it_reaches_the_cli_and_the_agent_surface(tmp_path):
    """P9: a capability lands on the CLI and the API in the same change.

    No new command and no new tool - `schema()` already carries `fields` from
    `field_types`, so `vitai schema --json` and the MCP `schema` tool both
    gained it. Asserted rather than assumed, because "it comes through for
    free" is the kind of claim that stops being true quietly."""
    import json
    from vitai.api import schema
    from vitai.mcp import call

    assert schema()["fields"]["daily"]["kcal_in"]["display_name"] == "energy in"

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    got = call(root, "schema", {})
    assert got["fields"]["daily"]["kcal_in"]["display_name"] == "energy in"
    assert json.dumps(got)  # and it survives the wire
