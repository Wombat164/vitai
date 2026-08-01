"""The set is the atom (#97, increment 1 of #59).

Synthetic data only (public repo), fictional athlete, 2030 dates. The three
motivating cases are represented by their SHAPE - a failed attempt, a set that
stopped short of failure, and a stack progression - never by real loads.
"""

import json
import sqlite3

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.jsonl import line_key
from vitai.schema import KEYS, validate_record
from vitai.sets import (FAILURE_KINDS, LOAD_TYPES, SIDE_VALUES,
                        is_failed_attempt, says_it_was_maximal, set_type_of,
                        set_types)


def a_set(**kw):
    row = {"date": "2030-05-01", "session_start": "2030-05-01T07:10:00+02:00",
           "exercise": "push-up", "block": 1, "round": None, "set_index": 1,
           "reps_completed": 13, "reps_attempted": 13,
           "load": None, "load_type": "bodyweight", "load_unit": None,
           "machine": None, "set_type": "working", "failure": None,
           "rir": None, "rpe": None, "rest_s": 90, "tempo": None,
           "duration_s": None, "side": None, "note": None,
           "source": "stated-in-chat", "recorded_at": None,
           "origin": "athlete", "path": None, "origin_evidence": None,
           # #97's example row writes `read_by: null` beside
           # `capture: "narrative"`, which #78 rejects - and rightly: a
           # narrated set WAS read by someone, and here that is the athlete.
           # Stated rather than worked around.
           "capture": "narrative", "read_by": "athlete"}
    row.update(kw)
    return row


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, rows):
    (root / "data" / "sets.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# The stack progression, as four rows. The third is the one that had nowhere
# to live: an attempted load that could not be completed.
STACK = [
    a_set(exercise="leg press", set_index=1, load=59, load_type="machine_stack",
          machine="leg-press-a", reps_completed=12, reps_attempted=12),
    a_set(exercise="leg press", set_index=2, load=66, load_type="machine_stack",
          machine="leg-press-a", reps_completed=12, reps_attempted=12),
    a_set(exercise="leg press", set_index=3, load=73, load_type="machine_stack",
          machine="leg-press-a", reps_completed=0, reps_attempted=1,
          failure="muscular"),
    a_set(exercise="leg press", set_index=4, load=66, load_type="machine_stack",
          machine="leg-press-a", reps_completed=12, reps_attempted=12),
]


# ---- case 1: a failed attempt is data, not absence -----------------------------------

def test_a_failed_attempt_is_recordable():
    """`73 FAILED` after `66x12` - the single most informative set of the
    block, and there was nowhere to put it."""
    failed = STACK[2]
    assert validate_record("sets", failed) == []
    assert is_failed_attempt(failed) is True


def test_a_failed_attempt_is_distinguishable_from_one_never_tried():
    """The absence of a row is a set that was never attempted. A row with
    zero completed is a set that was attempted and lost."""
    assert is_failed_attempt(a_set(reps_completed=0, reps_attempted=1)) is True
    assert is_failed_attempt(a_set(reps_completed=12, reps_attempted=12)) is False
    assert is_failed_attempt(a_set(reps_completed=None,
                                   reps_attempted=None,
                                   duration_s=60)) is False


def test_a_rep_cannot_be_finished_without_being_started():
    assert any("exceeds" in p for p in validate_record(
        "sets", a_set(reps_completed=12, reps_attempted=8)))


def test_a_set_that_says_nothing_happened_is_rejected():
    """A plank has no reps and a bench press has no duration, but a row with
    neither is not a set."""
    assert any("says nothing" in p for p in validate_record(
        "sets", a_set(reps_completed=None, reps_attempted=None)))


def test_an_isometric_hold_needs_no_reps():
    plank = a_set(exercise="plank", reps_completed=None, reps_attempted=None,
                  duration_s=60)
    assert validate_record("sets", plank) == []


# ---- case 2: a set that stopped short of failure --------------------------------------

def test_an_unstated_endpoint_is_never_read_as_maximal():
    """THE defect. 13 reps against a stated max of 12 read as maximal; set 2
    held 92% of it, where genuine failure leaves 55-70%. `null` means nobody
    said, and nobody said is not a maximum.
    """
    assert says_it_was_maximal(a_set(failure=None)) is False
    assert says_it_was_maximal(a_set(failure="volitional")) is False
    assert says_it_was_maximal(a_set(failure="muscular")) is True
    assert says_it_was_maximal(a_set(failure="technical")) is True


def test_failure_is_three_states_because_to_failure_is_ambiguous():
    assert set(FAILURE_KINDS) == {"technical", "muscular", "volitional"}
    for kind in FAILURE_KINDS:
        assert validate_record("sets", a_set(failure=kind)) == []
    assert any("failure" in p for p in validate_record(
        "sets", a_set(failure="yes")))


def test_the_push_up_block_is_representable():
    """13, 12, 10 with the endpoint stated - which is what was missing."""
    block = [a_set(set_index=i, reps_completed=r, reps_attempted=r,
                   failure="volitional", rir=3)
             for i, r in enumerate((13, 12, 10), start=1)]
    assert all(validate_record("sets", s) == [] for s in block)
    assert not any(says_it_was_maximal(s) for s in block)


# ---- loads do not all mean the same thing ----------------------------------------------

def test_a_stack_number_carries_its_machine():
    """66 on two machines is two different loads (#60), so the value is
    meaningless without the machine it is a number about."""
    orphan = a_set(load=66, load_type="machine_stack", machine=None)
    assert any("machine" in p for p in validate_record("sets", orphan))


def test_bodyweight_carries_no_load_of_its_own():
    """The load IS the athlete, and it changes as they do - push-ups get
    easier on a cut for reasons unrelated to strength."""
    assert any("bodyweight" in p for p in validate_record(
        "sets", a_set(load_type="bodyweight", load=80)))
    assert validate_record("sets", a_set(load_type="bodyweight",
                                         load=None)) == []


def test_added_mass_needs_a_number_to_add():
    assert any("bodyweight_plus" in p for p in validate_record(
        "sets", a_set(load_type="bodyweight_plus", load=None)))
    assert validate_record("sets", a_set(load_type="bodyweight_plus",
                                         load=20)) == []


def test_assistance_is_a_magnitude_not_a_negative_load():
    assert any("assistance" in p for p in validate_record(
        "sets", a_set(load_type="assisted", load=-20)))
    assert validate_record("sets", a_set(load_type="assisted", load=20)) == []


def test_load_type_is_closed_because_there_is_no_sixth_answer():
    assert set(LOAD_TYPES) == {"external", "bodyweight", "bodyweight_plus",
                               "assisted", "machine_stack"}
    assert any("load_type" in p for p in validate_record(
        "sets", a_set(load_type="band")))


# ---- the vocabularies -------------------------------------------------------------------

def test_set_type_is_a_registry_because_methodology_coins_new_ones():
    """The contrast with `load_type` is the point: that one is complete by
    construction, this one is a sample of a moving field (G85)."""
    for seed in ("working", "warmup", "drop", "backoff", "amrap", "cluster",
                 "rest_pause", "myo_rep"):
        assert seed in set_types(), seed


def test_an_unfamiliar_set_type_resolves_rather_than_erroring():
    assert set_type_of({"set_type": "something nobody here imagined"}) == "unknown"
    problems = validate_record("sets", a_set(set_type="something new"))
    # A FINDING and nothing else: the row is otherwise fine, so an
    # unfamiliar term must not drag other complaints along with it.
    assert len(problems) == 1 and "unknown set type" in problems[0]


def test_curated_aliases_resolve_and_nothing_is_fuzzy_matched():
    assert set_type_of({"set_type": "warm-up"}) == "warmup"
    assert set_type_of({"set_type": "dropset"}) == "drop"
    # A matcher that turned this into `warmup` would turn something else into
    # `warmup` silently, and nobody would find out.
    assert set_type_of({"set_type": "warmish"}) == "unknown"


def test_there_is_exactly_one_laterality_axis():
    """#99 must not add a second under another name. `null` is unstated and
    is never defaulted to bilateral."""
    assert set(SIDE_VALUES) == {"left", "right", "bilateral", "alternating"}
    assert validate_record("sets", a_set(side=None)) == []
    assert any("side" in p for p in validate_record("sets", a_set(side="both")))


def test_rir_and_rpe_are_kept_as_stated_and_never_converted():
    assert validate_record("sets", a_set(rir=3)) == []
    assert validate_record("sets", a_set(rpe=7.5)) == []
    assert validate_record("sets", a_set(rir=2, rpe=8)) == []
    both = validate_record("sets", a_set(rir=5, rpe=10))
    assert any(p.startswith("advisory:") for p in both), (
        "wildly inconsistent, and still both kept")


# ---- corrections must name one row --------------------------------------------------------

def test_correcting_set_two_of_four_retires_only_set_two(tmp_path):
    """Many sets share a date and a source, so without the position tuple a
    `supersedes` retires the whole block - the #43 defect, which cost real
    data once already."""
    root = repo(tmp_path)
    v = Vitai(root)
    for row in STACK:
        v.append("sets", {k: val for k, val in row.items()
                          if k != "recorded_at"})
    target = line_key("sets", STACK[1])
    v.append("sets", {**{k: val for k, val in STACK[1].items()
                         if k != "recorded_at"},
                      "reps_completed": 10, "reps_attempted": 12,
                      "failure": "technical", "supersedes": target})
    live = v.dataset("sets")
    assert len(live) == 4, "a correction retired sets it did not name"
    corrected = next(r for r in live if r["set_index"] == 2)
    assert corrected["reps_completed"] == 10
    assert [r["load"] for r in sorted(live, key=lambda r: r["set_index"])] == [
        59, 66, 73, 66]


def test_two_exercises_first_sets_are_different_rows():
    assert line_key("sets", a_set(exercise="push-up", set_index=1)) != \
        line_key("sets", a_set(exercise="squat", set_index=1))


def test_a_circuit_is_rounds_rather_than_unrelated_rows():
    """Without loop membership a 5-round circuit is 25 rows with nothing
    saying they belong together."""
    circuit = [a_set(exercise=ex, block=2, round=rnd, set_index=i,
                     reps_completed=10, reps_attempted=10)
               for rnd in range(1, 6)
               for i, ex in enumerate(("push-up", "squat", "row",
                                       "lunge", "plank"), start=1)]
    assert all(validate_record("sets", s) == [] for s in circuit)
    assert len({line_key("sets", s) for s in circuit}) == 25, (
        "two sets of the circuit share an identity")


# ---- the record's shape ------------------------------------------------------------------

def test_sessions_gains_no_nested_array():
    """Flat one-object-per-line is the whole repo's shape."""
    assert "sets" not in KEYS["sessions"]
    assert all(isinstance(k, str) for k in KEYS["sets"])


def test_a_set_carries_the_full_provenance_suite():
    """It is an observation dataset: `capture` distinguishes a narrated set
    from a photographed console (#78)."""
    for key in ("origin", "path", "origin_evidence", "capture", "read_by"):
        assert key in KEYS["sets"], key
    photo = a_set(capture="photo", read_by="model", origin="gym-console")
    assert validate_record("sets", photo) == []
    assert any("read_by" in p for p in validate_record(
        "sets", a_set(capture="photo", read_by=None)))


def test_sets_are_kept_exactly_as_recorded_for_now(tmp_path):
    """`sets` is deliberately NOT in `RESOLVED_DATASETS` yet, and this pins
    why rather than pretending it is finished.

    The resolver's unit is one canonical record per DATE. A set is not a
    per-date quantity - four sets of one exercise on one morning are four
    things that happened, not four claims about one - so adding `sets` there
    collapsed a whole block into a single row. Per-set resolution needs the
    resolver keyed on the position tuple, the way #43 taught `sessions` to key
    on `activity_id`, and that is its own increment.

    Until then nothing is merged, which is the safe direction: a claim kept is
    recoverable and a claim merged away is not.
    """
    root = repo(tmp_path)
    write(root, STACK)
    assert len(Vitai(root).dataset("sets")) == 4
    assert len(Vitai(root).sets()) == 4, "a block was collapsed"


def test_every_dataset_can_actually_be_created_as_a_table():
    """`index` is a SQL reserved word, and so is `table` - both were the
    obvious name for a field one increment apart, and both broke the read
    model. Asserted by CREATING the tables rather than against a keyword list
    I would have to keep correct: `key` on `thresholds` is in SQLite's
    keyword list and is perfectly legal as a column.
    """
    from vitai.db import _cols
    con = sqlite3.connect(":memory:")
    try:
        for dataset, keys in KEYS.items():
            con.execute(f"CREATE TABLE {dataset}({_cols(keys)})")
    finally:
        con.close()


def test_sets_reach_the_read_model(tmp_path):
    root = repo(tmp_path)
    write(root, STACK)
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        rows = con.execute(
            "SELECT set_index, load, machine, reps_completed FROM sets "
            "ORDER BY set_index").fetchall()
    finally:
        con.close()
    assert rows[2] == (3, 73.0, "leg-press-a", 0)


# ---- the surface --------------------------------------------------------------------------

def test_a_failed_set_reads_as_failed_not_as_zero(tmp_path, capsys):
    """"0 reps" reads as nothing happened. The most informative set of the
    block has to read like one."""
    root = repo(tmp_path)
    write(root, STACK)
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "0 reps" not in out


def test_a_stack_number_never_prints_without_its_machine(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, STACK)
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "@" in ln]
    assert len(lines) == 4, "the loop below would have passed vacuously"
    for line in lines:
        assert "leg-press-a" in line, line


