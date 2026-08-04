"""The exercise vocabulary, and what makes a restriction checkable (#98).

Increment 2 of #59. Two defects, one registry.

**`sets.exercise` was free text**, so `push-up`, `pushup` and `press-up` were
three exercises and no query grouped them - the same defect #79 names for
source strings, one domain over.

**A restriction could not see a set.** A live hip episode wanted
`pattern=hinge region=hip load=loaded` and had nothing to match against,
because nothing a session carried had those axes. The coarse
`restricts: strength` gate was used instead, and it blocked push-ups. That is
collateral damage caused *precisely* by the precise gate having nothing to
check. Give exercises the axes and a set INHERITS them, and the gate the
clinician actually described becomes mechanically checkable.

## The axes are borrowed, never invented

`pattern`, `load` and `plane` come from `restrictions.toml`; `region` from
`body_sites.toml`. A second movement taxonomy here would make the two
unjoinable, which is the entire defect being fixed.

## The set overrides the registry

`load` in the registry is the exercise's DEFAULT loading. A weighted push-up
is still `push-up` - the SET says it was loaded, via `load_type`, and the
check reads the set's answer when there is one and the default only when
there is not. Getting this backwards would let a registry default overrule an
observation, which is the wrong direction for a record built on observations.

## An unknown exercise abstains, and says so

This is the part that must not be got wrong. An unknown exercise has NO axes,
so a restriction check against it can neither pass nor fail. It reports that
the gate was NOT EVALUATED - never a silent pass.

A missing gate is the failure mode that matters here: a silent pass means the
athlete trains on an injury nobody flagged, and nothing in the output ever
says so. Abstaining is loud and recoverable; passing is quiet and is not.
"""

from __future__ import annotations

from .vocab import registry, resolve, restriction_matches, values

REGISTRY = "exercises"
SECTION = "exercises"
UNKNOWN = "unknown"

# The axes an entry carries, all borrowed from vocabularies that already
# exist. `region` is the list-valued one.
AXES = ("pattern", "load", "plane")


def resolve_exercise(written: object) -> str:
    """The registry slug for whatever was written, or `unknown`.

    Never an error. An exercise nobody here catalogued is a gap in
    `exercises.toml`, not a fault in the athlete's record - and the world's
    gym catalogue is far larger than any seed.
    """
    return resolve(REGISTRY, SECTION, written) or UNKNOWN


def entry(written: object) -> dict:
    """The registry entry for an exercise, or {} if it is unknown."""
    slug = resolve_exercise(written)
    if slug == UNKNOWN:
        return {}
    return (registry(REGISTRY).get(SECTION) or {}).get(slug) or {}


def exercises() -> list[str]:
    return sorted(registry(REGISTRY).get(SECTION) or {})


def regions_of(written: object) -> list[str]:
    """The body sites an exercise loads.

    A list, because loading several is anatomical fact: a push-up loads chest,
    shoulder and upper arm. Forcing one value would make the registry assert a
    primary mover, which is a modelling claim rather than an observation.
    """
    return list(entry(written).get("region") or [])


def patterns_of(written: object) -> list[str]:
    """The movement patterns an exercise involves.

    A LIST, for the same reason `region` is one. A thruster is a squat and an
    overhead press; a clean and jerk is a hinge and a press. Forcing one value
    means a restriction on loaded overhead pressing does not catch either of
    them, which is a real clinical gate quietly failing to fire.
    """
    value = entry(written).get("pattern")
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def load_of(rec: dict) -> str | None:
    """Whether this set was loaded, or None if nothing establishes it.

    The SET wins over the registry: `load_type` says what actually happened
    and the registry only says what usually does, so a registry default must
    never overrule an observation. A stated `load` with no `load_type` still
    counts - 40 kg on the record is evidence of loading whatever the row
    forgot to say.

    `assisted` resolves to BODYWEIGHT. The effective load is bodyweight MINUS
    the assistance, so an assisted pull-up is strictly easier than an
    unassisted one - and mapping it to `loaded` blocked the rehab regression
    while leaving the full movement allowed, which is precisely backwards.

    None means nothing said. An exercise whose registry entry omits `load`
    genuinely varies, and a restriction keyed on load must then ABSTAIN rather
    than guess in either direction.
    """
    kind = rec.get("load_type")
    if kind is not None:
        return "bodyweight" if kind in ("bodyweight", "assisted") else "loaded"
    load = rec.get("load")
    if isinstance(load, (int, float)) and not isinstance(load, bool) and load > 0:
        return "loaded"
    return entry(rec.get("exercise")).get("load")


