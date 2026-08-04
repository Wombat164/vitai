"""Reads over sets, and the numbers that must refuse to be computed (#100).

Increment 4 of #59. The arithmetic here is ordinary; what earns the module its
keep is that every derivation declines to produce a figure where the figure
would be a confident wrong answer. That is #60's finding generalised into the
derivation layer.

## Three live cases

**"66 kg went from 8 reps to 12 between Tuesday and Thursday"** was established
by reading two prose notes side by side. That is a query, not a read.

**A descending set series read as maximal and was not.** Set 1 sat against a
stated max and looked like one; set 2 held 92% of it, where a set taken to
genuine failure leaves 55-70%. The failure to REFUSE the maximal reading is
what manufactured a false fact. The arithmetic that recovered the truth is the
easy half.

**A tonnage sum across an evening's blocks** would add back-extension stack
kilos to leg-press stack kilos to bodyweight push-ups: three numbers on three
incomparable scales, summed into one figure nobody can defend.

## Every load resolves to a SCALE

    mass              external, and the resolvable bodyweight variants.
                      Kilograms. Comparable across time, exercises, machines.
    stack(machine M)  a pin number on M. Comparable within M only.
    ordinal(machine M) a resistance level on M. Comparable within M, and only
                      as ORDER - never as a ratio.

A stack number and a mass are both spelled in kilograms and are not the same
kind of thing, which is exactly why summing them looks reasonable right up
until someone acts on the total.

## Refusals, never silent skips

A derivation that quietly drops the rows it cannot handle produces a total
that is wrong in the direction of looking fine. So every refusal is a named
finding carrying the rows and the reason, and a caller that ignores findings
gets subtotals that visibly do not add up rather than a grand total that
silently does.
"""

from __future__ import annotations

from .sets import set_type_of

MASS = "mass"
STACK = "stack"
ORDINAL = "ordinal"

# The machine-scoped field that IS the load. `seat_pos`, `pad_pos` and
# `lever_pos` are also machine-scoped (#99) and are CONFIGURATION - they say
# how the machine was set up, not what the resistance was. Treating them as
# the scale meant that recording where the seat went reclassified a perfectly
# summable pin load as an un-multipliable ordinal, and disabled progression
# for that machine entirely.
ORDINAL_LOAD = "resistance_level"

# Load types whose number is kilograms of resistance, once resolved.
MASS_LOADS = ("external", "bodyweight_plus")

# The set types that are evidence of a maximal effort AT ALL. `amrap` is
# defined by its endpoint, which is what makes it eligible - but eligible is
# not sufficient: the `failure` field still has to say the body stopped it.
MAXIMAL_SET_TYPES = ("working", "amrap", "backoff", "drop", "rest_pause",
                     "myo_rep", "cluster")

# A set is evidence of a maximum only when the athlete says a rep was
# attempted and could not be completed. `volitional` is explicitly NOT, and
# the reason is that NOTHING WAS TESTED rather than that reps were left: the
# set ended because he stopped it, which is the commonest ending and is
# usually at perceived failure with `rir: 0`. Null means nobody said, which is
# the case that manufactured a false max.
MAXIMAL_FAILURES = ("muscular", "technical")


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def scale_of(rec: dict) -> tuple[str, str | None]:
    """The scale this set's load lives on: (kind, machine).

    The machine is part of the SCALE, not a label on it. Two stack numbers
    from different machines are two different units that happen to share a
    spelling, and the only way to stop them being added is to make the unit
    itself carry the machine.
    """
    machine = str(rec.get("machine") or "") or None
    if rec.get(ORDINAL_LOAD) is not None:
        if rec.get("load_type") == "machine_stack":
            # Two load-bearing numbers on one row, on different scales. Not
            # something to pick a winner for silently.
            return ("ambiguous", machine)
        return (ORDINAL, machine)
    if rec.get("load_type") == "machine_stack":
        return (STACK, machine)
    if rec.get("load_type") in MASS_LOADS or rec.get("load_type") in (
            "bodyweight", "assisted"):
        return (MASS, None)
    # A bare number with no `load_type` could be a mass or a pin. "Nobody
    # said" is applied to `failure`; it applies here too, and promoting it to
    # kilograms would put an unlabelled stack number beside barbell kilos.
    return ("unstated", None)


def scale_name(scale: tuple[str, str | None]) -> str:
    kind, machine = scale
    return kind if machine is None else f"{kind}({machine})"


