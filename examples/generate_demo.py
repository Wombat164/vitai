#!/usr/bin/env python3
"""Generate the synthetic demo content repo at examples/demo/.

Deterministic (seeded) so the committed data is reproducible and CI can prove
it - the demo is the plan's visibility substrate ("demo or it didn't happen").
A fictional athlete, ~12 weeks: a weight cut on an on-target rate, Tue/Thu runs
with an easy-HR story, weekend gym sessions, daily steps/sleep/rhr, two
inferences. Writes only current-schema (generation-1) fields.

Increment 1 adds the goal story the contribution model exists to show:
- a MONOTONIC steps goal, where every step counts;
- a GUARDED running goal, where volume beyond a 10% weekly ramp does not;
- one big unplanned long run near the end, which advances the steps goal,
  is refused by the running goal, and mints no milestone;
- a goal edit and a threshold change, so the record has an audit trail to
  reconstruct - including one loosening timed right after a missed week.

The three newest datasets are here for the same reason: each one holds a fact
the coarser datasets structurally could not.

- `sets` (#97/#99/#60) gives the weekend gym sessions their sets, including an
  attempted load that was not completed, a block nobody ever said was maximal,
  a bodyweight movement whose load is the athlete, and one stack number that
  looks comparable across two machines and is not.
- `meals` (#96) itemises one photographed plate, with the range carried on the
  part a photograph cannot settle and a zero-width one on the part a printed
  pack already did, plus an item nobody has priced yet.
- `journal` holds what the athlete SAID, including a claim the rest of the
  record contradicts.

- `weight` carries one DERIVED value (#170): the athlete's own average, kept
  in a notebook. A number they act on that nobody observed, declaring which
  weigh-ins it stands on and who did the arithmetic. It does not contest any
  other claim, so it changes no count here - what it shows is the shape of a
  declared lineage in a real record, and a value the engine can tell apart
  from an observation without being told twice.

`artifacts` is deliberately absent: the manifest is a pointer to a blob store,
so a demo of it means committing blobs and a store to put them in, and a
manifest with nothing behind it would demonstrate the opposite of the point.

    python examples/generate_demo.py          # (re)write examples/demo/
    python examples/generate_demo.py --check  # fail if committed data drifts

NO real person's data is ever in this repo.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from vitai.schema import CURRENT_GENERATION, KEYS

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"
END = date(2030, 6, 30)
DAYS = 84
# Day offsets of the travel week (the ISO week beginning 2030-05-27), which the
# athlete misses and then responds to by lowering the floor on 2030-06-06.
TRAVEL_WEEK = (49, 55)
# Day offset from which the athlete's lines carry generation-2 provenance and
# context fields. Before it they are founding-shape lines - deliberately, so
# the committed demo proves both shapes coexist in one file.
GEN2_FROM = 42

TOML = (
    "# Demo athlete thresholds (synthetic).\n"
    "[targets]\n"
    "phases = [[80.0, 76.0, 0.35], [76.0, 74.0, 0.25]]\n\n"
    "[tripwires]\n"
    "easy_hr_cap = 152\n"
    "rhr_baseline = 51\n"
    "steps_floor = 9000\n"
    "sleep_floor_h = 7.0\n"
    "pain_gate = 3\n\n"
    "# Which source wins which quantity when two of them describe one day.\n"
    "# The watch measures burn; the calorie app only models it. The app owns\n"
    "# intake, which the watch never sees at all.\n"
    "#\n"
    "# EVERY source that appears in the data is listed (#73). A term the\n"
    "# ladder has never heard of sorts LAST - below every configured source -\n"
    "# and nothing used to say so. `hand` is here for the sharpest reason:\n"
    "# it is the athlete writing a number down, and an unranked first-hand\n"
    "# reading losing to a relayed vendor figure is the ladder inverted at\n"
    "# exactly the point it exists for.\n"
    "[resolution]\n"
    # `notebook` sits LAST deliberately: it is the athlete's own arithmetic
    # over readings already in this ladder, so where it disagrees with them it
    # is the sum that is wrong, not the scale.
    'source_order = ["dexa", "tape", "scale", "hand", "watch", '
    '"gym-console", "vendor-api", "vendor-export", "app", "notebook"]\n\n'
    "[resolution.precedence]\n"
    'kcal_out = ["watch", "app"]\n'
    'kcal_in = ["app"]\n'
    'protein_g = ["app"]\n'
    'steps = ["watch", "app"]\n'
    '# A tape measure and a DEXA scan are both anchors; the scan wins.\n'
    'value = ["dexa", "tape"]\n'
)


def _jsonl(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def _build(target: Path) -> None:
    """Write the demo content repo into `target` (deterministic)."""
    rng = random.Random(42)
    (target / "data").mkdir(parents=True, exist_ok=True)
    (target / "vitai.toml").write_text(TOML, encoding="utf-8", newline="\n")

    start = END - timedelta(days=DAYS - 1)
    weight, daily, sessions = [], [], []
    long_runs = []
    kg = 80.2
    for i in range(DAYS):
        d = (start + timedelta(days=i)).isoformat()
        dow = (start + timedelta(days=i)).weekday()
        gen2 = i >= GEN2_FROM
        kg -= 0.05 * (0.7 + 0.6 * rng.random())            # ~0.24-0.45 kg/wk
        # No scale during the travel week - the weigh-ins are genuinely absent,
        # and context.jsonl says why. An engine that flagged that as a lapse
        # would be punishing the athlete for being away from their bathroom.
        weighed = rng.random() < 0.8 and not TRAVEL_WEEK[0] <= i <= TRAVEL_WEEK[1]
        if weighed:
            row_w = {"date": d, "kg": round(kg + rng.gauss(0, 0.25), 1),
                     "source": "scale", "note": None}
            if gen2:
                # Provenance chain (#35/#51): the scale observed it, the
                # vendor app and API carried it. `source` is only the
                # terminus - how it reached this record.
                row_w.update({"origin": "scale", "origin_evidence": None,
                              "path": "vendor-app>vendor-api"})
                # Observation time (#37). A settled morning routine until the
                # travel week, after which the athlete weighs whenever they
                # remember - which is the artifact the caveat exists for.
                # Body mass swings about a kilogram across a day, so a window
                # mixing 07:00 and 19:00 weigh-ins can manufacture or erase a
                # week of apparent progress. The routine falling apart after a
                # disruption is the ordinary way this happens.
                erratic = i > TRAVEL_WEEK[1] and rng.random() < 0.45
                hh = 19 if erratic else 7
                row_w.update({
                    # A gen-3 line carries every key introduced up to gen 3,
                    # null where unknown - the scale reports mass only.
                    "_gen": 4,
                    "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
                    "body_fat_lo": None, "body_fat_hi": None,
                    "measured_at": f"{hh:02d}:{rng.randrange(0, 40):02d}",
                    # Written the same evening the athlete logs the day.
                    "recorded_at": f"{d}T21:{i % 60:02d}:00+02:00",
                })
            weight.append(row_w)
        steps = int(rng.gauss(11500 if dow < 5 else 8300, 2100))
        if TRAVEL_WEEK[0] <= i <= TRAVEL_WEEK[1]:
            # A travel week: the steps floor is missed outright. This is the
            # week the athlete reacts to by lowering the floor a few days
            # later - the sequence the suspicious-edit flag exists to catch.
            steps = int(rng.gauss(5600, 900))
        row = {"date": d, "steps": max(2500, steps),
               "distance_km": round(max(2.5, steps) * 0.00075, 1),
               # A FIFTH of what this drew before. Five hours a day, in a
               # record that also shows 13 km of running a week: the two
               # magnitudes never belonged to the same person, and against a
               # 150-a-WEEK goal the engine correctly reported 1414 per cent,
               # which reads as a bug because it is one. The draw is unchanged
               # so the day-to-day shape survives; only the scale moves, and
               # the athlete lands at a plausible two to three times the
               # guideline the goal encodes.
               #
               # Divided AFTER the integer, which is what the committed data
               # was produced with: rounding the float instead moves six days
               # by one minute and the drift check fails on them.
               "active_min": round(int(max(60, rng.gauss(300, 70))) / 5),
               "kcal_out": int(rng.gauss(2850, 220)),
               # Intake is centred BELOW the declared targets (2150 kcal,
               # 145 g), not on them. Generating it at exactly the target made
               # the synthetic athlete permanently on plan, so the nutrition
               # rows were decorative: there was no shortfall to ask about, and
               # a demo that only shows the satisfied case teaches that
               # nutrition is logged and never spoken about. A typical day here
               # now falls a little short, and some days do not.
               "kcal_in": int(rng.gauss(2065, 260)),
               "protein_g": int(rng.gauss(128, 24)),
               "sleep_h": round(max(4.5, rng.gauss(7.3, 0.7)), 1),
               "rhr": int(rng.gauss(51, 2.2)),
               "alcohol": rng.random() < 0.12, "note": None}
        pain = rng.choice([0] * 10 + [1, 1, 2])
        # Roughly one day in nine the watch spent part of the day on the
        # charger. It is a fact about the LOG, not about the athlete, which is
        # exactly the distinction `coverage` carries.
        _charge_day = rng.random() < 0.11
        if gen2:
            # The athlete's tracker gained provenance mid-block. Both shapes
            # live in one file from here on, which is the point: the migration
            # is additive, and the old lines never had to be rewritten.
            row.update({"_gen": 2, "source": "watch", "pain": pain,
                        "pain_site": "hip" if pain else None,
                        # `hip` is a paired structure, so the side is required
                        # for the entry to be actionable: which hip.
                        "pain_side": "right" if pain else None,
                        "mood": max(1, min(10, int(rng.gauss(7, 1.5)))),
                        # WHAT THESE ARE OUT OF (#246). A bare 2 could be two
                        # out of ten or two out of four, and a client that
                        # renders "2/10" against an undeclared scale has
                        # invented the denominator. The personas deliberately
                        # keep theirs bare, because absent-means-unstated is
                        # the case a consumer has to handle and a fixture that
                        # only held the declared one would prove nothing
                        # about it.
                        "mood_scale": "nrs-0-10",
                        "pain_scale": "nrs-0-10" if pain is not None else None,
                        "feel": rng.choice(["fun", "neutral", "neutral", "chore"]),
                        # `coverage` is a claim about how completely the day was
                        # LOGGED, and this generator does not know that - it is
                        # inventing a day, not observing one. Stamping "full" on
                        # every row taught the field's first consumer that
                        # coverage is a constant, and `partial` never appeared in
                        # the demo at all, so the one distinction the field
                        # exists to draw was untestable against the fixture.
                        #
                        # A watch that is worn all day is a defensible "full". A
                        # day the athlete took it off to charge is `partial`, and
                        # the demo now contains both, because a fixture that only
                        # holds the easy case proves nothing (#186).
                        "coverage": "partial" if _charge_day else "full"})
        else:
            row["hip_pain"] = pain
        daily.append(row)
        # ONE WEEK WITH NO SESSIONS AT ALL (#274). Contract 28 emits a row for
        # every week in range including the ones holding nothing, and its own
        # note says a week of zeros means the record holds nothing for it,
        # never that the athlete did nothing. A demo that trains every single
        # week cannot show that row, so the first consumer to meet a gap meets
        # it in production.
        #
        # The days themselves stay: this is a week off training, not a week
        # the record forgot, and the two look identical in a fixture that
        # drops both. The distinction is the point.
        if _quiet_week(d):
            continue
        if dow in (1, 3):                                   # Tue/Thu runs
            hard = rng.random() < 0.3
            km = round(max(3.0, rng.gauss(6.5 if not hard else 5.0, 1.0)), 2)
            run = {"date": d, "type": "run", "distance_km": km,
                   "duration_s": int(km * rng.gauss(390, 25)),
                   "avg_hr": int(rng.gauss(166 if hard else 147, 5)),
                   "max_hr": None, "cadence": int(rng.gauss(168, 4)),
                   "kcal": int(km * 61), "rpe": 7 if hard else 4, "rpe_scale": "borg-cr10", "note": None}
            if gen2:
                run.update({"_gen": 2, "source": "watch",
                            "start_time": f"{d}T18:10:00+02:00",
                            "elevation_m": round(max(0.0, rng.gauss(35, 15)), 1),
                            "setting": "outdoor",
                            # Two routes, alternating by week. One route for
                            # every run made "which route" a question with one
                            # possible answer.
                            "route": ("canal-loop" if (i // 7) % 2 == 0
                                      else "hill-repeats"),
                            "place": "home", "with": None, "context": "solo",
                            "planned": "running",
                            "weather": rng.choice(["dry", "dry", "rain", "wind"])})
            else:
                run["location"] = None
            sessions.append(run)
        # A Sunday long run every other week, on the route the athlete calls
        # the ten-kilometre one. Its distance varies the way a real one does,
        # which is the point: asking for "the 10k" has to pick among several
        # runs that are near ten kilometres and none that is exactly ten.
        if gen2 and dow == 6 and (i // 7) % 2 == 1:
            long_km = round(rng.gauss(10.1, 0.45), 2)
            # NOT `start`: that name holds the block's first date in the
            # enclosing scope, and rebinding it to a clock time turned every
            # subsequent `start + timedelta(days=i)` into a TypeError.
            long_start = "09:20"
            long_run = {
                "date": d, "type": "run", "distance_km": long_km,
                "duration_s": int(long_km * rng.gauss(372, 18)),
                "avg_hr": int(rng.gauss(152, 4)), "max_hr": None,
                "cadence": int(rng.gauss(170, 3)), "kcal": int(long_km * 61),
                "rpe": 6, "rpe_scale": "borg-cr10", "note": None, "_gen": 2, "source": "watch",
                "start_time": f"{d}T{long_start}:00+02:00",
                "elevation_m": round(max(0.0, rng.gauss(22, 8)), 1),
                "setting": "outdoor", "route": "river-ten", "place": "home",
                "with": None, "context": "solo", "planned": "running",
                "weather": rng.choice(["dry", "dry", "wind", "rain"]),
                "track": f"tracks/river-ten-{d}.gpx",
            }
            sessions.append(long_run)
            long_runs.append((d, long_start, long_km, long_run["duration_s"]))
        if dow in (5, 6) and rng.random() < 0.8:            # weekend gym
            gym = {"date": d, "type": "strength",
                   "distance_km": None,
                   "duration_s": int(rng.gauss(3300, 400)),
                   "avg_hr": None, "max_hr": None, "cadence": None,
                   "kcal": None, "rpe": rng.choice([5, 6]), "rpe_scale": "borg-cr10", "note": None}
            if gen2:
                gym.update({"_gen": 2, "source": "watch",
                            "start_time": f"{d}T10:30:00+02:00",
                            "elevation_m": None, "setting": "indoor",
                            "route": None, "place": "home", "with": None,
                            "context": "solo", "planned": None, "weather": None})
            else:
                gym["location"] = None
            sessions.append(gym)
    inferences = [
        {"date": (END - timedelta(days=9)).isoformat(), "kind": "pattern",
         "statement": "Easy-run heart rate drifts over the cap in weeks where "
                      "average sleep is under 7h.",
         "confidence": 0.7, "model": "demo-model",
         "evidence": "sessions+daily, weeks of 2030-05-20 and 2030-06-03",
         "note": None},
        {"date": (END - timedelta(days=2)).isoformat(), "kind": "observation",
         "statement": "Weekend step counts run about 3k below weekdays; the "
                      "floor is carried by commute days.",
         "confidence": 0.85, "model": "demo-model",
         "evidence": "daily.steps by weekday, full range", "note": None},
    ]
    # The unplanned long run: a Saturday late in the block, after that week's
    # Tue/Thu runs have already spent the ramp budget. This is the event the
    # split verdict is built to explain.
    big_run_day = END - timedelta(days=7)
    sessions.append({"date": big_run_day.isoformat(), "type": "run",
                     "distance_km": 21.1,
                     "duration_s": int(21.1 * 402), "avg_hr": 158,
                     "max_hr": None, "cadence": 166, "kcal": int(21.1 * 61),
                     "location": None, "rpe": 8, "rpe_scale": "borg-cr10",
                     "note": "unplanned - joined a group long run",
                     "_gen": 2, "source": "watch",
                     "start_time": f"{big_run_day.isoformat()}T09:05:00+02:00",
                     "elevation_m": 41.0, "setting": "outdoor",
                     # NO ROUTE, but a track. The athlete joined a group and
                     # went somewhere they have no name for; the watch recorded
                     # it anyway. `route` is a name a PERSON gave a place,
                     # `track` is the data. A record where every track has a
                     # route conflates the two, and this row separates them.
                     "route": None, "place": "home", "with": "a group",
                     "context": "social", "planned": None, "weather": "dry",
                     "track": f"tracks/group-long-run-{big_run_day.isoformat()}.gpx"})
    # A richly-contextful day: a rainy Sunday walk with a partner on a route
    # the athlete has a name for. None of it is a number, and all of it is
    # what makes the day legible six months later.
    context_day = (END - timedelta(days=14)).isoformat()
    sessions.append({
        "date": context_day, "type": "walk", "distance_km": 6.4,
        "duration_s": 4920, "avg_hr": 104, "max_hr": None, "cadence": None,
        "kcal": 290, "rpe": 2, "rpe_scale": "borg-cr10", "note": None, "source": "watch",
        "start_time": f"{context_day}T14:05:00+02:00", "elevation_m": 18.0,
        "setting": "outdoor", "route": "canal-loop", "place": "home",
        "with": "partner", "context": "family", "planned": None,
        "weather": "rain", "_gen": 4, "recorded_at": None,
        "track": "tracks/canal-loop-2030-06-16.tcx",
        "activity_id": "9914203377", "activity_source": "watch"})
    # A stored track, linked from the session as DATA rather than recovered
    # by regex from a prose note (#43). Repo-relative, so the demo rebuilds
    # identically on any machine.
    tracks = target / "tracks"
    tracks.mkdir(exist_ok=True)
    # One stored track per long run. Not one per run: a named route with no
    # kept file is the ordinary case, and a demo where everything has a GPX
    # would misrepresent how records actually look.
    for _d, _start, _km, _dur in long_runs:
        (tracks / f"river-ten-{_d}.gpx").write_text(
            _route_gpx("river-ten", _d, _start, _km, _dur),
            encoding="utf-8", newline="\n")
    # The group run's track, filed under its own name because it has no route.
    (tracks / f"group-long-run-{big_run_day.isoformat()}.gpx").write_text(
        _route_gpx("river-ten", big_run_day.isoformat(), "09:05",
                   21.1, int(21.1 * 402)),
        encoding="utf-8", newline="\n")
    (tracks / "canal-loop-2030-06-16.gpx").write_text(
        _demo_gpx(context_day), encoding="utf-8", newline="\n")
    # The same walk as the watch recorded it, in TCX - which carries the
    # device's OWN distance (#48). That figure is an observation; the
    # haversine sum the engine derives from the coordinates is a derivation,
    # and the two disagreeing is information about the track rather than an
    # error to smooth away.
    (tracks / "canal-loop-2030-06-16.tcx").write_text(
        _demo_tcx(context_day), encoding="utf-8", newline="\n")

    # The SAME walk, as a second connector recorded it - with a NAIVE
    # start_time (#38). This is the shape a legacy connector writes, and until
    # the fix it took the whole build down the moment it met an offset-bearing
    # row. The two must resolve to one activity, and the record must say the
    # offset was assumed rather than quietly claiming two platforms agreed on
    # an instant.
    sessions.append({
        "date": context_day, "type": "walk", "distance_km": 6.38,
        "duration_s": 4906, "avg_hr": 103, "max_hr": None, "cadence": None,
        "kcal": 288, "rpe": 2, "rpe_scale": "borg-cr10", "note": None, "_gen": 2, "source": "app",
        "start_time": f"{context_day}T14:05:11", "elevation_m": None,
        "setting": "outdoor", "route": None, "place": None, "with": None,
        "context": None, "planned": None, "weather": None})
    for row in daily:
        if row["date"] == context_day:
            row.update({"mood": 9, "feel": "fun", "coverage": "full"})

    # THE PAIR THAT MATTERS (#51). Two weigh-ins on one day that look like
    # two sources agreeing, and are not: the export received its number FROM
    # the API, so the 20 g between them measures rounding in transit and says
    # nothing about whether the weight is right. The hand-written entry three
    # days later IS independent - and it is the one that disagrees by 400 g.
    # The useless comparison is the clean one; the informative comparison is
    # the noisy one, which is exactly backwards from how it reads.
    weighed_days = {row["date"]: row for row in weight}
    relay_day = next(d for d in sorted(weighed_days)
                     if d >= (END - timedelta(days=21)).isoformat())
    independent_day = next(d for d in sorted(weighed_days)
                           if d >= (END - timedelta(days=18)).isoformat()
                           and d != relay_day)
    for day in (relay_day, independent_day):
        weighed_days[day]["source"] = "vendor-api"
    weight.append({
        "date": relay_day,
        # 20 g apart: the export received this number FROM the API.
        "kg": round(weighed_days[relay_day]["kg"] + 0.02, 2),
        "source": "vendor-export", "note": None,
        "_gen": 4, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
        "body_fat_lo": None, "body_fat_hi": None, "measured_at": "07:12",
        "recorded_at": f"{relay_day}T21:30:00+02:00", "origin": "scale",
        "path": "vendor-app>vendor-api>other-vendor-api>other-vendor-export",
        "origin_evidence": "export header names the scale"})
    weight.append({
        "date": independent_day,
        # 400 g apart: a genuinely separate reading, and the informative one.
        "kg": round(weighed_days[independent_day]["kg"] + 0.4, 2),
        "source": "hand", "note": None,
        "_gen": 4, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
        "body_fat_lo": None, "body_fat_hi": None, "measured_at": "07:40",
        "recorded_at": f"{independent_day}T21:31:00+02:00", "origin": "athlete",
        "path": None, "origin_evidence": "written on a kitchen notepad"})

    # THE ACQUISITION CASE (#77/#78). A gym console is an independent
    # instrument the record almost never has - and the richest single reading
    # in a real record turned out to be its least verifiable, because it came
    # from a photograph of a console read by a model in a chat window, and
    # the photograph was never stored.
    #
    # Same origin, two acquisitions, two different error modes: the machine's
    # own link, and a picture of its display. `capture` is what separates
    # them; `origin` and `path` cannot, because both share those.
    console_day = (END - timedelta(days=9)).isoformat()
    sessions.append({
        "date": console_day, "type": "row", "distance_km": 3.1,
        "duration_s": 906, "avg_hr": None, "max_hr": None, "cadence": 25,
        "kcal": 148, "location": None, "rpe": 6, "rpe_scale": "borg-cr10", "note": None, "_gen": 6,
        "source": "gym-console", "start_time": f"{console_day}T19:40:00+02:00",
        "elevation_m": None, "setting": "indoor", "route": None,
        "place": "gym", "with": None, "context": "solo", "planned": None,
        "weather": None, "recorded_at": f"{console_day}T21:05:00+02:00",
        "track": None, "activity_id": None, "activity_source": None,
        "origin": "gym-console", "path": None,
        "origin_evidence": "the console's own display",
        "capture": "photo", "read_by": "model"})

    # THE UNNAMEABLE PAIR (#239). Two rides on one morning, same watch,
    # neither carrying a vendor id - which is the ORDINARY shape, not an edge
    # case: measured on a live record, seven sessions in ten shared a key with
    # something. Before ordinals, correcting either retired both, so two real
    # activities became one through the correction path.
    #
    # The third line corrects the SECOND ride's distance with a bare
    # reference, which names the most recent - the one a correction written
    # straight afterwards means. The first ride survives, and that is the
    # whole point.
    pair_day = (END - timedelta(days=16)).isoformat()
    for n, (km, secs, at, sup) in enumerate((
            (14.2, 2380, "08:28:00", None),
            (31.6, 4510, "08:47:00", None),
            (33.1, 4510, "09:02:00", f"{pair_day}/watch"))):
        sessions.append({
            "date": pair_day, "type": "cycle", "distance_km": km,
            "duration_s": secs, "avg_hr": None, "max_hr": None,
            "cadence": None, "kcal": None, "location": None, "rpe": None,
            "note": ("mis-typed as one ride; this is the second, corrected"
                     if sup else None),
            "_gen": 6, "source": "watch",
            "start_time": f"{pair_day}T{at}+02:00",
            "elevation_m": None, "setting": "outdoor", "route": None,
            "place": None, "with": None, "context": "solo", "planned": None,
            "weather": None,
            "recorded_at": f"{pair_day}T20:{10 + n:02d}:00+02:00",
            "track": None, "activity_id": None, "activity_source": None,
            "origin": "watch", "path": None, "origin_evidence": None,
            "capture": "connector", "read_by": None, "supersedes": sup})

    # A vendor-CLASSIFIED session (#88) and a MODELLED burn (#49) on the same
    # day. Neither is wrong to hold - what was wrong is that nothing said so:
    # a classifier's guess sat beside the athlete's own assertions under one
    # `type` column, and an estimated burn looked exactly like a measured one.
    guessed_day = (END - timedelta(days=12)).isoformat()
    sessions.append({
        "date": guessed_day, "type": "walk", "distance_km": 2.1,
        "duration_s": 1500, "avg_hr": 96, "max_hr": None, "cadence": None,
        "kcal": 95, "location": None, "rpe": None, "note": None, "_gen": 7,
        "source": "app", "start_time": f"{guessed_day}T12:40:00+02:00",
        "elevation_m": None, "setting": "outdoor", "route": None,
        "place": None, "with": None, "context": None, "planned": None,
        "weather": None, "recorded_at": f"{guessed_day}T21:40:00+02:00",
        "track": None, "activity_id": None, "activity_source": None,
        "origin": None, "path": None, "origin_evidence": None,
        "capture": None, "read_by": None,
        "modelled": None, "type_source": "vendor-classified"})
    for row in daily:
        if row["date"] == guessed_day and row.get("kcal_out") is not None:
            row["modelled"] = "kcal_out"

    # A two-source day: the calorie app disagrees with the watch about burn,
    # and owns intake the watch never sees. Field-wise precedence takes the
    # best witness per quantity - it does not add 2,443 to 2,844.
    two_source_day = (END - timedelta(days=21)).isoformat()
    app_claim = {"date": two_source_day, "steps": None, "distance_km": None,
                 "active_min": None, "kcal_out": 2844, "kcal_in": 2210,
                 "protein_g": 152, "sleep_h": None, "rhr": None,
                 "alcohol": None, "note": "logged in the calorie app",
                 "_gen": 2, "source": "app", "mood": None, "feel": None,
                 "coverage": "manual", "pain": None, "pain_site": None,
                 "pain_side": None}
    daily.append(app_claim)

    # THE LAST DAY BREACHES THE CAP, deliberately (#274). A daily ceiling is
    # scored on the day the viewpoint lands on, so a fixture whose final day
    # happens to be a quiet one exercises `room_left` and never `breach:
    # over` - and the over-side is the whole reason contract 24 exists. Every
    # shipped ceiling being respected teaches a consumer as little as no
    # ceiling at all.
    #
    # Written as an EDIT to the generated day rather than a second row: this
    # is the same athlete on the same day, not a second witness, and inventing
    # a source would have made it a resolution example instead of a ceiling
    # one.
    for row in daily:
        if row["date"] == END.isoformat() and row.get("source") != "app":
            row["kcal_in"] = 2870
            row["note"] = "long ride and a birthday dinner on the same day"
    daily.sort(key=lambda r: (r["date"], r.get("source") or ""))
    sessions.sort(key=lambda s: (s["date"], s["type"], s.get("source") or ""))

    goals, thresholds, achievements = _policy(start)
    events = _events(start)
    plans = _plans(start, sessions)
    context, measurements = _situational(start, END)
    medical = _medical(start, END)
    checks = _checks(END)
    # Built AFTER the session and weight lists are final: the sets hang off
    # sessions that exist and resolve their bodyweight against weigh-ins that
    # exist, so neither can be chosen before both are.
    sets = _strength(sessions, weight)
    # On the two-source day on purpose, so the itemised partial day meets the
    # athlete's own whole-day log and the record has to report the pair rather
    # than pick one.
    meals = _plates(two_source_day)
    journal = _said(start, END)

    # THE DERIVED CASE (#170). The athlete keeps their own average in a
    # notebook. It is a real number they act on, and it is not an observation:
    # it is two weigh-ins with arithmetic on top. Declaring that is what makes
    # it checkable - a reader can see which readings it stands on and that
    # nothing in this repo did the sum.
    #
    # It does not contest another claim on its date, so no count moves in this
    # corpus. The collapse it exists to enable (a written average agreeing
    # with the readings it was computed from is arithmetic agreeing with
    # itself) is exercised in `tests/test_lineage.py`.
    #
    # The RESTATEMENT half of the feature (correct an input, everything
    # standing on it is flagged) is exercised in `tests/test_lineage.py`
    # rather than here: it needs a superseded weigh-in, and dropping a line
    # from this record's weight series would move the weekly rates the whole
    # demo narrative is built on. Better a smaller demo than a demo whose
    # headline story shifted to make room for a second one.
    # WHERE THIS ROW SITS IS LOAD-BEARING, in two directions that pull against
    # each other, and getting it wrong switched off another demonstration
    # without failing a single test.
    #
    # It must stand ALONE: on a day that already has a reading the two claims
    # merge, and a merged row keeps no lineage, so the read model would show
    # none and the demo would demonstrate nothing.
    #
    # It must also stay INSIDE THE FINAL ISO WEEK. Dating it one day past the
    # last weigh-in looked adjacent and was not - the last weigh-in fell on a
    # Sunday, so the next day opened a new week holding one row, that week
    # became the one the rollup reports on, and the weigh-in-spread refusal
    # #37 exists to show stopped appearing in weekly.md. Nothing about the
    # lineage work was wrong; a demonstration row for one feature silently
    # turned off the demonstration of another.
    #
    # So the week is CHECKED rather than assumed. A date that looks adjacent
    # is exactly the trap.
    weighed_sorted = sorted(weighed_days)
    final_week = date.fromisoformat(weighed_sorted[-1]).isocalendar()[:2]
    avg_day = next(
        d.isoformat() for d in (
            date.fromisoformat(weighed_sorted[-1]) - timedelta(days=n)
            for n in range(7))
        if d.isocalendar()[:2] == final_week
        and d.isoformat() not in weighed_days
        and sum(1 for w in weighed_sorted if w < d.isoformat()) >= 2)
    assert date.fromisoformat(avg_day).isocalendar()[:2] == final_week, (
        "the notebook row must not open a week of its own")
    # The two most recent weigh-ins BEFORE it, so `derived_op` saying "the last
    # two" is true and nothing is derived from a reading taken afterwards.
    avg_inputs = [w for w in weighed_sorted if w < avg_day][-2:]
    weight.append({
        **{k: None for k in KEYS["weight"]},
        "date": avg_day,
        "kg": round(sum(weighed_days[d]["kg"] for d in avg_inputs)
                    / len(avg_inputs), 2),
        "source": "notebook", "measured_at": None,
        "recorded_at": f"{avg_day}T21:32:00+02:00",
        "origin": "athlete", "origin_evidence": "written in a notebook",
        # The athlete did the arithmetic, not the engine. That is the whole
        # distinction between the two derived captures - they carry identical
        # properties, and what `derived_external` says is that nothing in this
        # repo can reproduce the number from its inputs.
        "capture": "derived_external", "read_by": "athlete",
        "derived_from": [f"weight:{d}:{weighed_days[d].get('source') or 'unstated'}"
                         for d in avg_inputs],
        "derived_op": "mean of the last two weigh-ins, done on paper",
        "_gen": CURRENT_GENERATION["weight"]})

    # The provenance pair above appends out of order, and `recorded_at` is
    # derived from the date, so file order must follow date order or the
    # monotonicity check fires on the demo's own output.
    weight.sort(key=lambda r: (r["date"], r.get("recorded_at") or "",
                               r.get("source") or ""))

    for name, rows in (("weight", weight), ("daily", daily),
                       ("sessions", sessions), ("inferences", inferences),
                       ("goals", goals), ("thresholds", thresholds),
                       ("achievements", achievements), ("context", context),
                       ("measurements", measurements), ("medical", medical),
                       ("checks", checks), ("events", events),
                       ("sets", sets), ("meals", meals),
                       ("journal", journal), ("plans", plans)):
        (target / "data" / f"{name}.jsonl").write_text(
            _jsonl(rows), encoding="utf-8", newline="\n")


# The routes the athlete has names for. Real records have a handful, reused
# constantly, and the name is the thing a person remembers six months later -
# not the coordinates. Each carries the shape its track should have, so a
# route-matching consumer has more than one thing to match.
#
# Coordinates are fictional and deliberately coarse. A public demo repository
# is the last place real location data should ever be, and a synthetic athlete
# with a plausible-looking home is still a pattern worth not modelling.
ROUTES = {
    "canal-loop": {
        "lat": 51.2100, "lon": 3.2200, "climb": 0.55, "bend": 0.0016,
        "note": "flat towpath, there and back",
    },
    "hill-repeats": {
        "lat": 51.2260, "lon": 3.2410, "climb": 2.10, "bend": 0.0004,
        "note": "the same short rise, several times",
    },
    "river-ten": {
        "lat": 51.1980, "lon": 3.2050, "climb": 0.20, "bend": 0.0031,
        "note": "out along the river and back, the ten-kilometre one",
    },
}


# One degree of latitude is about 111.32 km. These tracks are short and far
# from the poles, so the flat approximation is fine - and using it is what
# lets a track be built to a TARGET LENGTH.
_M_PER_DEG_LAT = 111_320.0


def _route_gpx(route: str, day: str, start_hhmm: str, km: float,
               duration_s: int, fix_every_s: int = 10) -> str:
    """A synthetic track for a named route, BUILT TO THE SESSION'S OWN FIGURES.

    The geometry used to be fixed, so every track came out about 2 km whatever
    the row beside it said. A session claiming 10.48 km with a 2 km track is a
    fivefold contradiction sitting in the demo, and the first consumer to
    compare the two would have found it - which is the demo's entire job.
    Distance and elapsed time now come from the session, so the track's implied
    pace IS the session's pace and the two agree by construction.

    Deterministic - no RNG - so the demo stays byte-reproducible, which is what
    lets CI prove it.
    """
    import math
    r = ROUTES[route]
    hh, mm = (int(x) for x in start_hhmm.split(":"))
    n_out = max(8, int(duration_s / (2 * fix_every_s)))
    n = n_out * 2
    # Out and back, so each leg covers half the distance.
    step_deg = (km * 1000.0 / 2.0) / n_out / _M_PER_DEG_LAT
    dt = duration_s / n
    pts = []
    for i in range(n):
        leg = i if i < n_out else n - 1 - i           # out, then back
        secs = int(round(i * dt))
        pts.append((
            r["lat"] + leg * step_deg,
            r["lon"] + r["bend"] * math.sin(leg * math.pi / n_out),
            # The climb profile is per-100-metres-of-latitude, so it stays the
            # same gradient whatever the step size works out to be.
            round(4.0 + leg * r["climb"] * (step_deg / 0.00010), 1),
            f"{day}T{(hh + (mm * 60 + secs) // 3600) % 24:02d}:"
            f"{((mm * 60 + secs) // 60) % 60:02d}:{secs % 60:02d}Z",
        ))
    body = "\n".join(
        f'   <trkpt lat="{lat:.5f}" lon="{lon:.5f}"><ele>{ele}</ele>'
        f"<time>{t}</time></trkpt>" for lat, lon, ele, t in pts)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="vitai-demo" '
            'xmlns="http://www.topografix.com/GPX/1/1">\n'
            f" <trk><name>{route}</name><trkseg>\n"
            f"{body}\n"
            " </trkseg></trk>\n</gpx>\n")


def _demo_gpx(day: str) -> str:
    """A short synthetic track: a there-and-back along a canal, with a gentle
    rise. Deterministic - no RNG - so the demo stays byte-reproducible."""
    import math
    pts = []
    n = 240
    for i in range(n):
        leg = i if i < n // 2 else n - 1 - i          # out, then back
        # A curve rather than a straight line, so the shape classifier has
        # something to classify and RDP keeps a realistic number of vertices.
        pts.append((51.2100 + leg * 0.00010,
                    3.2200 + 0.0016 * math.sin(leg * math.pi / (n // 2)),
                    round(4.0 + leg * 0.55, 1),
                    f"{day}T14:{5 + i // 6:02d}:{(i * 10) % 60:02d}Z"))
    body = "\n".join(
        f'   <trkpt lat="{lat:.5f}" lon="{lon:.5f}"><ele>{ele}</ele>'
        f"<time>{t}</time></trkpt>" for lat, lon, ele, t in pts)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="vitai-demo" '
            'xmlns="http://www.topografix.com/GPX/1/1">\n'
            " <trk><name>canal-loop</name><trkseg>\n"
            f"{body}\n"
            " </trkseg></trk>\n</gpx>\n")


def _demo_tcx(day: str) -> str:
    """The same track as `_demo_gpx`, with the device's cumulative distance.

    The device's total is deliberately a little under the sum of the
    coordinates, which is what a watch that fuses GPS with an accelerometer
    actually reports on a curving path.
    """
    import math
    pts, n = [], 240
    for i in range(n):
        leg = i if i < n // 2 else n - 1 - i
        travelled = round(i * 11.2, 1)
        pts.append(
            f'<Trackpoint><Time>{day}T14:{5 + i // 6:02d}:{(i * 10) % 60:02d}Z</Time>'
            f"<Position><LatitudeDegrees>{51.2100 + leg * 0.00010:.5f}"
            "</LatitudeDegrees><LongitudeDegrees>"
            f"{3.2200 + 0.0016 * math.sin(leg * math.pi / (n // 2)):.5f}"
            "</LongitudeDegrees></Position>"
            f"<AltitudeMeters>{4.0 + leg * 0.55:.1f}</AltitudeMeters>"
            f"<DistanceMeters>{travelled}</DistanceMeters></Trackpoint>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            "<TrainingCenterDatabase "
            'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">\n'
            " <Activities><Activity Sport=\"Walking\"><Lap><Track>\n"
            + "\n".join(f"  {p}" for p in pts)
            + "\n </Track></Lap></Activity></Activities>\n"
            "</TrainingCenterDatabase>\n")


def _goal(date: str, slug: str, title: str, metric: str, target, policy: str,
          **kw) -> dict:
    """A goals.jsonl line with every key present (null for unknown)."""
    rec = {"date": date, "slug": slug, "title": title, "metric": metric,
           "dataset": None, "session_type": None, "tracker": None,
           "target": target, "policy": policy, "guard_pct": None,
           "period": "weekly", "on_period_end": "reset", "deadline": None,
           "status": "active", "motivator": None, "rationale": None,
           "on_success": None, "on_miss": None, "accountability": None,
           "set_by": "onboard", "reason": None, "note": None}
    rec.update(kw)
    return rec


def _goal2(date: str, slug: str, title: str, metric, target, policy: str,
           **kw) -> dict:
    """A generation-2 goals line: the G86 fields present, `_gen` stamped.

    The demo keeps BOTH generations in one file on purpose - that is what a
    real record looks like after a schema moves, and a gen-1 line that still
    validates is the property G25 exists to protect.
    """
    rec = _goal(date, slug, title, metric, target, policy)
    rec.update({"_gen": 2, "event": None, "deadline_kind": None,
                "verification": None, "change_kind": None})
    rec.update(kw)
    return rec


# A week off training. Chosen mid-block rather than at either end so it is a
# GAP with sessions on both sides, which is the shape a consumer has to render
# - a run of zero weeks at the edge could be explained away as the record
# starting or stopping.
#
# Deliberately NOT the travel week, which the record already declares as a
# context regime a fortnight later and which has its own missing weigh-ins.
# Two explanations for one gap would have made the fixture teach that an empty
# week always comes with a declared reason, and the whole point of contract
# 28's row is that a week of zeros says only what the record holds.
QUIET_WEEK = "2030-05-20"


def _quiet_week(day: str) -> bool:
    """Is this date inside the demo's one session-free week?"""
    from vitai.weeks import week_key

    return week_key(day) == QUIET_WEEK


