"""The engine already knew the unit (#310).

A client kept two maps by hand that this engine validates against: what unit
each field holds, and what an English speaker calls it. Both went stale the way
a copy of somebody else's knowledge does, and the second failed SILENTLY - a
question naming a metric the list had forgotten matched no topic, fell through
to a standing fact pack, and a model answered a question about step counts by
fluently describing a set of goals.

The unit was never published. It was in the FIELD NAME, by a convention nothing
enforces: `distance_km` says it, `rhr` and `steps` say nothing, and no rule
says which do. A client guessing from a suffix is one rename away from printing
kilometres as seconds.

UCUM AS REGISTRY DATA, NEVER A CONVERSION LIBRARY. Converting needs a runtime
dependency this engine does not ship, and it is the consumer's arithmetic in
any case: publishing the code is a statement about the record, performing the
conversion would be a claim about the world.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from vitai.api import field_types
from vitai.schema import KEYS, aliases_for, units
from vitai.vocab import registry

# The whole table, hashed, so a change to ANY key of ANY entry has to be
# deliberate - not just the `ucum` codes, which is all the first version
# covered.
PINNED_DIGEST = "d5b1a7ad5cf0b4ca"

REGISTRY = Path(__file__).resolve().parents[1] / "src" / "vitai" / "semantics" / "units.toml"
def _numeric_in_the_corpus() -> set[tuple[str, str]]:
    """Every (dataset, field) that actually holds a number in a shipped record.

    NOT `spec["types"]`, which is where the first gate looked and is why it
    silently skipped all fourteen numeric fields on `sets` plus
    `artifacts.bytes`: `schema._TYPES` has no entry for them, so they publish
    `types: null` and a check for "numeric" walked straight past. A strength
    client reading `load` got nothing at all - the reported failure, in the
    dataset it most concerns. Reading the corpus cannot make that mistake,
    because a number in a file is a number whatever the type table says.
    """
    root = Path(__file__).resolve().parent
    seen: set[tuple[str, str]] = set()
    paths = list((root / "fixtures" / "personas").glob("*/data/*.jsonl"))
    paths += list((root.parent / "examples" / "demo" / "data").glob("*.jsonl"))
    for path in paths:
        dataset = path.stem
        if dataset not in KEYS:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for field, value in json.loads(line).items():
                if (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and field in KEYS[dataset]):
                    seen.add((dataset, field))
    return seen


DECLARED = {(ds, f) for ds, fields in field_types().items()
            for f, spec in fields.items()
            if spec["types"] and set(spec["types"]) & {"integer", "number"}}
NUMERIC = DECLARED | _numeric_in_the_corpus()


# --- the gate -----------------------------------------------------------------

def test_every_number_the_engine_holds_says_what_it_is_in():
    """THE CLASSIFICATION GATE, the same shape as #299's for sensitivity - and
    that one earned its keep immediately by refusing `avg_power` until somebody
    classified it. A numeric field with no entry here is a number a consumer
    can only guess at, and it would arrive silently."""
    missing = sorted(f"{ds}.{f}" for ds, f in NUMERIC if not units(ds, f))
    assert not missing, (
        f"{missing} are numeric and say nothing about their units. Add an entry "
        "to semantics/units.toml: a `ucum` code, a `unit_of`/`scale_of`/"
        "`unit_in` naming the field that decides it, or `machine_scoped` / "
        "`ordinal` / `unstated` where there is no unit to give.")
    assert len(NUMERIC) > len(DECLARED), (
        "the gate must read the corpus as well as the type table - reading "
        "only the table is what let all of `sets` through")


def test_each_entry_gives_exactly_one_answer():
    """Four kinds, and a field must pick one. Two would mean the table
    disagreed with itself; none would mean the entry exists and says nothing."""
    kinds = {"ucum", "unit_of", "scale_of", "unit_in", "machine_scoped",
             "ordinal", "unstated"}
    for dataset in KEYS:
        for field in KEYS[dataset]:
            spec = units(dataset, field)
            if not spec:
                continue
            given = kinds & set(spec)
            assert len(given) == 1, f"{dataset}.{field}: {sorted(given)}"
            assert spec.get("label"), f"{dataset}.{field} has no label"


def test_a_field_with_no_quantity_says_nothing_rather_than_something_empty():
    """A date, a slug and a note are not dimensionless - they are not
    quantities. An empty dict is the answer; a `ucum` of `""` would be a claim
    that they are numbers with no unit."""
    for dataset, field in (("daily", "note"), ("daily", "date"),
                           ("sessions", "type"), ("weight", "source")):
        assert units(dataset, field) == {}, f"{dataset}.{field}"


def test_following_a_reference_lands_somewhere(tmp_path):
    """A POINTER TO NOTHING IS WORSE THAN SILENCE, because `{}` also means "not
    a quantity" - so a consumer cannot tell a dead reference from a field that
    has no unit, and the first version shipped three dead ones.

    `thresholds.value -> key` resolved for ZERO shipped rows: the six
    registered keys are not field names. `measurements.value -> kind` resolved
    for one of eight legal kinds. Both are now entries in the table, so
    following the pointer arrives.
    """
    from vitai.policy import THRESHOLD_METRIC
    from vitai.schema import MEASUREMENT_KINDS

    def resolves(name):
        return any(units(ds, name) for ds in KEYS)

    for kind in MEASUREMENT_KINDS:
        if kind == "other":
            continue           # deliberately open, and says so by its name
        assert resolves(kind), f"measurements.kind={kind!r} points at nothing"
    for key in THRESHOLD_METRIC:
        assert resolves(key), f"thresholds.key={key!r} points at nothing"


def test_a_reference_names_a_field_that_exists_in_that_dataset():
    """`unit_of` and `scale_of` are the honest answer where the unit is not a
    property of the field at all. They are also the easiest thing here to get
    wrong, because a name that resolves to nothing looks exactly like one that
    resolves."""
    for dataset in KEYS:
        for field in KEYS[dataset]:
            spec = units(dataset, field)
            for key in ("unit_of", "scale_of"):
                if key in spec:
                    assert spec[key] in KEYS[dataset], (
                        f"{dataset}.{field} points at {spec[key]!r}, "
                        f"which {dataset} does not have")


def test_a_named_scale_is_one_the_scale_registry_knows():
    known = set(registry("scales")["scales"])
    for dataset in KEYS:
        for field in KEYS[dataset]:
            named = units(dataset, field).get("scale")
            if named:
                assert named in known, f"{dataset}.{field} -> {named}"


# --- what the codes are -------------------------------------------------------

def test_every_entry_is_pinned_so_a_change_has_to_be_deliberate():
    """A FIELD'S UNIT IS IMMUTABLE, and this is the control on that rule.

    The issue's comment proposed a table keyed by (field, generation), so old
    rows resolve against the generation they were stamped with. Measured, that
    key does not hold: `_gen` is absent on 128 rows across 13 datasets in the
    shipped fixtures and defaults to 1; it is not a column in the read model,
    so a consumer holding a row cannot look it up; and `_carry_meta` takes the
    MAXIMUM across merged claims, so a row assembled from two generations
    reports the newer. So the rule is stronger and needs no key: the unit never
    changes, and changing what a field holds is a NEW FIELD.

    EVERY KEY, not just `ucum`, which is what the first version pinned. That
    left two holes a mutation walked straight through: `hip_pain`'s `scale_of`
    could be repointed at `mood_scale` with the whole suite green, and any
    `label` could be changed from "kilograms" to "pounds" while the code stayed
    `kg` - and the label is the string a client actually prints beside the
    number. "Printing kilometres as seconds", one key over.
    """
    import hashlib
    table = registry("units")
    flat = sorted(
        (name, key, str(value))
        for name, entry in table["unit"].items()
        for key, value in entry.items() if key != "aliases")
    flat += sorted(
        (f"{dataset}.{field}", key, str(value))
        for dataset, fields in table["override"].items()
        for field, entry in fields.items()
        for key, value in entry.items() if key != "aliases")
    digest = hashlib.sha256(repr(sorted(flat)).encode()).hexdigest()[:16]
    assert digest == PINNED_DIGEST, (
        f"the units table changed: {digest}\n"
        "If a UNIT changed, that is a new field, not an edit - retire the old "
        "one through `KEY_RETIREMENT` and give the new one its own name. If a "
        "label or a reference changed, update PINNED_DIGEST deliberately.")


def test_a_count_is_not_a_length_in_disguise():
    """`{steps}` is UCUM's annotation form - dimensionless, with the annotation
    saying what is being counted. Giving steps a length would let a consumer
    add them to a distance."""
    assert units("daily", "steps")["ucum"] == "{steps}"
    assert units("daily", "distance_km")["ucum"] == "km"


def test_an_ordinal_score_is_not_given_a_unit():
    """A 7 on the Borg scale is not seven of anything, so no unit - and no
    fixed SCALE either, which the first version got wrong.

    `rpe_scale` exists on both sessions and sets (#246) and its contract is
    that absent means unstated and no reader may invent a denominator: a
    stored 7 is "quite light" on Borg 6-20 and "very hard" on CR10. Naming
    CR10 here published one of those as fact for every row of both datasets,
    including a vendor import saying the other."""
    for dataset in ("sessions", "sets"):
        rpe = units(dataset, "rpe")
        assert "ucum" not in rpe, dataset
        assert "scale" not in rpe, dataset
        assert rpe["scale_of"] == "rpe_scale", dataset


def test_a_scale_the_row_names_itself_is_not_restated_here():
    """`daily` carries `mood_scale` and `pain_scale`. Hard-coding a scale here
    would be a second copy of a fact the row already holds, free to disagree
    with it - and the row is the one that is right."""
    assert units("daily", "mood") == {
        "scale_of": "mood_scale", "label": "mood score"}
    assert units("daily", "pain")["scale_of"] == "pain_scale"


def test_a_borrowed_unit_says_where_to_look_rather_than_guessing():
    """A goal's target is in the units of its metric. Answering with a constant
    would be wrong confidently, which is worse than the field name it
    replaces."""
    assert units("goals", "target")["unit_of"] == "metric"
    assert units("goals", "target_hi")["unit_of"] == "metric"


def test_one_name_meaning_three_things_is_resolved_per_dataset():
    """`value` is a measurement's quantity, a threshold's figure and a check's
    result. The override table is small on purpose, exactly as
    `SENSITIVITY_OVERRIDE` is: an override is a place a name stopped carrying
    its meaning."""
    assert units("measurements", "value")["unit_of"] == "kind"
    assert units("thresholds", "value")["unit_of"] == "key"
    # A check's slug is athlete-invented and nothing knows what it measures, so
    # this is NOT a reference: `unit_of` would send a consumer to look up a
    # name that is not a field, and it would get `{}` - which also means "not a
    # quantity", so a dead pointer and a non-quantity are indistinguishable.
    assert "unit_of" not in units("checks", "value")
    assert units("checks", "value")["unstated"]


# --- the English half ----------------------------------------------------------

def test_the_words_people_actually_use_are_published():
    """Nobody asks how their rhr was. This map cannot be derived from anything
    and the client copy of it failed silently."""
    assert "resting heart rate" in aliases_for("rhr")
    assert "sleep" in aliases_for("sleep_h")
    assert "calories" in aliases_for("kcal_in")
    assert "weight" in aliases_for("kg")
    assert "body fat" in aliases_for("body_fat_pct")


def test_a_field_nobody_asks_about_has_no_aliases_rather_than_a_guess():
    """A vocabulary that grows by guesswork is how "unusual" arrives as a
    category. The bound fields carry the unit and not the English, because
    nobody asks about the upper end of a confidence interval by name."""
    assert aliases_for("kg_hi") == []
    assert aliases_for("sodium_mg_100g") == []


def test_no_alias_collides_with_another_field():
    """A word that routes to two fields routes to neither, and it would do so
    silently - which is the failure this whole entry exists to fix."""
    seen: dict[str, str] = {}
    for name, entry in registry("units")["unit"].items():
        for alias in entry.get("aliases") or []:
            assert alias not in seen, f"{alias!r}: {seen[alias]} and {name}"
            seen[alias] = name


def test_no_alias_is_a_field_name_belonging_to_something_else():
    every = {f for fields in KEYS.values() for f in fields}
    for name, entry in registry("units")["unit"].items():
        for alias in entry.get("aliases") or []:
            assert alias == name or alias not in every, f"{alias!r} on {name}"


def test_no_alias_collides_with_another_registry():
    """THE TESTS THAT SHIPPED FIRST WERE BLIND TO EVERY OTHER VOCABULARY, and
    real collisions were in the file: "climbing" was an alias of `elevation_m`
    and also of the `climb` session type, "walking" was an alias of `steps` and
    also of the `walk` type AND of an activity class the restriction vocabulary
    reads, and "scale" was an alias of `kg`, a live `weight.source` value, and
    the word this file's own ordinal machinery uses.

    A router keyed on these hits a name that means an activity, which is the
    silent mis-routing this entry exists to stop - and for the restriction
    vocabulary it reaches the curated gate side, which #56 keeps deliberately
    separate."""
    from vitai.vocab import activity_classes

    taken: dict[str, str] = {}
    for slug, entry in registry("session_types")["types"].items():
        taken[slug] = "a session type"
        for alias in entry.get("aliases") or []:
            taken[alias] = f"an alias of session type {slug}"
    for cls in activity_classes():
        taken[cls] = "an activity class the restriction vocabulary reads"
    for slug in registry("scales")["scales"]:
        taken[slug] = "a named scale"

    for name, entry in registry("units")["unit"].items():
        for alias in entry.get("aliases") or []:
            assert alias not in taken, (
                f"{alias!r} on {name} is already {taken[alias]}")


def test_an_override_never_carries_aliases_that_would_be_dropped():
    """`aliases_for` reads the `unit` table only, so an alias written into an
    override would be silently ignored."""
    for dataset, fields in registry("units")["override"].items():
        for field, entry in fields.items():
            assert "aliases" not in entry, f"{dataset}.{field}"


# --- and it reaches a consumer -------------------------------------------------

def test_the_published_schema_carries_both():
    """It is no use as an internal table: the whole issue is that a client
    could not read it."""
    spec = field_types("daily")["daily"]["rhr"]
    assert spec["units"]["ucum"] == "/min"
    assert "resting heart rate" in spec["aliases"]


def test_the_units_payload_does_not_smuggle_the_aliases():
    """One file because both are facts about one field; two keys because a
    unit is what the number is in and an alias is what a person calls it."""
    spec = field_types("weight")["weight"]["kg"]
    assert "aliases" not in spec["units"]
    assert spec["aliases"]


def test_the_cli_publishes_it_too():
    """P9: the CLI and the API are one surface, and a client shelling out is
    the case this was reported from."""
    import json
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "schema", "--json"],
                         capture_output=True, text=True, check=True).stdout
    payload = json.loads(out)
    assert payload["fields"]["daily"]["rhr"]["units"]["ucum"] == "/min"
    assert "resting heart rate" in payload["fields"]["daily"]["rhr"]["aliases"]


# --- and it never converts anything --------------------------------------------

def test_the_registry_holds_codes_and_no_arithmetic():
    """UCUM is registry DATA here. A factor in this file would be the first
    line of a conversion library, and converting needs a dependency this engine
    does not ship - so the code is published and the arithmetic is the
    consumer's."""
    raw = REGISTRY.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in raw.splitlines() if not ln.lstrip().startswith("#"))
    for banned in ("factor", "multiply", "convert", "to_base", "si_factor"):
        assert banned not in body.lower(), banned


