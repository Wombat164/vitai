"""The ordering rule is pinned where it is defined and nowhere it is used.

`clocks.order_key` is doctrine: order on VALID time, keep transaction time
separate, and never trust the order lines happen to sit in. Its own docstring
puts it plainly - "an ordering a formatter can change is not an ordering" -
and eight readers across five modules depend on it.

Measured rather than assumed: replacing `order_key` with a constant, so a
stable sort keeps arrival order, leaves **2258 of 2264 tests passing**. Four
of the six failures are in `test_clocks.py`, the unit tests of the function
itself; the other two were added with the protocol seam and are the only
use-site coverage in the tree. Every reader that actually decides something
with it - which threshold is in force, which goal, which device row, what a
correction retires - is unprotected.

That is the same shape as every expensive defect here: a rule with one home
and no witness at the places it is load-bearing. So this exercises each use
site with a record whose FILE ORDER CONTRADICTS ITS DATES, and asserts the
answer comes from the record.

WHY IT MATTERS BEYOND TIDINESS, and #308 is the live instance: a client that
re-derived this rule from prose got it wrong, taking the first and last
elements of an append-only log as its span. Position and date agree on every
log written once, in order, on one device - which is every log anyone has
today. They stop agreeing when a file is restored from a backup or merged
across devices, which is when somebody is already having a bad day.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.clocks import order_key
from vitai.schema import KEYS

# ONE DAY, TWO LINES, WRITTEN OUT OF ORDER. The later line by `recorded_at`
# sits FIRST in the file, so anything reading file position gets the stale
# answer and anything reading the record gets the current one.
EARLY = "2030-05-01T06:00:00Z"
LATE = "2030-05-01T18:00:00Z"


def write(root: Path, name: str, rows: list[dict]) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / f"{name}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def record(tmp_path: Path, toml: str = "") -> Path:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    return root


def threshold(value: float, stamped: str, reason: str) -> dict:
    return {**{k: None for k in KEYS["thresholds"]}, "date": "2030-05-01",
            "key": "steps_floor", "value": value, "change_kind": "change",
            "set_by": "athlete", "reason": reason, "recorded_at": stamped}


# --- the rule itself -----------------------------------------------------------

def test_the_later_stamp_sorts_last_however_the_file_is_written():
    rows = [threshold(9000, LATE, "later"), threshold(7000, EARLY, "earlier")]
    assert [r["value"] for r in sorted(rows, key=order_key)] == [7000, 9000]
    assert [r["value"] for r in sorted(reversed(rows), key=order_key)] == [7000, 9000]


# --- and at every place that decides something with it -------------------------

def test_which_threshold_is_in_force_comes_from_the_record(tmp_path):
    """`policy._in_force` decides which policy a week is judged against. Read
    by file position it would take whichever line a formatter left last."""
    from vitai.policy import state

    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]
    for order in (rows, list(reversed(rows))):
        held = state([], order, "2030-05-02").thresholds
        assert held["steps_floor"] == 9000, order[0]["reason"]


def test_which_goal_is_live_comes_from_the_record(tmp_path):
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


def test_a_correction_retires_the_line_the_record_says_is_current(tmp_path):
    """`jsonl` reads a dataset in `order_key` order before applying
    `supersedes`. By file position a correction could retire the wrong one of
    two lines sharing a date."""
    root = record(tmp_path)
    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]
    write(root, "thresholds", rows)
    forwards = [r["value"] for r in Vitai(root).dataset("thresholds")]
    write(root, "thresholds", list(reversed(rows)))
    backwards = [r["value"] for r in Vitai(root).dataset("thresholds")]
    assert forwards == backwards == [7000, 9000]


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


def test_the_verdicts_a_record_produces_do_not_depend_on_line_order(tmp_path):
    """The property that matters end to end, and the one a formatter could
    have broken: reordering two lines in a file must not change a judgement."""
    root = record(tmp_path, "[tripwires]\nsteps_floor = 5000\n")
    daily = [{**{k: None for k in KEYS["daily"]}, "date": f"2030-05-{d:02d}",
              "steps": 8000, "source": "manual"} for d in range(1, 15)]
    write(root, "daily", daily)
    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]

    write(root, "thresholds", rows)
    forwards = Vitai(root).verdicts()
    write(root, "thresholds", list(reversed(rows)))
    backwards = Vitai(root).verdicts()
    assert forwards == backwards
    # And the weeks the dated row reaches take its figure, not the toml's -
    # the week BEFORE 2030-05-01 correctly still reads the file, since no
    # dated policy covers it (#148).
    reached = [r for r in forwards
               if r["metric"] == "steps" and r["week"] >= "2030-05-06"]
    assert reached and all(r["target"] == 9000 for r in reached), reached


def test_the_built_read_model_is_byte_identical_either_way(tmp_path):
    """A reformat that reorders lines must not change the artifact a consumer
    reads. This is `order_key`'s whole argument, at the surface a client
    actually holds."""
    rows = [threshold(9000, LATE, "raised in the evening"),
            threshold(7000, EARLY, "the morning figure")]
    first = record(tmp_path / "a")
    write(first, "thresholds", rows)
    second = record(tmp_path / "b")
    write(second, "thresholds", list(reversed(rows)))
    assert Vitai(first).build().read_bytes() == Vitai(second).build().read_bytes()


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
