"""Generator for the kenji persona (seed 137).

Osaka. 44, calibration technician in a metrology lab, and the only person in
this corpus who weighs himself the way his job weighs anything else.

THE AXIS HE STRESSES IS A SERIES THAT WAS WEIGHED RATHER THAN DRAWN. Every
other weight series here is a path the generator walked: a starting mass and a
step, with the step small enough to look like progress. His is the OUTPUT of
something - a cumulative energy balance he also logged - with measurement
scatter on top at a magnitude taken from published single-subject work rather
than chosen (see `SD_REL_DAY` below).

That distinction is what property 6 of `docs/persona-doctrine.md` is about, and
this corpus met its two named instances in one week:

  RAMPS. Four personas move a gram or two a day and never reverse, so a
  variation detector, a trend filter or a smoothing constant calibrated on
  them is calibrated on a body that does not fluctuate (#459, #462).

  UNRELATED STREAMS. The demo draws weight from one random stream and its two
  energy figures from two others, so the correlation between a deficit and a
  weight change is zero BY CONSTRUCTION, and an energy model scored against
  this corpus is scored against noise in both directions (#458, #461).

His record is built the other way round. Weight is not drawn at all: it is
carried forward from the balance he logged, and only the READING is drawn.
Change the balance and the weight changes with it, which is the property that
lets a test of an energy model be a test of the model.

WHAT THIS FIXTURE DOES NOT DO, and it is the sentence that matters most here.
It does not show that an energy model is TRUE of a person. The coupling in it
is authored, so an estimator that finds it has found something this file put
there. What it does is make the instrument falsifiable: before this record,
`agreement.compute_agreement` answered `explains: false` on all three records
it could be asked at all, so nothing distinguished a working estimator from a
broken one. A gate that has only ever returned one answer has been tested in
one direction.

TWO BLOCKS, AND THE SECOND IS THE EXPERIMENT. Twelve weeks at a deliberate
deficit, then thirteen at deliberate maintenance - because his question is not
"am I losing" but "how long must I weigh before a slope this small separates
from zero". The two blocks are also what give the record a RANGE of weekly
balances; a record at one steady deficit has nothing for a correlation to be
a correlation of.

NOTHING HERE IS COPIED FROM ANYWHERE. Every date, value and name is invented
for this fixture; the only figure taken from outside is the scatter magnitude,
which is cited.
"""

from __future__ import annotations

import random
from datetime import date

from . import common

SEED = 137
# Bumped only when the history could change an engine output
# (docs/persona-doctrine.md); never for prose, typos, or findings.
PERSONA_VERSION: int = 1

START = date(2030, 1, 7)
DEFAULT_END = date(2030, 6, 30)
# The day the deficit block ends and the maintenance block begins.
SWITCH = date(2030, 3, 31)

# --- the two numbers this record is built on, and where they come from -------
#
# ADOPTED, NOT CHOSEN (G85), which is the whole of #459's complaint about the
# four flat series: their scatter was picked, and picked an order of magnitude
# too small.
#
# Schneditz D, Hofmann P, Krenn S, Waller M, Mussnig S, Hecking M.
# "Day-to-day variability in euvolemic body mass." Ren Fail. 2023;45(2):2273421.
# doi:10.1080/0886022X.2023.2273421 (PMID 37955103). 9,521 days of standardised
# morning body mass from ONE healthy individual - single-subject, which is the
# design #459 asked for. The average and median relative difference between
# consecutive days were zero, with a standard deviation of 0.53 per cent for
# the one-day interval, rising to 0.69 per cent at seven days.
#
# THE PAPER REPORTS THE SD OF A DIFFERENCE, NOT OF A READING, and the two are
# not the same number. If each morning's reading sits a distance from the
# underlying mass and those distances are independent, the difference between
# two mornings has SD sigma * sqrt(2). Injecting 0.53 per cent directly as the
# per-reading scatter would therefore produce day-to-day differences with an SD
# near 0.75 per cent - forty per cent more movement than the paper measured,
# which is the same class of error as being too flat and harder to notice.
SD_REL_DAY = 0.0053
SD_REL_READING = SD_REL_DAY / (2 ** 0.5)

