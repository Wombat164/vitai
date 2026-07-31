"""Provenance is a CHAIN, not a source string (#35, #51).

The mistake this exists to stop, in one line: **an activity present in both
Polar and Strava is one measurement seen twice, not two measurements
agreeing.**

Platforms are mostly SINKS. Strava, Google Health and Apple Health
predominantly receive data recorded elsewhere, so treating their agreement as
corroboration double-counts a single reading and raises confidence on the
strength of nothing. Independent instruments corroborate; a sync pipeline
does not - it is the same instrument at the other end of a wire.

It was found by making the mistake twice. A walk read 2.226 km from a Strava
export and 2.23 km from Polar, and that near-agreement was taken as two
sources concurring; it is one Polar Pacer Pro reading. And the resolution
layer emitted `fitbit-api+mfp-export`, which reads as a union of independent
sources when MyFitnessPal had received those weights FROM Fitbit.

## The three parts of a chain

    reality -> origin -> hop -> hop -> ... -> terminus

- **origin** - what observed reality: a device, or a person typing. This is
  the only part corroboration may key on.
- **path** - the ordered hops it travelled. Every hop may add, change, infer
  or delete, so this is where trust is lost.
- **terminus** - how it entered this record. That is the existing `source`
  field, which answers only this and was being asked to answer all three.

## Two consequences that are easy to state and easy to get wrong

**Corroboration requires divergent ORIGINS.** Same origin, different path is
one measurement. `witnesses` must count distinct origins, not rows.

**Trust is bounded by the WEAKEST hop, not the origin.** A device-measured
weight that passed through a vendor which rounds, re-derives or back-fills is
no longer device-measured, however good the device was.

## Unstated is not absent

A row with no `origin` is in a different state from one whose origin is
recorded as unknown. Collapsing them asserts something nobody established -
and an unknown origin must never count as an independent source, or the
Takeout import (where the originating device is often lost entirely) would
manufacture corroboration out of missing data.
"""

from __future__ import annotations

from .vocab import meta, registry, resolve

# How hops are written in `path`: an ordered, arrow-separated list of names.
# Flat text rather than nested JSON for the same reason a restriction is
# (#18): it stays writable by hand and by a screenshot-reading skill, and the
# dataset stays one flat object per line.
SEPARATOR = ">"
UNKNOWN = "unknown"


def hops(path: object) -> list[str]:
    """The ordered hop names in a path, or [] for an empty one."""
    if path is None or not str(path).strip():
        return []
    return [h.strip() for h in str(path).split(SEPARATOR) if h.strip()]


def role_of(hop: object) -> str:
    """The registry role for a hop name, or `unknown` if unrecognised.

    Real hops are named for their vendor: `fitbit-api`, `mfp-export`,
    `polar-flow`. So a bare-role lookup alone would classify almost every real
    chain as unknown, and a trust signal that is always "unknown" tells nobody
    anything. The LAST token of the name is therefore tried against the role
    vocabulary - `fitbit-api` ends in `api`, `mfp-export` ends in `export`.

    That is a spelling rule over declared role names, not a vendor list and
    not a fuzzy match: it can only ever reach a role the registry already
    declares. A name whose last token names nothing stays `unknown`.

    The one direction that could cost something is promoting a hop to a
    NON-mutating role it does not deserve - a mutating step called
    `something-watch` would read as a device. Named here rather than guarded
    against, because the alternative (suffix-matching only mutating roles)
    makes every device hop unknown, which is the failure this exists to fix.
    """
    if (direct := resolve("provenance", "roles", hop)) is not None:
        return direct
    tail = str(hop or "").replace("_", "-").replace(" ", "-").split("-")[-1]
    return resolve("provenance", "roles", tail) or UNKNOWN


def may_mutate(hop: object) -> bool:
    """Could this hop have changed the value on its way through?"""
    entry = meta("provenance", "roles", hop)
    return bool(entry.get("may_mutate", True))


def roles() -> list[str]:
    return sorted(registry("provenance").get("roles") or {})


def origin_of(rec: dict) -> str | None:
    """The instrument that observed this value, or None if unstated.

    None means NOBODY SAID, which is not the same as `unknown` meaning
    "recorded, and we could not tell". Both refuse to corroborate, but only
    one of them is a gap someone could still fill.
    """
    value = rec.get("origin")
    return str(value) if value not in (None, "") else None


def is_independent(rec: dict) -> bool:
    """May this row's origin count as a distinct witness?

    An unstated or unknown origin may not. That is the guard which stops a
    Google Takeout import - where the originating device is frequently lost -
    from manufacturing corroboration out of missing data.
    """
    origin = origin_of(rec)
    return origin is not None and origin != UNKNOWN


def distinct_origins(recs: list[dict]) -> set[str]:
    """The genuinely independent origins among these claims."""
    return {str(origin_of(r)) for r in recs if is_independent(r)}


def independent_witnesses(recs: list[dict]) -> int:
    """How many INDEPENDENT observations these claims represent.

    Not `len(recs)`. Five rows carrying one watch's reading through five
    platforms are one witness, and reporting five is the false confidence
    this whole module exists to prevent.

    Rows with no usable origin each count as their own witness only when
    nothing else does: a record with no provenance at all still had one
    observation per row as far as anyone can tell, and pretending otherwise
    would silently merge a legitimately un-annotated history.
    """
    known = distinct_origins(recs)
    if known:
        return len(known) + sum(1 for r in recs if not is_independent(r))
    return len(recs)


