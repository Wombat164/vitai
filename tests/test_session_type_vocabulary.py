"""Session types are published, so a client stops reinventing them (#350).

A client wiring its correction vocabulary to the engine's took the metric half
from `aliases` - a straight improvement, since it had hand-maintained `rhr` and
`resting` while the engine publishes "pulse" for the same field, so an athlete
typing "pulse 52" matched nothing from a client holding the answer in another
module. The activity half could not be wired the same way, because no surface
published the session types or the inflections a person types.

The SET already existed - `vocab.session_types` - and 47 of the 52 types
already carried aliases. What was missing was the surface.
"""

from __future__ import annotations

import json

from vitai.api import schema, session_types
from vitai.vocab import registry, resolve_session_type


# --- what it publishes ----------------------------------------------------------

def test_every_type_is_published_with_its_registry_label():
    got = session_types()
    types = registry("session_types")["types"]
    assert set(got) == set(types)
    for slug, entry in got.items():
        assert entry["label"] == (types[slug].get("label") or slug), slug


def test_what_it_publishes_is_a_copy_a_caller_cannot_corrupt():
    """The published lists reach clients that normalise vocabularies in place -
    lower-case, de-dupe, drop what they will not show. Handing back the
    registry's own list means one such caller rewrites the engine's resolver
    for the rest of the process, with nothing raised."""
    got = session_types()
    got["run"]["aliases"].append("invented by a consumer")
    got["run"]["myfitnesspal"].append("also invented")
    for entry in session_types().values():
        entry.get("myfitnesspal", []).clear()

    assert resolve_session_type("invented by a consumer") is None
    assert resolve_session_type("also invented") is None
    assert resolve_session_type("swimming laps, freestyle, light/moderate effort") == "swim"
    assert session_types()["run"]["aliases"] == ["running", "jog", "jogging",
                                                 "ran", "jogged"]


# --- the inflections ------------------------------------------------------------

# Verbatim from the issue: the list a client is forced to invent today. It is
# the acceptance criterion, so it is written out rather than derived from the
# registry - a list built from what the registry holds would pass by
# construction and could never catch a dropped spelling.
INVENTED_BY_EVERY_CLIENT = {
    "run": ["run", "ran", "running", "jog", "jogged"],
    "cycle": ["cycle", "cycled", "cycling", "ride", "rode", "bike", "biked"],
    "swim": ["swim", "swam", "swimming"],
    "row": ["row", "rowed", "rowing"],
}


def test_every_spelling_the_issue_names_resolves():
    for slug, written in INVENTED_BY_EVERY_CLIENT.items():
        for word in written:
            assert resolve_session_type(word) == slug, word


def test_every_spelling_the_issue_names_is_also_published():
    """Resolving is not enough. A client reads the surface to build its own
    parser, so a spelling the engine matches but does not publish is one the
    client keeps inventing - which is the whole complaint."""
    got = session_types()
    for slug, written in INVENTED_BY_EVERY_CLIENT.items():
        published = {slug, *got[slug]["aliases"]}
        assert set(written) <= published, (slug, set(written) - published)


# Every past-tense spelling this engine publishes, written out. Not derived
# from the registry: a register built from what the registry holds passes by
# construction and cannot notice a dropped word. 18 of the first 29 were
# pinned by nothing, so deleting `climbed` broke no test.
PAST_TENSE = {
    "run": ["ran", "jogged"],
    "walk": ["walked"],
    "cycle": ["cycled", "rode", "biked"],
    "swim": ["swam", "swum"],
    "row": ["rowed"],
    "hike": ["hiked", "trekked"],
    "climb": ["climbed"],
    "strength": ["lifted"],
    "paddle": ["paddled"],
    "sail": ["sailed"],
    "surfing": ["surfed"],
    "golf": ["golfed"],
    "kayaking": ["kayaked"],
    "canoeing": ["canoed"],
    "snowboard": ["snowboarded"],
    "skateboard": ["skateboarded"],
    "windsurf": ["windsurfed"],
    "kitesurf": ["kitesurfed"],
    "snowshoe": ["snowshoed"],
    "mobility": ["stretched"],
    "ice_skate": ["ice skated"],
    "inline_skate": ["rollerbladed"],
    "wintersport": ["skied", "skated"],
    "trail_run": ["trail ran"],
    "mountain_bike_ride": ["mountain biked"],
    "stand_up_paddling": ["paddleboarded"],
}


def test_every_published_past_tense_resolves_to_its_type():
    for slug, words in PAST_TENSE.items():
        for word in words:
            assert resolve_session_type(word) == slug, word


def test_every_published_past_tense_is_also_offered():
    got = session_types()
    for slug, words in PAST_TENSE.items():
        assert set(words) <= set(got[slug]["aliases"]), slug