def is_maximal_evidence(rec: dict) -> bool:
    """May this set be read as evidence of a maximum?

    THE refusal this increment exists for. A set logged without a `failure`
    read as maximal against a stated max and was not: the next set held 92% of
    it, where genuine failure leaves 55-70%.

    `null` means nobody said. `volitional` means the athlete ended the set,
    which is usually at PERCEIVED failure - `rir: 0` and no rep attempted.
    Neither is evidence of a limit: one because nobody said, the other because
    nobody found out. Treating either as one manufactures a fact the athlete
    never claimed, which is how a real record acquired a max several reps
    below the truth.

    Note the direction. Reading `volitional` as sub-maximal is the mirror
    error and loses the same information: at `rir: 0` he believed there were
    none left, and the honest answer is that the question was not put.
    """
    return (rec.get("failure") in MAXIMAL_FAILURES
            and set_type_of(rec) in MAXIMAL_SET_TYPES)


def reps_of(rec: dict) -> int:
    """Reps COMPLETED, which is what volume counts.

    An attempted rep that failed is the most informative thing in a stack
    progression and it is not volume: nothing was lifted through it.
    """
    return _int(rec.get("reps_completed")) or 0


def _finding(kind: str, detail: str, rows: list[dict]) -> dict:
    return {"kind": kind, "detail": detail,
            "rows": [{"date": r.get("date"), "exercise": r.get("exercise"),
                      "set_index": r.get("set_index")} for r in rows]}


def bodyweight_on(weight_rows: list[dict], on: str,
                  window_days: int = 14) -> float | None:
    """The athlete's mass around a date, from the resolved weight TREND.

    A trend rather than the nearest morning (P6): body mass swings about a
    kilogram within a day, so a single reading is a worse estimate of the load
    on a push-up than the average of the fortnight around it.

    None when there is nothing near enough. The caller must then DECLINE
    rather than assume a mass - a made-up bodyweight propagates into every
    tonnage figure that touches it and is invisible once it has.
    """
    from datetime import date as _date

    try:
        when = _date.fromisoformat(str(on))
    except (TypeError, ValueError):
        return None
    near = []
    for row in weight_rows:
        kg = _num(row.get("kg"))
        if kg is None:
            continue
        try:
            day = _date.fromisoformat(str(row.get("date")))
        except (TypeError, ValueError):
            continue
        if abs((day - when).days) <= window_days:
            near.append(kg)
    return sum(near) / len(near) if near else None


def resolved_load(rec: dict, weight_rows: list[dict]) -> tuple[float | None, str]:
    """(kilograms, basis) for a set on the MASS scale, or (None, why not).

    `bodyweight` resolves against the athlete's mass on the day, which is the
    only way a push-up carries a load at all - and it is also why push-ups get
    easier across a cut for reasons that have nothing to do with strength.

    The result is MODELLED, not measured (P3), and says so. A resolved
    bodyweight tonnage must never sit beside barbell kilos as an equal figure.
    """
    kind = rec.get("load_type")
    load = _num(rec.get("load"))
    if load is not None and load < 0:
        return (None, f"a load of {load:g} is negative")
    if kind in MASS_LOADS:
        if load is None:
            return (None, "no load recorded")
        if kind == "bodyweight_plus":
            body = bodyweight_on(weight_rows, str(rec.get("date")))
            if body is None:
                return (None, "no weight data near this date to add to")
            return (body + load, "modelled")
        return (load, "measured")
    if kind == "bodyweight":
        body = bodyweight_on(weight_rows, str(rec.get("date")))
        if body is None:
            return (None, "no weight data near this date")
        return (body, "modelled")
    if kind == "assisted":
        if load is None:
            # "Nobody said how much" is not "no assistance". Treating it as
            # zero tonnages an assisted pull-up as an unassisted one, which is
            # the direction that overstates the work.
            return (None, "assistance is not stated, and unstated is not zero")
        body = bodyweight_on(weight_rows, str(rec.get("date")))
        if body is None:
            return (None, "no weight data near this date to subtract from")
        if load >= body:
            # Clamping to zero manufactures a figure from a row that cannot
            # be right. A data fault gets named.
            return (None, f"assistance ({load:g}) is at least the athlete's "
                          f"mass ({body:.1f}), which cannot be right")
        return (body - load, "modelled")
    return (None, f"load_type {kind!r} is not on the mass scale")


