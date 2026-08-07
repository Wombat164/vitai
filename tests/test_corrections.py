"""What a correction did, and what the record cannot tell you (#143).

A `supersedes` is accepted, applied and never characterised. The chain holds
both values, both timestamps and the context they landed in, and nothing looks
at any of it - `retractions` records that a claim came down, `dataset` returns
the survivor, and the row that lost sits in the file where nothing reads it.

THE CONSTRAINT IS THE HARDER HALF OF THE ISSUE. "Three of the last four
corrections moved in the same direction" is a fact about a file. "You are
massaging your numbers" is not something a training log gets to say, and the
issue was filed with the constraint attached precisely so nobody builds the
second version.

So the load-bearing test here is not any assertion about a value. It is
`test_it_cannot_tell_the_honest_correction_from_the_flattering_one`, which
builds the corpus's deliberate control pair - two records identical in shape
and opposite in ground truth - and asserts the output is the same. A detector
that appeared to separate them would be claiming a discrimination it does not
have, and the honest thing is to say the shape is the shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import Vitai, init
from vitai.corrections import characterise

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
PERSONAS = ROOT / "tests" / "fixtures" / "personas"


def _moved(correction: dict, field: str) -> dict:
    got, = [m for m in correction["moved"] if m["field"] == field]
    return got


def _weights(tmp_path: Path, values, note: str) -> Vitai:
    """One reading, then a correction of it. The shape both halves share."""
    v = Vitai(init(tmp_path / "content"))
    was, now = values
    v.append("weight", {"date": "2030-05-01", "kg": was, "source": "scale"})
    v.append("weight", {"date": "2030-05-02", "kg": now, "source": "scale",
                        "supersedes": "2030-05-01/scale", "note": note})
    return v


# --- what it says about a correction ------------------------------------------

def test_it_says_which_fields_moved_and_which_way(tmp_path):
    """The characterisation the record could not produce. `retractions` says
    a claim came down; this says the quantity went from 83 to 80."""
    v = _weights(tmp_path, (83.0, 80.0), "the scale was on the carpet")

    correction, = v.corrections("weight")

    assert _moved(correction, "kg") | {} == {
        "field": "kg", "was": 83.0, "now": 80.0, "direction": "down",
        "same_direction_run": 1}


def test_it_reads_the_row_the_normal_door_removes(tmp_path):
    """THE REASON THIS IS THE ONE SURFACE THAT DOES NOT GO THROUGH `dataset`.
    The row a correction retired is exactly the row the read door drops, so
    reading through it would leave this able to see only the half that won."""
    v = _weights(tmp_path, (83.0, 80.0), "corrected")

    assert [r["kg"] for r in v.dataset("weight")] == [80.0]
    assert _moved(v.corrections("weight")[0], "kg")["was"] == 83.0


def test_it_says_how_long_the_record_held_the_old_value(tmp_path):
    """From TRANSACTION time on both rows. The question is how long the record
    said the wrong thing, not how far apart the days were."""
    correction, = _weights(tmp_path, (83.0, 80.0), "later").corrections("weight")

    assert correction["lag_days"] is not None
    assert correction["lag_days"] >= 0


def test_an_unstamped_row_gives_no_lag_rather_than_a_zero(tmp_path):
    """A missing lag and a same-second correction are different facts, and the
    second is the interesting one - so collapsing them would invent the more
    remarkable of the two."""
    root = init(tmp_path / "content")
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 83.0, "source": "scale", "_gen": 1},
        {"date": "2030-05-02", "kg": 80.0, "source": "scale", "_gen": 1,
         "supersedes": "2030-05-01/scale"},
    ]) + "\n", encoding="utf-8")

    correction, = Vitai(root).corrections("weight")

    assert correction["lag_days"] is None


def test_the_identity_date_is_not_reported_as_a_moved_value():
    """A correction dated later than its target has not re-dated a reading:
    where the reference is `<date>/<source>` the date is part of what NAMES
    the row. The naive diff reported `date: was 2027-09-27, now 2027-10-04` on
    a shipped fixture whose reading was never re-dated at all, so it is
    carried as `target_date` beside the correction's own date instead.
    """
    correction, = characterise(PERSONAS / "tom" / "data", "weight")

    assert correction["date"] != correction["target_date"]
    assert not [m for m in correction["moved"] if m["field"] == "date"]
    assert _moved(correction, "kg")["direction"] == "down"


def test_a_word_replacing_a_word_has_no_direction(tmp_path):
    """Picking one - alphabetical, or some ranking of session types - would be
    an ordering this engine never declared."""
    v = Vitai(init(tmp_path / "content"))
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch"})
    v.append("sessions", {"date": "2030-05-02", "type": "walk",
                          "distance_km": 5.0, "source": "watch",
                          "supersedes": "2030-05-01/watch"})

    correction, = v.corrections("sessions")

    assert _moved(correction, "type")["direction"] == "changed"


@pytest.mark.parametrize("was,now,expected", [
    (5.0, 4.0, "down"),
    (5.0, 6.0, "up"),
    ("run", "walk", "changed"),
    (None, 5.0, "changed"),
    (5.0, None, "changed"),
    # BOOLEANS ARE NOT NUMBERS HERE, though Python says they are. `True > False`
    # is legal arithmetic and would report a flag being set as an INCREASE,
    # which is a direction nobody declared for a yes-or-no.
    (True, False, "changed"),
    (False, True, "changed"),
])
def test_direction_answers_only_where_the_question_has_an_answer(
        was, now, expected):
    """Every branch, because a branch nothing exercises can be rewritten to
    return anything: replacing one `changed` with `up` left the whole file
    green."""
    from vitai.corrections import _direction

    assert _direction(was, now) == expected


def test_a_chain_pairs_each_correction_with_the_one_it_displaced(tmp_path):
    """A CORRECTION IS A LEGITIMATE TARGET, and excluding them was a bug.

    In a chain every row shares one key: A, then B superseding it, then C
    superseding it again. Skipping rows that carry `supersedes` made C pair
    with A and report a move of 83 to 81 that nobody made - what C displaced
    was B, and the value it replaced was 82. Found by mutating the exclusion
    away and watching the suite stay green, which meant no fixture had a
    chain in it at all.
    """
    v = Vitai(init(tmp_path / "content"))
    for kg, ref in ((83.0, None), (82.0, "2030-05-01/scale"),
                    (81.0, "2030-05-01/scale")):
        row = {"date": "2030-05-01", "kg": kg, "source": "scale"}
        if ref:
            row["supersedes"] = ref
        v.append("weight", row)

    b, c = v.corrections("weight")

    assert (_moved(b, "kg")["was"], _moved(b, "kg")["now"]) == (83.0, 82.0)
    assert (_moved(c, "kg")["was"], _moved(c, "kg")["now"]) == (82.0, 81.0)
    assert c["corrects"] == b["row"]


def test_the_order_is_the_record_and_not_the_dict(tmp_path):
    """Same input, same output, and TRANSACTION order within a dataset.

    Sorting the lot by `date` looked tidier and was wrong: a run is counted in
    the order corrections landed, so a back-dated correction listed above the
    one it followed put `run 2` on the reader's screen above `run 1`.
    """
    v = Vitai(init(tmp_path / "content"))
    v.append("weight", {"date": "2030-05-02", "kg": 83.0, "source": "scale"})
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch"})
    v.append("sessions", {"date": "2030-05-03", "type": "run",
                          "distance_km": 4.0, "source": "watch",
                          "supersedes": "2030-05-01/watch"})
    v.append("weight", {"date": "2030-05-04", "kg": 80.0, "source": "scale",
                        "supersedes": "2030-05-02/scale"})

    got = v.corrections()

    assert [(c["dataset"], c["date"]) for c in got] == [
        ("weight", "2030-05-04"), ("sessions", "2030-05-03")]
    assert got == Vitai(v.root).corrections()


# --- the runs -----------------------------------------------------------------

def test_a_run_grows_while_the_direction_holds(tmp_path):
    """Three corrections to one quantity, all down, is a run of three."""
    v = Vitai(init(tmp_path / "content"))
    for day, kg in (("2030-05-01", 83.0), ("2030-05-02", 82.0),
                    ("2030-05-03", 81.0)):
        v.append("weight", {"date": day, "kg": kg, "source": "scale"})
    for n, (day, kg) in enumerate(
            (("2030-05-05", 82.5), ("2030-05-06", 81.5), ("2030-05-07", 80.5))):
        v.append("weight", {"date": day, "kg": kg, "source": "scale",
                            "supersedes": f"2030-05-0{n + 1}/scale"})

    runs = [_moved(c, "kg")["same_direction_run"] for c in v.corrections("weight")]

    assert runs == [1, 2, 3]


def test_a_run_counts_only_within_one_field(tmp_path):
    """Weight moving down and distance moving down are two corrections and two
    unrelated sequences. Counting them together would manufacture the longer
    number - and one field per test could not see it: with only `kg` moving
    there is no second field to contaminate the count, so keying the run on
    direction alone passed.
    """
    v = Vitai(init(tmp_path / "content"))
    v.append("daily", {"date": "2030-05-01", "steps": 9000, "kcal_in": 2400,
                       "source": "athlete"})
    v.append("daily", {"date": "2030-05-02", "steps": 8000, "kcal_in": 2400,
                       "source": "athlete"})
    v.append("daily", {"date": "2030-05-03", "steps": 9000, "kcal_in": 2000,
                       "source": "athlete", "supersedes": "2030-05-01/athlete"})
    v.append("daily", {"date": "2030-05-04", "steps": 7000, "kcal_in": 2400,
                       "source": "athlete", "supersedes": "2030-05-02/athlete"})

    first, second = v.corrections("daily")

    assert _moved(first, "kcal_in")["direction"] == "down"
    assert _moved(second, "steps")["direction"] == "down"
    # Two fields, one direction, two separate runs of one.
    assert _moved(first, "kcal_in")["same_direction_run"] == 1
    assert _moved(second, "steps")["same_direction_run"] == 1


def test_a_run_of_one_is_one_and_not_null(tmp_path):
    """The honest floor. One correction is a run of one, and a null there
    would have to be read as either "none" or "not counted"."""
    v = _weights(tmp_path, (83.0, 80.0), "once")

    assert _moved(v.corrections("weight")[0], "kg")["same_direction_run"] == 1


def test_a_move_the_other_way_ends_the_run(tmp_path):
    """Otherwise the count is a total rather than a run, and a record with one
    correction in each direction every week would climb forever."""
    v = Vitai(init(tmp_path / "content"))
    for day, kg in (("2030-05-01", 83.0), ("2030-05-02", 82.0),
                    ("2030-05-03", 81.0)):
        v.append("weight", {"date": day, "kg": kg, "source": "scale"})
    v.append("weight", {"date": "2030-05-04", "kg": 82.5, "source": "scale",
                        "supersedes": "2030-05-01/scale"})   # down
    v.append("weight", {"date": "2030-05-05", "kg": 81.5, "source": "scale",
                        "supersedes": "2030-05-02/scale"})   # down
    v.append("weight", {"date": "2030-05-06", "kg": 99.0, "source": "scale",
                        "supersedes": "2030-05-03/scale"})   # up

    v.append("weight", {"date": "2030-05-07", "kg": 80.0, "source": "scale"})
    v.append("weight", {"date": "2030-05-08", "kg": 78.0, "source": "scale",
                        "supersedes": "2030-05-07/scale"})   # down again

    runs = [(_moved(c, "kg")["direction"], _moved(c, "kg")["same_direction_run"])
            for c in v.corrections("weight")]

    # The FOURTH entry is what the reset is for. Without it the run is 3: the
    # earlier downs were never cleared, so a record alternating direction every
    # week would climb forever. Stopping at the `up` could not see that,
    # because a first move in a direction reads as 1 either way.
    assert runs == [("down", 1), ("down", 2), ("up", 1), ("down", 1)]


# --- it reports what the engine actually did ----------------------------------

def test_a_correction_that_never_applied_is_not_reported(tmp_path):
    """A row stamped BEFORE the row it names retires nothing - `retire` walks
    the merged order and the target is not behind it. Characterising it anyway
    described a move nobody made, and that invented direction then fed a run.

    The check is on the TARGET, not on the correcting row: the target has to
    be gone from the survivors.
    """
    root = init(tmp_path / "content")
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-02", "kg": 80.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-02T08:00:00+02:00",
         "supersedes": "2030-05-01/scale"},
        {"date": "2030-05-01", "kg": 83.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-03T08:00:00+02:00"},
    ]) + "\n", encoding="utf-8")
    v = Vitai(root)

    assert sorted(r["kg"] for r in v.dataset("weight")) == [80.0, 83.0]
    assert v.corrections("weight") == []


def test_the_order_is_the_instant_and_not_the_string(tmp_path):
    """THE #38 MISTAKE, which `clocks` and `devices.merge` both carry a warning
    about and this re-made. `+02:00` sorts after `+00:00` as a string whatever
    the instants are, so two rows either side of a clock change picked the
    wrong target - and the surface reported a value as withdrawn while
    `dataset()` still returned it standing.
    """
    root = init(tmp_path / "content")
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        # 21:00Z, older.
        {"date": "2030-05-01", "kg": 83.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-01T23:00:00+02:00"},
        # 21:30Z, NEWER, but the string sorts first.
        {"date": "2030-05-01", "kg": 84.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-01T22:30:00+01:00"},
        {"date": "2030-05-01", "kg": 80.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-04T08:00:00+02:00",
         "supersedes": "2030-05-01/scale"},
    ]) + "\n", encoding="utf-8")
    v = Vitai(root)

    standing = sorted(r["kg"] for r in v.dataset("weight"))
    correction, = v.corrections("weight")

    # Whatever it says was withdrawn must be a value the record no longer has.
    assert _moved(correction, "kg")["was"] not in standing
    assert _moved(correction, "kg")["was"] == 84.0


def test_a_correction_reaches_across_device_files(tmp_path):
    """Line numbers restart in every device stream, so comparing them across
    files meant nothing: a correction in `weight.jsonl` naming a target in
    `weight.laptop.jsonl` vanished from this surface completely, and another
    shape invented a move. Rows are named by the engine's row grammar now,
    and the sequence is the union `load` reads.
    """
    root = init(tmp_path / "content")
    (root / "data" / "weight.laptop.jsonl").write_text(json.dumps(
        {"date": "2030-05-01", "kg": 83.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-01T08:00:00+02:00"}) + "\n", encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(json.dumps(
        {"date": "2030-05-02", "kg": 80.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-02T08:00:00+02:00",
         "supersedes": "2030-05-01/scale"}) + "\n", encoding="utf-8")
    v = Vitai(root)

    assert [r["kg"] for r in v.dataset("weight")] == [80.0]
    correction, = v.corrections("weight")
    assert _moved(correction, "kg")["was"] == 83.0
    assert correction["row"] != correction["corrects"]


def test_an_event_dataset_is_never_characterised(tmp_path):
    """`emissions` never retires: two assertions on one day are two things
    that were said, and a later row cannot make an earlier one not have been
    said. A correction there applies to nothing, so there is nothing to
    characterise - and reporting one would describe a retirement the engine
    refuses to perform.
    """
    root = init(tmp_path / "content")
    (root / "data" / "emissions.jsonl").write_text("\n".join(
        json.dumps(r) for r in [
            {"date": "2030-05-01", "kind": "verdict", "metric": "weight_rate",
             "statement": "first", "surface": "cli", "policy_asof": "2030-05-01",
             "contract": "1", "_gen": 1,
             "recorded_at": "2030-05-01T08:00:00+02:00"},
            {"date": "2030-05-01", "kind": "verdict", "metric": "weight_rate",
             "statement": "second", "surface": "cli",
             "policy_asof": "2030-05-01", "contract": "1", "_gen": 1,
             "recorded_at": "2030-05-02T08:00:00+02:00",
             "supersedes": "2030-05-01/"},
        ]) + "\n", encoding="utf-8")
    v = Vitai(root)

    assert len(v.dataset("emissions")) == 2
    assert v.corrections("emissions") == []


def test_a_mixed_stamping_gives_no_lag_rather_than_an_exception(tmp_path):
    """One row naive and one carrying an offset. Subtracting them raises, and
    a read surface that dies on a legal record is worse than one that declines
    to answer a question it cannot: the difference between them rests on an
    assumed offset, which is a guess.
    """
    root = init(tmp_path / "content")
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 83.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-01T08:00:00"},
        {"date": "2030-05-02", "kg": 80.0, "source": "scale", "_gen": 1,
         "recorded_at": "2030-05-02T08:00:00+02:00",
         "supersedes": "2030-05-01/scale"},
    ]) + "\n", encoding="utf-8")

    correction, = Vitai(root).corrections("weight")

    assert correction["lag_days"] is None
    assert _moved(correction, "kg")["was"] == 83.0


def test_an_identity_keyed_row_can_be_indistinguishable_from_its_correction():
    """A LIMIT OF THE RECORD, pinned rather than papered over. `refs` appends
    an ordinal only on the date-and-source branch, so four rows of one goal all
    render as `goals:<slug>` and a correction names the same string as its
    target. That is #239's subject and not this surface's to fix - but a
    consumer reading `row == corrects` is being told something true: the
    reference cannot tell them apart.
    """
    correction, = [c for c in Vitai(DEMO).corrections() if c["dataset"] == "goals"]

    assert correction["row"] == correction["corrects"]
    assert correction["target_date"] != correction["date"]


def test_the_naming_fields_are_never_reported_as_values_that_moved():
    """`date` says WHEN a row is, not what it values, and a correction written
    on a later day has not re-dated anything. True whichever way the dataset
    keys: half the reference in `<date>/<source>`, the effective-dating axis in
    an identity-keyed one. The naive diff claimed a re-dating on two shipped
    fixtures whose targets were never re-dated at all.
    """
    for correction in Vitai(DEMO).corrections():
        assert not [m for m in correction["moved"]
                    if m["field"] in ("date", "slug", "source")], correction
        assert correction["target_date"]


# --- the constraint -----------------------------------------------------------

def test_it_cannot_tell_the_honest_correction_from_the_flattering_one(tmp_path):
    """THE LOAD-BEARING TEST, and the reason the issue was filed with its own
    constraint attached.

    The persona corpus pairs an honest back-fill with a flattering one on
    purpose: structurally identical, same fingerprint, opposite ground truth.
    A detector that separated them would be claiming a discrimination it does
    not have. So the two records here differ only in the athlete's own words,
    and everything the engine produces about them is identical.
    """
    honest = _weights(tmp_path / "a", (83.0, 80.0),
                      "the first reading was on carpet, this is the real one")
    flattering = _weights(tmp_path / "b", (83.0, 80.0),
                          "actually it was 80")

    a, = honest.corrections("weight")
    b, = flattering.corrections("weight")

    def engine_authored(c):
        """Everything except what the athlete wrote. `note` is his words, and
        it appears twice - as the row's note and as a field that moved."""
        return {k: v for k, v in c.items()
                if k not in ("note", "moved", "lag_days")} | {
            "moved": [m for m in c["moved"] if m["field"] != "note"]}

    assert engine_authored(a) == engine_authored(b)
    assert a["note"] != b["note"], "the fixtures have to actually differ"
    # And the lag is the same shape on both: a number, not a discriminator.
    assert (a["lag_days"] is None) == (b["lag_days"] is None)


