"""The ordering rule, checked where it is used and where it is not.

`clocks.order_key` orders rows by valid time, then by whether a transaction
time exists, then by that instant. Eight sort sites across FOUR modules use it
- `clocks`, `jsonl`, `contributions` and `policy`; `schema` re-exports it and
never sorts.

WHAT THIS FILE IS AND IS NOT, corrected after review. The first version claimed
to add use-site coverage and did not: the two sites it reaches, `policy._in_force`
and `jsonl.heads`, were ALREADY witnessed by `test_clocks.py`, whose four tests
assert through `state()` and `heads()` rather than through the key. Three of its
tests could not fail at all, because `Vitai.dataset()` and `build()` are ordered
by `devices.merge` - a second, hand-written implementation of the same doctrine
- and never touch `order_key`. Those are gone.

WHAT SURVIVES IS THE GAP THE REVIEW FOUND. Replacing `stamp_instant(stamp)`
with `str(stamp)` - comparing transaction times as TEXT - passed all 2275
tests, and it is the one property `order_key`'s own docstring spends three
lines defending: "Comparing stamps as text orders two rows written either side
of a timezone change by wall clock rather than by when they were written." An
athlete who flies east gets the wrong threshold in force, and nothing said so.

AND THE SECOND IMPLEMENTATION. `devices.merge` re-derives the doctrine by hand,
knowingly and with a comment saying so, and it is the sort that actually orders
every dataset a consumer reads. Two implementations of one rule is the shape
this repo keeps paying for; the sweep in #323 cannot see this pair because they
are not byte-identical. Both are pinned here.
"""

from __future__ import annotations

from pathlib import Path

from vitai.clocks import order_key
from vitai.schema import KEYS

# ONE DAY, TWO LINES, WRITTEN OUT OF ORDER. The later line by `recorded_at`
# sits FIRST in the file, so anything reading file position gets the stale
# answer and anything reading the record gets the current one.
EARLY = "2030-05-01T06:00:00Z"
LATE = "2030-05-01T18:00:00Z"


def threshold(value: float, stamped: str, reason: str) -> dict:
    return {**{k: None for k in KEYS["thresholds"]}, "date": "2030-05-01",
            "key": "steps_floor", "value": value, "change_kind": "change",
            "set_by": "athlete", "reason": reason, "recorded_at": stamped}


# --- the rule itself -----------------------------------------------------------

def test_the_later_stamp_sorts_last_however_the_file_is_written():
    rows = [threshold(9000, LATE, "later"), threshold(7000, EARLY, "earlier")]
    assert [r["value"] for r in sorted(rows, key=order_key)] == [7000, 9000]
    assert [r["value"] for r in sorted(reversed(rows), key=order_key)] == [7000, 9000]


# --- the two sites it reaches, which `test_clocks.py` already reached ---------

def test_which_threshold_is_in_force_comes_from_the_record():
    """`policy._in_force` decides which policy a week is judged against. Read
    by file position it would take whichever line a formatter left last."""
    from vitai.policy import state

    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]
    for order in (rows, list(reversed(rows))):
        held = state([], order, "2030-05-02").thresholds
        assert held["steps_floor"] == 9000, order[0]["reason"]


def test_which_goal_is_live_comes_from_the_record():
    """The same reader, over `goals`, where the identity is the slug."""
    from vitai.policy import state

    def goal(target: float, stamped: str) -> dict:
        return {**{k: None for k in KEYS["goals"]}, "date": "2030-05-01",
                "slug": "lean", "metric": "kg", "target": target,
                "direction": "down", "set_by": "athlete",
                "lifecycle_status": "active", "recorded_at": stamped}

    rows = [goal(68.0, LATE), goal(72.0, EARLY)]
    for order in (rows, list(reversed(rows))):
        live = state(order, [], "2030-05-02").goals
        assert [g["target"] for g in live] == [68.0]


def test_the_current_line_for_an_identity_comes_from_the_record():
    """`jsonl.heads` picks the CURRENT line per identity, which is what an
    editor of a policy row is changing. Its docstring says "the last line for a
    slug in file order", and the sort underneath it is what makes that mean
    the last line the RECORD puts last.

    The correction test above did not reach this: it asserts the order a
    dataset is returned in, and this decides which single line wins."""
    from vitai.jsonl import heads

    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]
    for order in (rows, list(reversed(rows))):
        head = heads(order, "thresholds")["steps_floor"]
        assert head["value"] == 9000, order[0]["reason"]


def test_an_unstamped_file_keeps_the_order_it_had(tmp_path):
    """The compatibility half, and the reason the key has three parts. A
    record that predates `recorded_at` has nothing but file order, and taking
    that away would reorder history rather than protect it."""
    rows = [threshold(7000, None, "first written"),
            threshold(9000, None, "second written")]
    for r in rows:
        r["recorded_at"] = None
    assert [r["value"] for r in sorted(rows, key=order_key)] == [7000, 9000]
    assert [r["value"] for r in sorted(reversed(rows), key=order_key)] == [9000, 7000]


def test_a_stamped_line_wins_over_an_unstamped_one_on_the_same_day():
    """`absent sorts BEFORE present`, so a legacy line yields to a line that
    says when it was written rather than to whichever came last in the file."""
    rows = [threshold(9000, LATE, "stamped"), threshold(7000, None, "legacy")]
    rows[1]["recorded_at"] = None
    assert [r["reason"] for r in sorted(rows, key=order_key)] == ["legacy",
                                                                  "stamped"]


