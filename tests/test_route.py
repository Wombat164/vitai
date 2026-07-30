"""Route geometry over synthetic tracks with KNOWN answers.

Every test here exists because a hand-rolled version got it wrong, or could
have. Synthetic tracks are used deliberately: a real track has no ground truth
to test against, so correctness would be assumed rather than demonstrated.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from vitai.route import (
    EARTH_R_M, Fix, analyse, classify_shape, clean, elevation_gain_m,
    find_stops, haversine_m, lcss_similarity, path_length_m, same_route,
    simplify,
)

UTC = timezone.utc
LAT0, LON0 = 51.0, 3.0
# Derived from the module's own earth radius so fixture and code cannot drift
# apart - the first version hard-coded 111_320 and disagreed by ~1 m per km.
M_PER_DEG_LAT = 2 * math.pi * EARTH_R_M / 360.0


def _north(metres: float) -> float:
    return LAT0 + metres / M_PER_DEG_LAT


def line(n: int = 60, spacing_m: float = 10.0, start: datetime | None = None,
         dt_s: float = 5.0, ele: float | None = None) -> list[Fix]:
    """A straight track due north, n points spacing_m apart."""
    t0 = start or datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    return [Fix(_north(i * spacing_m), LON0, ele,
                t0 + timedelta(seconds=i * dt_s)) for i in range(n)]


def test_haversine_matches_a_known_distance():
    a, b = Fix(LAT0, LON0), Fix(_north(1000.0), LON0)
    assert abs(haversine_m(a, b) - 1000.0) < 1.0


def test_simplify_keeps_a_straight_line_as_two_points():
    """RDP on a straight line must collapse to its endpoints - and the length
    must survive, which is the whole reason simplification is safe to do
    before measuring."""
    pts = line(50, 10.0)
    simple = simplify(pts)
    assert len(simple) == 2
    assert abs(path_length_m(simple) - path_length_m(pts)) < 1.0


def test_clean_removes_stationary_jitter_that_would_inflate_distance():
    """THE distance bug. A stationary receiver wobbling by ~1 m per fix must
    not accumulate distance."""
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    jitter = [Fix(LAT0 + (i % 2) * 1e-5, LON0, None, t0 + timedelta(seconds=i * 5))
              for i in range(60)]
    raw = path_length_m(jitter)
    assert raw > 40.0, "fixture should look like real jitter"
    assert path_length_m(clean(jitter)) == 0.0


def test_clean_drops_a_teleport_outlier():
    pts = line(20, 10.0)
    pts.insert(10, Fix(LAT0 + 5.0, LON0, None, pts[10].t))
    assert any(haversine_m(pts[0], p) > 100_000 for p in pts)
    assert all(haversine_m(pts[0], p) < 100_000 for p in clean(pts))


def test_elevation_ignores_noise_below_the_sustained_climb_threshold():
    """Flat ground with +/-4 m of GPS vertical noise (an 8 m swing, under the
    10 m GPS threshold) must report no ascent."""
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    flat = [Fix(_north(i * 10.0), LON0, 10.0 + (4.0 if i % 2 else -4.0),
                t0 + timedelta(seconds=i * 5)) for i in range(40)]
    assert elevation_gain_m(flat) == 0.0


def test_elevation_ignores_large_gps_noise_on_flat_ground():
    """The real failure: +/-15 m GNSS vertical noise on flat coastline
    reported 81 m of ascent before smoothing was added."""
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    noisy = [Fix(_north(i * 10.0), LON0, 10.0 + (15.0 if i % 3 == 0 else -12.0),
                 t0 + timedelta(seconds=i * 5)) for i in range(200)]
    gain = elevation_gain_m(noisy)
    assert gain is not None and gain < 20.0


def test_elevation_counts_a_real_sustained_climb():
    """A genuine climb is detected and roughly right.

    Deliberately NOT asserting an exact figure: the moving average that kills
    phantom ascent also flattens the ends of a ramp, so a 117 m synthetic climb
    over 40 points reports ~93 m. That under-read is the price of not
    hallucinating 81 m of ascent on flat coastline, and it shrinks as a real
    climb gets longer relative to the smoothing window. Asserting a band
    records the trade; asserting a magic number would only record my guess.
    """
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    rise, n = 3.0, 40
    climb = [Fix(_north(i * 10.0), LON0, 10.0 + i * rise,
                 t0 + timedelta(seconds=i * 5)) for i in range(n)]
    true_gain = rise * (n - 1)
    gain = elevation_gain_m(climb)
    assert gain is not None
    assert 0.7 * true_gain <= gain <= true_gain


def test_a_pause_is_a_stop_but_a_crossing_is_not():
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    pts = [Fix(_north(i * 10.0), LON0, None, t0 + timedelta(seconds=i * 5))
           for i in range(20)]
    here = pts[-1]
    # 20 s halt - a traffic light, not a stop
    pts += [Fix(here.lat, LON0, None, here.t + timedelta(seconds=s))
            for s in (5, 10, 15, 20)]
    assert find_stops(pts) == []
    # 120 s halt - a real stop
    pts += [Fix(here.lat, LON0, None, here.t + timedelta(seconds=s))
            for s in range(25, 146, 5)]
    stops = find_stops(pts)
    assert len(stops) == 1 and stops[0].seconds >= 45


# --- the order-blindness bug -------------------------------------------------

def test_a_route_and_its_reverse_are_not_the_same_shape():
    """THE similarity bug. A grid-overlap heuristic scores an out-and-back and
    a one-way identically because it discards order. LCSS must not."""
    one_way = line(40, 20.0)
    out_and_back = one_way + list(reversed(one_way))
    assert classify_shape(one_way)[0] == "point-to-point"
    assert classify_shape(out_and_back)[0] == "out-and-back"


def test_a_closed_circuit_is_a_loop_not_an_out_and_back():
    """A square walked once returns to its start, but never retraces itself."""
    side_m, per_side = 200.0, 20
    step = side_m / per_side
    mx = M_PER_DEG_LAT * math.cos(math.radians(LAT0))
    pts: list[Fix] = []
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    def add(lat, lon):
        nonlocal k
        pts.append(Fix(lat, lon, None, t0 + timedelta(seconds=k * 5)))
        k += 1

    k = 0
    for i in range(per_side):                      # north
        add(_north(i * step), LON0)
    for i in range(per_side):                      # east
        add(_north(side_m), LON0 + i * step / mx)
    for i in range(per_side):                      # south
        add(_north(side_m - i * step), LON0 + side_m / mx)
    for i in range(per_side):                      # west
        add(LAT0, LON0 + (side_m - i * step) / mx)
    shape, _ = classify_shape(pts)
    assert shape == "loop"


def test_same_route_matches_a_noisy_repeat_of_itself():
    base = line(60, 15.0)
    noisy = [Fix(p.lat + 8.0 / M_PER_DEG_LAT, p.lon, p.ele, p.t) for p in base]
    verdict, sim = same_route(base, noisy)
    assert verdict and sim > 0.8


def test_same_route_rejects_a_different_route():
    a = line(60, 15.0)
    mx = M_PER_DEG_LAT * math.cos(math.radians(LAT0))
    b = [Fix(LAT0, LON0 + i * 15.0 / mx, None, p.t) for i, p in enumerate(a)]
    verdict, sim = same_route(a, b)
    assert not verdict and sim < 0.5


def test_lcss_is_symmetric_enough_and_bounded():
    a, b = line(30, 20.0), line(30, 20.0)
    assert lcss_similarity(a, b) == 1.0
    assert 0.0 <= lcss_similarity(a, list(reversed(b))) <= 1.0


# --- determinism, the whole point of this module ------------------------------

def test_the_same_track_analysed_twice_is_identical():
    pts = line(80, 12.0, ele=25.0)
    a, b = analyse(pts), analyse(pts)
    assert a == b


def test_analyse_reports_the_parameters_that_produced_it():
    """A number without its parameter cannot be reproduced or argued with."""
    stats = analyse(line(40, 10.0))
    for key in ("simplify_epsilon_m", "lcss_epsilon_m", "stop_min_seconds",
                "climb_threshold_m"):
        assert key in stats.params


def test_cleaned_distance_is_never_greater_than_raw():
    """Cleaning and simplification may only remove phantom length."""
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    wobbly = [Fix(_north(i * 10.0) + (3e-5 if i % 2 else -3e-5), LON0, None,
                  t0 + timedelta(seconds=i * 5)) for i in range(60)]
    stats = analyse(wobbly)
    assert stats.distance_m <= stats.distance_raw_m


def test_a_big_circuit_is_a_loop_even_when_it_ends_a_little_away():
    """A fixed 75 m rule called a 2.2 km lake circuit ending 180 m from its
    start a point-to-point. 180 m is 8% of the distance travelled - clearly
    closed. The threshold has to scale with the track."""
    import math as _m
    mx = M_PER_DEG_LAT * _m.cos(_m.radians(LAT0))
    t0 = datetime(2030, 6, 1, 9, 0, tzinfo=UTC)
    pts, k = [], 0
    R = 350.0                      # ~2.2 km circumference
    for deg in range(0, 355, 2):   # stop just short of closing
        rad = _m.radians(deg)
        pts.append(Fix(LAT0 + (R * _m.cos(rad)) / M_PER_DEG_LAT,
                       LON0 + (R * _m.sin(rad)) / mx, None,
                       t0 + timedelta(seconds=k * 5)))
        k += 1
    shape, retrace = classify_shape(pts)
    assert shape == "loop", f"got {shape}"
    assert retrace < 0.3, "a circuit does not retrace itself"
