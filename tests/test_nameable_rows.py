"""Naming one row of several that share a key (#239).

`line_key` falls back to `<date>/<source>`, so two runs on one day from one
watch share a name. Contract 33 fixed what a reference RETIRES - one reference
takes ONE other row, the most recent, which is what a correction written
straight afterwards means.

What stayed broken is naming an EARLIER one, and the cost is concrete: five
rows of one key written as a chain cannot be repaired by appending at all. A
reference retires the most recent; a second append naming the same key retires
the FIRST APPEND rather than the next row down; and editing in place is what
append-only forbids. Three of those five rows are unreachable by any sequence
of writes.

TWO FIELDS, NEVER A PARSED REFERENCE, and the alternative was built first so
the reason is evidence rather than taste. Spelling the position into the
reference as `K#n` fails twice over. Nothing stops a bare key containing the
separator - `activity_id` is validated as an opaque string, `source` is not
content-checked at all, and a `meals` identity is free text - so
`2030-05-01/watch#2` is a legal bare key AND a legal narrowed one. And
disambiguating by lookup makes the MEANING OF A STORED REFERENCE DEPEND ON
WHAT ELSE IS IN VIEW: measured against the previous engine, a reference whose
target had not synced was read as a position and retired an unrelated row, and
a reference that had already applied flipped back to bare when a row with a
matching source arrived, resurrecting what it had retired.

So `supersedes` is untouched - same spelling, same meaning, every reference
already written keeps doing exactly what it did - and the position travels in
`supersedes_seq`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.jsonl import DataError, position_of, retire, target_of
from vitai.schema import (IDENTITY_KEY, KEYS, SEQUENCED, supersedes_problems,
                          validate_record)

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"


def _s(km, sup=None, at=None, seq=None, source="watch", date="2030-05-01"):
    row = {"date": date, "source": source, "distance_km": km, "type": "run"}
    if sup:
        row["supersedes"] = sup
    if at is not None:
        row["supersedes_seq"] = at
    if seq is not None:
        row["seq"] = seq
    return row


def _survivors(rows, dataset="sessions"):
    return [r["distance_km"] for r in retire(dataset, rows)]


def _three(tmp_path: Path) -> Vitai:
    v = Vitai(init(tmp_path / "content"))
    for km in (5.0, 8.0, 9.0):
        v.append("sessions", {"date": "2030-05-01", "type": "run",
                              "distance_km": km, "source": "watch"})
    return v


# --- the position ---------------------------------------------------------

def test_the_engine_stamps_a_position_on_every_row(tmp_path):
    """Counted over the rows already sharing this row's bare key."""
    assert [r["seq"] for r in _three(tmp_path).dataset("sessions")] == [0, 1, 2]


def test_rows_with_different_keys_number_independently(tmp_path):
    """A position is a position WITHIN a key, not within a file. Numbering by
    file position would make the field a line number under another name."""
    v = Vitai(init(tmp_path / "content"))
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch"})
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 6.0, "source": "app"})
    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 7.0, "source": "watch"})

    assert [r["seq"] for r in v.dataset("sessions")] == [0, 0, 0]


def test_a_bulk_import_numbers_its_own_batch(tmp_path):
    """Ten sessions on one day are 0..9. Counting only the rows already on
    disk would hand every row of the batch the same number, which is the
    collision this exists to remove arriving inside one write."""
    v = Vitai(init(tmp_path / "content"))

    v.append_many("sessions", [
        {"date": "2030-05-01", "type": "run", "distance_km": float(n),
         "source": "watch"} for n in range(1, 11)])

    assert [r["seq"] for r in v.dataset("sessions")] == list(range(10))


def test_a_caller_cannot_choose_its_own_position(tmp_path):
    """Machine-set, for the reason `recorded_at` is."""
    with pytest.raises(ValueError) as raised:
        Vitai(init(tmp_path / "content")).append(
            "sessions", {"date": "2030-05-01", "type": "run",
                         "distance_km": 5.0, "source": "watch", "seq": 7})

    assert "machine-set" in str(raised.value)


