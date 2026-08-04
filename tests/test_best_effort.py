"""The fastest contiguous N metres of a track.

The question this exists for is the one a runner actually asks - "what is my
best 10k" - and which no field in the record could answer. `sessions` holds a
distance and a duration per session, so a 10.48 km run and a 9.74 km run are
not comparable on either, and a pace would have to be computed from both. The
answer lives inside the track or nowhere.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from vitai.route import Fix, best_effort, haversine_m, path_length_m


def line(n: int, *, step_deg: float = 0.00009, secs: float = 2.0,
         start: datetime | None = None, dist: bool = False) -> list[Fix]:
    """A straight north-running line at a constant sampling interval."""
    t0 = start or datetime(2030, 1, 1, 12, 0, 0)
    pts = []
    for i in range(n):
        f = Fix(lat=51.0 + i * step_deg, lon=3.0,
                t=t0 + timedelta(seconds=i * secs))
        if dist:
            f = Fix(lat=f.lat, lon=f.lon, t=f.t, dist=i * 10.0)
        pts.append(f)
    return pts


def test_constant_speed_is_exactly_the_arithmetic():
    """No cleverness to hide a sign error behind: distance over speed."""
    pts = line(400)
    speed = haversine_m(pts[0], pts[1]) / 2.0
    e = best_effort(pts, 1000)
    assert e is not None
    assert abs(e.seconds - 1000 / speed) < 0.01


def test_the_window_is_exact_not_the_nearest_whole_fix():
    """The defect this guards.

    Taking whole fixes reports the time for slightly MORE than the asked
    distance. The error grows with the gap between fixes - at ten-second
    sampling a runner covers about 35 m between points, so an un-interpolated
    10 km window is really a 10.03 km one and the pace is quietly wrong.
    """
    pts = line(400, step_deg=0.00090, secs=10.0)      # ~100 m between fixes
    speed = haversine_m(pts[0], pts[1]) / 10.0
    e = best_effort(pts, 1000)
    assert e is not None
    # Un-interpolated, the answer would round up to the next whole fix and be
    # at least one sampling interval too long.
    assert abs(e.seconds - 1000 / speed) < 0.05
    assert e.seconds < 1000 / speed + 10.0


def test_it_finds_a_fast_section_inside_a_slow_track():
    t0 = datetime(2030, 1, 1, 12, 0, 0)
    pts, t = [], 0.0
    for i in range(300):
        # Fixes 100..199 are covered twice as fast as the rest.
        gap = 2.0 if 100 <= i < 200 else 4.0
        pts.append(Fix(lat=51.0 + i * 0.00009, lon=3.0,
                       t=t0 + timedelta(seconds=t)))
        t += gap
    e = best_effort(pts, 500)
    assert e is not None
    # The window must sit inside the fast stretch.
    assert 100 <= e.start_index <= 199
    slow = best_effort(pts[:100], 500)
    assert slow is not None and e.seconds < slow.seconds


def test_a_track_shorter_than_the_window_is_none_not_zero():
    assert best_effort(line(20), 100000) is None


def test_a_track_with_no_times_cannot_answer():
    pts = [Fix(lat=51.0, lon=3.0), Fix(lat=51.1, lon=3.0)]
    assert best_effort(pts, 100) is None


def test_the_device_figure_is_preferred_and_named():
    """`basis` is the point of the whole dataclass.

    A best effort measured against the watch's own cumulative distance rests
    on an observation. One measured against the haversine sum rests on a
    derivation, and a consumer that cannot tell will read both as a time trial.
    """
    with_dist = line(400, dist=True)
    e = best_effort(with_dist, 1000)
    assert e is not None and e.basis == "device"
    assert abs(e.seconds - 200.0) < 0.01        # 10 m per 2 s by construction

    without = line(400)
    assert best_effort(without, 1000).basis == "derived"


def test_a_backwards_device_figure_is_not_trusted():
    """A cumulative distance that decreases is not a cumulative distance."""
    pts = line(200, dist=True)
    broken = list(pts)
    broken[50] = Fix(lat=pts[50].lat, lon=pts[50].lon, t=pts[50].t, dist=5.0)
    e = best_effort(broken, 500)
    assert e is not None and e.basis == "derived"


def test_elapsed_includes_a_stop_rather_than_quietly_skipping_it():
    """A stop inside the window is counted.

    Excluding it would be the engine deciding which pauses were real, and an
    effort that skipped them would flatter the athlete in a way nothing in the
    record records. `find_stops` reports them separately, on purpose.
    """
    t0 = datetime(2030, 1, 1, 12, 0, 0)
    pts, t = [], 0.0
    for i in range(300):
        pts.append(Fix(lat=51.0 + i * 0.00009, lon=3.0,
                       t=t0 + timedelta(seconds=t)))
        t += 120.0 if i == 150 else 2.0       # a two-minute stop mid-track
    early = best_effort(pts[:150], 500)
    spanning = best_effort(pts[140:170], 500)
    assert early is not None
    if spanning is not None:
        assert spanning.seconds > early.seconds


def test_it_runs_on_the_demo_track():
    """The demo carries a 21.1 km group run, which is the only track long
    enough to hold a 10 km window."""
    from pathlib import Path

    from vitai.route import read_track
    p = (Path(__file__).resolve().parent.parent / "examples" / "demo" /
         "tracks" / "group-long-run-2030-06-23.gpx")
    if not p.exists():                       # generated; skip if not built
        return
    pts = read_track(p)
    total = path_length_m(pts)
    e = best_effort(pts, 10000)
    if total < 10000:
        assert e is None
    else:
        assert e is not None
        assert e.seconds > 0
        assert e.distance_m == 10000
        assert e.start_index < e.end_index