def test_nothing_it_returns_is_a_sentence_the_engine_wrote():
    """STRUCTURAL, NOT INTENTIONAL. A judgement cannot leak from a surface
    with no prose on it, so the only strings the engine authors here are field
    names and a closed direction vocabulary. `note`, `was` and `now` carry the
    athlete's own words and are not the engine speaking.
    """
    authored = set()
    for correction in Vitai(DEMO).corrections():
        authored |= {correction["dataset"], correction["reference"]}
        for move in correction["moved"]:
            authored.add(move["direction"])

    assert {"message", "detail", "severity", "verdict"} & set(
        Vitai(DEMO).corrections()[0]) == set()
    for value in authored:
        assert len(str(value).split()) <= 2, value


def test_the_direction_vocabulary_is_closed():
    """Four values, and no fifth appears without somebody deciding to add it.
    An open vocabulary is where a word like `suspicious` arrives."""
    seen = {m["direction"] for c in Vitai(DEMO).corrections()
            for m in c["moved"]}

    assert seen <= {"down", "up", "unchanged", "changed"}
    assert seen


def test_a_long_run_reads_the_same_as_a_short_one(tmp_path):
    """A THRESHOLD IS WHERE A COUNT BECOMES A VERDICT, and the CLI had one.

    It printed `[down, 3 in a row down]` above a run of one and `[down]`
    below it - different WORDS on the far side of `run > 1`, in the one place
    in this feature where the engine composes words at all, while its own
    docstring claimed there was no threshold. The textual test meant to police
    this scanned `corrections.py`, where the threshold was not.

    So this checks the OUTPUT: a run of four, every line the same sentence
    with a different digit.
    """
    v = Vitai(init(tmp_path / "content"))
    for n in range(1, 5):
        v.append("weight", {"date": f"2030-05-0{n}", "kg": 84.0 - n,
                            "source": "scale"})
    for n in range(1, 5):
        v.append("weight", {"date": f"2030-05-1{n}", "kg": 70.0 - n,
                            "source": "scale",
                            "supersedes": f"2030-05-0{n}/scale"})

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "corrections", "weight",
         "--root", str(v.root)], capture_output=True, text=True, check=True)
    kg_lines = [ln for ln in out.stdout.splitlines() if "kg:" in ln]

    assert [ln.split("[")[-1] for ln in kg_lines] == [
        "down, run 1]", "down, run 2]", "down, run 3]", "down, run 4]"]


