"""Deterministic route geometry from a GPS track (G40 tier 1, G85-for-algorithms).

Every number here is reproducible: the same track in gives the same numbers out,
and each one names the algorithm and the parameter that produced it. This module
exists because the alternative - improvising geometry in a throwaway script -
produced figures that were reported as fact and were wrong:

- a raw haversine sum over every fix OVERESTIMATES distance, because 3-10 m of
  GNSS jitter is counted as forward motion on every sample. It is worst at
  walking pace, where jitter is a large fraction of true per-sample
  displacement. A hand-rolled version reported 1.50 km against a watch odometer
  of 1.39 km and blamed the watch.
- a grid-cell overlap ratio is ORDER-BLIND: it scores an out-and-back identical
  to its reverse, and its threshold has no published basis.

**Dependency note (a decision, not an oversight).** The prior-art sweep
recommends movingpandas + traj-dist rather than hand-rolling. vitai is a
stdlib-only engine, and those pull geopandas/GDAL and a Cython build - a heavy
footprint for a personal record. The tradeoff taken here: implement the
published algorithms directly, cite each one, and test them against synthetic
tracks with known geometry so correctness is demonstrated rather than assumed.
If this module grows past that, take the dependency instead.

Algorithms and their sources:

- Ramer-Douglas-Peucker simplification (Douglas & Peucker 1973) - epsilon is a
  perpendicular-distance tolerance in metres, set near GNSS horizontal error.
- Sustained-climb threshold for elevation gain - Strava's published behaviour:
  ignore climbing not sustained past 10 m for GPS-only data, 2 m where a
  barometric altimeter is present. GPS vertical error is roughly +/-15 m, far
  worse than horizontal, so raw per-point deltas are never summed.
- Stop detection - CB-SMoT in spirit (Palma et al. 2008): a speed-and-duration
  rule rather than a bare speed threshold, so a slow shuffle is not a stop and
  a genuine pause is not missed.
- LCSS trajectory similarity (Vlachos, Kollios & Gunopulos 2002) - chosen over
  discrete Frechet because it takes an explicit spatial threshold and SKIPS
  non-matching points rather than being dragged by a single bad fix, which
  matters on consumer GPS. It is ordering-aware, which the grid heuristic was
  not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

# --- parameters, each with its source ----------------------------------------

MAX_PLAUSIBLE_MS = 12.0
"""Speed above which a fix is a GNSS artefact, not motion (m/s). ~43 km/h -
above any running or walking speed, below cycling, so it gates jitter spikes
without discarding real movement."""

MIN_STEP_M = 2.0
"""Displacement below which a fix is treated as standing still. Sits inside
typical 3-10 m GNSS error, so stationary noise stops accumulating distance."""

SIMPLIFY_EPSILON_M = 4.0
"""Ramer-Douglas-Peucker tolerance, in the middle of consumer GNSS horizontal
error. Distance is summed over the simplified vertices."""

ELEV_SMOOTH_WINDOW = 15
"""Points in the centred moving average applied to elevation before any gain is
counted. Without it, a threshold rule still accumulates phantom ascent from
+/-15 m GNSS vertical noise - flat coastline reported 81 m of climb. "Sustained"
has to be enforced on a smoothed series, not a raw one."""

CLIMB_THRESHOLD_GPS_M = 10.0
CLIMB_THRESHOLD_BARO_M = 2.0
"""Sustained climb required before it counts toward total ascent (Strava's
published thresholds)."""

STOP_MAX_SPEED_MS = 0.4
STOP_MIN_SECONDS = 45.0
"""A stop is movement below STOP_MAX_SPEED_MS sustained for at least
STOP_MIN_SECONDS. 0.4 m/s is well under a slow walk; 45 s excludes traffic
lights and crossings, which are not stops in any meaningful sense."""

LCSS_EPSILON_M = 18.0
"""Spatial tolerance for two points to be "the same place" when comparing
routes. Roughly 2-4x consumer GNSS error - enough headroom for jitter, tight
enough to tell adjacent streets apart."""

LCSS_WARP_WINDOW = 0.15
"""Fraction of track length by which matched indices may drift apart. Bounds
the alignment so a route is not matched to an unrelated section of itself."""

SAME_ROUTE_SIMILARITY = 0.80
"""Normalised LCSS at or above which two tracks are treated as the same route.
A starting value, to be tuned against known repeats - not a law."""

LOOP_CLOSE_M = 75.0
LOOP_CLOSE_FRACTION = 0.10
"""A track is CLOSED when its start and end are within LOOP_CLOSE_M, or within
LOOP_CLOSE_FRACTION of the distance travelled - whichever is larger. A fixed
threshold gets this wrong in both directions: 180 m apart is obviously a loop
on a 2.2 km lake circuit and obviously not one on a 400 m errand. Caught on a
real track that a fixed 75 m rule called point-to-point."""

RETRACE_SIMILARITY = 0.60
"""Similarity between the outbound half and the REVERSED return half above
which a track is an out-and-back. This is the ordering-aware replacement for
the grid-overlap heuristic, which could not tell a route from its reverse."""

EARTH_R_M = 6371008.8


@dataclass(frozen=True)
class Fix:
    """One GPS fix. `ele` and `t` may be absent; nothing here requires them."""
    lat: float
    lon: float
    ele: float | None = None
    t: datetime | None = None


@dataclass
class Stop:
    start: datetime | None
    seconds: float
    lat: float
    lon: float


@dataclass
class RouteStats:
    points_raw: int
    points_used: int
    distance_m: float
    distance_raw_m: float
    duration_s: float | None
    moving_s: float | None
    elevation_gain_m: float | None
    start: tuple[float, float]
    end: tuple[float, float]
    start_end_gap_m: float
    furthest_m: float
    furthest_at: tuple[float, float]
    bearing_deg: float | None
    shape: str
    retrace_similarity: float
    stops: list[Stop] = field(default_factory=list)
    params: dict = field(default_factory=dict)


# --- geometry ----------------------------------------------------------------

def haversine_m(a: Fix, b: Fix) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(h))


def bearing_deg(a: Fix, b: Fix) -> float:
    """Initial great-circle bearing a -> b, degrees clockwise from north."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dl = math.radians(b.lon - a.lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass(deg: float) -> str:
    return COMPASS[round(deg / 22.5) % 16]


