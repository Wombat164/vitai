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

def test_every_type_carries_a_label_and_its_names():
    got = session_types()
    assert len(got) == len(registry("session_types")["types"])
    for slug, entry in got.items():
        assert entry["label"], slug
        assert isinstance(entry["aliases"], list), slug


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


def test_the_past_tense_is_there_at_all():
    """No type carried one before #350: "running" resolved, "ran" did not, so
    the issue's headline example was the one that failed."""
    assert resolve_session_type("ran") == "run"
    assert resolve_session_type("swam") == "swim"
    assert resolve_session_type("walked") == "walk"
    assert resolve_session_type("lifted") == "strength"


def test_an_ambiguous_past_tense_is_left_out_on_purpose():
    """A bare "skated" cannot choose between ice and inline, so it resolves to
    neither rather than silently picking whichever the index saw first."""
    assert resolve_session_type("skated") is None
    assert resolve_session_type("ice skated") == "ice_skate"
    assert resolve_session_type("rollerbladed") == "inline_skate"


def test_a_game_you_play_gets_no_invented_verb():
    """Past tense was added where the type names something a person DOES.
    "tennised" is not a word, and a vocabulary that contains it is one nobody
    can trust to be about how people speak."""
    for slug in ("tennis", "badminton", "squash", "yoga", "pilates"):
        for alias in session_types()[slug]["aliases"]:
            assert not alias.endswith("ed"), (slug, alias)


def test_the_aliases_are_not_english_only():
    """Stated because the docstring used to claim the opposite. Five words
    rather than a policy - but "English-only" is a checkable claim and it was
    false."""
    for word, slug in (("schaatsen", "ice_skate"), ("voetbal", "soccer"),
                       ("velomobiel", "velomobile"), ("langlauf", "nordic_ski")):
        assert resolve_session_type(word) == slug, word


# --- recognition is not an offer list -------------------------------------------

def test_a_vendor_export_string_is_not_something_a_person_says():
    """#331's lesson one vocabulary over. Eight MyFitnessPal export strings sat
    in `aliases` - the list published as "what a person calls this" - so a
    client offering suggestions from it would have offered "running (jogging),
    9 mph (6.5 min mile)"."""
    for entry in session_types().values():
        for alias in entry["aliases"]:
            assert "myfitnesspal" not in alias, entry
            assert "mph" not in alias and "min mile" not in alias, entry


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
