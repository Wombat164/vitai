"""What a build of this engine can emit, so an absence is not ambiguous (#335).

The core install is dependency-free and some work ships as an optional extra.
A row enriched by an extra carries fields a core install cannot produce, so a
consumer meeting an absent field has two readings available and no way to
choose: the value was not measured, or the install that wrote the record could
not measure it.

The engine refuses that shape everywhere else. Absence and zero are different
facts. `no_data` was split into four reasons because one token carrying
several meanings is the defect I5 exists to prevent. `not_supported` exists so
a refusal is distinguishable from a gap. This is the same distinction at the
install boundary, and #148 is the reason it gets said rather than left
implicit: a consumer that cannot tell what an absence means will infer, and
the inference will be wrong exactly where it matters.

TWO QUESTIONS, AND ONLY ONE OF THEM IS ANSWERABLE TODAY.

  1. "Can the install in front of me produce field X." Answered completely,
     from the registry, with no dating and no per-record rows.

  2. "Could the build that wrote this older row produce field X." Answerable
     only if something says which build wrote the row, and nothing does.

The second one is the sharper half, and the honest answer is `unknown`.
`derived_build` is the only version-bearing field in the schema; it is
required only on a `derived_external` row, and it is set on 1 of 9676 rows in
the shipped corpus. It could not be pressed into service anyway: it names the
build that DERIVED a value, and this question is about what the writer was
CAPABLE of - which come apart precisely here, because the field being asked
about is the one that is missing, so there is no row to carry a stamp.

Stamping every row with an engine version would answer it and is not on the
table: contract 34 refused an install identifier deliberately, because a
stable per-install id is a tracking key.

So `unknown` it is - a value in the vocabulary that a consumer can see and act
on, not a null it has to interpret, and not a default that quietly asserts a
capability the record cannot support. Most historical rows resolve to it. That
is the honest answer rather than a gap being papered over: this record cannot
tell you which reading is right, said out loud instead of inferred.
"""

from __future__ import annotations

from . import __version__
from .vocab import registry

# What an absence MEANS, once the writing build is known.
NOT_MEASURED = "not_measured"
NOT_INSTALLED = "not_installed"
UNKNOWN = "unknown"

#: The whole vocabulary. A consumer switching on this has three cases and the
#: third is not an error condition - it is the commonest answer.
ABSENCE_MEANINGS = (NOT_MEASURED, NOT_INSTALLED, UNKNOWN)


def _data() -> dict:
    return registry("builds")


def extras() -> dict[str, list[str]]:
    """Each optional extra, and the fields only it can emit.

    Empty today, and that is the true state rather than a stub: the route
    extra that raised #335 is not built, so no field in this schema is owned
    by an extra. The mechanism is what #23 needs in order to ship without
    reintroducing the ambiguity.
    """
    return {name: list((meta or {}).get("fields") or [])
            for name, meta in sorted((_data().get("extras") or {}).items())}


def builds() -> dict[str, list[str]]:
    """Each released build the registry covers, and the extras it ships."""
    return {version: list((meta or {}).get("ships") or [])
            for version, meta in sorted((_data().get("builds") or {}).items())}


def this_build() -> str:
    """The build doing the reading. Not the build that wrote any given row."""
    return __version__


def owner(field: str) -> str | None:
    """The extra that owns `field`, or None if the core emits it."""
    for name, fields in extras().items():
        if field in fields:
            return name
    return None


def known_fields() -> set[str]:
    """Every field this engine can be asked about: the schema, plus whatever
    the extras declare.

    An extra's fields are included because they are exactly the ones the core
    schema does not have - that is what makes them the extra's - so a schema
    membership test alone would call the route extra's own output unheard-of.
    """
    from .schema import KEYS
    return ({f for fields in KEYS.values() for f in fields}
            | {f for fields in extras().values() for f in fields})