def _stamp(rows: list[dict], hour: int) -> list[dict]:
    """One strictly increasing `recorded_at` per row, in file order.

    Transaction time is machine-set on append and monotonic by construction,
    and `vitai validate` checks that across the WHOLE file: a repeated stamp
    orders nothing, and one out of order is how a hand-written line gives
    itself away. A demo that authored these by hand would fail the very check
    it is meant to show working, so they are generated from file position.
    """
    for n, row in enumerate(rows):
        row["recorded_at"] = f"{row['date']}T{hour:02d}:{n:02d}:00+02:00"
    return rows


# The seven configuration fields arrived at generation 3 (#99). A gen-2 line
# does not owe them and must not carry them - that is the whole G25 property,
# and `sets` is the only dataset here where both shapes can be shown inside
# one increment rather than across the athlete's tracker changing hands.
_SET_CONFIG_KEYS = ("equipment", "angle_class", "angle_deg",
                    "resistance_level", "seat_pos", "pad_pos", "lever_pos")


def _set(date: str, start: str, exercise: str, index: int, gen: int,
         **kw) -> dict:
    """A sets.jsonl line with every key its generation owes (null for unknown).

    `set_index` is required rather than optional: it is what lets a correction
    name one set out of five, and without it every unnumbered set of the same
    exercise shares an identity, so retiring one retires them all.
    """
    rec = {"date": date, "session_start": start, "exercise": exercise,
           "block": 1, "round": None, "set_index": index,
           "reps_completed": None, "reps_attempted": None,
           "load": None, "load_type": None, "load_unit": None, "machine": None,
           "set_type": "working", "failure": None, "rir": None, "rpe": None,
           "rest_s": None, "tempo": None, "duration_s": None, "side": None,
           "note": None, "source": "app", "recorded_at": None,
           "origin": None, "path": None, "origin_evidence": None,
           "capture": None, "read_by": None}
    if gen >= 3:
        rec.update(dict.fromkeys(_SET_CONFIG_KEYS))
    rec["_gen"] = gen
    rec.update(kw)
    return rec


