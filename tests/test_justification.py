"""What the engine told somebody, and whether it still rests on anything (#134).

The issue's complaint is that the justification link "applies to one dataset
only". Checked against the record rather than taken on trust, that is not what
was there. THREE fields already say "the claims this rests on":

    `inferences.depends_on`   cascaded by `retractions`, and only there.
    `derived_from`            on six lineage datasets, cascaded multi-hop by
                              `stale_derivations` over every dataset carrying
                              it - already general, for VALUES.
    `emissions.basis_claims`  validated on write, stored in the read model,
                              and read by nothing at all.

So the missing thing was never a fourth field. It was the cascade over the
third - and the third is the one that matters most, because an emission is the
only artifact here that a PERSON was handed. A stale derivation is a number in
a file; an unsupported assertion was read by somebody who may have changed
what they did about it.

WHAT THIS DELIBERATELY DOES NOT DO. It does not say the assertion is now
wrong. The engine cannot know whether the restatement changes what would be
said today - that is `still_holds`, which needs the policy in force at the
assertion's date rather than today's (#148). And it never retracts the
emission: the engine did say that, on that day, to that surface, and no later
correction makes it not have happened.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vitai.api import Vitai, init
from vitai.resolution import JUSTIFICATION_LINK, retractions
from vitai.db import CONTRACT_VERSION
from vitai.schema import KEYS

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"

# The one correction the shipped record makes, and the assertion that was
# delivered on the strength of it.
RETRACTED = "sessions:2030-06-14:watch:0"


def _emissions(ledger: list[dict]) -> list[dict]:
    return [e for e in ledger if e["kind"] == "emission"]


def _record(tmp_path: Path) -> Vitai:
    """Two weigh-ins where the second corrects the first."""
    v = Vitai(init(tmp_path / "content"))
    v.append("weight", {"date": "2030-05-01", "kg": 83.0, "source": "scale"})
    v.append("weight", {"date": "2030-05-02", "kg": 80.0, "source": "scale",
                        "supersedes": "2030-05-01/scale"})
    return v


def _emit(v: Vitai, basis: list[str], surface: str = "demo-coach",
          statement: str = "an assertion") -> None:
    v.assert_delivery([{
        "date": "2030-05-03", "kind": "verdict", "metric": "weight_rate",
        "statement": statement, "basis_claims": basis,
        "policy_asof": "2030-05-03"}], surface=surface)


def test_an_assertion_resting_on_a_retracted_claim_is_reported():
    """The shipped record carries one correction and one assertion that was
    delivered on the strength of it, so this is exercised on the same fixture
    a reader can open rather than only on a synthetic one."""
    entries = _emissions(retractions(Vitai(DEMO).datasets()))

    assert len(entries) == 1, entries
    assert entries[0]["cascaded_from"] == RETRACTED
    assert entries[0]["retracted_by"] == RETRACTED


def test_an_assertion_whose_basis_still_stands_is_not_reported():
    """#204's corollary: a fixture holding one value of a distinction proves
    nothing about the distinction. The demo ships one assertion on a restated
    claim and one on a claim nothing has touched, so a cascade that flagged
    everything would fail here rather than look correct."""
    v = Vitai(DEMO)
    delivered = v.dataset("emissions")
    reported = {e["claim_id"] for e in _emissions(v.retractions())}

    assert len(delivered) == 2
    assert len(reported) == 1


def test_the_assertion_is_not_itself_retracted():
    """THE WORDING IS THE RULE. `emissions` never retires, because it records
    an event: the engine did say that. What moved is what it rested on, and a
    ledger entry that read as "this assertion was withdrawn" would be the
    record claiming something nobody decided."""
    entry, = _emissions(retractions(Vitai(DEMO).datasets()))

    assert "the record has since restated" in entry["reason"]
    assert "which was retracted" not in entry["reason"]
    assert len(Vitai(DEMO).dataset("emissions")) == 2


def test_the_basis_may_be_the_claim_id_the_engine_itself_published(tmp_path):
    """THE FAILURE THAT WOULD HAVE BEEN SILENT, and the demo now carries it.

    The engine publishes two spellings of one claim. `claim_id` appends an
    ordinal on `sessions`, so the `claims` table says
    `sessions:2030-06-14:watch:0`; the retracted set is built from a
    `supersedes` reference, which cannot know an ordinal, so it says
    `sessions:2030-06-14:watch`. A consumer doing the obvious right thing -
    copying the id out of the engine's own read model - wrote an assertion
    that could never fall, with no warning on write and no finding on read.

    The first version of the demo fixture hid this by hand-writing the
    ordinal-less spelling, which no engine surface emits. Both spellings are
    checked here, because accepting only the published one would break every
    consumer that had already written the other.
    """
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch"})
    # The order a consumer actually meets: it quotes the ids the record
    # publishes TODAY, and the correction arrives afterwards.
    published = [c["claim_id"] for c in v.resolution()["claims"]
                 if c["claim_id"].startswith("sessions:2030-05-01:")]
    _emit(v, published, statement="the published spelling")
    _emit(v, ["sessions:2030-05-01:watch"], statement="the bare spelling")
    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 6.0, "source": "watch",
                          "supersedes": "2030-05-01/watch"})

    reasons = [e["reason"] for e in _emissions(v.retractions())]

    assert published == ["sessions:2030-05-01:watch:0"], published
    assert any("the published spelling" in r for r in reasons), reasons
    assert any("the bare spelling" in r for r in reasons), reasons


def test_an_assertion_resting_on_a_fallen_inference_falls_too(tmp_path):
    """THE SECOND HOP, and the reason the cascade is not one pass. An
    inference standing on a retracted claim comes down; an assertion delivered
    on the strength of THAT inference is in exactly the position this ledger
    exists to report, and a cascade that only intersected the directly
    retracted claims would have missed it while looking complete."""
    v = _record(tmp_path)
    v.append("inferences", {
        "date": "2030-05-02", "kind": "pattern", "statement": "trending down",
        "confidence": 0.4, "model": "a-model",
        "depends_on": ["weight:2030-05-01:scale"]})
    _emit(v, ["inference:2030-05-02:a-model"])

    entry, = _emissions(v.retractions())

    assert entry["cascaded_from"] == "inference:2030-05-02:a-model"
    # AND THE WORDING, which one phrase for both hops would get wrong half the
    # time. A claim is RESTATED by a correction somebody wrote; an inference
    # FELL because its own justification went, and nobody restated it.
    assert "has since fallen" in entry["reason"]
    assert "restated" not in entry["reason"]


def test_one_assertion_losing_two_bases_is_ordered_the_same_way_every_time(
        tmp_path):
    """SAME INPUT, SAME OUTPUT, tested as the property rather than by a proxy.

    Two entries about ONE emission that lost TWO of its bases agree on date,
    kind and claim_id, so their relative order comes from a set. Every other
    test here gives an emission a single basis, so nothing exercised it.

    THE FIRST VERSION OF THIS TEST WAS A PROXY AND IT PASSED WITH THE RULE
    DELETED. It asserted the two entries came out in sorted order, which the
    default hash seed happened to produce anyway, so removing the tiebreak
    changed nothing it could see. The property is that TWO RUNS AGREE, and the
    only honest way to check it is to run the thing twice under different hash
    seeds - which needs a subprocess, because the seed is fixed at startup.
    """
    v = _record(tmp_path)
    v.append("weight", {"date": "2030-05-04", "kg": 82.0, "source": "notebook"})
    v.append("weight", {"date": "2030-05-05", "kg": 81.0, "source": "notebook",
                        "supersedes": "2030-05-04/notebook"})
    _emit(v, ["weight:2030-05-04:notebook", "weight:2030-05-01:scale"])

    script = ("import json,sys;from vitai.api import Vitai;"
              "print(json.dumps(Vitai(sys.argv[1]).retractions()))")
    seen = set()
    for seed in ("0", "1", "2", "3", "4"):
        out = subprocess.run(
            [sys.executable, "-c", script, str(v.root)],
            capture_output=True, text=True, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed})
        seen.add(out.stdout.strip())

    assert len(seen) == 1, "the ledger came out differently under a new seed"
    entries = _emissions(json.loads(seen.pop()))
    assert [e["retracted_by"] for e in entries] == [
        "weight:2030-05-01:scale", "weight:2030-05-04:notebook"]


def test_an_emission_never_makes_a_derivation_look_stale(tmp_path):
    """A WIDENING THAT WAS NOT INERT, kept out rather than reasoned away.

    The ledger is computed once and read twice, and feeding the emission
    entries into the staleness check looked harmless because nothing derives
    from an emission. It was not: emission ids carry an ordinal from the row
    grammar, the staleness check strips a trailing ordinal before comparing,
    and a lineage naming the SECOND emission of a day therefore matched the
    FIRST one's ledger id. That is a stale finding about a row nobody
    restated, worded as though an emission had been.
    """
    v = _record(tmp_path)
    _emit(v, ["weight:2030-05-01:scale"], statement="this one falls")
    _emit(v, ["weight:2030-05-02:scale"], statement="this one stands")
    v.append("weight", {
        "date": "2030-05-06", "kg": 80.0, "source": "notebook",
        "capture": "derived_external", "derived_by": "by-hand",
        "derived_from": ["emissions:2030-05-03:unknown:1"],
        "derived_op": "a lineage naming the assertion that stands"})

    stale = [t for t in v.resolution()["tripwires"]
             if t["kind"] == "stale_derivation"]

    assert not stale, stale


def test_two_assertions_on_one_day_are_told_apart(tmp_path):
    """`emissions` has an explicit rule that two assertions on one day are two
    events, so an identity built from the date alone cannot name which of them
    fell - and a client asking "which of my assertions is unsupported" would
    get one answer twice.

    THE FIRST VERSION OF THIS TEST PROVED NOTHING. It delivered one assertion
    on a retracted claim and one on a standing claim, then asserted a single
    entry - which is true of a date-only identity too, because only one entry
    is produced either way. Replacing the identity with the bare date passed
    the whole file. Both assertions have to FALL for the collision to be
    visible, so both rest on the retracted claim and the entries are checked
    for being distinguishable rather than merely counted.
    """
    v = _record(tmp_path)
    _emit(v, ["weight:2030-05-01:scale"], statement="the first")
    _emit(v, ["weight:2030-05-01:scale"], statement="the second")

    entries = _emissions(v.retractions())

    assert len(entries) == 2, entries
    assert len({e["claim_id"] for e in entries}) == 2, entries


def test_the_surface_that_delivered_it_survives_into_the_entry(tmp_path):
    """"To whom" is half of what a client asks this ledger. The row grammar
    keys on date and source, and an emission has no `source` - so without the
    surface in the entry a consumer running several surfaces could not tell
    which of them handed out the assertion that fell.

    Recorded rather than fixed by giving `emissions` an IDENTITY_KEY: no tuple
    of its fields identifies a row, since two assertions on one day, one
    surface and one metric are still two events, and an identity with no
    ordinal fallback would collide silently.
    """
    v = _record(tmp_path)
    _emit(v, ["weight:2030-05-01:scale"], surface="another-surface")

    entry, = _emissions(v.retractions())

    assert "another-surface" in entry["reason"]


def test_a_basis_written_as_a_string_is_read_the_same_way(tmp_path):
    """The engine writes a list; the format invites hand editing, and a
    hand-written line tends to carry one string. Reading it as opaque would
    mean a hand-edited assertion silently never falls.

    BOTH SEPARATORS, because only one of them was tested and the docstring
    promised two: deleting the comma handling left the whole suite green while
    a comma-separated basis parsed as one bogus token and never fell.
    """
    v = _record(tmp_path)
    v.append("weight", {"date": "2030-05-04", "kg": 82.0, "source": "notebook"})
    v.append("weight", {"date": "2030-05-05", "kg": 81.0, "source": "notebook",
                        "supersedes": "2030-05-04/notebook"})
    rows = v.datasets()
    rows["emissions"] = [{
        "date": "2030-05-03", "kind": "verdict", "metric": "weight_rate",
        "statement": "hand written", "surface": "a-surface",
        "policy_asof": "2030-05-03", "contract": CONTRACT_VERSION,
        "basis_claims": "weight:2030-05-01:scale,weight:2030-05-04:notebook"}]

    fell = {e["cascaded_from"] for e in _emissions(retractions(rows))}

    assert fell == {"weight:2030-05-01:scale", "weight:2030-05-04:notebook"}


def test_the_finding_reaches_the_build_without_being_asked_for():
    """A ledger a caller has to know to query is a capability with no door.
    The same relation surfaces as a tripwire, which is where a reader who
    asked nothing in particular will meet it."""
    found = [t for t in Vitai(DEMO).resolution()["tripwires"]
             if t["kind"] == "unsupported_assertion"]

    assert len(found) == 1
    assert RETRACTED in found[0]["detail"]


def test_the_finding_is_review_and_never_error():
    """The engine does not know whether the restatement changes what would be
    said now. Calling it an error asserts that it does; calling it nothing
    asserts that it does not, and the second is the dangerous one."""
    found, = [t for t in Vitai(DEMO).resolution()["tripwires"]
              if t["kind"] == "unsupported_assertion"]

    assert found["severity"] == "review"


def test_the_ledger_reaches_the_cli():
    """P9. The engine and the CLI are one surface, and a client reading the
    record over the command line gets the same entry the API returns.

    FOUND BY WRITING THIS TEST. `resolve --json` labelled each line with the
    stream it came from and then splatted the row over it, so a tripwire and a
    retraction - both of which carry a `kind` of their own - overwrote the
    label and arrived indistinguishable. `stream` is the label that cannot be
    clobbered; `kind` is left exactly where it was.
    """
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "resolve", "--root", str(DEMO),
         "--json"], capture_output=True, text=True, check=True)
    rows = [json.loads(ln) for ln in out.stdout.splitlines()]
    emissions = [r for r in rows if r.get("stream") == "retraction"
                 and r.get("kind") == "emission"]

    assert len(emissions) == 1
    assert emissions[0]["cascaded_from"] == RETRACTED
    assert {r["stream"] for r in rows} == {"resolution", "tripwire",
                                           "retraction"}


def _rests_on_a_retracted_claim(v: Vitai, dataset: str) -> None:
    """Write a row of `dataset` whose justification link names a dead claim."""
    if dataset == "inferences":
        v.append("inferences", {
            "date": "2030-05-02", "kind": "pattern", "statement": "a guess",
            "confidence": 0.4, "model": "a-model",
            "depends_on": ["weight:2030-05-01:scale"]})
    elif dataset == "emissions":
        _emit(v, ["weight:2030-05-01:scale"])
    else:
        raise AssertionError(
            f"{dataset} is in JUSTIFICATION_LINK and this test does not know "
            f"how to write one, so nothing here proves it is read")


def test_every_named_link_is_actually_read(tmp_path):
    """THE CONTROL THAT KEEPS THIS FROM HAPPENING AGAIN, and it checks the
    behaviour rather than the map.

    `basis_claims` shipped validated, stored and unread for as long as it
    existed, and nothing failed while it did. An entry added to the registry
    with no cascade behind it would ship exactly the same way, so membership
    is not what is asserted: for every dataset the registry names, a row of
    that dataset resting on a retracted claim has to produce a ledger entry.

    THE LIMIT, stated rather than left to be discovered. This catches a KNOWN
    link name arriving on a dataset nothing reads, and it catches a registry
    entry that is decoration. It cannot catch a field with a name nobody has
    thought of yet - `rests_on` would ship silent, and the only guard against
    that is review.
    """
    for dataset in JUSTIFICATION_LINK:
        v = _record(tmp_path / dataset)
        _rests_on_a_retracted_claim(v, dataset)

        kinds = {e["kind"] for e in v.retractions()}

        assert kinds - {"claim"}, f"nothing reads {dataset}'s justification"


def test_no_link_field_exists_outside_the_two_read_paths():
    """The other half: a known link name on a dataset the registry does not
    name, and which the lineage cascade does not cover either."""
    for dataset, keys in KEYS.items():
        for key in keys:
            if key not in {"depends_on", "basis_claims", "derived_from"}:
                continue
            assert (key == "derived_from"
                    or JUSTIFICATION_LINK.get(dataset) == key), (
                f"{dataset}.{key} declares what a row rests on and nothing "
                f"reads it")


def test_the_link_is_not_a_fourth_field():
    """A DECISION PINNED, because the issue asks for the opposite. Adding
    `depends_on` to `emissions` would give the record two names for one
    relation on one dataset, and a consumer would then have to read both to
    be sure. The field that was already there is the field that is used."""
    assert "depends_on" not in KEYS["emissions"]
    assert "basis_claims" in KEYS["emissions"]
    assert "basis_claims" not in KEYS["inferences"]