def movement_of(rec: dict) -> dict:
    """The axes a logged set inherits from its exercise."""
    axes = entry(rec.get("exercise"))
    if not axes:
        return {}
    out: dict = {}
    if axes.get("plane"):
        out["plane"] = axes["plane"]
    if (load := load_of(rec)) is not None:
        out["load"] = load
    if patterns_of(rec.get("exercise")):
        out["pattern"] = patterns_of(rec.get("exercise"))
    return out


def gate_check(restriction: dict, rec: dict) -> dict:
    """Does this set fall under this restriction? `blocked` | `allowed` |
    `not_evaluated`.

    Three outcomes rather than a boolean, and the third is the point. An
    unknown exercise carries no axes, so the honest answer is that the gate
    could not be evaluated - a restriction cannot be shown to catch a movement
    nobody described, and it cannot be shown not to either.

    Returning `allowed` there would be a silent pass on a real restriction,
    which is how an athlete ends up training on an injury nobody flagged.
    """
    slug = resolve_exercise(rec.get("exercise"))
    if slug == UNKNOWN:
        return {"verdict": "not_evaluated", "exercise": slug,
                "detail": f"gate not evaluated: unknown exercise "
                          f"{rec.get('exercise')!r} carries no movement axes, "
                          "so this restriction can neither catch it nor clear "
                          "it - add it to semantics/exercises.toml"}
    if not restriction:
        # An axis-free restriction is not a gate over everything and it is not
        # a clean pass either - most often it is a spec that failed to parse,
        # since `parse_restriction` DROPS pairs it cannot resolve. Answering
        # `allowed` here turns a typo into a silent clearance.
        return {"verdict": "not_evaluated", "exercise": slug,
                "detail": "gate not evaluated: this restriction names no "
                          "axis=value pair the engine could resolve - a "
                          "mistyped axis parses to nothing, and an empty "
                          "restriction cannot clear a movement"}

    movement = movement_of(rec)
    sites = regions_of(rec.get("exercise"))
    # An axis the movement cannot supply is the OTHER way a gate fails open.
    # `restriction_matches` reads an absent axis as "does not match", which is
    # right for narrowing and wrong as a verdict: `activity=strength` names a
    # session-level axis no exercise carries, so every strength set came back
    # `allowed` from a restriction that plainly covers it.
    carried = set(movement) | ({"region"} if sites else set())
    if missing := sorted(set(restriction) - carried):
        return {"verdict": "not_evaluated", "exercise": slug,
                "detail": f"gate not evaluated: this restriction is keyed on "
                          f"{', '.join(missing)}, which {slug} does not carry "
                          "- it can neither be caught by it nor cleared of it"}

    # Each site and each pattern is tried in turn. An exercise loads several
    # sites and a thruster is two patterns; a restriction naming any one of
    # them catches the exercise. Requiring every one to match would clear a
    # hip restriction against a deadlift because it also loads the back.
    singles = [{**movement, "pattern": p, "region": r}
               for p in (movement.get("pattern") or [None])
               for r in (sites or [None])]
    hit = any(restriction_matches(
        restriction, {k: v for k, v in one.items() if v is not None})
        for one in singles)
    return {"verdict": "blocked" if hit else "allowed", "exercise": slug,
            "detail": (f"{slug} matches {_spell(restriction)}" if hit else
                       f"{slug} does not fall under {_spell(restriction)}")}


def _spell(restriction: dict) -> str:
    return " ".join(f"{a}={v}" for a, v in sorted(restriction.items()))


def problems(rec: dict) -> list[str]:
    """Validation for a set's exercise: a finding, never an error."""
    written = rec.get("exercise")
    if written is None or not str(written).strip():
        return []
    if resolve_exercise(written) == UNKNOWN:
        # A FINDING that names the unresolved string, so the fix is one alias
        # away. Not an error: the registry is a seed of a catalogue nobody has
        # ever finished, and rejecting the row would lose the training.
        return [f"unknown exercise {written!r} - it is recorded either way, "
                "but it carries no movement axes, so no restriction can be "
                "checked against it. Add it to semantics/exercises.toml"]
    return []