def _item(date: str, meal: str, item: str, **kw) -> dict:
    """A meals.jsonl line: one ITEM of a plate, never a dish.

    The per-100 g figures are what the table said, stored beside the table's
    name, because a composition table is an external fact that gets revised -
    a row holding only a gram count would silently re-price this plate the day
    an update shipped. The energy is derived from the grams and never stored.
    """
    rec = {"date": date, "meal": meal, "item": item,
           "grams": None, "grams_lo": None, "grams_hi": None,
           "kcal_100g": None, "protein_100g": None, "fat_100g": None,
           "carb_100g": None, "food_table": None, "note": None,
           "source": "hand", "recorded_at": None, "origin": "athlete",
           "path": None, "origin_evidence": None, "capture": None,
           "read_by": None, "_gen": 2}
    rec.update(kw)
    return rec


def _entry(date: str, kind: str, text: str, **kw) -> dict:
    """A journal.jsonl line: what the ATHLETE said, in their own words.

    Deliberately not an inference: an inference carries a `model` and is the
    engine's output, so filing a first-hand statement there would launder the
    athlete's own claim as something the engine worked out.
    """
    rec = {"date": date, "kind": kind, "text": text, "about": None,
           "source": "athlete", "confidence": None, "status": "open",
           "note": None, "recorded_at": None, "_gen": 2}
    rec.update(kw)
    return rec


