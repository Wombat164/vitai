"""`independent_sources` counts sources, not rows (#211).

Two rows agreeing is only evidence when they are two MEASUREMENTS. When one
measurement reaches the record twice - the athlete reads a scale, tells the
coach, and types the same figure into an app whose export lands later - the
agreement is a number equalling itself, and counting it as corroboration
raises confidence on nothing.

The sharper version, and the one that was live: correcting a row appends a
second row from the same source, and the count went UP. Carefulness was
penalised with false confidence, silently, in the flattering direction.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai, init
from vitai.provenance import independent_witnesses
from vitai.schema import CURRENT_GENERATION, KEYS

_made = [0]


def w(**kw):
    rec = {k: None for k in KEYS["weight"]}
    rec.update({"date": "2030-08-03", "kg": 82.7, "source": "stated-in-chat",
                "_gen": CURRENT_GENERATION["weight"]})
    rec.update(kw)
    return rec


def counted(tmp_path: Path, rows: list[dict]) -> float:
    _made[0] += 1
    root = init(tmp_path / f"content{_made[0]}")
    (root / "data" / "weight.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    Vitai(root).build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        return con.execute(
            "SELECT independent_sources FROM provenance").fetchone()[0]
    finally:
        con.close()


# --- the two live shapes -----------------------------------------------------

def test_a_correction_does_not_inflate_the_evidence(tmp_path):
    """THE ONE THAT WAS LIVE. Two rows, one source, one measurement, and a
    correction the engine itself resolved - reported as two independent
    sources. Fixing a row made the record look better witnessed."""
    assert counted(tmp_path, [
        w(recorded_at="2030-08-03T06:05:18+00:00"),
        w(origin="device", recorded_at="2030-08-03T06:11:18+00:00")]) == 1


def test_one_channel_delivering_twice_is_one_witness(tmp_path):
    assert counted(tmp_path, [
        w(recorded_at="2030-08-03T06:05:18+00:00"),
        w(recorded_at="2030-08-03T06:11:18+00:00")]) == 1


def test_one_reading_arriving_by_two_routes_is_one_witness(tmp_path):
    """The issue's opening case: the athlete read a scale, told the coach, and
    typed the same figure into an app. Two source names, one instrument, one
    reading, one moment. Two copies of a transcription cannot catch a mis-read
    dial or a bad calibration, which is what a second witness is for."""
    assert counted(tmp_path, [
        w(origin="scale-a", recorded_at="2030-08-03T06:05:18+00:00"),
        w(source="mfp-export", origin="scale-a",
          recorded_at="2030-08-03T06:11:18+00:00")]) == 1


# --- and what must NOT be merged away ---------------------------------------

def test_two_instruments_are_still_two(tmp_path):
    assert counted(tmp_path, [
        w(origin="scale-a", recorded_at="2030-08-03T06:05:18+00:00"),
        w(source="watch", origin="watch-b",
          recorded_at="2030-08-03T06:11:18+00:00")]) == 2


def test_two_unannotated_channels_are_still_two(tmp_path):
    """With no origins stated, the channel is the only independence anyone can
    demonstrate. Collapsing these would rewrite a legitimately un-annotated
    history, which is the failure the old counting rule was guarding."""
    assert counted(tmp_path, [
        w(recorded_at="2030-08-03T06:05:18+00:00"),
        w(source="mfp-export", recorded_at="2030-08-03T06:11:18+00:00")]) == 2


def test_a_named_instrument_absorbs_its_own_unnamed_row():
    """The same source, once with an origin and once without, is one source
    either way - not one instrument plus one anonymous witness."""
    assert independent_witnesses([{"source": "chat", "origin": "scale-a"},
                                  {"source": "chat"}]) == 1
    # ... and a DIFFERENT channel with no origin is still its own witness.
    assert independent_witnesses([{"source": "chat", "origin": "scale-a"},
                                  {"source": "app"}]) == 2


# --- the part supersession already handles ----------------------------------

def test_a_superseded_row_never_reaches_the_count(tmp_path):
    """`retire` drops it at load, so a correction that APPLIED is already
    excluded and needs nothing here. A correction that did not apply, because
    its reference matched no line, leaves a live row - counting it is correct
    behaviour on incorrect data, and the defect is the silent non-application.
    """
    # Two DIFFERENT channels, so without supersession this would be two.
    assert counted(tmp_path, [
        w(source="scale", origin="scale-a",
          recorded_at="2030-08-03T06:05:18+00:00"),
        w(source="hand", origin="notepad",
          recorded_at="2030-08-03T06:11:18+00:00",
          supersedes="2030-08-03/scale")]) == 1


# --- a row that names nothing stands alone -----------------------------------

def test_two_silences_are_not_one_witness():
    """Dedupe by source was ordered; dedupe by ABSENCE of source was not.

    Reading a missing source as a channel called "unknown" merged rows on the
    strength of what they both failed to say, which is the collapse
    `shares_origin` refuses one function away - the engine does not get to
    assume two anonymous rows are the same reading.
    """
    assert independent_witnesses([{}, {}]) == 2
    assert independent_witnesses([{"origin": "scale-a"}, {}]) == 2
    # And a row whose source is literally the word "unknown" is a channel like
    # any other, not a synonym for silence.
    assert independent_witnesses([{"source": "unknown"}, {}]) == 2


# --- the count and the label are one rule ------------------------------------

def test_the_resolution_label_agrees_with_the_count(tmp_path):
    """`independent_sources` said one witness while the resolution row beside
    it called the same pair "independent observations". Two fields, one
    question, two answers, on rows whose whole job is to say how well
    evidenced a value is."""
    _made[0] += 1
    root = init(tmp_path / f"agree{_made[0]}")
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        w(kg=82.7, recorded_at="2030-08-03T06:05:18+00:00"),
        w(kg=88.0, recorded_at="2030-08-03T06:11:18+00:00")]) + "\n",
        encoding="utf-8")
    Vitai(root).build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        witnesses, independent, compares = con.execute(
            "SELECT witnesses, independent, compares FROM resolution "
            "WHERE field='kg'").fetchone()
        sources = con.execute(
            "SELECT independent_sources FROM provenance").fetchone()[0]
    finally:
        con.close()
    assert witnesses == sources == 1
    assert not independent and compares == "pipeline fidelity"


def test_same_witness_is_the_pairwise_form_of_the_count():
    from vitai.provenance import same_witness
    pairs = [({"source": "a", "origin": "x"}, {"source": "a", "origin": "x"}, True),
             ({"source": "a", "origin": "x"}, {"source": "b", "origin": "y"}, False),
             ({"source": "a", "origin": "x"}, {"source": "a"}, True),
             ({"source": "a", "origin": "x"}, {"source": "b"}, False),
             ({"source": "a"}, {"source": "a"}, True),
             ({}, {}, False)]
    for left, right, shared in pairs:
        assert same_witness(left, right) is shared, (left, right)
        # The count must say the same thing: one witness where they are
        # shared, two where they are not.
        assert independent_witnesses([left, right]) == (1 if shared else 2)
