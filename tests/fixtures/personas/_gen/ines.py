"""Generator for the ines persona (seed 110).

Porto, Portugal. 41, freelance translator, two young children, runs four
mornings a week before the house wakes up. Ten weeks, starting the week the
record itself starts.

THE AXIS SHE STRESSES IS THAT SHE HAS NO PAST. Every other persona in this
corpus began before some mechanism existed, so their early rows are silent
about things the schema could not yet express - and a null in those rows means
"the field did not exist yet" as often as it means "nobody said". Ines started
after all of it. Her nulls are the real kind, and the corpus had no record in
which that was true.

That makes her the control the other nine could not be. When an engine output
degrades on a persona with a long history, the corpus could not previously say
whether the cause was the history or the code; against a record where every
field was available from row one, it can.

Two things she carries that no other persona does.

TWO RPE SCALES IN ONE RECORD. Her watch exports Borg's 6-20 and the strength
app she types into uses CR10, so the same integer means two different efforts
in two datasets of one record - an easy run at 12 would read as near-maximal
on the other scale. Both declare, which is the case `rpe_scale` exists for and
which no other record can demonstrate.

A DAILY CEILING AND A DAILY FLOOR ON ONE NUTRIENT AXIS. She caps energy and
floors protein, both per day, which is the shape the nutrition work is built
around and the one that had nowhere to live before a daily period existed.

See `PROFILE.md`, `LIES.md`, `METRICS.md`, `FINDINGS.md` and `WORLD.md`
alongside this file for the prose these numbers have to agree with. Entirely
synthetic; any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 110
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

# INSIDE THE CORPUS WINDOW, like everyone else. "Born after the new schema" is
# a statement about GENERATIONS, not about the calendar: every row here is
# written at the current generation for its dataset, so her record carries no
# field that did not exist when it was written. Putting her in a later year
# would have made `generate.py`'s shared end date silently produce an empty
# record, which it did on the first attempt.
START = date(2030, 4, 21)
DEFAULT_END = date(2030, 6, 30)

_TOML = """# ines - Porto. Started the record after every mechanism existed.
[athlete]
timezone = "Europe/Lisbon"

[targets]
# An approach goal: she is not cutting or bulking, she is converging.
phases = [[64.0, 62.0, 0.15]]

[tripwires]
steps_floor = 6000
sleep_floor_h = 6.5

