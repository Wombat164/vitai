"""What the engine told the athlete, and when (phase 3, 01-schema 8b).

The asymmetry this dataset closes: retracting an input empties the interval,
but the interval was CONSUMED - verdicts and warnings were computed from it and
acted on. Retraction propagated to the input and stopped, because verdicts are
rebuilt into the database and overwritten on every build, so nothing could
answer "what did the engine tell me last week, and does that still hold".

SURFACED ASSERTIONS ONLY. A computed verdict is rebuildable; an assertion
delivered to a person is an event in the world. That distinction is what most
of this file holds to, and the build-purity test at the bottom is the one that
would catch it being quietly abandoned.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.db import CONTRACT_VERSION
from vitai.schema import CURRENT_GENERATION, KEYS, validate_record


def an_emission(**kw):
    rec = {k: None for k in KEYS["emissions"]}
    rec.update({"date": "2030-05-06", "kind": "verdict",
                "metric": "weight_rate", "week": "2030-05-06",
                "statement": "ON TARGET, losing 0.35 kg/week",
                "policy_asof": "2030-05-06", "contract": "21",
                "surface": "cli", "_gen": CURRENT_GENERATION["emissions"]})
    rec.update(kw)
    return rec


def a_record(tmp_path) -> Path:
    return init(tmp_path / "content")


# --- what the schema will accept ---------------------------------------------

def test_a_well_formed_emission_validates():
    assert validate_record("emissions", an_emission()) == []


def test_the_kind_vocabulary_is_closed():
    """Open vocabularies elsewhere let an athlete write a word nobody
    anticipated. This dataset is written by a program, so an unrecognised kind
    is a consumer bug rather than a person expressing themselves."""
    assert validate_record("emissions", an_emission(kind="vibes"))
    for kind in ("verdict", "warning", "plan", "requirement"):
        assert validate_record("emissions", an_emission(kind=kind)) == []


@pytest.mark.parametrize("field", ["statement", "surface", "policy_asof"])
def test_an_assertion_that_cannot_say_what_it_asserted_is_refused(field):
    """Worse than no row: it records that something was said and loses what."""
    assert validate_record("emissions", an_emission(**{field: None}))
    assert validate_record("emissions", an_emission(**{field: "   "}))


def test_the_contract_at_emission_is_required():
    """A replay that cannot know which shape was in force cannot know whether
    the statement still means what it meant."""
    assert validate_record("emissions", an_emission(contract=None))


def test_basis_claims_takes_claim_ids():
    assert validate_record("emissions",
                           an_emission(basis_claims=["weight:2030-05-01:scale"])) == []
    assert validate_record("emissions", an_emission(basis_claims="one-string"))
    assert validate_record("emissions", an_emission(basis_claims=["nope"]))
    # Absent is legal: an assertion resting on nothing recordable still
    # happened, and refusing it would lose the event to gain a field.
    assert validate_record("emissions", an_emission(basis_claims=None)) == []


# --- the write path ----------------------------------------------------------

def test_assert_delivery_stamps_what_the_engine_owns(tmp_path):
    root = a_record(tmp_path)
    assert Vitai(root).assert_delivery([{
        "date": "2030-05-06", "kind": "verdict", "metric": "weight_rate",
        "statement": "ON TARGET", "policy_asof": "2030-05-06"}],
        surface="cli") == 1

    row = json.loads((root / "data" / "emissions.jsonl").read_text().strip())
    assert row["contract"] == CONTRACT_VERSION
    assert row["surface"] == "cli"
    assert row["recorded_at"]          # machine-stamped, not caller-supplied


@pytest.mark.parametrize("field", ["contract", "recorded_at", "device",
                                   "surface", "nonsense"])
def test_a_caller_cannot_supply_what_the_engine_stamps(tmp_path, field):
    """An allowlist, not a denylist. The denylist version of this on `claim`
    let `supersedes` through - a forgotten key on a write path is a capability
    nobody decided to grant. A caller that could name its own contract version
    could file an assertion as made under a shape that was never in force."""
    with pytest.raises(ValueError):
        Vitai(a_record(tmp_path)).assert_delivery([{
            "date": "2030-05-06", "kind": "verdict", "statement": "ON TARGET",
            "policy_asof": "2030-05-06", field: "x"}], surface="cli")


def test_an_assertion_names_who_delivered_it(tmp_path):
    """An assertion whose deliverer is unknown cannot be attributed when it
    turns out to have been wrong."""
    with pytest.raises(ValueError):
        Vitai(a_record(tmp_path)).assert_delivery(
            [{"date": "2030-05-06", "kind": "verdict", "statement": "x",
              "policy_asof": "2030-05-06"}], surface="")


def test_delivering_nothing_writes_nothing(tmp_path):
    root = a_record(tmp_path)
    assert Vitai(root).assert_delivery([], surface="cli") == 0
    assert (root / "data" / "emissions.jsonl").read_text() == ""


def test_two_assertions_on_one_day_are_two_events(tmp_path):
    """Pass-through, never resolved. Elsewhere two rows for one date and source
    contest a value; here they are two things that were said, and collapsing
    them would lose one."""
    root = a_record(tmp_path)
    v = Vitai(root)
    for statement in ("ON TARGET", "BEHIND"):
        v.assert_delivery([{"date": "2030-05-06", "kind": "verdict",
                            "statement": statement,
                            "policy_asof": "2030-05-06"}], surface="cli")
    assert len(Vitai(root).dataset("emissions")) == 2


# --- the rule the rest of this rests on --------------------------------------

def test_a_build_never_writes_an_emission(tmp_path):
    """BUILD IS A PURE FUNCTION OF THE RECORD, and this dataset is the first
    thing that could plausibly tempt it otherwise.

    Logging at computation rather than at delivery would duplicate the derived
    tier into the ground-truth tier, and a build that appends to the record
    makes a rebuild non-idempotent - the record-is-input, database-is-disposable
    split everything else here stands on. It would also be unbounded: every
    rebuild re-emitting the full verdict set.

    Asserted over the WHOLE record rather than over emissions alone, because
    the failure this guards against is a build writing anything at all.
    """
    root = a_record(tmp_path)
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": f"2030-05-{d:02d}", "kg": 80.0 - d * 0.1, "source": "scale",
         "note": None} for d in range(1, 15)]) + "\n", encoding="utf-8")
    Vitai(root).assert_delivery([{"date": "2030-05-06", "kind": "verdict",
                                  "statement": "ON TARGET",
                                  "policy_asof": "2030-05-06"}], surface="cli")

    before = {f.name: f.read_bytes() for f in (root / "data").glob("*.jsonl")}
    Vitai(root).build()
    Vitai(root).build()
    after = {f.name: f.read_bytes() for f in (root / "data").glob("*.jsonl")}
    assert before == after


def test_an_emission_reaches_the_read_model(tmp_path):
    root = a_record(tmp_path)
    Vitai(root).assert_delivery([{
        "date": "2030-05-06", "kind": "verdict", "statement": "ON TARGET",
        "basis_claims": ["weight:2030-05-01:scale"],
        "policy_asof": "2030-05-06"}], surface="cli")
    db = Vitai(root).build()
    con = sqlite3.connect(db if isinstance(db, (str, Path))
                          else root / "derived" / "health.db")
    try:
        stored, contract = con.execute(
            "SELECT basis_claims, contract FROM emissions").fetchone()
    finally:
        con.close()
    # A JSON array in a TEXT column, like `derived_from`; and `contract` is a
    # version STRING, which REAL affinity would have turned into a float.
    assert json.loads(stored) == ["weight:2030-05-01:scale"]
    assert contract == CONTRACT_VERSION


# --- the doors, both of them -------------------------------------------------

def test_a_correction_cannot_retire_an_assertion(tmp_path):
    """An emission is an EVENT. A later row cannot make an earlier one not
    have been said, and the engine forgetting what it told someone is the
    exact failure this dataset exists to prevent.

    Sharp here for a structural reason: `line_key` falls back to
    `date/source`, and emissions has no `source`, so every assertion on one
    day shares the key `"<date>/"`. One `supersedes` line naming it retired
    the whole day.
    """
    root = a_record(tmp_path)
    v = Vitai(root)
    for statement in ("ON TARGET", "BEHIND"):
        v.assert_delivery([{"date": "2030-05-06", "kind": "verdict",
                            "statement": statement,
                            "policy_asof": "2030-05-06"}], surface="cli")

    with (root / "data" / "emissions.jsonl").open("a", encoding="utf-8") as f:
        # A LATER `recorded_at` matters: `retire` only lets a later line
        # supersede, so a row without one sorts ahead of its targets and the
        # attack fails for a reason that has nothing to do with the guard.
        f.write(json.dumps({
            "date": "2030-05-06", "kind": "verdict", "statement": "MINE",
            "policy_asof": "2030-05-06", "contract": "21", "surface": "other",
            "recorded_at": "2031-01-01T00:00:00+00:00",
            "supersedes": "2030-05-06/"}) + "\n")

    assert len(Vitai(root).dataset("emissions")) == 3


@pytest.mark.parametrize("door", ["append", "append_many"])
def test_the_generic_append_is_not_a_door_into_emissions(tmp_path, door):
    """`assert_delivery` stamps the contract in force and the delivering
    surface. A row arriving through the generic append could name its own,
    which is the attack the docstring warns about arriving one method along."""
    v = Vitai(a_record(tmp_path))
    row = {"date": "2030-05-06", "kind": "verdict", "statement": "x",
           "policy_asof": "2030-05-06", "contract": "5", "surface": "spoofed"}
    with pytest.raises(ValueError):
        getattr(v, door)("emissions", row if door == "append" else [row])


def test_the_other_datasets_still_append_normally(tmp_path):
    """The guard is for emissions alone; blocking every append would be a
    cure worse than the disease."""
    v = Vitai(a_record(tmp_path))
    assert v.append("weight", {"date": "2030-05-06", "kg": 80.0,
                               "source": "scale"})


# --- shapes, not only presence -----------------------------------------------

def test_a_policy_date_that_is_not_a_date_is_refused():
    """"banana" satisfies "is not blank" and satisfies nothing else. The
    replay that reads this has to resolve it to a date, and discovering that
    at replay time is discovering it after the assertion was acted on."""
    assert validate_record("emissions", an_emission(policy_asof="banana"))


def test_the_week_is_the_monday_the_engine_buckets_on():
    assert validate_record("emissions", an_emission(week="2030-05-06")) == []
    assert validate_record("emissions", an_emission(week="2030-05-07"))
    assert validate_record("emissions", an_emission(week="banana"))


def test_the_surface_is_a_slug():
    assert validate_record("emissions", an_emission(surface="My CLI!!"))
    assert validate_record("emissions", an_emission(surface="loadline")) == []


def test_the_surface_is_stored_stripped(tmp_path):
    root = a_record(tmp_path)
    Vitai(root).assert_delivery([{"date": "2030-05-06", "kind": "verdict",
                                  "statement": "x",
                                  "policy_asof": "2030-05-06"}],
                                surface="  cli  ")
    assert Vitai(root).dataset("emissions")[0]["surface"] == "cli"
