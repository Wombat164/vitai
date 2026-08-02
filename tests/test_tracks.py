"""The track foreign key, and the identity it gives a session (#43).

Synthetic data only (public repo), fictional athlete, 2030 dates.

Two things are being fixed and they are easy to conflate. The FIRST is that a
session had no field naming the track that recorded it, so the link lived in a
prose note and was recovered by regex. The SECOND fell out of it: a session had
no per-row identity either, so a correction could not say which of two runs on a
day it corrected - and retired both.
"""

import json

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.jsonl import line_key, load
from vitai.schema import KEYS, CURRENT_GENERATION, supersedes_problems, validate_record


def session(date="2030-05-01", type="run", distance_km=5.0, source="watch",
            gen=None, **kw):
    """A session row at the CURRENT generation unless told otherwise."""
    rec = {"date": date, "type": type, "distance_km": distance_km,
           "duration_s": 1800, "avg_hr": None, "max_hr": None, "cadence": None,
           "kcal": None, "location": None, "rpe": None, "note": None,
           "source": source, "start_time": None, "elevation_m": None,
           "setting": None, "route": None, "place": None, "with": None,
           "context": None, "planned": None, "weather": None,
           "recorded_at": None, "track": None, "activity_id": None,
           "activity_source": None, "origin": None, "path": None,
           "origin_evidence": None, "capture": None, "read_by": None,
           "modelled": None, "type_source": None,
           "artifact": None,
           "device": None,
           "_gen": gen or CURRENT_GENERATION["sessions"]}
    # Fill any key this helper does not name explicitly. A helper that
    # hardcodes the full key list has to be edited by every generation block
    # that ever appends a field, and a mechanical edit repeated across files
    # is one that eventually gets done wrong; this stays correct by
    # construction instead.
    for _k in KEYS["sessions"]:
        rec.setdefault(_k, None)
    rec.update(kw)
    return rec


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, name, rows):
    (root / "data" / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- the fields ----------------------------------------------------------------

def test_a_session_can_name_its_track_and_its_vendor_id():
    assert validate_record("sessions", session(
        track="tracks/2026/16044209432.tcx", activity_id="16044209432",
        activity_source="strava")) == []


def test_an_absolute_track_path_is_rejected():
    """It leaks a username and a machine layout into a record meant to be
    portable, and it breaks a rebuild anywhere else - a determinism
    violation, not merely untidy."""
    for bad in ("/home/someone/tracks/a.gpx", "~/tracks/a.gpx", "C:/tracks/a.gpx"):
        problems = validate_record("sessions", session(track=bad))
        assert any("repo-relative" in p for p in problems), bad


def test_a_track_path_may_not_escape_the_repo():
    assert any("inside the repo" in p for p in
               validate_record("sessions", session(track="../../etc/passwd")))


def test_an_activity_id_is_an_opaque_string():
    """Never coerced to a number: leading zeros and non-numeric ids both
    exist, and a platform's id is a token rather than a quantity."""
    assert validate_record("sessions", session(activity_id="0091420")) == []
    assert any("opaque string" in p for p in
               validate_record("sessions", session(activity_id=9914203377)))


def test_an_id_needs_to_say_who_assigned_it():
    """`activity_source` is not `source`: Strava re-exporting a Polar-recorded
    run assigns an id that is evidence of relaying, not of recording (#35)."""
    assert any("needs one" in p for p in
               validate_record("sessions", session(activity_source="strava")))


def test_a_legacy_session_line_still_validates():
    """G25, on the dataset that has now moved four times."""
    legacy = {"date": "2030-05-01", "type": "run", "distance_km": 5.0,
              "duration_s": 1800, "avg_hr": None, "max_hr": None,
              "cadence": None, "kcal": None, "location": None, "rpe": None,
              "note": None}
    assert validate_record("sessions", legacy) == []


# ---- the identity it gives a session -------------------------------------------

def test_two_runs_on_one_day_from_one_watch_share_a_correction_key():
    """The defect, stated as a test. Without an identity both rows answer to
    `<date>/<source>`, so a correction aimed at one names both."""
    a, b = session(distance_km=5.0, gen=2), session(distance_km=8.0, gen=2)
    assert line_key("sessions", a) == line_key("sessions", b)


def test_correcting_one_of_two_same_day_runs_used_to_retire_both(tmp_path):
    """And it is silent: two real activities become one, which is the harm
    #16 exists to prevent, arriving through the correction path."""
    root = repo(tmp_path)
    write(root, "sessions", [
        session(distance_km=5.0), session(distance_km=8.0),
        session(distance_km=8.5, supersedes="2030-05-01/watch"),
    ])
    survived = [r["distance_km"] for r in load(root / "data", "sessions")]
    assert survived == [8.5], "the 5 km run was deleted by a correction to the 8"


def test_an_activity_id_makes_the_correction_precise(tmp_path):
    root = repo(tmp_path)
    write(root, "sessions", [
        session(distance_km=5.0, activity_id="aaa"),
        session(distance_km=8.0, activity_id="bbb"),
        session(distance_km=8.5, activity_id="bbb",
                supersedes="bbb@2030-05-01"),
    ])
    survived = [r["distance_km"] for r in load(root / "data", "sessions")]
    assert survived == [5.0, 8.5], "only the run that was corrected changed"


def test_an_ambiguous_correction_is_reported():
    """Reported rather than resolved - the engine cannot know which was meant,
    and guessing would delete an activity."""
    rows = list(enumerate([session(distance_km=5.0), session(distance_km=8.0),
                           session(distance_km=8.5,
                                   supersedes="2030-05-01/watch")], 1))
    problems = supersedes_problems("sessions", rows)
    assert any("matches 2 lines" in p for p in problems)
    assert any("activity_id" in p for p in problems)


def test_a_correction_pointing_at_nothing_is_reported():
    rows = list(enumerate([session(distance_km=5.0, activity_id="aaa"),
                           session(distance_km=8.5, activity_id="aaa",
                                   supersedes="typo@2030-05-01")], 1))
    assert any("matches no line" in p
               for p in supersedes_problems("sessions", rows))


def test_a_clean_record_reports_no_supersedes_problems():
    rows = list(enumerate([session(distance_km=5.0, activity_id="aaa")], 1))
    assert supersedes_problems("sessions", rows) == []


# ---- resolving geometry from the record ----------------------------------------

def _repo_with_track(tmp_path, **kw):
    root = repo(tmp_path)
    (root / "tracks").mkdir()
    (root / "tracks" / "a.gpx").write_text(
        '<?xml version="1.0"?><gpx version="1.1" '
        'xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        + "".join(f'<trkpt lat="{51.0 + i * 0.0002:.4f}" lon="3.0">'
                  f"<ele>{10 + i}</ele></trkpt>" for i in range(60))
        + "</trkseg></trk></gpx>", encoding="utf-8")
    write(root, "sessions", [session(track="tracks/a.gpx",
                                     activity_id="9914203377", **kw)])
    return root


