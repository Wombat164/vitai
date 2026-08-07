"""The engine's half of FIT: a format it cannot read, and a field for what
only that format carries (#91).

`route.py` has `read_gpx` and `read_tcx` and no `read_fit`, so the engine
cannot read the format most watches produce NATIVELY - and the two channels
only FIT carries had nowhere to go even if it could.

WHAT IS HERE. The dispatcher stops handing a FIT file to the XML parser and
says what is actually wrong, and `sessions` gains `avg_power`, which is the
schema gap any FIT ingest hits first.

WHAT IS NOT, and it is the decoder itself. The issue's own acceptance is a
decoder checked against each file's own `session` summary across real files,
on the grounds that a binary decoder which is subtly wrong emits plausible
numbers rather than errors. Synthetic bytes written by the same person who
wrote the decoder share that person's misunderstanding, so passing them proves
very little. That check needs real recordings, which are an athlete's and do
not belong in a public repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.route import UNREAD_FORMATS, read_track
from vitai.schema import KEYS, sensitivity, validate_record

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


# --- a format it cannot read says so --------------------------------------

def test_a_fit_file_is_not_handed_to_the_xml_parser(tmp_path):
    """The dispatch was `.tcx` or else GPX, so a FIT file came back as
    `ParseError: not well-formed (invalid token): line 1, column 0` - true of
    the bytes and useless to the reader. The file is fine; the engine cannot
    read it."""
    path = tmp_path / "ride.fit"
    path.write_bytes(b"\x0e\x10\x43\x08" + b"\x00" * 40)

    with pytest.raises(ValueError) as raised:
        read_track(path)

    assert "no reader for it" in str(raised.value)
    assert "not malformed" in str(raised.value)


def test_the_refusal_says_what_converting_costs(tmp_path):
    """Telling somebody to convert to GPX without saying that the conversion
    drops cadence and power sends them to lose the thing they came for."""
    path = tmp_path / "ride.fit"
    path.write_bytes(b"\x0e\x10")

    with pytest.raises(ValueError) as raised:
        read_track(path)

    assert "cadence and power" in str(raised.value)


def test_it_refuses_by_name_rather_than_by_parse_failure(tmp_path):
    """A FIT file whose bytes happen to start like XML would otherwise parse
    part-way and produce fixes from a format nobody wrote a reader for."""
    path = tmp_path / "ride.fit"
    path.write_bytes(b"<gpx><trk><trkseg></trkseg></trk></gpx>")

    with pytest.raises(ValueError):
        read_track(path)


def test_the_formats_it_can_read_are_unaffected(tmp_path):
    """The refusal is a lookup on a named set, so nothing else changed
    route."""
    gpx = tmp_path / "walk.gpx"
    gpx.write_text(
        '<?xml version="1.0"?>\n'
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="51.9" lon="-8.5"><ele>10</ele>'
        '<time>2030-05-01T08:00:00Z</time></trkpt>'
        '<trkpt lat="51.91" lon="-8.5"><ele>12</ele>'
        '<time>2030-05-01T08:01:00Z</time></trkpt>'
        "</trkseg></trk></gpx>", encoding="utf-8")

    assert len(read_track(gpx)) == 2
    assert ".gpx" not in UNREAD_FORMATS and ".tcx" not in UNREAD_FORMATS


def test_the_unread_set_is_named_rather_than_implied():
    """A format added to it is refused identically without anybody
    remembering to also handle its bytes."""
    assert UNREAD_FORMATS == {".fit": "FIT"}


# --- a field for what only that format carries ----------------------------

def test_a_session_can_carry_average_power(tmp_path):
    v = Vitai(init(tmp_path / "content"))

    row = v.append("sessions", {"date": "2030-05-01", "type": "cycle",
                                "distance_km": 30.0, "source": "watch",
                                "avg_power": 210})

    assert row["avg_power"] == 210


def test_power_is_a_whole_number_of_watts(tmp_path):
    """A strain gauge reports watts. A fractional average is a figure the
    device did not produce."""
    row = {k: None for k in KEYS["sessions"]}
    row.update({"date": "2030-05-01", "type": "cycle", "distance_km": 30.0,
                "source": "watch", "_gen": 1, "avg_power": 210.5})

    assert validate_record("sessions", row)


def test_an_older_line_never_owed_it():
    """G25. The field arrives at a generation; a row written before it is not
    missing it."""
    from vitai.schema import key_generation

    old = {k: None for k in KEYS["sessions"] if k != "avg_power"}
    old.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "_gen": 1})

    assert validate_record("sessions", old) == []
    assert key_generation("sessions", "avg_power") > 1


def test_it_is_named_for_what_it_is():
    """A bare `power` is ambiguous between average, maximum and NORMALISED,
    and normalised is the figure cyclists quote - so half its readers would
    take it for one and half for the other. Pinned because the issue asks for
    the bare name and this deviates from it deliberately."""
    assert "avg_power" in KEYS["sessions"]
    assert "power" not in KEYS["sessions"]
    assert "max_power" not in KEYS["sessions"]


def test_a_client_can_read_it_back():
    """A field written and never read wastes the record's own evidence, which
    is the worse of the two failure modes the population register names."""
    from vitai.query import SESSION_METRICS

    assert "avg_power" in SESSION_METRICS


def test_it_is_classified_as_a_measurement():
    """#299's gate caught this field on its first outing - a field with no
    sensitivity class raises rather than defaulting, which is what stopped it
    reaching a consumer unclassified."""
    assert sensitivity("sessions", "avg_power") == "measurement"


def test_the_shipped_record_carries_it_on_the_rides_and_not_the_runs():
    """The honest shape: a strain gauge is on a bike, so a run row leaving it
    null is a run rather than a gap."""
    rides = [s for s in Vitai(DEMO).dataset("sessions") if s["type"] == "cycle"]
    runs = [s for s in Vitai(DEMO).dataset("sessions") if s["type"] == "run"]

    assert [r for r in rides if r.get("avg_power")]
    assert not [r for r in runs if r.get("avg_power")]