def test_the_count_spans_every_device(tmp_path):
    """THE FEATURE'S CENTRAL PROPERTY. Counting only the file being written is
    the cheaper implementation and passes every single-device test, and it
    hands two machines the same number for the same key."""
    root = init(tmp_path / "content")
    (root / "data" / "sessions.laptop.jsonl").write_text(json.dumps({
        "date": "2030-05-01", "type": "run", "distance_km": 4.0,
        "source": "watch", "seq": 0, "_gen": 1,
        "recorded_at": "2020-01-01T08:00:00+02:00"}) + "\n", encoding="utf-8")

    written = Vitai(root).append("sessions", {
        "date": "2030-05-01", "type": "run", "distance_km": 5.0,
        "source": "watch"})

    assert written["seq"] == 1, "the other device's row was not counted"


def test_a_visible_higher_position_is_not_reused(tmp_path):
    """A COUNT IS RIGHT ONLY WHEN THE ROWS ARRIVE IN ORDER. Sync three devices
    out of order and a machine holding positions 3 and 4 but not 0 to 2 counts
    two rows and stamps 2 - colliding with a row it can see the proof of,
    because the record says five exist and the count says otherwise. Taking
    the higher of the count and one past the highest visible position uses
    what is already on screen."""
    root = init(tmp_path / "content")
    (root / "data" / "sessions.other.jsonl").write_text("\n".join(
        json.dumps(r) for r in [
            {"date": "2030-05-01", "type": "run", "distance_km": 3.0,
             "source": "watch", "seq": 3, "_gen": 1,
             "recorded_at": "2030-05-01T08:00:00+02:00"},
            {"date": "2030-05-01", "type": "run", "distance_km": 4.0,
             "source": "watch", "seq": 4, "_gen": 1,
             "recorded_at": "2030-05-01T09:00:00+02:00"},
        ]) + "\n", encoding="utf-8")

    written = Vitai(root).append("sessions", {
        "date": "2030-05-01", "type": "run", "distance_km": 9.0,
        "source": "watch"})

    assert written["seq"] == 5, "a bare count would have said 2"


def test_the_position_is_stored_and_not_recomputed(tmp_path):
    """THE WHOLE REASON THIS IS A FIELD. A row synced with an earlier stamp
    sorts into the middle of the merged order, and under any read-time scheme
    it would renumber the rows after it - so a reference written last week
    would name a different row. Stored, the numbers stay put."""
    v = _three(tmp_path)
    before = {r["distance_km"]: r["seq"] for r in v.dataset("sessions")}

    (v.root / "data" / "sessions.laptop.jsonl").write_text(json.dumps({
        "date": "2030-05-01", "type": "run", "distance_km": 4.0,
        "source": "watch", "seq": 0, "_gen": 1,
        "recorded_at": "2020-01-01T08:00:00+02:00"}) + "\n", encoding="utf-8")

    after = {r["distance_km"]: r["seq"]
             for r in Vitai(v.root).dataset("sessions")}

    assert after[4.0] == 0
    for km, seq in before.items():
        assert after[km] == seq, f"{km} was renumbered"


def test_a_bulk_import_is_not_quadratic(tmp_path):
    """`_targets_retired` carries this lesson from #210, so reintroducing it
    here would be the more embarrassing."""
    v = Vitai(init(tmp_path / "content"))
    rows = [{"date": "2030-05-01", "type": "run", "distance_km": float(n),
             "source": "watch"} for n in range(4000)]

    started = time.monotonic()
    out = v.append_many("sessions", rows)
    elapsed = time.monotonic() - started

    assert [r["seq"] for r in out] == list(range(4000))
    assert elapsed < 5.0, f"{elapsed:.1f}s for 4000 rows is the quadratic shape"


# --- the narrowed reference -----------------------------------------------