def progression(rows: list[dict], exercise: str,
                machine: str | None = None) -> dict:
    """The (load, reps, failure) trajectory for one exercise over time.

    MACHINE-SCOPED BY DEFAULT. Sets of one exercise spread across two machines
    are two series, and splicing them into one produces a trend that describes
    neither. When the rows span machines and the caller has not scoped, this
    refuses and names them rather than picking one.
    """
    from .exercises import resolve_exercise

    want = resolve_exercise(exercise)
    mine = [r for r in rows if resolve_exercise(r.get("exercise")) == want]
    if machine is not None:
        mine = [r for r in mine if str(r.get("machine") or "") == machine]
    findings: list[dict] = []
    scales = {scale_of(r) for r in mine}
    # MORE THAN ONE SCALE, full stop. Scoping to a machine used to be enough
    # to pass a mass set and a stack set through as one trajectory - the
    # refusal bypassed by the very scoping its own message recommends.
    if len(scales) > 1:
        findings.append(_finding(
            "cross_scale_progression",
            "these sets are on more than one scale ("
            + ", ".join(sorted(scale_name(s) for s in scales))
            + "), and a series across them describes neither. Scope the query "
              "to one machine, or ask about one kind of load", mine))
        return {"exercise": want, "machine": machine, "points": [],
                "findings": findings}
    points = [{
        "date": r.get("date"), "set_index": r.get("set_index"),
        "load": _num(r.get("load")), "load_type": r.get("load_type"),
        "scale": scale_name(scale_of(r)),
        "reps_completed": reps_of(r),
        "reps_attempted": _int(r.get("reps_attempted")),
        "failure": r.get("failure"),
        "maximal_evidence": is_maximal_evidence(r),
    } for r in sorted(mine, key=lambda r: (str(r.get("date") or ""),
                                           _int(r.get("set_index")) or 0))]
    return {"exercise": want, "machine": machine, "points": points,
            "findings": findings, "sessions": len({p["date"] for p in points})}


def working_weight(rows: list[dict], exercise: str) -> dict:
    """The load the athlete is currently working at, with its failure state.

    `working` sets only: a warm-up is not the working weight and a drop-set
    segment is a load chosen because the working one had just been reached.
    The failure state travels with the number because "80 kg for 8" means
    something different depending on whether 8 was all there was.
    """
    from .exercises import resolve_exercise

    want = resolve_exercise(exercise)
    mine = [r for r in rows
            if resolve_exercise(r.get("exercise")) == want
            and set_type_of(r) == "working"]
    if not mine:
        return {"exercise": want, "load": None,
                "detail": "no working sets recorded for this exercise - "
                          "warm-ups and drop sets are not the working weight"}
    # A load nothing was completed at is not a working weight - it is the
    # attempt that established the ceiling. Without this the heaviest row in
    # the block wins, which for a stack progression is the FAILED set.
    done = [r for r in mine if reps_of(r) > 0]
    if not done:
        attempted = any((_int(r.get("reps_attempted")) or 0) > 0 for r in mine)
        return {"exercise": want, "load": None,
                "detail": ("every working set of this exercise was an attempt "
                           "with nothing completed - a load that was not "
                           "lifted is not a working weight") if attempted else
                          ("no working set of this exercise records how many "
                           "reps were completed, and unstated is not zero")}
    latest = max(str(r.get("date") or "") for r in done)
    today = [r for r in done if str(r.get("date") or "") == latest]
    # Heaviest WITHIN ONE SCALE. `max` over the raw number ranked a pin of 66
    # above 60 kg, which is the comparison this whole module refuses.
    scales = {scale_of(r) for r in today}
    if len(scales) > 1:
        return {"exercise": want, "load": None, "date": latest,
                "detail": "the working sets on this date are on more than one "
                          "scale (" + ", ".join(sorted(scale_name(s)
                                                       for s in scales))
                          + "), so there is no single heaviest - ask about one "
                            "kind of load"}
    heaviest = max(today, key=lambda r: _num(r.get("load")) or 0.0)
    if _num(heaviest.get("load")) is None:
        return {"exercise": want, "load": None, "date": latest,
                "scale": scale_name(scale_of(heaviest)),
                "reps": reps_of(heaviest),
                "failure": heaviest.get("failure"),
                "maximal_evidence": is_maximal_evidence(heaviest),
                "detail": "these sets carry no load figure - a bodyweight "
                          f"movement has no working weight beyond the "
                          f"athlete's own mass ({reps_of(heaviest)} reps on "
                          f"{latest})"}
    return {"exercise": want, "date": latest,
            "load": _num(heaviest.get("load")),
            "scale": scale_name(scale_of(heaviest)),
            "reps": reps_of(heaviest),
            "failure": heaviest.get("failure"),
            "maximal_evidence": is_maximal_evidence(heaviest),
            "sessions": len({str(r.get("date")) for r in mine})}


def volume(rows: list[dict]) -> dict:
    """Sets and completed reps per exercise.

    Volume is scale-free - a rep is a rep - so this is the one figure here
    that sums across everything without refusing. A null-failure set counts
    fully: it happened, and counting it is not the same as reading it as a
    maximum.
    """
    from .exercises import resolve_exercise

    out: dict[str, dict] = {}
    for row in rows:
        key = resolve_exercise(row.get("exercise"))
        entry = out.setdefault(key, {"exercise": key, "sets": 0, "reps": 0,
                                     "failed_attempts": 0})
        entry["sets"] += 1
        entry["reps"] += reps_of(row)
        if reps_of(row) == 0 and (_int(row.get("reps_attempted")) or 0) > 0:
            entry["failed_attempts"] += 1
    return {"by_exercise": [out[k] for k in sorted(out)],
            "sets": sum(e["sets"] for e in out.values()),
            "reps": sum(e["reps"] for e in out.values())}