# The classic 7700 kcal per kg of tissue. It is here as the number this record
# was BUILT with, so a test can ask whether an estimator recovers it - not as a
# claim that it holds for anybody. `agreement.py` fits the density per record
# for exactly that reason and says so at length.
KCAL_PER_KG = 7700.0

_TOML = """# kenji - Osaka. A weight series that was weighed, not drawn.
[athlete]
timezone = "Asia/Tokyo"

[targets]
phases = [[78.0, 73.0, 0.4]]

[tripwires]
steps_floor = 6000
sleep_floor_h = 6.0

[resolution]
source_order = ["scale", "kitchen-log", "watch"]
"""


def _offset(_d: date) -> str:
    """Japan keeps one offset all year, which is why he is in Osaka.

    Every other generated record in this corpus crosses a summer-time boundary,
    so every one of them has a fortnight where a naive reader of `recorded_at`
    can get the order wrong. His does not, which makes him the record to reach
    for when a failure might be about the clock rather than the numbers.
    """
    return "+09:00"


def series(end: date = DEFAULT_END) -> list[tuple[date, float, int, int, str]]:
    """The record's spine: one row per day of (day, kg, kcal_in, kcal_out, block).

    ITS OWN RANDOM STREAM, seeded here rather than passed in. Four passes read
    this - the weigh-ins, the daily rows, the journal and the expectations -
    and a shared generator already advanced by an earlier pass would hand the
    later ones a different history than the one the record holds. That is not
    hypothetical: it happened while building `vera`, where the authored
    comparability row described runs the sessions were not built from and was
    wrong by two centimetres.

    THE WEIGHT IS CARRIED, NOT WALKED. `mass` moves only by the balance he
    logged, divided by the density above. The reading is `mass` plus scatter,
    and the scatter is thrown away afterwards - it is not carried into the next
    day, because a hydration swing is a property of the morning and not a debt
    the body repays.
    """
    rng = random.Random(SEED)
    out: list[tuple[date, float, int, int, str]] = []
    mass = 78.0
    for day in common.daterange(START, end):
        block = "deficit" if day <= SWITCH else "maintenance"
        # He aims at a deficit and misses, which is what gives the weekly
        # balances a spread. A record that hit its target every day would have
        # one balance repeated and nothing for a correlation to hold on to.
        aim = 480 if block == "deficit" else 0
        kcal_out = rng.gauss(2760, 150)
        kcal_in = kcal_out - aim + rng.gauss(0, 180)
        mass -= (kcal_out - kcal_in) / KCAL_PER_KG
        reading = mass + rng.gauss(0, SD_REL_READING * mass)
        out.append((day, round(reading, 2), round(kcal_in), round(kcal_out),
                    block))
    return out


def _weight(stamp: common.Stamper, end: date) -> list[dict]:
    """Every morning, same scale, same protocol slug, before eating.

    THE PROTOCOL SLUG NEVER CHANGES, and that is load-bearing rather than
    decorative. `api._weight_series_seam` refuses the whole energy question
    when a protocol change sits under the series, on the correct grounds that
    the two ends of a window would not be two readings of one measurand. A
    record built to be asked that question has to be a record where it can be
    asked.
    """
    return [common.record(
        "weight", date=day.isoformat(), kg=kg, source="scale", origin="scale",
        measured_at="06:20", protocol="morning-fasted-voided",
        capture="manual_entry", read_by="athlete",
        recorded_at=stamp.stamp(day))
        for day, kg, _in, _out, _b in series(end)]