def test_a_narrowed_reference_retires_the_row_it_names(tmp_path):
    """THE ACCEPTANCE CRITERION. The middle of three, which no bare reference
    can reach: a bare one takes the most recent, and a second bare one takes
    the first correction rather than the next row down."""
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.5, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 1})

    assert [r["distance_km"] for r in v.dataset("sessions")] == [5.0, 9.0, 8.5]


def test_the_chain_that_could_not_be_repaired_now_can():
    """Five rows of one key, of which three were unreachable by any sequence
    of appends."""
    rows = [_s(float(n), seq=n) for n in range(5)]
    rows += [_s(99.0, sup="2030-05-01/watch", at=2, seq=5)]

    assert _survivors(rows) == [0.0, 1.0, 3.0, 4.0, 99.0]


def test_two_corrections_to_one_key_are_two_intents(tmp_path):
    """THE CASE NO TEST COVERED, AND IT LOST DATA.

    `retire` treats two corrections naming one reference as the same intent
    expressed twice - the later wins and takes the earlier with it - which is
    right for two BARE references and false the moment a position is on one of
    them. A correction of position 1 and a correction of position 2 are two
    different intents that happen to share a key.

    Keying that test on the reference STRING dropped the earlier correction and
    brought its target's value back. Silently: `validate` reported nothing, the
    append path did not refuse, and `corrections()` showed one correction where
    two had been written. That is the data loss through the correction path
    this whole issue exists to close, reintroduced by the fix for it.
    """
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.1, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 1})
    v.append("sessions", {"date": "2030-05-03", "type": "run",
                          "distance_km": 9.1, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 2})

    assert [r["distance_km"] for r in v.dataset("sessions")] == [5.0, 8.1, 9.1]
    assert len(v.corrections("sessions")) == 2
    assert not v.validate()["problems"]


def test_a_bare_and_a_narrowed_correction_of_one_key_both_apply(tmp_path):
    """The same defect wearing the other shape: the bare one asks for whichever
    row is most recent and the narrowed one asks for a named row, and they are
    not the same intent however much of a key they share."""
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.1, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 1})
    v.append("sessions", {"date": "2030-05-03", "type": "run",
                          "distance_km": 9.1, "source": "watch",
                          "supersedes": "2030-05-01/watch"})

    assert len(v.dataset("sessions")) == 3
    assert 8.0 not in [r["distance_km"] for r in v.dataset("sessions")]


def test_two_bare_corrections_of_one_key_are_still_one_intent():
    """AND THE RULE THAT DOES NOT MOVE. Two BARE references naming one key are
    the same intent expressed twice - the later wins and takes the earlier with
    it, which is what stops a re-appended repair retiring a second, unrelated
    row. `test_line_keys.py` pins it; asserted here too because the fix above
    is one line away from breaking it."""
    rows = [_s(5.0, seq=0), _s(8.0, seq=1),
            _s(8.5, sup="2030-05-01/watch", seq=2),
            _s(9.0, sup="2030-05-01/watch", seq=3)]

    assert _survivors(rows) == [5.0, 9.0]


def test_a_batch_mixing_a_bare_and_a_narrowed_correction_is_accepted(tmp_path):
    """A TypeError on the HAPPY path. The #210 refusal sorts its references
    before it filters out the ones that applied, and `None` does not compare
    with an int - so a legitimate bulk import carrying both forms for one key
    was refused with a stack trace."""
    v = _three(tmp_path)

    written = v.append_many("sessions", [
        {"date": "2030-05-02", "type": "run", "distance_km": 8.1,
         "source": "watch", "supersedes": "2030-05-01/watch",
         "supersedes_seq": 1},
        {"date": "2030-05-02", "type": "run", "distance_km": 9.1,
         "source": "watch", "supersedes": "2030-05-01/watch"},
    ])

    assert len(written) == 2
    assert len(v.dataset("sessions")) == 3


