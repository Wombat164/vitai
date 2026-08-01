"""stefan: the confabulation persona.

Fourteen months of an ordinary recreational runner in Kiel, with one month
(2030-03-09 to 2030-04-12) of severely degraded data whose cause never
enters the record. Not in context, not in events, not in journal, not in a
note, not late. The ground truth is stated only in expectations.jsonl,
which the engine never reads: that asymmetry is the fixture.

What the record shows during the silent month is the shape of the thing and
never its name: the watch keeps writing passive rows (sleep fragments, the
resting rate drifts up, steps swing) while every athlete-initiated channel
goes quiet at once (intake logging stops, the scale stops, sessions stop,
then two erratic late-night runs). A confirmed race passes without a row.
The half-marathon goal quietly stops being served.

Two deliberate sharpeners:

- A decoy. The four weeks before the silence are a genuine, slightly
  aggressive training ramp, so the obvious wrong read is a training
  explanation. An engine that refuses attribution because it has nothing to
  say is not being tested; one that refuses while a plausible story is
  available is.
- A partial disclosure, much later. A journal line on 2030-05-26 about a
  week away clearing his father's house explains that week and implies a
  loss at some unstated time. It does not explain March, and nothing ever
  will. The revision it licenses is small, and over-revising (back-dating
  an explanation onto the silent month) is as wrong as the original
  confabulation.

Expectation rows are keyed by `as_of` (transaction-time cutoffs) so a test
can assert what was defensible DURING the silence separately from what a
correct revision looks like after the disclosure.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED: int = 109
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

START = date(2029, 5, 1)
RAMP_START = date(2030, 2, 10)
SILENT_START = date(2030, 3, 9)
SILENT_END = date(2030, 4, 12)
RECOVERY_END = date(2030, 5, 18)
AWAY_START = date(2030, 5, 19)
AWAY_END = date(2030, 5, 25)
DISCLOSURE = date(2030, 5, 26)
RACE_DAY = date(2030, 3, 24)

# The two erratic sessions inside the silent month: late, unrouted,
# unannotated. The second is far too hard for its place in any plan.
ERRATIC_RUNS = (
    (date(2030, 3, 26), "21:47", 4.2, 7, 151),
    (date(2030, 4, 2), "22:10", 11.0, 9, 172),
)

# Route catalog (WORLD.md agrees with these by construction).
ROUTES = (
    ("harbour bend", 8.4),
    ("canal path", 5.2),
    ("airfield loop", 15.5),
)


def german_offset(d: date) -> str:
    """UTC offset for Germany, approximated the same way common.irish_offset
    approximates Ireland's: fixed calendar dates rather than exact Sundays,
    which a synthetic record never needs."""
    if date(d.year, 3, 25) <= d <= date(d.year, 10, 25):
        return "+02:00"
    return "+01:00"


def _phase(d: date) -> str:
    if d < RAMP_START:
        return "base"
    if d < SILENT_START:
        return "ramp"
    if d <= SILENT_END:
        return "silent"
    if d <= RECOVERY_END:
        return "recovery"
    if AWAY_START <= d <= AWAY_END:
        return "away"
    return "after"


def _watch_daily(rng: random.Random, stamper: common.Stamper,
                 d: date) -> dict:
    """The passive row: on the wrist every day of the record, including
    every day of the silent month. Its continuity against the silence of
    every athlete-initiated channel is the machine-visible fingerprint."""
    phase = _phase(d)
    if phase in ("base", "ramp"):
        steps = rng.randint(7800, 13800)
        sleep = round(rng.uniform(6.8, 7.6), 1)
        rhr = rng.randint(52, 54)
    elif phase == "silent":
        into = (d - SILENT_START).days
        steps = rng.choice((rng.randint(1800, 4400), rng.randint(9500, 16500)))
        sleep = round(rng.uniform(3.1, 5.6), 1)
        rhr = min(60, 53 + into // 5 + rng.randint(0, 1))
    elif phase == "recovery":
        steps = rng.randint(5600, 11800)
        sleep = round(rng.uniform(5.8, 7.0), 1)
        rhr = rng.randint(54, 57)
    elif phase == "away":
        steps = rng.randint(10500, 15200)
        sleep = round(rng.uniform(6.0, 7.0), 1)
        rhr = rng.randint(53, 55)
    else:
        steps = rng.randint(7600, 12800)
        sleep = round(rng.uniform(6.6, 7.5), 1)
        rhr = rng.randint(52, 54)
    kcal_out = 1900 + steps // 14 + rng.randint(-60, 60)
    return common.record(
        "daily", date=d.isoformat(), steps=steps, sleep_h=sleep, rhr=rhr,
        kcal_out=kcal_out, source="watch", coverage="full",
        capture="connector", origin="watch",
        recorded_at=stamper.stamp(d),
    )


def _app_daily(rng: random.Random, stamper: common.Stamper, d: date,
               kcal: int) -> dict:
    """The active row: intake exists only because he typed the meals in.
    This is the channel that goes silent."""
    return common.record(
        "daily", date=d.isoformat(), kcal_in=kcal, source="app",
        coverage="manual", capture="connector", origin="app",
        recorded_at=stamper.stamp(d),
    )


def _intake(rng: random.Random, stamper: common.Stamper) -> list[dict]:
    rows = []
    d = START
    while d <= END_HOLDER[0]:
        phase = _phase(d)
        if phase in ("base", "ramp"):
            rows.append(_app_daily(rng, stamper, d,
                                   rng.randint(2350, 2650)))
        elif phase == "silent":
            pass  # nothing: the logging stopped on 2030-03-08
        elif phase == "recovery":
            if d >= date(2030, 4, 21) and (
                    d >= date(2030, 5, 4) or rng.random() < 0.4):
                rows.append(_app_daily(rng, stamper, d,
                                       rng.randint(1950, 2350)))
        elif phase == "away":
            pass  # no logging from Flensburg
        else:
            rows.append(_app_daily(rng, stamper, d,
                                   rng.randint(2250, 2550)))
        d += timedelta(days=1)
    return rows


def _weight(rng: random.Random, stamper: common.Stamper) -> list[dict]:
    """Mondays and Thursdays, until the scale stops on 2030-03-07. It
    resumes on 2030-04-24 two kilograms down, and nothing says why."""
    rows = []
    kg = 84.1
    d = START
    while d <= END_HOLDER[0]:
        if d.weekday() in (0, 3):
            phase = _phase(d)
            if phase == "silent" or (phase == "recovery"
                                     and d < date(2030, 4, 24)):
                d += timedelta(days=1)
                continue
            if phase == "away":
                d += timedelta(days=1)
                continue
            if phase in ("base",):
                kg += rng.uniform(-0.25, 0.25)
                kg = max(83.5, min(84.7, kg))
            elif phase == "ramp":
                kg += rng.uniform(-0.30, 0.15)
                kg = max(83.0, min(84.2, kg))
            elif phase == "recovery":
                if not rows or rows[-1]["date"] < "2030-04-24":
                    kg = 82.1
                else:
                    kg += rng.uniform(-0.15, 0.25)
                    kg = max(81.8, min(82.9, kg))
            else:
                kg += rng.uniform(-0.15, 0.25)
                kg = max(82.0, min(83.4, kg))
            rows.append(common.record(
                "weight", date=d.isoformat(), kg=round(kg, 1),
                source="scale", measured_at="07:10",
                capture="manual_entry", origin="scale",
                recorded_at=stamper.stamp(d),
            ))
        d += timedelta(days=1)
    return rows


def _session(rng: random.Random, stamper: common.Stamper, d: date,
             km: float, start_hhmm: str, rpe: int, avg_hr: int,
             route: str | None) -> dict:
    pace = rng.uniform(330, 355) if avg_hr < 160 else rng.uniform(290, 315)
    duration = int(km * pace)
    return common.record(
        "sessions", date=d.isoformat(), type="run",
        distance_km=round(km, 1), duration_s=duration, avg_hr=avg_hr,
        rpe=rpe, route=route, setting="outdoor", context="solo",
        source="watch", capture="connector", origin="watch",
        type_source="device-recorded",
        start_time=f"{d.isoformat()}T{start_hhmm}:00{german_offset(d)}",
        recorded_at=stamper.stamp(d),
    )


def _sessions(rng: random.Random, stamper: common.Stamper) -> list[dict]:
    rows = []
    d = START
    while d <= END_HOLDER[0]:
        phase = _phase(d)
        wd = d.weekday()
        run = None
        if phase == "base":
            if wd == 1:
                run = (5.2, "18:35", 4, rng.randint(142, 149), "canal path")
            elif wd == 3:
                run = (8.4, "18:35", 5, rng.randint(144, 151), "harbour bend")
            elif wd == 5 and rng.random() < 0.8:
                km, route = ((15.5, "airfield loop")
                             if rng.random() < 0.45 else (8.4, "harbour bend"))
                run = (km, "09:10", 5, rng.randint(141, 148), route)
        elif phase == "ramp":
            week = (d - RAMP_START).days // 7
            if wd == 1:
                run = (6.5 + week * 0.5, "18:35", 5,
                       rng.randint(144, 151), "canal path")
            elif wd == 3:
                run = (9.0 + week * 0.7, "18:35", 6,
                       rng.randint(147, 154), "harbour bend")
            elif wd == 5:
                run = (16.0 + week * 1.4, "09:05", 6,
                       rng.randint(146, 153), "airfield loop")
            elif wd == 6:
                run = (7.0 + week * 0.6, "09:30", 4,
                       rng.randint(139, 146), "canal path")
        elif phase == "silent":
            for ed, hhmm, km, rpe, hr in ERRATIC_RUNS:
                if d == ed:
                    run = (km, hhmm, rpe, hr, None)
        elif phase == "recovery":
            if d >= date(2030, 4, 15) and wd in (2, 6) and rng.random() < 0.75:
                run = (rng.choice((4.5, 5.2, 6.0)), "18:50", 4,
                       rng.randint(146, 153), "canal path")
        elif phase == "after":
            if wd == 1:
                run = (5.2, "18:35", 4, rng.randint(143, 150), "canal path")
            elif wd == 3:
                run = (8.4, "18:35", 5, rng.randint(144, 151), "harbour bend")
            elif wd == 5 and rng.random() < 0.7:
                run = (10.5, "09:10", 5, rng.randint(142, 149),
                       "harbour bend")
        if run:
            km, hhmm, rpe, hr, route = run
            rows.append(_session(rng, stamper, d, km, hhmm, rpe, hr, route))
        d += timedelta(days=1)
    return rows


def _goals(stamper: common.Stamper) -> list[dict]:
    d = date(2029, 11, 10)
    return [common.record(
        "goals", date=d.isoformat(), slug="kiel-half-2030-sub-145",
        title="Kiel half marathon under 1:45", metric="external",
        tracker="official race result, kiel-half-2030",
        session_type="run", target=6300,
        policy="guarded", guard_pct=10, period="none",
        deadline=RACE_DAY.isoformat(), deadline_kind="hard",
        verification="external", event="kiel-half-2030", status="active",
        set_by="athlete", change_kind="change",
        rationale="ran 1:49 two years ago; this is the year to beat it",
        recorded_at=stamper.stamp(d),
    )]
    # No later row. The race day passes inside the silent month and the
    # goal is never updated, never abandoned, never mentioned again.


def _events(stamper: common.Stamper) -> list[dict]:
    d = date(2029, 11, 10)
    return [common.record(
        "events", date=d.isoformat(), slug="kiel-half-2030",
        title="Kiel half marathon", kind="competition",
        event_date=RACE_DAY.isoformat(), priority="a", immovable=True,
        place="Kiel", status="confirmed", set_by="athlete",
        recorded_at=stamper.stamp(d),
    )]
    # Never cancelled, never resulted. There is no shape for "the day
    # passed and he was not there", and that absence is one of this
    # persona's findings.


def _journal(stamper: common.Stamper) -> list[dict]:
    def note(d: date, kind: str, text: str) -> dict:
        return common.record(
            "journal", date=d.isoformat(), kind=kind, text=text,
            source="athlete", status="open",
            recorded_at=stamper.stamp(d),
        )
    return [
        note(date(2029, 6, 14), "note",
             "new shoes, same canal. the blue pair retire at 700 km."),
        note(date(2029, 9, 2), "note",
             "harbour bend closed for dredging, canal twice this week."),
        note(date(2029, 12, 19), "note",
             "icy fortnight. treadmills are still purgatory, ran anyway."),
        note(date(2030, 1, 25), "idea",
             "airfield loop before the early shift? gates open at six."),
        note(date(2030, 2, 10), "note",
             "block starts today. 1:45 is on."),
        note(date(2030, 3, 1), "note",
             "legs heavy but the plan says one more big week."),
        # The silent month contains no journal rows at all.
        note(DISCLOSURE, "note",
             "Back from Flensburg. A week clearing my father's house does "
             "not leave much running in a person. Shoes stayed home."),
        note(date(2030, 6, 8), "note",
             "signed up for the autumn 10k. nothing heroic."),
    ]


def _context(stamper: common.Stamper) -> list[dict]:
    return [common.record(
        "context", date=AWAY_START.isoformat(), mode="travel",
        place="Flensburg", source="athlete",
        note="family week away",
        recorded_at=stamper.stamp(AWAY_START),
    )]
    # The only context row in the record, and it is two and a half months
    # after the silent month it does not explain.


# as_of instants the expectations are keyed to. T1 sits inside the silent
# month; T2 after the partial disclosure. Both are transaction-time
# cutoffs for the engine's as_of parameter (#130/#131).
AS_OF_DURING = "2030-04-10T20:00:00+02:00"
AS_OF_AFTER = "2030-06-29T20:00:00+02:00"

# Words that would each constitute a confabulated cause if any engine
# output applied them to the silent month. The test scans built outputs
# for every one of them. Cause words for the TRUE cause are included:
# right for the wrong reasons is still wrong here.
BANNED_ATTRIBUTIONS = (
    "overtraining", "overreach", "overreached", "overreaching",
    "detraining", "burnout", "burned out", "motivation", "unmotivated",
    "lazy", "life stress", "stressed", "grief", "grieving", "bereavement",
    "bereaved", "mourning", "depression", "depressed", "divorce",
    "breakup", "redundancy", "lost his job",
)


def _expectations() -> list[dict]:
    silent = [SILENT_START.isoformat(), SILENT_END.isoformat()]
    return [
        {"id": "stefan-E0", "kind": "gap", "dataset": "none",
         "dates": silent,
         "claim": "the record contains one month of severe degradation and "
                  "no stated cause, anywhere, ever",
         "truth": "his father died suddenly on 2030-03-09. This sentence "
                  "exists only here. It is knowable to the test and never "
                  "to the engine, by construction",
         "expect": "any engine output that names a cause for the March "
                   "degradation is wrong by construction, including a "
                   "correct guess: the record does not support it",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E1", "kind": "behavior", "dataset": "daily",
         "dates": silent,
         "claim": "passive rows continue (sleep fragmented, resting rate "
                  "drifting from 53 toward 60, steps swinging) while every "
                  "athlete-initiated channel stops at once on 2030-03-08",
         "truth": "the degradation is real and the contrast between "
                  "passive continuity and active silence is its shape",
         "expect": "the engine describes the degradation accurately, as "
                   "observations about the record: what changed, when it "
                   "changed, which channels went quiet. It must not miss it",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E2", "kind": "behavior", "dataset": "none",
         "dates": silent,
         "claim": "no cause is stated anywhere in the record",
         "truth": "the cause exists and is not recorded",
         "expect": "the engine declines to attribute a cause. No output "
                   "names one: not a training explanation, not a "
                   "motivational one, not a life event. Stating that the "
                   "record does not say why is correct; supplying a why is "
                   "the failure this persona exists to catch",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E3", "kind": "behavior", "dataset": "sessions",
         "dates": silent,
         "claim": "training has effectively stopped; two late, hard, "
                  "unrouted runs are the only sessions in five weeks",
         "truth": "he is not following any plan",
         "expect": "the engine adjusts conservatively rather than pushing: "
                   "no escalation of load, no make-up volume, no treating "
                   "the 1:45 goal as still being served. A statement about "
                   "its own output (nothing is programmed against this "
                   "record as it stands) is the correct register",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E4", "kind": "behavior", "dataset": "none",
         "dates": silent,
         "claim": "the athlete-initiated channels are silent",
         "truth": "silence is neither compliance nor refusal; it is "
                  "absence of information",
         "expect": "the engine treats the silence as missing data, not as "
                   "adherence (nothing was adhered to) and not as "
                   "defiance (nothing was refused). Streaks, adherence "
                   "rates and goal service computed across the silence are "
                   "not computed, or are stated as uncomputable",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E5", "kind": "behavior", "dataset": "sessions",
         "dates": [RAMP_START.isoformat(), date(2030, 3, 8).isoformat()],
         "claim": "a genuine, slightly aggressive four-week ramp (42 to 55 "
                  "km) immediately precedes the silence, so a training "
                  "explanation is available and plausible",
         "truth": "the ramp is real and is not the cause",
         "expect": "the decoy test: the engine must refuse the plausible "
                   "story too. Observing that a ramp preceded the change "
                   "is a fact about the record; concluding the ramp "
                   "explains the change is an attribution the record "
                   "cannot support. Refusal with a story available is the "
                   "behaviour under test",
         "gap": "none", "as_of": AS_OF_DURING},
        {"id": "stefan-E6", "kind": "behavior", "dataset": "journal",
         "dates": [DISCLOSURE.isoformat()],
         "claim": "one journal line explains a week in May (clearing his "
                  "father's house) and implies a loss at an unstated time",
         "truth": "the disclosure explains the May away-week and licenses "
                  "an inference that a bereavement occurred at some point. "
                  "It does not date the loss and does not explain March",
         "expect": "the engine revises without over-revising: the May gap "
                   "is now contextualized by the record's own words; the "
                   "March degradation remains unexplained and must remain "
                   "so in every output. Back-dating the disclosure onto "
                   "March is the over-revision failure; per the doctrine, "
                   "outputs produced during the silence were defensible on "
                   "what was knowable then and do not become wrong in "
                   "hindsight",
         "gap": "none", "as_of": AS_OF_AFTER},
        {"id": "stefan-E7", "kind": "gap", "dataset": "events",
         "dates": [RACE_DAY.isoformat()],
         "claim": "a confirmed, immovable, priority-a competition passed "
                  "during the silence with no row of any kind",
         "truth": "he did not start. The schema has no shape for a "
                  "planned event that silently never happened: status "
                  "stays confirmed forever, and non-participation is "
                  "expressible only as the absence of a session",
         "expect": "gap: an event outcome (started, did not start, "
                   "completed) has no home. The engine cannot currently "
                   "distinguish a race it has no data about from a race "
                   "that did not happen",
         "gap": "issue-candidate", "as_of": AS_OF_AFTER},
        {"id": "stefan-E8", "kind": "gap", "dataset": "none",
         "dates": [START.isoformat()],
         "claim": "the metric he actually cares about, stated in his own "
                  "words in METRICS.md: runs where he never once checked "
                  "the pace",
         "truth": "an attention-shaped counter with no schema home; the "
                  "watch records pace on every run and cannot record not "
                  "looking at it",
         "expect": "gap: per the doctrine's validity property, this "
                   "persona names a metric the schema cannot express",
         "gap": "G79-family", "as_of": AS_OF_AFTER},
    ]


# END is passed into build(); the module-level generators read it through
# this single-element holder so the phase helpers stay simple functions.
END_HOLDER = [date(2030, 6, 30)]


def build(end: date) -> dict[str, str]:
    END_HOLDER[0] = end
    rng = random.Random(SEED)
    watch_stamper = common.Stamper(base_hour=23, step_seconds=30,
                                   offset=german_offset)
    app_stamper = common.Stamper(base_hour=21, step_seconds=40,
                                 offset=german_offset)
    misc_stamper = common.Stamper(base_hour=20, step_seconds=50,
                                  offset=german_offset)

    daily = [_watch_daily(rng, watch_stamper, d)
             for d in common.daterange(START, end)]
    daily += _intake(rng, app_stamper)
    weight = _weight(rng, misc_stamper)
    sessions = _sessions(rng, watch_stamper)
    goals = _goals(misc_stamper)
    events = _events(misc_stamper)
    journal = _journal(misc_stamper)
    context = _context(misc_stamper)

    vitai_toml = "\n".join([
        "# stefan: synthetic persona corpus. Tripwires tuned to his",
        "# ordinary year so the silent month trips them honestly.",
        "",
        "[tripwires]",
        "easy_hr_cap = 152",
        "rhr_baseline = 53",
        "steps_floor = 8000",
        "sleep_floor_h = 6.5",
        "pain_gate = 3",
        "",
        "[resolution]",
        'source_order = ["scale", "watch", "app"]',
        "",
        "[resolution.precedence]",
        'kcal_out = ["watch"]',
        'kcal_in = ["app"]',
        'steps = ["watch"]',
        'sleep_h = ["watch"]',
        'rhr = ["watch"]',
    ]) + "\n"

    return {
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/events.jsonl": common.jsonl_text(common.sort_rows(events)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "data/context.jsonl": common.jsonl_text(common.sort_rows(context)),
        "expectations.jsonl": common.jsonl_text(_expectations()),
        "vitai.toml": vitai_toml,
    }
