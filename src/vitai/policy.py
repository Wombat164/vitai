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
from .schema import (COMPARABLE, IDENTITY_KEY, NOT_COMPARABLE, OFFSET,
                     OVERLAP_BASIS, UNKNOWN_COMPETENCE)

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
        return tuple(g for g in self.goals if lifecycle_of(g) == "active")

    def measured_goals(self) -> tuple[dict, ...]:
        """Goals the engine keeps measuring, which outlives being active.

        A COMPLETED GOAL IS STILL MEASURED (#235). `achieved` was terminal and
        maintenance is not: an athlete who reached a floor and is holding it is
        in a different state from one who reached it once, and the engine could
        not tell them apart because it stopped counting the moment the goal
        left `active`. That is what made `sustaining` inexpressible - not the
        missing word, the missing measurement.

        Measured is not the same as SCORED-AGAINST. A completed goal is
        counted so its achievement can be read; it mints no milestones,
        because passing a quarter of a target you already completed is not an
        achievement, and re-minting on every rebuild would be the celebratory
        defect polarity work already took out once.
        """
        return tuple(g for g in self.goals
                     if lifecycle_of(g) in ("active", "completed"))

    def threshold(self, key: str) -> float | None:
        return self.thresholds.get(key)


# The one place `status` is read forward (#235, G89). A retirement is not done
# until every reader prefers the successor, and re-implementing the fallback at
# each reader is how `hip_pain` ended up dual-active in five modules rather than
# retired in one.
#
# `achieved` SPLITS, which is the whole point of the change: it was an
# achievement value in a lifecycle list, so forward it becomes lifecycle
# `completed`, and the achievement half is derived on the progress row rather
# than carried here.
LIFECYCLE_FORWARD = {
    "proposed": "proposed",
    "active": "active",
    "paused": "on_hold",
    "abandoned": "cancelled",
    "achieved": "completed",
}


def lifecycle_of(goal: dict) -> str | None:
    """Where this goal is in its own life, successor first.

    Prefers `lifecycle_status`; falls back to mapping the retired `status`
    forward. Returns None when a line carries neither, which validation
    refuses on a new line and cannot happen on an old one.
    """
    declared = goal.get("lifecycle_status")
    if declared:
        return str(declared)
    old = goal.get("status")
    return LIFECYCLE_FORWARD.get(str(old), str(old)) if old else None


