"""Per-event, per-goal contribution: the answer to "did today serve a goal".

The old model had one event produce one result. That is wrong (G18): a single
walk feeds a steps goal AND a calorie goal; a single big unplanned run feeds
the calorie goal but does NOT advance the running goal, because volume the
athlete did not budget is ramp rate, and ramp rate - not distance - is what
injures people. So one event fans out to every goal in force that day, each
with its own signed verdict.

Two contribution policies (declared per goal, not inferred):

- MONOTONIC: more always counts. Steps, calories, protein, reading minutes.
- GUARDED: the goal has a ramp guardrail. Volume up to `guard_pct` above the
  recent baseline counts; the excess is unbudgeted and does NOT advance the
  goal. The athlete is not scolded - the engine simply declines to credit it,
  and the coach explains why.

Contribution vocabulary (closed):
    advances | partial | unbudgeted | neutral | regresses

MILESTONES are derived from counted progress only. That is the point of the
guard: a 30 km week off a 12 km base mints no milestone, so the record cannot
congratulate an athlete for the exact behaviour that injures them. An
ACHIEVEMENT, by contrast, is recorded by a human (see the `achievements`
dataset) - the engine never invents one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .clocks import order_key
from .policy import (_event_index, days_between, deadline_of,
                     lifecycle_of, state)
from .schema import (ATTESTED, EXTERNAL, GOAL_DATASETS, KEYS, MEASURED,
                     verification_of)

ADVANCES, PARTIAL, UNBUDGETED, NEUTRAL, REGRESSES = (
    "advances", "partial", "unbudgeted", "neutral", "regresses")

# Milestone fractions of a goal's target, as a share of counted progress.
MILESTONE_FRACTIONS = (0.25, 0.5, 0.75, 1.0)

# Calendar weeks of history used as the ramp baseline for a guarded goal.
BASELINE_WEEKS = 4

# The datasets an event can arrive from. A goal scoped OUTSIDE these cannot be
# fed by the contribution engine at all - `weight` and `measurements` became
# legal goal scopes in #27, but nothing iterates them here, and a goal the
# engine cannot feed must report UNKNOWN progress rather than zero.
#
# The distinction is not cosmetic: 0% reads as total failure, and telling an
# athlete who has lost 3 kg that they are at 0% of their weight goal is the
# G69 harm in a new place. Reaching a target from a starting point is an
# APPROACH, not an accumulation, and modelling it properly needs the goal
# KINDS of G62 (quantity | skill | maintenance). Until then the engine says
# it does not know, which is both true and safe.
CONTRIBUTING_DATASETS = frozenset({"daily", "sessions"})

# How a goal's scope was arrived at. `dataset` unset is NOT the default - it is
# UNSTATED, and collapsing the two lets the engine assert something nobody said
# (the same "absent is not a value" line #35 draws for `recorder`).
DECLARED, INFERRED, AMBIGUOUS, UNDECLARED = (
    "declared", "inferred", "ambiguous", "undeclared")


def scope_of(goal: dict) -> tuple[str | None, str]:
    """(dataset this goal draws from, how we know) - inferring where we can.

    A hand-written goal row generally does not set `dataset`; the demo's
    fixtures did, which is why the #34 guard looked like it worked and the
    live record still rendered `0/73 (0%)` for an athlete at 83 kg.

    Rather than widen the guard to "unset also counts as unfeedable", the
    scope is INFERRED from the metric where the metric can only belong to one
    dataset: a goal in `kg` is a weight goal, and saying so removes the trap
    instead of papering over it.

    Where a metric names a column in more than one dataset the scope stays
    AMBIGUOUS and nothing is inferred - `distance_km` is walking on a daily
    line and running on a session line, which is the whole reason `dataset`
    exists. Guessing there would quietly count the athlete's commute toward a
    running goal, which is the failure `_in_scope` was written to prevent.
    """
    if (declared := goal.get("dataset")) is not None:
        return str(declared), DECLARED
    metric = goal.get("metric")
    if not isinstance(metric, str) or not metric:
        return None, UNDECLARED
    hosts = sorted(ds for ds in GOAL_DATASETS if metric in KEYS.get(ds, ()))
    if len(hosts) == 1:
        return hosts[0], INFERRED
    return None, AMBIGUOUS if hosts else UNDECLARED


def _week_key(d: str) -> str:
    dt = datetime.fromisoformat(d).date()
    return (dt - timedelta(days=dt.weekday())).isoformat()


def _period_key(period: str | None, d: str) -> str:
    """The bucket a date falls in for a goal's period. 'none' = one bucket."""
    if period == "weekly":
        return _week_key(d)
    if period == "monthly":
        return d[:7]
    if period == "quarterly":
        month = int(d[5:7])
        return f"{d[:4]}-Q{(month - 1) // 3 + 1}"
    if period == "yearly":
        return d[:4]
    return "all"


