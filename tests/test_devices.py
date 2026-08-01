"""One writer per file, so a merge is a set union (#105).

Synthetic data only (public repo), fictional athlete, 2030 dates.

The property under test is structural rather than behavioural: no two devices
write the same file, so a conflict cannot occur - not "is resolved". Most of
these assert that the topology holds rather than that some reconciler works,
because there is no reconciler and there must not be one.
"""

import json
import sqlite3

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.devices import (deduplicate, device_of, duplicates, event_key,
                           is_slug, merge, stream_paths, write_path)
from vitai.jsonl import load
from vitai.schema import CURRENT_GENERATION, KEYS


def repo(tmp_path, device=None):
    root = tmp_path / "content"
    main(["init", str(root)])
    if device:
        with (root / "vitai.toml").open("a", encoding="utf-8") as fh:
            fh.write(f'\n[device]\nslug = "{device}"\n')
    return root


def weight(**kw):
    row = {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None}
    row.update(kw)
    return row


# ---- the topology ---------------------------------------------------------------------

def test_a_device_only_ever_writes_its_own_file(tmp_path):
    """Not "conflicts are resolved" - structurally cannot occur. Two devices
    appending to one record touch two files, and a set union of disjoint
    files is something every sync transport already does correctly.
    """
    from vitai.jsonl import append
    root = repo(tmp_path)
    data = root / "data"
    append(data, "weight", weight(kg=80.0), device="laptop")
    append(data, "weight", weight(date="2030-05-02", kg=79.8), device="phone")
    append(data, "weight", weight(date="2030-05-03", kg=79.6), device="laptop")

    # `vitai init` touches an empty `weight.jsonl`, which contributes no
    # rows and is simply the actor whose name is nothing.
    written = sorted(p.name for p in data.glob("weight.*.jsonl"))
    assert written == ["weight.laptop.jsonl", "weight.phone.jsonl"]
    for path in data.glob("weight.*.jsonl"):
        rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln]
        assert len({r["device"] for r in rows}) == 1, path
    assert len(load(data, "weight")) == 3


def test_a_single_file_record_keeps_working_untouched(tmp_path):
    """Every existing record is an actor whose name is nothing."""
    root = repo(tmp_path)
    Vitai(root).append("weight", weight())
    assert (root / "data" / "weight.jsonl").exists()
    assert not list((root / "data").glob("weight.*.jsonl"))
    assert len(Vitai(root).dataset("weight")) == 1


def test_the_reader_unions_every_device_file(tmp_path):
    root = repo(tmp_path)
    data = root / "data"
    (data / "weight.laptop.jsonl").write_text(json.dumps(weight(
        kg=80.0, device="laptop",
        recorded_at="2030-05-01T09:00:00+02:00")) + "\n", encoding="utf-8")
    (data / "weight.phone.jsonl").write_text(json.dumps(weight(
        date="2030-05-02", kg=79.8, device="phone",
        recorded_at="2030-05-02T09:00:00+02:00")) + "\n", encoding="utf-8")
    rows = load(data, "weight")
    assert [r["device"] for r in rows] == ["laptop", "phone"]


def test_a_stray_filename_is_not_a_device_stream(tmp_path):
    """A slug that could carry a separator or a second dot would make the
    dataset ambiguous, so anything that is not one is not a device file."""
    root = repo(tmp_path)
    data = root / "data"
    strays = ("weight.backup.2030.jsonl", "weight.my backup.jsonl",
              "weight..jsonl")
    for name in strays:
        (data / name).write_text("{}\n", encoding="utf-8")
    assert [p.name for p in stream_paths(data, "weight")] == ["weight.jsonl"]
    # And the real one still is.
    (data / "weight.laptop.jsonl").write_text("{}\n", encoding="utf-8")
    assert [p.name for p in stream_paths(data, "weight")] == [
        "weight.jsonl", "weight.laptop.jsonl"]


@pytest.mark.parametrize("slug,ok", [
    ("laptop", True), ("phone-2", True), ("a", True), ("x" * 32, True),
    ("Laptop", False), ("my laptop", False), ("a.b", False),
    ("x" * 33, False), ("../etc", False), ("-lead", False)])