def test_an_unstated_endpoint_prints_as_unstated(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [a_set(failure=None)])
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    assert "endpoint unstated" in capsys.readouterr().out


def test_sets_read_back_in_the_order_they_were_performed(tmp_path):
    """13, 12, 10 is a fatigue curve; 10, 12, 13 is a warm-up. File order is
    not the claim - the counters are."""
    root = repo(tmp_path)
    write(root, [a_set(set_index=3, reps_completed=10, reps_attempted=10),
                 a_set(set_index=1, reps_completed=13, reps_attempted=13),
                 a_set(set_index=2, reps_completed=12, reps_attempted=12)])
    assert [r["reps_completed"] for r in Vitai(root).sets()] == [13, 12, 10]


def test_an_unnumbered_set_sorts_last_rather_than_first(tmp_path):
    """Placing a set nobody numbered at the front would invent a claim about
    when it happened."""
    root = repo(tmp_path)
    write(root, [a_set(set_index=None, reps_completed=8, reps_attempted=8),
                 a_set(set_index=1, reps_completed=13, reps_attempted=13)])
    assert [r["reps_completed"] for r in Vitai(root).sets()] == [13, 8]


def test_the_date_filter_scopes_the_listing(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [a_set(), a_set(date="2030-05-02",
                                session_start="2030-05-02T07:10:00+02:00")])
    capsys.readouterr()
    main(["sets", "--root", str(root), "--on", "2030-05-02"])
    out = capsys.readouterr().out
    assert "2030-05-01" not in out and "2030-05-02" in out


