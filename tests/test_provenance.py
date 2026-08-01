"""Provenance is a chain, and corroboration requires divergent origins (#35/#51).

Synthetic data only (public repo), fictional athlete, 2030 dates.

The mistake under test, in one line: **an activity present in both Polar and
Strava is one measurement seen twice, not two measurements agreeing.**

The sharpest evidence is an inversion. On a real record, `fitbit-api` and
`mfp-export` agreed to 13 g across 52 days - because one fed the other - while
the only genuinely independent pair had sd 0.342 and a 1.67 kg outlier. The
useless comparison was the clean one and the informative comparison was the
noisy one, which is exactly backwards from how the output read.
"""

import json

import pytest

from vitai import vocab
from vitai.api import Vitai
from vitai.cli import main
from vitai.provenance import (capture_of, capture_problems, describe,
                              has_artifact, hops, independent_witnesses,
                              is_independent, may_mutate, may_transcribe,
                              role_of, shares_origin, trust_ceiling)
from vitai.schema import validate_record


def weight(date="2030-05-01", kg=80.0, source="scale", **kw):
    rec = {"date": date, "kg": kg, "source": source, "note": None,
           "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
           "body_fat_lo": None, "body_fat_hi": None, "measured_at": None,
           "recorded_at": None, "origin": None, "path": None,
           "origin_evidence": None, "_gen": 4}
    rec.update(kw)
    return rec


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, rows):
    (root / "data" / "weight.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- the chain -----------------------------------------------------------------

def test_a_path_is_an_ordered_list_of_hops():
    assert hops("fitbit-app>fitbit-api>mfp-export") == [
        "fitbit-app", "fitbit-api", "mfp-export"]
    assert hops(None) == []
    assert hops("  ") == []


def test_an_unrecognised_hop_is_assumed_to_mutate():
    """Roles, not vendors: listing platforms would be a sample of the ones
    this author happens to use. A stranger hop is handled by assuming it MIGHT
    have changed the value, because assuming lossless is what costs something.
    """
    # A name whose last token says nothing - "platform" WOULD have resolved,
    # via the role suffix rule, which is the point of picking one that does not.
    assert role_of("acme-widget") == "unknown"
    assert may_mutate("acme-widget") is True
    assert role_of("export") == "export"
    assert may_mutate("export") is True
    assert may_mutate("watch") is False


def test_trust_is_bounded_by_the_weakest_hop_not_the_origin():
    """A device-measured weight that passed through a vendor which rounds,
    re-derives or back-fills is no longer device-measured, however good the
    device was."""
    assert trust_ceiling(weight(origin="aria-scale")) == "device-measured"
    assert trust_ceiling(weight(origin="aria-scale", path="watch")) == (
        "device-measured")
    assert trust_ceiling(weight(origin="aria-scale", path="watch>export")) == (
        "derived-in-transit")
    assert trust_ceiling(weight(origin="aria-scale", path="mystery-hop")) == (
        "unknown-transit")


def test_an_unstated_origin_cannot_be_trusted_as_device_measured():
    assert trust_ceiling(weight()) == "unknown-transit"


def test_describe_reads_as_a_chain():
    assert describe(weight(origin="aria-scale")) == "aria-scale, direct"
    assert describe(weight(origin="aria-scale", path="watch>export")) == (
        "aria-scale -> watch (device) -> export (export)")


# ---- corroboration requires divergent origins ----------------------------------

def test_two_points_on_one_pipe_are_one_witness():
    """N platforms carrying one device's file is still N=1. Reporting more is
    the false confidence the whole model exists to prevent."""
    relayed = [weight(source="fitbit-api", origin="aria-scale", path="app>api"),
               weight(source="mfp-export", origin="aria-scale",
                      path="app>api>mfp-api>mfp-export")]
    assert independent_witnesses(relayed) == 1
    assert shares_origin(*relayed) is True


def test_two_instruments_are_two_witnesses():
    independent = [weight(source="fitbit-api", origin="aria-scale", path="app>api"),
                   weight(source="hand", origin="athlete")]
    assert independent_witnesses(independent) == 2
    assert shares_origin(*independent) is False


def test_an_unknown_origin_never_counts_as_independent():
    """The guard that stops a Google Takeout import - where the originating
    device is frequently lost - from manufacturing corroboration out of
    missing data."""
    assert is_independent(weight(origin="unknown")) is False
    assert is_independent(weight(origin=None)) is False
    assert shares_origin(weight(origin="unknown"), weight(origin="unknown")) is False


def test_an_unannotated_record_still_counts_each_row():
    """A record with no provenance at all had one observation per row as far
    as anyone can tell. Merging them would silently rewrite a legitimately
    un-annotated history."""
    assert independent_witnesses([weight(), weight()]) == 2


# ---- what the resolver reports --------------------------------------------------

def test_a_relayed_pair_is_labelled_pipeline_fidelity(tmp_path):
    """THE test for this increment. The 20 g between these two measures
    rounding in transit and says nothing about whether the weight is right."""
    root = repo(tmp_path)
    write(root, [weight(kg=80.00, source="fitbit-api", origin="aria-scale",
                        path="app>api"),
                 weight(kg=80.02, source="mfp-export", origin="aria-scale",
                        path="app>api>mfp-api>mfp-export")])
    rows = [e for e in Vitai(root).explanations() if e["field"] == "kg"]
    assert len(rows) == 1
    assert rows[0]["witnesses"] == 1
    assert rows[0]["independent"] is False
    assert rows[0]["compares"] == "pipeline fidelity"


def test_an_independent_pair_is_labelled_as_such(tmp_path):
    """And it is the NOISY one - 400 g apart, against the relay's 20 g."""
    root = repo(tmp_path)
    write(root, [weight(kg=79.90, source="fitbit-api", origin="aria-scale",
                        path="app>api"),
                 weight(kg=80.30, source="hand", origin="athlete")])
    rows = [e for e in Vitai(root).explanations() if e["field"] == "kg"]
    assert rows[0]["witnesses"] == 2
    assert rows[0]["independent"] is True
    assert rows[0]["compares"] == "independent observations"


def test_provenance_is_not_adjudicated_as_if_it_were_a_quantity(tmp_path):
    """`origin` and `path` describe where a value came FROM. Resolved by the
    precedence ladder they were reported as contested fields whose sources
    'disagreed' - true, and meaningless: of course two chains differ, that is
    what makes them two chains."""
    root = repo(tmp_path)
    write(root, [weight(source="fitbit-api", origin="aria-scale", path="app>api"),
                 weight(source="hand", origin="athlete")])
    contested = {e["field"] for e in Vitai(root).explanations()}
    assert not contested & {"origin", "path", "origin_evidence"}


def test_the_provenance_table_reports_independence_and_trust(tmp_path):
    root = repo(tmp_path)
    write(root, [weight(kg=80.0, source="fitbit-api", origin="aria-scale",
                        path="app>api"),
                 weight(kg=80.02, source="mfp-export", origin="aria-scale",
                        path="app>api>mfp-api>mfp-export"),
                 weight(date="2030-05-02", kg=79.9, source="hand",
                        origin="athlete")])
    rows = {r["date"]: r for r in Vitai(root).provenance()}
    assert rows["2030-05-01"]["independent_sources"] == 1
    assert rows["2030-05-01"]["trust"] == "derived-in-transit"
    assert rows["2030-05-02"]["independent_sources"] == 1
    assert rows["2030-05-02"]["trust"] == "device-measured"


def test_a_merged_row_records_no_single_path(tmp_path):
    """A merged row has as many paths as it had claims. Putting one of them on
    the row would assert a journey this value did not solely take; the full
    set lives in `provenance.chain`."""
    root = repo(tmp_path)
    write(root, [weight(source="fitbit-api", origin="aria-scale", path="app>api"),
                 weight(source="hand", origin="athlete")])
    row = Vitai(root).canonical("weight")[0]
    assert row["path"] is None
    assert row["origin"] == "aria-scale+athlete"
    chain = Vitai(root).provenance()[0]["chain"]
    assert "aria-scale" in chain and "athlete" in chain


def test_a_single_claim_keeps_its_own_chain(tmp_path):
    root = repo(tmp_path)
    write(root, [weight(source="fitbit-api", origin="aria-scale", path="app>api",
                        origin_evidence="TCX Creator: Aria")])
    row = Vitai(root).canonical("weight")[0]
    assert row["path"] == "app>api"
    assert row["origin_evidence"] == "TCX Creator: Aria"


# ---- validation ------------------------------------------------------------------

def test_a_path_needs_an_origin_to_have_travelled_from():
    problems = validate_record("weight", weight(path="app>api"))
    assert any("origin" in p for p in problems)


def test_a_legacy_row_without_provenance_still_validates():
    """G25 on four datasets at once: nothing that predates this is invalid."""
    legacy = {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None}
    assert validate_record("weight", legacy) == []


def test_a_vendor_prefixed_hop_resolves_by_its_role_suffix():
    """Real hops are named for their vendor. A bare-role lookup alone would
    classify almost every real chain as unknown, and a trust signal that is
    always "unknown" tells nobody anything."""
    assert role_of("fitbit-api") == "api"
    assert role_of("mfp-export") == "export"
    assert role_of("garmin_watch") == "device"
    assert role_of("mystery-hop") == "unknown", "a name that says nothing stays unknown"


def test_a_real_relay_chain_reads_as_derived_in_transit():
    assert trust_ceiling(weight(
        origin="aria-scale",
        path="fitbit-app>fitbit-api>mfp-api>mfp-export")) == "derived-in-transit"


# ---- #77/#78: how a value was acquired -----------------------------------------

def test_capture_resolves_through_the_registry_with_aliases():
    assert capture_of({"capture": "photo"}) == "photo"
    assert capture_of({"capture": "screenshot"}) == "photo"
    assert capture_of({"capture": "bluetooth"}) == "ble"
    assert capture_of({"capture": "stated-in-chat"}) == "narrative"


def test_an_unrecognised_capture_lands_in_unknown():
    """A capture method nobody here imagined is a gap in the registry, not a
    fault in the athlete's record - and `unknown` already assumes the costly
    side of both properties."""
    assert capture_of({"capture": "telepathy"}) == "unknown"
    assert may_transcribe({"capture": "telepathy"}) is True
    assert has_artifact({"capture": "telepathy"}) is False


def test_the_ordering_is_not_a_quality_ranking():
    """`ble` has no human in the loop and no durable artifact; `photo` has a
    reader in the loop but the evidence SURVIVES and can be re-read. Two
    different virtues, and a query must be able to ask for either."""
    assert may_transcribe({"capture": "ble"}) is False
    assert has_artifact({"capture": "ble"}) is False
    assert may_transcribe({"capture": "photo"}) is True
    assert has_artifact({"capture": "photo"}) is True


def test_a_transcribing_capture_must_say_who_read_it():
    """A photo read by nobody is an unattributed reading; a photo read by a
    MODEL is an inference over an artifact rather than a measurement, which
    is the whole reason the field exists."""
    assert any("read_by" in p for p in capture_problems({"capture": "photo"}))
    assert capture_problems({"capture": "photo", "read_by": "model"}) == []
    assert any("read_by" in p for p in
               capture_problems({"capture": "photo", "read_by": "the cat"}))


def test_a_non_transcribing_capture_needs_no_reader():
    assert capture_problems({"capture": "ble"}) == []
    assert capture_problems({"capture": "connector"}) == []


def test_a_transcription_is_not_device_measured():
    """The acquisition bounds the value just as a hop does. The origin is
    still the console; what changes is what can be claimed about the number.
    """
    console = {"origin": "gym-console", "path": None}
    assert trust_ceiling(console) == "device-measured"
    assert trust_ceiling({**console, "capture": "ble"}) == "device-measured"
    assert trust_ceiling({**console, "capture": "photo",
                          "read_by": "model"}) == "transcribed"
    assert trust_ceiling({**console, "capture": "narrative",
                          "read_by": "athlete"}) == "transcribed"


def test_absent_capture_changes_nothing():
    """No importer is required to set it, and guessing it for a record's
    history would manufacture provenance - the thing this line of work
    exists to prevent."""
    console = {"origin": "gym-console", "path": None}
    assert "capture" not in console
    assert trust_ceiling(console) == "device-measured"


def test_sessions_finally_carry_the_chain():
    """`origin`/`path`/`origin_evidence` landed on weight, daily and
    measurements in #51 and were never extended to sessions - which is
    exactly where multi-instrument claims collide."""
    from vitai.schema import KEYS
    for key in ("origin", "path", "origin_evidence", "capture", "read_by"):
        assert key in KEYS["sessions"], key


def test_one_origin_two_acquisitions_are_two_claims():
    """A photo-read and a BLE-read of one console on one evening share an
    origin and a path, and differ only in capture. That is why capture is a
    field rather than another hop."""
    photo = {"origin": "gym-console", "path": None, "capture": "photo",
             "read_by": "model"}
    link = {"origin": "gym-console", "path": None, "capture": "ble"}
    assert shares_origin(photo, link) is True
    assert capture_of(photo) != capture_of(link)
    assert trust_ceiling(photo) != trust_ceiling(link)


def test_a_transcription_cannot_mask_a_worse_condition():
    """Returning "transcribed" early let it hide a weaker signal: a photo
    with no origin at all, or a chain containing a hop nobody recognises,
    claimed more than the row deserved - this module's own weakest-link rule
    used against itself."""
    assert trust_ceiling({"capture": "photo", "read_by": "model"}) == (
        "unknown-transit"), "no origin is worse than a transcription"
    assert trust_ceiling({"origin": "gym-console", "path": "acme-widget",
                          "capture": "photo", "read_by": "model"}) == (
        "unknown-transit"), "an unrecognised hop is worse than a transcription"


def test_a_reader_needs_something_to_have_read():
    """The mirror of "a path needs an origin to have travelled from"."""
    assert any("capture" in p for p in capture_problems({"read_by": "model"}))


def test_a_row_at_the_previous_generation_still_validates():
    """The G25 property, stated as what it protects rather than as generation
    arithmetic.

    #51 had already consumed a generation for `sessions` without adding the
    columns, so an existing deployment's `append` was stamping rows with it.
    Reusing that number would have made every one of those rows owe five keys
    it cannot have - the time bomb, arriving through a restructuring rather
    than through a new field.

    Anchored to the generation the CAPTURE FIELDS landed on rather than to
    `CURRENT_GENERATION`, which moves every time any later change adds a
    field. Pinned to a moving target this breaks on the next unrelated
    increment, saying nothing about the property it exists to protect.
    """
    from vitai.schema import KEYS, key_generation, validate_record
    landed = key_generation("sessions", "capture")
    row = {k: None for k in KEYS["sessions"]
           if key_generation("sessions", k) < landed}
    row.update({"date": "2030-05-01", "type": "run", "_gen": landed - 1})
    assert validate_record("sessions", row) == [], (
        "a row stamped at the generation before this change must not "
        "suddenly owe the fields this change adds")


def test_the_catalog_normalises_spellings():
    """Its job is that `Polar Pacer Pro`, `polar-pacer-pro` and `PacerPro` are
    one thing - a NORMALIZER, not a constraint."""
    from vitai.provenance import resolve_source
    for written in ("Polar Pacer Pro", "polar-pacer-pro", "polar", "PACER PRO"):
        assert resolve_source(written) == "polar-watch", written
    assert resolve_source("PM5") == "concept2-pm"
    assert resolve_source("crosstrainer") == "elliptical-console"


def test_an_uncatalogued_source_resolves_rather_than_erroring():
    """The G85 failure is a CLOSED vocabulary that makes a stranger's device
    unrepresentable. Unrecognised lands in `other`, never an error."""
    from vitai.provenance import resolve_source
    assert resolve_source("some-machine-nobody-catalogued") == "other"
    assert resolve_source(None) == "unknown"
    assert resolve_source("") == "unknown"


def test_other_carries_a_kind_rather_than_multiplying_the_catalog():
    """`session_types.toml` refused `outdoor_other` because it pre-coordinates
    two axes. Same rule: there is no `other-console` or `other-wearable`."""
    from vitai.provenance import resolve_source, source_kind
    assert source_kind("scale") == "scale"
    assert resolve_source("scale") == "other", "a kind name is not an instrument"
    assert source_kind("some rower console") in {"unknown", "gym_console"}
    catalogued = set(vocab.sources())
    assert not [s for s in catalogued if s.startswith("other-")]


def test_a_private_source_name_never_needs_to_appear_here():
    """A source named for someone's own spreadsheet or their own gym resolves
    to `other`, which is what the catchall is for. A public registry must not
    carry a private name, and the checks work on the KIND, so nothing is lost.
    """
    from vitai.provenance import impossible_claims, resolve_source
    assert resolve_source("someones-personal-sheet") == "other"
    assert impossible_claims({"source": "someones-personal-sheet",
                              "steps": 9000}, ["steps"]) == []


def test_a_scale_cannot_observe_distance():
    """What earns this registry its keep. Not a resolution tie - a tie is two
    instruments disagreeing, and this is one instrument claiming something it
    has no sensor for."""
    from vitai.provenance import impossible_claims
    scale = {"source": "fitbit aria", "kg": 80.0, "steps": 9000,
             "distance_km": 4.2}
    assert set(impossible_claims(scale, ["kg", "steps", "distance_km"])) == {
        "steps", "distance_km"}


def test_a_console_cannot_observe_sleep():
    from vitai.provenance import impossible_claims
    console = {"source": "PM5", "sleep_h": 7.5, "distance_km": 3.1}
    assert impossible_claims(console, ["sleep_h", "distance_km"]) == ["sleep_h"]


def test_a_watch_claiming_steps_is_fine():
    from vitai.provenance import impossible_claims
    watch = {"source": "polar", "steps": 9000, "distance_km": 4.2}
    assert impossible_claims(watch, ["steps", "distance_km"]) == []


def test_a_registry_gap_never_becomes_an_accusation():
    from vitai.provenance import impossible_claims
    assert impossible_claims({"source": "acme-thing", "steps": 1},
                             ["steps"]) == []


@pytest.mark.parametrize("rec,fields", [
    ({"source": "manual", "rhr": 52}, ["rhr"]),
    ({"source": "oura", "kcal_out": 2400}, ["kcal_out"]),
    ({"source": "fitbit", "kg": 80.0}, ["kg"]),
    ({"source": "mfp", "steps": 9000}, ["steps"]),
])
def test_a_deny_list_does_not_accuse_realistic_rows(rec, fields):
    """This was first written as a per-instrument WHITELIST of what each
    device can observe, and every one of these was flagged by it.

    An Oura ring does report calories. A hand-typed row can carry a heart
    rate the athlete read off a watch. A relaying app carries whatever it
    received. Watch models differ in what they record. A whitelist turns each
    omission into a false accusation against a real row; a deny list turns it
    into silence.
    """
    from vitai.provenance import impossible_claims
    assert impossible_claims(rec, fields) == []


def test_the_catalog_implies_no_precedence():
    """Which instrument to believe is a local judgement and stays in config:
    a figure stated in chat outranks a vendor channel in one record and would
    not in another."""
    entries = vocab.registry("sources")["sources"]
    for slug, entry in entries.items():
        assert "rank" not in entry and "precedence" not in entry, slug


def test_every_catalogued_kind_is_a_declared_kind():
    kinds = set(vocab.source_kinds()) | {"unknown"}
    for slug, entry in vocab.registry("sources")["sources"].items():
        assert entry["kind"] in kinds, f"{slug}: {entry['kind']}"


def test_every_denied_field_is_a_real_schema_field():
    """A `cannot` entry naming a column that does not exist would make the
    check silently unenforceable."""
    from vitai.schema import KEYS
    real = {f for keys in KEYS.values() for f in keys}
    for kind, entry in vocab.registry("sources")["kinds"].items():
        for f in entry.get("cannot") or []:
            assert f in real, f"{kind} denies {f!r}, which is not a field"


def test_ordinary_source_strings_resolve_without_a_migration():
    """Acceptance: an existing record keeps working. Every spelling here is a
    generic one - a public registry's tests must not name somebody's actual
    equipment or their personal files any more than the registry may.
    """
    from vitai.provenance import resolve_source, source_kind
    expected = {
        "polar": "polar-watch",
        "crosstrainer": "elliptical-console",
        "fitbit-aria": "fitbit-scale",
        "mfp-export": "myfitnesspal",
        "strava-export": "strava",
        "manual": "athlete",
        "stated-in-chat": "athlete",
    }
    for written, slug in expected.items():
        assert resolve_source(written) == slug, written
    # An uncatalogued instrument still resolves, and still gets no kind it
    # cannot justify.
    assert resolve_source("a-machine-in-someones-gym") == "other"
    assert source_kind("a-machine-in-someones-gym") == "unknown"
def test_every_generation_a_deployment_could_have_stamped_still_validates():
    """The G25 property in general, over every dataset and every generation.

    A row carries `_gen`, so a row stamped at generation N owes exactly the
    keys introduced at or before N. Any change that reuses a generation
    instead of advancing one breaks this for a row already on disk somewhere,
    which is the whole failure mode - and unlike a test naming one increment's
    fields, this cannot go out of date.
    """
    from vitai.schema import (CURRENT_GENERATION, KEYS, key_generation,
                              validate_record)
    seed = {"sessions": {"type": "run"},
            "measurements": {"kind": "waist_cm", "value": 84.0},
            "daily": {}, "weight": {}}
    for ds, fields in seed.items():
        for gen in range(1, CURRENT_GENERATION[ds] + 1):
            row = {k: None for k in KEYS[ds] if key_generation(ds, k) <= gen}
            row.update({"date": "2030-05-01", "_gen": gen, **fields})
            assert validate_record(ds, row) == [], (ds, gen,
                                                    validate_record(ds, row))


def test_the_capture_fields_share_one_generation_of_their_own():
    from vitai.schema import key_generation
    landed = key_generation("sessions", "capture")
    for k in ("read_by", "origin", "path", "origin_evidence"):
        assert key_generation("sessions", k) == landed, k
    assert key_generation("sessions", "track") < landed
# ---- #49/#88: was it measured at all? ------------------------------------------

def test_modelled_names_fields_not_the_whole_row():
    """The distinction is per-field: one row can carry a measured step count
    and an estimated burn."""
    from vitai.provenance import is_modelled, modelled_fields
    row = {"modelled": "kcal_out rhr", "kcal_out": 1728, "rhr": 0, "steps": 9000}
    assert modelled_fields(row) == {"kcal_out", "rhr"}
    assert is_modelled(row, "kcal_out") is True
    assert is_modelled(row, "steps") is False


def test_an_unannotated_row_claims_nothing():
    from vitai.provenance import modelled_fields
    assert modelled_fields({"kcal_out": 1728}) == set()


def test_modelled_must_name_real_fields():
    """A typo would make the declaration silently unenforceable - the field
    would keep being treated as measured."""
    from vitai.provenance import value_kind_problems
    assert any("not a field" in p for p in
               value_kind_problems({"modelled": "kcal_ou"}, ["kcal_out"]))
    assert value_kind_problems({"modelled": "kcal_out"}, ["kcal_out"]) == []


def test_a_categorical_label_can_say_how_it_was_assigned():
    """1,093 of 1,502 session types in one live record were a classifier's
    guess, and the record could not tell them from the 409 the athlete
    asserted (#88)."""
    from vitai.provenance import TYPE_SOURCES, type_source, value_kind_problems
    assert "vendor-classified" in TYPE_SOURCES
    assert type_source({"type_source": "vendor-classified"}) == "vendor-classified"
    assert type_source({}) is None
    assert any("type_source" in p for p in
               value_kind_problems({"type_source": "guessed", "type": "run"}, []))


def test_a_type_source_needs_a_type():
    from vitai.provenance import value_kind_problems
    assert any("needs a 'type'" in p for p in
               value_kind_problems({"type_source": "vendor-classified"}, []))


# ---- #140: capture carries a rank, so a recollection loses to a device -----
#
# The ladder's discriminator is `source`. When a value logged from memory and
# a value read off the scale are BOTH recorded as `source: scale`, precedence
# has nothing to rank by and no configuration helps. That is strictly harder
# than two devices disagreeing, where the ladder can do its job.

def test_a_remembered_number_loses_to_a_device_reading_of_the_same_source():
    from vitai.resolution import resolve as resolve_claims
    rows = [weight(kg=83.0, capture="narrative", read_by="athlete",
                   recorded_at="2030-05-01T21:00:00+02:00"),
            weight(kg=80.4, capture="ble",
                   recorded_at="2030-05-01T07:00:00+02:00")]
    got = resolve_claims({"weight": rows})
    assert got["canonical"]["weight"][0]["kg"] == 80.4


def test_it_wins_even_when_the_recollection_is_the_LATER_line():
    """The whole finding. Recency exists so a re-export can correct itself,
    and it would hand the record to whichever restatement came last - which
    is exactly the shape the athlete meant to distinguish when they wrote
    down how they got the number.
    """
    from vitai.resolution import resolve as resolve_claims
    rows = [weight(kg=80.4, capture="file_export",
                   recorded_at="2030-05-01T07:00:00+02:00"),
            weight(kg=83.0, capture="manual_entry",
                   recorded_at="2030-05-09T21:00:00+02:00")]
    got = resolve_claims({"weight": rows})
    assert got["canonical"]["weight"][0]["kg"] == 80.4


def test_an_explicit_correction_still_wins():
    """`supersedes` is the deliberate correction path and is applied at load,
    so a correction retires the line it corrects and never reaches this
    contest. Without that, "the scale said 82.4, I mistyped it" would have
    become unsayable.
    """
    from vitai.api import Vitai
    from vitai.cli import main as cli
    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp()) / "content"
    cli(["init", str(root)])
    write(root, [
        weight(kg=80.4, source="scale", capture="ble",
               recorded_at="2030-05-01T07:00:00+02:00"),
        weight(kg=82.4, source="scale", capture="manual_entry",
               supersedes="2030-05-01/scale",
               recorded_at="2030-05-02T09:00:00+02:00"),
    ])
    assert Vitai(root).canonical()["weight"][0]["kg"] == 82.4


