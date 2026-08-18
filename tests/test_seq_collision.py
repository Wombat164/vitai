"""Two offline devices can stamp one position, and a correction named it (#391).

`seq` is `max(count, highest + 1)` over what the appending machine can SEE.
Actor-per-file (#105) is what makes a union merge safe, and it is exactly what
removes the shared counter that kept `seq` unique: two devices, both offline,
both appending to one `line_key`, both compute the same next position. The
union then holds two live rows at one seat, and `supersedes_seq` addresses a
row BY that seat.

NOTHING IS CORRUPTED AND NO WRITE IS LOST - the merge is still correct. What is
wrong is that a written correction stops meaning one thing, which is the
property `jsonl.target_of` says an append-only record depends on:

    In an append-only record a written reference has to mean one thing
    forever, and a field does what a parsed string cannot.

Synthetic data only, fictional athlete, 2030 dates.
"""

from __future__ import annotations

import json

import pytest

from vitai.devices import merge
from vitai.jsonl import retire

DAY = "2030-05-01"


def row(device, seq, kg, **kw):
    """A weigh-in as two offline devices would have written it.

    Both stamp `seq` from what they can see, and neither can see the other -
    so both stamp the same number. `recorded_at` differs because two machines
    do not write at the same instant, and it is deliberately NOT the thing any
    rule here leans on: #210 settled that `recorded_at` is machine-set, and a
    resolution reaching for wall-clock ordering across devices is reaching for
    a clock that issue already refused.
    """
    out = {"date": DAY, "kg": kg, "source": "scale", "note": None,
           "seq": seq, "device": device,
           "recorded_at": f"{DAY}T{7 + seq:02d}:{'00' if device == 'laptop' else '30'}:00+02:00",
           "_gen": 2}
    out.update(kw)
    return out


def streams(correction=None):
    """(laptop, phone) streams, each in its own file's order."""
    laptop = [row("laptop", 0, 80.0)]
    phone = [row("phone", 0, 77.7)]
    if correction is not None:
        laptop.append(correction)
    return [("laptop", laptop), ("phone", phone)]


def merged(correction=None, order=("laptop", "phone")):
    by_name = dict(streams(correction))
    return merge([(name, by_name[name]) for name in order], "weight")


def survivors(correction=None, order=("laptop", "phone")):
    return [(r.get("device"), r.get("kg"))
            for r in retire("weight", merged(correction, order))
            if not r.get("supersedes")]


# --- the collision is real ------------------------------------------------------

def test_two_offline_devices_stamp_the_same_position():
    """The precondition, measured rather than asserted. If `seq` ever became
    unique across devices this whole file would be about nothing, and it would
    say so here rather than by passing."""
    seats = [(r["date"], r["source"], r["seq"]) for r in merged()]
    assert len(seats) == 2
    assert seats[0] == seats[1], "the two rows do not share a seat"


# --- what a correction naming that seat does ------------------------------------

CORRECTION = {"date": DAY, "kg": 79.5, "source": "scale",
              "note": "recalibrated", "seq": 1, "device": "laptop",
              "recorded_at": f"{DAY}T21:00:00+02:00", "_gen": 2,
              "supersedes": f"{DAY}/scale", "supersedes_seq": 0}


def test_a_correction_naming_a_collided_seat_retires_exactly_what_it_names():
    """THE DEFECT. A correction carrying `supersedes_seq: 0` names a position
    two live rows occupy, and there is no rule saying which one it retires.

    The engine retires ONE of them - whichever the merge happened to put last -
    so the phone's reading disappears because of when its wall clock said it
    was written. The correction was authored on the laptop, about the laptop's
    own row, and it silently deleted a peer's observation instead.
    """
    left = survivors({**CORRECTION, "supersedes_device": "laptop"})
    assert ("phone", 77.7) in left, (
        "a correction naming the laptop's row retired the phone's")
    assert ("laptop", 80.0) not in left, "the named row survived"


def test_a_correction_defaults_to_the_row_its_own_machine_wrote():
    """AND THIS IS WHY THE NEW FIELD IS RARELY NEEDED. A correction is authored
    on a machine, about a row that machine can see, and the row it means is
    overwhelmingly the one it wrote itself. `device` is already stamped on the
    correction, so the answer is on the row rather than read off the record -
    which is what makes it stable as peers arrive."""
    assert survivors(CORRECTION) == [("phone", 77.7)], (
        "the laptop's correction did not retire the laptop's row")


def test_the_default_is_the_same_answer_before_and_after_the_peer_syncs():
    """THE PROPERTY THE WHOLE TOPOLOGY EXISTS FOR, and the one a rule that
    ordered the occupants would break. Before the phone's file arrives the seat
    has one occupant and the correction retires it; after it arrives the seat
    has two and the own-device rule picks the same one. A rule keyed to
    "whichever is most recent" flips here, and the row it retired comes back
    while a peer's observation disappears.
    """
    alone = [("laptop", [row("laptop", 0, 80.0), CORRECTION])]
    before = [(r.get("device"), r.get("kg"))
              for r in retire("weight", merge(alone, "weight"))
              if not r.get("supersedes")]
    assert before == [], "the laptop's own row survived its own correction"
    assert ("laptop", 80.0) not in survivors(CORRECTION), (
        "the peer's arrival changed which row the correction retires")


def test_a_writer_with_no_device_at_a_contested_seat_retires_nothing():
    """FAIL CLOSED where nothing on the correction can say which occupant it
    means. The alternative is to pick one, and picking is what makes the
    reference stop meaning one thing: the answer would depend on which peer
    has synced, so a correction written last week retires a different row this
    week and the one it retired comes back. `target_of` already refuses that
    shape for a parsed reference; this refuses it for a contested seat.
    """
    anonymous = {k: v for k, v in CORRECTION.items() if k != "device"}
    left = survivors(anonymous)
    assert ("laptop", 80.0) in left and ("phone", 77.7) in left, (
        "an unaddressable correction retired something instead of refusing")