def _daily(stamp: common.Stamper, end: date) -> list[dict]:
    """Both energy figures, every day, for the whole block.

    THIS IS NOT TYPICAL LOGGING AND THE RECORD SHOULD NOT BE READ AS IF IT
    WERE. #372 measured intake logged on 24 per cent of days in a real record,
    and those the days eating went to plan. He logs every day because the
    experiment has an end date and he treats it as one - `METRICS.md` says so,
    and `WORLD.md` says what he does after it ends.
    """
    rows = []
    for day, _kg, kcal_in, kcal_out, _b in series(end):
        rows.append(common.record(
            "daily", date=day.isoformat(),
            kcal_in=kcal_in, kcal_out=kcal_out,
            source="kitchen-log", origin="kitchen-log",
            capture="manual_entry", read_by="athlete",
            recorded_at=stamp.stamp(day)))
    return rows


def _instruments(stamp: common.Stamper) -> list[dict]:
    return [
        common.record(
            "instruments", date=START.isoformat(), origin="scale",
            from_date=START.isoformat(), name="the bench scale at home",
            maker=None, model=None, source="athlete",
            note="he calibrates it against a check mass on the first of every "
                 "month and has never had to adjust it",
            recorded_at=stamp.stamp(START)),
        common.record(
            "instruments", date=START.isoformat(), origin="kitchen-log",
            from_date=START.isoformat(), name="the kitchen scale and the log",
            source="athlete", recorded_at=stamp.stamp(START)),
    ]


def _slope_per_week(points: list[tuple[date, float]]) -> float:
    """Least squares slope in kg per week, spelled out rather than imported.

    The expectations below state what his own numbers do, and they have to
    state it by arithmetic a reader can check against the committed rows
    without running the engine - which is the same reason `vera`'s
    comparability figures are computed here rather than by calling the
    derivation they are supposed to be a second opinion on.
    """
    n = len(points)
    xs = [(d - points[0][0]).days for d, _ in points]
    ys = [kg for _, kg in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) * 7.0


def _journal(stamp: common.Stamper, end: date) -> list[dict]:
    """His weekly note, and the claim at the end that his own numbers refuse.

    THE METRIC THE SCHEMA CANNOT EXPRESS (doctrine property 3) is the number
    he writes down every Sunday: how many more mornings he expects to need
    before a slope this small separates from zero. It is not a weight, a rate,
    a target or a verdict - it is a statement about the MEASUREMENT PROCESS,
    an answer to "when will this record be able to tell me" rather than to
    "what am I". `goals` cannot hold it, `thresholds` cannot hold it and no
    verdict is about it, so it lives in prose, which is where this corpus puts
    everything the schema has no field for.

    It is also his disagreement with the engine, and it is not the author's.
    He calibrates instruments for a living, and to him a number without an
    interval is not a result. The engine's answer to a weekly rate is a
    DIRECTION - `losing`, `on_target` - and he regards a direction word where
    an interval belongs as a category error, not a simplification. He would
    rather it printed nothing.
    """
    rows = []
    for day, _kg, _in, _out, block in series(end):
        if day.weekday() != 6:
            continue
        if block == "deficit":
            text = ("Sunday count. Weighed every morning this week. The block "
                    "is doing what it is supposed to, so there is nothing to "
                    "detect yet - the question starts in April.")
        else:
            left = max(0, (end - day).days)
            text = (f"Sunday count. {left} mornings left in the block. Still "
                    f"cannot separate this slope from zero, which is the "
                    f"answer I am after and not a failure of the week.")
        rows.append(common.record(
            "journal", date=day.isoformat(), kind="note", text=text,
            source="athlete", recorded_at=stamp.stamp(day)))
    rows.append(common.record(
        "journal", date=end.isoformat(), kind="claim",
        text="The maintenance block held me flat.",
        source="athlete", recorded_at=stamp.stamp(end)))
    return rows