def _events(daily: list[dict], sessions: list[dict]) -> list[tuple[str, str, dict]]:
    """(date, dataset, record) for everything that can serve a goal, in order.

    Sorted by date then dataset then a stable rendering of the record, so two
    builds over the same inputs emit contributions in the same order
    (working rule 6: determinism).

    The tiebreak is a STRING, not the item list itself: two events on the same
    day can hold different types under the same key (a null `kcal` on one
    session, a number on the next), and comparing those directly raises.
    """
    evs = [(r["date"], "daily", r) for r in daily if r.get("date")]
    evs += [(r["date"], "sessions", r) for r in sessions if r.get("date")]
    return sorted(evs, key=lambda e: (e[0], e[1], repr(sorted(e[2].items(),
                                                              key=repr))))


def _in_scope(goal: dict, dataset: str, rec: dict) -> bool:
    """Does this event belong to the goal at all?

    Without this, a `distance_km` running goal would also count the kilometres
    the athlete walked, because both datasets carry a column of that name.
    """
    if (want := goal.get("dataset")) is not None and want != dataset:
        return False
    if (kind := goal.get("session_type")) is not None and rec.get("type") != kind:
        return False
    return True


def _baseline(history: dict[str, float], week: str) -> float | None:
    """Mean weekly volume over the recent weeks the athlete actually trained.

    Weeks with no recorded volume are EXCLUDED rather than averaged in as
    zeroes. Averaging in the empty weeks before a goal existed would drag the
    baseline down and make a steady, unchanged training week read as a ramp -
    the guard would fire hardest on exactly the athlete it should ignore.
    """
    monday = datetime.fromisoformat(week).date()
    prior = [
        history.get((monday - timedelta(days=7 * (i + 1))).isoformat(), 0.0)
        for i in range(BASELINE_WEEKS)
    ]
    trained = [p for p in prior if p > 0]
    # No history at all means no ramp to exceed - the guard cannot fire on the
    # first week of a goal, which would be nonsense.
    return sum(trained) / len(trained) if trained else None


def compute_contributions(goals: list[dict], thresholds: list[dict],
                          daily: list[dict],
                          sessions: list[dict]) -> tuple[list[dict], list[dict]]:
    """(contributions, milestones) for every event against the goals in force.

    Every event is judged against `state(event_date)` - the goals as they stood
    THAT day - so a goal declared in June never retroactively judges May, and
    editing a target today leaves every past contribution untouched (G20).
    """
    contributions: list[dict] = []
    milestones: list[dict] = []

    # Per-goal running state: counted progress per period bucket, weekly totals
    # of raw volume for the ramp baseline, and milestones already minted.
    progress: dict[str, dict[str, float]] = {}
    weekly_volume: dict[str, dict[str, float]] = {}
    minted: set[tuple[str, str, float]] = set()

    for when, dataset, rec in _events(daily, sessions):
        in_force = state(goals, thresholds, when)
        for goal in in_force.measured_goals():
            slug, metric = goal.get("slug"), goal.get("metric")
            if not slug or not metric or verification_of(goal) in (
                    EXTERNAL, ATTESTED):
                # An external goal lives in another app; vitai tracks and
                # reinforces it but cannot verdict it from this record (G19).
                # An ATTESTED goal has no measure at all and never will - the
                # engine holds it, surfaces it and asks about it, and takes the
                # athlete's word as the only evidence there will ever be (G86).
                continue
            if not _in_scope(goal, dataset, rec):
                continue
            value = rec.get(metric)
            if value is None or isinstance(value, bool) or not isinstance(
                    value, (int, float)):
                continue

            bucket = _period_key(goal.get("period"), when)
            done = progress.setdefault(slug, {}).get(bucket, 0.0)
            row = _judge(goal, slug, when, value, done,
                         weekly_volume.setdefault(slug, {}))
            row.update({"date": when, "dataset": dataset, "goal": slug,
                        "metric": metric, "period": bucket})
            contributions.append(row)

            counted = row["counted"]
            progress[slug][bucket] = done + counted
            week = _week_key(when)
            weekly_volume[slug][week] = weekly_volume[slug].get(week, 0.0) + value

            milestones += _milestones(goal, slug, when, bucket, done,
                                      done + counted, minted)

    contributions.sort(key=lambda r: (r["date"], r["goal"], r["dataset"], r["metric"]))
    milestones.sort(key=lambda r: (r["date"], r["goal"], r["fraction"]))
    return contributions, milestones


