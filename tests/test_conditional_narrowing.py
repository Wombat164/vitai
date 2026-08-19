"""A narrowing that narrowed for some records and not others (#464).

Contract 54 declares `meta:supersedes_seq` `narrowed`, which forces a move for
anyone who authors that field. Its own migration note says "Nothing required,
and every existing correction keeps working", because `jsonl._addressed`'s rule
2 - a seat with one occupant is that occupant - covers "every record written
before this contract and every single-device record after it, unchanged".

Both sentences are in `README.md`, about seventy lines apart, and they disagree.
A private content repo of 5,237 rows, every one with `device: None`, asked
mechanically, was told MUST MOVE by a rule that cannot apply to it: a seat can
only be contested where two machines wrote it.

WHAT SHIPS IS A CONDITION, AND THE LAZY ANSWER IS INVERTED ON PURPOSE. #452
refused a "must a client move" field because its safe answer, `yes`, costs the
author nothing and so wins. A condition has the opposite temptation - "does not
apply to you" is the answer that costs a client nothing - so a conditional row
STILL FORCES A MOVE until the engine has evaluated the condition against a real
record. Silence never excuses.

THE CONTROL AT THE BOTTOM IS THE ONE THAT MATTERS. No record in this
repository has more than one device, so the condition is TRUE everywhere here
and an exemption that is never observed to fail is a permanent free pass with a
name. A two-device record is built to prove it can fail.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vitai import contracts
from vitai.api import Vitai, init

DEMO = "examples/demo"
PERSONAS = Path(__file__).parent / "fixtures" / "personas"

# The client that met this: it authors lines, so `meta` is its whole read-set.
AUTHOR_READS = ["meta"]


def _one_writer(tmp_path):
    """A record written by a single unnamed machine, which is every record
    this repository holds and every record written before contract 54."""
    root = init(tmp_path / "one")
    v = Vitai(root)
    v.append("weight", {"date": "2030-05-01", "kg": 80.0})
    v.append("weight", {"date": "2030-05-02", "kg": 79.8})
    return v


def _two_writers(tmp_path):
    """A record two machines have written, where a seat can be contested."""
    root = init(tmp_path / "two")
    data = Path(root) / "data"
    for device, kg in (("laptop", 80.0), ("phone", 79.9)):
        (data / f"weight.{device}.jsonl").write_text(
            json.dumps({"date": "2030-05-01", "kg": kg, "device": device,
                        "seq": 0, "_gen": 13}) + "\n", encoding="utf-8")
    return Vitai(root)


# ------------------------------------------------------------------ the defect

def test_the_declaration_can_carry_a_condition():
    """The gap, asserted rather than described. Contract 54 narrowed a field
    for records with two writers and for no others, and a change kind has
    nowhere to put the qualifier."""
    row = [r for r in contracts.touched(54)
           if r["surface"] == "meta:supersedes_seq"][0]
    assert row.get("unless"), (
        "contract 54 forces a move on every author of `supersedes_seq`, "
        "including the single-device records its own migration note says need "
        "do nothing")


def test_a_condition_names_something_the_engine_publishes():
    """Not a language. A condition resolves to a predicate this engine already
    exposes, the same way a surface resolves to a table or a method, and a
    test refuses one that does not - which is what stops the vocabulary
    growing into prose."""
    assert contracts.CONDITIONS, "an empty vocabulary asserts nothing"
    for name in contracts.CONDITIONS:
        assert contracts.unresolved_condition(name) is None, name
    assert contracts.unresolved_condition("no-such-condition") is not None


def test_every_declared_condition_is_used_and_every_used_one_is_declared():
    """Both directions, for the reason the change kinds give: an unused member
    of a closed vocabulary is vacuity, and an undeclared one is a typo that
    would silently excuse a client."""
    used = {r.get("unless") for rows in contracts.declaration().values()
            for r in rows if r.get("unless")}
    assert used == set(contracts.CONDITIONS), (used, set(contracts.CONDITIONS))


# ------------------------------------------------- silence never excuses

def test_an_unevaluated_condition_still_forces_the_move():
    """THE LOAD-BEARING RULE. `contracts.assess` has no record, so it cannot
    know whether the condition holds - and the answer to "I do not know" is
    move, for the reason an unstated read-set gets the same answer."""
    verdict = contracts.assess(52, 54, AUTHOR_READS)
    assert verdict["must_move"] is True
    forced = [r["surface"] for r in verdict["because"]]
    assert "meta:supersedes_seq" in forced
    conditional = [r["surface"] for r in verdict["conditional"]]
    assert conditional == ["meta:supersedes_seq"]


def test_the_condition_is_named_back_so_a_client_knows_to_ask():
    """A row that quietly carried a condition nobody could see would be worse
    than none: the client would absorb a contract it did not need, which is
    the cost #450 measured."""
    row = contracts.assess(52, 54, AUTHOR_READS)["conditional"][0]
    assert row["unless"] in contracts.CONDITIONS
    assert contracts.CONDITIONS[row["unless"]]["says"]


