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
54 are registry data, and the gate at the bottom of this file refuses a name
built from a word nobody blessed.
"""

from __future__ import annotations

from vitai.api import field_types
from vitai.schema import KEYS, PLAIN_WORDS, aliases_for, display_name, units

# Every word the engine is allowed to show a person: the derivation's
# vocabulary, plus the words its curated names introduce.
#
# WRITTEN OUT, not computed from the registry, and that is the whole point.
# The first version built this half by reading the curated names themselves,
# which made the allowlist self-defeating: setting `seat_pos = "seat pos"`
# blessed "pos" on the way past, and the gate that exists to catch exactly
# that entry waved it through. An allowlist derived from the thing it checks
# is not an allowlist.
#
# Here rather than in `schema` because it is the TEST's question - production
# only needs to know which words derivation may pass through.
CURATED_WORDS = frozenset({
    "100", "active", "as", "average", "band", "bound", "carbohydrate",
    "content", "derivation", "distance", "duration", "elevation", "energy",
    "exertion", "fat", "fibre", "g", "gain", "guard", "hash", "heart", "id",
    "identifier", "in", "lever", "lower", "maximum", "minutes", "of", "out",
    "pad", "per", "perceived", "position", "power", "precise", "protein",
    "rate", "reference", "reserve", "rest", "resting", "seat", "sequence",
    "session", "sodium", "sugar", "trained", "upper", "weight", "with",
})
BLESSED = PLAIN_WORDS | CURATED_WORDS


def test_the_fields_the_issue_names_read_as_a_person_would_say_them():
    assert display_name("daily", "kcal_in") == "energy in"
    assert display_name("daily", "kcal_out") == "energy out"
    assert display_name("daily", "sleep_h") == "sleep"
    assert display_name("daily", "rhr") == "resting heart rate"


def test_it_is_not_the_first_alias():
    """The thing the issue rules out, asserted rather than described.

    EITHER ORDER, and the first version of this got the reason wrong. It said
    the list "arrives sorted", so the head is an accident of the alphabet.
    This engine publishes `aliases_for(field)` in REGISTRY order - a consumer
    that sorts is sorting something already arbitrary. So the claim is not
    about sorting at all: an alias list has no head that means anything,
    because it is a recognition SET, and whichever end you take is a word
    chosen to be matched rather than to be printed.

    NOT "the name always differs from the head" either, which is the third
    version of this test and the second thing I got wrong about it: for
    `sleep_h` the registry head IS "sleep", which is the right name. A rule
    that happens to hold is not the claim. The claim is that the head is not a
    SOURCE - it produces a bad name often enough that a consumer cannot use
    it - so the test names the fields where it does."""
    for field, head_would_give in (("kcal_out", "calories out"),
                                   ("grams", "portion"),
                                   ("elevation_m", "elevation"),
                                   ("rir", "rir")):
        assert aliases_for(field)[0] == head_would_give, field
        assert display_name("daily", field) != head_would_give, field
    # And sorting it, which some consumer will do, is no better - `rir` goes
    # from the raw token to "left in the tank", which is worse.
    for field, sorted_head in (("kcal_out", "burned"),
                               ("sleep_h", "hours slept"),
                               ("rir", "left in the tank"),
                               ("kcal_in", "calories")):
        assert sorted(aliases_for(field))[0] == sorted_head, field
        assert display_name("daily", field) != sorted_head, field


def test_the_name_is_still_a_word_people_use_for_it():
    """Not a licence to invent: the display name is the one the engine would
    use in its own prose, not a new coinage.

    EVERY FIELD WITH ALIASES, not the four I first hand-picked - which all
    passed, while five others did not. The client printed "maximum heart
    rate", the athlete typed it back, and the recognition index the same
    client was given did not contain it. `max_hr`, `kcal`, `elevation_m`,
    `reps_completed` and `grams` each gained the missing alias."""
    checked = 0
    for dataset in KEYS:
        for field in KEYS[dataset]:
            known = aliases_for(field)
            if not known:
                continue
            checked += 1
            assert display_name(dataset, field) in known, (field, known)
    # A floor, so the test cannot quietly stop checking anything: 33 today,
    # counted per (dataset, field) since a field can appear in two datasets.
    assert checked >= 33, checked


def test_it_is_not_the_unit_label():
    """`label` names the unit, and two different fields share one - which is
    exactly why a consumer cannot use it as a name."""
    assert units("daily", "kcal_in")["label"] == units("daily", "kcal_out")["label"]
    assert display_name("daily", "kcal_in") != display_name("daily", "kcal_out")


def test_a_plain_field_name_is_derived_rather_than_hand_written():
    """The other 135. A registry entry per field would be a second copy of the
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