def test_valid_time_beats_transaction_time(tmp_path):
    """The two clocks are not interchangeable and the order between them is
    the doctrine. A line for an EARLIER day, written later, is still an
    earlier day - backfilling a week does not rewrite it."""
    backfilled = threshold(7000, LATE, "entered late, for an earlier day")
    backfilled["date"] = "2030-04-01"
    current = threshold(9000, EARLY, "entered early, for today")
    assert [r["value"] for r in sorted([current, backfilled], key=order_key)] \
        == [7000, 9000]


# --- and the guard against this happening again --------------------------------

# THE OTHER IMPLEMENTATION OF THIS RULE, declared. `devices.merge` re-derives
# the ordering doctrine by hand - `(stamp is not None, stamp_instant(stamp) or
# _NO_INSTANT, device, position)` - knowingly, with a comment saying it is
# copying the canon, and it is the sort that actually orders every dataset a
# consumer reads. #323's duplicate sweep cannot see the pair, because they are
# not byte-identical: one sorts records, the other sorts a device's stream.
#
# Listed rather than merged, because they answer different questions and the
# merge has a device and a position in its key. What must not happen is the two
# drifting on the half they share, which the next test pins.
SECOND_IMPLEMENTATION = ("devices.py", "merge")


def test_the_hand_written_sort_still_agrees_on_the_half_they_share():
    """RUN, not grepped. Both implementations must put an unstamped row before
    a stamped one and both must compare INSTANTS rather than text - a fix to
    one that misses the other is how a record starts answering two ways, and
    `devices.merge` is the sort that actually orders every dataset a consumer
    reads.

    The first version of this checked the source for `stamp_instant`, which a
    mutation walked straight through: reading a function's text is not running
    it."""
    from vitai.devices import merge

    east = threshold(9000, "2030-05-01T23:30:00+02:00", "before the flight")
    utc = threshold(7000, "2030-05-01T22:00:00+00:00", "after landing")
    legacy = threshold(5000, None, "unstamped")
    legacy["recorded_at"] = None

    merged = merge([("phone", [east]), ("laptop", [utc])], "thresholds")
    assert [r["value"] for r in merged] == [9000, 7000], "instants, not text"

    with_legacy = merge([("phone", [legacy]), ("laptop", [utc])], "thresholds")
    assert [r["value"] for r in with_legacy] == [5000, 7000], "absent first"


def test_both_implementations_answer_the_same_way():
    """The property that matters when there are two: on the inputs they share,
    they agree. Asserted over the pair the timezone trap turns on."""
    from vitai.devices import merge

    east = threshold(9000, "2030-05-01T23:30:00+02:00", "before the flight")
    utc = threshold(7000, "2030-05-01T22:00:00+00:00", "after landing")
    by_key = [r["value"] for r in sorted([utc, east], key=order_key)]
    by_merge = [r["value"] for r in merge([("a", [utc]), ("b", [east])],
                                          "thresholds")]
    assert by_key == by_merge == [9000, 7000]


def test_a_transaction_time_is_compared_as_an_instant_and_not_as_text():
    """THE GAP THE REVIEW FOUND, and the property the key's docstring argues
    for: "comparing stamps as text orders two rows written either side of a
    timezone change by wall clock rather than by when they were written".

    Replacing `stamp_instant(stamp)` with `str(stamp)` passed all 2275 tests.
    An athlete who flies east writes 23:30+02:00 and then 22:00Z - later by the
    clock on the wall, earlier by every clock that matters - and the record
    took the wrong one as current."""
    east = threshold(9000, "2030-05-01T23:30:00+02:00", "before the flight")
    utc = threshold(7000, "2030-05-01T22:00:00+00:00", "after landing")

    assert [r["value"] for r in sorted([east, utc], key=order_key)] == [9000, 7000]
    assert [r["value"] for r in sorted([utc, east], key=order_key)] == [9000, 7000]


def test_the_timezone_case_reaches_the_readers_that_decide():
    """Not just the key: the two sites that use it to pick a current line."""
    from vitai.jsonl import heads
    from vitai.policy import state

    east = threshold(9000, "2030-05-01T23:30:00+02:00", "before the flight")
    utc = threshold(7000, "2030-05-01T22:00:00+00:00", "after landing")
    for order in ([east, utc], [utc, east]):
        assert heads(order, "thresholds")["steps_floor"]["value"] == 7000
        assert state([], order, "2030-05-02").thresholds["steps_floor"] == 7000


def test_every_reader_that_orders_rows_uses_the_one_rule():
    """A ninth reader sorting by `date` alone, or by nothing, is how the rule
    stops being a rule. Pinned by call site rather than by count, so adding a
    reader means saying where."""
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "vitai"
    users = set()
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and node.id == "order_key"
                    and path.name != "clocks.py"):
                users.add(path.name)
    # `schema.py` re-exports it for other modules and never sorts with it, so
    # it is absent here by design rather than by omission.
    assert users == {"contributions.py", "jsonl.py",
                     "policy.py"}, sorted(users)
    schema_src = (src / "schema.py").read_text(encoding="utf-8")
    assert "order_key" in schema_src and "noqa: F401" in schema_src