def test_the_human_rendering_says_nothing_the_engine_did_not_measure():
    """The one surface that composes words, checked as words.

    A judgement reaching a person arrives through this rendering or not at
    all, and every other guarantee test here polices the RETURN VALUE - so a
    printed sentence added to the CLI passed the entire suite, including a
    literal "SUSPICIOUS: pattern detected".
    """
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "corrections",
         "--root", str(DEMO)], capture_output=True, text=True, check=True)

    assert "corrects" in out.stdout, "the rendering has to have produced rows"
    for word in ("suspicious", "unusual", "anomal", "massag", "alert",
                 "pattern", "concern", "warning", "should", "you "):
        assert word not in out.stdout.lower(), word


def test_it_is_asked_and_never_raised():
    """NOT A TRIPWIRE, deliberately. A tripwire is the engine bringing
    something up unprompted, and bringing up "your corrections trend
    downward" unprompted IS the accusation whatever words it uses. Answering
    when asked is not, which is why this is a read surface and the build's
    findings do not grow.
    """
    v = Vitai(DEMO)
    kinds = {t["kind"] for t in v.resolution()["tripwires"]}

    assert v.corrections()
    assert not [k for k in kinds if "correction" in k]
    assert "correction" not in v.rollup().lower()


def test_a_build_writes_nothing_about_them(tmp_path):
    """The other half of not raising: a characterisation that quietly landed
    in the read model would be raised on every read of it."""
    import sqlite3

    v = _weights(tmp_path, (83.0, 80.0), "corrected")
    v.build()
    con = sqlite3.connect(v.root / "derived" / "health.db")
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    assert not [t for t in tables if "correction" in t]