def test_the_table_holds_nothing_a_conversion_could_be_built_from():
    """The rule as a property of the data rather than a promise in a comment.

    Every value in this registry is a string or a list of strings. There is no
    number anywhere in it, so there is nothing to multiply by - a conversion
    would have to bring its own factors, and at that point it is a library,
    which is a runtime dependency this engine does not ship.
    """
    def leaves(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v)
        else:
            yield node

    table = registry("units")
    def numeric(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        # A FACTOR IN QUOTES IS STILL A FACTOR. The first version checked the
        # type, so `si = "4.184"` passed it and the banned-words test too.
        try:
            float(str(value))
        except ValueError:
            return False
        return True

    # `ucum` is exempt: `1` is UCUM's own code for a plain ratio, and a CODE
    # is never a factor. Everything else in the table must be unarithmetic.
    def strip_codes(node):
        if isinstance(node, dict):
            return {k: strip_codes(v) for k, v in node.items() if k != "ucum"}
        if isinstance(node, list):
            return [strip_codes(v) for v in node]
        return node

    numbers = [v for v in leaves(strip_codes(
        {k: v for k, v in table.items() if k != "version"})) if numeric(v)]
    assert not numbers, numbers


def test_the_unit_accessor_returns_strings_and_never_a_quantity():
    """A consumer cannot accidentally do arithmetic with what it is handed."""
    for dataset in KEYS:
        for field in KEYS[dataset]:
            for key, value in units(dataset, field).items():
                assert isinstance(value, str), f"{dataset}.{field}.{key}"


def test_the_registry_parses_and_declares_its_version():
    data = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert set(data) == {"version", "unit", "override"}


@pytest.mark.parametrize("dataset,field", sorted(NUMERIC))
def test_every_numeric_field_round_trips_through_the_public_surface(dataset, field):
    """The gate above checks the table; this checks that what the table says
    actually reaches the payload a consumer reads."""
    assert field_types(dataset)[dataset][field]["units"] == units(dataset, field)