def registry_problems() -> list[str]:
    """Everything wrong with the registry itself, for a test to assert on.

    An off-vocabulary axis value must never silently create a new pattern or a
    new body site: the whole point of borrowing the vocabularies is that the
    two stay joinable, and a typo that invents `hindge` breaks that quietly.
    """
    from .anatomy import resolve as resolve_site
    from .vocab import axis_values

    out: list[str] = []
    entries = registry(REGISTRY).get(SECTION) or {}
    for slug, data in sorted(entries.items()):
        if slug != slug.lower() or " " in slug or "_" in slug:
            # Slug shape, which is also the anti-fusion check: a token like
            # `incline_dumbbell_bench_press` is a pre-coordinated entry and
            # must not exist. Hyphens, lowercase, no underscores.
            out.append(f"{slug!r} is not a slug - lowercase and hyphenated")
        for axis in AXES:
            value = data.get(axis)
            if value is None:
                # `load` is legitimately absent: an exercise done both ways -
                # a dip, a pull-up, a back extension - has no default, and
                # the SET has to say. `pattern` and `plane` are required.
                if axis != "load":
                    out.append(f"{slug!r} has no {axis}")
                continue
            for one in (value if isinstance(value, list) else [value]):
                if one not in axis_values(axis):
                    out.append(f"{slug!r} has {axis} {one!r}, which is not in "
                               f"restrictions.toml: "
                               f"{', '.join(axis_values(axis))}")
            if isinstance(value, list) and axis != "pattern":
                out.append(f"{slug!r} has a list {axis} - only `pattern` and "
                           "`region` are multi-valued")
        sites = data.get("region")
        if not sites:
            out.append(f"{slug!r} names no region")
        elif not isinstance(sites, list):
            out.append(f"{slug!r} has a non-list region - a movement loads "
                       "several sites and the field is a list")
        else:
            for site in sites:
                if resolve_site(site) is None:
                    out.append(f"{slug!r} names region {site!r}, which is not "
                               "a body_sites.toml slug")
        if not data.get("source"):
            out.append(f"{slug!r} does not say where it came from - `source` "
                       "records the licence position per entry")
    return out


# --- what a movement REQUIRES (#227) -----------------------------------------
#
# A prescription that cannot be provisioned is not a plan. These read the
# `fixture` and `kit` axes so a session's requirements are DERIVED from its
# exercise list rather than restated by every coach, app and template.
#
# The split is ownership, not size: a FIXTURE belongs to the place and is what
# the athlete would leave behind; KIT belongs to him and is what he takes.

FIXTURES = "fixtures"


def fixture_values() -> list[str]:
    return values(FIXTURES, "fixtures")


def kit_values() -> list[str]:
    return values(FIXTURES, "kit")


def fixtures_of(written: object) -> list[str] | None:
    """The fixtures a movement requires, or None if nobody annotated it.

    **None and [] are different answers and a caller must not conflate them.**
    `[]` means the movement needs nothing - a floor press, deliberately, as the
    contrast with a bench press. `None` means the registry has not been
    annotated for this exercise, and reading it as "needs nothing" is what
    strands an athlete at a park with a programme written for a rack.
    """
    e = entry(written)
    return None if "fixture" not in e else list(e.get("fixture") or [])


def kit_of(written: object) -> list[str] | None:
    """The kit a movement requires, or None if nobody annotated it.

    Same None/[] distinction as `fixtures_of`.
    """
    e = entry(written)
    return None if "kit" not in e else list(e.get("kit") or [])


def requirements(written_list: list) -> dict:
    """What a set of exercises needs, and what is not known.

    Returns `fixtures`, `kit` and `unannotated`. The third is the load-bearing
    one: a requirements list that silently omits the movements nobody
    catalogued would read as complete, and a consumer would answer "you can do
    this here" on evidence it does not have. Anything matching against a place
    must refuse, not guess, while `unannotated` is non-empty.
    """
    fx: set[str] = set()
    kt: set[str] = set()
    unknown: list[str] = []
    for written in written_list:
        f, k = fixtures_of(written), kit_of(written)
        if f is None and k is None:
            unknown.append(resolve_exercise(written))
            continue
        fx.update(f or [])
        kt.update(k or [])
    return {"fixtures": sorted(fx), "kit": sorted(kt),
            "unannotated": sorted(set(unknown))}


def validate_fixtures() -> list[str]:
    """Every `fixture`/`kit` value on an exercise names a fixtures.toml slug."""
    out: list[str] = []
    known_fx, known_kit = set(fixture_values()), set(kit_values())
    for slug, data in (registry(REGISTRY).get(SECTION) or {}).items():
        for axis, known in (("fixture", known_fx), ("kit", known_kit)):
            got = data.get(axis)
            if got is None:
                continue
            if not isinstance(got, list):
                out.append(f"{slug!r} has a non-list {axis} - a movement may "
                           "need several, and the field is a list")
                continue
            for value in got:
                if value not in known:
                    out.append(f"{slug!r} names {axis} {value!r}, which is not "
                               "a fixtures.toml slug")
    return out
