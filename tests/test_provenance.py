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
from vitai.provenance import (describe, hops, independent_witnesses,
                              is_independent, may_mutate, role_of,
                              shares_origin, trust_ceiling)
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


# ---- #79: the source catalog ----------------------------------------------------

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