def test_capture_never_overrules_the_configured_precedence():
    """It breaks a tie the SOURCE ladder left, and nothing more. Precedence
    is the athlete's own judgement about their instruments; a registry
    default is not entitled to overturn it."""
    from vitai.resolution import resolve as resolve_claims
    rows = [weight(kg=83.0, source="mfp-export", capture="narrative"),
            weight(kg=80.4, source="scale", capture="ble")]
    got = resolve_claims({"weight": rows}, {"kg": ("mfp-export", "scale")})
    assert got["canonical"]["weight"][0]["kg"] == 83.0


def test_the_audit_trail_names_capture_when_capture_decided():
    """A resolution nobody can explain is one nobody can dispute. Saying
    "the later-written scale claim supersedes the earlier" would have been
    false in the one place the record explains itself."""
    from vitai.resolution import resolve as resolve_claims
    rows = [weight(kg=83.0, capture="narrative", read_by="athlete"),
            weight(kg=80.4, capture="ble")]
    got = resolve_claims({"weight": rows})
    reason = got["explanations"][0]["reason"]
    assert "closer to the instrument" in reason
    assert "ble" in reason and "narrative" in reason


def test_two_recollections_still_tie_and_that_is_the_honest_answer():
    """`sofia`, the persona that motivated this, is NOT resolved by it: she
    records every weight as `manual_entry` or `narrative` under one source,
    so there is no device claim for a recollection to lose to and capture
    cannot separate them. Recency decides, as before.

    Recording this so the change is not read as fixing her case. What it
    fixes is a record that mixes a device capture with a recollection.
    """
    from vitai.provenance import restatements
    assert restatements({"capture": "manual_entry"}) == restatements(
        {"capture": "narrative"})