def _event(date: str, slug: str, title: str, kind: str, event_date: str,
           **kw) -> dict:
    """An events.jsonl line with every key present (null for unknown)."""
    rec = {"date": date, "slug": slug, "title": title, "kind": kind,
           "event_date": event_date, "priority": None, "immovable": True,
           "place": None, "status": "confirmed", "set_by": "athlete",
           # NULL until the day is past (#139), which is the ordinary state of
           # a fixture and must never be read as "did not happen".
           "reason": None, "note": None, "outcome": None}
    rec.update(kw)
    return rec


def _plan(date_made: str, slug: str, for_date: str, activity: str,
          tier: str, **kw) -> dict:
    """A plans.jsonl line with every key present (null for unknown)."""
    rec = {"date": date_made, "slug": slug, "for_date": for_date,
           "for_phase": None, "activity": activity, "setting": None,
           "tier": tier, "serves": None, "set_by": "athlete",
           "requires": None, "outcome": "unresolved", "reason": None,
           "session_ref": None, "note": None, "supersedes": None,
           "device": None}
    rec.update(kw)
    return rec


def _plans(start: date, sessions: list[dict]) -> list[dict]:
    """What days were MEANT to be, including the ones that were not (#221).

    Every outcome the vocabulary has, because a fixture holding one value of a
    closed enum proves nothing about the distinction the field exists to draw
    - and this vocabulary's whole purpose is that a skipped plan, an
    unactivated one and an unanswered one are different facts.

    Nothing here is scored. `reason` is COM-B and is a classification; the
    demo carries the values so a consumer can see them, not so anything can
    total them.
    """
    d = (start + timedelta(days=50)).isoformat()
    ran = sorted(s["date"] for s in sessions if s.get("type") == "run")
    done = ran[-1] if ran else (start + timedelta(days=55)).isoformat()
    return _stamp([
        # COMPLETED, and the session cites nothing - the plan cites the
        # session, which is the direction that survives the day not happening.
        _plan(d, "tue-easy-run", done, "run", "programme",
              serves="running", for_phase="evening",
              outcome="completed", session_ref=done,
              note="the ordinary case, and the one the old field could hold"),
        # SKIPPED, with the reason on the axis a coach can act on: the gym was
        # shut, which is opportunity rather than motivation, and collapsing
        # the two is what the two-value vocabulary did.
        _plan(d, "thu-strength", (start + timedelta(days=52)).isoformat(),
              "strength", "programme", serves="running", for_phase="evening",
              outcome="skipped", reason="opportunity_physical",
              note="gym shut for maintenance"),
        # DID NOT ACTIVATE. The precondition never held, so there was nothing
        # to skip - and without the value a cautious athlete who writes a
        # condition down is punished for the forecast.
        _plan(d, "sat-long-run-outdoors",
              (start + timedelta(days=54)).isoformat(), "run", "committed",
              for_phase="morning", setting="outdoor",
              requires="dry-forecast", outcome="did_not_activate",
              note="if it is dry; it was not"),
        # PROVISIONAL and unanswered. Recording an idea has to be free or the
        # athlete stops recording ideas - and silence is not a lapse, so the
        # outcome stays unresolved and carries no reason at all.
        _plan(d, "maybe-a-swim", (start + timedelta(days=56)).isoformat(),
              "swim", "provisional", for_phase="evening",
              note="an idea, and skipping it costs nothing"),
        # A DELIBERATE REST, which the model already holds can be the
        # achievement rather than the failure. `motivation_reflective` is the
        # COM-B subtype for it, and the two-value axis called it `chosen`
        # alongside "could not face it".
        _plan(d, "sun-rest", (start + timedelta(days=55)).isoformat(),
              "run", "programme", serves="running", for_phase="morning",
              outcome="skipped", reason="motivation_reflective",
              note="legs still heavy from the long run - took the rest"),
    ], hour=21)


