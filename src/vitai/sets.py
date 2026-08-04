"""The set is the atom (#97, increment 1 of #59).

Anything coarser cannot answer the questions this record has already asked.
Three live cases, all of which lived in prose because the schema had nowhere
to put them:

**A failed attempt has no home.** `73 FAILED` after `66x12` is the single most
informative set of a stack progression - an attempted load that could not be
completed - and there was no field for it. An attempted set that was not
completed is DATA, not absence, and it is a different fact from a set that was
never attempted (no row at all).

**A set logged against a stated max read as maximal, and was not.** Push-ups
of 13, 12, 10 against a stated max of 12: set 1 looked like a maximum, but set
2 held 92% of it, where a set taken to genuine failure typically leaves
55-70%. The real max was nearer 15-17. There was no way to say "this was not
taken to failure", so the truth had to be reconstructed by arithmetic
afterwards - which is the definition of a fact the schema failed to hold.

**Everything else was a note string.** "66 kg went from 8 reps to 12 between
Tuesday and Thursday" was worked out by reading two prose notes side by side.

## The two distinctions that earn the schema its keep

**Attempted vs completed.** Attempted counts reps INITIATED, including one
that failed mid-rep; completed counts reps finished. `73 FAILED` with nothing
completed is `reps_attempted: 1, reps_completed: 0, failure: "muscular"`.

**Failure is three states, not a flag.** `technical` (form broke first),
`muscular` (a rep was attempted and could not be completed) and `volitional`
(the athlete ended the set) are three different events, and "to failure" is
ambiguous across all three.

`volitional` names the MECHANISM and says nothing about reserve; `rir`
carries that. The commonest way a set ends is that someone judges he cannot
do another without starting one and finding out, which is `volitional` with
`rir: 0` - not a contradiction, and not `muscular`, because `muscular`
asserts a rep was attempted and lost. A `volitional` set must not be read as
sub-maximal without checking `rir`, which is the mirror of the rule below. `null` means UNSTATED - and a null-failure set must never be
read as maximal by anything downstream. That refusal is #100's to enforce;
this module's job is that the field exists and is first-class.

## Loads do not all mean the same thing

`load_type` is a CLOSED enum in code, unlike `set_type` next door in a
registry. It answers exactly one question - how does this number resolve to a
resistance - and there is no sixth answer to discover:

- `external` - a mass, comparable across time and across gyms;
- `bodyweight` - the load IS the athlete, so `load` is null and resolves
  against their weight on that date. It also means push-ups get easier as an
  athlete cuts from 83 to 73 kg, for reasons that have nothing to do with
  strength;
- `bodyweight_plus` - weighted dips: `load` is the ADDED mass;
- `assisted` - the effective load is bodyweight MINUS the assistance;
- `machine_stack` - **a pin number, not a mass** (#60). 66 on two machines is
  two different loads, which is why the machine travels with the number.
"""

from __future__ import annotations

from .anatomy import SIDES
from .clocks import is_stamp
from .exercises import problems as exercise_problems
from .vocab import registry, resolve

DATASET = "sets"

# Three states, because "to failure" is ambiguous across all three and the
# ambiguity produced a wrong inference on a real record within a day.
FAILURE_KINDS = ("technical", "muscular", "volitional")

# Closed by construction: how a number resolves to a resistance.
LOAD_TYPES = ("external", "bodyweight", "bodyweight_plus", "assisted",
              "machine_stack")

# One laterality axis, aligned with `anatomy.SIDES`, plus alternating work.
# `null` is UNSTATED and is never defaulted to bilateral - #99 must not add a
# second axis for the same question under another name.
SIDE_VALUES = tuple(sorted(set(SIDES) | {"alternating"}))

UNKNOWN = "unknown"


def set_type_of(rec: dict) -> str:
    """The registry set type, or `unknown` for an unfamiliar one.

    Never an error. Strength methodology coins set types faster than any
    sample, so an unrecognised term is a gap in `set_types.toml` rather than a
    fault in the athlete's record.
    """
    return resolve("set_types", "types", rec.get("set_type")) or UNKNOWN