def test_every_published_name_is_made_of_words_somebody_blessed():
    """THE CONTROL THAT MATTERS, because everything above is about today's
    fields and this is about tomorrow's.

    AN ALLOWLIST, after review killed the denylist with this test's own
    headline example. The first version listed abbreviations to reject, and
    `power_w` walked through it: "w" was not on a list built by auditing the
    fields that already exist. Fourteen of twenty plausible next fields
    passed. A denylist derived from today's field set is a list of what you
    already have, and the next field is the only thing a gate is for.

    Now a token must be one somebody decided a person would read. It fails
    CLOSED: a new field either gets a curated name or its words get added to
    `PLAIN_WORDS` deliberately.

    CHECKED ON THE PUBLISHED NAME, curated or derived. The first version
    skipped curated fields entirely - `if field in curated: continue` - so
    changing `seat_pos` to "seat pos" in the registry passed the whole suite,
    republishing one of the nine defects this PR cites as fixed."""
    from vitai.vocab import registry

    CURATED = set(registry("units").get("name", {}))
    offenders = []
    for dataset in KEYS:
        for field in KEYS[dataset]:
            shown = display_name(dataset, field)
            # DERIVED NAMES GET THE NARROWER LIST, and this cost a third
            # instance of the same defect to learn. The union blesses every
            # word a CURATED name introduces, including the unit letter in
            # "energy per 100 g" and the function words in "policy as of" - so
            # `alcohol_g` derived to "alcohol g" and the gate passed it,
            # exactly the `sodium_mg` class the allowlist replaced the
            # denylist to catch. A word earned by appearing inside a name
            # somebody wrote is not a word derivation may emit on its own.
            allowed = BLESSED if field in CURATED else PLAIN_WORDS
            for word in shown.replace(",", " ").split():
                if word.lower().strip(".") not in allowed:
                    offenders.append(f"{dataset}.{field} -> {shown!r} ({word!r})")
    assert not offenders, (
        "these would show a person a word nothing has blessed. Either add a "
        "[name] entry in semantics/units.toml, or add the word to "
        f"schema.PLAIN_WORDS on purpose: {sorted(set(offenders))}")


def test_the_gate_would_stop_the_fields_that_walked_through_the_old_one():
    """Named explicitly, because "it fails closed" is a claim about inputs
    that do not exist yet and is otherwise untestable."""
    from vitai.schema import PLAIN_WORDS

    for field in ("power_w", "weight_lb", "hrv_ms", "temp_c", "waist_cm",
                  "cal_burned", "bp_sys", "one_rm", "ftp_w", "ts_utc",
                  # And the ones the UNION let through before derived names
                  # got the narrower list. `alcohol_g` is not hypothetical:
                  # `daily.alcohol` exists and `carb_g`/`fat_g`/`sugar_g` set
                  # the convention.
                  "alcohol_g", "weight_g", "session_id", "as_of", "week_of"):
        shown = display_name("sessions", field)
        assert any(w.lower() not in PLAIN_WORDS for w in shown.split()), (
            f"{field} -> {shown!r} would ship unnoticed")
    for token in ("w", "ms", "g", "id", "of", "as"):
        assert token not in PLAIN_WORDS, token


def test_a_curated_name_may_not_restate_the_abbreviation_it_replaces():
    """The junk-entry hole. Review changed `seat_pos` to "seat pos" in the
    registry and the full suite stayed green."""
    from vitai.vocab import registry

    for field, name in registry("units").get("name", {}).items():
        for word in name.replace(",", " ").split():
            assert word.lower().strip(".") in BLESSED, (field, name, word)


def test_no_two_fields_of_one_dataset_show_the_same_name():
    """The PR's central argument, asserted. The whole case against
    `units.label` is that two fields answer "kilocalories" - so a display name
    that collided would reproduce the defect it exists to remove. It held by
    luck before this: setting `carb_g = "fat"` passed the whole suite."""
    for dataset in KEYS:
        shown = [display_name(dataset, f) for f in KEYS[dataset]]
        dupes = {n for n in shown if shown.count(n) > 1}
        assert not dupes, f"{dataset}: {sorted(dupes)}"


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


def test_the_fields_two_successive_audits_found(tmp_path):
    """A regression guard on the sixteen fields a token audit caught after my
    eyeballed list missed them, and the five review caught after the token
    audit could not - those are real words that are wrong in CONTEXT, which no
    token check finds. Reading the derived list is the only way."""
    assert display_name("sets", "rir") == "reps in reserve"
    assert display_name("meals", "sodium_mg") == "sodium"
    assert display_name("sets", "seat_pos") == "seat position"
    assert display_name("sessions", "with") == "trained with"
    assert display_name("regimes", "to_date") == "end date"
    assert display_name("goals", "slug") == "identifier"


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


def test_every_blessed_word_is_earned_by_a_name_that_exists():
    """BACK-PRESSURE on both lists, which review found had none.

    A word blessed for a field that later retires stays blessed forever, and
    the next field carrying it derives straight through. That is the rot that
    killed the abbreviation list this replaced - twenty-one of its thirty
    tokens were unwitnessed, because every field carrying them was curated,
    so the list was mostly decoration.

    Both directions are now closed: the gate above stops a name using a word
    nobody blessed, and this stops a word outliving the name that earned it."""
    from vitai.vocab import registry

    curated = registry("units").get("name", {})
    derived_words = {t for ds in KEYS for f in KEYS[ds] if f not in curated
                     for t in f.split("_")}
    curated_words = {w.lower().strip(".") for n in curated.values()
                     for w in str(n).replace(",", " ").split()}

    assert not (PLAIN_WORDS - derived_words), (
        "blessed for derivation but no field derives it: "
        f"{sorted(PLAIN_WORDS - derived_words)}")
    assert not (CURATED_WORDS - curated_words - PLAIN_WORDS), (
        "blessed for a curated name that no longer says it: "
        f"{sorted(CURATED_WORDS - curated_words - PLAIN_WORDS)}")