def test_the_json_form_is_the_same_rows(tmp_path, capsys):
    root = repo(tmp_path)
    # Written in the WRONG order, so the assertion below fails if the sort is
    # removed - STACK's own file order already matches the expected output.
    write(root, [STACK[2], STACK[0], STACK[3], STACK[1]])
    capsys.readouterr()
    main(["sets", "--root", str(root), "--json"])
    rows = [json.loads(line) for line in
            capsys.readouterr().out.strip().splitlines()]
    assert [r["set_index"] for r in rows] == [1, 2, 3, 4]
    assert [r["load"] for r in rows] == [59, 66, 73, 66]


def test_an_empty_record_says_so_rather_than_printing_nothing(tmp_path, capsys):
    root = repo(tmp_path)
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    assert "no sets logged" in capsys.readouterr().out


@pytest.mark.parametrize("key", ["block", "round", "set_index", "rest_s",
                                 "duration_s"])
def test_counters_are_whole_numbers(key):
    assert any(key in p for p in validate_record("sets", a_set(**{key: -1})))


# ---- what the review of this feature found ------------------------------------------

def test_a_set_nobody_numbered_cannot_be_corrected_so_it_is_rejected():
    """Two unnumbered sets of one exercise share an identity, so a
    `supersedes` naming either retires both - #43 again, in the increment
    whose acceptance criterion is that it cannot happen.
    """
    assert any("set_index" in p for p in validate_record(
        "sets", a_set(set_index=None)))