def set_types() -> list[str]:
    return sorted(registry("set_types").get("types") or {})


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def position(rec: dict) -> str:
    """The reference a `supersedes` correcting this set would name.

    Delegates to `jsonl.identity_of`, which is the ONE renderer. This existed
    as a second implementation and spelled a null differently, so a reference
    computed here named nothing when `line_key` read it - a correction that
    matches no line, failing quietly, on the ordinary logging path.

    Imported inside the function because `jsonl` reaches this module through
    `schema`, and a module-level import would close the cycle.
    """
    from .jsonl import identity_of
    return identity_of(DATASET, rec) or ""


def attempted(rec: dict) -> int | None:
    """Reps initiated, falling back to reps completed where only one is given.

    A row that says only "12" is saying twelve were done and, absent any
    statement otherwise, twelve were tried. Inferring the reverse - that a
    stated `reps_attempted` implies the same number completed - would invent
    the completion of a rep that may have failed, which is the whole point.
    """
    tried = _int(rec.get("reps_attempted"))
    # `is not None`, not truthiness: a stated zero is a STATEMENT, and reading
    # it as unstated then falls through to the completed count, contradicting
    # the very number the athlete wrote down.
    return tried if tried is not None else _int(rec.get("reps_completed"))


def is_failed_attempt(rec: dict) -> bool:
    """Reps were initiated and none were completed - `73 FAILED`.

    Distinguishable from a set that was never attempted, which is the absence
    of a row.
    """
    return (_int(rec.get("reps_completed")) == 0
            and (_int(rec.get("reps_attempted")) or 0) > 0)


def says_it_was_maximal(rec: dict) -> bool:
    """Did the athlete state this set ended because it could not continue?

    Deliberately narrow, and deliberately NOT the inverse of "was it easy".
    Only `muscular` and `technical` are endpoints the body imposed; a
    `volitional` stop and an UNSTATED one are both "nobody said", and reading
    either as a maximum is the defect that produced a wrong push-up max.
    """
    return rec.get("failure") in ("muscular", "technical")