def test_no_type_conjugates_a_verb_nobody_says():
    """The register is the whole permitted set, so an `-ed` word added to any
    type without being written down here fails. The earlier control listed
    five slugs to check, three of which carry no aliases at all - so it
    asserted nothing for those, passed with `soccered` added to `soccer`, and
    omitted `golf`, the one type that would have failed it."""
    allowed = {w for words in PAST_TENSE.values() for w in words}
    for slug, entry in session_types().items():
        for alias in entry["aliases"]:
            if alias.endswith("ed"):
                assert alias in allowed, (slug, alias)


def test_the_past_tense_exists_at_all():
    """No type carried one before #350: "running" resolved, "ran" did not, so
    the issue's headline example was the one that failed."""
    assert resolve_session_type("ran") == "run"
    assert resolve_session_type("swam") == "swim"
    assert resolve_session_type("walked") == "walk"
    assert resolve_session_type("lifted") == "strength"


def test_an_ambiguous_form_lands_where_its_present_tense_already_did():
    """`skated` cannot tell ice from inline and `skied` cannot tell alpine
    from nordic, so both go to the coarse type - which is where the registry
    was already sending `skating` and `ski` before this. Following that
    precedent rather than inventing a second rule for the past tense."""
    for present, past in (("skating", "skated"), ("ski", "skied")):
        assert resolve_session_type(past) == resolve_session_type(present)
        assert resolve_session_type(past) == "wintersport"
    assert resolve_session_type("ice skated") == "ice_skate"
    assert resolve_session_type("rollerbladed") == "inline_skate"


def test_the_aliases_are_not_english_only():
    """Stated because the docstring used to claim the opposite. Five words
    rather than a policy - but "English-only" is a checkable claim and it was
    false."""
    for word, slug in (("schaatsen", "ice_skate"), ("voetbal", "soccer"),
                       ("velomobiel", "velomobile"), ("langlauf", "nordic_ski"),
                       ("randonnee", "backcountry_ski")):
        assert resolve_session_type(word) == slug, word


# --- recognition is not an offer list -------------------------------------------

# A person says a short phrase. A vendor emits a catalogue row: it qualifies,
# punctuates, and quantifies - "swimming laps, freestyle, light/moderate
# effort". This is a SHAPE rule, and it is written as what an alias may be
# rather than what it may not, because the first version of this control was a
# denylist of the three substrings present in the eight strings being moved
# ("myfitnesspal", "mph", "min mile"). That could only ever catch the eight
# already fixed: putting "swimming laps, freestyle, light/moderate effort" back
# into `aliases` passed it, and it is one of the eight. A denylist drawn from
# today's offenders is a list of what you already have.
MAX_WORDS = 3
FORBIDDEN_PUNCTUATION = ",()/;:"
# Digits are out, with one witnessed exception. Back-pressure both ways: if
# this entry loses its witness the test fails and the exception goes.
ALIASES_THAT_MAY_CARRY_A_DIGIT = {"concept2"}


def test_an_alias_has_the_shape_of_something_a_person_says():
    """#331's lesson one vocabulary over: `aliases` is published as what a
    person calls this, so a client offering suggestions from it must not be
    offered "running (jogging), 9 mph (6.5 min mile)"."""
    for slug, entry in session_types().items():
        for alias in entry["aliases"]:
            assert not any(c in alias for c in FORBIDDEN_PUNCTUATION), (slug, alias)
            assert len(alias.split()) <= MAX_WORDS, (slug, alias)
            if any(c.isdigit() for c in alias):
                assert alias in ALIASES_THAT_MAY_CARRY_A_DIGIT, (slug, alias)


def test_every_digit_bearing_exception_still_has_a_witness():
    published = {a for e in session_types().values() for a in e["aliases"]}
    assert ALIASES_THAT_MAY_CARRY_A_DIGIT <= published


def test_the_shape_rule_rejects_a_vendor_string_it_has_never_seen():
    """The point of a shape rule: it must catch the NEXT vendor, not the one
    that prompted it. None of these is in the registry."""
    for invented in ("aerobics, general",
                     "stationary bike, moderate effort (bicycling)",
                     "walking, 3.5 mph, level, brisk"):
        assert (any(c in invented for c in FORBIDDEN_PUNCTUATION)
                or len(invented.split()) > MAX_WORDS), invented


def test_the_vendor_tokens_are_published_under_the_vendors_own_name():
    """Where `strava` and `healthkit` already lived. The distinction is DATA -
    a named field the registry declares in `alias_fields` - rather than a
    regex over a suffix, which would be a second classification drifting from
    the first."""
    run = session_types()["run"]
    assert run["strava"] == ["Run"]
    assert any("mph" in s for s in run["myfitnesspal"]), run
    assert "myfitnesspal" in registry("session_types")["alias_fields"]


