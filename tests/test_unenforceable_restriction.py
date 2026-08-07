"""A row that says it restricts something and names nothing (#75).

Load-bearing facts keep arriving in prose the engine cannot read, and nothing
compares the two. The sharpest recorded instance: two `medical` rows carried,
in the note, the words "RESTRICTION NOT ENFORCEABLE - no value in the
restricts vocabulary expresses this". They were right - `restricts` was null -
and for three days the record stated a restriction no gate could act on while
the athlete trained inside it.

The note announced its own unenforceability, in English, and that announcement
was itself unreadable.

WORSE THAN A MISSING VALUE, which is the reason this is a finding rather than
a nicety: a missing value is at least legible as missing. Here the record
looks complete, reads correctly to a person, and is silently inert to the
machine.

MECHANICAL, NOT A PROSE SCAN. Reading notes for restriction-shaped sentences
is a heuristic that fires on the wrong rows and misses the quiet ones. Two
shapes state a restriction in a field the engine already reads: a row whose
own `kind` is `restriction`, and a row naming the `precondition` that would
clear one. Both with `restricts` empty.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _medical(v: Vitai, **kw) -> None:
    row = {"date": "2030-05-01", "slug": "hip", "kind": "injury",
           "title": "a hip thing", "body_site": "hip", "severity": "mild",
           "status": "active", "source": "athlete"}
    row.update(kw)
    v.append("medical", row)


def _found(v: Vitai) -> list[dict]:
    return [t for t in v.resolution()["tripwires"]
            if t["kind"] == "unenforceable_restriction"]


def _record(tmp_path: Path) -> Vitai:
    return Vitai(init(tmp_path / "content"))


def test_a_row_whose_kind_is_restriction_must_restrict_something(tmp_path):
    """The row's own declared kind says it is a restriction, and it names
    nothing it restricts."""
    v = _record(tmp_path)
    _medical(v, kind="restriction", note="nothing in the vocabulary fits")

    found, = _found(v)

    assert "names nothing it restricts" in found["detail"]
    assert found["severity"] == "review"


def test_the_append_path_already_refuses_the_precondition_shape(tmp_path):
    """HALF OF THIS WAS ALREADY CLOSED, AND AT A BETTER BOUNDARY. A
    `precondition` with no `restricts` is refused at append - "a check that
    lifts no restriction is just a note" - which is a refusal where the cause
    is rather than a finding in a later report."""
    import pytest

    from vitai.jsonl import DataError

    v = _record(tmp_path)
    with pytest.raises(DataError) as raised:
        _medical(v, precondition="hop-test")

    assert "gates nothing" in str(raised.value)


def test_a_precondition_that_arrived_by_sync_is_still_reported(tmp_path):
    """Which is why the finding keeps that shape too. `append` covers writes
    through this engine and nothing else: the format invites hand editing and
    rows arrive from other writers, and a row that never passed through this
    validation is exactly the one nothing has checked."""
    root = init(tmp_path / "content")
    (root / "data" / "medical.jsonl").write_text(json.dumps({
        "date": "2030-05-01", "slug": "hip", "kind": "injury",
        "title": "a hip thing", "body_site": "hip", "severity": "mild",
        "status": "active", "source": "athlete", "precondition": "hop-test",
        "_gen": 1}) + "\n", encoding="utf-8")

    found, = _found(Vitai(root))

    assert "hop-test" in found["detail"]


def test_an_ordinary_injury_with_no_restriction_is_not_a_finding(tmp_path):
    """Most medical rows restrict nothing and say so by omission. A finding on
    every one of them is the alert that teaches a reader to skip."""
    v = _record(tmp_path)
    _medical(v, note="tweaked it on a hill rep")

    assert _found(v) == []


def test_a_restriction_that_names_what_it_restricts_is_not_a_finding(tmp_path):
    v = _record(tmp_path)
    _medical(v, kind="restriction", restricts="strength")

    assert _found(v) == []


def test_it_does_not_read_the_note(tmp_path):
    """A prose scan would fire on this and it is not a restriction. The
    predicate is the fields the engine already reads, so a note that merely
    talks about restrictions changes nothing."""
    v = _record(tmp_path)
    _medical(v, note="the physio said no restriction is needed, keep training")

    assert _found(v) == []


def test_a_later_row_that_names_the_restriction_clears_it(tmp_path):
    """`medical` is identity-keyed, so a later row for the slug is the repair.
    Reporting the superseded line forever would be a finding that can never
    reach zero, which is the state #245 records people stop reading."""
    v = _record(tmp_path)
    _medical(v, kind="restriction")
    assert _found(v)

    _medical(v, date="2030-05-04", kind="restriction", restricts="strength")

    assert _found(v) == []


def test_the_repair_is_reported_while_it_is_still_the_head(tmp_path):
    """The control for the test above: it clears because the HEAD changed, not
    because any later row of any kind silences it."""
    v = _record(tmp_path)
    _medical(v, kind="restriction")
    _medical(v, slug="knee", kind="injury", body_site="knee")

    assert len(_found(v)) == 1


def test_two_unenforceable_rows_are_two_findings(tmp_path):
    """One per slug: they are two restrictions nobody can act on, and
    collapsing them would hide the second."""
    v = _record(tmp_path)
    _medical(v, kind="restriction")
    _medical(v, slug="shoulder", kind="restriction", body_site="shoulder")

    assert len(_found(v)) == 2


def test_it_says_what_to_do_when_the_vocabulary_cannot_express_it(tmp_path):
    """The pressure runs one way: prose can always express the thing and a
    vocabulary cannot, so the fact lands in the note and the field stays
    empty. Saying only "this is wrong" leaves the writer with the same
    problem."""
    v = _record(tmp_path)
    _medical(v, kind="restriction")

    found, = _found(v)

    assert "gap worth filing" in found["detail"]


def test_the_shipped_record_has_none(tmp_path):
    """Every restriction in every fixture names what it restricts, which is
    why nothing caught this: the corpus exercises the healthy case only."""
    assert _found(Vitai(DEMO)) == []


def test_it_is_a_finding_and_not_a_refusal(tmp_path):
    """The row is legal and the record is not wrong - it is inert. A build
    that refused would make a record unreadable over something the engine
    cannot fix for it."""
    v = _record(tmp_path)
    _medical(v, kind="restriction")

    assert _found(v)
    assert not v.validate()["problems"]
    assert v.build()