def _events(start: date) -> list[dict]:
    """Dated fixtures: the one the block is built around, one that is simply
    true and constrains it (G86), and one restated with its outcome."""
    d0 = start.isoformat()
    return [
        _event(d0, "autumn-half", "The autumn half marathon", "competition",
               "2030-09-15", priority="a", place="a river town",
               note="the date the whole run block is planned backwards from"),
        _event(d0, "spring-5k-race", "The spring 5k", "competition",
               "2030-05-15", priority="b", place="the park circuit",
               note="a hard date - the goal that points at it cannot be "
                    "part-met"),
        # THE OUTCOME, once the day is past (#139). The race happened and the
        # record holds no session for it, which is the common case rather than
        # the exotic one: a race day is exactly when logging is least likely.
        # Without this row the demo could not tell that apart from a race the
        # athlete skipped, and neither could any consumer built against it.
        _event((start + timedelta(days=40)).isoformat(), "spring-5k-race",
               "The spring 5k", "competition", "2030-05-15", priority="b",
               place="the park circuit", outcome="took_place",
               note="ran it; the watch was left at home, so there is no "
                    "session row and that is a gap in the log rather than "
                    "in the running"),
        _event((start + timedelta(days=30)).isoformat(), "hip-scan",
               "Hip imaging follow-up", "clinical", "2030-07-10",
               priority="c", immovable=True,
               note="booked by the clinic - coarse on purpose, no diagnosis here"),
    ]