# ------------------------------------------------ evaluated against a record

def test_a_single_writer_record_is_excused(tmp_path):
    """The record #464 was raised on: one machine, so no seat can be contested
    and rule 2 retires what it always retired."""
    out = _one_writer(tmp_path).contract_impact(52, reads=AUTHOR_READS)
    assert out["must_move"] is False
    assert [r["surface"] for r in out["excused"]] == ["meta:supersedes_seq"]
    assert out["excused"][0]["unless"] == "one-writer"


def test_a_two_writer_record_is_not_excused(tmp_path):
    """THE CONTROL ON THE WHOLE FEATURE. An exemption that no record can fail
    is a free pass with a name on it, and no record in this repository has two
    devices - so one is built here."""
    engine = _two_writers(tmp_path)
    assert len(engine.devices()) == 2, engine.devices()
    out = engine.contract_impact(52, reads=AUTHOR_READS)
    assert out["must_move"] is True
    assert out["excused"] == []
    assert "meta:supersedes_seq" in [r["surface"] for r in out["because"]]


def test_a_read_set_that_does_not_author_lines_is_unaffected(tmp_path):
    """A consumer that reads the built model never had this row in its
    intersection and still does not. The condition must not become a second
    route to a verdict it was never part of."""
    out = _one_writer(tmp_path).contract_impact(52, reads=["weight.kg"])
    assert out["must_move"] is False
    assert out["excused"] == []


def test_the_rooted_answer_and_the_rootless_one_differ_only_by_the_excusal(tmp_path):
    """Everything else about the verdict has to be the same object, or the two
    doors answer different questions and a client can pick the kind one."""
    rooted = _one_writer(tmp_path).contract_impact(52, reads=AUTHOR_READS)
    rootless = contracts.assess(52, 54, AUTHOR_READS)
    assert rooted["touched"] == rootless["touched"]
    assert rooted["conditional"] == rootless["conditional"]
    assert rooted["must_move"] != rootless["must_move"]


# --------------------------------------------------------------- the corpus

def test_no_record_in_this_repository_can_fail_the_condition():
    """Pinned, because it is the reason the control above is built by hand.

    A condition that is true everywhere it has been asked is indistinguishable
    from an exemption nobody checks. This is the third time in three days that
    a corpus could not exhibit the phenomenon a check is about - see
    `docs/persona-doctrine.md`'s sixth property, and #462.
    """
    counts = {}
    for root in [Path(DEMO)] + sorted(
            p for p in PERSONAS.iterdir() if p.is_dir() and p.name != "_gen"):
        counts[root.name] = len(Vitai(root).devices())
    assert max(counts.values()) <= 1, counts
    assert set(counts.values()) <= {0, 1}


# --------------------------------------------------------------------- P9

def test_the_cli_evaluates_the_condition_only_when_given_a_record(tmp_path):
    root = str(Path(_one_writer(tmp_path).root))
    bare = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "contract-impact", "--since", "52",
         "--reads", "meta", "--json"], capture_output=True, text=True)
    rooted = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "contract-impact", "--since", "52",
         "--reads", "meta", "--root", root, "--json"],
        capture_output=True, text=True)
    assert bare.returncode == 1, bare.stderr
    assert rooted.returncode == 0, rooted.stderr
    assert json.loads(bare.stdout)["must_move"] is True
    assert json.loads(rooted.stdout)["must_move"] is False
