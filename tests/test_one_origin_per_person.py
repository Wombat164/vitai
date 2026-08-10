"""The athlete is one origin (#94).

Chat, calendar, photo and receipt are one witness, not four - and the engine
counted four. Measured before the change, with the athlete's OWN declared
aliases: `me`, `self`, `manual` and `spreadsheet` all resolve to `athlete` in
`semantics/sources.toml`, and `independent_witnesses` reported **4** for one
person saying one thing four ways.

The mirror error is just as wrong and the issue is explicit about it: a console
figure transcribed from a photograph is NOT the athlete's observation. The
instrument observed it and the athlete carried it, and collapsing those would
under-count real corroboration.

THE DISCRIMINATOR IS ALREADY IN THE RECORD. Contract 40 drew the line in as
many words: `source` is the channel a value arrived by, `origin` is the
instrument that observed it. So a conduit claim names an instrument and is
counted by it; a claim with no instrument behind it, from a person, is that
person's own observation. No new field, no new vocabulary.

The conduit half already worked before this change - measured: a console
photograph beside a watch export reported two witnesses, and a watch
photograph beside that watch's own export reported one. What was broken was
only the person half.
"""

from __future__ import annotations

from vitai.provenance import (
    PERSON,
    independent_witnesses,
    resolve_source,
    source_kind,
)


def rec(source: str | None, origin: str | None = None, **kw) -> dict:
    return {"source": source, "origin": origin, "date": "2030-05-01", **kw}


# --- the person half, which was wrong ------------------------------------------

def test_one_person_writing_it_four_ways_is_one_witness():
    """The issue's case, in the athlete's own declared spellings."""
    four = [rec("stated-in-chat"), rec("spreadsheet"), rec("notebook"), rec("me")]
    assert independent_witnesses(four) == 1


def test_every_alias_of_the_athlete_folds_onto_the_athlete():
    """Not a hand-picked few: whatever the registry declares as the athlete
    counts as the athlete, so adding a spelling there cannot reopen this."""
    from vitai.vocab import registry

    entry = registry("sources")["sources"]["athlete"]
    aliases = list(entry.get("aliases") or [])
    assert len(aliases) >= 5, aliases
    assert independent_witnesses([rec(a) for a in aliases]) == 1


def test_two_different_people_are_two_witnesses():
    """The mirror error. The athlete saying they felt tired and a clinician
    recording the same IS corroboration - folding all people together would
    delete it."""
    assert independent_witnesses([rec("me"), rec("gp")]) == 2
    assert source_kind("gp") == PERSON and resolve_source("gp") == "clinician"


def test_a_person_saying_it_twice_does_not_become_two():
    assert independent_witnesses([rec("athlete"), rec("athlete")]) == 1


# --- the conduit half, which already worked and must keep working --------------

def test_a_transcribed_instrument_is_the_instrument_not_the_athlete():
    """A console figure photographed by the athlete is the console's
    observation. This is the under-counting error the issue warns about, and
    it passed before the change - pinned so the person rule cannot swallow
    it."""
    got = independent_witnesses([rec("photo", origin="matrix-rower"),
                                 rec("polar-api", origin="polar-watch")])
    assert got == 2


def test_two_athlete_channels_naming_one_device_are_one_witness():
    """The part that makes the rule safe rather than a new hole: a photograph
    of the watch plus the watch's own export is one instrument seen twice."""
    got = independent_witnesses([rec("photo", origin="polar-watch"),
                                 rec("polar-api", origin="polar-watch")])
    assert got == 1


def test_naming_an_instrument_beats_being_a_person():
    """A person channel that DOES name an instrument is a conduit, and is
    counted by the instrument - otherwise the fix above would erase the
    corroboration the issue is trying to protect."""
    photo = rec("stated-in-chat", origin="matrix-rower")
    watch = rec("polar-api", origin="polar-watch")
    assert independent_witnesses([photo, watch]) == 2


# --- what the record cannot tell apart ----------------------------------------

def test_a_transcription_that_names_no_instrument_asserts_no_independence():
    """The issue's remaining case: where a transcription cannot name what it
    transcribed, the record cannot tell it from the athlete's own observation.

    Both readings get the same answer and it is the safe one. If it IS their
    observation, one athlete witness is right. If it is an unnamed
    transcription, no second instrument is credited and combined confidence
    cannot exceed the best single source - which is what the issue asks for in
    the case it says the record cannot resolve."""
    assert independent_witnesses([rec("me"), rec("stated-in-chat")]) == 1
    # And it does not suppress a real instrument standing beside it.
    assert independent_witnesses(
        [rec("me"), rec("polar-api", origin="polar-watch")]) == 2


def test_two_uncatalogued_channels_stay_two():
    """The person rule folds PEOPLE, not strangers. Two unrecognised sources
    are not evidence of one another, and merging them would assert a shared
    origin nobody stated."""
    assert independent_witnesses([rec("some-app"), rec("another-app")]) == 2


def test_instruments_are_untouched():
    assert independent_witnesses([rec("polar-api"), rec("garmin-connect")]) == 2


# --- what review found the first fold walked around --------------------------

def test_an_uncatalogued_person_name_does_not_collapse_onto_the_catchall():
    """`[kinds.person]` declares aliases the SOURCE catalogue does not, so a
    source spelled `human` or `person` has a person KIND while resolving to
    the `other` sentinel. The first fold sent it there, merging two unrelated
    strangers with each other AND with the catalogue's real catchall - which
    is `kind = unknown`, not a person at all.

    `test_two_uncatalogued_channels_stay_two` above states the rule and the
    fold walked around it, because the two strings it picks happen not to trip
    the kind fallback."""
    from vitai.provenance import CATALOG_OTHER, resolve_source, source_kind

    for spelling in ("human", "person"):
        assert source_kind(spelling) == PERSON, spelling
        assert resolve_source(spelling) == CATALOG_OTHER, spelling

    assert independent_witnesses([rec("human"), rec("person")]) == 2
    assert independent_witnesses([rec("human"), rec("other")]) == 2


def test_a_derivation_naming_one_person_by_another_spelling_is_one_witness(tmp_path):
    """The lineage path, which the first fix missed entirely.

    `independent_witnesses` compares `derived_from` references - which embed a
    source - against the plain rows' sources, and BOTH sides used the raw
    string. So the issue's own bug survived here after the plain path was
    fixed: a derivation whose lineage names `me`, beside a plain row written
    `self`, counted two witnesses for one person."""
    lineage = rec("derived", derived_from=["weight:2030-05-01:me"])
    plain = rec("self")
    assert independent_witnesses([lineage, plain]) == 1
    # And a derivation naming a real instrument still corroborates.
    other = rec("derived", derived_from=["weight:2030-05-01:polar-api"])
    assert independent_witnesses([other, plain]) == 2


def test_a_conduit_row_occupies_the_person_s_channel(tmp_path):
    """The behaviour review called an under-count, pinned as deliberate.

    A person's conduit row DOES occupy that person's channel, so their own
    unattributed figure beside it adds no witness. That is #211's rule - an
    anonymous row on a channel already represented is the same delivery - and
    it is what the issue asks for where a transcription cannot name what it
    transcribed. Restricting the fold to rows with no instrument breaks
    `test_source_counting.test_a_correction_does_not_inflate_the_evidence`."""
    assert independent_witnesses(
        [rec("stated-in-chat", origin="withings-scale"), rec("me")]) == 1
    # A DIFFERENT person's claim is still a second witness.
    assert independent_witnesses(
        [rec("stated-in-chat", origin="withings-scale"), rec("gp")]) == 2