def test_moving_them_did_not_stop_them_resolving():
    """The load-bearing half: an import that hands over the vendor's exact
    string must still match, or the move would have broken every MyFitnessPal
    activity to fix a display list."""
    assert resolve_session_type(
        "Running (jogging), 9 mph (6.5 min mile)") == "run"
    assert resolve_session_type(
        "swimming laps, freestyle, light/moderate effort") == "swim"
    assert resolve_session_type("jogging") == "run"


def test_an_alias_field_may_hold_several_spellings():
    """`_index` read ONE value per alias field, which was enough while every
    such field held one vendor token. MyFitnessPal ships three for `run`, by
    effort, so they had nowhere to go but `aliases`."""
    assert len(session_types()["run"]["myfitnesspal"]) == 3
    for spelling in session_types()["run"]["myfitnesspal"]:
        assert resolve_session_type(spelling) == "run", spelling


# --- P9: the same answer on every surface ---------------------------------------

def test_it_reaches_the_published_schema():
    assert schema()["session_types"] == session_types()


def test_it_reaches_the_cli_and_the_agent_surface(tmp_path):
    """By the route `fields` already uses - a separate accessor would be a new
    place for parity to fail (#257)."""
    import contextlib
    import io

    from vitai.cli import main
    from vitai.mcp import call

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["schema", "--json"])
    assert json.loads(buf.getvalue())["session_types"] == session_types()

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    assert call(root, "schema", {})["session_types"] == session_types()


def test_a_client_reads_both_vocabularies_with_one_shape():
    """The issue's ask: "the same map one vocabulary over, so a client reads
    both with one code path"."""
    fields = schema()["fields"]["daily"]["rhr"]
    types = schema()["session_types"]["run"]
    assert isinstance(fields["aliases"], list)
    assert isinstance(types["aliases"], list)


# --- a relay composes its own name into the vendor's string (#390) -------------


def test_a_relayed_vendor_string_resolves_like_the_direct_one():
    """THE REGRESSION #390 REPORTS. When a third-party app writes an exercise
    to Fitbit, the Fitbit account export records the attribution INSIDE
    `activityName` - so the archive holds "walking, general (MyFitnessPal)"
    where the direct export holds "walking, general".

    The vocabulary change that moved these eight strings under `myfitnesspal`
    reasoned that "the vendor's export does not carry it and nothing here
    composes one". Something does, so both spellings are real and dropping
    either one reverts sessions to `other` on the next re-import.
    """
    from vitai.vocab import resolve_session_type

    for direct, relayed in (
        ("walking, general",
         "Walking, general (MyFitnessPal)"),
        ("running (jogging), 9 mph (6.5 min mile)",
         "Running (jogging), 9 mph (6.5 min mile) (MyFitnessPal)"),
        ("stationary bike, moderate effort (bicycling, cycling, biking)",
         "Stationary bike, moderate effort (bicycling, cycling, biking) (MyFitnessPal)"),
        ("strength training (weight lifting, weight training)",
         "Strength training (weight lifting, weight training) (MyFitnessPal)"),
    ):
        assert resolve_session_type(direct) is not None, direct
        assert resolve_session_type(relayed) == resolve_session_type(direct)


def test_only_a_declared_source_is_stripped():
    """THE SCOPE, and the whole difference between this and a regex over a
    suffix - which is what the change that caused #390 rightly wanted to
    avoid.

    Two of the registry's own alias strings END in parentheses that are part
    of the name. If the rule stripped any trailing group they would stop
    resolving, which would be a worse regression than the one being fixed.
    """
    from vitai.vocab import resolve_session_type

    assert resolve_session_type(
        "running (jogging), 9 mph (6.5 min mile)") == "run"
    assert resolve_session_type(
        "bicycling, 12-14 mph, moderate (cycling, biking, bike riding)") == "cycle"
    # A trailing group naming nothing the registries know is left alone, so an
    # unrecognised activity stays unrecognised rather than being truncated
    # into a match.
    assert resolve_session_type("Competitive Zorbing (Blorbo)") is None


def test_the_relay_rule_never_overrides_a_declared_value():
    """Ordered last in `resolve`, so a string a registry declares outright can
    never be reinterpreted through its parentheses. A vocabulary that changes
    what an existing declared value means is not a widening."""
    from vitai.vocab import resolve, resolve_session_type

    assert resolve_session_type("walking, general") == "walk"
    # The sources registry itself is exempt: it would recurse, and a source
    # name does not carry a relay attribution because the relay IS a source.
    assert resolve("sources", "sources", "MyFitnessPal") == "myfitnesspal"


def test_a_declined_proposal_stays_declined_through_the_relay_form():
    """`Elliptical, High Resistance` proposed `strength` off the word
    Resistance and was declined. Arriving via a relay must not smuggle it in:
    the rule removes an attribution, it does not soften matching."""
    from vitai.vocab import resolve_session_type

    assert resolve_session_type("Elliptical, High Resistance") is None
    assert resolve_session_type(
        "Elliptical, High Resistance (MyFitnessPal)") is None
