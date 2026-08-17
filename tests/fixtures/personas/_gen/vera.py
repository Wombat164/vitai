"""Generator for the vera persona (seed 131).

Bilbao. 36, runs trails and road, and records every run twice without meaning
to: the watch on her wrist and the phone in her vest both log it.

THE AXIS SHE STRESSES IS TWO INSTRUMENTS MEASURING ONE QUANTITY. Every other
record in this corpus has one distance per run, so nothing in the fixtures ever
held two claims about the same metres and asked what their difference means.
Hers has a hundred-odd runs recorded by both, and the shape of the
disagreement is the whole point:

  THE TWO AGREE ON AVERAGE. The median difference across the overlap is small -
  neither device is systematically longer over a season of running.

  AND THEY DISAGREE PER RUN, ASYMMETRICALLY. Under tree cover on the trail the
  phone loses signal and reads SHORT by a lot; on the open road the two land
  within a few tens of metres. So the range runs much further one way than the
  other, and its midpoint is nowhere near its median.

That combination is why this persona exists rather than a simpler one where a
scale reads two kilos heavy. A pair with a clean constant offset can be summed
up by one number; this one cannot, and a design that collapsed bias and spread
into a single figure would report these two as "agreeing" and lose the finding
entirely.

WHAT THE RECORD DOES ABOUT IT: NOTHING, DELIBERATELY. She records both claims
and one `comparability` row saying what she measured. No reading is adjusted,
because measuring that two instruments disagree is not a licence to correct
either - and the row's `offset` status does not lift the seam refusal.

NOTHING HERE IS COPIED FROM ANYWHERE. Every date, route, origin name and
distance below is invented for this fixture.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 131
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

START = date(2030, 1, 5)
DEFAULT_END = date(2030, 6, 30)

# Her two routes, and the reason the disagreement has a shape. The river path is
# open; the forest loop runs under canopy for most of its length, which is where
# the phone loses fix and under-reads.
ROAD_KM = 8.4
TRAIL_KM = 12.6


def _offset(d: date) -> str:
    """UTC offset for northern Spain, approximated the way `common` does for
    Ireland: summer time from late March to late October, +01:00 otherwise.
    Exact to the day is not something a synthetic record needs."""
    return ("+02:00" if date(d.year, 3, 25) <= d <= date(d.year, 10, 25)
            else "+01:00")


_TOML = """# vera - Bilbao. Every run recorded twice, by two things that disagree.
[athlete]
timezone = "Europe/Madrid"

[targets]
phases = [[59.0, 57.5, 0.1]]

[tripwires]
steps_floor = 7000
sleep_floor_h = 6.5