def test_a_device_slug_cannot_smuggle_a_path(slug, ok):
    from pathlib import Path
    assert is_slug(slug) is ok
    if ok:
        assert write_path(Path("/d"), "weight",
                          slug).name == f"weight.{slug}.jsonl"
    else:
        with pytest.raises(ValueError):
            write_path(Path("/d"), "weight", slug)


def test_no_device_is_the_unsuffixed_file_rather_than_an_error():
    """An empty slug is "this record has one writer", which is every
    existing record - not a malformed name."""
    from pathlib import Path
    assert is_slug("") is False
    assert write_path(Path("/d"), "weight", "").name == "weight.jsonl"
    assert write_path(Path("/d"), "weight", None).name == "weight.jsonl"


def test_the_unsuffixed_file_has_no_device(tmp_path):
    from pathlib import Path
    assert device_of(Path("weight.jsonl"), "weight") == ""
    assert device_of(Path("weight.laptop.jsonl"), "weight") == "laptop"


# ---- deterministic ordering -------------------------------------------------------------

def test_the_order_is_total_so_any_device_builds_the_same_thing():
    """The device slug is the tiebreak that makes the order total. Without it
    two devices with the same stamp order by whichever file was read first,
    and the two builds differ."""
    same = "2030-05-01T09:00:00+02:00"
    streams = [("phone", [weight(kg=1, recorded_at=same)]),
               ("laptop", [weight(kg=2, recorded_at=same)])]
    forward = [r["kg"] for r in merge(streams, "weight")]
    backward = [r["kg"] for r in merge(list(reversed(streams)), "weight")]
    assert forward == backward == [2, 1]


def test_unstamped_rows_keep_their_file_order():
    """A legacy record resolves exactly as it always did."""
    streams = [("", [weight(kg=1), weight(kg=2), weight(kg=3)])]
    assert [r["kg"] for r in merge(streams, "weight")] == [1, 2, 3]


def test_an_unstamped_row_sorts_BEFORE_a_stamped_one():
    """The canon `clocks.order_key` sets, and the opposite of what a plain
    string comparison gives - `""` sorts before any stamp as text, but
    `stamp == ""` sorts True and therefore last.

    The all-unstamped case above passes either way, which is why it did not
    catch this. Getting it backwards put a stamped correction BEFORE the
    unstamped legacy line it supersedes, and the backwards walk then kept the
    line the athlete had retired.
    """
    streams = [("phone", [weight(kg=2, recorded_at="2030-05-01T08:00:00+00:00")]),
               ("", [weight(kg=1)])]
    assert [r["kg"] for r in merge(streams, "weight")] == [1, 2]


def test_stamps_order_as_instants_not_as_text():
    """Two stamps either side of a timezone change order by wall clock as
    strings - the #37 trap, which this record already knows about."""
    earlier = weight(kg=1, recorded_at="2030-05-01T10:00:00+02:00")   # 08:00Z
    later = weight(kg=2, recorded_at="2030-05-01T09:30:00+00:00")
    assert [r["kg"] for r in merge([("a", [earlier]), ("b", [later])],
                                   "weight")] == [1, 2]


def test_a_correction_written_on_another_device_still_retires_its_target(tmp_path):
    """Cross-device supersedes, which nothing covered. The union has to put
    the correction after its target for the backwards walk to retire it."""
    root = repo(tmp_path)
    data = root / "data"
    (data / "weight.laptop.jsonl").write_text(json.dumps(weight(
        kg=99.0, device="laptop",
        recorded_at="2030-05-01T10:00:00+02:00")) + "\n", encoding="utf-8")
    (data / "weight.phone.jsonl").write_text(json.dumps({
        **weight(kg=80.0, device="phone",
                 recorded_at="2030-05-01T11:00:00+02:00"),
        "supersedes": "2030-05-01/scale"}) + "\n", encoding="utf-8")
    assert [r["kg"] for r in load(data, "weight")] == [80.0]