def test_a_drop_sets_segments_each_have_their_own_identity():
    """`set_types.toml` prescribes logging a drop set as several rows sharing
    a block. Sharing an INDEX as well would give them one identity, so
    correcting the first segment would retire all of them."""
    segments = [a_set(set_type="drop", block=2, set_index=i, load=load,
                      load_type="external", reps_completed=6, reps_attempted=6)
                for i, load in enumerate((60, 50, 40), start=1)]
    assert all(validate_record("sets", s) == [] for s in segments)
    assert len({line_key("sets", s) for s in segments}) == 3


def test_a_stated_zero_attempt_is_a_statement_not_a_silence():
    """`or` read a stated zero as unstated and fell through to the completed
    count, contradicting the number the athlete wrote down."""
    from vitai.sets import attempted
    assert attempted({"reps_attempted": 0, "reps_completed": 8}) == 0
    assert attempted({"reps_attempted": None, "reps_completed": 8}) == 8


def test_a_row_claiming_nothing_happened_is_rejected(tmp_path, capsys):
    """0 of 0 with no duration validated clean and then printed "0 reps" -
    the exact reading the FAILED branch exists to prevent."""
    assert any("says nothing happened" in p for p in validate_record(
        "sets", a_set(reps_completed=0, reps_attempted=0)))
    root = repo(tmp_path)
    write(root, [a_set(reps_completed=0, reps_attempted=0)])
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    assert "0 reps" not in capsys.readouterr().out


