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
