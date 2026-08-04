"""The fastest 1k, 5k, 10k, half and full of every stored track (#247).

The question a runner asks first, and one no field could answer: `sessions`
holds a distance and a duration, so a 10.48 km run and a 9.74 km run are
comparable on neither, and a pace computed from both averages the warm-up in.
The answer lives inside the track or nowhere - so a client that wanted it had
to parse the GPX itself, at which point the number is the client's claim
rather than this engine's.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vitai.api import Vitai
from vitai.route import STANDARD_DISTANCES_M, best_efforts, read_track

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def rows(tmp_path):
    import shutil
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("derived"))
    Vitai(root, on="2030-06-30").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        return con.execute(
            "SELECT track, distance_m, seconds, basis, start, end "
            "FROM best_efforts ORDER BY track, distance_m").fetchall()
    finally:
        con.close()


def test_the_table_is_populated(tmp_path):
    assert len(rows(tmp_path)) > 5


def test_one_row_per_track_and_distance(tmp_path):
    """A track can hold several efforts, and hanging them off `sessions` would
    flatten that."""
    got = rows(tmp_path)
    assert len({(r[0], r[1]) for r in got}) == len(got)
    by_track = {}
    for track, distance, *_ in got:
        by_track.setdefault(track, []).append(distance)
    assert any(len(v) > 1 for v in by_track.values())


def test_a_track_shorter_than_a_window_yields_no_row(tmp_path):
    """The record declining to answer, which is not a zero."""
    got = rows(tmp_path)
    assert not any(r[2] == 0 for r in got)
    short = [r for r in got if r[0].endswith("canal-loop-2030-06-16.tcx")]
    assert [r[1] for r in short] == [1000.0]


def test_basis_survives_into_the_row(tmp_path):
    """The load-bearing column. `device` was measured against the watch's own
    cumulative distance, an observation; `derived` against the engine's
    haversine sum, which is not. A consumer that cannot tell them apart reads
    both as a time trial."""
    got = rows(tmp_path)
    assert {r[3] for r in got} == {"device", "derived"}


def test_every_row_carries_its_window(tmp_path):
    """Without start and end a time cannot be located in the track, so a
    consumer could not show where it happened or check it."""
    for _, _, _, _, start, end in rows(tmp_path):
        assert start and end and start < end


def test_the_distances_are_the_conventional_set():
    """A set rather than a parameter: storing all of them is cheap, and
    storing an arbitrary one on request is not a read model. The half and the
    full carry their exact metric distances, because a 21 km best is not a
    half."""
    assert STANDARD_DISTANCES_M == (1000.0, 5000.0, 10000.0, 21097.5, 42195.0)


def test_a_short_track_simply_yields_fewer():
    track = read_track(DEMO / "tracks" / "canal-loop-2030-06-16.tcx")
    got = best_efforts(track)
    assert [e.distance_m for e in got] == [1000.0]


def test_seconds_is_elapsed_and_not_called_moving_time(tmp_path):
    """A stop inside the window counts. Excluding it would be the engine
    deciding which pauses were real, and the column name is the place that
    promise is kept or broken."""
    import shutil
    root = tmp_path / "d2"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("derived"))
    Vitai(root, on="2030-06-30").build()
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(best_efforts)")]
    finally:
        con.close()
    assert "seconds" in cols and not any("moving" in c for c in cols)