def test_a_defeated_narrowed_correction_is_reported(tmp_path):
    """`_dud_corrections` matched on the key alone, so a defeated NARROWED
    correction went unreported whenever any OTHER correction of the same key
    applied - the loud wrong state going quiet, which is the failure #210
    exists to close."""
    root = init(tmp_path / "content")
    (root / "data" / "sessions.jsonl").write_text("\n".join(
        json.dumps(r | {"_gen": 1}) for r in [
            _s(5.0, seq=0) | {"recorded_at": "2030-05-01T08:00:00+02:00"},
            _s(8.0, seq=1) | {"recorded_at": "2030-05-01T09:00:00+02:00"},
            # Defeated: stamped before the row it names.
            _s(8.5, sup="2030-05-01/watch", at=1, seq=2)
            | {"recorded_at": "2030-05-01T07:00:00+02:00"},
            # And one that applies, sharing the key.
            _s(5.5, sup="2030-05-01/watch", at=0, seq=3)
            | {"recorded_at": "2030-05-01T10:00:00+02:00"},
        ]) + "\n", encoding="utf-8")

    problems = Vitai(root).validate()["problems"]

    assert any("did NOT apply" in p and "position 1" in p for p in problems)


def test_a_position_nothing_carries_is_not_an_ordering_defeat(tmp_path):
    """TWO CONTRADICTORY INSTRUCTIONS FOR ONE LINE, before the dud check
    learned about positions. A narrowed reference naming a position no row of
    that key has was diagnosed as a correction defeated by ordering - "it
    sorted before its target, fix the clock" - because the KEY was present,
    while `supersedes_problems` said "matches no line, probably mistyped"
    about the same row. It is the offline-first case: the row it names has not
    arrived, and the advice is to wait.
    """
    root = init(tmp_path / "content")
    (root / "data" / "sessions.jsonl").write_text("\n".join(
        json.dumps(r | {"_gen": 1}) for r in [
            _s(5.0, seq=0) | {"recorded_at": "2030-05-01T08:00:00+02:00"},
            _s(8.0, seq=1) | {"recorded_at": "2030-05-01T09:00:00+02:00"},
            _s(8.5, sup="2030-05-01/watch", at=7, seq=2)
            | {"recorded_at": "2030-05-01T10:00:00+02:00"},
        ]) + "\n", encoding="utf-8")

    report = Vitai(root).validate()

    assert not [p for p in report["problems"] if "did NOT apply" in p]
    assert any("names no line" in a for a in report["advisories"])


def test_the_bare_reference_still_means_what_it_meant(tmp_path):
    """EVERY REFERENCE ALREADY WRITTEN KEEPS DOING WHAT IT DID. A record
    holding corrections written before this field existed must not resolve
    differently for having been read by a newer engine."""
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 9.5, "source": "watch",
                          "supersedes": "2030-05-01/watch"})

    assert [r["distance_km"] for r in v.dataset("sessions")] == [5.0, 8.0, 9.5]


@pytest.mark.parametrize("source", ["watch#2", "a#b", "watch#0"])
def test_a_key_containing_a_separator_is_just_a_key(source):
    """WHAT THE PARSED FORM COULD NOT DO. `2030-05-01/watch#2` is a legal bare
    key, and under a `K#n` grammar it is also a legal narrowed one - so the
    parsed version retired a DIFFERENT row for exactly this shape. With the
    position in its own field there is nothing to parse and nothing to get
    wrong: the key is the key."""
    rows = [_s(1.0, seq=0), _s(2.0, seq=1), _s(3.0, seq=2),
            _s(40.0, source=source, seq=0),
            _s(41.0, sup=f"2030-05-01/{source}", source=source, seq=1)]

    assert _survivors(rows) == [1.0, 2.0, 3.0, 41.0]


def test_a_narrowed_reference_does_not_spend_the_one_row_budget():
    """A bare reference asks for whichever row is most recent and takes one. A
    narrowed one asks for a named row, so it must not also consume that budget
    - two references, two rows retired, not three."""
    rows = [_s(1.0, seq=0), _s(2.0, seq=1), _s(3.0, seq=2),
            _s(8.5, sup="2030-05-01/watch", at=1, seq=3),
            _s(9.5, sup="2030-05-01/watch", seq=4)]

    assert len(_survivors(rows)) == 3


