"""A correction that would retire nothing is refused, not accepted (#210).

The failure is silent in every recorded instance: the correction lands,
`retire` walks past it, both rows stay live, and the write reports success. The
direction of the harm is always the same - the value the correction was meant
to replace is what every reader sees afterwards - and a silent no-op is
indistinguishable from success at the point of writing and from a deliberate
value at the point of reading.

IT IS REACHABLE THROUGH THE APPEND PATH, not only through hand-written lines.
A row another writer stamped ahead of this machine's clock is a target that a
correction written now sorts BEFORE, and nothing said so. That matters far
beyond a typo: any record where one write is meant to undo an earlier one has
the same shape, and "it landed and did nothing" is the worst available outcome.

WHAT IS NOT REFUSED is as deliberate as what is. A reference matching no row at
all stays legal, because a record that syncs writer by writer legitimately
holds a correction whose target has not arrived yet, and refusing that would
make offline-first writing impossible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.jsonl import DataError
from vitai.db import CONTRACT_VERSION
from vitai.schema import CURRENT_GENERATION, KEYS

# Stamps in the real past, because `now_stamp` reads the machine clock: a
# fixture dated in the 2030s is stamped in the FUTURE relative to a write
# happening now, which is the very condition under test.
HELD = "2020-05-01"


def _row(**kw) -> dict:
    rec = {k: None for k in KEYS["weight"]}
    rec.update({"date": HELD, "kg": 80.0, "source": "scale",
                "_gen": CURRENT_GENERATION["weight"]})
    rec.update(kw)
    return rec


def _repo(tmp_path: Path, files: dict[str, list[dict]]) -> Vitai:
    root = init(tmp_path / "content")
    (root / "vitai.toml").write_text('[device]\nslug = "laptop"\n',
                                     encoding="utf-8")
    for name, rows in files.items():
        (root / "data" / name).write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return Vitai(root)


def _correct(v: Vitai) -> dict:
    return v.append("weight", {"date": HELD, "kg": 81.4, "source": "scale",
                               "supersedes": f"{HELD}/scale"})


def test_a_correction_of_a_row_stamped_ahead_of_this_writer_is_refused(tmp_path):
    """THE CASE THAT WAS SILENT. Another writer's row carries a stamp this
    machine's clock has not reached, so a correction written now sorts before
    it and `retire` never sees the reference."""
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(device="phone", recorded_at="2031-01-01T09:00:00+02:00")]})

    with pytest.raises(DataError) as raised:
        _correct(v)

    assert "would retire nothing" in str(raised.value)
    assert "2031-01-01" in str(raised.value), (
        "the refusal must name the stamp that beat it, or the writer cannot "
        "tell which row is in the way")


def test_the_refused_correction_did_not_land(tmp_path):
    """Refused BEFORE the write, not complained about after it. A row on disk
    that the engine has already objected to is the state this exists to
    prevent."""
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(device="phone", recorded_at="2031-01-01T09:00:00+02:00")]})
    with pytest.raises(DataError):
        _correct(v)

    assert [r["kg"] for r in Vitai(v.root).dataset("weight")] == [80.0]


def test_an_ordinary_correction_is_untouched(tmp_path):
    """The check must not cost a working correction. This is the case the
    whole mechanism exists for, and refusing it would be worse than the bug."""
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(device="phone", recorded_at="2020-05-01T09:00:00+02:00")]})

    _correct(v)

    assert [r["kg"] for r in Vitai(v.root).dataset("weight")] == [81.4]


def test_a_correction_of_an_unstamped_row_still_works(tmp_path):
    """The issue says an unstamped row is "un-supersedable by construction".
    It is not: an absent stamp sorts BEFORE a present one, so a correction
    written now sorts after it and applies. The stuck direction is the other
    one - an unstamped CORRECTION over a stamped target - which this path
    cannot produce, because it stamps every row it writes."""
    v = _repo(tmp_path, {"weight.jsonl": [_row()]})

    _correct(v)

    assert [r["kg"] for r in Vitai(v.root).dataset("weight")] == [81.4]


def test_a_correction_whose_target_has_not_synced_yet_is_allowed(tmp_path):
    """OFFLINE-FIRST SURVIVES. A reference matching no row is a different
    situation from one the ordering has defeated: it repairs itself when the
    target arrives, and refusing it would make writer-by-writer sync
    impossible.

    THE RECORD HAS ROWS, just not that one. An empty record was the first
    fixture here and it proved nothing: the check returns early when there is
    nothing held, so refusing every unmatched reference passed this test.
    Found by mutating the rule it exists for.
    """
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(date="2020-04-01", device="phone",
             recorded_at="2020-04-01T09:00:00+02:00")]})

    _correct(v)

    kept = sorted(r["kg"] for r in Vitai(v.root).dataset("weight"))
    assert kept == [80.0, 81.4], (
        "the correction lands and waits for its target, and the unrelated "
        "row is untouched")


def test_a_plain_append_is_not_checked(tmp_path):
    """Only a row carrying `supersedes` asks the question, so an ordinary
    write pays nothing for this."""
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(device="phone", recorded_at="2031-01-01T09:00:00+02:00")]})

    v.append("weight", {"date": "2020-05-02", "kg": 79.9, "source": "scale"})

    assert len(Vitai(v.root).dataset("weight")) == 2


def test_a_correction_that_did_nothing_now_fails_validate(tmp_path):
    """The half the append path cannot reach: rows already in a record.

    An advisory is a thing somebody has to notice, and not noticing is what
    made all three instances invisible. This is now a problem, so `validate`
    exits non-zero.
    """
    v = _repo(tmp_path, {"weight.jsonl": [
        _row(kg=8.04, recorded_at="2020-05-01T07:00:00+02:00"),
        _row(kg=80.4, supersedes=f"{HELD}/scale")]})

    report = v.validate()

    assert any("did NOT apply" in p for p in report["problems"])
    assert not [a for a in report["advisories"] if "did NOT apply" in a]


def test_the_record_still_builds(tmp_path):
    """G26, and the two halves go opposite ways on purpose: a record that
    cannot be built is one nobody can look at to find out what is wrong with
    it."""
    v = _repo(tmp_path, {"weight.jsonl": [
        _row(kg=8.04, recorded_at="2020-05-01T07:00:00+02:00"),
        _row(kg=80.4, supersedes=f"{HELD}/scale")]})

    assert v.build().exists()


def test_the_repair_is_the_one_the_message_names(tmp_path):
    """Refusing is only fair because the remedy exists and is stated: a
    reference retires earlier corrections naming it as well as its target, so
    appending the correction again clears the one that sorted too early."""
    v = _repo(tmp_path, {"weight.jsonl": [
        _row(kg=8.04, recorded_at="2020-05-01T07:00:00+02:00"),
        _row(kg=80.4, supersedes=f"{HELD}/scale")]})
    assert any("did NOT apply" in p for p in v.validate()["problems"])

    _correct(v)
    after = Vitai(v.root)

    assert [r["kg"] for r in after.dataset("weight")] == [81.4]
    assert not [p for p in after.validate()["problems"] if "did NOT apply" in p]


def test_the_refusal_message_says_what_a_caller_may_author(tmp_path):
    """The rule stopped contradicting itself. `recorded_at` is still
    machine-set; what changed is that the refusal now says which clock a
    caller DOES own, rather than leaving them to conclude the record has no
    way to express when a thing happened."""
    v = _repo(tmp_path, {})

    with pytest.raises(ValueError) as raised:
        v.append("weight", {"date": HELD, "kg": 80.0, "source": "scale",
                            "recorded_at": "2020-05-01T09:00:00+02:00"})

    message = str(raised.value)
    assert "machine-set" in message
    assert "VALID time" in message and "measured_at" in message


# --- the cases the first cut got wrong ---------------------------------------

def test_a_batch_that_corrects_its_own_earlier_row_is_checked(tmp_path):
    """A CORRECTION EMITTED BEFORE ITS TARGET, in one batch.

    The first cut built its key set from held rows alone, so a correction
    whose target arrives in the SAME append was skipped entirely - and a bulk
    import, which is how rows actually arrive, landed the exact dud this
    refuses and reported success.
    """
    from vitai.jsonl import append_many

    root = init(tmp_path / "content")
    (root / "vitai.toml").write_text('[device]\nslug = "laptop"\n',
                                     encoding="utf-8")

    with pytest.raises(DataError):
        append_many(root / "data", "weight", [
            {"date": HELD, "kg": 80.4, "source": "scale",
             "supersedes": f"{HELD}/scale"},
            {"date": HELD, "kg": 8.04, "source": "scale"}], device="laptop")


def test_the_same_batch_written_in_the_right_order_is_accepted(tmp_path):
    """And the check must not cost the batch that works. Target first, then
    the correction: it sorts later, retires the target, and applies."""
    from vitai.jsonl import append_many

    root = init(tmp_path / "content")
    (root / "vitai.toml").write_text('[device]\nslug = "laptop"\n',
                                     encoding="utf-8")
    append_many(root / "data", "weight", [
        {"date": HELD, "kg": 8.04, "source": "scale"},
        {"date": HELD, "kg": 80.4, "source": "scale",
         "supersedes": f"{HELD}/scale"}], device="laptop")

    assert [r["kg"] for r in Vitai(root).dataset("weight")] == [80.4]


def test_a_repair_that_clears_only_a_dead_correction_is_refused(tmp_path):
    """THE WORST OUTCOME AVAILABLE, and the first cut produced it.

    `retire` counts a reference as applied when it retires ANY row - including
    an earlier dead correction naming the same key. So re-appending a
    correction whose target is still stamped ahead cleared the DUD, satisfied
    the "did it apply" check, and left the wrong value winning with nothing
    reporting it. A loud wrong state became a quiet one, via the remedy the
    engine itself was recommending.

    The question is now whether the TARGET went, asked by difference.
    """
    v = _repo(tmp_path, {
        "weight.phone.jsonl": [_row(kg=8.04, device="phone",
                                    recorded_at="2031-01-01T09:00:00+02:00")],
        "weight.jsonl": [_row(kg=80.4, supersedes=f"{HELD}/scale")]})
    assert any("did NOT apply" in p for p in v.validate()["problems"])

    with pytest.raises(DataError):
        _correct(v)

    assert any("did NOT apply" in p for p in Vitai(v.root).validate()["problems"]), (
        "the record stays loudly wrong rather than quietly wrong")


def test_a_mid_sync_record_still_passes_validate(tmp_path):
    """The escalation had to be split, not applied wholesale.

    `corrections_that_did_not_apply` reported two causes with opposite
    remedies. Escalating both made an ordinary record part way through a sync
    exit non-zero, with advice - append it again - that is wrong for it:
    there is nothing to append, the fix is for the other writer's file to
    arrive.
    """
    v = _repo(tmp_path, {"weight.phone.jsonl": [
        _row(date="2020-04-01", device="phone",
             recorded_at="2020-04-01T09:00:00+02:00")]})
    _correct(v)

    report = Vitai(v.root).validate()

    assert not [p for p in report["problems"] if "did NOT apply" in p]
    assert any("names no line" in a for a in report["advisories"])


def test_an_event_dataset_is_refused_for_the_right_reason(tmp_path):
    """An event is never retired - a later row cannot make an earlier one not
    have been said - so a reference there is not defeated by ordering, it is
    meaningless. Explaining it as an ordering problem would send a writer to
    fix a clock over a row no clock can help."""
    from vitai.jsonl import append_many

    root = init(tmp_path / "content")
    said = {"date": HELD, "kind": "verdict", "statement": "a figure",
            "surface": "cli", "policy_asof": HELD, "contract": CONTRACT_VERSION}
    append_many(root / "data", "emissions", [said], device="laptop")

    with pytest.raises(DataError) as raised:
        append_many(root / "data", "emissions",
                    [dict(said, supersedes=f"{HELD}/")], device="laptop")

    assert "never retired" in str(raised.value)
    assert "sorts before" not in str(raised.value)