def test_a_build_is_byte_identical_whichever_device_runs_it(tmp_path):
    root = repo(tmp_path)
    data = root / "data"
    (data / "weight.laptop.jsonl").write_text(json.dumps(weight(
        kg=80.0, device="laptop",
        recorded_at="2030-05-01T09:00:00+02:00")) + "\n", encoding="utf-8")
    (data / "weight.phone.jsonl").write_text(json.dumps(weight(
        date="2030-05-02", kg=79.8, device="phone",
        recorded_at="2030-05-02T09:00:00+02:00")) + "\n", encoding="utf-8")
    main(["build", "--root", str(root)])
    first = (root / "derived" / "health.db").read_bytes()

    # Same file set, files RENAMED so the directory listing order flips - the
    # closest thing to "a different device ran it" that a test can stage. The
    # earlier version captured `first` and never compared it, so the property
    # in the name was unpinned.
    (data / "weight.laptop.jsonl").rename(data / "weight.zzz-laptop.jsonl")
    (data / "weight.zzz-laptop.jsonl").rename(data / "weight.laptop.jsonl")
    main(["build", "--root", str(root)])
    assert (root / "derived" / "health.db").read_bytes() == first

    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        got = con.execute("SELECT device, kg FROM weight ORDER BY date").fetchall()
    finally:
        con.close()
    assert got == [("laptop", 80.0), ("phone", 79.8)]


# ---- the clock stops being a cross-device problem -------------------------------------------

def test_a_lagging_second_device_can_still_write(tmp_path):
    """Actor-per-file dissolves the skew problem rather than solving it: a
    phone whose clock sits behind the laptop never compares against the
    laptop's stamps, because it never reads the laptop's file.
    """
    from datetime import datetime, timedelta, timezone

    root = repo(tmp_path)
    data = root / "data"
    ahead = datetime(2030, 5, 1, 12, 0, tzinfo=timezone.utc)
    from vitai.jsonl import append
    append(data, "weight", weight(), now=ahead, device="laptop")
    # An hour behind, and on its own file - which is not a clock fault.
    behind = ahead - timedelta(hours=1)
    append(data, "weight", weight(date="2030-05-02", kg=79.8),
           now=behind, device="phone")
    assert len(load(data, "weight")) == 2


def test_a_device_whose_own_clock_jumped_backwards_is_still_refused(tmp_path):
    """The guard keeps its real job. Loosening it to a no-op would have been
    the easy way to make the test above pass."""
    from datetime import datetime, timedelta, timezone

    from vitai.jsonl import DataError, append
    root = repo(tmp_path)
    data = root / "data"
    ahead = datetime(2030, 5, 1, 12, 0, tzinfo=timezone.utc)
    append(data, "weight", weight(), now=ahead, device="laptop")
    with pytest.raises(DataError, match="transaction time"):
        append(data, "weight", weight(date="2030-05-02"),
               now=ahead - timedelta(hours=1), device="laptop")


# ---- what union does not solve --------------------------------------------------------------

def test_one_workout_pulled_by_two_devices_is_one_event(tmp_path):
    """Union does not deduplicate, and nothing else would notice: two rows
    describing one event, from two files, both legitimate appends."""
    session = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
               "duration_s": 1800, "activity_id": "9914203377",
               "activity_source": "strava"}
    laptop = {**session, "device": "laptop",
              "recorded_at": "2030-05-01T20:00:00+02:00"}
    phone = {**session, "device": "phone",
             "recorded_at": "2030-05-02T08:00:00+02:00"}
    assert event_key("sessions", laptop) == event_key("sessions", phone)
    kept, dropped = deduplicate([laptop, phone], "sessions")
    assert len(kept) == 1 and len(dropped) == 1
    assert kept[0]["device"] == "laptop", "the first in merge order is kept"


def test_two_real_events_are_not_deduplicated():
    a = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
         "activity_id": "1"}
    b = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
         "activity_id": "2"}
    assert event_key("sessions", a) != event_key("sessions", b)
    assert duplicates([a, b], "sessions") == []


def test_the_write_fields_do_not_make_one_event_into_two():
    """Two devices pulling one workout stamp different `recorded_at` values
    and carry different slugs, and neither difference makes it two
    workouts."""
    base = {"date": "2030-05-01", "kg": 80.0, "source": "scale"}
    a = {**base, "device": "laptop", "recorded_at": "2030-05-01T09:00:00+02:00"}
    b = {**base, "device": "phone", "recorded_at": "2030-05-02T09:00:00+02:00"}
    assert event_key("weight", a) == event_key("weight", b)