[resolution]
source_order = ["scale", "watch", "app", "hand"]
"""


def _weight(rng: random.Random, stamp: common.Stamper, end: date) -> list[dict]:
    """Weighs Monday and Thursday, always the same way, and says so.

    `protocol` is the point: she declared her procedure on the first line and
    kept it, so every reading in the record is comparable with every other by
    something the record states rather than something a reader assumes. No
    other persona can say that - theirs began before the field existed.
    """
    rows = []
    kg = 64.6
    for day in common.daterange(START, end):
        if day.weekday() not in (0, 3):
            continue
        kg = round(kg - rng.uniform(0.0, 0.09), 2)
        rows.append(common.record(
            "weight", date=day.isoformat(), kg=kg, source="scale",
            measured_at="06:40", protocol="fasted-post-void",
            origin="bathroom-scale", capture="ble", read_by=None,
            recorded_at=stamp.stamp(day)))
    # One reading she took at the gym on a different scale, after breakfast,
    # and labelled honestly. It disagrees by more than her week-to-week drift
    # and is the only row in her record that is not comparable with the rest.
    odd = START + timedelta(days=39)
    rows.append(common.record(
        "weight", date=odd.isoformat(), kg=65.8, source="hand",
        measured_at="18:05", protocol="fed-evening-clothed",
        origin="gym-scale", capture="manual_entry", read_by="athlete",
        note="the gym scale, after dinner, in clothes",
        recorded_at=stamp.stamp(odd)))
    return rows


def _daily(rng: random.Random, stamp: common.Stamper, end: date) -> list[dict]:
    """Logged from day one, with the scales declared.

    She logs food in an app that reports energy and protein, and rates mood
    and any niggle on a 0-10 clinical scale because her physiotherapist asked
    her to. Both say which scale, so a client can render "3 out of 10" without
    inventing the denominator.
    """
    rows = []
    for day in common.daterange(START, end):
        weekday = day.weekday()
        steps = int(rng.gauss(8200, 1500)) + (1800 if weekday < 4 else 0)
        # She eats under her cap most days and over it on Saturdays.
        kcal = int(rng.gauss(1980, 130)) + (420 if weekday == 5 else 0)
        protein = int(rng.gauss(118, 14))
        niggle = 2 if 24 <= (day - START).days <= 33 else 0
        rows.append(common.record(
            "daily", date=day.isoformat(), steps=max(2200, steps),
            distance_km=round(max(2.2, steps) * 0.00072, 1),
            active_min=int(rng.gauss(52, 12)),
            kcal_in=kcal, protein_g=protein,
            sleep_h=round(rng.gauss(6.9, 0.6), 1),
            rhr=int(rng.gauss(54, 3)),
            mood=max(1, min(10, int(rng.gauss(7, 1.2)))),
            mood_scale="nrs-0-10",
            pain=niggle, pain_site="achilles" if niggle else None,
            pain_side="left" if niggle else None,
            pain_scale="nrs-0-10" if niggle else None,
            coverage="full", source="app", origin="phone",
            capture="connector", recorded_at=stamp.stamp(day)))
    return rows


def _sessions(rng: random.Random, stamp: common.Stamper,
              end: date) -> tuple[list[dict], list[dict]]:
    """Four runs a week from a watch that reports RPE on Borg's 6-20.

    The scale matters here and nowhere else in the corpus: her strength app
    uses CR10, so the same integer means two different efforts depending on
    which dataset it is in. An easy run at 12 would read as near-maximal on
    the other scale. Both rows declare, which is the case `rpe_scale` exists
    for and which no other record can demonstrate - hers is the only one whose
    two sources genuinely differ.
    """
    rows, tracks = [], []
    for day in common.daterange(START, end):
        if day.weekday() not in (0, 2, 4, 6):
            continue
        n = (day - START).days
        km = round(rng.uniform(5.0, 7.5) + (3.0 if day.weekday() == 6 else 0), 2)
        secs = int(km * rng.uniform(320, 355))
        # Borg 6-20: her easy runs sit at 11-13, which on CR10 would read as
        # maximal. That is the whole reason the scale is declared.
        rpe = 15 if day.weekday() == 6 else rng.choice([11, 12, 13])
        track = None
        if day.weekday() == 6 and n < 30:
            track = f"tracks/long-{day.isoformat()}.gpx"
            tracks.append((track, day.isoformat(), secs))
        rows.append(common.record(
            "sessions", date=day.isoformat(), type="run", distance_km=km,
            duration_s=secs, avg_hr=int(rng.gauss(146, 7)),
            start_time=f"{day.isoformat()}T06:10:00+00:00",
            rpe=rpe, rpe_scale="borg-rpe-6-20",
            setting="outdoor", context="solo", source="watch",
            origin="running-watch", capture="connector",
            track=track, recorded_at=stamp.stamp(day)))
    return rows, tracks


def _sets(stamp: common.Stamper) -> list[dict]:
    """One strength session a week, typed into an app that uses CR10.

    The volitional case #244 is about: she stops because she judges she has
    nothing left, without starting a rep and failing it. `rir: 0` says she
    believed none were left; `failure: volitional` says she ended the set. It
    is not `muscular`, because nothing was tested.
    """
    rows = []
    for week in range(0, 10):
        day = START + timedelta(days=week * 7 + 1)
        for index, (reps, load) in enumerate(
                ((10, 30.0), (8, 35.0), (6, 40.0)), start=1):
            rows.append(common.record(
                "sets", date=day.isoformat(),
                session_start=f"{day.isoformat()}T19:30:00+00:00",
                exercise="goblet-squat", block=1, set_index=index,
                reps_completed=reps, reps_attempted=reps,
                load=load, load_type="external", load_unit="kg",
                set_type="working",
                failure="volitional" if index == 3 else None,
                rir=0 if index == 3 else 2,
                rpe=8 if index == 3 else 6, rpe_scale="borg-cr10",
                equipment="kettlebell", source="app", origin="phone",
                capture="manual_entry", read_by="athlete",
                recorded_at=stamp.stamp(day)))
    return rows


def _goals(stamp: common.Stamper) -> list[dict]:
    """Four goals, and three of them could not have been stated before.

    A daily energy CEILING and a daily protein FLOOR on one axis; a weight
    goal she is APPROACHING rather than counting up to; and a step floor she
    reached in week three and has held since, which is `sustaining` - a state
    that had nowhere to live while `achieved` was terminal.
    """
    d0 = START.isoformat()
    return [
        common.record(
            "goals", date=d0, slug="energy-cap",
            title="Stay under 2200 kcal on a weekday", metric="kcal_in",
            dataset="daily", target=2200, polarity="ceiling", period="daily",
            policy="monotonic", tracker="sum", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="I want the trousers I already own to fit",
            rationale="about 300 under what I seem to eat when I do not think",
            on_success="hold", on_miss="reflect", recorded_at=stamp.stamp(START)),
        common.record(
            "goals", date=d0, slug="protein-floor",
            title="At least 110 g of protein a day", metric="protein_g",
            dataset="daily", target=110, polarity="floor", period="daily",
            policy="monotonic", tracker="sum", lifecycle_status="active",
            verification="measured", set_by="athlete",
            motivator="so the running does not eat the muscle",
            rationale="my own number, not a guideline - it is what I can hit",
            on_success="hold", on_miss="reflect", recorded_at=stamp.stamp(START)),
        common.record(
            "goals", date=d0, slug="settle-at-62",
            title="Settle at 62 kg and stay there", metric="kg",
            dataset="weight", target=62.0, polarity="approach", period="none",
            policy="monotonic", lifecycle_status="active",
            verification="measured", set_by="athlete",
            deadline=None, motivator="I have been up and down this range for years",
            rationale="converging, from either side - not a cut",
            on_success="hold", on_miss="reflect", recorded_at=stamp.stamp(START)),
        common.record(
            "goals", date=(START + timedelta(days=21)).isoformat(),
            slug="daily-steps", title="Keep 8000 steps a day", metric="steps",
            dataset="daily", target=8000, polarity="floor", period="daily",
            policy="monotonic", tracker="sum", lifecycle_status="completed",
            verification="measured", set_by="athlete",
            motivator="the school run does most of it already",
            rationale="reached it in week three; the point now is not to lose it",
            on_success="hold", on_miss="reflect",
            recorded_at=stamp.stamp(START + timedelta(days=21))),
    ]


def _journal(stamp: common.Stamper) -> list[dict]:
    day = START + timedelta(days=28)
    return [
        common.record(
            "journal", date=day.isoformat(), kind="claim",
            text="the achilles thing is nothing, it goes once I am warm",
            about="left achilles", source="athlete",
            recorded_at=stamp.stamp(day)),
        common.record(
            "journal", date=(START + timedelta(days=41)).isoformat(),
            kind="preference",
            text="I run before the children are up or I do not run",
            source="athlete",
            recorded_at=stamp.stamp(START + timedelta(days=41))),
    ]


def _expectations() -> list[dict]:
    return [
        {"id": "ines-E1", "kind": "gap", "dataset": "sessions",
         "dates": [], "claim":
             "her runs carry rpe 11-13 and her sets carry rpe 6-8",
         "truth":
             "the runs are on Borg 6-20 and the sets on CR10; both rows say "
             "which, so 12 on a run is an easy effort and 8 on a set is a "
             "hard one",
         "expect":
             "nothing may compare an rpe across the two datasets without "
             "reading `rpe_scale` first, and nothing may render either as a "
             "fraction of ten. A consumer that pools them produces a mean of "
             "two different quantities - which is exactly what every record "
             "in this corpus would have done before the scale could be "
             "stated, and why she is the only persona who can demonstrate it",
         "gap": "none in the engine: each value is validated against its "
                "declared scale. The gap is in any consumer that pools them, "
                "and she is the only record that can demonstrate it"},
        {"id": "ines-E2", "kind": "gap", "dataset": "weight",
         "dates": [(START + timedelta(days=39)).isoformat()],
         "claim": "a 65.8 kg reading, 1.4 kg above the trend",
         "truth":
             "taken on a different scale, after dinner, in clothes, and "
             "labelled `fed-evening-clothed` while every other reading is "
             "`fasted-post-void`",
         "expect":
             "the reading is not an error and must not be dropped, and it is "
             "also not comparable with the rest. The protocol is stated, so "
             "an engine reading it has everything it needs to say so rather "
             "than to average it in",
         "gap": "protocol is recorded and validated; nothing yet groups a "
                "trend by it, so the row still enters the weekly mean"},
        {"id": "ines-E3", "kind": "gap", "dataset": "goals",
         "dates": [(START + timedelta(days=21)).isoformat()],
         "claim": "a completed step goal she is still meeting",
         "truth":
             "she reached 8000 steps a day in week three and has held it, "
             "which is `sustaining` rather than `achieved`",
         "expect":
             "a completed goal keeps being measured so the holding is "
             "visible, and mints no milestone for holding it",
         "gap": "none: this is the state the lifecycle/achievement split "
                "exists for, and she is the fixture that exercises it from "
                "the day the goal was declared rather than retrofitted"},
        {"id": "ines-E4", "kind": "gap", "dataset": "daily",
         "dates": [], "claim":
             "every null in this record means nobody said",
         "truth":
             "she started after every mechanism existed, so no null here is "
             "the schema having been narrower at the time",
         "expect":
             "this is the control the other nine cannot be. Where an output "
             "degrades on a persona with a long history, the corpus can now "
             "ask whether the cause was the history or the code by running "
             "the same question against a record with no legacy at all",
         "gap": "none: this expectation exists to be cited by other "
                "personas' findings rather than to fail on its own"},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight = _weight(rng, common.Stamper(base_hour=7), end)
    daily = _daily(rng, common.Stamper(base_hour=21), end)
    sessions, tracks = _sessions(rng, common.Stamper(base_hour=7), end)
    sets = _sets(common.Stamper(base_hour=20))
    goals = _goals(common.Stamper(base_hour=9))
    journal = _journal(common.Stamper(base_hour=22))

    files: dict[str, str] = {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/sets.jsonl": common.jsonl_text(common.sort_rows(sets)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "expectations.jsonl": common.jsonl_text(_expectations()),
        "persona.toml": common.persona_toml(
            "ines", PERSONA_VERSION, SEED,
            (START.isoformat(), end.isoformat())),
    }
    for ref, day, secs in tracks:
        files[ref] = common.gpx_text(day, "06:10", secs, name="long run")
    return files
