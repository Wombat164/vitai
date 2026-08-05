"""The week, defined once, and the weekly session rollup built on it (#208).

The read model had 32 tables and not one of them said how far the athlete ran
this week or how many sessions he did. `verdicts` was the only table with an
engine-COMPUTED `week` column, and it carries judgements rather than
quantities, so a client wanting the most ordinary chart in the genre - a
weekly bar - had to sum `sessions.distance_km` itself, bucket the dates
itself and count rows itself.

One did, and got it wrong twice in ways nothing could have caught:

- It INVENTED A TAXONOMY. `run` and `test` became "runs", anything starting
  with `gym` became "gym", and the record holds `run`, `strength`, `walk` and
  `row` - so 17 of 43 sessions matched neither bucket and vanished, taking
  their distance with them. The bars looked entirely plausible.
- It REIMPLEMENTED THE WEEK, and happened to agree with the engine's Monday.
  That is luck. Week boundaries are the engine's under effective-dated policy,
  and nothing would have told the client the day they diverged.

The type vocabulary is the engine's too, and `type_source` exists precisely
because a session's type has provenance: a label a vendor's classifier
assigned and one the athlete asserted are different facts. A client bucketing
on `type` is making a claim it has no standing to make.

WHICH IS WHY THE WEEK IS DEFINED HERE AND NOWHERE ELSE. The argument against
the client reimplementing it is not weakened by the engine having done so four
times internally: `verdicts`, `contributions`, `report` and `query` each
carried their own copy of the same arithmetic, which is three opportunities
for one of them to be corrected alone.

They were four copies of the arithmetic and TWO contracts, which is the trap
this dedup nearly walked into. Three of them raised on a value that was not a
date; `query` returned "". Unifying onto the tolerant one would have quietly
turned a named `ValueError` in `report` into a `None` bucket that renders as a
literal "None" week in the rollup, and a contextless `TypeError` three frames
deep in `verdicts`. So `week_of` raises, `week_key` does not, and every caller
keeps the contract it had.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# What the rollup counts. Deliberately not configurable: the point of the
# table is that every consumer gets the same buckets.
SESSION_WEEK_KEYS = ["week", "type", "sessions", "distance_km", "duration_s"]


def as_date(value: str | date | None) -> date | None:
    """A date, or None where the value is not one. Never raises."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def week_of(value: str | date) -> str:
    """The Monday that starts this date's week, ISO. RAISES on a non-date.

    THE ENGINE'S ONE DEFINITION OF A WEEK. Monday-anchored, matching
    `verdicts.week`, and `schema` validates any authored `week` field against
    the same anchor.

    Loud, because most callers here are bucketing rows the record says are
    dated and a value that is not a date is a defect upstream. A silent bucket
    under `None` puts a literal "None" week in the rollup and a confusing
    TypeError several frames later in `verdicts`, where the old behaviour
    named the offending value.
    """
    d = as_date(value)
    if d is None:
        raise ValueError(
            f"not a date: {value!r}. A week is bucketed from a row's `date`, "
            f"and a row this engine cannot date cannot be put in a week")
    return (d - timedelta(days=d.weekday())).isoformat()


def week_key(value: str | date | None) -> str | None:
    """`week_of`, tolerant: None where the value is not a date.

    THE SAME ARITHMETIC, a different contract, and the pair exists because
    unifying four copies onto one of them would have changed behaviour for
    three callers. `query` deliberately tolerates an undated row; `verdicts`,
    `report` and `contributions` deliberately do not, and quietly making them
    tolerant would have turned a named ValueError into a `None` bucket that
    renders as a week.
    """
    try:
        return week_of(value)
    except ValueError:
        return None


def _weeks_between(first: str, last: str) -> list[str]:
    """Every week key from one to the other inclusive, none skipped.

    The gaps are the point. A client that renders only the weeks it received
    rows for draws an x-axis where a deload week, an injured month and a dead
    connector all look like time briefly running faster.
    """
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    out = []
    while start <= end:
        out.append(start.isoformat())
        start += timedelta(days=7)
    return out


def session_weeks(sessions: list[dict],
                  on: str | date | None = None) -> list[dict]:
    """Sessions per week per type, with the empty weeks present.

    One row per (week, type), plus one row per week that has no sessions at
    all - `sessions` is 0 there, and that count is the discriminator rather
    than a null type, because a session whose type never got recorded is a
    logged session and an empty week is not.

    WHAT THIS COUNTS IS WHAT WAS LOGGED. A week of zeros says the record holds
    no sessions for it, which is not the same fact as a week the athlete did
    nothing in, and nothing here can tell those apart - that needs coverage
    (#93, #186). The rollup states the first and a consumer must not render it
    as the second.

    `distance_km` and `duration_s` are the sums of the rows that CARRY one, and
    null where none did. Summing an absent distance as zero would report a
    swim, a strength session and a broken import identically, all of them as
    having covered no ground. A count of 3 beside a distance drawn from 1 is
    the honest shape.

    `on` bounds the last week, so a rebuild of an unchanged record produces
    the same table (#207). Without it the range would end wherever the wall
    clock happened to be.
    """
    # NOTHING VANISHES QUIETLY, which is this table's whole charter: a
    # filter here would drop an undated session and its distance exactly the
    # way the client's taxonomy dropped 17 of 43. `week_of` raises and names
    # the value, which is what `report` and `verdicts` already do on the same
    # record, so a bad date fails one way rather than three.
    weeks_of = [(week_of(s.get("date")), s) for s in sessions]
    if not weeks_of:
        return []

    buckets: dict[tuple[str, str | None], dict] = {}
    for week, s in weeks_of:
        key = (week, s.get("type"))
        row = buckets.setdefault(key, {"week": key[0], "type": key[1],
                                       "sessions": 0, "distance_km": None,
                                       "duration_s": None})
        row["sessions"] += 1
        for field in ("distance_km", "duration_s"):
            value = s.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[field] = (row[field] or 0) + value

    weeks = sorted({w for w, _ in buckets})
    last = week_key(on) or weeks[-1]
    # A viewpoint BEFORE the record's last session does not truncate it. The
    # rows exist and hiding them would be the engine editing history to match
    # the day it was asked, which is not what a viewpoint is for.
    span = _weeks_between(weeks[0], max(last, weeks[-1]))

    out = []
    for week in span:
        # `str()` because a `type` that is not a string still loads: schema
        # warns and the build proceeds, and sorting an int beside a string
        # would take the whole read model down over one bad row. The same
        # coercion `api.sets` already applies, for the same reason.
        rows = sorted((r for (w, _), r in buckets.items() if w == week),
                      key=lambda r: (r["type"] is None, str(r["type"] or "")))
        out += rows or [{"week": week, "type": None, "sessions": 0,
                         "distance_km": None, "duration_s": None}]
    return out