def test_an_unstated_capture_assumes_the_costly_side():
    """As everything else about `unknown` does. It TIES with a stated
    recollection, because we know nothing worse about an unstated capture
    than about a stated one."""
    from vitai.provenance import MOST_RESTATED, restatements
    assert restatements({}) == MOST_RESTATED
    assert restatements({"capture": "narrative"}) == MOST_RESTATED


def test_every_registered_capture_carries_a_rank():
    """A capture added later without one would silently take the costly
    default and lose every contest, which is a decision somebody should make
    rather than inherit."""
    from vitai.vocab import registry
    entries = registry("capture")["capture"]
    missing = [k for k, v in entries.items() if "restatements" not in v]
    assert missing == [], missing


def test_the_rank_is_not_a_quality_ordering():
    """`capture.toml` says so in capitals and this holds it to it: `ble` has
    no human in the loop and no durable artifact, `file_export` leaves an
    archive that survives. Different virtues, same distance from the
    instrument, and nothing here says which is better."""
    from vitai.provenance import restatements
    assert (restatements({"capture": "ble"})
            == restatements({"capture": "file_export"})
            == restatements({"capture": "connector"}))


def test_a_silent_line_is_not_a_worst_case():
    """UNSTATED IS NOT ABSENT. Defaulting silence to the worst rank made a
    line that said nothing lose to a line that said `file_export`, so a food
    log re-exported the next morning without a capture lost to the previous
    morning's annotated export - the 1,700 kcal error #70 exists to prevent,
    reintroduced by the fix for #140.

    The cost of "assume the costly side" lands on the OTHER claim here:
    penalising the silent row promotes the stale annotated one.
    """
    from vitai.resolution import resolve as resolve_claims

    def daily(**kw):
        rec = {"date": "2030-05-01", "kcal_in": None, "source": "mfp-export",
               "note": None, "steps": None, "recorded_at": None,
               "capture": None, "_gen": 8}
        rec.update(kw)
        return rec

    rows = [daily(kcal_in=1354, capture="export",
                  recorded_at="2030-05-01T08:00:00+02:00"),
            daily(kcal_in=3091, recorded_at="2030-05-02T08:00:00+02:00")]
    got = resolve_claims({"daily": rows})
    assert got["canonical"]["daily"][0]["kcal_in"] == 3091