def _policy(start: date) -> tuple[list[dict], list[dict], list[dict]]:
    """The demo's dated policy: goals, threshold changes, one achievement."""
    d0 = start.isoformat()
    goals = [
        # THE TWO ACHIEVEMENT STATES THAT HAD NOWHERE TO LIVE (#235), because
        # the old vocabulary mixed lifecycle with achievement and `achieved`
        # was terminal.
        #
        # SUSTAINING: reached and still being held. `achieved` said the story
        # was over; this athlete hit his weekly active-minutes floor months ago
        # and is keeping it, which is a different fact from having hit it once.
        #
        # `active_min` deliberately: no other demo goal claims that metric, and
        # a second goal on one metric would make the demo exhibit the
        # first-match-wins ambiguity `_goal_for` already concedes it should not
        # be resolving.
        _goal(d0, "active-minutes", "Keep 150 active minutes a week",
              "active_min", 150, "monotonic", dataset="daily",
              status="achieved",
              motivator="Everything else works better when this one does",
              rationale="Reached it in the spring; the point now is not to lose it",
              on_success="hold", on_miss="reflect"),
        # NOT ACHIEVED: the window closed. Not a prediction - the deadline is
        # in the past and the target was not met. FHIR's `not-attainable`
        # means "not POSSIBLE to be met", which is the modal claim G58's
        # declaration gate makes; this is the plainer "has not been met".
        # Left `active` deliberately: the athlete never closed it, and the
        # engine reporting the arithmetic is not the same as him deciding to
        # abandon it.
        # A 5k TIME is not a thing this engine measures, it is a thing a race
        # clock measures. It was carried as 200 km of running a week, which is
        # not a volume any human runs, and its own rationale gave the game
        # away by describing the 200 as the total for the whole block. So the
        # goal says what it is: verified externally, tracked by the clock, no
        # numeric target, pointed at the race on the date its deadline already
        # named.
        _goal(d0, "spring-5k", "Sub-22 for the 5k by the spring race",
              "external", None, "monotonic", tracker="the race clock",
              period="none", deadline="2030-05-15",
              verification="external", deadline_kind="hard",
              event="spring-5k-race",
              motivator="Wanted one fast one before the half-marathon block",
              rationale="the clock at the race decides this one, not the "
                        "training log",
              on_success="hold", on_miss="reflect"),
        _goal(d0, "steps", "Walk 70k steps a week", "steps", 70000,
              "monotonic", dataset="daily",
              motivator="Keep the desk job from winning",
              rationale="10k a day, averaged - a floor that survives a bad day",
              on_success="hold", on_miss="reflect"),
        _goal(d0, "running", "Build to 30 km a week, injury-free", "distance_km",
              30, "guarded", guard_pct=0.1, dataset="sessions",
              session_type="run", deadline="2030-08-31",
              motivator="Finish the autumn half without limping",
              rationale="10% weekly ramp is the ceiling my hip tolerated last time",
              on_success="escalate", on_miss="hold"),
        # A goal that lives in another app entirely: vitai tracks and asks
        # about it, but never invents a verdict for it (G19).
        _goal((start + timedelta(days=21)).isoformat(), "segment",
              "Take back the riverside segment", "external", None, "monotonic",
              tracker="a public segment leaderboard", period="none",
              on_period_end=None,
              motivator="Losing it to a neighbour stung more than expected"),
        # The steps goal is raised once, mid-block, and explained.
        _goal((start + timedelta(days=42)).isoformat(), "steps",
              "Walk 77k steps a week", "steps", 77000, "monotonic",
              dataset="daily", set_by="athlete",
              reason="the 70k weeks stopped feeling like effort",
              motivator="Keep the desk job from winning",
              rationale="10k a day, averaged - a floor that survives a bad day",
              on_success="hold", on_miss="reflect"),
        # --- generation 2 (G86) ------------------------------------------
        # The run block is anchored to a real fixture. The deadline is the
        # organiser's date, so it is HARD by derivation rather than by the
        # athlete re-declaring it.
        _goal2((start + timedelta(days=45)).isoformat(), "running",
               "Build to 30 km a week, injury-free", "distance_km", 30,
               "guarded", guard_pct=0.1, dataset="sessions",
               session_type="run", event="autumn-half", deadline=None,
               set_by="athlete",
               reason="anchoring the block to the race rather than a date I picked",
               motivator="Finish the autumn half without limping",
               rationale="10% weekly ramp is the ceiling my hip tolerated last time",
               on_success="escalate", on_miss="hold"),
        # A SOFT deadline, and then a move of it. This is the false positive
        # the increment removes: the date was self-imposed, so revising it is
        # a change of direction, not a retreat - and the engine must not
        # accuse anyone of gaming a commitment they invented.
        _goal2((start + timedelta(days=14)).isoformat(), "weight",
               "Down to 78 kg, unhurried", "kg", 78, "monotonic",
               # `dataset` deliberately UNSET, which is the shape a
               # hand-written goal row actually has (#36). The scope is
               # inferred from the metric - a goal in kg is a weight goal -
               # and the engine then declines to score it rather than
               # reporting 0%.
               period="none", on_period_end=None,
               deadline="2030-10-01", deadline_kind="soft", set_by="athlete",
               motivator="The hill on the way home stops being an event",
               rationale="slow enough that the running keeps improving"),
        # THE DIRECTION, DECLARED (#273). A level goal with no polarity is
        # scored as a floor, so "down to 78" read as though more kilograms
        # were progress - and the demo shipped it that way, which meant no
        # consumer could learn from this fixture that a level goal exists.
        #
        # The EARLIER line above deliberately keeps its polarity unset. That
        # is the shape a goal written before contract 24 actually has, it is
        # what `vitai validate` advises on, and a record where every line was
        # already correct would demonstrate neither the hazard nor the advice.
        _goal2((start + timedelta(days=70)).isoformat(), "weight",
               "Down to 78 kg, unhurried", "kg", 78, "monotonic",
               polarity="ceiling",
               period="none", on_period_end=None,
               deadline="2031-02-01", deadline_kind="soft", set_by="athlete",
               reason="the race block matters more than the scale this year, "
                      "and saying which way is down so the engine can score it",
               motivator="The hill on the way home stops being an event",
               rationale="slow enough that the running keeps improving"),
        # A CEILING THAT IS BREACHED, which is contract 24's motivating case
        # and which no shipped fixture could show. 1100 kcal a day against a
        # 1200 cap once reported 641.7% and minted four milestones for
        # breaching it; a consumer reading a demo of nothing but floors
        # reproduces that in its own client, which is what happened.
        #
        # `daily` and not a period that accumulates: a cap is a per-day limit,
        # and scoring one over a week is the same defect facing the other way.
        # 2600 rather than a round 2500: the record holds two days above it,
        # so the fixture exercises `breach: over` rather than only the
        # comfortable side of a cap. A demo whose every ceiling is respected
        # teaches a consumer as little as one with no ceiling at all.
        #
        # Well clear of the intake floor, which a target may not be set
        # beneath (G58) - a cap that refused at declaration would demonstrate
        # the refusal and not the ceiling.
        _goal2((start + timedelta(days=28)).isoformat(), "intake-cap",
               "Stay under 2600 kcal on a normal day", "kcal_in", 2600,
               "monotonic", polarity="ceiling", period="daily",
               dataset="daily", on_period_end=None, set_by="athlete",
               motivator="The big days were undoing the ordinary ones",
               rationale="a ceiling for a normal day, not for a race week"),
        # ATTESTED: no metric, no target, and there never will be one. The
        # engine holds it, surfaces it and asks about it, and takes the
        # athlete's word as the only evidence there will ever be (G83).
        _goal2((start + timedelta(days=14)).isoformat(), "enjoy-running",
               "Enjoy running again, the way I used to", None, None,
               "monotonic", verification="attested", period="none",
               on_period_end=None, dataset=None, set_by="athlete",
               motivator="The training worked and the enjoying stopped",
               rationale="nothing measures this and nothing should"),
        _goal2((start + timedelta(days=48)).isoformat(), "steps",
               "Walk 77k steps a week", "steps", 7700, "monotonic",
               dataset="daily", set_by="athlete",
               motivator="Keep the desk job from winning",
               rationale="10k a day, averaged - a floor that survives a bad day",
               on_success="hold", on_miss="reflect"),
        # A CORRECTION: the earlier line was a mis-entry, not a change of
        # mind, so it must leave no churn row behind (#26).
        _goal2((start + timedelta(days=49)).isoformat(), "steps",
               "Walk 77k steps a week", "steps", 77000, "monotonic",
               dataset="daily", set_by="athlete", change_kind="correction",
               supersedes=f"steps@{(start + timedelta(days=48)).isoformat()}",
               reason="the 7700 on the previous line was a typo for 77000",
               motivator="Keep the desk job from winning",
               rationale="10k a day, averaged - a floor that survives a bad day",
               on_success="hold", on_miss="reflect"),
    ]
    thresholds = [
        {"date": d0, "key": "steps_floor", "value": 9000,
         "change_kind": "change", "set_by": "onboard",
         "reason": "starting floor from the onboarding interview", "note": None},
        {"date": d0, "key": "kcal_target", "value": 2150,
         "change_kind": "change", "set_by": "onboard",
         "reason": "deficit sized for the phase-1 rate", "note": None},
        {"date": d0, "key": "protein_g_target", "value": 145,
         "change_kind": "change", "set_by": "onboard",
         "reason": "1.8 g/kg at target weight", "note": None},
        # A deliberate loosening, three days after a missed steps week. The
        # engine flags the TIMING; the stated reason is what makes it readable
        # as a deload rather than a retreat.
        {"date": (start + timedelta(days=59)).isoformat(), "key": "steps_floor",
         "value": 8000, "change_kind": "change", "set_by": "athlete",
         "reason": "travel week, protecting the run block instead", "note": None},
    ]
    achievements = [
        {"date": (start + timedelta(days=77)).isoformat(),
         "title": "First 21 km in one run", "goal": "running",
         "source": "athlete",
         "note": "unplanned, and the hip held - but it was not budgeted"},
    ]
    return goals, thresholds, achievements