def test_an_unsessioned_set_sorts_last_like_every_other_unstated_thing(tmp_path):
    """The doctrine was applied to the counters and not to the nullable field
    in front of them, so a set nobody placed sorted FIRST - inventing a claim
    that it happened before the ones that were placed."""
    root = repo(tmp_path)
    write(root, [a_set(session_start=None, reps_completed=8, reps_attempted=8),
                 a_set(reps_completed=13, reps_attempted=13, set_index=2)])
    assert [r["reps_completed"] for r in Vitai(root).sets()] == [13, 8]


def test_one_bad_counter_does_not_take_down_the_whole_listing(tmp_path):
    """`validate` reports a counter of the wrong type but does not stop the
    file loading, so comparing it against an int raised and the listing died
    rather than sorting oddly."""
    root = repo(tmp_path)
    write(root, [{**a_set(), "block": "2"}, a_set(block=1, set_index=2)])
    rows = Vitai(root).sets()
    assert len(rows) == 2


def test_a_session_start_that_is_not_an_instant_is_rejected():
    """It is the leading identity field, so two spellings of one instant fork
    the identity and a correction citing the other names no line."""
    assert any("session_start" in p for p in validate_record(
        "sets", a_set(session_start="7am-ish")))
    assert validate_record("sets", a_set(session_start=None)) == []


def test_a_stack_number_is_never_labelled_as_kilograms(tmp_path, capsys):
    """A mass unit on a pin number is #60 written down: it makes the value
    look comparable across machines, which is the one thing it is not."""
    row = a_set(load=66, load_type="machine_stack", machine="leg-press-a",
                load_unit="kg", reps_completed=12, reps_attempted=12)
    assert any("MASS" in p for p in validate_record("sets", row))
    root = repo(tmp_path)
    write(root, [{**row, "load_unit": None}])
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    out = capsys.readouterr().out
    assert "kg" not in out and "stack" in out


def test_a_null_slug_still_keys_the_way_it_always_did():
    """Generalising IDENTITY_KEY to accept a tuple silently changed how a
    row with an explicit null identity renders. Any existing goals or medical
    file holding a `supersedes` that names the old spelling would have had
    the line it corrected quietly un-retired on the next load.
    """
    assert line_key("goals", {"slug": None, "date": "2030-01-01"}) == (
        "None@2030-01-01")
    assert line_key("goals", {"date": "2030-01-01"}) == "@2030-01-01"
    assert line_key("goals", {"slug": "cut", "date": "2030-01-01"}) == (
        "cut@2030-01-01")


def test_half_points_are_standard_on_the_rir_anchored_scale():
    """A deliberate loosening of `rpe` from integer to numeric, and it
    reaches `sessions` too - strictly looser, so nothing that validated
    before stops validating."""
    assert validate_record("sets", a_set(rpe=7.5)) == []
    session = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
               "duration_s": 1800, "avg_hr": None, "max_hr": None,
               "cadence": None, "kcal": None, "location": None, "rpe": 7.5,
               "note": None}
    assert validate_record("sessions", session) == []