def _verdict(field: str, build: str | None) -> bool | None:
    """Can `build` emit `field`: True, False, or None for "cannot tell".

    ONE COPY OF THE RULE. `absence` and `can_emit` ask the same underlying
    question in two vocabularies, and two implementations of one rule is how
    they drift into disagreeing about the case nobody tested.

    IT FAILS CLOSED ON THE FIELD, and the first cut did not. The rule read
    "no extra claims this field, therefore any build can emit it", which is a
    verdict derived from NON-membership of the extras map - so a field that
    does not exist got the same confident yes as `rhr`. `can_emit("hrr")`, a
    typo for `rhr`, answered "yes". Membership of a written-down set is the
    shape this repo uses for a control, because a rule built from the absence
    of an entry can only ever be right about the entries it already has.
    """
    if field not in known_fields():
        return None
    known = builds()
    if build is None or str(build) not in known:
        return None
    holder = owner(field)
    # No extra claims this field and the schema does have it, so every build
    # that could write the row at all could have written this value.
    return holder is None or holder in known[str(build)]


def absence(field: str, build: str | None) -> str:
    """What an absent `field` means on a row written by `build`.

    `build` is the version that WROTE the row, and it has NO DEFAULT - unlike
    `can_emit`, where defaulting to the reading install is the useful case.
    Here the same convenience would be a trap: silently answering about the
    build in front of you, for a row some older build wrote, is precisely the
    wrong inference this issue exists to prevent. Passing None says the writer
    is unknown, and the answer says so back.

    A COVERED BUILD IS A POSITIVE STATEMENT. A build listed in the registry
    shipping no extras says this build could emit the core schema and nothing
    beyond it, which is what makes `not_measured` sayable. A build merely
    ABSENT says only that nobody recorded what it could do. Those must not
    collapse onto each other - it is the same distinction one level up.
    """
    verdict = _verdict(field, build)
    if verdict is None:
        return UNKNOWN
    return NOT_MEASURED if verdict else NOT_INSTALLED


def can_emit(field: str, build: str | None = None) -> str:
    """Whether `build` can produce `field`: yes, no, or unknown.

    Defaults to the build doing the READING, which is the single-install
    question and the one #23 waits on. Ask about another version to get the
    cross-record question, and expect `unknown` for anything older than this
    registry.
    """
    verdict = _verdict(field, this_build() if build is None else build)
    return UNKNOWN if verdict is None else ("yes" if verdict else "no")


def problems() -> list[str]:
    """What is wrong with the registry, empty when it is sound.

    The file makes claims about itself - a listed build is a positive
    statement, an extra names the fields it and only it can emit - and a claim
    with nothing checking it is decoration. Each of these turns silently into
    a WRONG ANSWER rather than an error, which is why they are worth catching
    while the file is still small:

    - a build entry with no `ships` key reads as shipping nothing, so an
      absent key manufactures a positive statement of incapacity
    - a build shipping an extra that is not declared answers `not_installed`
      for every one of that extra's fields, because the lookup finds nothing
    - two extras claiming one field resolve by whichever sorts first, so a
      build shipping the other one is told it cannot emit what it can
    """
    data = _data()
    declared = set((data.get("extras") or {}))
    out: list[str] = []
    for name, meta in sorted((data.get("extras") or {}).items()):
        if not (meta or {}).get("fields"):
            out.append(f"extra {name!r} declares no fields")
    seen: dict[str, str] = {}
    for name, fields in extras().items():
        for field in fields:
            if field in seen:
                out.append(f"field {field!r} is claimed by both {seen[field]!r} "
                           f"and {name!r}")
            seen[field] = name
    for version, meta in sorted((data.get("builds") or {}).items()):
        if "ships" not in (meta or {}):
            out.append(f"build {version!r} has no `ships` key, so it would "
                       f"read as shipping nothing")
        for extra in (meta or {}).get("ships") or []:
            if extra not in declared:
                out.append(f"build {version!r} ships undeclared extra {extra!r}")
    return out