[resolution]
# THE WATCH FIRST, and that is a preference rather than a finding. She trusts
# the thing strapped to her wrist over the thing in a vest pocket; the record
# says so here so the resolver has a rule, and says nothing about which is
# closer to the truth - which is what the `comparability` row is for.
source_order = ["watch", "phone", "scale", "athlete"]
"""


RUN_SEED = SEED + 1


def _runs(end: date) -> list[tuple[date, str, float, float]]:
    """Every run, with what each instrument said about it.

    ITS OWN RANDOM STREAM, AND THAT IS A CORRECTNESS REQUIREMENT RATHER THAN
    TIDINESS. Three passes read these runs - the sessions, the comparability
    row and the expectations - and the first version took a shared generator
    that the weight pass had already advanced, so the sessions were built from
    one set of runs and the row describing them from another. The figures
    disagreed by two centimetres and the row was quietly wrong about the
    record it was supposed to summarise. Seeding here makes every caller read
    the same runs whatever order they run in.

    THE DIFFERENCES ARE BUILT, NOT SPRINKLED, because the finding has to be a
    property of the route rather than of the random number generator. On the
    road the two land within about thirty metres of each other. On the trail
    the phone drops fix under the canopy and reads short by a few hundred
    metres to over a kilometre - one long tail, no matching tail the other
    way, which is the asymmetry `spread` cannot express.
    """
    rng = random.Random(RUN_SEED)
    out = []
    day = START
    while day <= end:
        # THREE ROAD RUNS TO ONE TRAIL RUN, and the ratio is what makes the
        # median near zero while the tail stays long. A record where half the
        # runs were under canopy would have a median sitting in the middle of
        # the disagreement, which describes neither the road runs nor the trail
        # ones - and would read as a clean constant offset that could be summed
        # up in a single number. The finding only exists when the typical run
        # agrees and the minority does not.
        if day.weekday() in (0, 2, 4):      # Mon/Wed/Fri: the river path
            watch = round(ROAD_KM + rng.uniform(-0.12, 0.12), 2)
            phone = round(watch + rng.uniform(-0.03, 0.03), 2)
            out.append((day, "river-path", watch, phone))
        elif day.weekday() == 6:            # Sunday: the forest loop
            watch = round(TRAIL_KM + rng.uniform(-0.2, 0.2), 2)
            phone = round(watch - rng.uniform(0.35, 1.25), 2)
            out.append((day, "forest-loop", watch, phone))
        day += timedelta(days=1)
    return out


def _sessions(stamp: common.Stamper, end: date) -> list[dict]:
    """Two rows per run, one per instrument, both claiming the same outing.

    They are two CLAIMS about one event, which is what makes the overlap
    measurable at all: canonicalisation resolves them to one session, and the
    raw claims are where the disagreement still lives.
    """
    rows = []
    for day, route, watch_km, phone_km in _runs(end):
        secs = int((watch_km if route == "river-path" else watch_km) * 322)
        for origin, km in (("watch", watch_km), ("phone", phone_km)):
            rows.append(common.record(
                "sessions", date=day.isoformat(), type="run",
                distance_km=km, duration_s=secs,
                start_time=f"{day.isoformat()}T07:15:00{_offset(day)}",
                route=route, setting="outdoor",
                source=origin, origin=origin, capture="ble", read_by=None,
                recorded_at=stamp.stamp(day)))
    return rows


def _weight(rng: random.Random, stamp: common.Stamper,
            end: date) -> list[dict]:
    """Ordinary on purpose: the interest in this record is entirely in the two
    distance claims, and the weight series is here so the rollup renders."""
    rows = []
    kg = 59.2
    for day in common.daterange(START, end):
        if day.weekday() != 0:
            continue
        kg = round(kg - rng.uniform(0.0, 0.05), 2)
        rows.append(common.record(
            "weight", date=day.isoformat(), kg=kg, source="scale",
            origin="scale", measured_at="07:00", capture="manual_entry",
            read_by="athlete", recorded_at=stamp.stamp(day)))
    return rows


def _instruments(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "instruments", date=START.isoformat(), origin="watch",
            from_date=START.isoformat(), name="the running watch",
            source="athlete", recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=START.isoformat(), origin="phone",
            from_date=START.isoformat(), name="the phone in her vest",
            source="athlete",
            note="rides in a chest pocket; loses fix under the canopy",
            recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=START.isoformat(), origin="scale",
            from_date=START.isoformat(), name="the scale at home",
            source="athlete", recorded_at=stamp.stamp(START)),
    ]


def _comparability(stamp: common.Stamper, end: date) -> list[dict]:
    """THE FIRST `comparability` ROW ANY RECORD IN THIS CORPUS HAS WRITTEN.

    AUTHORED, NOT DERIVED, AND THAT IS THE POINT OF IT. `overlap_calibration`
    computes the same figures from her session claims, and if this row were
    written by calling that function the test comparing the two would be
    comparing a value with itself. She wrote down what she measured; the
    derivation measures it again; a test asserts they agree. Two paths to one
    number is a check, one path twice is a mirror.

    The numbers are computed here from the same runs the sessions are built
    from, by the plain arithmetic the row is supposed to state: the median of
    the differences, the full width they spanned, and the two ends of that
    width.

    THE TWO ENDS ARE WHY THIS ROW EXISTS (contract 52). Her disagreement runs
    one way: the low tail is a few centimetres and the high tail is over a
    kilometre, so a reader halving the spread about the median would put an
    edge six hundred metres below anything either instrument ever recorded and
    cut off the twenty-odd canopy runs that are the whole finding. Until
    `difference_lo`/`difference_hi` existed that shape reached a reader only
    through the `note` below, which is a sentence in English beside data
    contradicting it.
    """
    runs = _runs(end)
    diffs = sorted(round(watch - phone, 6) for _d, _r, watch, phone in runs)
    mid = len(diffs) // 2
    centre = (diffs[mid] if len(diffs) % 2
              else round((diffs[mid - 1] + diffs[mid]) / 2, 6))
    last = runs[-1][0]
    return [common.record(
        "comparability", date=last.isoformat(), field="distance_km",
        # Sorted, the way the pair is identified everywhere else: asking
        # whether two instruments agree is one question regardless of order.
        origin_a="phone", origin_b="watch",
        status="offset", bias=centre,
        spread=round(diffs[-1] - diffs[0], 6),
        difference_lo=diffs[0], difference_hi=diffs[-1],
        basis="overlap",
        overlap_ref=(f"{len(runs)} run(s) both instruments recorded, "
                     f"{runs[0][0].isoformat()} to {last.isoformat()}"),
        note="the road runs agree to within tens of metres; the forest loop "
             "is where they part, and it parts one way only",
        source="athlete", recorded_at=stamp.stamp(last))]


def _expectations(end: date) -> list[dict]:
    runs = _runs(end)
    diffs = sorted(round(watch - phone, 6) for _d, _r, watch, phone in runs)
    return [
        {"id": "vera-E1", "kind": "behavior", "dataset": "sessions",
         "dates": [runs[0][0].isoformat(), runs[-1][0].isoformat()],
         "claim": "every run carries two distance claims, one per instrument",
         "truth": f"{len(runs)} runs recorded by both `watch` and `phone`",
         "expect": "`overlap_calibration` pairs them by date and measures the "
                   "difference. The canonical series holds one distance per "
                   "run, so the disagreement is only visible in the raw "
                   "claims - which is why the derivation reads those",
         "gap": "none"},
        {"id": "vera-E2", "kind": "behavior", "dataset": "comparability",
         "dates": [runs[-1][0].isoformat()],
         "claim": "the two agree on average and disagree per run",
         "truth": f"the median difference is {diffs[len(diffs) // 2]:g} km "
                  f"while the full width is "
                  f"{round(diffs[-1] - diffs[0], 2):g} km",
         "expect": "a `comparability` row of status `offset` carrying BOTH "
                   "figures. A design collapsing them into one number would "
                   "report this pair as agreeing and lose the finding, which "
                   "is that they agree on average and not on any given run",
         "gap": "none"},
        {"id": "vera-E3", "kind": "behavior", "dataset": "comparability",
         "dates": [runs[-1][0].isoformat()],
         "claim": "the range runs further one way than the other",
         "truth": "the phone under-reads badly under canopy and never "
                  "over-reads by nearly as much, so the low tail is long and "
                  "the high tail is short",
         "expect": "the asymmetry is RECORDED and not folded into `spread`. "
                   "`difference_lo` and `difference_hi` (contract 52) hold "
                   "the two observed ends, so the row keeps the shape the "
                   "derivation measured; a consumer reconstructing bias plus "
                   "or minus half the spread is wrong on both sides at once "
                   "and the row now says so in data rather than in a note",
         "gap": "the row can STATE the range and still earns no BAND: "
                "`offset` does not lift the seam, and observed extrema carry "
                "no coverage factor. Whether a client may ever render a band "
                "from a measured overlap is #402's remaining open question"},
        {"id": "vera-E4", "kind": "behavior", "dataset": "sessions",
         "dates": [runs[-1][0].isoformat()],
         "claim": "nothing in the record is corrected by the measurement",
         "truth": "both distance claims stand exactly as each instrument "
                  "reported them",
         "expect": "no reading is adjusted. An `offset` row records that a "
                   "difference was measured and never licenses applying it; "
                   "the seam refusal lifts only for `comparable`",
         "gap": "none"},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight = _weight(rng, common.Stamper(base_hour=7), end)
    sessions = _sessions(common.Stamper(base_hour=8), end)
    instruments = _instruments(common.Stamper(base_hour=20))
    comparability = _comparability(common.Stamper(base_hour=21), end)
    expectations = _expectations(end)

    return {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/instruments.jsonl": common.jsonl_text(
            common.sort_rows(instruments)),
        "data/comparability.jsonl": common.jsonl_text(
            common.sort_rows(comparability)),
        "expectations.jsonl": common.jsonl_text(expectations),
    }
