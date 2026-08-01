"""How a set was configured, and the numbers that only mean something on one
machine (#99, increment 3 of #59).

Two live cases, and the second is the one with teeth.

**An incline press loses its incline.** The qualifier either vanished or fused
into prose, and a fused name is a vocabulary that multiplies by the size of
every axis it swallows - which is why `exercises.toml` refuses
`incline_dumbbell_bench_press` and why this file has to exist for that refusal
to mean anything.

**A crosstrainer at resistance level 15, against 13 a session earlier.** The
variable that dominated the session had nowhere to live, so distance alone
read as a marginal gain when +15.4% resistance with +4.7% cadence is
meaningfully more work.

## Machine-scoped values are not quantities

`resistance_level`, `seat_pos`, `pad_pos` and `lever_pos` are ordinals on one
manufacturer's scale. Level 15 on this crosstrainer is not level 15 on that
one, and it is not 15/13 of level 13 even where the arithmetic looks
proportional - the scale is not established to be linear, or even to have a
zero.

So a machine-scoped value REQUIRES its `machine`. A number that cannot say
which machine it came from is a confident wrong answer waiting for a consumer,
and #60 filed it because it had already produced one. The comparison refusals
belong to #100; this module owns the validation rule and the storage shape.

The portable ones - `angle_deg` - carry a unit in the name and mean the same
thing everywhere, which is exactly what makes them a different kind of field
rather than a stricter version of the same one.

## Absent is absent

No modifier is defaulted, ever. An unstated equipment is unknown, not
`barbell`; an unstated angle is unknown, not `flat`. A default here would put
a claim nobody made into a field a query will later trust, which is the
record-wide rule (`settings.toml`, #83's assist field) applied to two more
columns.
"""

from __future__ import annotations

from .vocab import registry, resolve

REGISTRY = "modifiers"
UNKNOWN = "unknown"

# Categorical axes shipped in this increment. `grip`, `grip_width`, `stance`,
# `position`, `rom` and `assistance` are specified in #99 and held back: an
# axis with no case behind it is a guess about what someone will want.
CATEGORICAL = ("equipment", "angle_class")

# A number that means nothing without the machine it was read off. The rule is
# not "prefer a machine" - it is that the value is uninterpretable without one.
MACHINE_SCOPED = ("resistance_level", "seat_pos", "pad_pos", "lever_pos")

# Numbers that are physical quantities: comparable across machines, across
# gyms and across years, which is the whole difference.
PORTABLE = ("angle_deg",)

ALL = CATEGORICAL + MACHINE_SCOPED + PORTABLE


def resolve_modifier(axis: str, written: object) -> str:
    """The registry value for an axis, or `unknown`.

    Never an error, and `unknown` rather than None so a caller cannot
    accidentally treat an unfamiliar implement as an absent one. Those are
    different facts: nobody said, versus said something nobody here has
    catalogued.
    """
    if written is None:
        return UNKNOWN
    return resolve(REGISTRY, axis, written) or UNKNOWN


def values(axis: str) -> list[str]:
    return sorted(registry(REGISTRY).get(axis) or {})


def is_machine_scoped(field: str) -> bool:
    return field in MACHINE_SCOPED


def configuration(rec: dict) -> dict:
    """How this set was configured, with every stated axis resolved.

    Only what the row actually says. An axis nobody stated is absent from the
    result rather than present as `unknown`, so a caller can tell a set logged
    without a grip from one logged with a grip nobody recognises.
    """
    out: dict = {}
    for axis in CATEGORICAL:
        if rec.get(axis) is not None:
            out[axis] = resolve_modifier(axis, rec[axis])
    for field in MACHINE_SCOPED + PORTABLE:
        if rec.get(field) is not None:
            out[field] = rec[field]
    return out


def comparable(a: dict, b: dict, field: str) -> bool:
    """May these two sets' values for this field be compared at all?

    RAISES for a field this module does not own, rather than returning False.
    A misspelling and a legitimate refusal must not look alike: a caller that
    asks about `resistence_level` is asking a question it thinks it
    understands, and answering "no" quietly tells it the comparison was
    considered and declined.

    False when either row does not STATE the value. Two machines matching is
    not enough - a consumer that subtracts after a True would find a None.

    A machine-scoped value may only be compared within one machine. Names are
    folded through `_normalise` first: the same crosstrainer typed once with a
    capital and once without is one machine, and letting that split the pair
    drops the very progression this exists to make visible.

    A portable quantity is comparable except across angle CLASSES. An incline
    of 30 degrees and a decline of 30 degrees are stored with the same number
    and are sixty degrees apart, because the class carries the sign.

    #100 owns what a derivation does with the answer. The rule lives here so
    it is not restated wherever someone wants a comparison.
    """
    if field not in ALL:
        raise ValueError(
            f"{field!r} is not a modifier this module owns - one of "
            f"{', '.join(ALL)}")
    if a.get(field) is None or b.get(field) is None:
        return False
    if field in MACHINE_SCOPED:
        left, right = _same_machine(a), _same_machine(b)
        return bool(left) and left == right
    if field == "angle_deg":
        classes = {resolve_modifier("angle_class", r.get("angle_class"))
                   for r in (a, b) if r.get("angle_class") is not None}
        return len(classes) < 2
    return True


def _same_machine(rec: dict) -> str:
    """A machine name folded to one spelling, or "" if unstated."""
    from .vocab import _normalise
    return _normalise(rec.get("machine")) if rec.get("machine") else ""


def problems(rec: dict) -> list[str]:
    """Validation for a set's modifiers."""
    out: list[str] = []
    for axis in CATEGORICAL:
        written = rec.get(axis)
        if written is None:
            continue
        if not isinstance(written, str) or not written.strip():
            out.append(f"'{axis}' is a value from semantics/modifiers.toml or "
                       f"null for unstated, got {written!r}")
        elif resolve_modifier(axis, written) == UNKNOWN:
            # A FINDING, never an error: an unfamiliar implement is a gap in
            # the registry, and rejecting the row would lose the training.
            #
            # `unknown` is not a storable value and there is no registry entry
            # for it. Storing the placeholder would make "I could not tell"
            # indistinguishable from "nobody catalogued this", and null
            # already says the first thing.
            out.append(f"unknown {axis} {written!r} - one of "
                       f"{', '.join(values(axis))}, or null if nobody said. "
                       "Add an alias to semantics/modifiers.toml if this is a "
                       "real one")

    for field in MACHINE_SCOPED + PORTABLE:
        value = rec.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out.append(f"'{field}' is a number, got {value!r}")
            continue
        if value < 0:
            out.append(f"'{field}' cannot be negative, got {value!r}")

    for field in MACHINE_SCOPED:
        if rec.get(field) is not None and not str(rec.get("machine") or "").strip():
            # The #60 rule. This is not a preference for completeness: the
            # value is UNINTERPRETABLE without a machine, and stored bare it
            # invites exactly the cross-machine comparison that made it wrong.
            out.append(f"'{field}' is a number on one machine's own scale, so "
                       "it needs a 'machine' to be a number about - level 15 "
                       "here is not level 15 there, and it is not 15/13 of "
                       "level 13 either")

    if (deg := rec.get("angle_deg")) is not None and isinstance(deg, (int, float)) \
            and not isinstance(deg, bool) and deg > 90:
        out.append(f"'angle_deg' is a bench or gradient angle in degrees, "
                   f"got {deg!r} - beyond 90 the bench is behind the athlete")
    return out
