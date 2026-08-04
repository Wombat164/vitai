"""Every row is nameable (#239).

`line_key` names one record at a time, so where the record cannot tell two
rows apart it hands both the same name - and a `supersedes` aimed at either
retired BOTH. Measured on a live record, seven sessions in ten shared a key
with something, so this was the ordinary case rather than an edge: correcting
one of ten sessions on a day deleted all ten, which is the silent data loss
#16 exists to prevent arriving through the correction path.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.jsonl import retire


def s(km, sup=None, source="watch", date="2030-05-01"):
    row = {"date": date, "source": source, "distance_km": km, "type": "run"}
    if sup:
        row["supersedes"] = sup
    return row


def survivors(rows, dataset="sessions"):
    return [r["distance_km"] for r in retire(dataset, rows)]


# --- what a bare reference retires -----------------------------------------
#
# NO ORDINAL SYNTAX. An earlier cut named rows `K#0`, `K#1` so an author could
# point at one exactly, and ordinals assigned at READ TIME are positions in the
# merged order: a phone syncing a row stamped earlier inserts ahead of rows
# already there and renumbers the group, so a reference written last week names
# a different row and something already retired comes back. Naming an earlier
# row exactly needs an ordinal STORED on it, the way `sets` carries
# `set_index`.

# --- what one reference retires ---------------------------------------------

def test_a_bare_reference_retires_one_row_not_the_day():
    """THE DEFECT. Two real activities became one."""
    assert survivors([s(5.0), s(8.0), s(8.5, "2030-05-01/watch")]) == [5.0, 8.5]


def test_a_bare_reference_names_the_most_recent():
    """Which is the row a correction written straight afterwards means."""
    assert survivors([s(5.0), s(8.0), s(9.0),
                      s(9.5, "2030-05-01/watch")]) == [5.0, 8.0, 9.5]


def test_two_corrections_naming_one_reference_retire_one_other_row():
    """Counting the retired duplicate twice would take a second, unrelated
    row - the original harm coming back through the repair path."""
    assert survivors([s(5.0), s(8.0), s(8.5, "2030-05-01/watch"),
                      s(9.0, "2030-05-01/watch")]) == [5.0, 9.0]


def test_a_correction_to_another_key_is_still_an_ordinary_row_here():
    """"Not a correction to K" is not the same as "not a correction at all";
    reading it that way skipped this row and retired an older, unrelated one."""
    assert survivors([s(5.0), s(8.0, "2030-05-01/app"),
                      s(8.5, "2030-05-01/watch")]) == [5.0, 8.5]


def test_a_read_time_ordinal_would_not_have_been_stable():
    """The reason there is no ordinal syntax, kept as a test so the next
    attempt starts from the evidence: a device syncing a row stamped earlier
    reorders the group under any positional scheme."""
    from vitai.devices import merge
    def stamped(km, rec, sup=None):
        r = s(km, sup)
        r["recorded_at"] = rec
        return r
    laptop = [stamped(5.0, "2030-05-01T10:00:00+00:00"),
              stamped(8.0, "2030-05-01T11:00:00+00:00")]
    phone = [stamped(3.0, "2030-05-01T09:00:00+00:00")]
    alone = [r["distance_km"] for r in merge([("laptop", laptop)], "sessions")]
    both = [r["distance_km"] for r in
            merge([("laptop", laptop), ("phone", phone)], "sessions")]
    assert alone == [5.0, 8.0] and both == [3.0, 5.0, 8.0]


def test_a_chain_still_comes_down_whole():
    """A superseded by B, B superseded by C legitimately shares one reference.
    Two corrections naming one reference are the same intent expressed twice:
    the later wins and takes the earlier with it."""
    assert survivors([s(1.0), s(2.0, "2030-05-01/watch"),
                      s(3.0, "2030-05-01/watch")]) == [3.0]


def test_a_repair_clears_a_correction_that_sorted_too_early():
    """Without this, appending the repair leaves the dead line behind and the
    record has no legal path back to quiet - a row that fails with no way to
    green, which append-only makes impossible to edit away."""
    dead = s(2.0, "2030-05-01/watch")
    dead["recorded_at"] = None
    target = s(1.0)
    target["recorded_at"] = "2030-05-01T07:00:00+02:00"
    repair = s(2.0, "2030-05-01/watch")
    repair["recorded_at"] = "2030-05-04T07:00:00+02:00"
    # In MERGED order the unstamped correction sorts first, which is what made
    # it do nothing in the first place.
    assert survivors([dead, target, repair]) == [2.0]


def test_a_reference_matching_nothing_retires_nothing():
    assert survivors([s(5.0), s(8.0, "2030-05-01/nobody")]) == [5.0, 8.0]


# --- and the demo carries the case ------------------------------------------

def test_the_demo_has_an_unnameable_pair_corrected_precisely():
    """Two rides one morning, same watch, neither carrying a vendor id - the
    ordinary shape. The correction takes the second and leaves the first."""
    rows = [json.loads(line) for line in
            (Path(__file__).resolve().parents[1] / "examples" / "demo"
             / "data" / "sessions.jsonl").read_text().splitlines() if line.strip()]
    day = [r for r in rows if r.get("type") == "cycle"]
    assert len(day) == 3 and len({r["date"] for r in day}) == 1
    assert not any(r.get("activity_id") for r in day)
    kept = [r["distance_km"] for r in retire("sessions", rows)
            if r["date"] == day[0]["date"] and r["type"] == "cycle"]
    assert kept == [14.2, 33.1], "the first ride was retired by mistake"