def shares_origin(a: dict, b: dict) -> bool:
    """Do these two claims come from the same instrument?

    False when either origin is unstated or unknown - the engine does not get
    to assume two anonymous rows are the same reading any more than it gets
    to assume they are different.
    """
    return (is_independent(a) and is_independent(b)
            and origin_of(a) == origin_of(b))


# --- was it MEASURED at all? (#49, #88) ---------------------------------------
#
# The orthogonal question to origin and capture. Those say WHICH instrument and
# HOW it reached us; this says whether the number was ever observed.
#
# A model output arriving in a field whose name and type imply measurement is
# invisible by construction: `kcal_out: 1728` on two different dates is BMR
# modelling, because the tracker was not worn - and nothing downstream can
# tell. Five separate instances turned up in ONE import, which is what makes
# it a rule rather than three patches.
#
# The harm is specific and not tidiness. An inflated burn reaching a deficit
# makes the arithmetic read ON TARGET while the scale goes up, and the athlete
# is told to hold a plan that is not working. Labelling it in a note is not
# enforcement: prose is not a thing code can check.
#
# `modelled` is a flat list of the FIELDS on this row that are model outputs,
# because the distinction is per-field - one row can carry a measured step
# count and an estimated burn.

# How a CATEGORICAL label was arrived at (#88). Not the same question as
# `capture`: a vendor classifier is not an acquisition method, it is an
# inference over sensor data nobody outside the vendor ever sees. In one live
# record 1,093 of 1,502 session types were a classifier's guess and the record
# could not tell them from the 409 the athlete asserted.
TYPE_SOURCES = ("athlete-stated", "device-recorded", "vendor-classified",
                "engine-inferred")


def modelled_fields(rec: dict) -> set[str]:
    """Fields on this row that are model outputs rather than observations."""
    written = rec.get("modelled")
    if not written or not str(written).strip():
        return set()
    return {f.strip() for f in str(written).replace(",", " ").split() if f.strip()}


def is_modelled(rec: dict, field: str) -> bool:
    return field in modelled_fields(rec)


def type_source(rec: dict) -> str | None:
    """How this row's categorical `type` was assigned, if stated."""
    written = rec.get("type_source")
    return str(written) if written else None


def value_kind_problems(rec: dict, keys: list[str]) -> list[str]:
    """Validation for the two ways a row can say a value was not observed."""
    out: list[str] = []
    for f in sorted(modelled_fields(rec)):
        if f == "modelled":
            out.append("'modelled' cannot name itself")
        elif f not in keys:
            out.append(f"'modelled' names {f!r}, which is not a field on this "
                       "dataset")
    if (t := rec.get("type_source")) is not None and str(t) not in TYPE_SOURCES:
        out.append(f"'type_source' is one of {', '.join(TYPE_SOURCES)}, "
                   f"got {t!r}")
    if rec.get("type_source") is not None and rec.get("type") is None:
        out.append("'type_source' says how a type was assigned, so it needs "
                   "a 'type'")
    return out


def trust_ceiling(rec: dict) -> str:
    """`device-measured` | `derived-in-transit` | `unknown-transit`.

    A value is only device-measured if it reached us untouched. One hop that
    rounds, re-derives or back-fills breaks that claim - and a hop nobody
    recognises breaks it too, because the alternative is to assume a stranger
    was lossless.
    """
    if not is_independent(rec):
        return "unknown-transit"
    chain = hops(rec.get("path"))
    if not chain:
        return "device-measured"
    if any(role_of(h) == UNKNOWN for h in chain):
        return "unknown-transit"
    return ("derived-in-transit" if any(may_mutate(h) for h in chain)
            else "device-measured")


def describe(rec: dict) -> str:
    """The chain in one readable line, for a report or an explanation."""
    origin = origin_of(rec) or "unstated origin"
    chain = hops(rec.get("path"))
    if not chain:
        return f"{origin}, direct"
    named = " -> ".join(f"{h} ({role_of(h)})" for h in chain)
    return f"{origin} -> {named}"


def problems(rec: dict) -> list[str]:
    """Validation for the two provenance fields."""
    out: list[str] = []
    origin = rec.get("origin")
    if origin is not None and (not isinstance(origin, str) or not origin.strip()):
        out.append("'origin' names the instrument that observed the value, "
                   f"or null if nobody said (got {origin!r})")
    path = rec.get("path")
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            out.append("'path' is an arrow-separated chain of hops "
                       f"(e.g. 'polar-flow{SEPARATOR}strava'), or null")
        elif origin in (None, ""):
            # A path with no origin describes a journey from nowhere, and it
            # would let an anonymous row look annotated.
            out.append("'path' records how a value travelled, so it needs an "
                       "'origin' to have travelled from")
    if rec.get("origin_evidence") is not None and not isinstance(
            rec.get("origin_evidence"), str):
        out.append("'origin_evidence' is the text a file declared "
                   "(e.g. 'TCX Creator: Polar Pacer Pro'), or null")
    return out