# --- the shipped record -------------------------------------------------------

def test_the_corpus_carries_both_directions():
    """#204's corollary: a fixture holding one value of a distinction proves
    nothing about the distinction, and direction is the distinction here."""
    marcus, = characterise(PERSONAS / "marcus" / "data", "sessions")
    tom, = characterise(PERSONAS / "tom" / "data", "weight")
    demo = [c for c in Vitai(DEMO).corrections() if c["dataset"] == "sessions"]

    assert _moved(marcus, "distance_km")["direction"] == "down"
    assert _moved(tom, "kg")["direction"] == "down"
    assert _moved(demo[0], "distance_km")["direction"] == "up"


def test_the_downward_correction_the_issue_was_filed_about():
    """A session logged at 16 km and corrected to 9 two days later. The issue
    says nothing looks at this; now something can be asked to."""
    correction, = characterise(PERSONAS / "marcus" / "data", "sessions")

    assert _moved(correction, "distance_km")["was"] == 16.0
    assert _moved(correction, "distance_km")["now"] == 9.0
    assert correction["lag_days"] == 2.0


def test_every_persona_and_the_demo_read_without_raising():
    """G26's neighbour: a record with no corrections answers with an empty
    list rather than refusing, and one with an odd chain does not explode."""
    for root in [DEMO] + sorted(p for p in PERSONAS.iterdir()
                                if (p / "data").is_dir()):
        assert isinstance(Vitai(root).corrections(), list)


# --- the doors ----------------------------------------------------------------

def test_the_three_surfaces_agree():
    """P9."""
    from_api = Vitai(DEMO).corrections("sessions")
    from_mcp = mcp.call(DEMO, "corrections", {"dataset": "sessions"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "corrections", "sessions",
         "--root", str(DEMO), "--json"], capture_output=True, text=True,
        check=True)
    from_cli = [json.loads(ln) for ln in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli
    assert from_api


def test_the_cli_says_so_when_there_is_nothing_to_show(tmp_path):
    """An empty answer that prints nothing is indistinguishable from a command
    that failed quietly."""
    root = init(tmp_path / "content")
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "corrections", "--root", str(root)],
        capture_output=True, text=True, check=True)

    assert "no corrections" in out.stdout


def test_an_unknown_dataset_is_refused():
    with pytest.raises(KeyError):
        Vitai(DEMO).corrections("nonsense")