def test_it_engages_once_every_claim_in_the_contest_says():
    """The premise of the test above: a record part-way through adopting
    `capture` is the normal case and must behave exactly as before, and a
    record that has adopted it gets the ranking it asked for."""
    from vitai.resolution import resolve as resolve_claims

    def daily(**kw):
        rec = {"date": "2030-05-01", "kcal_in": None, "source": "mfp-export",
               "note": None, "steps": None, "recorded_at": None,
               "capture": None, "_gen": 8}
        rec.update(kw)
        return rec

    rows = [daily(kcal_in=1354, capture="file_export",
                  recorded_at="2030-05-01T08:00:00+02:00"),
            daily(kcal_in=3091, capture="narrative",
                  recorded_at="2030-05-02T08:00:00+02:00")]
    got = resolve_claims({"daily": rows})
    assert got["canonical"]["daily"][0]["kcal_in"] == 1354


def test_a_capture_decided_disagreement_raises_a_tripwire():
    """A correction is not a disagreement (#70), so contests sharing a source
    are skipped - and that swallowed the one #140 is about, at any spread. A
    device reading and a recollection of the same instrument disagreeing is
    not the correction mechanism working."""
    from vitai.resolution import resolve as resolve_claims
    got = resolve_claims({"weight": [weight(kg=80.4, capture="ble"),
                                     weight(kg=68.0, capture="narrative")]})
    assert [t["kind"] for t in got["tripwires"]] == ["source_disagreement"]


