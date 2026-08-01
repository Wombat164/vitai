"""Generator for the tom persona (seed 107).

Sheffield, UK. 53, taxi driver, BMI 36 at the record's start. Five years on a
paper notebook: a crash diet that works, a full regain, a second attempt that
gets abandoned, and a slow honest descent that finally sticks. See
`PROFILE.md`, `WORLD.md`, `METRICS.md`, `FINDINGS.md` and `LIES.md` alongside
this file for the prose this generator's numbers have to agree with. Entirely
synthetic; any resemblance to a real person is accidental and unintended.

`build(end)` returns a mapping from a repo-relative output path to the file
content that belongs there. It writes nothing itself - `generate.py` decides
whether that content lands on disk or is compared against what is already
committed.

Written and verified against installed `vitai 0.2.3` (see `_gen/common.py`
for the schema pin). Re-verify this generator against the handbook before
trusting its output once that version changes.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import common

SEED = 107
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

START = date(2025, 7, 1)
DEFAULT_END = date(2030, 6, 30)

# The regain-peak weigh-in (true) and the self-serving correction of it two
# weeks later (T3, LIES.md). Both dates are load-bearing constants: the
# generator uses them to place rows, the expectations reference them, and
# LIES.md quotes them.
PEAK_DATE = date(2027, 9, 27)
CORRECTION_DATE = date(2027, 10, 4)

# The arc's control points (LIES.md / PROFILE.md): 118 -> 104 (crash) ->
# 116.2 (full regain, the peak the correction targets) -> 108 -> 113 (second
# regain) -> the record's own end, wherever `--end` puts it, at 107. The
# final point is appended in `build()` because it depends on `end`.
CONTROL_BASE = [
    (START, 118.0),
    (date(2026, 3, 1), 104.0),
    (PEAK_DATE, 116.2),
    (date(2028, 12, 1), 108.0),
    (date(2029, 9, 30), 113.0),
]

# Nine notebook-transcription batches (LIES.md T1 backdrop, not itself a
# lie): (period_start, period_end, the day he actually typed that stretch
# up). Batches are contiguous and their transcribe dates strictly increase,
# which is what keeps file order and recorded_at order aligned once rows are
# sorted by date (see the note in `_weight`).
def _batches(end: date) -> list[tuple[date, date, date]]:
    return [
        (date(2025, 7, 1), date(2025, 12, 31), date(2026, 1, 10)),
        (date(2026, 1, 1), date(2026, 6, 30), date(2026, 8, 15)),
        (date(2026, 7, 1), date(2026, 12, 31), date(2027, 2, 1)),
        (date(2027, 1, 1), date(2027, 6, 30), date(2027, 9, 1)),
        (date(2027, 7, 1), date(2027, 12, 31), date(2028, 1, 15)),
        (date(2028, 1, 1), date(2028, 6, 30), date(2028, 9, 1)),
        (date(2028, 7, 1), date(2028, 12, 31), date(2029, 2, 1)),
        (date(2029, 1, 1), date(2029, 9, 30), date(2029, 11, 1)),
        (date(2029, 10, 1), end, min(date(2030, 6, 28), end)),
    ]


# The annual Benidorm fortnight (WORLD.md): no scale, no notebook, no
# reservoir, no pool. Five Septembers fall inside the record.
BENIDORM = [(date(y, 9, 5), date(y, 9, 18)) for y in range(2025, 2030)]


def _in_benidorm(d: date) -> bool:
    return any(w0 <= d <= w1 for w0, w1 in BENIDORM)


# Four knee flares (medical.jsonl symptom rows); each also pauses the Sunday
# reservoir walk for its window, which is why sessions.jsonl and
# medical.jsonl agree with each other without sharing a table.
FLARES = [
    ("knee-flare-2026-01", date(2026, 1, 5), date(2026, 1, 26),
     "cold snap and the knee's not happy about it, giving the reservoir a miss for a bit"),
    ("knee-flare-2027-02", date(2027, 2, 10), date(2027, 3, 3),
     "knee's swollen up again, laying off the Sunday loop till it settles"),
    ("knee-flare-2028-11", date(2028, 11, 5), date(2028, 11, 27),
     "knee's given out on him, in a right mood about it"),
    ("knee-flare-2029-06", date(2029, 6, 8), date(2029, 6, 29),
     "knee flared after a run of long shifts, resting it a couple of weeks"),
]

ROUTES = {"reservoir-loop": 4.8}

GOAL1_SLUG = "crash-diet-2025"
GOAL1_SET = date(2025, 7, 5)
GOAL1_DONE = date(2026, 3, 20)
GOAL2_SLUG = "regain-recovery-2027"
GOAL2_SET = CORRECTION_DATE
GOAL2_ABANDON = date(2028, 2, 18)
GOAL3_SLUG = "steady-2029"
GOAL3_SET = date(2029, 10, 5)

MED_DATE = date(2027, 3, 8)

JOURNAL_DATE = date(2029, 12, 20)


# --- shared arc math -----------------------------------------------------------


def _true_kg(d: date, control: list[tuple[date, float]], rng: random.Random) -> float:
    """The continuous ground-truth weight on day `d`: linear interpolation
    across the arc's control points, plus small day-to-day noise. The
    regain-peak date is pinned exactly (no noise) because LIES.md T3 needs a
    specific, undisputed true value for the row it targets."""
    if d == PEAK_DATE:
        return 116.2
    if d <= control[0][0]:
        base = control[0][1]
    elif d >= control[-1][0]:
        base = control[-1][1]
    else:
        base = control[-1][1]
        for (d0, v0), (d1, v1) in zip(control, control[1:]):
            if d0 <= d <= d1:
                frac = (d - d0).days / max(1, (d1 - d0).days)
                base = v0 + (v1 - v0) * frac
                break
    return base + rng.gauss(0, 0.35)


def _transcribe(true_kg: float, rng: random.Random) -> float:
    """LIES.md T1: the notebook-transcription rounding bias. 78% of the time
    he rounds to the nearest half-kilo, always down from a shifted value;
    the rest of the time he keeps a decimal but still shades it down. Both
    branches subtract enough before rounding that the result can never land
    at or above the true value - the bias is one-directional by
    construction, never a coin flip that happens to round up."""
    if rng.random() < 0.78:
        shifted = true_kg - rng.uniform(0.35, 0.85)
        return round(shifted * 2) / 2
    shifted = true_kg - rng.uniform(0.4, 0.9)
    return round(shifted, 1)


def _digit_stats(pairs: list[tuple[float, float]]) -> tuple[float, float, int]:
    """Measured (not asserted) statistics over the ordinary transcribed rows:
    the percentage ending in .0 or .5, and the mean (true - recorded) bias.
    Feeds `tom-E1` so the expectation quotes what the generator actually
    produced rather than the number LIES.md was drafted against."""
    n = len(pairs)
    ending = sum(1 for _, rec in pairs if round(rec * 10) % 5 == 0)
    bias = sum(true - rec for true, rec in pairs) / n
    return 100.0 * ending / n, bias, n


# --- weight ----------------------------------------------------------------------


def _weight(rng: random.Random, stamper: common.Stamper, end: date,
            control: list[tuple[date, float]]
            ) -> tuple[list[dict], list[tuple[float, float]], list[date]]:
    """~340 rows over five years: an irregular weigh-in gap (paper notebook,
    not a daily habit), skipping the annual Benidorm fortnight, transcribed
    into the file in nine date-ordered batches (see `_batches`). The
    regain-peak and its self-serving correction (T3) are folded into the
    same per-batch, date-ordered pass as everything else, which is what
    keeps `recorded_at` order matching file (date) order once
    `common.sort_rows` runs: both orderings agree because batch periods and
    batch transcribe-dates increase together, and within a batch this
    function stamps in ascending date order.
    """
    batches = _batches(end)
    dates: set[date] = set()
    d = START
    while d <= end:
        gap = max(2, min(10, round(rng.gauss(5.2, 2.0))))
        d = d + timedelta(days=gap)
        if d > end:
            break
        if _in_benidorm(d):
            continue
        dates.add(d)
    dates.add(PEAK_DATE)
    dates.add(CORRECTION_DATE)

    by_batch: dict[date, list[date]] = {}
    for d in sorted(dates):
        for p0, p1, t in batches:
            if p0 <= d <= p1:
                by_batch.setdefault(t, []).append(d)
                break

    rows: list[dict] = []
    stats_pairs: list[tuple[float, float]] = []
    for t in sorted(by_batch):
        for d in sorted(by_batch[t]):
            measured_at = f"{rng.choice([5, 6]):02d}:{rng.randrange(0, 59):02d}"
            if d == CORRECTION_DATE:
                fields = {
                    "date": d.isoformat(), "kg": 114.9, "source": "mechanical-scale",
                    "origin": "mechanical-scale", "capture": "manual_entry",
                    "note": "that reading was never right, scale must have been on the carpet",
                    "supersedes": f"{PEAK_DATE.isoformat()}/mechanical-scale",
                    "recorded_at": stamper.stamp(t),
                }
            elif d == PEAK_DATE:
                fields = {
                    "date": d.isoformat(), "kg": 116.2, "source": "mechanical-scale",
                    "measured_at": measured_at, "origin": "mechanical-scale",
                    "capture": "manual_entry", "recorded_at": stamper.stamp(t),
                }
            else:
                true_val = _true_kg(d, control, rng)
                recorded = _transcribe(true_val, rng)
                stats_pairs.append((true_val, recorded))
                fields = {
                    "date": d.isoformat(), "kg": recorded, "source": "mechanical-scale",
                    "measured_at": measured_at, "origin": "mechanical-scale",
                    "capture": "manual_entry", "recorded_at": stamper.stamp(t),
                }
            rows.append(common.record("weight", **fields))
    return rows, stats_pairs, sorted(dates)


# --- measurements ------------------------------------------------------------


def _measurements(rng: random.Random, stamper: common.Stamper, end: date,
                   control: list[tuple[date, float]]) -> list[dict]:
    """~30 waist-tape rows: the belt-hole truth he actually trusts (METRICS.md).
    Unlike weight, these are not rounded down or batch-transcribed - he logs
    them the evening he takes them, and the value is whatever the tape says."""
    rows = []
    d = START + timedelta(days=18)
    while d <= end:
        gap = max(35, min(110, round(rng.gauss(60, 20))))
        d = d + timedelta(days=gap)
        if d > end:
            break
        if _in_benidorm(d):
            continue
        true_val = _true_kg(d, control, rng)
        waist = round(40.0 + true_val * 0.72 + rng.gauss(0, 0.4), 1)
        fields = {
            "date": d.isoformat(), "kind": "waist_cm", "value": waist,
            "source": "tape-measure", "origin": "tape-measure",
            "capture": "manual_entry", "recorded_at": stamper.stamp(d),
        }
        rows.append(common.record("measurements", **fields))
    return rows


# --- sessions ------------------------------------------------------------------


def _reservoir_walk(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    duration_s = int(rng.uniform(65, 85) * 60)
    with_lin = rng.random() < 0.3
    fields = {
        "date": d.isoformat(), "type": "walk", "distance_km": ROUTES["reservoir-loop"],
        "duration_s": duration_s, "rpe": rng.choice([3, 4, 4, 5]),
        "source": "athlete",
        "start_time": f"{d.isoformat()}T09:{rng.randrange(0, 40):02d}:00{common.irish_offset(d)}",
        "setting": "outdoor", "route": "reservoir-loop", "place": "reservoir",
        "with": "Lin" if with_lin else None,
        "context": "family" if with_lin else "solo",
        "weather": rng.choice(["dry", "dry", "rain", "wind", "cold"]),
        "type_source": "athlete-stated", "capture": "manual_entry",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _pool_swim(rng: random.Random, stamper: common.Stamper, d: date) -> dict:
    duration_s = int(rng.uniform(20, 26) * 60)
    fields = {
        "date": d.isoformat(), "type": "swim", "distance_km": 0.5,
        "duration_s": duration_s, "rpe": rng.choice([2, 3, 3]),
        "note": "twenty lengths, leisure centre, quiet at that hour",
        "source": "athlete",
        "start_time": f"{d.isoformat()}T14:00:00{common.irish_offset(d)}",
        "setting": "indoor", "place": "leisure centre", "context": "solo",
        "type_source": "athlete-stated", "capture": "manual_entry",
        "recorded_at": stamper.stamp(d),
    }
    return common.record("sessions", **fields)


def _sessions(rng: random.Random, stamper: common.Stamper, end: date,
              flare_windows: list[tuple[date, date]]) -> list[dict]:
    """~120 walks and swims across five years: the reservoir loop on Sundays
    "when knee allows" (skipped during a flare window and roughly 70% of
    other Sundays too - he is not a man who walks every week), and a
    Thursday pool swim at the leisure centre. No device ever touches these
    rows (WORLD.md: he hates apps); both are athlete-stated, manual_entry.
    The walk to nursery with Jack is deliberately NOT a session row here -
    it lives only in METRICS.md (see FINDINGS.md on that gap)."""
    rows: list[dict] = []
    for d in common.daterange(START, end):
        if _in_benidorm(d):
            continue
        wd = d.weekday()
        if wd == 6:
            if any(f0 <= d <= f1 for f0, f1 in flare_windows):
                continue
            if rng.random() < 0.28:
                rows.append(_reservoir_walk(rng, stamper, d))
        elif wd == 3:
            if rng.random() < 0.20:
                rows.append(_pool_swim(rng, stamper, d))
    return rows


# --- daily -----------------------------------------------------------------------


_DAILY_NOTES = [
    (date(2025, 12, 25), {"note": "Christmas dinner then a nap, Lin says I "
                                  "ate like there was no tomorrow",
                          "alcohol": True}),
    (date(2026, 4, 12), {"note": "Kelly had the baby, a boy, Jack. Didn't "
                                 "leave the hospital car park for two "
                                 "hours, just sat there grinning."}),
    (date(2028, 11, 9), {"note": "knee's given out again, in a right mood "
                                 "about it", "mood": 2}),
    (date(2028, 12, 3), {"note": "fourteen of fourteen with the shopping, "
                                 "first time all year", "mood": 8}),
    (date(2029, 9, 2), {"note": "landed in Benidorm, feet up for a "
                                "fortnight, first pint at the airport bar",
                        "alcohol": True}),
    (date(2030, 1, 1), {"note": "new year, told Lin I'm not doing the "
                                "crash thing again, slow this time"}),
]


def _daily(stamper: common.Stamper) -> list[dict]:
    """Nearly absent, per PROFILE.md/WORLD.md: no wearable ever, so no
    steps, sleep_h or rhr anywhere in this dataset - just a handful of notes
    on days that mattered."""
    rows = []
    for d, extra in _DAILY_NOTES:
        fields = {"date": d.isoformat(), "source": "athlete", "capture": "manual_entry",
                   "recorded_at": stamper.stamp(d)}
        fields.update(extra)
        rows.append(common.record("daily", **fields))
    return rows


# --- medical -----------------------------------------------------------------------


def _medical(stamper: common.Stamper) -> list[dict]:
    rows = []
    rows.append(common.record(
        "medical", date=START.isoformat(), slug="knee", kind="state",
        title="Knees ache, right one worse - old wear from years on the cab",
        body_site="knee", severity="moderate", status="active",
        restricts="impact", restriction="pattern=jump region=knee load=loaded",
        provider_type="gp", source="athlete",
        note=("years in and out of the car; the GP calls it wear and tear, "
              "nothing for it but not to overdo the impact"),
        onset_date="2010-01-01", recorded_at=stamper.stamp(START)))

    rows.append(common.record(
        "medical", date=MED_DATE.isoformat(), slug="bp-medication", kind="medication",
        title="Started blood pressure tablets, GP-prescribed",
        severity="none", status="active", provider_type="gp", source="athlete",
        note=("doctor said the readings run lower on days he's been out "
              "walking, so a good home reading after a walk isn't him "
              "fixing anything"),
        onset_date=MED_DATE.isoformat(), recorded_at=stamper.stamp(MED_DATE)))

    for slug, onset, resolved, note in FLARES:
        rows.append(common.record(
            "medical", date=onset.isoformat(), slug=slug, kind="symptom",
            title="Knee flare, reservoir walks paused", body_site="knee",
            severity="mild", status="resolved", resolved_date=resolved.isoformat(),
            restricts="impact", source="athlete", note=note,
            onset_date=onset.isoformat(), recorded_at=stamper.stamp(onset)))
    return rows


# --- goals ---------------------------------------------------------------------


def _goals(stamper: common.Stamper) -> tuple[list[dict], list[date]]:
    """Three eras (PROFILE.md/FINDINGS.md): a hard-deadline crash goal that
    is achieved and never reopened despite the regain that follows it; a
    2027 recovery goal that is later marked abandoned even though its
    target is in fact crossed the following year by other means; and a
    guarded, modest, still-active goal from the point the descent turns
    honest. Status changes are plain dated CHANGE rows (no supersedes) -
    both lines of each pair stay, and the pair is the audit trail."""
    def _goal_row(**kw) -> dict:
        # `common.record`'s own first parameter is named `dataset` (which
        # TABLE this row belongs to), which collides by name with the
        # `goals` schema's OWN `dataset` field (which dataset the goal's
        # metric lives in). Pop the schema field out, build the skeleton,
        # then set it directly on the resulting dict to sidestep the clash.
        goal_dataset = kw.pop("dataset", None)
        rec = common.record("goals", **kw)
        rec["dataset"] = goal_dataset
        return rec

    rows = []
    common_fields = dict(
        title="Get down under 108 kg", metric="kg", dataset="weight", target=108.0,
        policy="monotonic", period="none", deadline="2026-03-31", deadline_kind="hard",
        motivator="the letter after the works health check",
        rationale="a hard number to aim at by a hard date, not an open-ended rate",
        set_by="athlete", verification="measured")
    rows.append(_goal_row(date=GOAL1_SET.isoformat(), slug=GOAL1_SLUG,
                           status="active", recorded_at=stamper.stamp(GOAL1_SET),
                           **common_fields))
    rows.append(_goal_row(date=GOAL1_DONE.isoformat(), slug=GOAL1_SLUG,
                           status="achieved", recorded_at=stamper.stamp(GOAL1_DONE),
                           **common_fields))

    common_fields2 = dict(
        title="Back under 110 by the summer", metric="kg", dataset="weight", target=110.0,
        policy="monotonic", period="none", deadline="2028-06-30", deadline_kind="soft",
        motivator="the regain scared him more than the doctor did",
        rationale="pick a date this time instead of an open-ended thing",
        set_by="athlete", verification="measured")
    rows.append(_goal_row(date=GOAL2_SET.isoformat(), slug=GOAL2_SLUG,
                           status="active", recorded_at=stamper.stamp(GOAL2_SET),
                           **common_fields2))
    rows.append(_goal_row(date=GOAL2_ABANDON.isoformat(), slug=GOAL2_SLUG,
                           status="abandoned",
                           reason="gave up on hitting a date, kept walking anyway",
                           recorded_at=stamper.stamp(GOAL2_ABANDON), **common_fields2))

    rows.append(_goal_row(
        date=GOAL3_SET.isoformat(), slug=GOAL3_SLUG,
        title="Half a kilo a month, no crash this time", metric="kg", dataset="weight",
        target=100.0, policy="guarded", guard_pct=15, period="monthly",
        on_period_end="carry", status="active",
        motivator="Lin said if he crashed again she'd hide the scale",
        rationale="slow enough this time that a regain has nowhere to come from",
        set_by="athlete", verification="measured",
        recorded_at=stamper.stamp(GOAL3_SET)))

    return rows, [GOAL1_SET, GOAL1_DONE, GOAL2_SET, GOAL2_ABANDON, GOAL3_SET]


# --- journal -----------------------------------------------------------------------


def _journal(stamper: common.Stamper) -> list[dict]:
    """LIES.md T2: a single, unfalsifiable claim. No kcal or intake dataset
    exists for tom at all, so there is no fingerprint anywhere in the
    record that could corroborate or contradict it - the point of this row
    is that the engine has nothing to check it against."""
    fields = {
        "date": JOURNAL_DATE.isoformat(), "kind": "claim",
        "text": ("Six weeks now, not been near that machine at the rank. "
                 "Feels like it's finally stuck this time."),
        "about": "vending-machine streak", "source": "athlete",
        "confidence": 0.85, "status": "open",
        "recorded_at": stamper.stamp(JOURNAL_DATE),
    }
    return [common.record("journal", **fields)]


# --- expectations (ground truth; not read by the engine) -------------------------


def _e1_digit_preference(pct: float, bias: float, n: int, weigh_dates: list[date]) -> dict:
    return {
        "id": "tom-E1", "kind": "lie", "dataset": "weight",
        "dates": [weigh_dates[0].isoformat(), weigh_dates[-1].isoformat()],
        "claim": (f"across {n} ordinary notebook weigh-ins, {pct:.0f}% of the "
                  "recorded values end in .0 or .5"),
        "truth": (f"the underlying continuous readings do not cluster there; "
                  f"transcribed values run on average {bias:.2f} kg below the "
                  "true value, always downward, by construction never upward"),
        "expect": ("a terminal-digit distribution test on weight.jsonl should "
                   "be able to flag this as a rounding/digit-preference "
                   "pattern; because the bias is one-directional and roughly "
                   "constant, a RATE estimate (kg per week) stays close to "
                   "unbiased, but a LEVEL estimate (today's kg) reads "
                   "slightly light; the engine should treat this as a "
                   "distribution observation about the record, never as "
                   "evidence he is lighter than the scale actually said"),
        "gap": "G-tom-1: vitai has no terminal-digit or rounding-bias check today",
    }


def _e2_vending_streak() -> dict:
    return {
        "id": "tom-E2", "kind": "gap", "dataset": "journal",
        "dates": [JOURNAL_DATE.isoformat()],
        "claim": "a journal claim states six weeks without the vending machine",
        "truth": ("he broke the streak four times in that window; nothing "
                  "in the record says so because no intake or kcal dataset "
                  "exists for tom at all"),
        "expect": ("the engine should hold this as a claim (journal "
                   "kind=claim, status=open), never promote it to a fact "
                   "feeding any number or trend; there is no fingerprint to "
                   "check it against and the engine must not invent one"),
        "gap": "G-tom-5: an unfalsifiable claim with zero corroborating "
               "data anywhere in the record",
    }


def _e3_self_serving_correction() -> dict:
    return {
        "id": "tom-E3", "kind": "lie", "dataset": "weight",
        "dates": [PEAK_DATE.isoformat(), CORRECTION_DATE.isoformat()],
        "claim": ("a supersedes row dated 2027-10-04 corrects the "
                  "2027-09-27 weigh-in from 116.2 to 114.9, citing "
                  "'scale was on carpet'"),
        "truth": ("116.2 was the correct reading; nothing about the scale's "
                  "placement changed between the two entries; the correction "
                  "arrives on the very date the next loss attempt begins"),
        "expect": ("supersedes is honoured at face value - the corrected "
                   "value is what the record reports as current - but the "
                   "superseded row is preserved and remains quotable, never "
                   "deleted; a correction landing exactly at a trend "
                   "inflection, on the athlete's own most unflattering row, "
                   "is a pattern worth flagging as an audit signal (pairs "
                   "with marcus M2's guarded-ramp correction), even though "
                   "no such check exists today"),
        "gap": ("G-tom-2: correction-provenance auditing (a supersedes that "
                "improves an inconvenient reading, timed at an era "
                "boundary) is not implemented"),
    }


def _e4_goal_eras(goal_dates: list[date]) -> dict:
    return {
        "id": "tom-E4", "kind": "behavior", "dataset": "goals",
        "dates": [d.isoformat() for d in goal_dates],
        "claim": ("three goal eras across five years: a 2025 hard-deadline "
                  "crash goal reaching 'achieved' in 2026-03, a 2027 "
                  "recovery goal later marked 'abandoned', and a 2029 "
                  "modest guarded goal still active at the record's end"),
        "truth": ("the achieved goal is never reopened even though the "
                  "weight fully regains afterward; the abandoned goal's "
                  "target (under 110) is in fact crossed the following "
                  "year, just not through that goal"),
        "expect": ("goal status is its own lifecycle, independent of what "
                   "the weight later does; an achieved goal does not "
                   "un-achieve on regain, and an abandoned goal does not "
                   "retroactively take credit for a later coincidental "
                   "crossing of its target"),
        "gap": "none",
    }


def _e5_knee_restriction() -> dict:
    return {
        "id": "tom-E5", "kind": "behavior", "dataset": "medical",
        "dates": [START.isoformat()] + [f[1].isoformat() for f in FLARES],
        "claim": ("an athlete-stated knee restriction (no high-impact, "
                  "stairs limited) stands for the whole record, with four "
                  "short-lived symptom flares layered on top"),
        "truth": ("the restriction never lifts; each flare resolves on its "
                  "own resolved_date and the chronic state row is untouched"),
        "expect": ("nothing high-impact should ever be programmed while the "
                   "restriction stands, citing the restriction row only "
                   "(class b); during a flare window the engine may note "
                   "that sessions paused, never suggest a cause or what he "
                   "should do about his knee"),
        "gap": "none",
    }


def _e6_medication_expects_gap() -> dict:
    return {
        "id": "tom-E6", "kind": "gap", "dataset": "medical",
        "dates": [MED_DATE.isoformat()],
        "claim": ("the BP medication row records, in prose, that readings "
                  "run lower on days he has been out walking"),
        "truth": ("none of the four `expects` tokens (elevated_requirement, "
                  "rapid_loss, appetite_suppression, lean_mass_risk) "
                  "describes a blood-pressure effect, so the claim is "
                  "carried only in `note`, with `expects` left null"),
        "expect": ("the engine should be able to read a medication's "
                   "declared effect on a measurement domain other than "
                   "weight or intake from prose, when no enum token fits, "
                   "without inventing a false match; it must never suppress "
                   "or explain a blood-pressure tripwire it does not "
                   "actually implement"),
        "gap": ("G-tom-3: the `expects` vocabulary is scoped to weight/"
                "intake effects; a medication that changes a different "
                "measured quantity has no structured home"),
    }


def _e7_waist_vs_scale() -> dict:
    return {
        "id": "tom-E7", "kind": "gap", "dataset": "measurements",
        "dates": [START.isoformat(), DEFAULT_END.isoformat()],
        "claim": ("waist-tape readings and scale-weight readings both trend "
                  "down across the record, with different noise and "
                  "different provenance"),
        "truth": ("they are different quantities from different "
                  "instruments; the tape is not subject to the scale's "
                  "rounding-down bias, but that makes it a clean source for "
                  "waist_cm, not a better source for kg"),
        "expect": ("the ladder must never resolve one quantity's value "
                   "using another quantity's readings; waist_cm stays its "
                   "own trend line, cited only when a claim is actually "
                   "about waist, never blended into a weight-level estimate"),
        "gap": "none: this is a boundary the ladder already respects by "
               "ranking sources within a field, not across fields",
    }


def _e8_unschema_metrics() -> dict:
    return {
        "id": "tom-E8", "kind": "gap", "dataset": "checks",
        "dates": [],
        "claim": ("the metric that matters most to him - '12 of 14' stairs "
                  "against the bannister he built, and fares in a row "
                  "before needing to sit - never appears in any dataset"),
        "truth": ("unlike rachel, who logs her own fourteen-stairs fraction "
                  "as a degraded checks.jsonl pass/fail row with the "
                  "fraction in the note, tom never writes his down anywhere "
                  "machine-readable; it lives only in METRICS.md"),
        "expect": ("the engine has nothing to read here and must not invent "
                   "a proxy for it; this is deliberately the sharper half "
                   "of the G79 pair with rachel - the same fraction-shaped "
                   "metric, independently invented by two athletes, "
                   "encoded (in degraded form) by one and never encoded at "
                   "all by the other"),
        "gap": ("G79: fraction-shaped and occupational-capacity metrics "
                "have no schema-native home; here, additionally, no "
                "degraded encoding exists at all"),
    }


def _e9_benidorm_gaps() -> dict:
    return {
        "id": "tom-E9", "kind": "gap", "dataset": "weight",
        "dates": [w0.isoformat() for w0, _ in BENIDORM],
        "claim": ("a fixed two-week gap appears in weight and session "
                  "logging every September, for five consecutive Septembers"),
        "truth": ("this is an annual family holiday (Benidorm), not a lapse "
                  "or a device outage; no scale or notebook travels with him"),
        "expect": ("the engine should read a short, regularly recurring gap "
                   "as context rather than missing data to estimate or a "
                   "sign of non-adherence; it must not draw a trend line "
                   "straight across the gap without noting the record "
                   "thins there"),
        "gap": ("G-tom-4: no holiday/travel context dataset exists for tom "
                "(unlike sofia's or derek's context.jsonl), so this gap has "
                "no structured explanation attached to it in the record "
                "itself, only in WORLD.md"),
    }


def _e10_batch_backfill(transcribe_dates: list[date]) -> dict:
    return {
        "id": "tom-E10", "kind": "behavior", "dataset": "weight",
        "dates": [d.isoformat() for d in transcribe_dates],
        "claim": ("recorded_at on weight.jsonl clusters into nine dense "
                  "groups, each months after the dates it covers"),
        "truth": ("every value in these batches is the true notebook entry "
                  "for its date; the back-fill is a transcription habit, not "
                  "a fabrication (contrast marcus M3: same back-fill shape, "
                  "true data; contrast priya P1: same shape, false data)"),
        "expect": ("a future back-fill heuristic must treat recorded_at "
                   "clustering as an observation about WHEN a record was "
                   "written, never by itself as evidence about whether WHAT "
                   "was written is true; tom is one half of that "
                   "calibration pair"),
        "gap": "none: marcus M3 and tom together are the test that any "
               "such heuristic stays neutral",
    }


_TOML = """# tom: synthetic persona corpus, thresholds tuned to his record.
[targets]
phases = [[113.0, 100.0, 0.3]]

