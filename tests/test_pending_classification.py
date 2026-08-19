"""A correction cannot be recognised before it is appended (#425).

WHAT #425 SAID, AND WHAT IS ACTUALLY TRUE. The issue reasons that an importer's
rows legally carry no `recorded_at`, so a guard asking which claim came later
classifies every incoming row AMBIGUOUS. Measured against this engine, the
shape is sharper and partly different:

  * `append_many` STAMPS BEFORE IT GUARDS. Inside it, rows get their
    `recorded_at` and only then is the corrections guard consulted. So the
    WRITE path is not broken: appending a declared correction over a held row
    works and retires it.

  * THE HOLE IS THAT NOTHING PUBLIC CAN ASK BEFORE THE WRITE, and the private
    function that looks like the answer gave the WRONG one on legal input.
    Called with unstamped rows - which is exactly what an importer holds - it
    refused a correction that names its target, with "this write is stamped
    None". `merge` sorts absent before present by design, so every correction
    in an unstamped batch sorted ahead of its target and came back refused: an
    answer manufactured by the question rather than read off the record.

WHAT THE FIX IS. `_prepared` models the stamp the append will assign - by
running the assignment, not by estimating it - and `pending_problems` asks the
same guard over those rows, so asking gives the answer the write gives. The
guard itself now REFUSES to answer about an unstamped row rather than
answering wrongly. And `classify_pending` says what a row IS in one word, with
no clock consulted to decide it: an undeclared restatement is a second claim,
not a correction, and the engine says so rather than inferring intent from a
timestamp the caller may not author.

Synthetic data only. The 1,354 -> 3,091 day is #425's own fixture: a
MyFitnessPal day exported at lunchtime and completed after dinner.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from vitai.cli import main
from vitai.jsonl import (DataError, PENDING_VERDICTS, append_many,
                         classify_pending, load, pending_problems)

HELD, COMPLETED = 1354, 3091
DAY, SOURCE = "2030-05-01", "mfp-export"
REF = f"{DAY}/{SOURCE}"


def _repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root / "data"


def _daily(**kw):
    """A daily row as an importer legally prepares it: NO `recorded_at`.

    Supplying one is refused outright - "the one clock in the record that
    cannot be authored" - so this is not an omission, it is the only legal
    shape a pending row has.
    """
    row = {"date": DAY, "kcal_in": None, "source": SOURCE, "note": None,
           "steps": None, "_gen": 8}
    row.update(kw)
    return row


def _verdicts(answers):
    return [a["verdict"] for a in answers]


# ---------------------------------------------------------------- the halves
# that already worked, pinned before anything else so a regression in them is
# not read as a result about the new surface.

def test_the_write_path_accepts_a_declared_correction(tmp_path):
    """`append_many` stamps and then guards, so the correction applies and the
    stale row goes."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    append_many(data, "daily", [_daily(kcal_in=COMPLETED, supersedes=REF)],
                device="phone")
    assert [r["kcal_in"] for r in load(data, "daily")] == [COMPLETED]


