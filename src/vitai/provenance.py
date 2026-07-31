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


# --- the source catalog (#79) ---------------------------------------------------

CATALOG_OTHER = "other"

# Words that name how a value ARRIVED rather than what observed it. They
# belong to `capture`, and a source string ending in one is still naming the
# instrument in front of it.
CHANNEL_SUFFIXES = frozenset({
    "export", "api", "takeout", "sync", "connector", "csv", "dump",
    "archive", "download", "file"})


def resolve_source(written: object) -> str:
    """Catalogued instrument for whatever was written, or `other`.

    NEVER an error. An uncatalogued instrument is a gap in the registry, not a
    fault in the athlete's record - and a private source name (someone's own
    spreadsheet, their own gym) resolves here precisely so it never has to
    appear in a public file.
    """
    if written is None or str(written).strip() == "":
        return UNKNOWN
    if (found := resolve("sources", "sources", written)) is not None:
        return found
    # Source strings routinely carry the CHANNEL as a suffix - `mfp-export`,
    # `fitbit-takeout`, `strava-api`. That suffix answers `capture`, not
    # "which instrument", so it is stripped and the instrument looked up
    # again. A spelling rule over declared names, not a fuzzy match: it can
    # only reach an entry that already names the base.
    base = str(written).replace("_", "-").rsplit("-", 1)
    if len(base) == 2 and base[1].lower() in CHANNEL_SUFFIXES:
        if (found := resolve("sources", "sources", base[0])) is not None:
            return found
    return CATALOG_OTHER


def source_kind(written: object) -> str:
    """What KIND of thing observed this - a watch, a scale, a console, a
    person. Google Fit's `Device.type` axis, extended.

    An uncatalogued source still gets a kind where the name says one: a row
    whose source is written `scale` or `watch` is not a catalogued instrument,
    but it is plainly not a person either. That is exactly the shape the issue
    asked for - `other` PLUS a kind - rather than a `generic-scale` entry that
    would multiply the catalog by the size of the kind axis.
    """
    catalogued = meta("sources", "sources", resolve_source(written)).get("kind")
    if catalogued and catalogued != UNKNOWN:
        return catalogued
    return resolve("sources", "kinds", written) or UNKNOWN


def cannot_observe(written: object) -> set[str]:
    """Fields no instrument of this KIND can physically produce.

    A DENY list, not a whitelist. Written the other way round it turned every
    omission into a false accusation - an Oura ring does report calories, a
    hand-typed row can carry a heart rate read off a watch, a relaying app
    carries whatever it received. An omission here produces silence instead,
    which is the direction that costs nothing.

    Held at the kind rather than the instrument because that is the level at
    which the claim is confidently true of EVERY member.
    """
    kind = source_kind(written)
    return set(meta("sources", "kinds", kind).get("cannot") or [])


def denied_fields() -> set[str]:
    """Every field any kind is declared unable to observe.

    A field no kind denies is never checked, so adding a schema column cannot
    retroactively accuse anybody.
    """
    return {f for entry in registry("sources")["kinds"].values()
            for f in entry.get("cannot") or []}


def impossible_claims(rec: dict, fields: list[str]) -> list[str]:
    """Fields this row states that its own instrument cannot observe (#79).

    Not a resolution tie to adjudicate - a tie is two instruments disagreeing,
    and this is one instrument claiming something it has no sensor for: a
    scale reporting distance, a rowing console reporting sleep, a food log
    reporting heart rate. Nothing caught that before, because `source` was
    free text and nothing knew what a scale is.

    Silent unless the source's KIND is known and denies the field outright,
    so an uncatalogued instrument is never accused of anything.
    """
    denied = cannot_observe(rec.get("source"))
    if not denied:
        return []
    return [f for f in fields
            if f in denied and rec.get(f) is not None]


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
