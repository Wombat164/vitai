"""Dated policy: what the athlete was aiming at, and when.

The increment-1 correction to a real flaw (G14, generalized by G20): goals,
calorie targets, macros and thresholds used to be current-state (vitai.toml
and prose in plan.md), so editing one silently rewrote how every past day had
been judged. That destroys the audit chain - the record could no longer answer
"what was I attaining THAT day", and a rebuild after loosening a target would
retroactively turn old misses into hits.

Here policy is effective-dated data. `state(on)` reconstructs the goals and
thresholds in force on a date, so every judgment uses the policy that was
actually in force THEN. Loosening a goal today changes today forward and
nothing else.

The second half is that goalpost-moving is itself a signal (G20). The athlete
owns the record and nothing blocks an edit - but churn is derived and a
loosening timed right after a miss is FLAGGED, so the coach can ask about it
rather than silently accept it. The flag invites a question; it never accuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .schema import IDENTITY_KEY

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

    Sorting is by date only: `sorted` is stable, so two lines sharing a date
    keep file order and the later-appended one wins. That keeps a rebuild
    byte-identical (working rule 6) without needing a tiebreak field.
    """
    ident = IDENTITY_KEY[dataset]
    out: dict[str, dict] = {}
    for r in sorted((r for r in records if r.get("date") and r["date"] <= on),
                    key=lambda r: r["date"]):
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
           value_key: str, metric_of) -> list[dict]:
    """Consecutive-line diffs per identity, oldest first, declaration excluded."""
    ident = IDENTITY_KEY[dataset]
    chains: dict[str, list[dict]] = {}
    for r in sorted((r for r in records if r.get("date")), key=lambda r: r["date"]):
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
            deadline_pushed = (
                kind == "goal"
                and isinstance(prev.get("deadline"), str)
                and isinstance(cur.get("deadline"), str)
                and cur["deadline"] > prev["deadline"]
            )
            rows.append({
                "slug": slug,
                "kind": kind,
                "date": cur["date"],
                "edit_no": ordinal,
                "metric": metric_of(cur, slug),
                "before": before,
                "after": after,
                "direction": LOOSENED if deadline_pushed and direction in
                             (UNCHANGED, UNKNOWN) else direction,
                "deadline_pushed": deadline_pushed,
                "reason": cur.get("reason"),
                "set_by": cur.get("set_by"),
            })
    return rows


def plan_churn(goals: list[dict], thresholds: list[dict],
               verdicts: list[dict] | None = None) -> list[dict]:
    """One row per policy EDIT: what moved, which way, and whether to ask.

    `suspicious` fires when a loosening (or a pushed deadline) lands within a
    week of a week that metric was judged behind - the "moved the goalposts
    right after a bad week" pattern. It is a prompt, never a verdict: the row
    carries the athlete's own `reason` so an explained change reads as what it
    is. An edit with no stated reason is exactly the one worth asking about.
    """
    behind = _behind_weeks(verdicts)
    rows = _edits(goals, "goals", "goal", "target",
                  lambda rec, slug: rec.get("metric"))
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
