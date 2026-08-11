"""A hill is not extra distance (#23).

A hilly 10 km costs what a longer flat one does. Comparing the two by distance
alone says the athlete was slower, which is a statement about the terrain
reported as a statement about them.

Minetti et al. 2002 published the cost of running as a function of gradient,
in J/kg/m. This converts each stretch to the flat distance of equal cost. The
PUBLISHED curve, not a vendor's tuned one: Strava's grade adjustment is
undocumented and optimised for competitive parity rather than metabolic cost,
so a number derived from it is one nobody can check against a source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vitai import route
from vitai.route import Fix, grade_adjusted_distance_m, grade_cost

TRACKS = Path(__file__).resolve().parents[1] / "examples" / "demo" / "tracks"

FLAT_COST = 3.6


def ramp(slope: float, metres: int = 1000, spacing: int = 5) -> list[Fix]:
    """A dead-straight track at a constant gradient.

    9.0e-6 degrees of latitude is about a metre, so `i` is the metre.
    Synthetic on purpose: a real track cannot tell you what the answer should
    be, and every defect in this module was found by a case that could.
    """
    return [Fix(lat=50.0 + i * 9.0e-6, lon=4.0, ele=100.0 + i * slope)
            for i in range(0, metres + 1, spacing)]


# --- the curve ----------------------------------------------------------------

def test_the_flat_cost_is_the_published_constant():
    assert grade_cost(0.0) == FLAT_COST


def test_the_cheapest_gradient_is_downhill_not_flat():
    """The shape that makes the curve worth using. Minetti's minimum sits
    around a 20% descent - running downhill costs LESS than running on the
    flat, which no linear adjustment can express."""
    costs = {g / 100: grade_cost(g / 100) for g in range(-45, 46)}
    cheapest = min(costs, key=lambda g: costs[g])
    assert -0.25 <= cheapest <= -0.15, cheapest
    assert costs[cheapest] < grade_cost(0.0)


def test_climbing_costs_more_than_the_same_descent_saves():
    """The asymmetry, and the reason symmetric elevation noise inflates an
    adjusted distance rather than cancelling out of it."""
    for g in (0.05, 0.10, 0.20):
        up = grade_cost(g) - FLAT_COST
        down = FLAT_COST - grade_cost(-g)
        assert up > down, g


def test_a_gradient_beyond_the_study_is_refused_not_clamped():
    """Outside the measured range the polynomial is an extrapolation and turns
    sharply - far enough down it goes negative, which would say running off a
    cliff releases energy. Clamping would quietly report a 60% slope as a 45%
    one."""
    assert grade_cost(0.46) is None
    assert grade_cost(-0.46) is None
    assert grade_cost(0.45) is not None
    assert grade_cost(-0.45) is not None


# --- the adjustment -----------------------------------------------------------

@pytest.mark.parametrize("slope", [0.0, 0.05, 0.10, -0.05, -0.10])
def test_a_steady_gradient_reproduces_the_curve(slope):
    """Against an answer that can be worked out by hand, which is what caught
    the defect this module shipped first: every step was measured from the
    segment's anchor rather than from the point before it, so `run`
    accumulated 5 + 10 + 15 instead of 5 + 5 + 5 and every gradient came out a
    fraction of itself. A steady 10% climb scored 1.29 against the curve's own
    1.66 and no real track would have shown it.

    The tolerance is for the elevation smoothing, which flattens the two ends
    of a ramp."""
    got = grade_adjusted_distance_m(ramp(slope))
    want = grade_cost(slope) / FLAT_COST
    assert got["multiplier"] == pytest.approx(want, rel=0.05), (slope, got)


def test_flat_ground_adjusts_to_itself():
    got = grade_adjusted_distance_m(ramp(0.0))
    assert got["multiplier"] == pytest.approx(1.0, abs=1e-9)
    assert got["adjusted_m"] == pytest.approx(got["measured_m"], rel=0.01)


def test_a_climb_is_longer_and_a_descent_is_shorter():
    up = grade_adjusted_distance_m(ramp(0.10))
    down = grade_adjusted_distance_m(ramp(-0.10))
    assert up["adjusted_m"] > up["measured_m"]
    assert down["adjusted_m"] < down["measured_m"]


def test_no_elevation_means_no_answer():
    """Absent stays absent. A track with no elevation is not a flat track."""
    flat_no_ele = [Fix(lat=50.0 + i * 9.0e-6, lon=4.0) for i in range(0, 201)]
    assert grade_adjusted_distance_m(flat_no_ele) is None
    assert grade_adjusted_distance_m([]) is None


def test_a_route_beyond_the_curve_reports_what_it_could_judge():
    """A 60% slope is steeper than the study measured. The first version
    extrapolated a route-level multiplier from whatever fraction stayed inside
    the curve - a confident 3.49x for a whole climb, computed from 5% of it.
    The adjusted figure is now the flat-equivalent of the part that could be
    judged, and the coverage says so."""
    got = grade_adjusted_distance_m(ramp(0.60))
    assert got["covered_pct"] < 10
    assert got["beyond_the_curve_m"] > 0
    assert got["adjusted_m"] < got["measured_m"]


def test_it_is_a_second_figure_and_not_a_correction():
    """The distance is what it was. A consumer reading `adjusted_m` as a
    better measurement of how far somebody went has been misled by the name,
    so the measured figure travels beside it."""
    got = grade_adjusted_distance_m(ramp(0.10))
    assert "measured_m" in got and "adjusted_m" in got
    assert got["basis"] == "minetti-2002"


# --- against real tracks ------------------------------------------------------

def test_the_demo_tracks_adjust_by_a_believable_amount():
    """Riverside and canal routes with no net rise. The adjustment should be a
    couple of percent - the residual of the cost curve's asymmetry over small
    undulations - and anything larger means noise is being read as terrain.

    This is the check that caught the first defect, though not its cause: a
    2.7 km canal loop with zero net rise came out at 4.06 km of flat
    equivalent, a 51% penalty. The cause was the step accumulation above, not
    the baseline - worth saying, because the first version of this comment
    blamed the baseline and was wrong about its own bug."""
    seen = 0
    for path in sorted(TRACKS.glob("*.gpx")):
        points = route.clean(route.read_track(path))
        got = grade_adjusted_distance_m(points)
        if got is None:
            continue
        seen += 1
        assert 1.0 <= got["multiplier"] < 1.10, (path.name, got["multiplier"])
        assert got["covered_pct"] > 95, (path.name, got["covered_pct"])
    assert seen >= 3


def test_a_gradient_floor_keeps_flat_ground_flat():
    """WHAT THE 25 m FLOOR IS FOR, and no committed track can show it: the demo
    tracks are synthetic and their elevation is smooth, so shortening the floor
    to a metre changes their answers by nothing at all.

    Consumer GNSS vertical error is roughly 5 m one sigma. Over a 5 m step
    that is a gradient of +/-100%; over 25 m it is +/-20%, and the cost curve
    is convex so the error does not cancel - it accumulates as phantom climb.
    Dead-flat ground costs 11.8% extra without the floor."""
    import random

    rng = random.Random(7)
    flat = [Fix(lat=50.0 + i * 9.0e-6, lon=4.0, ele=100.0 + rng.gauss(0, 5.0))
            for i in range(0, 2001, 5)]

    assert grade_adjusted_distance_m(flat)["multiplier"] < 1.05

    original = route.MIN_GRADE_RUN_M
    try:
        route.MIN_GRADE_RUN_M = 5.0
        assert grade_adjusted_distance_m(flat)["multiplier"] > 1.10
    finally:
        route.MIN_GRADE_RUN_M = original


def test_the_baseline_is_the_derived_distance_not_the_jitter_sum():
    """A track that wanders horizontally has a haversine sum far longer than
    the route: that is the overestimate #23 opens with. The adjusted figure
    has to rest on the simplified length like every other distance here, and
    the demo tracks cannot show it because they carry almost no jitter."""
    import random

    rng = random.Random(11)
    jittery = [Fix(lat=50.0 + i * 9.0e-6 + rng.gauss(0, 4.0e-5),
                   lon=4.0 + rng.gauss(0, 4.0e-5), ele=100.0)
               for i in range(0, 2001, 5)]
    raw = route.path_length_m(jittery)
    got = grade_adjusted_distance_m(jittery)
    # 13% on this track, which is the size of the effect rather than a bound I
    # picked: simplification removes the jitter that survives inside its own
    # 4 m tolerance and no more.
    assert raw > 1.05 * got["measured_m"], (raw, got["measured_m"])
    assert got["measured_m"] == pytest.approx(
        route.path_length_m(route.simplify(jittery)), rel=1e-9)


def test_a_net_flat_loop_is_not_adjusted_away():
    """It ends where it started, so the ups and downs cancel in elevation and
    do NOT cancel in cost. A multiplier of exactly 1.0 would mean the
    asymmetry had been lost somewhere."""
    points = route.clean(route.read_track(
        TRACKS / "canal-loop-2030-06-16.gpx"))
    got = grade_adjusted_distance_m(points)
    assert got["multiplier"] > 1.0


def test_it_rides_on_the_analysis_every_caller_already_gets():
    stats = route.analyse(route.read_track(TRACKS / "river-ten-2030-06-02.gpx"))
    assert stats.grade_adjusted is not None
    assert stats.grade_adjusted["measured_m"] > 0


def test_a_track_without_elevation_leaves_the_field_absent():
    stats = route.analyse([Fix(lat=50.0 + i * 9.0e-6, lon=4.0)
                           for i in range(0, 201)])
    assert stats.grade_adjusted is None


# --- the smoothing is shared, so two readings cannot disagree ------------------

def test_one_smoothing_serves_both_readers():
    """`elevation_gain_m` and this both read the same profile. Two copies of a
    moving average would drift into disagreeing about the same hill."""
    import inspect

    source = inspect.getsource(route)
    assert source.count("def _smooth_elevation") == 1
    assert source.count("_smooth_elevation(") >= 3