def _judge(goal: dict, slug: str, when: str, value: float, done: float,
           volume: dict[str, float]) -> dict:
    """One event against one goal: how much of it counts, and why."""
    if value < 0:
        return {"value": value, "counted": 0.0, "contribution": REGRESSES,
                "headroom": None}
    if value == 0:
        return {"value": value, "counted": 0.0, "contribution": NEUTRAL,
                "headroom": None}

    if goal.get("policy") != "guarded":
        return {"value": value, "counted": float(value),
                "contribution": ADVANCES, "headroom": None}

    guard = goal.get("guard_pct")
    base = _baseline(volume, _week_key(when))
    if base is None or guard is None:
        # Nothing to ramp from yet: credit it, and say so via a null headroom.
        return {"value": value, "counted": float(value),
                "contribution": ADVANCES, "headroom": None}

    allowed = base * (1.0 + float(guard))
    used = volume.get(_week_key(when), 0.0)
    headroom = round(max(allowed - used, 0.0), 3)
    if used >= allowed:
        # The week's budget was already spent; this is pure unbudgeted ramp.
        return {"value": value, "counted": 0.0, "contribution": UNBUDGETED,
                "headroom": headroom}
    if used + value <= allowed:
        return {"value": value, "counted": float(value),
                "contribution": ADVANCES, "headroom": headroom}
    # Straddles the guard: the budgeted part counts, the excess does not.
    return {"value": value, "counted": round(allowed - used, 3),
            "contribution": PARTIAL, "headroom": headroom}


def _milestones(goal: dict, slug: str, when: str, bucket: str,
                before: float, after: float,
                minted: set[tuple[str, str, float]]) -> list[dict]:
    """Target fractions crossed by COUNTED progress since the last event."""
    # A COMPLETED GOAL MINTS NOTHING (#235). It is measured so its
    # achievement can be read, not scored again: passing a quarter of a target
    # already completed is not an achievement, and re-minting on every rebuild
    # is the celebratory defect this engine has taken out once already.
    if lifecycle_of(goal) == "completed":
        return []
    target = goal.get("target")
    if target is None or isinstance(target, bool) or not isinstance(
            target, (int, float)) or target <= 0:
        return []
    out: list[dict] = []
    for frac in MILESTONE_FRACTIONS:
        mark = float(target) * frac
        if before < mark <= after and (slug, bucket, frac) not in minted:
            minted.add((slug, bucket, frac))
            out.append({
                "date": when, "goal": slug, "period": bucket,
                "fraction": frac, "value": round(after, 3), "target": target,
                "label": f"{int(frac * 100)}% of {goal.get('title') or slug}",
            })
    return out


def achievement_of(counted: float | None, target: object,
                   lifecycle: str | None, days_left: int | None) -> str | None:
    """How this goal is going against its target (#235).

    DERIVED, NEVER AUTHORED. A goals line is a DECLARATION, so the engine does
    not write its opinion into one; this lands on the progress row instead.

    NOT YET UNIFIED WITH `verdicts`, and the issue asked for that. This
    derives from counted-against-target; `verdicts` still scores thresholds
    per metric-week by different code, so the two can still disagree about one
    metric. Splitting the vocabulary is what makes the unification expressible
    - both axes now have somewhere to live - but the unification itself is
    #199, which has its own settled decision about precedence and is not
    smuggled in here.

    Returns None where the engine cannot say: an attested goal nobody can
    measure, a goal drawing on a dataset the contribution engine does not
    iterate, or one with no target to be measured against. A word here would
    be an answer to a question the engine was not able to ask.
    """
    usable = (counted is not None and isinstance(target, (int, float))
              and not isinstance(target, bool))
    if not usable:
        return None
    met = float(counted) >= float(target)

    # STILL HOLDING IT. `achieved` is terminal and maintenance is not, so a
    # goal that reached its target and is keeping it had nowhere to live.
    if lifecycle == "completed":
        # STILL HOLDING IT, or nothing sayable yet. A completed goal is judged
        # against the CURRENT bucket, which is usually half-elapsed, so
        # reporting a shortfall would assert "not met" about a goal the
        # athlete closed BECAUSE it was met - and would flip on a Monday.
        # Detecting a maintenance goal that has genuinely lapsed needs the
        # period to be known-closed, which the progress row cannot see.
        return "sustaining" if met else None
    if lifecycle in ("cancelled", "rejected"):
        return "achieved" if met else "not_achieved"
    if met:
        return "achieved"
    # THE WINDOW CLOSED with the target unmet. FHIR's reading, checked rather
    # than assumed: `not-achieved` is "has not been met", which is exactly
    # this. `not-attainable` means "not possible to be met" - the modal claim
    # G58's declaration-time gate makes, which does not exist, so nothing here
    # emits that word and it is not in the vocabulary.
    if days_left is not None and days_left < 0:
        return "not_achieved"
    return "in_progress" if float(counted) > 0 else "no_progress"