@pytest.mark.parametrize("order", [("laptop", "phone"), ("phone", "laptop")])
def test_the_answer_does_not_depend_on_which_file_arrived_first(order):
    """A rule that only holds when the devices sync in order is not a rule.

    Actor-per-file exists so that any two machines holding the same segments
    derive the byte-identical record whatever order the files arrived in, and
    a resolution that read differently under a different arrival order would
    quietly retire that property. All three outcomes are checked under both
    orders, because it is the RULE that has to be order-free, not one branch.
    """
    anonymous = {k: v for k, v in CORRECTION.items() if k != "device"}
    assert survivors({**CORRECTION, "supersedes_device": "phone"}, order) == [
        ("laptop", 80.0)]
    assert survivors(CORRECTION, order) == [("phone", 77.7)]
    assert sorted(survivors(anonymous, order)) == [("laptop", 80.0),
                                                   ("phone", 77.7)]


def test_the_correction_still_reaches_a_seat_only_one_row_occupies():
    """The ordinary single-device case is untouched: a narrowed reference with
    no device still retires the one row at that position."""
    one = [("laptop", [row("laptop", 0, 80.0), CORRECTION])]
    left = [(r.get("device"), r.get("kg"))
            for r in retire("weight", merge(one, "weight"))
            if not r.get("supersedes")]
    assert left == [], "the only occupant was not retired"


def test_a_device_that_names_no_occupant_retires_nothing():
    """A correction pointing at a machine with no row at that seat is a
    reference that matches nothing, which is `supersedes_problems`' existing
    "matches no line" case rather than a licence to fall back on guessing."""
    assert survivors({**CORRECTION, "supersedes_device": "tablet"}) == [
        ("laptop", 80.0), ("phone", 77.7)]


# --- the record says so out loud ------------------------------------------------

def test_validate_reports_the_correction_that_cannot_be_resolved():
    """The advice has to be actionable, and for this row it is: name the
    machine. Before this change the same record was told "NOTHING CAN NAME
    THEM APART", which was true when nothing could."""
    from vitai.schema import supersedes_problems

    anonymous = {k: v for k, v in CORRECTION.items() if k != "device"}
    problems = supersedes_problems("weight", list(enumerate(merged(anonymous), 1)))
    assert any("supersedes_device" in p for p in problems), problems


def test_validate_is_quiet_once_the_correction_is_addressed():
    from vitai.schema import supersedes_problems

    rows = list(enumerate(merged({**CORRECTION,
                                  "supersedes_device": "laptop"}), 1))
    assert supersedes_problems("weight", rows) == []


def test_validate_is_quiet_when_the_default_resolves_it():
    """The ordinary multi-device case writes no new field and gets no advice,
    which is the difference between a resolution and a workaround."""
    from vitai.schema import supersedes_problems

    assert supersedes_problems("weight", list(enumerate(merged(CORRECTION), 1))) == []


def _problems(**overrides):
    """Validation problems for a full-shape weight row, ONE key at a time.

    Full-shape, because a partial row reports a missing key for every column
    the generation declares and would let any assertion below pass on the
    wrong message. And the rule must be the NAMED one: until this change
    `supersedes_device` was simply an unknown key, so a test asserting only
    that the field is mentioned passed against the engine it was written to
    falsify - which is #424's shape, in the file that closes #391.
    """
    from vitai.schema import KEYS, validate_record

    row = {k: None for k in KEYS["weight"]}
    row.update({"date": DAY, "kg": 80.0, "source": "scale", "seq": 1,
                "_gen": CORRECTION["_gen"]})
    row.update(overrides)
    problems = validate_record("weight", row)
    assert not any("unknown key" in p for p in problems), (
        "the field is still unregistered, so every assertion here would pass "
        "for the wrong reason")
    return problems


def test_a_correction_cannot_name_a_device_without_a_position():
    """`supersedes_device` narrows a POSITION, and the whole reason it exists
    is that a position can be occupied twice. Standing alone it would be a
    second addressing mode with its own argument, which this issue does not
    make - so it is refused rather than quietly given a meaning."""
    problems = _problems(supersedes=f"{DAY}/scale", supersedes_device="phone")
    assert any("cannot stand alone" in p and "supersedes_device" in p
               for p in problems), problems


def test_the_field_is_only_legal_beside_a_reference():
    problems = _problems(supersedes_device="phone")
    assert any("cannot stand alone" in p and "supersedes_device" in p
               for p in problems), problems


def test_a_writer_may_not_stamp_it_as_json_junk():
    problems = _problems(supersedes=f"{DAY}/scale", supersedes_seq=0,
                         supersedes_device=7)
    assert any("device slug" in p and "supersedes_device" in p
               for p in problems), problems


def test_a_well_formed_correction_is_accepted():
    """The control on the three above: the same shape, correctly written,
    reports nothing - so they are refusing what they name and not the row."""
    assert _problems(supersedes=f"{DAY}/scale", supersedes_seq=0,
                     supersedes_device="phone") == []


def test_the_correction_round_trips_through_a_file(tmp_path):
    """The field survives a write and a read, which is what makes it a record
    rather than an in-memory convention."""
    path = tmp_path / "weight.laptop.jsonl"
    payload = {**CORRECTION, "supersedes_device": "phone"}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    back = json.loads(path.read_text().splitlines()[0])
    assert back["supersedes_device"] == "phone"