def test_a_position_nothing_carries_retires_nothing():
    """The same shape as a mistyped bare reference: it retires nothing, and
    `validate` says so rather than the engine guessing at the nearest row."""
    rows = [_s(5.0, seq=0), _s(8.0, seq=1),
            _s(8.5, sup="2030-05-01/watch", at=7, seq=2)]

    assert _survivors(rows) == [5.0, 8.0, 8.5]


def test_a_narrowed_correction_can_name_a_correction(tmp_path):
    """A middle row of a real chain IS a correction, so excluding corrections
    from what a narrowed reference may name would hollow out the repair this
    issue is about."""
    v = Vitai(init(tmp_path / "content"))
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch"})
    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 6.0, "source": "watch",
                          "supersedes": "2030-05-01/watch"})

    v.append("sessions", {"date": "2030-05-03", "type": "run",
                          "distance_km": 6.5, "source": "watch",
                          "supersedes": "2030-05-02/watch", "supersedes_seq": 0})

    assert [r["distance_km"] for r in v.dataset("sessions")] == [6.5]
    rows = [json.loads(ln) for ln
            in (v.root / "data" / "sessions.jsonl").read_text().splitlines()
            if ln.strip()]
    assert not [p for p in supersedes_problems(
        "sessions", list(enumerate(rows, 1))) if "matches no line" in p]


def test_a_position_alone_names_nothing():
    """`supersedes_seq` narrows `supersedes`; a position with no key is a
    position in nothing."""
    problems = validate_record("sessions", {
        **{k: None for k in KEYS["sessions"]},
        "date": "2030-05-01", "type": "run", "distance_km": 5.0,
        "source": "watch", "_gen": 1, "supersedes_seq": 0})

    assert any("cannot stand alone" in p for p in problems)


@pytest.mark.parametrize("bad", ["1", -3, True, 1.5])
def test_a_position_that_is_not_a_whole_count_is_refused(bad):
    """Shape-checked as well as refused at append: the append path covers
    writes through this engine and nothing else, and the format invites hand
    editing. Unchecked, `"1"` and `1` are two spellings of one position."""
    row = {k: None for k in KEYS["sessions"]}
    row.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "_gen": 1, "seq": bad})

    assert [p for p in validate_record("sessions", row) if "seq" in p]


def test_zero_is_a_position_and_not_an_absence():
    """The first row of a key is 0, which is falsy - so a check written as
    `if rec.get("seq")` would treat the commonest row in the record as having
    no position at all."""
    row = {k: None for k in KEYS["sessions"]}
    row.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "_gen": 1, "seq": 0})

    assert validate_record("sessions", row) == []
    assert position_of(row) == 0
    assert target_of({"supersedes": "k", "supersedes_seq": 0}) == ("k", 0)


# --- the #210 refusal, over the new shape ---------------------------------

def test_a_reference_to_a_row_not_yet_synced_stays_legal(tmp_path):
    """#210's rule, and it cuts the way offline-first needs: a reference
    matching NO row is a record that syncs writer by writer, and refusing it
    would make offline-first writing impossible."""
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.5, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 9})

    assert len(v.dataset("sessions")) == 4


def test_a_narrowed_correction_that_would_retire_nothing_is_refused(tmp_path):
    """The other half of #210. The target EXISTS and the correction still
    cannot reach it, because another writer stamped that row ahead of this
    machine's clock. Silence there is the failure #210 exists to close."""
    v = _three(tmp_path)
    (v.root / "data" / "sessions.laptop.jsonl").write_text(json.dumps({
        "date": "2030-05-03", "type": "run", "distance_km": 4.0,
        "source": "watch", "seq": 0, "_gen": 1,
        "recorded_at": "2099-01-01T08:00:00+02:00"}) + "\n", encoding="utf-8")

    with pytest.raises(DataError) as raised:
        Vitai(v.root).append("sessions", {
            "date": "2030-05-04", "type": "run", "distance_km": 8.5,
            "source": "watch", "supersedes": "2030-05-03/watch",
            "supersedes_seq": 0})

    assert "would retire nothing" in str(raised.value)