def problems(rec: dict) -> list[str]:
    """Validation for one set."""
    out: list[str] = []
    if not str(rec.get("exercise") or "").strip():
        out.append("'exercise' names the movement, and a set of nothing is "
                   "not a set")
    else:
        # The vocabulary lives in exercises.py (#98). An unfamiliar movement
        # is a FINDING rather than an error - the row is kept either way, and
        # it is what makes a restriction checkable against a set.
        out += exercise_problems(rec)

    done, tried = _int(rec.get("reps_completed")), _int(rec.get("reps_attempted"))
    for key in ("reps_completed", "reps_attempted"):
        value = rec.get(key)
        if value is not None and _int(value) is None:
            out.append(f"'{key}' is a whole number of reps, got {value!r}")
        elif _int(value) is not None and _int(value) < 0:
            out.append(f"'{key}' cannot be negative, got {value!r}")
    if done is not None and tried is not None and done > tried:
        out.append(f"'reps_completed' ({done}) exceeds 'reps_attempted' "
                   f"({tried}) - a rep cannot be finished without being started")
    if (not (tried or 0) and not (done or 0)
            and not (_int(rec.get("duration_s")) or 0)):
        # A plank has no reps and a bench press has no duration, but a row
        # with neither says nothing happened - and neither does a row that
        # states zero of both, which used to validate clean and then print
        # "0 reps", the exact reading the FAILED branch exists to prevent.
        out.append("a set needs reps or a 'duration_s' greater than zero - a "
                   "row claiming none of either says nothing happened. A "
                   "FAILED attempt is 'reps_attempted' 1 or more with "
                   "'reps_completed' 0")
    if _int(rec.get("set_index")) is None:
        # REQUIRED, a deliberate tightening of #97's field list. The position
        # tuple is the only thing that lets a `supersedes` name one set out of
        # four, and a row with no index shares an identity with every other
        # unnumbered set of the same exercise - so correcting one retires them
        # all. That is #43 exactly, and it cost real data once. A set nobody
        # can name is a set nobody can correct.
        out.append("'set_index' is the set's position in its block, and it is "
                   "required: without it a correction naming this set retires "
                   "every other unnumbered set of the same exercise")

    start = rec.get("session_start")
    if start is not None and not is_stamp(start):
        # The leading identity field. Two spellings of one instant fork the
        # identity, so a correction citing the other spelling names no line.
        out.append("'session_start' is an ISO 8601 instant with an explicit "
                   f"offset, the same shape as sessions.start_time - got "
                   f"{start!r}")

    kind = rec.get("load_type")
    if kind is not None and kind not in LOAD_TYPES:
        out.append(f"'load_type' is one of {', '.join(LOAD_TYPES)}, "
                   f"got {kind!r}")
    load = _num(rec.get("load"))
    if rec.get("load") is not None and load is None:
        out.append(f"'load' is a number, got {rec.get('load')!r}")
    elif load is not None and load < 0:
        out.append(f"'load' cannot be negative, got {rec.get('load')!r} - "
                   "assistance is recorded as its magnitude under "
                   "load_type 'assisted', not as a negative load")
    if kind == "bodyweight" and load is not None:
        out.append("load_type 'bodyweight' means the load IS the athlete, so "
                   "'load' is null and resolves against their weight on the "
                   "day - use 'bodyweight_plus' for added mass")
    if kind == "bodyweight_plus" and load is None:
        out.append("load_type 'bodyweight_plus' records the ADDED mass, so it "
                   "needs a 'load'")
    if kind == "machine_stack" and not str(rec.get("machine") or "").strip():
        # A stack number is not a mass: 66 on two machines is two different
        # loads, so the value carries its machine or it cannot be compared
        # with anything at all (#60).
        out.append("load_type 'machine_stack' is a pin number rather than a "
                   "mass, so it needs a 'machine' to be a number about")
    if kind == "machine_stack" and str(rec.get("load_unit") or "").lower() in (
            "kg", "kgs", "kilogram", "kilograms", "lb", "lbs", "pound",
            "pounds"):
        # A mass unit on a pin number is the #60 error written down: it makes
        # the value look comparable across machines, which is the one thing it
        # is not.
        out.append(f"load_unit {rec.get('load_unit')!r} states a MASS, and a "
                   "machine stack number is a pin position - leave it null or "
                   "name the machine's own scale")

    if (f := rec.get("failure")) is not None and f not in FAILURE_KINDS:
        out.append(f"'failure' is one of {', '.join(FAILURE_KINDS)}, or null "
                   f"for unstated - got {f!r}")
    if (s := rec.get("side")) is not None and s not in SIDE_VALUES:
        out.append(f"'side' is one of {', '.join(SIDE_VALUES)}, or null for "
                   f"unstated - got {s!r}")
    if rec.get("set_type") is not None and set_type_of(rec) == UNKNOWN:
        out.append(f"unknown set type {rec.get('set_type')!r} - one of "
                   f"{', '.join(set_types())}, or add an alias to "
                   "semantics/set_types.toml")

    rir = rec.get("rir")
    if rir is not None and (_int(rir) is None or _int(rir) < 0):
        out.append(f"'rir' is reps in reserve, a whole number 0 or more, "
                   f"got {rir!r}")
    rpe = _num(rec.get("rpe"))
    if rec.get("rpe") is not None and (rpe is None or not 0 <= rpe <= 10):
        out.append(f"'rpe' is a 0-10 scale, got {rec.get('rpe')!r}")
    for key in ("block", "round", "set_index", "rest_s", "duration_s"):
        value = rec.get(key)
        if value is not None and (_int(value) is None or _int(value) < 0):
            out.append(f"'{key}' is a whole number 0 or more, got {value!r}")

    # RIR and RPE are alternative expressions of the same thing and are never
    # converted silently. Stated together they should agree, on the standard
    # RIR-anchored scale where RPE 10 is zero in reserve. An ADVISORY, not an
    # error: an athlete who uses both loosely is not making a data error.
    if _int(rir) is not None and rpe is not None:
        implied = 10 - _int(rir)
        if abs(implied - rpe) > 2:
            out.append(f"advisory: 'rir' {rir} implies about RPE {implied} on "
                       f"the RIR-anchored scale, and 'rpe' says {rpe} - both "
                       "are kept as stated and neither is converted")
    return out