def test_an_ordinary_same_source_correction_stays_silent():
    """The premise. Raising "mfp-export says 3091, mfp-export says 1354"
    reports the correction mechanism working as a fault."""
    from vitai.resolution import resolve as resolve_claims
    got = resolve_claims({"weight": [
        weight(kg=80.4, recorded_at="2030-05-01T07:00:00+02:00"),
        weight(kg=68.0, recorded_at="2030-05-02T07:00:00+02:00")]})
    assert got["tripwires"] == []


def test_the_trail_never_states_the_reverse_of_what_happened():
    """`_why` tested only that the two ranks DIFFERED, which read correctly
    when the sort had already put the closer claim first and stated the exact
    reverse whenever anything else decided. The reason must name the winner's
    capture as the closer one, or it is a false sentence in the one place the
    record explains itself."""
    from vitai.resolution import _why
    closer = weight(kg=80.4, capture="ble")
    further = weight(kg=83.0, capture="narrative")
    assert "closer to the instrument" in _why(closer, further, ())
    # Reversed: capture did NOT decide, so it must not claim it did.
    assert "closer to the instrument" not in _why(further, closer, ())


def test_derived_does_not_assert_a_rank_it_cannot_know():
    """The count is the count of its INPUTS, which the registry cannot see: a
    computation over a remembered number is that remembered number wearing
    arithmetic."""
    from vitai.provenance import MOST_RESTATED, restatements
    assert restatements({"capture": "derived"}) == MOST_RESTATED