def test_a_session_resolves_its_own_track(tmp_path):
    """The point of the field: geometry rebuilds from the record rather than
    from whatever path someone typed."""
    root = _repo_with_track(tmp_path)
    by_id = Vitai(root).session_route("9914203377")
    by_date = Vitai(root).session_route("2030-05-01")
    assert by_id.distance_m == by_date.distance_m > 0


def test_an_unknown_reference_says_what_to_give_instead(tmp_path):
    root = _repo_with_track(tmp_path)
    with pytest.raises(KeyError, match="activity_id or a date"):
        Vitai(root).session_route("nope")


def test_a_broken_pointer_is_not_a_missing_session(tmp_path):
    """The session is the fact; the track is an attachment. The error says so
    rather than implying the activity did not happen."""
    root = repo(tmp_path)
    write(root, "sessions", [session(track="tracks/gone.gpx",
                                     activity_id="123")])
    with pytest.raises(FileNotFoundError, match="attachment"):
        Vitai(root).session_route("123")


def test_a_broken_pointer_is_an_advisory_not_a_build_failure(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, "sessions", [session(track="tracks/gone.gpx", activity_id="1")])
    main(["validate", "--root", str(root)])
    out = capsys.readouterr().out
    assert "ADVISORY" in out and "cannot be rebuilt" in out
    assert "all data lines valid" in out