def test_a_narrowed_correction_that_applies_is_not_refused(tmp_path):
    """The control for the check above: the guard turning into the failure it
    guards against is the shape to watch for."""
    v = _three(tmp_path)

    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.5, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 1})

    assert [r["distance_km"] for r in v.dataset("sessions")] == [5.0, 9.0, 8.5]


# --- what validate says ---------------------------------------------------

def test_an_ambiguous_reference_now_says_which_position_to_write():
    """AMBIGUOUS AND NAMEABLE. Where the matched rows carry distinct positions
    the author can name one, so the message is what to write rather than
    advice about a vendor identity they cannot retrofit."""
    rows = [_s(5.0, seq=0), _s(8.0, seq=1),
            _s(8.5, sup="2030-05-01/watch", seq=2)]

    problems = supersedes_problems("sessions", list(enumerate(rows, 1)))

    assert any("'supersedes_seq': 0, 1" in p for p in problems)


def test_a_narrowed_reference_is_not_reported_as_ambiguous():
    """The point of the narrowing, seen from the validator. Three rows share
    the key, so a BARE reference to it is ambiguous and says so - and the same
    reference carrying a position names exactly one row and must not be
    reported at all. Without this, `validate` would tell an author who did the
    right thing that it was ambiguous, which is the advice that made them do
    it in the first place."""
    rows = [_s(1.0, seq=0), _s(2.0, seq=1), _s(3.0, seq=2)]
    bare = rows + [_s(9.0, sup="2030-05-01/watch", seq=3)]
    narrowed = rows + [_s(9.0, sup="2030-05-01/watch", at=1, seq=3)]

    assert [p for p in supersedes_problems("sessions", list(enumerate(bare, 1)))
            if "matches" in p]
    assert not supersedes_problems("sessions", list(enumerate(narrowed, 1)))


def test_a_narrowed_reference_to_a_position_nothing_carries_is_reported():
    """The other half: naming a position no row of that key has is a reference
    that retires nothing, and it reads the same as a mistyped bare one."""
    rows = [_s(1.0, seq=0), _s(2.0, seq=1),
            _s(9.0, sup="2030-05-01/watch", at=7, seq=2)]

    problems = supersedes_problems("sessions", list(enumerate(rows, 1)))

    assert any("matches no line" in p for p in problems)


def test_a_reference_nothing_can_name_apart_says_that_instead():
    """AMBIGUOUS AND NOT NAMEABLE, which is a different sentence. Telling
    somebody holding a five-year-old file to add a vendor identity is advice
    they cannot take for the rows in front of them."""
    rows = [_s(5.0), _s(8.0), _s(8.5, sup="2030-05-01/watch")]

    problems = supersedes_problems("sessions", list(enumerate(rows, 1)))

    assert any("NOTHING CAN NAME THEM APART" in p for p in problems)
    assert any("cannot be corrected in place" in p for p in problems)
    assert any("activity_id" in p for p in problems)


def test_two_machines_offline_together_collide_and_it_is_reported():
    """THE RESIDUAL, NAMED RATHER THAN HIDDEN. `seq` counts across every
    stream and never reuses a position it can see, so one machine never hands
    out a number twice - two that cannot see each other will."""
    rows = [_s(5.0, seq=0), _s(8.0, seq=0)]

    problems = supersedes_problems("sessions", list(enumerate(rows, 1)))

    assert any("no correction can name one of them" in p for p in problems)


