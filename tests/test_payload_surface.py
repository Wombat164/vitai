"""The fourth surface a client reads, and the reads nobody checked (#453).

#452 built a declaration in three grammars - `table`, `meta:`, `report:` - and
#454 was the first change that had nothing to declare against: it moved the
published vocabulary without moving the contract, correctly, because the
vocabulary is not contract-versioned and two precedents say so.

The gap was filed as "the declaration cannot name the `schema()` payload". The
first real consumer measured it, and the gap is one instance of something
larger: NOTHING EVER CHECKED THAT A CLIENT'S READ NAMES A REAL SURFACE. A
read-set of pure nonsense earned "you may stay", which is the fail-open this
module's own docstring says it exists to prevent, sitting one argument to the
left of the one it closed.

So this file gates three things:

1. a read that names nothing published is REFUSED, not ignored;
2. the payload is nameable, so a client can say it reads it and be believed;
3. the payload carries a DIGEST, because a surface that moves between contract
   numbers cannot be declared against one.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from vitai import contracts
from vitai.api import schema


# The two contracts the live consumer is actually asking about: it is pinned
# at 52 and this engine emits 54. Used throughout so the numbers in these
# tests are the numbers in the field rather than convenient ones.
HERE, HEAD = 52, 54


def test_a_read_set_that_names_nothing_does_not_earn_a_stay():
    """THE FAIL-OPEN, and it is the same one `assess` already closed once.

    An empty read-set was made to mean "move", because silence must not mean
    safety. A read-set of typos is silence with extra characters: it matches
    no surface, so every touched row lands in `not_yours`, and the verdict
    comes back "may stay" over a client that told the engine nothing it could
    understand.

    `weght.kg` is what this looks like in the field - one transposition in a
    map a person maintains - and the answer it currently gets is the
    reassuring one.
    """
    with pytest.raises(ValueError) as e:
        contracts.assess(HERE, HEAD, ["weght.kg", "sesions"])
    assert "weght.kg" in str(e.value)
    assert "sesions" in str(e.value)


def test_one_bad_read_among_good_ones_is_still_refused():
    """Not "most of it resolved, so answer anyway".

    A client whose map is 29 parts right is the dangerous case, not the safe
    one: the verdict is computed over 29 surfaces and PRESENTED as the answer
    for 30. Partial is refused for the reason the floor is refused - a partial
    answer to "may I stay" has the same shape as a wrong one.
    """
    with pytest.raises(ValueError) as e:
        contracts.assess(HERE, HEAD, ["weight.kg", "daily.steps", "not_a_table"])
    assert "not_a_table" in str(e.value)
    assert "weight.kg" not in str(e.value), "a resolving read was named as a problem"


def test_a_read_set_that_resolves_is_answered_as_before():
    """The control on the check above: validation must not eat the verdict."""
    v = contracts.assess(HERE, HEAD, ["weight.kg", "daily.steps"])
    assert v["reads_stated"] is True
    assert v["must_move"] is False
    assert [r["surface"] for r in v["touched"]] == [
        "overlaps", "comparability.overlap_ref",
        "meta:supersedes_device", "meta:supersedes_seq"]


def test_a_property_is_a_published_read_surface():
    """An engine-side bug the live read-set found.

    `unresolved` asked `callable(getattr(Vitai, head))` and a `property`
    object is not callable - so `report:policy`, which a real client reads and
    a real engine publishes, was reported as naming nothing. The check was
    looking for a function where the question is whether a consumer can reach
    it.
    """
    assert contracts.unresolved("report:policy") is None
    assert contracts.unresolved("report:status_line") is None
    assert contracts.unresolved("report:no_such_method") is not None
    assert contracts.unresolved("report:_private") is not None


def test_a_namespace_written_bare_resolves():
    """`_covers` has always accepted a bare `meta` or `report` as naming the
    whole namespace. `unresolved` did not, so the two halves of the same
    grammar disagreed and only the half nothing called was strict."""
    for bare in ("meta", "report", "payload"):
        assert contracts.unresolved(bare) is None, bare


def test_the_payload_is_nameable():
    """The gap #453 was filed for.

    `fields`, `ordering`, `phase_rule`, `session_types`, `pending_verdicts`,
    `ambiguous_aliases`, `impact`, `builds` - and inside `fields`, the
    `aliases`, `units` and `display_name` a client renders. None of it could
    be written down before this.
    """
    for named in ("payload:fields", "payload:fields.aliases",
                  "payload:fields.display_name", "payload:fields.units",
                  "payload:session_types", "payload:ambiguous_aliases",
                  "payload:impact.floor", "payload:builds.released"):
        assert contracts.unresolved(named) is None, named


def test_a_payload_name_that_is_not_published_is_refused():
    """Fail-closed, and per top-level key rather than over one flat pile: a
    sub-name that exists under `impact` must not resolve under `fields`."""
    assert contracts.unresolved("payload:no_such_key") is not None
    assert contracts.unresolved("payload:fields.no_such_spec") is not None
    assert contracts.unresolved("payload:fields.floor") is not None


def test_the_payload_names_come_from_the_payload():
    """Derived, not restated. A catalogue kept beside the payload would agree
    with it by construction and would catch nothing - the same argument
    `catalogue` already makes for tables."""
    assert set(contracts.catalogue()["payload"]) == set(schema())


def test_no_contract_declares_a_payload_surface():
    """THE DESIGN RULE, gated rather than written down.

    The payload is not contract-versioned - #350 moved eight aliases out of it
    with no bump, #331 added `display_name` to it with no bump, #400 moved six
    words in it with no bump - so a contract row that named a payload surface
    would be claiming a versioning this engine does not do. The grammar exists
    for the READ-SET, so a client can say what it reads and be told the
    contract cannot answer for it.
    """
    for contract, rows in contracts.declaration().items():
        for row in rows:
            assert contracts._namespace(row["surface"]) != "payload", (
                f"contract {contract} declares {row['surface']}, and the "
                f"payload does not move with the contract number")


def test_a_payload_read_is_named_back_and_does_not_move_the_verdict():
    """What a client gets for declaring one.

    Not silence, which would let it believe the contract verdict covered the
    payload too, and not a forced move, which would make every vocabulary fix
    a migration and rebuild the treadmill #450 measured. It is told the engine
    understood the read and that the answer for it is the digest.
    """
    v = contracts.assess(HERE, HEAD, ["weight.kg", "payload:fields.aliases"])
    assert v["payload_reads"] == ["payload:fields.aliases"]
    assert v["must_move"] is False
    assert v["payload_digest"] == contracts.payload_digest()


def test_every_verdict_carries_the_digest():
    """Including one where no payload read was declared: the client that has
    not thought about the payload is the one that needs telling it exists."""
    v = contracts.assess(HERE, HEAD, ["weight.kg"])
    assert v["payload_reads"] == []
    assert v["payload_digest"] == contracts.payload_digest()


def test_the_payload_carries_its_own_digest():
    """Published where the payload is, because the client that emits against
    this engine has the payload in hand and needs no second call to record
    what it emitted against."""
    assert schema()["payload_digest"] == contracts.payload_digest()
    assert len(contracts.payload_digest()) == 16


def test_the_digest_does_not_feed_itself():
    """A checksum inside the thing it sums, so the exclusion is load-bearing
    rather than tidy: leave it in and the value depends on itself."""
    payload = schema()
    assert "payload_digest" in payload
    assert contracts.payload_digest() == contracts._digest_of(payload)
    assert contracts._digest_of(payload) == contracts._digest_of(
        {k: v for k, v in payload.items() if k != "payload_digest"})


def test_the_digest_moves_when_the_published_vocabulary_moves(monkeypatch):
    """The whole point. #400 changed four alias entries and two display names
    in a live consumer's shipped artifact and nothing anywhere moved."""
    import vitai.api as api
    before = contracts.payload_digest()
    original = api.ambiguous_aliases
    monkeypatch.setattr(api, "ambiguous_aliases",
                        lambda: {**original(), "beats": ["avg_hr", "rhr"]})
    assert contracts.payload_digest() != before


