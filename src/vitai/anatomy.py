"""Where it hurts: a closed body-site vocabulary with post-coordinated sides.

`pain_site` began as free text, which meant the record could hold "knee",
"Knee", "left knee" and "patella" as four unrelated places, none of them
countable and none of them comparable across a year. This module loads the
curated registry that replaces it (`semantics/body_sites.toml`) and resolves
what the athlete actually typed onto it.

Two decisions carry the design, both taken from prior art rather than
invented (see docs/prior-art-anatomy.md):

- **Laterality is post-coordinated.** A side is its own field, never part of
  the site name. HL7 FHIR splits `BodyStructure.includedStructure.structure`
  from `.laterality`; openEHR's `CLUSTER.anatomical_location` mandates only
  the body-site name and hangs laterality off it as a qualifier. Two
  standards, the same call, independently. Folding sides into names would
  also double the vocabulary for no gain.
- **The vocabulary is small and validated.** Granularity follows the Michigan
  Body Map, a validated self-report instrument, trimmed to musculoskeletal
  sites. An athlete choosing from thirty options in a three-minute weekly
  ritual is a different problem from a clinician coding against forty
  thousand, and solving the second one here would break the first.

The registry is curated knowledge (P5): neither data nor code, versioned in
the repo, human-mergeable, and evidence-tagged in its own comments.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import resources

# Sides, post-coordinated. `bilateral` is a real answer and not a fudge - both
# knees hurting is a different fact from one of them hurting.
SIDES = {"left", "right", "bilateral"}


@lru_cache(maxsize=1)
def registry() -> dict:
    """The parsed body-site registry (cached; it is read-only curated data)."""
    path = resources.files("vitai") / "semantics" / "body_sites.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sites() -> dict[str, dict]:
    return dict(registry().get("sites", {}))


@lru_cache(maxsize=1)
def regions() -> dict[str, str]:
    return dict(registry().get("regions", {}))


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """Every spelling the registry accepts -> its canonical site slug.

    Includes each site's own slug and label, so `resolve("Lower back")` and
    `resolve("lower_back")` both land. Aliases exist so the athlete is never
    asked to learn the vocabulary - the ingest skill maps their words onto
    it, and only an unmappable word becomes a question.
    """
    index: dict[str, str] = {}
    for slug, meta in sites().items():
        index[_normalise(slug)] = slug
        if label := meta.get("label"):
            index.setdefault(_normalise(label), slug)
        for alias in meta.get("aliases", []):
            index.setdefault(_normalise(alias), slug)
    return index


def _normalise(text: str) -> str:
    """Case, spacing and punctuation folded; 'IT band' == 'it_band'.

    ONE FOLD, NOT TWO. This was a byte-identical second copy of
    `vocab._normalise`, which is the rule every registry lookup in the engine
    uses to decide two spellings are one thing. Two copies of a fold do not
    disagree on the day they are written; they disagree the first time one of
    them learns something. A widening for unicode dashes - smart punctuation
    from a phone is how a hand-written plain-text record acquires one - would
    land in `vocab` and leave `pain_site` resolving the old way, silently,
    which is the `hip_pain` shape exactly.

    `vocab` imports `anatomy` lazily and inside functions, so taking the
    dependency this direction adds no cycle.
    """
    from .vocab import _normalise as fold

    return fold(text)


def resolve(name: str | None) -> str | None:
    """Canonical site slug for whatever the athlete wrote, or None."""
    if not name:
        return None
    return _alias_index().get(_normalise(name))


def is_site(name: str | None) -> bool:
    return resolve(name) is not None


def is_paired(site: str | None) -> bool:
    """Does this structure exist on both sides, and so need a side to be usable?"""
    slug = resolve(site)
    return bool(slug and sites()[slug].get("paired"))


def region_of(site: str | None) -> str | None:
    """The site's region, so "anything in the lower limb" is answerable without
    an ontology reasoner - the whole reason the hierarchy is two levels deep."""
    slug = resolve(site)
    return sites()[slug].get("region") if slug else None


def label_of(site: str | None) -> str | None:
    slug = resolve(site)
    return sites()[slug].get("label") if slug else None


def osiics_of(site: str | None) -> str | None:
    """IOC sports-injury code for this site, where one has been VERIFIED.

    None means "not confirmed from a primary source", not "no such code".
    The registry deliberately leaves unverified letters blank.
    """
    slug = resolve(site)
    return sites()[slug].get("osiics") if slug else None


def describe(site: str | None, side: str | None = None) -> str | None:
    """Athlete-facing rendering: "Left knee", "Lower back", "Both achilles"."""
    slug = resolve(site)
    if slug is None:
        return None
    label = sites()[slug].get("label") or slug
    if side == "bilateral":
        return f"Both {label.lower()}"
    if side in ("left", "right"):
        return f"{side.capitalize()} {label.lower()}"
    return label


def known_sites() -> list[str]:
    """Canonical slugs, sorted - for error messages and pickers."""
    return sorted(sites())