[tripwires]
pain_gate = 3

# Only three sources appear anywhere in this record; every one is listed
# here. Once [resolution] exists at all, an unlisted source is a hard
# validate failure, not a warning (handbook pitfall 4).
[resolution]
source_order = ["mechanical-scale", "tape-measure", "athlete"]

[resolution.precedence]
kg = ["mechanical-scale"]
value = ["tape-measure"]
distance_km = ["athlete"]
duration_s = ["athlete"]

[preferences]
suppressed_metrics = []
nudge_ok = false
check_tolerance = 0.02
"""


def build(end: date = DEFAULT_END) -> dict[str, str]:
    rng = random.Random(SEED)

    weight_stamper = common.Stamper(base_hour=20)
    measurements_stamper = common.Stamper(base_hour=21)
    sessions_stamper = common.Stamper(base_hour=18)
    daily_stamper = common.Stamper(base_hour=22)
    medical_stamper = common.Stamper(base_hour=9)
    goals_stamper = common.Stamper(base_hour=19)
    journal_stamper = common.Stamper(base_hour=21)

    control = CONTROL_BASE + [(end, 107.0)]

    weight, stats_pairs, weigh_dates = _weight(rng, weight_stamper, end, control)
    measurements = _measurements(rng, measurements_stamper, end, control)
    flare_windows = [(f[1], f[2]) for f in FLARES]
    sessions = _sessions(rng, sessions_stamper, end, flare_windows)
    daily = _daily(daily_stamper)
    medical = _medical(medical_stamper)
    goals, goal_dates = _goals(goals_stamper)
    journal = _journal(journal_stamper)

    pct_terminal, mean_bias, n_std = _digit_stats(stats_pairs)
    transcribe_dates = [t for _, _, t in _batches(end)]

    expectations = [
        _e1_digit_preference(pct_terminal, mean_bias, n_std, weigh_dates),
        _e2_vending_streak(),
        _e3_self_serving_correction(),
        _e4_goal_eras(goal_dates),
        _e5_knee_restriction(),
        _e6_medication_expects_gap(),
        _e7_waist_vs_scale(),
        _e8_unschema_metrics(),
        _e9_benidorm_gaps(),
        _e10_batch_backfill(transcribe_dates),
    ]

    return {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(weight)),
        "data/measurements.jsonl": common.jsonl_text(common.sort_rows(measurements)),
        "data/sessions.jsonl": common.jsonl_text(common.sort_rows(sessions)),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(daily)),
        "data/medical.jsonl": common.jsonl_text(common.sort_rows(medical)),
        "data/goals.jsonl": common.jsonl_text(common.sort_rows(goals)),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(journal)),
        "expectations.jsonl": common.jsonl_text(
            sorted(expectations, key=lambda r: str(r["id"]))),
    }
