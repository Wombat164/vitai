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

from datetime import UTC, datetime, timedelta

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


# The smallest step a stamp can take. Microseconds are the finest resolution
# `datetime` carries, and the serialised form must show them or the increment
# would be invisible in the file.
TICK = timedelta(microseconds=1)

# How far the wall clock may sit BEHIND the last stamp before appending is
# refused rather than clamped. Sub-second overlap is the normal case in a
# write loop and is what the logical clock exists to absorb silently. A
# minute is different in kind: it means the system clock is wrong, and
# clamping thousands of rows past a wrong clock would bury the problem under
# stamps that look fine and carry a false wall time.
#
# An operational choice, not a published threshold - stated so it can be
# argued with rather than discovered.
CLOCK_SKEW_TOLERANCE = timedelta(seconds=60)


def now_stamp(now: datetime | None = None,
              after: datetime | None = None) -> str:
    """Transaction time: ISO 8601, MICROSECONDS, with an EXPLICIT offset.

    A HYBRID LOGICAL CLOCK, not a reading of the wall clock (#44). Wall time
    is used whenever it has actually moved on; otherwise the stamp is one tick
    past `after`, so a stamp is STRICTLY greater than its predecessor.

    Second resolution and a non-strict comparison are what broke this: a loop
    importing 227 weight readings produced ONE distinct value across all of
    them, because a second is an eternity in a write loop and "not older than"
    admits equal. Equal is the failure case - a tie is precisely the thing
    that makes the field useless, since ordering was the only reason for it.

    Bulk import is not an edge case here, it is how rows actually arrive:
    every source so far lands as hundreds of rows in a tight loop. A clock
    that only works when writes are a second apart does not work.

    Under load this drifts microseconds ahead of true time, which is the right
    trade. An ordering that is occasionally a few microseconds optimistic is
    strictly better than one that does not exist.

    The offset is not decoration either. A bare local timestamp is unorderable
    against one written elsewhere, and this record travels - the athlete logs
    from home, from a hotel and from a race weekend.
    """
    when = (now or datetime.now()).astimezone()
    if after is not None and when <= after:
        when = after + TICK
    return when.isoformat(timespec="microseconds")


def stamp_instant(value: object) -> datetime | None:
    """A `recorded_at` as an INSTANT, for comparing rather than string-matching.

    Two stamps written either side of a flight carry different offsets, and
    comparing them as text orders them by wall clock instead of by when they
    happened - the #38 mistake, one clock over. `+02:00` sorts after `+00:00`
    as a string no matter which came first.
    """
    when = parse_time(value)
    return when if is_aware(when) else None


def is_stamp(value: object) -> bool:
    """A valid transaction time: parseable, and carrying an offset."""
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


# Sorts before every real instant, for rows with no transaction time. Only
# ever compared against other absent rows (the boolean above it separates the
# two groups), so its value is arbitrary - it exists to keep the tuple
# comparable rather than to mean anything.
_NO_INSTANT = datetime.min.replace(tzinfo=UTC)


def order_key(rec: dict) -> tuple:
    """(valid time, has-transaction-time, transaction time) - the sort key.

    The middle element is what makes absent sort BEFORE present: `False` orders
    before `True`, so an unstamped legacy row precedes a stamped one on the
    same date, and a file of entirely unstamped rows keeps file order under a
    stable sort.

    The third is an INSTANT, not the raw string. Comparing stamps as text
    orders two rows written either side of a timezone change by wall clock
    rather than by when they were written.
    """
    stamp = rec.get("recorded_at")
    return (str(rec.get("date") or ""), stamp is not None,
            stamp_instant(stamp) or _NO_INSTANT)


