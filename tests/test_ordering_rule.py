"""The ordering rule, published as data (#308).

A client that keeps its own append-only claim logs re-derived this engine's
ordering rule and got it wrong: two of its readers answered "over what span was
this sent" by taking the first and last elements of a log, which is ARRIVAL
order, and a third sorted. One screen described one log two ways, and the wrong
answer was in the sentence stating what a processor already holds.

The interesting part is not the bug. The engine had settled this exact question
across several contract versions and expressed it only in Python, so a consumer
could re-derive it, hand-port it, or not hold claims at all. The third is the
honest answer and is where that client is heading, but it is not reachable
while the engine does not stamp client-held claims.

WHY THE FAILURE IS QUIET. Position and date agree on every log appended once,
in order, on one device - which is every log anyone has today. They stop
agreeing exactly when a log is restored from backup or merged across devices,
which is the moment someone is already having a bad day.

THE PREMISE IS OFF IN ONE DETAIL and it is worth recording. The issue says the
read model "already carries `line_shape` so a client can conform without
guessing a schema". There is no such identifier anywhere in this repo -
measured. The thing it is reaching for is `api.schema()`, whose `generations`
map versions what the prose calls the line shape. So the rule goes there, which
is the same place and reaches CLI and MCP for free.
"""

from __future__ import annotations

import json

from vitai.api import schema
from vitai.clocks import ORDERING_RULE, order_key, ordering_rule
from vitai.schema import KEYS

EARLY = "2030-05-01T06:00:00Z"
LATE = "2030-05-01T18:00:00Z"


def row(value: float, stamped: str | None, when: str = "2030-05-01") -> dict:
    return {**{k: None for k in KEYS["thresholds"]}, "date": when,
            "key": "steps_floor", "value": value, "change_kind": "change",
            "set_by": "athlete", "recorded_at": stamped}


# --- the rule is the comparator, not a description of it ------------------------

def test_ordering_rule_is_the_comparator():
    """THE CONTROL THIS WHOLE ISSUE TURNS ON. A published rule that disagrees
    with the engine is worse than none, because a client conforms to it and
    diverges - which is the failure being fixed, one level up.

    So every clause is executed against `order_key` rather than read."""
    rule = ordering_rule()

    # sort_on: the named field decides, ahead of everything else.
    a = row(1, LATE, when="2030-04-01")
    b = row(2, EARLY, when="2030-05-01")
    assert rule["sort_on"] == "date"
    assert [r["value"] for r in sorted([b, a], key=order_key)] == [1, 2], (
        "an earlier date wins even when written later")

    # then_on: with the same valid time, the named field breaks the tie.
    assert rule["then_on"] == "recorded_at"
    late, early = row(9, LATE), row(7, EARLY)
    assert [r["value"] for r in sorted([late, early], key=order_key)] == [7, 9]

    # absent_transaction_time_sorts: before.
    assert rule["absent_transaction_time_sorts"] == "before"
    assert [r["value"] for r in sorted([row(9, LATE), row(7, None)],
                                       key=order_key)] == [7, 9]

    # transaction_time_compared_as: instant, not text.
    assert rule["transaction_time_compared_as"] == "instant"
    east = row(9, "2030-05-01T23:30:00+02:00")
    utc = row(7, "2030-05-01T22:00:00+00:00")
    assert [r["value"] for r in sorted([east, utc], key=order_key)] == [9, 7], (
        "later by the wall clock, earlier by when it was written")

    # position_in_file_is_not_order: the client's actual bug.
    assert rule["position_in_file_is_not_order"] is True
    written = [row(9, LATE), row(7, EARLY)]
    assert [r["value"] for r in sorted(written, key=order_key)] == [7, 9]
    assert [r["value"] for r in sorted(reversed(written), key=order_key)] == [7, 9]


def test_the_clients_bug_is_reproducible_from_the_rule():
    """The specific mistake: reading a log's ENDS as its date range. Appended
    in order it agrees; restored out of order it does not, and the rule says
    which answer is right."""
    log = [row(1, EARLY, when="2030-05-03"), row(2, LATE, when="2030-05-01")]
    by_position = (log[0]["date"], log[-1]["date"])
    ordered = sorted(log, key=order_key)
    by_rule = (ordered[0]["date"], ordered[-1]["date"])
    assert by_position == ("2030-05-03", "2030-05-01"), "arrival order"
    assert by_rule == ("2030-05-01", "2030-05-03"), "what the rule says"
    assert by_position != by_rule


def test_an_unstamped_log_keeps_file_order():
    """The compatibility half, and why `absent sorts before` is not arbitrary:
    a record that predates `recorded_at` has nothing but file order, and taking
    that away would reorder history rather than protect it."""
    log = [row(7, None), row(9, None)]
    assert [r["value"] for r in sorted(log, key=order_key)] == [7, 9]
    assert [r["value"] for r in sorted(reversed(log), key=order_key)] == [9, 7]


# --- what it is, and what it is not --------------------------------------------

def test_every_value_names_a_field_or_an_answer():
    """Not sentences to parse. A consumer builds a comparator from this, so a
    value that needed reading would put the client back where it started."""
    for key, value in ordering_rule().items():
        assert isinstance(value, (str, bool)), (key, value)
        if isinstance(value, str):
            assert " " not in value, (key, value)


def test_the_fields_it_names_exist_on_every_dataset():
    """A rule naming a field the rows do not carry is a rule nobody can
    apply."""
    rule = ordering_rule()
    for dataset, keys in KEYS.items():
        assert rule["sort_on"] in keys, dataset
        assert rule["then_on"] in keys, dataset


def test_it_is_a_copy_so_a_consumer_cannot_edit_the_engines_rule():
    got = ordering_rule()
    got["sort_on"] = "tampered"
    assert ordering_rule()["sort_on"] == "date"
    assert ORDERING_RULE["sort_on"] == "date"


# --- P9: the same answer on every surface ---------------------------------------

def test_it_reaches_the_published_schema():
    assert schema()["ordering"] == ordering_rule()


def test_it_reaches_the_cli_and_the_agent_surface(tmp_path):
    """No new command and no new tool: `schema()` already carries what CLI and
    MCP serialise, which is the route #257 chose for `fields` and for the same
    stated reason - a separate surface is a new place for parity to fail."""
    import contextlib
    import io

    from vitai.cli import main
    from vitai.mcp import call

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["schema", "--json"])
    assert json.loads(buf.getvalue())["ordering"] == ordering_rule()

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    assert call(root, "schema", {})["ordering"] == ordering_rule()
