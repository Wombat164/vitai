"""Vocabularies as curated registries, not Python sets (G85).

The structural reason G85 kept happening: a vocabulary in CODE can only be
extended by a developer, so it can only ever contain what the developer had
seen. `gym_a` shipped in a public engine because the author had a Strength A
day; cycling, swimming, rowing and every team sport fell into `other` because
he did not do them. That is not a taxonomy, it is a sample of one person.

A vocabulary in a REGISTRY can be extended without touching code, carries its
prior art in its own comments, and can retire a value without deleting it.

## What this module deliberately does NOT do

It does not make safety-bearing vocabularies athlete-editable at runtime. The
issue proposed that, and for `session_types` it is right - somebody's sport
missing is a bug in our sample, not in them. But an activity class that no
rule understands is an unenforced gate, which is the exact harm the whole
restriction rework exists to remove. So registries are curated files with
generous ALIASES: the athlete's words map onto the vocabulary, and widening
the vocabulary itself stays a reviewed change.

## Value retirement

`KEY_RETIREMENT` retires a KEY at a generation. It could not retire a VALUE
inside a still-live key, which is what `gym_a` needed. `retired.<value>` in a
registry does that: the value stays legal forever (an old line is history, not
an error) and resolves forward to its replacement.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def registry(name: str) -> dict:
    """Parse a registry file from `semantics/` (cached; curated read-only data)."""
    path = resources.files("vitai") / "semantics" / f"{name}.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _normalise(text: object) -> str:
    """Case, spacing and punctuation folded, so "Gym A" == "gym_a"."""
    return " ".join(str(text).replace("_", " ").replace("-", " ").lower().split())


@lru_cache(maxsize=None)
def _index(name: str, section: str) -> dict[str, str]:
    """Every accepted spelling in one section -> its canonical slug.

    Includes each slug, its label, its aliases, and any retired value that
    maps into the section - so an old line resolves without special-casing.
    """
    data = registry(name)
    out: dict[str, str] = {}
    for slug, meta in (data.get(section) or {}).items():
        out.setdefault(_normalise(slug), slug)
        if label := (meta or {}).get("label"):
            out.setdefault(_normalise(label), slug)
        for alias in (meta or {}).get("aliases", []):
            out.setdefault(_normalise(alias), slug)
    for old, meta in (data.get("retired") or {}).items():
        target = (meta or {}).get("maps_to")
        if target in (data.get(section) or {}):
            out.setdefault(_normalise(old), target)
    return out


def values(name: str, section: str) -> list[str]:
    """Canonical slugs in a section, sorted - for pickers and error messages."""
    return sorted((registry(name).get(section) or {}))


def resolve(name: str, section: str, written: object) -> str | None:
    """Canonical slug for whatever was written, or None if unrecognised."""
    if written is None or str(written).strip() == "":
        return None
    return _index(name, section).get(_normalise(written))


def is_value(name: str, section: str, written: object) -> bool:
    return resolve(name, section, written) is not None


def meta(name: str, section: str, written: object) -> dict:
    """The registry entry behind a value (empty dict if unrecognised)."""
    slug = resolve(name, section, written)
    return dict((registry(name).get(section) or {}).get(slug) or {}) if slug else {}


def retired(name: str) -> dict[str, dict]:
    """Values that are legal but no longer offered, and what they map to."""
    return dict(registry(name).get("retired") or {})


def is_retired(name: str, written: object) -> bool:
    return _normalise(written) in {_normalise(k) for k in retired(name)}


# --- session types ------------------------------------------------------------

def session_types() -> list[str]:
    return values("session_types", "types")


def resolve_session_type(written: object) -> str | None:
    return resolve("session_types", "types", written)


def session_classes(written: object) -> set[str]:
    """The restriction classes a session of this type falls under.

    Declared in the registry rather than hardcoded in the safety layer, so
    adding a sport does not mean editing the code that decides what a gate
    blocks - which is how `gym_a` and `gym_b` ended up mapping identically to
    both upper and lower body, carrying no gating information at all.
    """
    return set(meta("session_types", "types", written).get("classes") or [])


# --- restriction axes ---------------------------------------------------------

AXES = ("pattern", "region", "load", "plane", "activity")


def axis_values(axis: str) -> list[str]:
    """Legal values on one restriction axis.

    `region` reuses semantics/body_sites.toml wholesale - both its SITES
    (knee, achilles) and its REGIONS (lower_limb, trunk), because a clinical
    restriction is written at whichever level the clinician used. Inventing a
    second anatomy here would be the same mistake in a new place.
    """
    if axis == "region":
        from .anatomy import known_sites, regions
        return sorted(set(known_sites()) | set(regions()))
    return values("restrictions", axis)


def resolve_axis(axis: str, written: object) -> str | None:
    if axis == "region":
        from .anatomy import regions, resolve as resolve_site
        if (site := resolve_site(written)) is not None:
            return site
        key = _normalise(written).replace(" ", "_")
        return key if key in regions() else None
    return resolve("restrictions", axis, written)


def activity_classes() -> list[str]:
    return values("restrictions", "activity")


# --- post-coordinated restriction specs ---------------------------------------

def parse_restriction(spec: object) -> dict[str, str]:
    """`"pattern=hinge region=hip load=loaded"` -> a resolved axis dict.

    Kept as flat `key=value` text rather than nested JSON so a restriction
    stays writable by hand and by a screenshot-reading skill, and so the
    dataset stays one flat object per line like everything else.

    Unrecognised axes and values are dropped here and REPORTED by
    `restriction_problems`, so a typo becomes a loud validation error rather
    than a silently narrower gate.
    """
    out: dict[str, str] = {}
    for token in str(spec or "").replace(",", " ").split():
        if "=" not in token:
            continue
        axis, _, written = token.partition("=")
        axis = axis.strip().lower()
        if axis in AXES and (slug := resolve_axis(axis, written)):
            out[axis] = slug
    return out


def restriction_problems(spec: object) -> list[str]:
    """Everything wrong with a restriction spec, for the validator."""
    if spec is None or str(spec).strip() == "":
        return []
    problems: list[str] = []
    seen = False
    for token in str(spec).replace(",", " ").split():
        if "=" not in token:
            problems.append(f"{token!r} is not an axis=value pair - a "
                            "restriction reads like 'pattern=hinge region=hip'")
            continue
        axis, _, written = token.partition("=")
        axis = axis.strip().lower()
        if axis not in AXES:
            problems.append(f"unknown restriction axis {axis!r} - one of "
                            f"{', '.join(AXES)}")
            continue
        if resolve_axis(axis, written) is None:
            problems.append(f"unknown {axis} {written!r} - one of "
                            f"{', '.join(axis_values(axis))}")
            continue
        seen = True
    if not seen and not problems:
        problems.append("a restriction needs at least one axis=value pair")
    return problems


def restriction_matches(restriction: dict[str, str],
                        movement: dict[str, str]) -> bool:
    """Does a proposed movement fall under a restriction?

    An ABSENT axis on the restriction means "any", so `pattern=flexion` alone
    catches flexion anywhere. An absent axis on the MOVEMENT means unknown,
    and unknown does not match - a restriction narrows, and a movement nobody
    described cannot be shown to fall inside it.

    This is what makes the two clinical gates behave:

        no loaded hip work      pattern=hinge region=hip load=loaded
        ...a hip thrust         pattern=hinge region=hip load=loaded  -> blocked
        ...a squat              pattern=squat region=hip load=loaded  -> allowed

    `lower_body` would have banned the squat the clinician permitted. Naming
    the pattern separately from the region is the whole difference.
    """
    if not restriction:
        return False
    for axis, required in restriction.items():
        got = movement.get(axis)
        if got is None:
            return False
        if axis == "region":
            from .anatomy import region_of, resolve as resolve_site
            here = resolve_site(got)
            # A restriction on a REGION (lower_limb) catches its sites; a
            # restriction on a SITE matches only that site.
            if here != required and region_of(here) != required:
                return False
        elif resolve_axis(axis, got) != required:
            return False
    return True