def _expectations(end: date) -> list[dict]:
    rows = series(end)
    maintenance = [(d, kg) for d, kg, _i, _o, b in rows if b == "maintenance"]
    slope = _slope_per_week(maintenance)
    net = maintenance[-1][1] - maintenance[0][1]
    # The SD of a DIFFERENCE between two readings is the per-reading SD times
    # root two - the same relation, used the other way round, that turns the
    # paper's 0.53 per cent into `SD_REL_READING` above.
    endpoint_sd = SD_REL_READING * maintenance[-1][1] * (2 ** 0.5)
    deficit = [(d, kg) for d, kg, _i, _o, b in rows if b == "deficit"]
    return [
        {"id": "kenji-E1", "kind": "behavior", "dataset": "weight",
         "dates": [rows[0][0].isoformat(), rows[-1][0].isoformat()],
         "claim": "the weight series is the output of the logged balance plus "
                  "measurement scatter, not a walked path",
         "truth": f"mass moves only by (kcal_out - kcal_in) / {KCAL_PER_KG:g} "
                  f"and each morning's reading adds independent scatter with "
                  f"SD {SD_REL_READING * 100:.3f} per cent of body mass, which "
                  f"is the 0.53 per cent one-day figure of Schneditz 2023 "
                  f"divided by root two because the paper reports the SD of a "
                  f"DIFFERENCE between two readings",
         "expect": "day-to-day movement matching published single-subject "
                   "variation, and a correlation between weekly balance and "
                   "weekly weight change that exists because the record was "
                   "built that way. It does NOT show an energy model is true "
                   "of a person; it shows an estimator can be scored",
         "gap": "none"},
        {"id": "kenji-E2", "kind": "behavior", "dataset": "daily",
         "dates": [SWITCH.isoformat()],
         "claim": "two blocks, a deficit then deliberate maintenance",
         "truth": f"{len(deficit)} days aiming at a 480 kcal deficit, then "
                  f"{len(maintenance)} aiming at zero",
         "expect": "a RANGE of weekly balances rather than one repeated "
                   "value. A record held at a single steady deficit gives a "
                   "correlation nothing to be a correlation of, and "
                   "`compute_agreement` refuses it outright when every "
                   "balance is the same number",
         "gap": "none"},
        {"id": "kenji-L-01", "kind": "lie", "dataset": "journal",
         "dates": [end.isoformat()],
         "claim": "his journal claim of the last day that the maintenance "
                  "block held him flat",
         "truth": f"his own two readings of that block disagree about the "
                  f"impression it gives. Its least-squares slope is "
                  f"{slope:+.3f} kg/week, which is flat; its endpoints differ "
                  f"by {net:+.2f} kg, which is {abs(net) / endpoint_sd:.1f} "
                  f"times the SD of a difference between two readings at this "
                  f"scatter and so is ordinary noise reading as a gain. "
                  f"Neither is wrong. What is wrong is stating a conclusion "
                  f"from one of them, and his own Sunday notes through the "
                  f"block say in terms that he cannot yet separate this slope "
                  f"from zero - so he asserted on the last day the thing he "
                  f"had spent thirteen weeks writing down that he could not "
                  f"establish",
         "expect": "the engine observes the contradiction and does not "
                   "resolve it. Two statements disagreeing is an observation. "
                   "The refusal to score a weekly rate on this block is the "
                   "CORRECT answer rather than a shortcoming, and he is the "
                   "one person in this corpus who would say so himself",
         "gap": "the number he actually wants - how many more mornings until "
                "a slope this small separates from zero - has no field in the "
                "schema and lives in his Sunday notes as prose"},
    ]


def build(end: date = DEFAULT_END) -> dict[str, str]:
    return {
        "vitai.toml": _TOML,
        "data/weight.jsonl": common.jsonl_text(common.sort_rows(
            _weight(common.Stamper(base_hour=6, offset=_offset), end))),
        "data/daily.jsonl": common.jsonl_text(common.sort_rows(
            _daily(common.Stamper(base_hour=21, offset=_offset), end))),
        "data/instruments.jsonl": common.jsonl_text(common.sort_rows(
            _instruments(common.Stamper(base_hour=20, offset=_offset)))),
        "data/journal.jsonl": common.jsonl_text(common.sort_rows(
            _journal(common.Stamper(base_hour=22, offset=_offset), end))),
        "expectations.jsonl": common.jsonl_text(_expectations(end)),
    }