def test_an_undeclared_restatement_is_two_claims_not_a_correction(tmp_path):
    """A row that does not NAME its target retires nothing. Both claims live
    and resolution picks between them - the engine behaving correctly, not a
    hole."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    append_many(data, "daily", [_daily(kcal_in=COMPLETED)], device="phone")
    assert sorted(r["kcal_in"] for r in load(data, "daily")) == [HELD,
                                                                COMPLETED]


# ------------------------------------------------------------------ the hole

def test_asking_before_the_write_gives_the_answer_the_write_gives(tmp_path):
    """THE DEFECT #425 NAMES. An importer must be able to ask what the append
    will do BEFORE it writes, and the answer must match what the append then
    does.

    Against the engine as it was, this failed on the import line: nothing
    public answered at all.
    """
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]

    assert pending_problems(data, "daily", pending, device="phone") == [], (
        "the engine refused, before the write, a correction the write accepts")
    append_many(data, "daily", pending, device="phone")
    assert [r["kcal_in"] for r in load(data, "daily")] == [COMPLETED]


def test_the_guard_refuses_to_answer_about_an_unstamped_row(tmp_path):
    """AND THE OLD WRONG ANSWER IS GONE RATHER THAN MERELY BYPASSED.

    The private guard used to answer an ordering question about rows with no
    ordering field, and its answer - "this write is stamped None, so the
    correction sorts before its target" - was wrong for every legal pending
    row. A new public name in front of the same function would leave that trap
    for the next caller, so the function now declines the question and names
    the one that can answer it.

    Against the engine as it was, this failed: the call returned a refusal
    sentence instead of raising.
    """
    from vitai.jsonl import _corrections_that_would_not_apply

    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    with pytest.raises(ValueError) as caught:
        _corrections_that_would_not_apply(
            data, "daily", [_daily(kcal_in=COMPLETED, supersedes=REF)])
    said = str(caught.value)
    assert "recorded_at" in said
    assert "pending_problems" in said, said


# ------------------------------------------------- what a pending row IS, and
# the clock is not asked

def test_a_declared_correction_classifies_as_one_before_the_write(tmp_path):
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    answers = classify_pending(
        data, "daily", [_daily(kcal_in=COMPLETED, supersedes=REF)],
        device="phone")
    assert _verdicts(answers) == ["correction"]
    assert answers[0]["target"] == REF


def test_an_undeclared_restatement_says_so_rather_than_being_inferred(
        tmp_path):
    """#425's own confirming case, answered the way #425 was closed.

    The verdict is NOT `correction`. An undeclared restatement is a second
    claim to this engine, and the only fact that could make it a correction is
    a clock the caller may not author - so the engine says what the row is and
    names the field that would change it, rather than guessing at intent.
    """
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    answers = classify_pending(data, "daily", [_daily(kcal_in=COMPLETED)],
                               device="phone")
    assert _verdicts(answers) == ["restatement"]
    assert answers[0]["target"] is None
    assert "supersedes" in answers[0]["reason"]
    assert REF in answers[0]["reason"]


def test_a_row_the_record_has_never_seen_is_new(tmp_path):
    data = _repo(tmp_path)
    answers = classify_pending(data, "daily", [_daily(kcal_in=HELD)],
                               device="phone")
    assert _verdicts(answers) == ["new"]


def test_a_batch_restating_its_own_earlier_row_says_so(tmp_path):
    """The batch-blindness the corrections guard already had to fix once. A
    day carried twice in ONE import restates itself on the second row, and
    calling that `new` because the file did not hold it yet would answer about
    a state the write never produces."""
    data = _repo(tmp_path)
    answers = classify_pending(
        data, "daily",
        [_daily(kcal_in=HELD), _daily(kcal_in=COMPLETED)], device="phone")
    assert _verdicts(answers) == ["new", "restatement"]


def test_a_target_that_has_not_synced_is_unmatched_and_not_refused(tmp_path):
    """Offline-first stays legal. A correction naming a row that has not
    arrived is neither a correction nor a refusal; it applies when the target
    lands, and saying so is what stops a caller 'fixing' it."""
    data = _repo(tmp_path)
    answers = classify_pending(
        data, "daily", [_daily(kcal_in=COMPLETED, supersedes="2030-04-01/mfp-export")],
        device="phone")
    assert _verdicts(answers) == ["unmatched"]
    assert pending_problems(
        data, "daily",
        [_daily(kcal_in=COMPLETED, supersedes="2030-04-01/mfp-export")],
        device="phone") == []


def test_every_verdict_word_is_one_the_module_publishes(tmp_path):
    """A verdict a consumer cannot enumerate is a string it has to guess at."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    answers = classify_pending(
        data, "daily",
        [_daily(kcal_in=COMPLETED),
         _daily(kcal_in=COMPLETED, supersedes=REF),
         _daily(kcal_in=COMPLETED, supersedes="2030-04-01/mfp-export")],
        device="phone")
    assert len(answers) == 3
    assert set(_verdicts(answers)) <= set(PENDING_VERDICTS)
    assert [a["row"] for a in answers] == [1, 2, 3]


# ------------------------------------------------ THE CONTROL ON THE FIX, and
# the part #425's resume flagged as unverified

def _peer_holds_a_row_stamped_ahead(tmp_path):
    """A laptop writes the held day with a clock a day ahead of the phone's.

    Not exotic: it is the case the corrections guard was built for, and the
    one a modelled stamp could silence without anybody noticing. The laptop's
    own reading comes back too, because asking as the laptop means asking with
    the laptop's clock - `pending_problems` raises the same backwards-clock
    refusal the append does, and pretending the laptop reads the phone's wall
    time would be asking about a machine that does not exist.
    """
    data = _repo(tmp_path)
    ahead = datetime.now().astimezone() + timedelta(days=1)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="laptop",
                now=ahead)
    return data, ahead


def test_a_correction_a_peer_stamped_ahead_of_is_still_refused(tmp_path):
    """MODELLING THIS DEVICE'S STAMP MUST NOT SILENCE THE GUARD.

    High water comes from THIS device's file alone (#105), so the modelled
    stamp is allowed to be earlier than a peer's - because the real one will
    be. Taking high water from the merged record instead would stamp the
    modelled row past the peer's and report a correction as applicable that
    the write would refuse, which is the shape #391 rejected arriving from the
    other side.
    """
    data, _ = _peer_holds_a_row_stamped_ahead(tmp_path)
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]

    problems = pending_problems(data, "daily", pending, device="phone")
    assert problems, "the modelled stamp silenced the peer guard"
    assert "would retire nothing" in problems[0]

    assert _verdicts(classify_pending(data, "daily", pending,
                                      device="phone")) == ["refused"]


