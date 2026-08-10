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


# THE COMPARATOR, AS DATA (#308). A client that persists claims outside the
# engine has to order them, and today it can only re-derive the rule from prose
# or hand-port the Python. One did the first and got it wrong: two readers took
# the ends of an append-only log as its date range, which is ARRIVAL order, and
# a third sorted - so one screen described one log two ways.
#
# WHY THE FAILURE IS QUIET, and why publishing beats documenting. Position and
# date agree on every log appended once, in order, on one device, which is
# every log anyone has today. They stop agreeing exactly when a log is restored
# from backup or merged across devices - the moment someone is already having a
# bad day and is least able to notice that their record now reports wrong
# dates.
#
# EVERY VALUE HERE NAMES A FIELD OR AN ANSWER, never a sentence to parse. A
# consumer builds a comparator from it; it is not documentation with a version
# number on it.
ORDERING_RULE = {
    # Sort on VALID time first: what day the row is about.
    "sort_on": "date",
    # Then on TRANSACTION time: when the row was written.
    "then_on": "recorded_at",
    # An unstamped row sorts BEFORE a stamped one on the same date, so a
    # legacy row yields to one that says when it was written, and a file of
    # entirely unstamped rows keeps file order under a stable sort.
    "absent_transaction_time_sorts": "before",
    # The stamp is compared as an INSTANT. As text, two rows written either
    # side of a timezone change order by wall clock rather than by when they
    # were written.
    "transaction_time_compared_as": "instant",
    # Arrival order is never the answer. This is the sentence the client that
    # filed the issue needed.
    "position_in_file_is_not_order": True,
}


def ordering_rule() -> dict:
    """How to order claims, as data rather than as code (#308).

    Published because the alternative is a client re-deriving it. The rule is
    short; it was only ever invisible.

    NOT A PORT and not a promise to run in the client: it names the fields to
    sort on and what absence means, which is what a comparator needs.
    `test_ordering_rule_is_the_comparator` runs `order_key` against every
    clause, so this cannot drift from the function it describes - a published
    rule that disagrees with the engine would be worse than none, because a
    client would conform to it and diverge.
    """
    return dict(ORDERING_RULE)


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
    # IN THE ORDER THEY WERE USED, not alphabetically. The report joins these
    # with the word "then", and a sorted set made it assert a chronology the
    # record contradicts - `zz-morning` followed by `aa-evening` rendered as
    # "aa-evening then zz-morning". Ordered by first appearance by DATE, with
    # file order breaking a tie, because that is the sequence the athlete
    # actually moved through.
    # ONE SPELLING IS NOT TWO PROTOCOLS. Comparing the raw strings meant
    # `Fasted-Post-Void` and `fasted-post-void` were two, so a rate was
    # declined as NOT COMPARABLE for an athlete who weighed the same way both
    # times. The validator does report the spelling - `protocol` must be a
    # slug - but it is a separate call, and a refusal that fires on a typo is
    # a refusal readers learn to skip past.
    #
    # THE WHOLE REGISTRY FOLD, not half of it. `vocab.resolve` normalises AND
    # decamels - `index.get(_normalise(text)) or index.get(_normalise(
    # _decamel(text)))` - so `FastedPostVoid` is one value with
    # `fasted-post-void` to every lookup in the engine. Borrowing only
    # `_normalise` left exactly the vendor and importer token shape `_decamel`
    # exists for still seaming, while the comment claimed the registry's
    # equivalence.
    #
    # A SEPARATOR FOLDS TO A WORD BOUNDARY, NEVER TO NOTHING. `post-void` and
    # `postvoid` are two protocols and must stay two; `_normalise` replaces a
    # hyphen with a space rather than deleting it, which is what keeps the fold
    # injective over slugs - a kebab slug maps one-to-one onto its token list.
    #
    # AN EMPTY FOLD IS SILENCE. `" "`, `"-"` and `"___"` all normalise to
    # nothing, and the raw-value filter above let them through as three named
    # protocols that then merged into one. A placeholder is not a procedure.
    #
    # The RAW spelling is what gets reported, because the athlete's own words
    # are what a reader should see - only the COMPARISON folds.
    from .vocab import _decamel, _normalise

    def fold(text: str) -> str:
        plain = _normalise(text)
        return plain if " " in plain else _normalise(_decamel(text))

    # ORDERED BY `order_key`, NOT BY FILE POSITION, and that is this module's
    # own acceptance criterion: "an ordering a formatter can change is not an
    # ordering". Sorting by `(date, file index)` was cosmetic while both
    # spellings were listed; now that the first one becomes the single
    # athlete-facing name, reordering two lines in a file changed the report.
    dated = sorted((r for r in rows if r.get("protocol") not in (None, "")),
                   key=order_key)
    seen: dict[str, str] = {}
    for rec in dated:
        spelling = str(rec["protocol"])
        key = fold(spelling)
        if not key:
            continue
        seen.setdefault(key, spelling)
    distinct = list(seen.values())
    named = [str(r["protocol"]) for r in dated if fold(str(r["protocol"]))]
    return {"protocols": distinct, "seam": len(distinct) > 1,
            "stated": len(named), "silent": len(rows) - len(named)}