def capability(rows: list[dict], origin: str, measures: str,
               on: str | date, condition: str | None = None) -> dict:
    """What this instrument was competent at, as of `on` (#171).

    Returns the capability row in force, or a synthesised `unknown` one. Never
    None: a consumer asking "can this device measure sleep" gets an answer with
    a competence in the vocabulary rather than a null it has to interpret.

    NO DEFAULT OUTSIDE THE RECORD, and this is the whole of the #148 lesson
    carried one dataset over. There, baselines lived in a mutable file outside
    the append-only record and dated rows overlaid it, so any week with no
    dated row was judged by whatever that file said TODAY - a reconstruction of
    March returning March's data under September's policy. A capability default
    in `semantics/` would be the identical defect: effective-dating that a
    default escapes is not effective-dating.

    So silence resolves to `unknown`, which is a value IN the vocabulary and
    distinct from `absent`. "Nobody has said" and "it does not measure this"
    are different facts and a consumer can act on both.

    DATED THROUGH `_in_force`, the same machinery policy already uses: last
    line per identity whose date is on or before `on`, ordered by valid time
    with transaction time breaking ties. Shared because getting effective
    dating right twice is how the two implementations drift; the identity and
    the storage are NOT shared, for the reason #335 gives.

    `condition` scopes the question. A wrist sensor can measure heart rate
    seated and be a proxy for it at threshold, so a statement is about one
    instrument measuring one thing under one condition - and asking without a
    condition asks about the unconditioned statement rather than about all of
    them.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    want = (str(origin), str(measures), condition)
    for row in _in_force(rows, "capabilities", on_s).values():
        if (str(row.get("origin")), str(row.get("measures")),
                row.get("condition")) == want:
            return row
    return {"origin": str(origin), "measures": str(measures),
            "condition": condition, "competence": UNKNOWN_COMPETENCE,
            "construct": None, "basis": None, "date": None,
            # SAID RATHER THAN INFERRED FROM A NULL DATE. A consumer that has
            # to work out whether a row was stated is a consumer that will get
            # it wrong on the row where it matters.
            "stated": False}


def _earns_its_status(row: dict) -> bool:
    """Is this row entitled to the weight `comparability` gives `comparable`
    and `offset` - LIFTING a refusal - or is it only entitled to whatever a
    `not_comparable` row already is, the record's default?

    FAIL CLOSED (#373 review), and written here because this is the first
    dataset in this engine where the distinction matters. `jsonl.load`
    quarantines a line that fails to PARSE and nothing else; a line that
    parses but fails the SCHEMA - `basis` not `overlap`, no `overlap_ref` -
    comes through it untouched, because `build`/`verdicts` read a dataset
    straight off `load`, not off `validate_record`. For every dataset before
    this one that was harmless: a schema-invalid row could only be dropped
    from a POSITIVE claim (a capability nobody can act on, a goal nobody can
    read), never used to weaken a REFUSAL that was protecting something. This
    dataset's whole job is to lift the instrument-seam refusal, so a row
    that has not earned the two conditions #171 requires for that - a
    `basis` of `overlap` and a named `overlap_ref` - must not be able to
    lift it merely by writing `comparable` in the status column. A hand-
    written line with `basis: "stated"` and no `overlap_ref` verified this in
    the review that found it: it lifted the seam, and the verdict for the
    week it spanned came back `ahead` on a difference two different scales
    produced, not the athlete.

    A gate derived from data the record itself supplies has to distrust that
    data the same way any other input does - GATES MUST FAIL CLOSED - and a
    row is the record's data regardless of whether a human or a script wrote
    the line. `not_comparable` needs no such gate: it can only ADD to a
    refusal that is already the default, never weaken one, so a row claiming
    it is honoured regardless of `basis` - `vitai validate` still reports it
    as malformed, which is a different question from whether the SEAM stays
    refused.
    """
    if row.get("status") not in (COMPARABLE, OFFSET):
        return True
    overlap_ref = row.get("overlap_ref")
    return (row.get("basis") == OVERLAP_BASIS
           and isinstance(overlap_ref, str) and bool(overlap_ref.strip()))


def comparability(rows: list[dict], field: str, origin_a: str, origin_b: str,
                  on: str | date) -> dict:
    """Are these two instruments on the same footing for this field? (#33 item 2)

    Returns the comparability row in force, or a synthesised `not_comparable`
    one. Never None, for exactly `capability`'s reason one dataset over: a
    consumer asking whether a rate can span a scale change gets an answer in
    the vocabulary rather than a null it has to interpret.

    SILENCE RESOLVES TO `not_comparable`, and that is #33's whole acceptance
    criterion rather than an engineering default. Comparability is EARNED BY
    OVERLAP - a period of simultaneous measurement from both instruments,
    recorded in this record - never assumed because two readings share a
    field name. A comparability table shipped in `semantics/` would be #148's
    defect one dataset over: effective-dating that a default escapes is not
    effective-dating, so there is no default outside the record.

    A ROW THAT HAS NOT EARNED ITS STATUS IS ALSO SILENCE (`_earns_its_status`,
    #373 review). `comparable` and `offset` LIFT a refusal, so a row claiming
    either one is honoured only where it satisfies the conditions that make
    the claim earned rather than asserted; anything else is treated as
    ABSENT from this question rather than downgraded to `not_comparable` in
    place. The filter runs AFTER `_in_force`, which has already picked the
    one surviving row per LITERAL identity - so within one identity (one
    order of `origin_a`/`origin_b`) an unearned row contributes nothing at
    all, there being no earlier row of that same identity left to fall back
    to. What it cannot shadow is the OTHER identity this question straddles:
    `(a, b)` and `(b, a)` are stored separately, and an unearned, later-dated
    row on one of them must not win the cross-identity tie-break in
    `matches` over an earned row still standing on the other - a downgrade
    in place would let it, by keeping it in the pool with a later `date`.
    This is the one dataset here where that distinction is load-bearing:
    every dataset before it could only lose a POSITIVE claim to a schema
    failure, never gain a weakened REFUSAL from one.

    ORDER-INSENSITIVE IN THE PAIR, deliberately, though the identity stored
    on a row is not: `(field, origin_a, origin_b)` and
    `(field, origin_b, origin_a)` are two different identities as far as
    `_in_force`/`supersedes` are concerned, because whether a scale is
    comparable to a DEXA is one fact about the PAIR regardless of which one
    somebody typed first when they wrote it down - asking (dexa, scale) is
    the same question as asking (scale, dexa). So the match here is by SET
    rather than by tuple order, and where more than one in-force row answers
    (because both orders were written as separate lines), the most recently
    dated one wins - the same tie-break `_in_force` already applies within
    one identity, reapplied by hand across the two identities this question
    can straddle.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    want = frozenset({str(origin_a), str(origin_b)})
    matches = [
        row for row in _in_force(rows, "comparability", on_s).values()
        if str(row.get("field")) == str(field)
        and frozenset({str(row.get("origin_a")), str(row.get("origin_b"))})
        == want
        and _earns_its_status(row)]
    if matches:
        return max(matches, key=order_key)
    return {"field": str(field), "origin_a": str(origin_a),
            "origin_b": str(origin_b), "status": NOT_COMPARABLE,
            "bias": None, "spread": None, "basis": None, "overlap_ref": None,
            "date": None,
            # SAID RATHER THAN INFERRED FROM A NULL DATE, `capability`'s own
            # reasoning: a consumer that has to work out whether a row was
            # stated is a consumer that will get it wrong on the row where it
            # matters.
            "stated": False}


def all_comparable(rows: list[dict], field: str, instruments: list[str],
                   on: str | date) -> bool:
    """Does EVERY pair among `instruments` resolve to `comparable`? (#33 item 3)

    The gate the weight-rate seam refusal (`verdicts.compute_verdicts`) and
    its report-layer mirror (`report.build_report`) both call, so the two
    surfaces cannot drift on what "every pair" means. `offset` is not enough
    here and never will be: it records that a cross-instrument difference was
    MEASURED, not that the two sides may be read as one series, and applying
    a measured offset to a reading would be fabricating a measurement (P4).
    Only `comparable` lifts the refusal.

    WHAT IS NOT SHARED IS THIS FUNCTION'S OWN `on` - each caller resolves its
    own viewpoint and hands it in, and the two used to disagree (#373 review):
    `compute_verdicts` passed `wk`, the Monday of the week whose rate it
    judges, and `report.build_report` passed `today`, the moment the report
    is generated. A `comparable` row dated partway through a week is in force
    by `today` but not yet by that week's Monday, so the rollup read it as
    lifted while the verdicts table for the identical week still refused -
    two surfaces giving two answers about one record, which is exactly what
    sharing this gate was supposed to make impossible. It was never
    impossible: sharing the PAIRWISE DEFINITION does not share the
    VIEWPOINT, and this function has no way to enforce the second half from
    inside itself; it can only be as consistent as its callers choose to be.
    Both now ask as of the week under judgment, matching `policy.state`'s own
    rule that a judgment uses the policy in force THEN rather than the policy
    in force when someone happens to be reading - callers are responsible for
    passing the SAME `on` for the SAME window, and a caller that judges a
    different window (a live "as of right now" surface with no week of its
    own) is free to pass `today`; nothing here would catch it.

    Vacuously true for zero or one instrument. That cannot happen where this
    is called today - `clocks.instrument_seam` only reports a seam once at
    least two distinct instruments are behind one window - but it is stated
    rather than left to an empty `combinations()` call reading as an
    accident.
    """
    from itertools import combinations

    named = sorted({str(i) for i in instruments})
    return all(comparability(rows, field, a, b, on)["status"] == COMPARABLE
              for a, b in combinations(named, 2))


def instrument(rows: list[dict], origin: str, on: str | date) -> dict | None:
    """The instrument reporting as `origin` on `on`, or None (#311).

    NONE IS AN ANSWER HERE, and this is where it parts company with
    `capability` one dataset over. A capability question always gets a row
    back, synthesised as `unknown` if nobody has spoken, because "nobody said
    this watch measures sleep" is a fact a consumer must be able to act on. An
    unregistered instrument is different: the register adds a NAME and a
    provenance to an identity that already works without it. Returning a
    hollow row would dress up an empty register as a populated one, and the
    issue's requirement is that an unregistered origin still renders, just
    with less - which is what a caller does with None.

    RESOLVED ON `origin` ALONE, never on `source`. The issue proposed `source
    or origin`, and that `or` crosses the line contract 40 drew: `source` is
    the CHANNEL a value arrived by, `origin` is the INSTRUMENT that observed
    it. 4331 of 9673 origin-bearing rows in the corpus name a channel and no
    instrument, so the fallback would have answered for all of them - and a
    re-export or a new app, which is a channel change, would have resolved to
    a different instrument and read as an instrument change. That is the
    confound this register exists to remove, manufactured by the register.

    NOT `_in_force`, deliberately, though the dataset is dated. That machinery
    answers "the last statement on or before this date", which is right for a
    policy that stays in force until replaced. An instrument is an INTERVAL
    with an end: the watch sold in 2029 did not keep reporting into 2030
    merely because no line replaced it. Reading a closed interval as
    last-one-wins is exactly the silently-confident error the issue names.
    """
    on_s = on.isoformat() if isinstance(on, date) else str(on)
    want = str(origin)
    for row in rows:
        if str(row.get("origin")) != want:
            continue
        first, last = row.get("from_date"), row.get("to_date")
        if not isinstance(first, str) or first > on_s:
            continue
        # An open interval has not ended. `to_date` absent means the
        # instrument is still in use, which is why it is not defaulted.
        if last is None or str(last) >= on_s:
            return row
    return None


def _in_force(records: list[dict], dataset: str, on: str) -> dict[str, dict]:
    """Last line per identity whose date is on or before `on`.

    Ordered by (date, recorded_at) - valid time then transaction time (#37).
    Sorting was by date alone, which meant two lines sharing a date resolved
    by FILE POSITION, and a sort, a reformat or a merge could silently change
    which one won. `sorted` is stable and the key is constant across unstamped
    rows, so a legacy file still resolves exactly as it did.

    A TUPLE IDENTITY IS AN IDENTITY. This read `r.get(ident)` with whatever
    `IDENTITY_KEY` declared, which returns None for the tuple-keyed datasets -
    `sets`, `meals` and now `capabilities` - so every one of their rows was
    silently skipped and the function returned nothing. It has only ever been
    called with scalar-keyed datasets, so the gap cost nothing and was
    invisible; it is the shape that stops the machinery being reusable, which
    is the one thing #171 wanted from it.

    A row is skipped when its identity is ABSENT. For a tuple that means every
    component is None: a partly-stated identity is a validation problem rather
    than a row to drop here, and `capabilities.condition` is legitimately null
    - an unconditioned statement is a statement.
    """
    ident = IDENTITY_KEY[dataset]
    parts = ident if isinstance(ident, tuple) else (ident,)
    out: dict[str, dict] = {}
    for r in sorted((r for r in records if r.get("date") and r["date"] <= on),
                    key=order_key):
        values = tuple(r.get(k) for k in parts)
        if all(v is None for v in values):
            continue
        out[str(values[0]) if len(values) == 1 else str(values)] = r
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