def test_the_refusal_is_the_same_sentence_the_append_raises(tmp_path):
    """ASK AND DO MUST AGREE, on the refusing side too. A pre-write answer
    that differs from the write is worse than no pre-write answer, because a
    caller acts on it."""
    data, _ = _peer_holds_a_row_stamped_ahead(tmp_path)
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]

    asked = pending_problems(data, "daily", pending, device="phone")
    with pytest.raises(DataError) as caught:
        append_many(data, "daily", pending, device="phone")
    # The stamps inside the sentence differ between the two calls - they are
    # two different writes - so the part that must match is everything up to
    # the stamp the write would carry.
    prefix = asked[0].split(" and this write is stamped ")[0]
    assert prefix in str(caught.value), (asked[0], str(caught.value))


def test_the_answer_survives_the_peer_syncing_it(tmp_path):
    """PEER-AFTER-SYNC, which is the case the resume named as the skipped one.

    Once the correction is legitimately written, its stamp is a fact on the
    row and every reader sorts by the same value. So the prediction made on
    the phone before the write is what the MERGED record - the view a peer
    gets after sync - then shows. Nothing here is view-dependent: the phone
    was refused while its clock was behind, is accepted once past, and the
    peer agrees with both.
    """
    data, _ = _peer_holds_a_row_stamped_ahead(tmp_path)
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]
    past = datetime.now().astimezone() + timedelta(days=2)

    # Same rows, same machine, a clock that has now passed the peer's stamp.
    assert pending_problems(data, "daily", pending, device="phone",
                            now=past) == []
    append_many(data, "daily", pending, device="phone", now=past)

    # `load` merges every device's stream, so this IS the post-sync view.
    assert [r["kcal_in"] for r in load(data, "daily")] == [COMPLETED]


def test_the_peer_that_wrote_the_row_can_still_correct_it(tmp_path):
    """THE OTHER HALF OF THE CONTROL, and the reason the refusal above is not
    view-dependence.

    The refusal says something true about THIS machine's clock, not about the
    record: "nothing appended from this machine can correct that row until its
    clock passes that stamp". The laptop that wrote the row is past it by
    construction, so it is answered yes - and the pre-write answer differs
    between the two machines because the stamps they would write differ, which
    is what a per-device file means (#105). A written row, by contrast, reads
    the same everywhere, which is what `test_the_answer_survives_the_peer_
    syncing_it` holds.
    """
    data, ahead = _peer_holds_a_row_stamped_ahead(tmp_path)
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]

    assert pending_problems(data, "daily", pending, device="laptop",
                            now=ahead + timedelta(minutes=1)) == []
    assert pending_problems(data, "daily", pending, device="phone")


# ------------------------------------------------------------ nothing written

def test_asking_writes_nothing(tmp_path):
    """A question that appends is not a question. Both surfaces stamp in
    memory and neither opens a file for writing."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    before = sorted((p.name, p.read_bytes()) for p in data.rglob("*.jsonl"))

    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]
    pending_problems(data, "daily", pending, device="phone")
    classify_pending(data, "daily", pending, device="phone")
    classify_pending(data, "daily", [_daily(kcal_in=COMPLETED)],
                     device="tablet")

    assert sorted((p.name, p.read_bytes())
                  for p in data.rglob("*.jsonl")) == before


# ---------------------------------------------------------- the public door

def test_the_engine_api_answers_the_same_question(tmp_path):
    """`Vitai` is where an importer actually stands, and an answer it cannot
    reach from there is half a fix. It knows its own root and device slug, so
    the caller supplies neither."""
    from vitai.api import Vitai, init

    v = Vitai(init(tmp_path / "content"))
    v.append_many("daily", [_daily(kcal_in=HELD)])

    assert _verdicts(v.classify_pending(
        "daily", [_daily(kcal_in=COMPLETED)])) == ["restatement"]
    assert _verdicts(v.classify_pending(
        "daily", [_daily(kcal_in=COMPLETED, supersedes=REF)])) == \
        ["correction"]


def test_the_engine_api_has_nothing_to_classify_for_an_event_dataset(tmp_path):
    """`emissions` has one door and it is not the generic append, so there is
    no append here to answer about. Refused for the same reason and in the
    same words as the write, rather than answered about a path that does not
    exist."""
    from vitai.api import Vitai, init

    v = Vitai(init(tmp_path / "content"))
    with pytest.raises(ValueError, match="assert_delivery"):
        v.classify_pending("emissions", [])