def _perp_distance_m(p: Fix, a: Fix, b: Fix) -> float:
    """Perpendicular distance from p to segment a-b, in metres.

    Uses a local equirectangular projection: over the few hundred metres a
    simplification segment spans, the error is far below the tolerance being
    applied, and it avoids a projection dependency.
    """
    lat0 = math.radians((a.lat + b.lat) / 2)
    mx = EARTH_R_M * math.cos(lat0)

    def xy(f: Fix) -> tuple[float, float]:
        return (math.radians(f.lon) * mx, math.radians(f.lat) * EARTH_R_M)

    (px, py), (ax, ay), (bx, by) = xy(p), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points: list[Fix], epsilon_m: float = SIMPLIFY_EPSILON_M) -> list[Fix]:
    """Ramer-Douglas-Peucker (1973). Iterative, so a long track cannot blow the
    recursion limit."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        lo, hi = stack.pop()
        worst, worst_i = 0.0, -1
        for i in range(lo + 1, hi):
            d = _perp_distance_m(points[i], points[lo], points[hi])
            if d > worst:
                worst, worst_i = d, i
        if worst > epsilon_m and worst_i > 0:
            keep[worst_i] = True
            stack.append((lo, worst_i))
            stack.append((worst_i, hi))
    return [p for p, k in zip(points, keep) if k]


def clean(points: list[Fix]) -> list[Fix]:
    """Drop implausible jumps and sub-noise wobble, in that order.

    Returns at least the first fix. This runs BEFORE simplification: an outlier
    left in place would anchor a simplification segment and distort it.
    """
    if not points:
        return []
    out = [points[0]]
    for p in points[1:]:
        prev = out[-1]
        d = haversine_m(prev, p)
        if prev.t and p.t:
            dt = (p.t - prev.t).total_seconds()
            if dt > 0 and d / dt > MAX_PLAUSIBLE_MS:
                continue
        if d < MIN_STEP_M:
            continue
        out.append(p)
    return out


def path_length_m(points: list[Fix]) -> float:
    return sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))


def elevation_gain_m(points: list[Fix], barometric: bool = False) -> float | None:
    """Total ascent, counting only climbs sustained past the threshold.

    Raw per-point elevation deltas are never summed: GPS vertical error is
    roughly +/-15 m, so a naive sum reports enormous phantom ascent on flat
    ground. Returns None when the track carries no elevation at all.
    """
    eles = [p.ele for p in points if p.ele is not None]
    if len(eles) < 2:
        return None
    threshold = CLIMB_THRESHOLD_BARO_M if barometric else CLIMB_THRESHOLD_GPS_M
    w = max(1, min(ELEV_SMOOTH_WINDOW, len(eles) // 2 or 1))
    if w > 1:
        half = w // 2
        eles = [sum(eles[max(0, i - half):i + half + 1])
                / len(eles[max(0, i - half):i + half + 1])
                for i in range(len(eles))]
    gain = 0.0
    anchor = eles[0]
    for e in eles[1:]:
        if e > anchor + threshold:
            gain += e - anchor
            anchor = e
        elif e < anchor:
            anchor = e
    return gain


def find_stops(points: list[Fix]) -> list[Stop]:
    """CB-SMoT-style: slow AND sustained. Needs timestamps; returns [] without."""
    timed = [p for p in points if p.t is not None]
    if len(timed) < 3:
        return []
    stops: list[Stop] = []
    i = 0
    while i < len(timed) - 1:
        j = i
        while j < len(timed) - 1:
            dt = (timed[j + 1].t - timed[j].t).total_seconds()
            if dt <= 0:
                j += 1
                continue
            if haversine_m(timed[j], timed[j + 1]) / dt >= STOP_MAX_SPEED_MS:
                break
            j += 1
        if j > i:
            secs = (timed[j].t - timed[i].t).total_seconds()
            if secs >= STOP_MIN_SECONDS:
                seg = timed[i:j + 1]
                stops.append(Stop(
                    start=timed[i].t, seconds=secs,
                    lat=sum(p.lat for p in seg) / len(seg),
                    lon=sum(p.lon for p in seg) / len(seg)))
            i = j
        else:
            i += 1
    return stops


# --- similarity (ordering-aware) ---------------------------------------------

RESAMPLE_SPACING_M = 10.0
"""Uniform spacing applied before any similarity comparison. LCSS matches
point against point, so unevenly-sampled sequences score near zero even when
they trace the same ground - and Ramer-Douglas-Peucker output is deliberately
uneven. Resampling makes the comparison about geometry rather than sampling."""


def resample(points: list[Fix], spacing_m: float = RESAMPLE_SPACING_M) -> list[Fix]:
    """Points at uniform arc-length spacing along the path.

    Linear interpolation between fixes; over a 10 m step the great-circle
    correction is far below GNSS error.
    """
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    carry = 0.0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg = haversine_m(a, b)
        if seg <= 0:
            continue
        pos = spacing_m - carry
        while pos <= seg:
            f = pos / seg
            out.append(Fix(a.lat + (b.lat - a.lat) * f,
                           a.lon + (b.lon - a.lon) * f, None, None))
            pos += spacing_m
        carry = (carry + seg) % spacing_m
    if haversine_m(out[-1], points[-1]) > spacing_m / 2:
        out.append(points[-1])
    return out


def lcss_similarity(a: list[Fix], b: list[Fix],
                    epsilon_m: float = LCSS_EPSILON_M,
                    warp: float = LCSS_WARP_WINDOW) -> float:
    """Normalised LCSS (Vlachos et al. 2002), 0..1.

    Ordering-aware: a route and its reverse do NOT score as identical, which is
    the specific defect of set/grid-overlap comparison. Points further apart
    than epsilon simply fail to match rather than dragging the score, which is
    what makes it robust to a single bad fix.
    """
    if not a or not b:
        return 0.0
    n, m = len(a), len(b)
    band = max(1, int(warp * max(n, m)))
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        lo = max(1, i - band)
        hi = min(m, i + band)
        for j in range(lo, hi + 1):
            if haversine_m(a[i - 1], b[j - 1]) <= epsilon_m:
                cur[j] = prev[j - 1] + 1
            else:
                cur[j] = max(prev[j], cur[j - 1])
        prev = cur
    return prev[m] / min(n, m)


def same_route(a: list[Fix], b: list[Fix],
               threshold: float = SAME_ROUTE_SIMILARITY) -> tuple[bool, float]:
    """Is b the same physical route as a? Returns (verdict, similarity).

    Checked in both directions and the better taken, so a route walked the
    other way round still matches itself - while a route and its reverse remain
    distinguishable in `classify_shape`, which compares halves rather than
    wholes.
    """
    ra, rb = resample(a), resample(b)
    fwd = lcss_similarity(ra, rb)
    rev = lcss_similarity(ra, list(reversed(rb)))
    best = max(fwd, rev)
    return best >= threshold, best


def classify_shape(points: list[Fix]) -> tuple[str, float]:
    """loop | out-and-back | point-to-point, plus the retrace similarity.

    An out-and-back is detected by comparing the outbound half against the
    REVERSED return half - if the second half retraces the first, those two
    sequences align. This is the ordering-aware replacement for counting shared
    grid cells, which could not distinguish a route from its reverse and so
    could not distinguish these shapes at all.
    """
    if len(points) < 4:
        return "too-short", 0.0
    dense = resample(points)
    mid = len(dense) // 2
    out_half, back_half = dense[:mid], list(reversed(dense[mid:]))
    retrace = lcss_similarity(out_half, back_half)
    gap = haversine_m(points[0], points[-1])
    travelled = path_length_m(points)
    closed = gap <= max(LOOP_CLOSE_M, LOOP_CLOSE_FRACTION * travelled)
    if retrace >= RETRACE_SIMILARITY:
        return "out-and-back", retrace
    if closed:
        return "loop", retrace
    return "point-to-point", retrace


# --- the one entry point -----------------------------------------------------

def analyse(points: list[Fix], barometric: bool = False) -> RouteStats:
    """Everything tier-1 about a track, deterministically."""
    raw = list(points)
    cleaned = clean(raw)
    used = simplify(cleaned)
    if len(used) < 2:
        used = cleaned if len(cleaned) >= 2 else raw

    dist = path_length_m(used)
    timed = [p for p in raw if p.t is not None]
    duration = (timed[-1].t - timed[0].t).total_seconds() if len(timed) >= 2 else None
    stops = find_stops(cleaned)
    moving = (duration - sum(s.seconds for s in stops)) if duration is not None else None

    home = used[0]
    furthest = max(used, key=lambda p: haversine_m(home, p))
    shape, retrace = classify_shape(used)

    return RouteStats(
        points_raw=len(raw), points_used=len(used),
        distance_m=dist, distance_raw_m=path_length_m(raw),
        duration_s=duration, moving_s=moving,
        elevation_gain_m=elevation_gain_m(used, barometric),
        start=(home.lat, home.lon), end=(used[-1].lat, used[-1].lon),
        start_end_gap_m=haversine_m(used[0], used[-1]),
        furthest_m=haversine_m(home, furthest),
        furthest_at=(furthest.lat, furthest.lon),
        bearing_deg=bearing_deg(home, furthest) if haversine_m(home, furthest) > 1 else None,
        shape=shape, retrace_similarity=retrace, stops=stops,
        params={
            "max_plausible_ms": MAX_PLAUSIBLE_MS, "min_step_m": MIN_STEP_M,
            "simplify_epsilon_m": SIMPLIFY_EPSILON_M,
            "climb_threshold_m": CLIMB_THRESHOLD_BARO_M if barometric
            else CLIMB_THRESHOLD_GPS_M,
            "stop_max_speed_ms": STOP_MAX_SPEED_MS,
            "stop_min_seconds": STOP_MIN_SECONDS,
            "lcss_epsilon_m": LCSS_EPSILON_M,
            "retrace_similarity_threshold": RETRACE_SIMILARITY,
        },
    )


# --- GPX ingestion (stdlib only) ---------------------------------------------

_GPX_NS = {"g": "http://www.topografix.com/GPX/1/1",
           "g0": "http://www.topografix.com/GPX/1/0"}


def read_gpx(path) -> list[Fix]:
    """Track points from a GPX file. Tolerates GPX 1.0 and 1.1, and a missing
    time or elevation on any point."""
    import xml.etree.ElementTree as ET
    root = ET.parse(str(path)).getroot()
    pts = root.findall(".//g:trkpt", _GPX_NS) or root.findall(".//g0:trkpt", _GPX_NS)
    out: list[Fix] = []
    for e in pts:
        ele_el = e.find("g:ele", _GPX_NS)
        if ele_el is None:
            ele_el = e.find("g0:ele", _GPX_NS)
        t_el = e.find("g:time", _GPX_NS)
        if t_el is None:
            t_el = e.find("g0:time", _GPX_NS)
        t = None
        if t_el is not None and t_el.text:
            try:
                t = datetime.fromisoformat(t_el.text.strip().replace("Z", "+00:00"))
            except ValueError:
                t = None
        out.append(Fix(
            lat=float(e.get("lat")), lon=float(e.get("lon")),
            ele=float(ele_el.text) if ele_el is not None and ele_el.text else None,
            t=t))
    return out