def instrument_seam(rows: list[dict]) -> dict:
    """Did the INSTRUMENT change under this rate? (#33, item 3)

    Returns `{instruments, seam, stated, silent}` - the distinct instruments
    named in the window, whether more than one was, and how many rows said and
    did not say. Deliberately the same shape as `protocol_seam`, because it is
    the same argument one axis over and a consumer should not have to learn
    two.

    THE CALIBRATION SEAM, WHICH IS THE ONE #33 IS ABOUT. Two weight readings
    from two scales are not two samples of one series: consumer scales carry
    offsets of a kilo or more, and concatenating them puts a step at the seam
    that is arithmetically indistinguishable from real weight change. Worse,
    it lands exactly where a long gap makes a jump look plausible, so the
    engine would confirm a change that is an instrument swap.

    Measured before building: the shipped demo's recent weight window spans
    `athlete`, `scale` and a `dexa+scale` merge, and `weight_rate` scored it
    `ahead` / `behind` / `on_target` with nothing anywhere saying the readings
    came from different devices. `origin` was written for exactly this and no
    derivation read it - the same "specified, validated, never read" shape as
    `protocol` before #174 and `coverage` before #186.

    NO SIZE ESTIMATE, and the absence is the point, exactly as for `protocol`.
    Holding a table of how many kilograms an Aria reads over a Withings would
    be a per-instrument accuracy claim about equipment this engine has never
    seen, and #171 has already settled that no vendor figures are imported.
    What is knowable from the record is that the instrument changed, which is
    enough to decline the comparison.

    SILENCE IS NOT AN INSTRUMENT. Rows naming no origin are counted and
    otherwise ignored: a record that has never used the field must not acquire
    a seam the day it starts. 45% of the corpus's origin-bearing rows name a
    channel and no instrument, so the alternative would seam almost everything.

    A SEAM IS NO COMMON INSTRUMENT, not "more than one name". This is where
    the analogy with `protocol` stops, and measuring made the difference
    obvious: a canonical row can read `dexa+scale`, meaning two devices
    observed ONE reading. Counting names, the shipped demo seamed on a window
    of `scale, scale, dexa+scale, scale` - where every reading includes a
    scale observation and the series is perfectly comparable.

    So the question is whether ANY ONE instrument is behind every reading in
    the window. A corroborated reading is compatible with either series; a
    reading only one device saw, following readings only a different device
    saw, is the swap. That is the hazard #33 describes and nothing wider.

    NOT A SPLIT, and that is the lesson of #315. Splitting `weight` by
    protocol made `safety._loss_pct_per_week` pick endpoints protocol-blind
    and a RED-S hold silently stopped firing. This reports a seam and moves
    nothing.
    """
    from .provenance import PERSON, resolve_source, source_kind

    # THE REGISTRY FOLD, so one instrument spelled two ways is not two.
    # `resolve_source` is the same canonicaliser `origin_of` consumers use,
    # and borrowing half of it is what #174 already paid for here.
    #
    # A PERSON IS NOT AN INSTRUMENT, which #94 settled one issue over. A row
    # whose origin is `athlete` is the athlete writing down what they read;
    # counting that as a device seamed the shipped demo against its own
    # hand-entered rows and would have declined a rate because somebody typed
    # a number in. The transcription hazard is real and it is not a
    # calibration offset, which is what this function is about.
    def instruments(rec: dict) -> list[str]:
        raw = rec.get("origin")
        if raw in (None, ""):
            return []
        return [part for part in str(raw).split("+")
                if part.strip() and source_kind(part) != PERSON]

    dated = sorted((r for r in rows if instruments(r)), key=order_key)
    seen: dict[str, str] = {}
    per_row: list[set[str]] = []
    for rec in dated:
        folded = set()
        for spelling in instruments(rec):
            key = resolve_source(spelling)
            seen.setdefault(key, spelling)
            folded.add(key)
        per_row.append(folded)
    # The intersection across readings: empty means no single instrument was
    # behind all of them.
    common: set[str] = set(per_row[0]) if per_row else set()
    for folded in per_row[1:]:
        common &= folded
    return {"instruments": list(seen.values()),
            "seam": bool(per_row) and not common,
            "stated": len(per_row), "silent": len(rows) - len(per_row)}


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