def tonnage(rows: list[dict], weight_rows: list[dict] | None = None) -> dict:
    """Load x reps, PER SCALE, and never one total.

    THE refusal that gives this module its shape. A grand total here would add
    stack kilos to mass kilos to another machine's stack - three units sharing
    a spelling - and the sum is a number nobody can defend, arrived at by
    arithmetic nobody would defend if it were written out.

    So the return carries subtotals and no `total` key at all. Not a total set
    to None, which a consumer would render as zero: the key is absent, so a
    caller asking for one gets a KeyError rather than a plausible figure.
    """
    weight_rows = weight_rows or []
    buckets: dict[str, dict] = {}
    findings: list[dict] = []
    unresolved: dict[str, list[dict]] = {}
    for row in rows:
        scale = scale_of(row)
        name = scale_name(scale)
        reps = reps_of(row)
        if scale[0] == "ambiguous":
            unresolved.setdefault(
                "the row carries both a resistance level and a stack load, "
                "which are two different scales", []).append(row)
            continue
        if scale[0] == "unstated":
            unresolved.setdefault(
                "there is no 'load_type', so this number could be kilograms "
                "or a pin position", []).append(row)
            continue
        if scale[0] == STACK and scale[1] is None:
            # THE refusal this module exists for, and it was walking straight
            # through: two pin numbers with no machine named merged into one
            # `stack` bucket and summed. A stack number without its machine
            # has no scale at all.
            unresolved.setdefault(
                "a stack load with no 'machine' has no scale - a pin number "
                "is only a number on one machine", []).append(row)
            continue
        if scale[0] == ORDINAL:
            # An ordinal has no zero and no established spacing, so it cannot
            # be multiplied by anything. Level 15 for 20 minutes is not 300 of
            # a unit.
            unresolved.setdefault("ordinal", []).append(row)
            continue
        if scale[0] == MASS:
            load, basis = resolved_load(row, weight_rows)
            if load is None:
                unresolved.setdefault(basis, []).append(row)
                continue
        else:
            load, basis = _num(row.get("load")), "measured"
            if load is None:
                unresolved.setdefault("no load recorded", []).append(row)
                continue
        if basis == "modelled":
            # P3: a resolved bodyweight is a MODELLED estimate, and it must
            # not sit beside barbell kilos as an equal. Summed together, an
            # 80 kg athlete's push-ups dominate the figure with a number
            # nobody weighed - and the total then moves when they cut, for
            # reasons that have nothing to do with training. Its own bucket.
            name = f"{name}(modelled)"
        entry = buckets.setdefault(name, {
            "scale": name, "tonnage": 0.0, "sets": 0, "basis": set()})
        entry["tonnage"] += load * reps
        entry["sets"] += 1
        entry["basis"].add(basis)

    for reason, rows_out in sorted(unresolved.items()):
        findings.append(_finding(
            "not_summable" if reason == "ordinal" else "unresolved_load",
            ("a machine ordinal has no zero and no established spacing, so it "
             "cannot be multiplied into a tonnage" if reason == "ordinal"
             else f"{reason}, so these sets contribute nothing rather than "
                  "an assumed figure"),
            rows_out))
    if len(buckets) > 1:
        findings.append(_finding(
            "no_grand_total",
            "these subtotals are on different scales ("
            + ", ".join(sorted(buckets))
            + ") and do not add up. There is no total, deliberately",
            []))
    return {"by_scale": [{**b, "basis": sorted(b["basis"])}
                         for _, b in sorted(buckets.items())],
            "findings": findings}


def ordinal_change(before: dict, after: dict, field: str = "resistance_level"
                   ) -> dict:
    """The change in a machine ordinal, expressed as STEPS and never a ratio.

    "Level 15 is 15/13 of level 13" is not a valid inference even where the
    arithmetic looks proportional: the scale is not established to be linear,
    or to have a zero. Steps are what an ordinal supports, so steps are what
    this returns - and it refuses outright across machines.
    """
    from .modifiers import comparable

    if not comparable(before, after, field):
        return {"field": field, "steps": None,
                "detail": "these two are not on one machine's scale, so the "
                          "difference between them is not a quantity"}
    a, b = _num(before.get(field)), _num(after.get(field))
    if a is None or b is None:
        return {"field": field, "steps": None,
                "detail": "one of these sets does not state the value"}
    return {"field": field, "steps": b - a, "from": a, "to": b,
            "machine": before.get("machine"),
            "detail": f"{abs(b - a):g} step(s) "
                      f"{'up' if b > a else 'down' if b < a else 'unchanged'} "
                      "on this machine's own scale. The spacing between steps "
                      "is not established, so this is an order, not a ratio"}
