"""Weekly goal-attainment verdicts: the machine-readable contract.

One row per (ISO week, metric): value, target, verdict. This is what a game
economy, dashboard, or coaching skill consumes - deterministic, rebuilt on
every build, projected into the `verdicts` table of the read model.

Verdict vocabulary (closed): on_target | ahead | behind | no_data.
"ahead"/"behind" are metric-relative (for weight rate, faster than the
phase target counts as "ahead" only in the arithmetic sense - the coaching
layer decides whether ahead is good; the engine does not moralise).

Each week is judged against the thresholds IN FORCE ON ITS MONDAY (G14/G20).
Two consequences worth stating plainly: lowering the steps floor today cannot
turn last March's misses into hits on the next rebuild, and a threshold edited
mid-week does not re-score the days already lived under the old number.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from .weeks import week_of
from .clocks import weigh_in_timing
from .config import Config, overlay, phase_rate_for
from .policy import state
from .schema import EXTERNAL_METRIC
from .schema import statistics as _statistics

ON, AHEAD, BEHIND, NODATA = "on_target", "ahead", "behind", "no_data"

# WHY there is no verdict (#177). `no_data` answers "can a judgement be
# rendered"; this answers "why not", and they are different questions that
# should not share a token.
#
# The distinction already existed in the data and was recoverable ONLY by
# inspecting which fields were null: value and target both absent meant the
# input was missing, target absent meant no policy, both present meant the
# measurement could not support the judgement. Every consumer would have
# reverse-engineered that from row shape, each slightly differently, and none
# of them is the engine.
#
# A SECOND FIELD rather than more verdict words, deliberately. The verdict
# answers one question with one answer, and a consumer that ignores the reason
# degrades to exactly today's behaviour rather than breaking on a widened
# vocabulary it switches on. It also leaves room for the cases that do not
# exist yet, and the uncertainty work already has two.
NO_INPUT = "no_input"                # the record holds nothing to judge
NO_POLICY = "no_policy"              # nothing to judge it against
NOT_SUPPORTED = "not_supported"      # the measurement cannot support a verdict
CONTRAINDICATED = "contraindicated"  # judging it would be actively harmful
SUPPRESSED = "suppressed"            # the athlete asked not to be scored

PENDING = "pending"                  # answerable, and not yet: a source is due
# WHAT THE ENGINE WILL VOUCH FOR, beside the reason it will not (#185/#189).
#
# An athlete asks "have I had enough protein today". Three things are being
# asked and they are not equally answerable: protein against a target is one
# logged quantity against a stated goal, and energy balance is a DIFFERENCE OF
# TWO INEXACT AGGREGATES. Subtracting those does not average their errors, it
# amplifies the relative one - two large separately-inexact numbers differencing
# to a small one is the worst arithmetic available, and "400 kcal left" can
# carry uncertainty larger than the figure.
#
# The engine returned both with the same confidence and only one deserved it.
# So a judged row now says which:
#
#   magnitude - render the number, at the resolution it supports
#   direction - render ahead, behind, on track, and NEVER a figure
#
# ONE FIELD WITH THE REFUSALS, not a parallel table. #177 already shipped a
# vocabulary for what the engine will not answer and enforced totality in both
# directions; this is the positive half of the same question, and keeping them
# apart would ship two vocabularies for one thing. `provisional` - a day still
# open, so the number is "so far" rather than final - is the third value this
# field is shaped for, and it belongs to the day-completeness work, which this
# issue's own Related section files separately.
#
# A CLIENT CANNOT DERIVE THIS. It would have to reimplement the per-field
# policy, every client would derive it slightly differently, and that
# duplication is what this engine exists to prevent.
MAGNITUDE, DIRECTION = "magnitude", "direction"
ANSWERS = {MAGNITUDE, DIRECTION}

REFUSAL_REASONS = {NO_INPUT, NO_POLICY, NOT_SUPPORTED, CONTRAINDICATED,
                   SUPPRESSED, PENDING}

# How many gaps a source must have supplied before its cadence is worth
# believing. Four gaps means five arrivals, which is thin, and thin is why the
# refusal below is the CONSERVATIVE direction: with no established cadence the
# engine says `no_input`, which is what it says today. A guessed cadence would
# promise an athlete that something is coming when nothing is.
MIN_GAPS_FOR_CADENCE = 4


def expected_next(rows: list[dict], on: date, field: str) -> date | None:
    """When the next reading of `field` is due, from its source's OWN
    arrivals, or None when the record cannot say (#202).

    EARNED FROM THE RECORD, NOT DECLARED. Nothing tells the engine that a
    connector syncs nightly or that an export is taken weekly, and asking an
    importer to declare it would put a promise in config that the data can
    already demonstrate. A source that has landed every day for a month is due
    tomorrow, and the record says so without being told.

    PER SOURCE, and only counting rows that actually carry the value. Pooling
    every source would average a nightly device with a monthly clinic visit
    into a cadence neither of them has, and a row whose field is null is not an
    arrival of that field however well-formed the line is. The answer is the
    soonest arrival still AHEAD across the sources that have an established
    cadence, because the question is when this metric next lands rather than
    which source wins. Where every source is already late, it is the least
    stale expectation, which is the one that says most accurately how overdue
    this metric is.

    The median gap rather than the mean: one holiday, one flat battery or one
    forgotten week would drag a mean far enough to make the estimate useless,
    and those are the normal shape of a person's logging rather than outliers
    to be cleaned.

    Returns None below `MIN_GAPS_FOR_CADENCE`, on the same discipline the
    verdict layer already applies to weigh-in timing: where the reference is
    thin, decline rather than average.
    """
    by_source: dict[str, set] = defaultdict(set)
    for r in rows:
        if r.get(field) is None or not r.get("date"):
            continue
        # `datetime` rather than `date`, matching `_week_key` and the rest of
        # the engine: a time-bearing `date` is a schema WARNING and still
        # loads, so parsing it strictly here would take down a build that
        # worked yesterday.
        when = datetime.fromisoformat(str(r["date"])).date()
        if when <= on:
            by_source[str(r.get("source") or "")].add(when)

    due = []
    for days in by_source.values():
        days = sorted(days)
        if len(days) < MIN_GAPS_FOR_CADENCE + 1:
            continue
        gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
        due.append(days[-1] + timedelta(days=gaps[len(gaps) // 2]))
    if not due:
        return None
    # The soonest arrival STILL AHEAD. A plain minimum picked whichever source
    # was furthest overdue and reported it as the next thing to land, so a
    # monthly visit missed in May outranked a scale due tomorrow. A source
    # that has already failed to deliver is not the soonest answer.
    ahead = [d for d in due if d >= on]
    # If every source is late, the LEAST stale expectation: it is the one that
    # says most accurately how overdue this metric is.
    return min(ahead) if ahead else max(due)


# From the registry, so the code cannot know a statistic the vocabulary does
# not (semantics/statistics.toml). A module constant because the vocabulary
# is a shipped file rather than record data - `vocab.registry` is itself
# cached, so this is about saying the set is fixed, not about the file read.
STATISTICS = frozenset(_statistics())

AVERAGE = "average"
MAXIMUM = "maximum"
COUNT = "count"
COMPOSITE = "composite-of-summaries"
PERIOD_CHANGE = "period-over-period-change"


# Which metrics survive as a number, and which only as a direction.
#
# `energy_availability` is (mean intake - exercise per day) / fat-free mass:
# expenditure carries 20 to over 90 per cent error in the validation
# literature, systematic and activity-dependent, self-reported intake carries
# its own under-reporting on top, and the difference amplifies both.
#
# `weight_rate` is not a vendor estimate - it is two means of the same scale -
# and it still does not survive, on this project's own pre-registered
# measurement: the median 95 per cent half-width on a week-over-week rate is
# 1.74 times the entire decision half-band. A rate whose interval swamps the
# band it is judged against is a direction, and reporting it to three decimal
# places was the engine claiming a precision it had already measured away.
#
# Everything else is one logged or measured quantity against a stated policy,
# which is the shape that does survive.
ANSWERS_BY_METRIC = {
    # One logged or measured quantity against a stated policy - the shape
    # that survives. Self-report under-reports, but one-signed and into a
    # SAFETY FLOOR, so the bias errs toward firing rather than toward
    # silence, and both are gated on at least 7 of 14 days carrying a value.
    "intake_floor": MAGNITUDE,
    "protein_floor": MAGNITUDE,
    "steps": MAGNITUDE,
    "sleep": MAGNITUDE,
    "rhr": MAGNITUDE,
    # A count of reports is exact.
    "symptom_chest_pain": MAGNITUDE,
    "symptom_syncope": MAGNITUDE,

    # (mean intake - exercise per day) / fat-free mass. Expenditure carries 20
    # to over 90 per cent error in the validation literature, self-report
    # carries its own on top, and the difference amplifies the relative error
    # rather than averaging it.
    "energy_availability": DIRECTION,
    # NOT a vendor estimate - two means of the same scale - and it still does
    # not survive. This project's pre-registered run measured a median
    # `u_rate / half-band` of 1.74 and found that MORE THAN HALF of scored
    # weeks admit no verdict word at all.
    #
    # Which is worth stating plainly: that result does not support `direction`
    # either. Its own decision was that the DECISION UNIT is wrong and a
    # refusal predicate ships, which is #171's to build. `direction` is the
    # strictly weaker of the two tokens this field has, so it is an
    # improvement on claiming a magnitude and it is not the answer.
    "weight_rate": DIRECTION,
    # An unweighted mean of per-session average heart rates, at intensity by
    # construction - a 20-minute jog weighing the same as a 2-hour run. The
    # per-field table adopted at the same gate says avg_hr is usable at rest
    # and NOT at intensity, so a magnitude here would contradict this
    # project's own shipped policy.
    "easy_hr": DIRECTION,
    # A 0-10 ordinal whose SCALE is declared per row (contract 26) and does
    # not reach the verdict. `magnitude` says render the number at the
    # resolution it supports, and a bare ordinal with no denominator has
    # none - which is verbatim the defect contract 26 exists to name. The
    # value is exact as reported; what is missing is the bound. Carrying the
    # scale through to this row would make it a magnitude honestly.
    "pain_gate": DIRECTION,
}


def _answers(metric: str) -> str:
    """What the engine will vouch for on this metric.

    CLOSED WORLD, like `statistic` beside it. A default would hand every new
    metric the STRONGER claim silently, which is the failure this field
    exists to fix arriving through the door marked convenience.
    """
    if metric not in ANSWERS_BY_METRIC:
        raise ValueError(
            f"{metric!r} reports a number and nothing says what it is good "
            f"for: add it to ANSWERS_BY_METRIC as {MAGNITUDE!r} or "
            f"{DIRECTION!r}. Defaulting would promise a magnitude for a "
            "figure that may not carry one")
    return ANSWERS_BY_METRIC[metric]


def _week_key(d: str) -> str:
    # ONE definition of a week, in `weeks` (#208). It was four copies of the
    # arithmetic and TWO contracts: this one raises on a value that is not a
    # date, `query`'s returns "". `week_of` is the raising half, so nothing
    # about this caller changes.
    return week_of(d)


def _weeks_covered(*datasets: list[dict]) -> list[str]:
    weeks = {_week_key(r["date"]) for ds in datasets for r in ds if r.get("date")}
    return sorted(weeks)


def _row(week: str, metric: str, value: float | None, target: float | None,
         verdict: str, goal: str | None = None,
         reason: str | None = None, due: str | None = None,
         statistic: str | None = None,
         window_days: int | None = None) -> dict:
    # A reason is REQUIRED with a refusal and forbidden without one, so a new
    # refusal site cannot ship unlabelled and a judged row cannot carry a
    # reason nobody asked for. This is the totality the issue asks for, held
    # at the one place every row is built rather than at each caller.
    if verdict == NODATA and reason not in REFUSAL_REASONS:
        raise ValueError(
            f"a {NODATA} verdict needs a reason, one of "
            f"{', '.join(sorted(REFUSAL_REASONS))}, got {reason!r}. Once a "
            "refusal ships under a bare token the reason is gone and cannot "
            "be recovered from the row")
    if verdict != NODATA and reason is not None:
        raise ValueError(f"{verdict} is a judgement, not a refusal; it has no "
                         f"reason to carry (got {reason!r})")
    # `due` says when the source that has been supplying this metric is next
    # expected. It belongs to a REFUSAL and never to a judgement: a verdict
    # the engine reached needs no promise about what arrives later.
    if due is not None and verdict != NODATA:
        raise ValueError(f"{verdict} is a judgement and carries no due date "
                         f"(got {due!r})")
    if reason == PENDING and due is None:
        raise ValueError(
            f"{PENDING} means the answer is coming, so it carries WHEN. "
            "Without an instant it is `no_input` wearing optimism, and a "
            "metric that is pending forever is a broken connector nobody "
            "will notice")
    # WHAT KIND OF NUMBER `value` IS (#261 layer 1). Required wherever there
    # is a value, and held here rather than at each caller for the reason
    # `reason` is: a new metric must not be able to ship unlabelled. One
    # column carried a maximum, a week-over-week change and six averages, and
    # a consumer reading the weekly `steps` average as a weekly total saw a
    # week five thousand steps a day short of the one that happened.
    if value is not None and statistic not in STATISTICS:
        raise ValueError(
            f"{metric!r} reports a value, so it says what KIND of number it "
            f"is: one of {', '.join(sorted(STATISTICS))}, got {statistic!r}. "
            "An aggregate whose statistic a reader has to infer from the "
            "metric name is one they will infer wrongly")
    # And a refusal carries none: there is no number for it to describe, and
    # a statistic beside a null value describes nothing.
    if value is None and statistic is not None:
        raise ValueError(f"{metric!r} has no value, so it has no statistic "
                         f"to declare (got {statistic!r})")
    # OVER WHAT. A statistic with no stated population is half an answer, and
    # the half it leaves out is the one that misleads: `intake_floor` is a
    # mean over FOURTEEN days on a row keyed by one week, so a consumer
    # reading "average" against the week it can see reads it over the wrong
    # population. Defaults to the keyed week, which is what every weekly
    # metric uses, so the exceptions are the rows that say so.
    if value is not None and window_days is None:
        window_days = 7
    # EVERY JUDGED ROW SAYS WHAT IT IS GOOD FOR, AND NO REFUSAL DOES - the
    # same totality `reason` has, in the other direction.
    #
    # Keyed on the VERDICT and not on the value, which the first cut got
    # wrong. A refusal often keeps its number: `not_supported` fires when
    # weigh-in drift accounts for the whole rate, so not even the sign is
    # supported, and `contraindicated` fires when judging would be actively
    # harmful. Stamping those rows `direction` told a consumer the engine
    # vouches for ahead-or-behind on exactly the rows where it had just said
    # it vouches for nothing. #185's own table is explicit: a refusal gets
    # the reason and no number at all.
    #
    # Derived from the metric rather than passed in, because a caller free to
    # choose is a caller free to promise a magnitude for a figure that cannot
    # carry one.
    answers = None if (value is None or verdict == NODATA) else _answers(metric)
    return {"week": week, "metric": metric,
            "value": round(value, 3) if value is not None else None,
            "target": target, "verdict": verdict, "goal": goal,
            "reason": reason, "due": due, "statistic": statistic,
            "window_days": window_days, "answers": answers}


def _awaiting(rows: list[dict], field: str, week: str,
              today: date | None) -> dict:
    """Is this an empty week, or a week whose data has not landed yet? (#202)

    `no_input` says the record holds nothing. True, and useless on its own: it
    cannot tell an athlete that nothing will ever come apart from a source that
    delivers in four hours, and the honest client sentence built on it is
    "check again later", which is the most robotic thing this engine makes
    anyone say.

    THE DEGRADATION IS THE POINT, and it is what stops `pending` becoming an
    excuse. A refusal is pending only while the expected arrival is still
    ahead. Once that day is past, the reason drops back to `no_input` and the
    row KEEPS the date it was due, so a consumer can say the source is two days
    late rather than repeating that the answer is coming. A metric that stayed
    hopeful forever would be a broken connector nobody noticed.

    `week` is the week whose data is MISSING, which is not always the week
    being judged: a rate needs two weeks, and a future arrival cannot fill the
    earlier one.
    """
    if today is None:
        return {"reason": NO_INPUT}
    due = expected_next(rows, today, field)
    if due is None:
        return {"reason": NO_INPUT}          # its own history cannot say
    start = date.fromisoformat(week)
    if not (start <= due <= start + timedelta(days=6)):
        # An arrival that lands outside this week cannot fill it, whichever
        # side it falls. Waiting for it would be waiting for the wrong thing.
        return {"reason": NO_INPUT}
    if due < today:
        # Expected, and it did not come. Still a refusal, and now an overdue
        # one: the date rides along so the lateness is visible. Due TODAY is
        # not late - "arrives in four hours" is the case this exists for.
        return {"reason": NO_INPUT, "due": due.isoformat()}
    return {"reason": PENDING, "due": due.isoformat()}


def _target_for(goals_in_force: tuple[dict, ...], metric: str,
                threshold: float) -> tuple[float, str | None]:
    """The value this metric is judged against, and the goal behind it (#199).

    A DECLARED GOAL TARGET SUPERSEDES THE THRESHOLD while it is in force. The
    two were separate scoring systems that never met: `goals` held a target
    the athlete chose and `verdicts` held a floor he did not, they were
    computed by different code, and the shipped demo had them disagreeing
    about steps - 99.9% of one number beside `on_target` against another.

    A threshold is a floor nobody chose; a goal target is an aim he did. Where
    he has said what he is aiming at, that is what he is judged against, and
    the config value goes back to being what it is - a default for a metric
    nobody has spoken about.

    THE SAFETY FLOORS ARE NOT REACHED BY THIS. `intake_floor`, `protein_floor`
    and `energy_availability` are computed on a separate path that never
    consults goals, which is what makes them non-suppressible: a target
    declared under a floor changes what he is scored against and cannot switch
    off the sentence saying the floor was crossed.
    """
    for g in goals_in_force:
        if g.get("metric") != metric or g.get("metric") == EXTERNAL_METRIC:
            continue
        target = g.get("target")
        usable = (isinstance(target, (int, float))
                  and not isinstance(target, bool))
        # ONLY WHERE THE UNITS MATCH, which is the part the decision could not
        # state because it was about precedence rather than arithmetic. These
        # rows compare a PER-DAY average against a per-day floor. A weekly goal
        # target is a period TOTAL, and swapping one in compared 9739 steps a
        # day against 77000 a week and called it behind at 85% of target -
        # trading a disagreement between two systems for a wrong answer from
        # one, which is worse.
        #
        # A period-total goal is already scored, by `goal_progress` and the
        # achievement axis that exists for exactly this. What supersedes here
        # is a target stated in the same unit the row is in: a daily one.
        if usable and g.get("period") == "daily":
            return float(target), g.get("slug")
        return threshold, g.get("slug")
    return threshold, None


def _goal_for(goals_in_force: tuple[dict, ...], metric: str) -> str | None:
    """The active goal this metric serves, if any - the verdict's goal linkage.

    First match by declaration order wins. Two active goals on one metric is a
    modelling smell the coach should raise, not something the engine resolves.
    """
    for g in goals_in_force:
        if g.get("metric") == metric and g.get("metric") != EXTERNAL_METRIC:
            return g.get("slug")
    return None


def compute_verdicts(cfg: Config, weight: list[dict], daily: list[dict],
                     sessions: list[dict], today: date | None = None,
                     goals: list[dict] | None = None,
                     thresholds: list[dict] | None = None,
                     medical: list[dict] | None = None) -> list[dict]:
    """Deterministic weekly verdict rows across all configured metrics."""
    rows: list[dict] = []
    weeks = _weeks_covered(weight, daily, sessions)
    if not weeks:
        return rows

    # Policy as of each week's Monday: thresholds overlaid on vitai.toml, and
    # the goals that were active then (for the `goal` linkage column).
    as_of = {wk: state(goals or [], thresholds or [], wk) for wk in weeks}
    cfg_for = {wk: overlay(cfg, as_of[wk].thresholds) for wk in weeks}
    goals_for = {wk: as_of[wk].active_goals() for wk in weeks}

    # --- weight rate: mean(kg) this week vs previous week, vs phase target ---
    by_week_kg: dict[str, list[float]] = defaultdict(list)
    by_week_rows: dict[str, list[dict]] = defaultdict(list)
    for w in weight:
        if w.get("kg") is not None:
            by_week_kg[_week_key(w["date"])].append(w["kg"])
            by_week_rows[_week_key(w["date"])].append(w)
    for wk in weeks:
        vals = by_week_kg.get(wk)
        prev_wk = (datetime.fromisoformat(wk).date() - timedelta(days=7)).isoformat()
        prev = by_week_kg.get(prev_wk)
        if not vals or not prev:
            if vals or prev:
                # The MISSING side. When this week has weigh-ins and the
                # previous one does not, no future arrival can fill the
                # earlier week, and calling that pending promises something
                # that cannot happen.
                rows.append(_row(wk, "weight_rate", None, None, NODATA,
                                 **_awaiting(weight, "kg",
                                             wk if not vals else prev_wk,
                                             today)))
            continue
        rate = mean(prev) - mean(vals)  # positive = losing
        target = phase_rate_for(cfg_for[wk], mean(vals))
        goal = _goal_for(goals_for[wk], "weight_rate")
        if target is None:
            rows.append(_row(wk, "weight_rate", rate, None, NODATA, goal,
                             reason=NO_POLICY, statistic=PERIOD_CHANGE))
            continue
        # #37: a rate whose weigh-in times are spread widely enough to
        # account for it is not a rate, and this is the machine-readable
        # contract - a consumer reading AHEAD or BEHIND here will render it as
        # fact. Reporting the number with NODATA says "here is what the scale
        # did, and no, we cannot judge it", which is the honest pair. The same
        # shape as `_drops_rate_verdict` for a medical contraindication: the
        # engine already knows how to decline to score something.
        timing = weigh_in_timing(by_week_rows.get(wk, [])
                                 + by_week_rows.get(prev_wk, []))
        if timing["known"] and not timing["unknown"] and (
                timing["drift_kg"] >= abs(rate)):
            rows.append(_row(wk, "weight_rate", rate, target, NODATA, goal,
                             reason=NOT_SUPPORTED, statistic=PERIOD_CHANGE))
            continue
        if abs(rate - target) <= 0.25:
            verdict = ON
        else:
            verdict = AHEAD if rate > target else BEHIND
        rows.append(_row(wk, "weight_rate", rate, target, verdict, goal,
                         statistic=PERIOD_CHANGE))

    # --- easy-run HR discipline: weekly avg of run avg_hr vs cap ------------
    by_week_hr: dict[str, list[int]] = defaultdict(list)
    for s in sessions:
        if s.get("type") == "run" and s.get("avg_hr"):
            by_week_hr[_week_key(s["date"])].append(s["avg_hr"])
    for wk in weeks:
        cap = cfg_for[wk].easy_hr_cap
        hrs = by_week_hr.get(wk)
        if cap is None or not hrs:
            continue
        avg = mean(hrs)
        aim, goal = _target_for(goals_for[wk], "easy_hr", float(cap))
        rows.append(_row(wk, "easy_hr", avg, aim,
                         ON if avg <= aim else BEHIND, goal,
                         statistic=AVERAGE))

    # --- daily floors/gates, weekly aggregated ------------------------------
    daily_by_week: dict[str, list[dict]] = defaultdict(list)
    for d in daily:
        daily_by_week[_week_key(d["date"])].append(d)

    for wk in weeks:
        days = daily_by_week.get(wk, [])
        if not days:
            continue
        eff = cfg_for[wk]
        active = goals_for[wk]
        if eff.steps_floor is not None:
            steps = [d["steps"] for d in days if d.get("steps") is not None]
            if steps:
                avg = mean(steps)
                aim, goal = _target_for(active, "steps",
                                        float(eff.steps_floor))
                rows.append(_row(wk, "steps", avg, aim,
                                 ON if avg >= aim else BEHIND, goal,
                                 statistic=AVERAGE))
        if eff.sleep_floor_h is not None:
            sleeps = [d["sleep_h"] for d in days if d.get("sleep_h") is not None]
            if sleeps:
                avg = mean(sleeps)
                aim, goal = _target_for(active, "sleep_h",
                                        float(eff.sleep_floor_h))
                rows.append(_row(wk, "sleep", avg, aim,
                                 ON if avg >= aim else BEHIND, goal,
                                 statistic=AVERAGE))
        if eff.pain_gate is not None:
            # `pain` after the gen-2 generalization; old lines arrive here
            # already mapped from `hip_pain` by resolution.canonical_daily.
            pains = [d.get("pain") if d.get("pain") is not None else d.get("hip_pain")
                     for d in days
                     if d.get("pain") is not None or d.get("hip_pain") is not None]
            if pains:
                worst = max(pains)
                # CURRENT NAME FIRST. `_goal_for` matches `metric` exactly, so
                # looking up only the retired name linked this verdict to a
                # goal nobody writes any more: an athlete who has only ever
                # recorded `pain` got the right number with `goal: None`, and
                # a missing linkage looks identical to having declared no
                # goal at all. Only the record that predates the gen-2
                # generalization still declares `hip_pain`, so it is the
                # fallback and never the first choice.
                rows.append(_row(wk, "pain_gate", float(worst), float(eff.pain_gate),
                                 ON if worst <= eff.pain_gate else BEHIND,
                                 _goal_for(active, "pain")
                                 or _goal_for(active, "hip_pain"),
                                 statistic=MAXIMUM))
        if eff.rhr_baseline is not None:
            rhrs = [d["rhr"] for d in days if d.get("rhr") is not None]
            if rhrs:
                avg = mean(rhrs)
                rows.append(_row(wk, "rhr", avg, float(eff.rhr_baseline + 5),
                                 ON if avg <= eff.rhr_baseline + 5 else BEHIND,
                                 _goal_for(active, "rhr"), statistic=AVERAGE))

    # Safety floors that need no configuration (G68). Every rule above is
    # opt-in: it produces nothing until the athlete sets a threshold. That is
    # right for coaching preferences and wrong for danger, and it meant an
    # athlete who had configured nothing - the state every new user is in -
    # got `tripwires: none` while eating 1200 kcal a day and losing a kilo a
    # week. These rows fire from defaults, like the absolute RHR band.
    rows += _default_floor_rows(weight, daily, sessions, medical or [])

    # G72: when a declared medication makes rapid loss the EXPECTED outcome,
    # the rate verdict is meaningless and actively harmful - it tells someone
    # for whom the treatment is working that she is failing a target nobody
    # set for her. Drop the row rather than dress it up; the nutrition floors
    # and the lean-mass composite carry the real risk on this pathway.
    # LABELLED, not deleted (#177). Dropping the row made a contraindicated
    # metric indistinguishable from one that was never computed, and the
    # doctrine everywhere else in this engine is that suppression is a label
    # and never a deletion. The judgement still does not happen; what changes
    # is that the record says so.
    if _drops_rate_verdict(medical or [], weeks):
        rows = [_row(r["week"], r["metric"], r["value"], r["target"], NODATA,
                     r["goal"], reason=CONTRAINDICATED,
                     statistic=r["statistic"])
                if r["metric"] == "weight_rate" else r for r in rows]

    # G33, last: a suppressed metric is still RECORDED, just not scored. The
    # data keeps accumulating for the day the athlete wants it back; what
    # stops is the judging.
    if cfg.suppressed_metrics:
        rows = [_row(r["week"], r["metric"], r["value"], r["target"], NODATA,
                     r["goal"], reason=SUPPRESSED, statistic=r["statistic"])
                if r["metric"] in cfg.suppressed_metrics else r
                for r in rows]
    rows.sort(key=lambda r: (r["week"], r["metric"]))
    return rows


def _drops_rate_verdict(medical: list[dict], weeks: list[str]) -> bool:
    """Is rapid loss the declared, expected outcome of a treatment?

    Deliberately narrow: only a medication or state line that SAYS so does
    this, and it removes one verdict rather than quietening the safety layer.
    Every absolute floor still fires.
    """
    from .safety import _expectations, _as_date

    if not weeks:
        return False
    last = _as_date(weeks[-1])
    return last is not None and "rapid_loss" in _expectations(medical, last)


def _default_floor_rows(weight: list[dict], daily: list[dict],
                        sessions: list[dict], medical: list[dict]) -> list[dict]:
    """Verdict rows for the absolute nutrition floors and energy availability.

    These live in `verdicts` as well as in the escalation surface because a
    verdict is what a dashboard, a game and the weekly rollup already read. A
    safety finding that only exists in a channel nobody renders is a safety
    finding nobody sees.
    """
    from .safety import (
        EA_LOW_THRESHOLD, INTAKE_FLOOR_KCAL, PROTEIN_FLOOR_G_PER_KG,
        RED_S_WINDOW_DAYS, _expectations, _latest_weight, _window,
        energy_availability,
    )

    window, _, end = _window(daily, RED_S_WINDOW_DAYS)
    if not window:
        return []
    wk = _week_key(end.isoformat())
    out: list[dict] = []

    floor = INTAKE_FLOOR_KCAL
    if "elevated_requirement" in _expectations(medical, end):
        floor += 500.0
    intakes = [float(r["kcal_in"]) for r in window if r.get("kcal_in") is not None]
    if len(intakes) >= 7:
        mean_intake = sum(intakes) / len(intakes)
        out.append(_row(wk, "intake_floor", mean_intake, floor,
                        BEHIND if mean_intake <= floor else ON,
                        statistic=AVERAGE, window_days=RED_S_WINDOW_DAYS))

    kg = _latest_weight(weight, end)
    proteins = [float(r["protein_g"]) for r in window
                if r.get("protein_g") is not None]
    if kg and len(proteins) >= 7:
        per_kg = (sum(proteins) / len(proteins)) / kg
        out.append(_row(wk, "protein_floor", per_kg, PROTEIN_FLOOR_G_PER_KG,
                        BEHIND if per_kg < PROTEIN_FLOOR_G_PER_KG else ON,
                        statistic=AVERAGE, window_days=RED_S_WINDOW_DAYS))

    ea, _terms = energy_availability(daily, weight, sessions)
    if ea is not None:
        # NOT an average, despite being built from one. It is
        # (mean intake - exercise per day) / fat-free mass, and on a record
        # with fewer than fourteen logged intakes the two terms do not share
        # a denominator - the mean is over the days that carry one, the
        # second divides by the window length regardless. So it is the mean
        # of no per-day series that exists.
        out.append(_row(wk, "energy_availability", ea, EA_LOW_THRESHOLD,
                        BEHIND if ea < EA_LOW_THRESHOLD else ON,
                        statistic=COMPOSITE, window_days=RED_S_WINDOW_DAYS))
    out += _symptom_rows(weight, daily, sessions, medical)
    return out


# Red-flag symptom classes, and the verdict metric each is counted under. A
# recurrent symptom is the most important thing about an athlete's week, so it
# belongs in the row set a dashboard already renders - not only in an
# escalation channel a consumer has to know to ask for.
SYMPTOM_METRICS = {"cardiac": "symptom_chest_pain", "syncope": "symptom_syncope"}


def _symptom_rows(weight: list[dict], daily: list[dict], sessions: list[dict],
                  medical: list[dict]) -> list[dict]:
    """One row per (week, symptom class): how many were reported, against zero."""
    from .safety import escalations

    counts: dict[tuple[str, str], int] = {}
    for row in escalations(medical, daily, weight, sessions,
                           include_low_energy_availability=False):
        metric = SYMPTOM_METRICS.get(str(row.get("trigger")))
        if metric and row.get("date"):
            key = (_week_key(str(row["date"])), metric)
            counts[key] = counts.get(key, 0) + 1
    return [_row(wk, metric, float(n), 0.0, BEHIND, statistic=COUNT)
            for (wk, metric), n in sorted(counts.items())]