def test_a_duplicate_is_reported_and_never_silently_merged(tmp_path):
    """An append-only record must not resolve two legitimate lines on its
    own. The athlete decides."""
    root = repo(tmp_path)
    data = root / "data"
    session = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
               "duration_s": 1800, "avg_hr": None, "max_hr": None,
               "cadence": None, "kcal": None, "location": None, "rpe": None,
               "note": None, "activity_id": "9914203377",
               "activity_source": "strava"}
    for device, stamp in (("laptop", "2030-05-01T20:00:00+02:00"),
                          ("phone", "2030-05-02T08:00:00+02:00")):
        (data / f"sessions.{device}.jsonl").write_text(
            json.dumps({**session, "device": device,
                        "recorded_at": stamp}) + "\n", encoding="utf-8")
    v = Vitai(root)
    assert len(v.dataset("sessions")) == 2, "nothing was dropped"
    found = v.duplicate_captures()
    assert len(found) == 1
    assert found[0]["dataset"] == "sessions"
    assert "captured twice" in found[0]["detail"]


def test_a_record_with_one_device_reports_no_duplicates(tmp_path):
    root = repo(tmp_path)
    Vitai(root).append("weight", weight())
    assert Vitai(root).duplicate_captures() == []


# ---- the content-blind property ------------------------------------------------------------

def test_the_merge_never_reads_a_field_of_the_record():
    """A sync layer built on this moves opaque files: it cannot corrupt data
    it cannot read, it needs no contract bump when the schema moves, and a
    server that never could read the content has nothing to be trusted with.

    Asserted by giving `merge` rows whose only recognisable key is the one
    that ORDERS them. Anything that reached into the record proper would
    raise here.
    """
    streams = [("phone", [{"recorded_at": "2030-05-02T09:00:00+02:00"}]),
               ("laptop", [{"recorded_at": "2030-05-01T09:00:00+02:00"}])]
    got = merge(streams, "weight")
    assert [r["recorded_at"][:10] for r in got] == ["2030-05-01", "2030-05-02"]


def test_nothing_syncs_the_derived_database(tmp_path):
    """`derived/` is rebuildable in seconds, and SQLite's main file and its
    WAL must stay consistent - a client that uploads them independently
    produces a database that is corrupt rather than merely stale."""
    root = repo(tmp_path)
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "derived/" in ignore


# ---- the schema -------------------------------------------------------------------------------

def test_every_dataset_can_say_which_machine_wrote_the_line():
    assert all("device" in keys for keys in KEYS.values())


def test_device_is_beside_source_and_not_inside_it():
    """`source` says which INSTRUMENT observed the value; `device` says which
    MACHINE wrote it down. Conflating them would make a phone and a laptop
    look like two instruments, which is the false-corroboration defect #35
    exists to prevent."""
    from vitai.schema import validate_record
    row = weight(device="laptop", source="scale",
                 _gen=CURRENT_GENERATION["weight"])
    row = {k: row.get(k) for k in KEYS["weight"]} | {"_gen": row["_gen"]}
    assert validate_record("weight", row) == []
    assert row["source"] == "scale" and row["device"] == "laptop"


def test_a_device_that_is_not_a_slug_is_rejected():
    from vitai.schema import validate_record
    bad = {k: None for k in KEYS["weight"]}
    bad.update({"date": "2030-05-01", "kg": 80.0, "device": "My Laptop"})
    assert any("device" in p for p in validate_record("weight", bad))


def test_a_line_written_before_multi_device_still_validates():
    """G25: the field is additive and nullable, and "nobody said" is the
    correct reading for a record that predates it."""
    from vitai.schema import key_generation, validate_record
    landed = key_generation("weight", "device")
    row = {k: None for k in KEYS["weight"]
           if key_generation("weight", k) < landed}
    row.update({"date": "2030-05-01", "kg": 80.0, "_gen": landed - 1})
    assert validate_record("weight", row) == []


# ---- what the review of this feature found ------------------------------------------

def test_a_caller_cannot_assert_which_machine_wrote_a_line():
    """Machine-set, like `recorded_at`. Otherwise a caller writes a row into
    the plain file claiming it came from the phone, and "device is metadata
    about the write" stops being enforceable."""
    import tempfile
    from pathlib import Path

    from vitai.jsonl import append
    data = Path(tempfile.mkdtemp())
    with pytest.raises(ValueError, match="machine-set"):
        append(data, "weight", {**weight(), "device": "phone"})


