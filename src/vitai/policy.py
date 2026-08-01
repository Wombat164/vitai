"""Dated policy: what the athlete was aiming at, and when.

The increment-1 correction to a real flaw (G14, generalized by G20): goals,
calorie targets, macros and thresholds used to be current-state (vitai.toml
and prose in plan.md), so editing one silently rewrote how every past day had
been judged. That destroys the audit chain - the record could no longer answer
"what was I attaining THAT day", and a rebuild after loosening a target would
retroactively turn old misses into hits.

Here policy is effective-dated data. `state(on)` reconstructs the goals and
thresholds in force on a date, so a judgment uses the policy that was actually
in force THEN. Loosening a goal today changes today forward and nothing else.

HOW FAR THAT GOES, precisely, because the sentence above is easy to read as
more than it is (#148). It holds for a key on a date that HAS a dated row.
A week carrying no row for a threshold still falls through to whatever
`vitai.toml` says today, and most of `Config` - the rate phases, the
resolution ladder, suppressed metrics, the check tolerance, the intake
buffer - has no dated history to fall back TO. So editing a threshold in
September still re-judges every historical week that lacked an explicit row:
a reconstruction of March returns March's data under September's policy.

That is a correctness problem in the reconstruction itself, not only in
staleness detection, and it is open. `config.policy_digest` makes it
detectable in the meantime; finishing G14 - snapshotting a toml change into
the record when it happens, so `state` is TOTAL - is the fix.

The second half is that goalpost-moving is itself a signal (G20). The athlete
owns the record and nothing blocks an edit - but churn is derived and a
loosening timed right after a miss is FLAGGED, so the coach can ask about it
rather than silently accept it. The flag invites a question; it never accuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .clocks import order_key
from .schema import IDENTITY_KEY

HARD, SOFT = "hard", "soft"

# Which way is "easier" for a threshold. A FLOOR (walk at least 9000 steps) is
# loosened by lowering it; a CAP (keep easy runs under 152 bpm, keep pain under
# 3) is loosened by raising it. Without this the engine cannot tell a genuine
# re-plan from a quiet retreat - the delta alone has no sign.
THRESHOLD_POLARITY: dict[str, str] = {
    "steps_floor": "floor",
    "sleep_floor_h": "floor",
    "protein_g_target": "floor",
    "easy_hr_cap": "cap",
    "rhr_baseline": "cap",
    "pain_gate": "cap",
}

# A threshold and the verdict metric it governs are named differently (the
# threshold is `steps_floor`, the weekly verdict is `steps`). The suspicion
# check needs the verdict's name to ask "was this metric missed just before
# the edit", so the mapping is explicit rather than guessed by prefix.
THRESHOLD_METRIC: dict[str, str] = {
    "steps_floor": "steps",
    "sleep_floor_h": "sleep",
    "pain_gate": "pain_gate",
    "easy_hr_cap": "easy_hr",
    "rhr_baseline": "rhr",
}

LOOSENED, TIGHTENED, UNCHANGED, UNKNOWN = "loosened", "tightened", "unchanged", "unknown"

# How long after a missed week a loosening still reads as a reaction to it.
SUSPICION_WINDOW_DAYS = 7


@dataclass(frozen=True)
class State:
    """The policy in force on one date - the answer to "what was I aiming at"."""

    on: str
    goals: tuple[dict, ...]
    thresholds: dict[str, float]

    def goal(self, slug: str) -> dict | None:
        for g in self.goals:
            if g.get("slug") == slug:
                return g
        return None

    def active_goals(self) -> tuple[dict, ...]:
        return tuple(g for g in self.goals if g.get("status") == "active")

    def threshold(self, key: str) -> float | None:
        return self.thresholds.get(key)


def _in_force(records: list[dict], dataset: str, on: str) -> dict[str, dict]:
    """Last line per identity whose date is on or before `on`.

    Ordered by (date, recorded_at) - valid time then transaction time (#37).
    Sorting was by date alone, which meant two lines sharing a date resolved
    by FILE POSITION, and a sort, a reformat or a merge could silently change
    which one won. `sorted` is stable and the key is constant across unstamped
    rows, so a legacy file still resolves exactly as it did.
    """
    ident = IDENTITY_KEY[dataset]
    out: dict[str, dict] = {}
    for r in sorted((r for r in records if r.get("date") and r["date"] <= on),
                    key=order_key):
        if (slug := r.get(ident)) is not None:
            out[str(slug)] = r
    return out


def state(goals: list[dict], thresholds: list[dict], on: str | date) -> State:
    """Reconstruct the goals and thresholds in force on `on`.

    A policy line takes effect ON its own date. Lines dated after `on` are
    invisible here - that is the whole point: a past day never sees a target
    that did not exist yet.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    goal_heads = _in_force(goals, "goals", on_s)
    thr_heads = _in_force(thresholds, "thresholds", on_s)
    return State(
        on=on_s,
        goals=tuple(goal_heads[s] for s in sorted(goal_heads)),
        thresholds={k: v["value"] for k, v in sorted(thr_heads.items())
                    if v.get("value") is not None},
    )


def context_on(context: list[dict], on: str | date) -> dict | None:
    """The situational mode in force on a date (G34), or None if unrecorded.

    Context is a timeline like every other policy: the mode in force is the
    latest line dated on or before `on`. It exists so the engine can EXPLAIN
    missingness instead of flagging it - a week with no weigh-in while the
    facilities line says there was no scale is not a lapse, and treating it
    as one teaches the athlete that the record punishes honesty about
    circumstances.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    live = [c for c in context if c.get("date") and c["date"] <= on_s]
    if not live:
        return None
    return sorted(live, key=order_key)[-1]


def has_facility(context: list[dict], on: str | date, facility: str) -> bool | None:
    """Was a facility available on this date? None when context is silent.

    None and False are different answers and must not collapse: "we do not
    know" is not "there was no scale".
    """
    current = context_on(context, on)
    if current is None or current.get("facilities") is None:
        return None
    have = {f.strip() for f in str(current["facilities"]).replace(",", " ").split()}
    return facility in have


def days_between(on: str, when: str | None) -> int | None:
    """Days from `on` to a date; negative once it has passed, None if unset.

    A countdown is the practical value of a hard date: it is what a taper is
    planned backwards from, and "how long have I got" is the question the
    athlete actually asks. Derived at read time, never stored.
    """
    if not isinstance(when, str):
        return None
    try:
        return (datetime.fromisoformat(when).date()
                - datetime.fromisoformat(on).date()).days
    except ValueError:
        return None


def events_on(events: list[dict], on: str | date) -> tuple[dict, ...]:
    """The fixtures known on a date, soonest first - what a plan aims at (G86).

    Effective-dated like all policy: a line takes effect on its own `date`, and
    the fixture itself falls on `event_date`. Both matter and they are usually
    months apart, which is why they are separate fields.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    heads = _in_force(events, "events", on_s)
    live = [e for e in heads.values() if e.get("status") != "cancelled"]
    return tuple(sorted(live, key=lambda e: (str(e.get("event_date") or ""),
                                             str(e.get("slug") or ""))))


def _event_index(events: list[dict] | None) -> dict[str, dict]:
    """Latest line per event slug, regardless of date - the anchor lookup.

    Deliberately NOT as-of filtered: a goal edited in April that anchors to a
    race declared in May still points at a real fixture, and refusing to
    resolve it would report the goal as having no deadline at all.
    """
    out: dict[str, dict] = {}
    for e in sorted((e for e in (events or []) if e.get("date")),
                    key=order_key):
        if (slug := e.get("slug")) is not None:
            out[str(slug)] = e
    return out


def deadline_of(goal: dict, events: dict[str, dict] | None = None) -> tuple[
        str | None, str | None, str | None]:
    """(deadline, hardness, source) for a goal - resolving any event anchor.

    An anchored goal takes the fixture's date, and that date is HARD whenever
    the event says it is immovable: an organiser's race date is not the
    athlete's to move, so the hardness is derived rather than re-declared.
    An explicit `deadline_kind` on the goal still wins - the athlete may hold
    themselves to a soft interpretation of a fixed date, and saying so is
    exactly the kind of thing this field exists to record.
    """
    declared = goal.get("deadline_kind")
    anchor = (events or {}).get(str(goal.get("event") or ""))
    if anchor is not None:
        hardness = declared or (HARD if anchor.get("immovable") else None)
        return (anchor.get("event_date") or goal.get("deadline"), hardness,
                str(goal.get("event")))
    return goal.get("deadline"), declared, None


def _direction(kind: str, key: str, before: float | None, after: float | None) -> str:
    """Did this edit make the policy easier or harder to satisfy?"""
    if before is None or after is None:
        return UNKNOWN
    if after == before:
        return UNCHANGED
    # A goal target is something to reach, so it behaves like a floor.
    polarity = "floor" if kind == "goal" else THRESHOLD_POLARITY.get(key, "")
    if not polarity:
        return UNKNOWN
    easier = after < before if polarity == "floor" else after > before
    return LOOSENED if easier else TIGHTENED


def _behind_weeks(verdicts: list[dict] | None) -> dict[str, list[str]]:
    """metric -> the ISO-week Mondays that metric was judged behind."""
    out: dict[str, list[str]] = {}
    for row in verdicts or []:
        if row.get("verdict") == "behind" and row.get("metric") and row.get("week"):
            out.setdefault(row["metric"], []).append(row["week"])
    return {k: sorted(v) for k, v in out.items()}


def _follows_a_miss(metric: str, edit_date: str, behind: dict[str, list[str]]) -> bool:
    """Was there a missed week for this metric just before the edit?"""
    try:
        edited = datetime.fromisoformat(edit_date).date()
    except ValueError:
        return False
    for week in behind.get(metric, []):
        try:
            week_end = datetime.fromisoformat(week).date() + timedelta(days=6)
        except ValueError:
            continue
        if 0 <= (edited - week_end).days <= SUSPICION_WINDOW_DAYS:
            return True
    return False


def _edits(records: list[dict], dataset: str, kind: str,
           value_key: str, metric_of,
           events: dict[str, dict] | None = None) -> list[dict]:
    """Consecutive-line diffs per identity, oldest first, declaration excluded."""
    ident = IDENTITY_KEY[dataset]
    chains: dict[str, list[dict]] = {}
    for r in sorted((r for r in records if r.get("date")), key=order_key):
        if (slug := r.get(ident)) is not None:
            chains.setdefault(str(slug), []).append(r)

    rows: list[dict] = []
    for slug in sorted(chains):
        chain = chains[slug]
        ordinal = 0
        for prev, cur in zip(chain, chain[1:]):
            # A line explicitly marked a correction fixes a mis-entry; it is
            # not the athlete changing their mind, so it is not churn (G31).
            if cur.get("change_kind") == "correction":
                continue
            ordinal += 1
            before, after = prev.get(value_key), cur.get(value_key)
            direction = _direction(kind, slug, before, after)
            was, _, _ = deadline_of(prev, events) if kind == "goal" else (None,) * 3
            now, hardness, _ = deadline_of(cur, events) if kind == "goal" else (None,) * 3
            deadline_pushed = (isinstance(was, str) and isinstance(now, str)
                               and now > was)
            # A pushed deadline only reads as a LOOSENING when the date was
            # HARD. A race date cannot move, so moving it is a retreat from
            # something real; a date the athlete invented is a direction of
            # travel they may revise at no cost to anyone, and calling that
            # goalpost-moving is a trust-destroying false accusation (G86).
            #
            # When hardness is UNKNOWN the engine says so and stops there. The
            # push is still recorded as the fact it is, so a coach can ask "was
            # that a hard date?" - which is the G89 shape: accumulate the
            # evidence, surface it, do not decide on the athlete's behalf.
            reads_as_retreat = deadline_pushed and hardness == HARD
            rows.append({
                "slug": slug,
                "kind": kind,
                "date": cur["date"],
                "edit_no": ordinal,
                "metric": metric_of(cur, slug),
                "before": before,
                "after": after,
                "direction": LOOSENED if reads_as_retreat and direction in
                             (UNCHANGED, UNKNOWN) else direction,
                "deadline_pushed": deadline_pushed,
                "deadline_kind": hardness,
                "reason": cur.get("reason"),
                "set_by": cur.get("set_by"),
            })
    return rows


def plan_churn(goals: list[dict], thresholds: list[dict],
               verdicts: list[dict] | None = None,
               events: list[dict] | None = None) -> list[dict]:
    """One row per policy EDIT: what moved, which way, and whether to ask.

    `suspicious` fires when a loosening (or a pushed HARD deadline) lands
    within a week of a week that metric was judged behind - the "moved the
    goalposts right after a bad week" pattern. It is a prompt, never a verdict:
    the row carries the athlete's own `reason` so an explained change reads as
    what it is. An edit with no stated reason is exactly the one worth asking
    about.

    A CORRECTION is not churn at all and never reaches these rows (G31/#26):
    it asserts the retired line was never a real intention, so counting it
    would manufacture a plan-stability problem out of a fixed typo.
    """
    behind = _behind_weeks(verdicts)
    index = _event_index(events)
    rows = _edits(goals, "goals", "goal", "target",
                  lambda rec, slug: rec.get("metric"), events=index)
    rows += _edits(thresholds, "thresholds", "threshold", "value",
                   lambda rec, slug: THRESHOLD_METRIC.get(slug, slug))
    for row in rows:
        loosened = row["direction"] == LOOSENED
        row["suspicious"] = bool(
            loosened and _follows_a_miss(str(row["metric"] or ""), row["date"], behind)
        )
        row["unexplained"] = bool(loosened and not row.get("reason"))
    rows.sort(key=lambda r: (r["date"], r["kind"], r["slug"]))
    return rows