def _medical(start: date, end: date) -> list[dict]:
    """Two episodes: one closed, one still gating (G11), on opposite sides.

    The resolved calf strain shows a complete lifecycle - onset, physio visit,
    resolution - so the episode window is visible with both ends. The achilles
    episode is deliberately left open at the end of the block so the demo
    always renders an ACTIVE gate: the state a consumer most needs to handle
    correctly, and the one that is easiest to forget to test against.

    Nothing here is a diagnosis and no clinician is named - `provider_type` is
    as specific as the record gets about who was seen.
    """
    return [
        {"date": (start + timedelta(days=9)).isoformat(), "slug": "calf-strain",
         "kind": "injury", "title": "Left calf strain on a hill rep",
         "body_site": "calf", "body_side": "left",
         "severity": "moderate", "status": "active",
         "resolved_date": None, "restricts": "run impact",
         "provider_type": None, "source": "athlete",
         "note": "pulled up mid-session, walked home"},
        {"date": (start + timedelta(days=14)).isoformat(), "slug": "calf-strain",
         "kind": "visit", "title": "Physio assessment - left calf",
         "body_site": "calf", "body_side": "left",
         "severity": "mild", "status": "monitoring",
         "resolved_date": None, "restricts": "impact",
         "provider_type": "physio", "source": "athlete",
         "note": "cleared to walk and cycle; graded return to running"},
        {"date": (start + timedelta(days=31)).isoformat(), "slug": "calf-strain",
         "kind": "injury", "title": "Left calf strain resolved",
         "body_site": "calf", "body_side": "left",
         "severity": "none", "status": "resolved",
         "resolved_date": (start + timedelta(days=31)).isoformat(),
         "restricts": None, "provider_type": "physio", "source": "athlete",
         "note": "full sessions with no symptoms for two weeks"},
        # Still open at the end of the block: the demo always has a live gate,
        # and this one is CONDITIONAL - the restriction lifts on a day the
        # morning check passes, and stands on a day nobody ran it.
        {"date": (end - timedelta(days=4)).isoformat(), "slug": "achilles",
         "kind": "symptom", "title": "Right achilles soreness after the long run",
         # THE OTHER LEG (#145), and it agrees with the title, which already
         # said "Right achilles". One episode per side is what makes the field
         # worth having: a consumer gating "the calf" must not stop the work
         # this athlete can do on the other leg, and a fixture where every
         # episode shares a side could not show that.
         "body_site": "achilles", "body_side": "right",
         "severity": "mild", "status": "monitoring",
         "resolved_date": None, "restricts": "impact", "provider_type": None,
         "source": "athlete",
         "note": "stiff first thing; eases once warm - watching it",
         "onset_date": (end - timedelta(days=6)).isoformat(),
         "precondition": "hop-test", "expects": None,
         # Post-coordinated (G85): impact is the coarse projection, and the
         # structured spec says what the physio actually said - loaded calf
         # work is out, everything else on that leg is fine.
         "restriction": "pattern=jump region=achilles load=loaded", "_gen": 3},
        # A historical episode, entered late: onset years before the entry
        # date, which the record could not express until the split.
        {"date": (end - timedelta(days=1)).isoformat(), "slug": "old-ankle",
         "kind": "injury", "title": "Ankle sprain (recalled, pre-record)",
         # NO SIDE, deliberately: it predates the field in the story this
         # record tells, which is the shape most real episodes have.
         #
         # It draws no advisory, and that is the rule working rather than
         # failing. `side_advisories` fires only where an episode can still
         # GATE - open, and restricting something - because a resolved
         # episode restricts nothing and naming its side changes no answer.
         # This one is resolved.
         "body_site": "ankle", "severity": "none", "status": "resolved",
         "resolved_date": "2028-05-01", "restricts": None,
         "provider_type": "physio", "source": "athlete",
         "note": "recorded from memory while filling in history",
         "onset_date": "2028-03-02", "precondition": None,
         "expects": None, "restriction": None, "_gen": 3},
    ]


def _checks(end: date) -> list[dict]:
    """Daily results for the achilles gate's hop test.

    Deliberately incomplete. Two days pass, one fails, and the last day has no
    entry at all - so the demo renders all three gate states, including the
    one that matters most: a check nobody did is not a pass.
    """
    return [
        {"date": (end - timedelta(days=3)).isoformat(), "slug": "hop-test",
         "result": "pass", "value": 5, "source": "athlete",
         "note": "5 hops, no pain"},
        {"date": (end - timedelta(days=2)).isoformat(), "slug": "hop-test",
         "result": "fail", "value": 2, "source": "athlete",
         "note": "sore by the third hop - walked instead"},
        {"date": (end - timedelta(days=1)).isoformat(), "slug": "hop-test",
         "result": "pass", "value": 5, "source": "athlete", "note": None},
    ]


def _strength(sessions: list[dict], weight: list[dict]) -> list[dict]:
    """Sets for gym sessions the record ALREADY holds (#97/#99/#60).

    Hung off existing sessions rather than invented beside them. A set whose
    `session_start` names no session is a set nobody can put in a session, and
    a demo arguing for this dataset with rows the rest of the file does not
    corroborate would be arguing for nothing.

    The three days are chosen by RULE rather than written down, so the block
    survives a reseed: the earliest gym session that carries both a start_time
    and a same-day weigh-in (the bodyweight block needs both to resolve), and
    the last two gym weekends.

    No RNG. Every draw in this file feeds one shared stream, so a single extra
    `rng.random()` here would rewrite twelve committed datasets. The narrative
    is hand-tuned anyway - these numbers are an argument, not a sample.
    """
    weighed = {row["date"] for row in weight}
    # Only sessions past the provenance cutover carry a `start_time`, which is
    # the leading identity field: without it a set can name its date but not
    # its session, and two sessions on one day become indistinguishable.
    gym = [s for s in sessions if s["type"] == "strength" and s.get("start_time")]
    early = next(s for s in gym if s["date"] in weighed)
    last = gym[-1]
    # A week back, not simply the one before: the two stack readings below have
    # to sit far enough apart to READ as a progression, because the point is
    # that they are not one.
    cutoff = (date.fromisoformat(last["date"]) - timedelta(days=5)).isoformat()
    prior = [s for s in gym if s["date"] <= cutoff][-1]

    rows: list[dict] = []
    # --- the block nobody said was maximal -----------------------------------
    # 13, 12, 10 with `failure` null throughout. Set 1 LOOKS like a maximum and
    # set 2 holds 92% of it, where a set taken to genuine failure leaves 55-70%
    # - so the real max is nearer 15 than 13, and the only reason anyone can
    # tell is that the record says nobody stated an endpoint. Null is UNSTATED,
    # and a reader that treats it as "to failure" gets the athlete's ceiling
    # wrong by three reps.
    #
    # `bodyweight` means the load IS the athlete: `load` is null and resolves
    # against the weigh-in on the day, which is also why push-ups get easier
    # across a cut for reasons that have nothing to do with strength.
    #
    # Generation 2, and this is the honest half of the coexistence story: these
    # were logged before the configuration columns existed, and a push-up would
    # have had nothing to put in them anyway.
    for index, reps in ((1, 13), (2, 12), (3, 10)):
        rows.append(_set(
            early["date"], early["start_time"], "push-up", index, 2,
            reps_completed=reps, reps_attempted=reps, load_type="bodyweight",
            rest_s=90, source="hand", origin="athlete",
            origin_evidence="written in the notebook between sets",
            capture="manual_entry"))

    # --- the attempt that was not completed ----------------------------------
    # Two different shapes, and they are different facts. Set 3 initiated five
    # reps and finished four: the fifth stalled halfway, which is data about
    # where the ceiling is. Set 4 initiated one and finished none - the
    # `75 FAILED` line that is the single most informative set of a session and
    # had nowhere to live until this dataset. Neither is the same fact as no
    # row at all, which is what a set that was never attempted looks like.
    #
    # The back-off set closes the block on a `volitional` stop, so the file
    # holds all three endpoint states beside each other: reps left by choice,
    # reps that could not be completed, and nobody saying.
    #
    # Every set below is the athlete ASSERTING it - what changed since the
    # notebook block is only where it was written down. The app is the
    # terminus, never the observer, which is the whole distinction `source`
    # alone was being asked to carry and could not.
    logged = {"origin": "athlete", "capture": "manual_entry",
              "origin_evidence": "typed into the gym app between sets"}
    bench = [
        _set(prior["date"], prior["start_time"], "bench-press", 1, 3,
             set_type="warmup", reps_completed=8, reps_attempted=8,
             load=40, load_type="external", load_unit="kg", rest_s=120,
             equipment="barbell", angle_class="flat", **logged),
        _set(prior["date"], prior["start_time"], "bench-press", 2, 3,
             reps_completed=6, reps_attempted=6, load=60, load_type="external",
             # The set carries a perceived exertion and says which scale it is
             # on (#246). Without it a 7 here is unreadable: "quite light" on
             # Borg's 6-20 and "very hard" on CR10.
             load_unit="kg", rir=2, rpe=7, rpe_scale="borg-cr10", rest_s=180,
             equipment="barbell", angle_class="flat", **logged),
        _set(prior["date"], prior["start_time"], "bench-press", 3, 3,
             reps_completed=4, reps_attempted=5, load=70, load_type="external",
             load_unit="kg", failure="muscular", rir=0, rest_s=180,
             equipment="barbell", angle_class="flat", **logged,
             note="the fifth stalled halfway up and came back down"),
        _set(prior["date"], prior["start_time"], "bench-press", 4, 3,
             reps_completed=0, reps_attempted=1, load=75, load_type="external",
             load_unit="kg", failure="muscular", rir=0, rest_s=180,
             equipment="barbell", angle_class="flat", **logged),
        _set(prior["date"], prior["start_time"], "bench-press", 5, 3,
             set_type="backoff", reps_completed=8, reps_attempted=8, load=60,
             load_type="external", load_unit="kg", failure="volitional",
             rir=2, rest_s=180, equipment="barbell", angle_class="flat",
             **logged),
    ]
    rows += bench

    # --- the number that is not a mass ---------------------------------------
    # 66 on the blue-frame leg press, and 66 on the grey one a week later. A
    # naive reader sees a load held flat across a week; there is no such fact
    # here, because a stack number is a PIN POSITION on one manufacturer's
    # scale and 66 on two machines is two different loads. `load_unit` is null
    # for the same reason: stating kilograms would make the value look
    # comparable, which is the one thing it is not.
    #
    # `seat_pos` differs between them, which is a second machine-scoped ordinal
    # and travels with its machine for exactly the same reason.
    rows.append(_set(
        prior["date"], prior["start_time"], "leg-press", 1, 3, block=2,
        reps_completed=12, reps_attempted=12, load=66,
        load_type="machine_stack", machine="leg press (blue frame)",
        rest_s=120, equipment="machine", seat_pos=4, **logged))
    # --- a load the athlete carries, plus one they added ---------------------
    # `bodyweight_plus` records the ADDED mass only, so the resolved load is
    # the weigh-in plus ten - which makes it a MODELLED figure that must never
    # sit beside barbell kilos as an equal number.
    rows.append(_set(
        last["date"], last["start_time"], "dip", 1, 3,
        reps_completed=6, reps_attempted=7, load=10,
        load_type="bodyweight_plus", load_unit="kg", failure="technical",
        rest_s=150, equipment="plate", **logged,
        note="the seventh went crooked and I racked it"))
    rows.append(_set(
        last["date"], last["start_time"], "leg-press", 1, 3, block=2,
        reps_completed=12, reps_attempted=12, load=66,
        load_type="machine_stack", machine="leg press (grey frame)",
        rest_s=120, equipment="machine", seat_pos=3, **logged))

    rows.sort(key=lambda r: (r["date"], r["block"], r["set_index"]))
    return _stamp(rows, 20)