def goal_progress(goals: list[dict], thresholds: list[dict], daily: list[dict],
                  sessions: list[dict], on: str,
                  events: list[dict] | None = None) -> list[dict]:
    """Per-goal standing as of `on`: counted progress in the current period.

    This is what `vitai goals` renders and what a dashboard reads. Progress is
    COUNTED progress, so a guarded goal shows what the athlete actually banked,
    not the raw volume they logged.
    """
    contributions, milestones = compute_contributions(goals, thresholds, daily,
                                                      sessions)
    in_force = state(goals, thresholds, on)
    declared, edited = _declaration_dates(goals)
    index = _event_index(events)

    rows: list[dict] = []
    for goal in in_force.goals:
        slug = goal.get("slug")
        if not slug:
            continue
        bucket = _period_key(goal.get("period"), on)
        scope, how = scope_of(goal)
        # A goal is countable only if the engine could ever score it. Three
        # ways it cannot, and all three previously reported a fabricated 0:
        # nobody can measure it (attested), another app measures it
        # (external), or it draws from a dataset the contribution engine does
        # not iterate. The contract note added in #34 already told consumers
        # an attested row has no progress - the data disagreed with it.
        settled_here = verification_of(goal) == MEASURED
        countable = settled_here and (scope is None
                                      or scope in CONTRIBUTING_DATASETS)
        counted = sum(c["counted"] for c in contributions
                      if c["goal"] == slug and c["period"] == bucket)
        unbudgeted = sum(c["value"] - c["counted"] for c in contributions
                         if c["goal"] == slug and c["period"] == bucket)
        target = goal.get("target")
        pct = None
        if (countable and isinstance(target, (int, float))
                and not isinstance(target, bool) and target):
            pct = round(100.0 * counted / float(target), 1)
        deadline, hardness, anchor = deadline_of(goal, index)
        rows.append({
            "slug": slug,
            "title": goal.get("title"),
            "metric": goal.get("metric"),
            "policy": goal.get("policy"),
            # The retired name keeps its column so a consumer reading it is
            # not broken by the split; both now come from the successor.
            "status": lifecycle_of(goal),
            "lifecycle_status": lifecycle_of(goal),
            "achievement_status": achievement_of(
                counted if countable else None, target,
                lifecycle_of(goal), days_between(on, deadline_of(goal, index)[0])),
            "period": goal.get("period"),
            "bucket": bucket,
            "target": target,
            "counted": round(counted, 3) if countable else None,
            "unbudgeted": round(unbudgeted, 3) if countable else None,
            "progress_pct": pct,
            "dataset": scope,
            "scope": how,
            "declared": declared.get(slug),
            "last_edited": edited.get(slug),
            "deadline": deadline,
            "deadline_kind": hardness,
            "days_to_deadline": days_between(on, deadline),
            "event": anchor,
            "verification": verification_of(goal),
            "motivator": goal.get("motivator"),
            "tracker": goal.get("tracker"),
            "milestones": sum(1 for m in milestones
                              if m["goal"] == slug and m["period"] == bucket),
        })
    return rows


def _declaration_dates(goals: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """(first-seen, last-seen) date per slug - "set when, last moved when"."""
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for r in sorted((r for r in goals if r.get("date")), key=order_key):
        slug = str(r.get("slug"))
        first.setdefault(slug, r["date"])
        last[slug] = r["date"]
    return first, last