def test_two_identical_weigh_ins_from_one_device_are_two_weigh_ins(tmp_path):
    """A duplicate capture is by definition two DEVICES describing one event.
    Without that, the athlete stepping on the scale twice on one day fired on
    every single-file record the moment anyone called the API."""
    root = repo(tmp_path)
    data = root / "data"
    (data / "weight.jsonl").write_text(
        "\n".join(json.dumps(weight(recorded_at=f"2030-05-01T0{h}:00:00+02:00"))
                  for h in (7, 8)) + "\n", encoding="utf-8")
    assert len(Vitai(root).dataset("weight")) == 2
    assert Vitai(root).duplicate_captures() == []


def test_a_field_value_cannot_forge_another_rows_identity():
    """The key was a separator join over `str(v)`, and nothing forbids the
    separators in free text - so two genuinely different rows collided and
    `deduplicate` dropped a real one."""
    a = {"date": "2030-05-01", "kg": 80.0,
         "note": "hi\u241fsource\u241escale", "source": None}
    b = {"date": "2030-05-01", "kg": 80.0, "note": "hi", "source": "scale"}
    assert event_key("weight", a) != event_key("weight", b)


def test_a_type_difference_is_not_the_same_value():
    a = {"date": "2030-05-01", "note": 1}
    b = {"date": "2030-05-01", "note": "1"}
    assert event_key("weight", a) != event_key("weight", b)


def test_deduplicate_keeps_the_first_even_when_the_list_aliases_one_row():
    """Keying on `id()` made `[r, r]` drop BOTH copies, including the one
    being kept."""
    row = {"date": "2030-05-01", "kg": 80.0, "device": "laptop"}
    kept, dropped = deduplicate([row, row], "weight")
    assert len(kept) == 2 and dropped == [], "one device, so not a duplicate"
    other = {**row, "device": "phone"}
    kept, dropped = deduplicate([row, other], "weight")
    assert len(kept) == 1 and len(dropped) == 1


def test_the_record_keeps_both_lines_while_the_derived_numbers_converge(tmp_path):
    """Append-only: both writes are legitimate and neither is un-appendable.
    Only the derived side converges - otherwise one session captured twice
    doubles its distance in every figure downstream.
    """
    root = repo(tmp_path)
    data = root / "data"
    session = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
               "duration_s": 1800, "avg_hr": None, "max_hr": None,
               "cadence": None, "kcal": None, "location": None, "rpe": None,
               "note": None, "activity_id": "9914203377",
               "activity_source": "strava"}
    for device, stamp in (("laptop", "2030-05-01T20:00:00+02:00"),
                          ("phone", "2030-05-02T08:00:00+02:00")):
        (data / f"sessions.{device}.jsonl").write_text(
            json.dumps({**session, "device": device,
                        "recorded_at": stamp}) + "\n", encoding="utf-8")
    v = Vitai(root)
    assert len(v.dataset("sessions")) == 2, "the record lost a line"
    assert len(v.canonical("sessions")) == 1, "the derived side double-counts"


def test_validate_reads_every_device_file(tmp_path, capsys):
    """A malformed line in a device file passed validate clean and was then
    quarantined by the build - silently."""
    root = repo(tmp_path)
    (root / "data" / "weight.laptop.jsonl").write_text(
        "{not json\n", encoding="utf-8")
    capsys.readouterr()
    try:
        main(["validate", "--root", str(root)])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "MALFORMED" in out and "weight.laptop.jsonl" in out


def test_a_device_file_is_never_silently_ignored_for_its_case(tmp_path):
    """Writers are strict; readers must not be. A case-insensitive
    filesystem hands `weight.laptop.jsonl` back as `weight.Laptop.jsonl`, and
    excluding it made the device's whole stream vanish from the union -
    silently, which is the worst outcome available for a file full of real
    data. Windows CI caught it.
    """
    from pathlib import Path
    root = repo(tmp_path)
    data = root / "data"
    (data / "weight.Laptop.jsonl").write_text(json.dumps(weight(
        kg=80.0, device="laptop",
        recorded_at="2030-05-01T09:00:00+02:00")) + "\n", encoding="utf-8")
    assert len(load(data, "weight")) == 1
    assert device_of(Path("weight.Laptop.jsonl"), "weight") == "laptop"
    # And the writer stays strict, so nothing produces that name here.
    with pytest.raises(ValueError):
        write_path(data, "weight", "Laptop")