def test_route_reaches_the_cli_by_session(tmp_path, capsys):
    root = _repo_with_track(tmp_path)
    capsys.readouterr()
    main(["route", "--root", str(root), "--session", "9914203377"])
    assert "km" in capsys.readouterr().out


def test_route_needs_something_to_analyse(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(SystemExit, match="--session"):
        main(["route", "--root", str(root)])


# ---- what the review pass caught -----------------------------------------------

def test_an_activity_id_survives_the_read_model_as_text(tmp_path):
    """SQLite REAL affinity converts "9914203377" to a float, destroying
    leading zeros and any id past 2^53 - silently, and in the one field whose
    whole job is to be an opaque token. Asserted through a real build."""
    import sqlite3
    from datetime import date as _date
    root = _repo_with_track(tmp_path, activity_source="strava")
    Vitai(root).build(today=_date(2030, 5, 2))
    con = sqlite3.connect(root / "derived" / "health.db")
    value, kind = con.execute(
        "SELECT activity_id, typeof(activity_id) FROM sessions "
        "WHERE activity_id IS NOT NULL").fetchone()
    assert (value, kind) == ("9914203377", "text")


def test_a_leading_zero_id_is_not_eaten(tmp_path):
    import sqlite3
    from datetime import date as _date
    root = repo(tmp_path)
    write(root, "sessions", [session(activity_id="0091420")])
    Vitai(root).build(today=_date(2030, 5, 2))
    con = sqlite3.connect(root / "derived" / "health.db")
    assert con.execute("SELECT activity_id FROM sessions").fetchone()[0] == "0091420"


def test_a_supersedes_chain_is_not_an_ambiguous_reference():
    """A <- B <- C sharing one reference is documented behaviour: the chain
    retires all of it. Flagging that would report the correction mechanism
    working as designed."""
    rows = list(enumerate([
        session(distance_km=5.0),
        session(distance_km=8.0, supersedes="2030-05-01/watch"),
        session(distance_km=8.5, supersedes="2030-05-01/watch"),
    ], 1))
    assert supersedes_problems("sessions", rows) == []


def test_a_unc_path_is_absolute_too():
    assert any("repo-relative" in p for p in validate_record(
        "sessions", session(track="\\\\server\\share\\a.gpx")))


def test_a_merge_takes_the_identity_triple_from_one_claim(tmp_path):
    """Per-field precedence is right for quantities and wrong for an identity:
    resolving id and assigner independently can pair one platform's id with
    another platform's name for who assigned it - a provenance neither source
    ever claimed (#35, made by the resolver rather than by a connector)."""
    root = repo(tmp_path)
    write(root, "sessions", [
        session(source="watch", distance_km=6.40, duration_s=4920,
                start_time="2030-05-01T14:05:00+02:00",
                activity_id="watch-1", activity_source="watch",
                track="tracks/a.gpx"),
        session(source="app", distance_km=6.38, duration_s=4906,
                start_time="2030-05-01T14:05:11+02:00",
                activity_id="app-9", activity_source="app", track=None),
    ])
    merged = Vitai(root).canonical("sessions")
    assert len(merged) == 1, "two platforms, one activity"
    row = merged[0]
    assert row["source"] == "app+watch"
    # Whichever claim owns the id must also own the assigner and the track.
    owner = "watch" if row["activity_id"] == "watch-1" else "app"
    assert row["activity_source"] == owner
    assert (row["track"] is not None) == (owner == "watch")
