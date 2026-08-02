"""Declared derivation lineage (#170).

`derived_from` names the rows a computed value stands on, `derived_op` says
how, and BOTH ARE DECLARED RATHER THAN EXECUTABLE. That distinction is the
subject of most of this file: the engine reads lineage to decide what a value
may be used for, and never to reproduce the value itself.

Two consequences the contract promises, and they are what these tests hold to:

  - a derived value never corroborates its own inputs, so rows standing on a
    shared input are ONE witness however many rows they are;
  - a value whose input the record later restated is FLAGGED, not corrected,
    because an engine that cannot re-run the derivation cannot produce a right
    answer and a confident wrong one is worse than a flagged old one.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.cli import main
from vitai.provenance import derivation_groups, independent_witnesses
from vitai.resolution import (_lineage_to_claim_id, derivation_cycles,
                              stale_derivations)
from vitai.schema import CURRENT_GENERATION, KEYS, validate_record


def a_weight(**kw):
    rec = {k: None for k in KEYS["weight"]}
    rec.update({"date": "2030-05-01", "kg": 80.0, "source": "scale",
                "_gen": CURRENT_GENERATION["weight"]})
    rec.update(kw)
    return rec


# --- what the schema will accept ---------------------------------------------

def test_a_row_with_no_lineage_is_the_ordinary_case():
    """Lineage is optional. Nearly every row anyone records is observed."""
    assert validate_record("weight", a_weight()) == []


def test_a_derived_row_states_a_derived_capture():
    """A computed value that claims to have been observed is a lie about how it
    got here, and `capture` is the field that already carries that fact."""
    problems = validate_record("weight", a_weight(
        derived_from=["weight:2030-04-24:scale"], capture="manual_entry"))
    assert problems and "COMPUTED" in problems[0]

    assert validate_record("weight", a_weight(
        derived_from=["weight:2030-04-24:scale"], capture="derived")) == []


def test_an_operation_without_inputs_says_nothing():
    """`derived_op` describes HOW something was computed. Without naming what
    it was computed FROM it is a sentence with no subject: unfalsifiable, and
    worse than absent because it reads as lineage at a glance."""
    problems = validate_record("weight", a_weight(
        derived_op="seven day mean", capture="derived"))
    assert problems and "derived_op" in problems[0]


def test_an_empty_lineage_is_not_a_lineage():
    """`[]` claims to be derived from nothing, which is not a weaker claim than
    absent - it is a different and false one."""
    assert validate_record("weight", a_weight(
        derived_from=[], capture="derived"))


def test_the_record_level_check_does_not_guess_at_self_reference():
    """A row reference computed from ONE record always carries ordinal 0, so a
    second same-day same-source reading deriving from the first is
    indistinguishable here from a row deriving from itself. Rejecting the
    honest lineage would be worse than missing the absurd one, so the loop
    check lives in `derivation_cycles`, which has every row and real
    ordinals."""
    assert validate_record("weight", a_weight(
        derived_from=["weight:2030-05-01:scale"], capture="derived")) == []


# --- a derived value never corroborates its own inputs -----------------------

def test_two_instruments_are_two_witnesses():
    """The baseline this is measured against: independent origins still count
    independently, and nothing here changes that."""
    assert independent_witnesses([{"origin": "scale-a"},
                                  {"origin": "watch-b"}]) == 2


def test_two_computations_of_one_reading_are_one_witness():
    """The defect this exists to prevent. Two calculators agreeing about one
    scale reading is one observation reported twice, and counting it as two
    manufactures confidence out of arithmetic."""
    lineage = ["weight:2030-04-24:scale-a"]
    assert independent_witnesses([
        {"origin": "calc-one", "derived_from": lineage},
        {"origin": "calc-two", "derived_from": lineage}]) == 1


def test_sharing_is_transitive_through_a_chain():
    """A row from x and y, one from y and z, one from z and w. Each link is the
    same observation reappearing with more arithmetic on top, so a two-hop
    derivation is still not a second look at the athlete."""
    assert independent_witnesses([
        {"origin": "c1", "derived_from": ["x", "y"]},
        {"origin": "c2", "derived_from": ["y", "z"]},
        {"origin": "c3", "derived_from": ["z", "w"]}]) == 1
    assert len(derivation_groups([
        {"derived_from": ["x", "y"]}, {"derived_from": ["y", "z"]}])) == 1


def test_derivations_from_different_inputs_stay_separate():
    """The collapse must not overreach. Two values computed from two DIFFERENT
    readings are two observations, and merging them would hide evidence in the
    name of not inventing it."""
    assert independent_witnesses([
        {"origin": "c1", "derived_from": ["weight:2030-04-24:scale-a"]},
        {"origin": "c2", "derived_from": ["weight:2030-05-01:watch-b"]}]) == 2


def test_a_derived_row_beside_an_observed_one_is_still_two():
    """Only the derived rows collapse among themselves. An observation standing
    beside a computed value is a real second witness."""
    assert independent_witnesses([
        {"origin": "calc", "derived_from": ["weight:2030-04-24:scale-a"]},
        {"origin": "watch-b"}]) == 2


def test_rows_that_declare_nothing_are_not_thereby_related():
    """Absent lineage is unknown, not shared. Treating it as shared would
    collapse an entire un-annotated history into one witness."""
    assert derivation_groups([{}, {}]) == []
    assert derivation_groups([{"derived_from": []},
                              {"derived_from": []}]) == []
    assert independent_witnesses([{"origin": "a"}, {"origin": "b"}]) == 2


# --- a restated input flags its dependants ----------------------------------

def test_a_retracted_input_raises_a_tripwire():
    rows = [a_weight(date="2030-05-08", source="calc", capture="derived",
                     derived_from=["weight:2030-05-01:scale"],
                     derived_op="seven day mean")]
    found = stale_derivations({"weight": rows}, {"weight:2030-05-01:scale"})
    assert [t["kind"] for t in found] == ["stale_derivation"]
    assert "weight:2030-05-01:scale" in found[0]["detail"]


def test_the_tripwire_reports_rather_than_corrects():
    """The value stays. `derived_op` is declared rather than executable, so the
    engine cannot recompute it, and inventing a replacement would be exactly
    the confident wrong answer a visible flag beats."""
    rows = [a_weight(date="2030-05-08", source="calc", capture="derived",
                     derived_from=["weight:2030-05-01:scale"])]
    stale_derivations({"weight": rows}, {"weight:2030-05-01:scale"})
    assert rows[0]["kg"] == 80.0
    assert rows[0]["derived_from"] == ["weight:2030-05-01:scale"]


def test_a_live_input_raises_nothing():
    rows = [a_weight(date="2030-05-08", source="calc", capture="derived",
                     derived_from=["weight:2030-05-01:scale"])]
    assert stale_derivations({"weight": rows}, set()) == []
    assert stale_derivations({"weight": rows},
                             {"weight:2030-04-24:scale"}) == []


def test_a_dataset_without_the_field_is_skipped_not_crashed():
    """Datasets that never gained lineage still flow through the same pass."""
    assert stale_derivations({"checks": [{"date": "2030-05-01"}]},
                             {"weight:2030-05-01:scale"}) == []


# --- through the engine, not just the units ----------------------------------
#
# The unit tests above hand `stale_derivations` a set already written in the
# grammar it wants, which is exactly the shape that cannot see a wiring defect.
# These go through `vitai build`, which is the deliverable.

def test_a_derived_row_survives_a_build(tmp_path: Path) -> None:
    """A list-valued column has to reach sqlite as something sqlite can bind.
    `derived_from` is the first one, and a schema-valid row that crashes the
    build would make the whole feature unusable through its primary output."""
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None},
        {"date": "2030-05-08", "kg": 79.5, "source": "calc", "note": None,
         "capture": "derived", "derived_op": "seven day mean",
         "derived_from": ["weight:2030-05-01:scale"]},
    ]) + "\n", encoding="utf-8")

    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        stored = con.execute(
            "SELECT derived_from FROM weight WHERE source='calc'").fetchone()[0]
        assert json.loads(stored) == ["weight:2030-05-01:scale"]
        assert con.execute(
            "SELECT value FROM meta WHERE key='contract'").fetchone()[0] == "20"
    finally:
        con.close()


def test_derived_op_keeps_its_type(tmp_path: Path) -> None:
    """Under REAL affinity `derived_op = "7"` comes back as 7.0. It is free
    text and a numeric-looking description is still text."""
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {"date": "2030-05-08", "kg": 79.5, "source": "calc", "note": None,
         "capture": "derived", "derived_op": "7",
         "derived_from": ["weight:2030-05-01:scale"]}) + "\n", encoding="utf-8")
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        assert con.execute("SELECT derived_op FROM weight").fetchone()[0] == "7"
    finally:
        con.close()


def test_a_restated_input_reaches_the_tripwires_through_a_build(tmp_path):
    """The grammars differ - `derived_from` carries row references and the
    retraction ledger carries claim ids - so this goes through the real wiring
    rather than a hand-written set, which is where a mix-up would hide."""
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None},
        {"date": "2030-05-08", "kg": 79.5, "source": "calc", "note": None,
         "capture": "derived", "derived_op": "seven day mean",
         "derived_from": ["weight:2030-05-01:scale"]},
        {"date": "2030-05-01", "kg": 81.0, "source": "scale", "note": None,
         "supersedes": "2030-05-01/scale"},
    ]) + "\n", encoding="utf-8")

    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        found = con.execute(
            "SELECT detail FROM conservation WHERE kind='stale_derivation'"
        ).fetchall()
    finally:
        con.close()
    assert len(found) == 1
    # It reports a RESTATEMENT and asks which version was used. It does not
    # claim to know: a row reference names a date and a source, not a version.
    assert "restated" in found[0][0]


def test_a_derivation_from_a_live_input_raises_nothing_in_a_build(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None},
        {"date": "2030-05-08", "kg": 79.5, "source": "calc", "note": None,
         "capture": "derived", "derived_from": ["weight:2030-05-01:scale"]},
    ]) + "\n", encoding="utf-8")
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        assert con.execute(
            "SELECT count(*) FROM conservation WHERE kind='stale_derivation'"
        ).fetchone()[0] == 0
    finally:
        con.close()


# --- the ordering case, and the cycle check ----------------------------------

def test_the_count_does_not_depend_on_row_order():
    """A cluster contributes exactly one witness however the rows arrive.
    Keeping one row of the cluster and letting the origin pass count it made
    the answer depend on which row survived, and a cluster whose survivor
    shared an origin with a real observation contributed nothing at all."""
    observed = {"origin": "scale-a"}
    same = {"origin": "scale-a", "derived_from": ["x"]}
    other = {"origin": "watch-b", "derived_from": ["x"]}
    assert independent_witnesses([observed, same, other]) == 2
    assert independent_witnesses([observed, other, same]) == 2


def test_a_row_derived_from_itself_is_caught_with_the_real_ordinals():
    rows = [{"date": "2030-05-01", "source": "scale",
             "derived_from": ["weight:2030-05-01:scale"]}]
    assert [t["kind"] for t in derivation_cycles({"weight": rows})] == [
        "derivation_cycle"]


def test_a_loop_through_another_row_is_caught_too():
    rows = [{"date": "2030-05-01", "source": "a",
             "derived_from": ["weight:2030-05-02:b"]},
            {"date": "2030-05-02", "source": "b",
             "derived_from": ["weight:2030-05-01:a"]}]
    assert len(derivation_cycles({"weight": rows})) == 2


def test_a_second_reading_deriving_from_the_first_is_not_a_cycle():
    """The case the record-level check could not tell apart. Two rows share a
    date and a source; the second derives from the first. Real ordinals make
    them distinct, and this is an honest lineage."""
    rows = [{"date": "2030-05-01", "source": "scale"},
            {"date": "2030-05-01", "source": "scale",
             "derived_from": ["weight:2030-05-01:scale"]}]
    assert derivation_cycles({"weight": rows}) == []
    assert validate_record("weight", a_weight(
        derived_from=["weight:2030-05-01:scale"], capture="derived")) == []


def test_a_derived_capture_alias_is_resolved_not_string_matched():
    """`athlete-derived` resolves to `derived_external` through the registry.
    A raw string comparison would reject a correctly-captured row."""
    assert validate_record("weight", a_weight(
        derived_from=["weight:2030-04-24:scale"],
        capture="athlete-derived")) == []


def test_staleness_cascades_to_what_stands_on_it():
    """C from B from A. Restate A and BOTH fall: a value computed from a stale
    value is stale too. Without the cascade "everything computed from this"
    would have meant "one hop", which the documentation does not say."""
    rows = [{"date": "2030-05-01", "source": "a"},
            {"date": "2030-05-02", "source": "b",
             "derived_from": ["weight:2030-05-01:a"]},
            {"date": "2030-05-03", "source": "c",
             "derived_from": ["weight:2030-05-02:b"]}]
    found = stale_derivations({"weight": rows}, {"weight:2030-05-01:a"})
    assert [t["date"] for t in found] == ["2030-05-02", "2030-05-03"]
    # The two findings say DIFFERENT things. The first row's own input was
    # restated; the second row's input is untouched and merely stale itself,
    # and calling that a restatement would be false.
    assert "been restated" in found[0]["detail"]
    assert "is itself stale" in found[1]["detail"]


def test_the_cascade_terminates_on_a_loop():
    """A cycle is an error rather than a licence to spin."""
    rows = [{"date": "2030-05-01", "source": "a",
             "derived_from": ["weight:2030-05-02:b"]},
            {"date": "2030-05-02", "source": "b",
             "derived_from": ["weight:2030-05-01:a"]}]
    assert len(stale_derivations({"weight": rows}, {"weight:2030-05-01:a"})) == 2


def test_a_long_chain_does_not_exhaust_the_stack():
    """A recursive walk died at around a thousand links, and an honest daily
    derived series reaches that in three years. A build that dies on a long
    record is a worse failure than the loop it was looking for."""
    rows = [{"date": f"2030-01-{i % 28 + 1:02d}", "source": f"s{i}",
             "derived_from": [f"weight:2030-01-{(i + 1) % 28 + 1:02d}:s{i + 1}"]}
            for i in range(3000)]
    assert derivation_cycles({"weight": rows}) == []


def test_an_identity_keyed_reference_is_not_read_as_a_claim_id():
    """`sets` and `meals` key on an identity tuple, so their references are
    also three parts and are NOT claim ids. Translating one produced a
    plausible-looking id that could only ever match by accident, which is the
    grammar confusion this whole path exists to avoid."""
    assert _lineage_to_claim_id("weight:2030-05-01:scale") == \
        "weight:2030-05-01:scale"
    assert _lineage_to_claim_id("sessions:2030-05-01:watch:2") == \
        "sessions:2030-05-01:watch"
    assert _lineage_to_claim_id("meals:lunch-plate:rice") is None


def test_an_unnumbered_reference_points_at_the_first_row():
    """Where a date and a source name several rows, a lineage that omits the
    ordinal names the FIRST of them. A derived row that is itself first
    therefore names itself, and reporting that is the right answer to what was
    written - the fix is to write the ordinal."""
    first_is_derived = [{"date": "2030-05-01", "source": "scale",
                         "derived_from": ["weight:2030-05-01:scale"]},
                        {"date": "2030-05-01", "source": "scale"}]
    assert len(derivation_cycles({"weight": first_is_derived})) == 1


# --- a derived value is not an observation, in every layer that counts them --

def test_a_computed_row_is_not_a_weigh_in():
    """It has no `measured_at` because nobody stood on a scale to produce it,
    and that is an INAPPLICABLE time rather than a missing one. Counting it as
    unknown made the engine report that part of a rate could not be checked
    for time-of-day drift while every actual weigh-in behind it was timed."""
    from vitai.clocks import weigh_in_timing

    weighed = [{"date": "2030-05-01", "measured_at": "07:10"},
               {"date": "2030-05-02", "measured_at": "19:10"}]
    alone = weigh_in_timing(weighed)
    with_average = weigh_in_timing(weighed + [
        {"date": "2030-05-03", "measured_at": None,
         "derived_from": ["weight:2030-05-01:scale"]}])

    assert with_average == alone
    assert with_average["unknown"] == 0
    # The spread the readings actually show is preserved, not diluted.
    assert with_average["spread_h"] == 12.0


def test_an_untimed_observation_is_still_unknown():
    """The exclusion is for COMPUTED rows only. A weigh-in nobody wrote a time
    against is a real gap and must keep saying so."""
    from vitai.clocks import weigh_in_timing

    timing = weigh_in_timing([{"date": "2030-05-01", "measured_at": "07:10"},
                              {"date": "2030-05-02", "measured_at": None}])
    assert timing["unknown"] == 1


def test_the_demo_lineage_row_stays_inside_the_final_week():
    """A demonstration row for one feature must not switch off another.

    Dated one day past the last weigh-in it looked adjacent and was not: that
    weigh-in fell on a Sunday, so the next day opened an ISO week holding a
    single row, that week became the one the rollup reports on, and the
    weigh-in-spread refusal #37 exists to demonstrate stopped appearing. The
    suite was green throughout, which is the whole reason this is pinned here
    rather than left to the eye.
    """
    import json
    from datetime import date as _date
    from pathlib import Path as _Path

    rows = [json.loads(line) for line in
            (_Path(__file__).parent.parent / "examples" / "demo" / "data"
             / "weight.jsonl").read_text().splitlines() if line.strip()]
    derived = [r for r in rows if r.get("derived_from")]
    assert len(derived) == 1

    weighed = sorted(r["date"] for r in rows if not r.get("derived_from"))
    week = _date.fromisoformat(weighed[-1]).isocalendar()[:2]
    assert _date.fromisoformat(derived[0]["date"]).isocalendar()[:2] == week

    # And it stands alone, or it would merge and a merged row keeps no lineage.
    assert derived[0]["date"] not in weighed
    # Nothing is derived from a reading taken after it.
    assert all(ref.split(":")[1] < derived[0]["date"]
               for ref in derived[0]["derived_from"])