def test_no_dataset_registers_the_position_at_its_founding_generation():
    """G25 REACHES EVERY DATASET, INCLUDING THE ONES NOTHING HAS WRITTEN YET.

    The first cut skipped the bump for a dataset still at generation 1,
    reasoning that nothing has written one so `seq` could be founding there.
    That is an assertion about somebody else's record. `regimes` is written by
    no fixture in this repo and may be written in one nobody here can see, and
    registering `seq` at generation 1 makes the exemption
    `line_generation < key_generation` false for every line that could exist -
    so each is held to a key that postdates it. #295's failure mode, committed
    while fixing its neighbour.
    """
    from vitai.schema import KEY_GENERATION, SEQUENCED

    for dataset in SEQUENCED:
        assert KEY_GENERATION[dataset]["seq"] > 1, dataset


def test_a_line_of_a_never_written_dataset_still_validates():
    """The same thing said as behaviour rather than as a number. `regimes` is
    the one dataset here with no rows in any fixture, which is exactly why it
    was the one that got this wrong."""
    row = {k: None for k in KEYS["regimes"]}
    row.update({"date": "2030-05-01", "kind": "unanchored", "dataset": "weight",
                "field": "kg", "from_date": "2030-05-01",
                "to_date": "2030-05-02", "text": "a regime",
                "source": "athlete", "_gen": 1})
    row.pop("seq", None)

    assert validate_record("regimes", row) == []


def test_an_older_line_never_owed_a_position():
    """G25, and the acceptance criterion the issue itself corrected: "existing
    rows gain an ordinal" cannot be met by backfill, because assigning
    positions to lines already written means editing them."""
    old = {k: None for k in KEYS["sessions"]}
    old.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "_gen": 1})
    old.pop("seq", None)

    assert validate_record("sessions", old) == []


# --- where it applies, and what reads it ----------------------------------

def test_it_reaches_every_dataset_whose_key_can_collide():
    """The rule rather than a list: a dataset that names rows by a slug or a
    tuple already has an answer, and `emissions` never retires at all."""
    for dataset in KEYS:
        wants = dataset not in IDENTITY_KEY and dataset != "emissions"
        assert (dataset in SEQUENCED) == wants, dataset
        assert ("seq" in KEYS[dataset]) == wants, dataset


def test_a_narrowed_correction_reaches_the_corrections_surface(tmp_path):
    """`corrections.py` pairs a correction with its target by key, so without
    the narrowing the surface whose whole job is "what a correction actually
    did" omitted every correction written the way `validate` advises."""
    v = _three(tmp_path)
    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 8.5, "source": "watch",
                          "supersedes": "2030-05-01/watch", "supersedes_seq": 1})

    correction, = v.corrections("sessions")
    moved, = [m for m in correction["moved"] if m["field"] == "distance_km"]

    assert (moved["was"], moved["now"]) == (8.0, 8.5)


def test_the_shipped_record_carries_positions_and_a_collision():
    """#204's corollary. The demo has a day holding two rides from one watch,
    so it exercises the case the field exists for."""
    from vitai.jsonl import line_key

    sessions = Vitai(DEMO).dataset("sessions")
    keyed: dict[str, list[dict]] = {}
    for row in sessions:
        keyed.setdefault(line_key("sessions", row), []).append(row)
    collided = [rows for rows in keyed.values() if len(rows) > 1]

    assert all(r.get("seq") is not None for r in sessions)
    assert collided, "no shipped day holds two rows of one key"
    for rows in collided:
        assert len({r["seq"] for r in rows}) == len(rows)


def test_the_shipped_record_still_validates():
    assert not Vitai(DEMO).validate()["problems"]


def test_the_cli_reports_the_new_advice(tmp_path):
    """P9: the advice reaches a person through the surface they run."""
    root = init(tmp_path / "content")
    (root / "data" / "sessions.jsonl").write_text("\n".join(
        json.dumps(r | {"_gen": 1}) for r in [
            _s(5.0, seq=0), _s(8.0, seq=1),
            _s(8.5, sup="2030-05-01/watch", seq=2)]) + "\n", encoding="utf-8")

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "validate", "--root", str(root)],
        capture_output=True, text=True)

    assert "'supersedes_seq': 0, 1" in out.stdout