def _plates(day: str) -> list[dict]:
    """One photographed plate, itemised, plus a snack nobody has priced (#96).

    Deliberately on the day the calorie app already logged a whole-day intake.
    A partial day and a whole day are DIFFERENT QUANTITIES - the meals the
    athlete did not photograph are missing from one and present in the other -
    so the pair is reported and never resolved. Resolving it is the trap:
    `stated-in-chat` outranks an app export in the precedence ladder, so
    writing a photo estimate into `kcal_in` would displace the athlete's own
    itemised log with a model's guess.

    What the photograph settles and what it does not is the whole split. It
    settles COMPOSITION well - skin-on thigh rather than breaded, which is 40
    kcal/100 g of difference - and PORTIONS badly, which is what the ranges
    carry. There is no confidence number anywhere here: no corpus of
    photo-estimated meals scored against weighed truth exists, so a decimal
    would be a calibration nobody has ever measured. The range IS the
    confidence statement.
    """
    rows = [
        # The item the photograph genuinely cannot settle, and the widest
        # contributor by a distance: 80 g of chicken either way is ~190 kcal,
        # and no amount of model effort on the pixels recovers it. One question
        # does, which is why asking is a step rather than a fallback.
        _item(day, "lunch", "chicken thigh, skin on, roasted",
              grams=150, grams_lo=110, grams_hi=190,
              kcal_100g=240, protein_100g=25.0, fat_100g=15.0, carb_100g=0.0,
              food_table="ciqual", capture="photo", read_by="model",
              origin_evidence="a photograph of the plate, taken before eating"),
        _item(day, "lunch", "mixed leaves",
              grams=80, grams_lo=60, grams_hi=100,
              kcal_100g=17, protein_100g=1.4, fat_100g=0.3, carb_100g=1.5,
              food_table="ciqual", capture="photo", read_by="model",
              origin_evidence="a photograph of the plate, taken before eating",
              note="matte leaves, no dressing - the second bowl in the same "
                   "frame has obvious dressing on it"),
        # The smallest thing on the plate and the second-widest number on it.
        # A photograph cannot see poured oil at all, and at 884 kcal/100 g the
        # 13 g nobody can bound is worth more than the entire salad.
        _item(day, "lunch", "olive oil",
              grams=10, grams_lo=5, grams_hi=18,
              kcal_100g=884, protein_100g=0.0, fat_100g=100.0, carb_100g=0.0,
              food_table="ciqual", capture="photo", read_by="model",
              origin_evidence="a photograph of the plate, taken before eating"),
        # The packaged one. Its range is stated and ZERO-WIDTH, which is not
        # the same as absent: the pack settled the quantity, so the bounds are
        # an assertion rather than an omission. Its composition comes off the
        # label rather than a food table, which is why `food_table` is per-item
        # - two items of one meal can legitimately come from different tables,
        # and a figure whose source is unrecorded cannot be rechecked when that
        # table is revised.
        _item(day, "lunch", "rye crispbread",
              grams=20, grams_lo=20, grams_hi=20,
              kcal_100g=336, protein_100g=9.5, fat_100g=1.7, carb_100g=63.0,
              food_table="pack-label", capture="manual_entry",
              origin_evidence="the figures printed on the pack"),
        # An item with no composition at all. NAMED rather than dropped: a
        # total that silently omits something is wrong in the direction that
        # matters most, and an unpriced item is a lookup that has not happened
        # yet rather than an item that contributes nothing. It is what makes
        # this day's total report itself as incomplete.
        _item(day, "snack", "mixed nuts, a handful",
              grams=30, grams_lo=20, grams_hi=45,
              capture="narrative", read_by="athlete"),
    ]
    return _stamp(rows, 21)


def _said(start: date, end: date) -> list[dict]:
    """What the athlete said, and what became of it.

    The dataset earns its place on the last row: a CLAIM the rest of the
    record contradicts. Everything else here could be inferred from the
    numbers eventually; that a thing was said, on a date, cannot be, and it is
    ground truth even when what was said is wrong.

    `status` is what stops this becoming a diary nobody reads back. A worry
    that is still open is a thing to raise; one that resolved is not, and an
    idea that grew into a real goal must be able to say so rather than sitting
    there looking un-acted-on forever.

    `confidence` is how FIRMLY it was expressed, never how likely it is to be
    true - a passing "maybe I should" is not a decision, and the difference is
    what keeps an athlete from being held to something they never chose.
    """
    return _stamp([
        # Superseded by the running goal anchoring to the autumn half. The
        # grain of a goal has to be able to close, or the coach keeps asking
        # about a musing that has already become a commitment.
        _entry((start + timedelta(days=14)).isoformat(), "idea",
               "Maybe I should point all of this at a race in the autumn "
               "instead of just running.",
               about="running", confidence=0.3, status="superseded",
               note="became the running goal once the autumn half was entered"),
        # A preference constrains what may be PROPOSED. Without it the obvious
        # advice on a stalling cut is to cut harder, which is precisely the
        # thing this athlete has said they will not trade.
        _entry((start + timedelta(days=35)).isoformat(), "preference",
               "I would rather the weight came off slowly than lose the part "
               "where the running is fun.",
               about="weight", confidence=0.9),
        # Answered by the pattern inference of the same date, so it closes.
        _entry((end - timedelta(days=9)).isoformat(), "question",
               "Is the easy-run heart rate creeping up because of the short "
               "nights, or is it just the weather?",
               about="avg_hr", status="resolved",
               note="the sleep half is answered by the inference recorded the "
                    "same day; nothing here explains the weather half"),
        # Still open, and it is the athlete talking themselves out of a
        # symptom that is currently gating impact work.
        _entry((end - timedelta(days=4)).isoformat(), "worry",
               "The achilles is stiff first thing and I keep telling myself "
               "it eases once I am warm.",
               about="achilles", confidence=0.6),
        # THE ONE THAT EARNS THE DATASET. Said firmly, and the weigh-ins
        # disagree: the travel week has none at all, and the routine after it
        # is split between 07:00 and 19:00 - which is the same artifact that
        # makes the current rate unreadable. A record that held only the
        # numbers could show the gap; only this can show that the athlete
        # believes otherwise, which is the thing worth raising with them.
        _entry((end - timedelta(days=2)).isoformat(), "claim",
               "I weigh myself every morning, same time, before anything "
               "else.",
               about="kg", confidence=0.8),
    ], 22)


def _situational(start: date, end: date) -> tuple[list[dict], list[dict]]:
    """Context timeline (G34) + the sparse anchor reads (G16)."""
    context = [
        {"date": start.isoformat(), "mode": "normal",
         "facilities": "scale gym routes", "place": "home",
         "source": "onboard", "note": "baseline setup"},
        # The travel week, declared. This is what turns a missing weigh-in
        # from a lapse into a circumstance the engine can account for.
        {"date": (start + timedelta(days=49)).isoformat(), "mode": "travel",
         "facilities": "routes", "place": "away", "source": "athlete",
         "note": "work trip - no scale, no gym, hotel treadmill only"},
        {"date": (start + timedelta(days=56)).isoformat(), "mode": "normal",
         "facilities": "scale gym routes", "place": "home",
         "source": "athlete", "note": "home again"},
    ]
    measurements = [
        {"date": start.isoformat(), "kind": "waist_cm", "value": 92.0,
         "source": "tape", "note": "morning, unfasted"},
        {"date": (start + timedelta(days=42)).isoformat(), "kind": "waist_cm",
         "value": 89.5, "source": "tape", "note": None},
        {"date": end.isoformat(), "kind": "waist_cm", "value": 88.0,
         "source": "tape", "note": None},
        # An anchor-class read the scale cannot produce.
        {"date": (start + timedelta(days=42)).isoformat(), "kind": "body_fat_pct",
         "value": 22.4, "source": "dexa", "note": "clinic scan"},
    ]
    return context, measurements


def _read_all(root: Path) -> dict[str, str]:
    """The generated INPUTS only.

    Deliberately skips derived/: it is gitignored and holds a binary SQLite
    file, so a local `vitai build` before `--check` would otherwise blow up on
    a UTF-8 decode rather than reporting drift.
    """
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file() and "derived" not in p.parts
            # Tracks included (#64): the personal gate permits coordinates in
            # `examples/demo/tracks/` on the grounds that they are the
            # generator's own output, and that grounds is only true if they
            # are actually compared. They were not.
            and p.suffix in (".jsonl", ".toml", ".gpx", ".tcx")}


def main() -> int:
    if "--check" in sys.argv[1:]:
        tmp = Path(tempfile.mkdtemp()) / "demo"
        _build(tmp)
        want, got = _read_all(tmp), _read_all(DEMO)
        # compare only the generated inputs (vitai.toml + data/), not derived/
        # Tracks are included (#64): the personal gate permits coordinates in
        # `examples/demo/tracks/` on the grounds that they are the generator's
        # output, and that grounds is only true if they are actually compared.
        keys = {k for k in want} | {
            k for k in got
            if k.endswith((".jsonl", ".toml", ".gpx", ".tcx", ".fit"))}
        drift = [k for k in sorted(keys) if want.get(k) != got.get(k)]
        if drift:
            print(f"demo data DRIFTED from generator: {drift}", file=sys.stderr)
            print("run `python examples/generate_demo.py` and commit.", file=sys.stderr)
            return 1
        print("demo data matches the generator")
        return 0
    _build(DEMO)
    print(f"wrote {DEMO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