def test_the_digest_stands_still_for_provenance(monkeypatch):
    """`engine` and `builds.this` are the same string and the docstring
    already says neither is a gate: they move for a docs fix and stand still
    while the shape moves. A digest that carried them would cry wolf on every
    release and a client would learn to ignore it, which is worse than not
    having one."""
    import vitai.api as api
    import vitai.builds as builds
    before = contracts.payload_digest()
    monkeypatch.setattr(api, "__version__", "99.99.99")
    monkeypatch.setattr(builds, "__version__", "99.99.99")
    payload = schema()
    assert payload["engine"] == "99.99.99"
    assert payload["builds"]["this"] == "99.99.99"
    assert contracts.payload_digest() == before


def test_the_digest_is_the_same_in_a_second_process():
    """Set iteration and hash randomisation are how a digest becomes a coin
    toss, and a flapping digest is a stale-payload alarm that means nothing."""
    code = ("import sys; sys.path.insert(0, 'src');"
            "from vitai import contracts; print(contracts.payload_digest())")
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin"},
                           check=True).stdout.strip()
            for seed in ("0", "1", "12345")}
    assert len(runs) == 1, runs
    assert runs == {contracts.payload_digest()}


def test_the_payload_is_json_and_stays_json():
    """The digest hashes serialised JSON with no fallback encoder on purpose.
    A `default=` would let an unserialisable value through and hash its
    `repr`, which on most objects carries a memory address - a digest that
    changes every run, reported as the payload moving."""
    json.dumps(schema(), sort_keys=True)


def test_the_validation_can_fail():
    """The control on the control. A resolver that returned None for
    everything would satisfy every test above and check nothing."""
    assert contracts.unresolved("definitely_not_a_table") is not None
    assert contracts.unresolved("weight.definitely_not_a_column") is not None
    assert contracts.unresolved("meta:definitely_not_a_meta_key") is not None