def _minutes(hhmm: object) -> int | None:
    if not isinstance(hhmm, str):
        return None
    try:
        t = datetime.strptime(hhmm, "%H:%M")
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def protocol_seam(rows: list[dict]) -> dict:
    """Did the PROCEDURE change under this rate? (#174, proposal 4)

    Returns `{protocols, seam, stated, silent}` - the distinct protocols named
    in the window, whether more than one was, and how many rows said and did
    not say. A rate spanning a seam is measuring the change of procedure as
    well as the change in the athlete.

    THE CALIBRATION-SEAM ARGUMENT, ONE AXIS OVER. The engine already refuses a
    rate whose weigh-in TIMES are spread widely enough to account for it. A
    protocol change is the same defect with a discrete cause instead of a
    continuous one: `fasted-post-void` and `fed-evening-clothed` are not two
    readings of one measurand, they are two measurands, and the difference
    between them is breakfast and a pair of shoes rather than anything the
    athlete did. `protocol` was written for exactly this and nothing read it.

    NO SIZE ESTIMATE, and that absence is the point. It would be easy to hold
    a table of how many kilograms a clothed evening weigh-in adds and subtract
    it; that is a per-protocol accuracy claim about equipment and habits this
    engine has never seen, and it is the figure the project refuses to invent
    everywhere else. What is knowable from the record is that the procedure
    changed, which is enough to decline the comparison.

    SILENCE IS NOT A PROTOCOL. Rows that name none are counted and otherwise
    ignored: a record that has never used the field must not acquire a seam
    the day it starts, and a run of unnamed rows beside one named row is an
    unanchored interval rather than a change of procedure - which is what the
    rest of #174 is about, and is not decided here.
    """
    named = [str(r["protocol"]) for r in rows
             if r.get("protocol") not in (None, "")]
    distinct = sorted(set(named))
    return {"protocols": distinct, "seam": len(distinct) > 1,
            "stated": len(named), "silent": len(rows) - len(named)}


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
    # A DERIVED VALUE IS NOT A WEIGH-IN (#170). It has no measurement time
    # because nobody stood on a scale to produce it, and that is an
    # inapplicable time rather than a missing one. Counting it as unknown made
    # the engine report that part of a rate could not be checked for
    # time-of-day drift, when in fact every actual weigh-in behind that rate
    # was timed - a computed row cannot drift with the clock, so it has
    # nothing to say about whether the readings did.
    weighed = [r for r in rows if not r.get("derived_from")]
    times = [m for m in (_minutes(r.get("measured_at")) for r in weighed)
             if m is not None]
    unknown = len(weighed) - len(times)
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


# --- comparing timestamps that do not share a frame (#38) ----------------------
#
# The record holds BOTH shapes and will for a long time. The Polar connector
# wrote naive local time; the schema's own example shows an offset, so any
# writer following the documentation produces offset-aware values. The moment
# both coexist, a direct comparison raises - which means the documentation
# broke the build, the worst version of this bug because it punishes the
# correct behaviour.
#
# It also blocks its own repair: offsets cannot be backfilled row by row,
# because from the first converted row until the last, the record would hold
# both shapes and be unbuildable. The comparison has to tolerate the mixture
# BEFORE any migration can start.

def parse_time(value: object) -> datetime | None:
    """An ISO-8601 timestamp, naive or offset-aware, or None if unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_aware(when: datetime | None) -> bool:
    return when is not None and when.utcoffset() is not None


def comparable(a: datetime | None, b: datetime | None) -> tuple[
        datetime | None, datetime | None, bool]:
    """Two timestamps, and whether they can honestly be compared as instants.

    Three cases:

    - both aware -> true instants, comparable;
    - both NAIVE -> they share a frame by construction, so wall-clock order is
      instant order BETWEEN THEM. Comparable, and this is the whole existing
      record;
    - MIXED -> not comparable, and the engine says so rather than inventing
      the missing offset.

    That last decision is the substantive one, and it goes against the obvious
    repair of "attach a zone to the naive one". The tempting choices are all
    wrong in the case that actually occurs:

    - the SYSTEM zone makes the build depend on which machine ran it (CI runs
      UTC, a laptop does not), breaking determinism outright;
    - the OTHER value's offset looks clever and fails on the commonest
      pairing there is. Platforms routinely emit UTC (`...Z`) while a local
      connector writes naive local time. Lending the UTC row's +00:00 to a
      naive +02:00 row places it two hours from where it happened, and the
      error is invisible because the result still looks like a clean instant.

    A misplaced instant is worse than an absent one: it silently merges two
    activities that were an hour apart, or separates one that two platforms
    both recorded. So the timestamp test is declined and the caller falls back
    to the weaker evidence it already has, with the reason reported.

    The real repair is a DECLARED home zone, which G30 already specifies as
    effective-dated (a relocation changes it from a date forward, and past
    days keep the zone that applied then). That is a separate change with a
    config surface and a DST story; guessing one here would foreclose it.
    """
    if a is None or b is None:
        return a, b, False
    return a, b, is_aware(a) == is_aware(b)
