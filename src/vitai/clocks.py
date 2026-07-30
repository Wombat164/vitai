"""The three clocks a record needs, and only one of them is `date`.

The bug that found this: two `goals` rows shared an effective date, one
superseding the other, and NOTHING IN THE DATA said which won. Resolution
fell back to file order - which is real information right up until a sort, a
reformat, a merge or a git conflict resolution rewrites it, silently changing
what the record asserts. An ordering a formatter can change is not an
ordering.

The tempting repair - put a time on `date` - is wrong, because `date` is
already answering two questions and only one of them wants a clock:

| Clock | Question | Granularity | Set by |
|---|---|---|---|
| valid time (`date`) | when did this become true | a day | the athlete |
| transaction time (`recorded_at`) | when was this line written | full | the machine |
| observation time (`start_time`, `measured_at`) | when was it measured | full | the device |

Forcing a time onto `date` would make the athlete state something they do not
know and never meant - "I decided this at 14:32" is a fact about a keystroke,
not about the goal. And it still would not sort, because **valid time is not
monotonic and must not be**: a line written today about a decision made last
week is legitimately backdated.

Transaction time is monotonic by construction and never authored by a human,
which is exactly what a tie-break needs. Together the two make the record
bitemporal in Snodgrass's sense, which buys something P2 wants and could not
previously do: tell "what the record said on 30 July, as we understood it
then" apart from "as we understand it now" - a corrected history from a
rewritten one.

## Absent sorts before present

Every existing line has no `recorded_at`, so the migration must be a READ
NO-OP. With the key constant across all legacy rows, Python's stable sort
preserves file order exactly as before, and a stamped row sorts after an
unstamped one on the same date - which is right, because the stamped one was
demonstrably written later.
"""

from __future__ import annotations

from datetime import datetime

# Body mass swings on the order of a kilogram between morning-fasted and
# evening across a normal day. This is an ORDER-OF-MAGNITUDE anchor from the
# general observation that diurnal variation runs about 1-2% of body mass -
# it is not a personal calibration, and the engine does not pretend it is.
#
# It exists to answer one question honestly: could the SPREAD of weigh-in
# times account for the rate being reported? A cut targeting 0.67 kg/week
# against weigh-ins scattered from 07:00 to 19:00 is reading a number the
# timing alone could have produced. That is a fabricated trend in the P4
# sense, and the engine must say so rather than print the figure.
DIURNAL_KG_PER_DAY = 1.0
WAKING_HOURS = 12.0

# Above this spread, tightening the weigh-in routine is a real action the
# athlete can take. Below it the routine is already tight and a caveat that
# tells them to fix it would be blaming the wrong thing.
WIDE_SPREAD_H = 2.0


def now_stamp(now: datetime | None = None) -> str:
    """Transaction time: ISO 8601, seconds, with an EXPLICIT offset.

    The offset is not decoration. A bare local timestamp is unorderable
    against one written in another timezone, and this record travels - the
    athlete logs from home, from a hotel and from a race weekend.
    """
    return (now or datetime.now()).astimezone().isoformat(timespec="seconds")


def is_stamp(value: object) -> bool:
    """A valid transaction time: parseable, and carrying an offset."""
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def order_key(rec: dict) -> tuple:
    """(valid time, has-transaction-time, transaction time) - the sort key.

    The middle element is what makes absent sort BEFORE present: `False` orders
    before `True`, so an unstamped legacy row precedes a stamped one on the
    same date, and a file of entirely unstamped rows keeps file order under a
    stable sort.
    """
    stamp = rec.get("recorded_at")
    return (str(rec.get("date") or ""), stamp is not None, str(stamp or ""))


def _minutes(hhmm: object) -> int | None:
    if not isinstance(hhmm, str):
        return None
    try:
        t = datetime.strptime(hhmm, "%H:%M")
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def weigh_in_timing(rows: list[dict]) -> dict:
    """How consistent were the weigh-in times behind a rate? (#37)

    Returns `{known, unknown, spread_h, drift_kg}`. `drift_kg` is what the
    spread alone could account for - the number that decides whether a rate is
    worth printing without a caveat.

    Deliberately no "consistent vs inconsistent" verdict on a made-up cutoff.
    The codebase has been bitten twice by hand-rolled thresholds with no
    published basis (G85 for algorithms), so this reports the observed spread
    and the arithmetic consequence, and lets the caller compare it against the
    rate actually being claimed.
    """
    times = [m for m in (_minutes(r.get("measured_at")) for r in rows)
             if m is not None]
    unknown = len(rows) - len(times)
    spread_h = (max(times) - min(times)) / 60.0 if len(times) > 1 else 0.0
    return {
        "known": len(times),
        "unknown": unknown,
        "spread_h": round(spread_h, 2),
        "drift_kg": round(spread_h / WAKING_HOURS * DIURNAL_KG_PER_DAY, 2),
    }


def timing_caveat(timing: dict, rate_kg_week: float) -> str | None:
    """The sentence a rate must carry when its weigh-in times cannot support it.

    Two ways a rate is not trustworthy, and they need different wording:

    - the times are UNKNOWN, so the engine cannot check at all. It says that,
      rather than implying the number is clean;
    - the times are known and SPREAD widely enough that the drift alone rivals
      the rate. Printing "losing 0.67 kg/week" from weigh-ins scattered across
      the day is reporting the clock, not the athlete.

    Silence is the third outcome and the common one: a consistent morning
    routine needs no caveat, and adding one to every line would train the
    reader to skip it.
    """
    if timing["known"] == 0:
        return ("Weigh-in times are not recorded, so this rate cannot be "
                "checked for time-of-day drift - a shift from evening to "
                "morning weigh-ins alone moves the scale about a kilogram.")
    if timing["unknown"]:
        return (f"{timing['unknown']} of these weigh-ins have no recorded "
                "time, so part of this rate cannot be checked for "
                "time-of-day drift.")
    if timing["drift_kg"] >= abs(rate_kg_week):
        said = (f"Weigh-ins span {timing['spread_h']:.1f} h, which alone can "
                f"account for about {timing['drift_kg']:.2f} kg - as much as "
                f"the {abs(rate_kg_week):.2f} kg/week this line reports, so "
                "the trend is not yet separable from weigh-in timing.")
        # Advice only where there is something to act on. Telling an athlete
        # who already weighs within half an hour to "be more consistent" is
        # noise, and it is not what made the rate unreadable - a very small
        # rate is. Saying so and stopping is the honest version.
        if timing["spread_h"] >= WIDE_SPREAD_H:
            said += " Weigh at a consistent time before reading it as progress."
        return said
    return None
