"""What every interval-shaped field claims, and where its width came from.

#402 says estimates should carry error bands and the bands must be earned.
Measuring before building, which is what the last three changes were for, says
the first thing to fix is not a missing band - it is that the intervals already
shipped do not say what they are.

FOUR `_lo`/`_hi`-SHAPED FIELDS, AT LEAST THREE MEANINGS. `weight.kg_lo` is a
limit an instrument stated; `meals.grams_lo` is a range whoever estimated the
portion gave; `comparability.difference_lo` is the lowest difference observed,
which `db.py` says in as many words is NOT a band; `goals.target_hi` is the far
end of an intention. One naming convention, and nothing anywhere states which
is which - no `u_given_as`, no coverage factor, no `ci95` in `src/`.

#465 is what that costs. A standard uncertainty described as a 95 per cent
half-width understated a finding by a factor of two, in this repository's own
shipped comments, and it stood until the number was recomputed. The remedy
there was to publish both ratios and name them; the remedy here is the same
rule generalised - a coverage word that says what it covers, beside a basis
word that says where the width came from.

WHAT EARNED MEANS, AS A RULE:

1. A band names a BASIS from a closed set, which is #402's list and no more.
   Nothing may supply a width because it seems about right.
2. A band names what it COVERS, from a closed set whose every member states
   the claim out loud. `lo`/`hi` name no coverage, so the word beside them must.
3. A field with no declared width HAS NO WIDTH. That is #402's third state -
   estimated, width unknown - and it needs no register and no default, because
   the honest answer is the absence itself.
4. An interval-shaped field that is NOT a band says so. Silence would read as
   an oversight and a consumer would apply the convention to it.

WHY REFUSING IS RIGHT FOR A RECORD THAT CANNOT EARN ONE, which is most of them.
Twelve of the sixteen records here cannot even feed the weekly-mean estimator
(#460), and `daily.kcal_out` - the field #402 was actually raised about - has
no overlap, no published figure and nothing the athlete said. The alternative
to refusing is a number that looks measured on the one field whose whole
problem is that nobody measured it, which is the failure this issue names in
its own words. An absent width is legible; an invented one is not.

NOTHING NEW IS BANDED HERE. This publishes what the schema already ships,
which is the part that can be stated truthfully today.
"""

from __future__ import annotations

import tomllib
from importlib import resources

# WHAT A PAIR CLAIMS ABOUT THE VALUE. Every member names its coverage out loud,
# which is #457's `p10`/`p90` lesson generalised: a word like `band` or
# `interval` restates the shape and claims nothing.
COVERS = {
    "limits": ("the value lies between them - validated bounds, asserting no "
               "distribution and no probability"),
    "stated-range": ("somebody said the value is somewhere in here, which is "
                     "testimony about a range and is not modelled at all"),
}

# WHERE THE WIDTH CAME FROM. #402's closed list, minus the member nothing uses:
# `measured-overlap` is its strongest basis and no field earns one yet.
BASES = {
    "source-published": ("the instrument or table that produced the value "
                         "stated the width, recorded as given"),
    "written-with-the-value": ("whoever recorded the value gave a range "
                               "instead of a figure, as part of the same "
                               "claim"),
}

AXES = {"covers": COVERS, "basis": BASES}


def declaration() -> dict[str, dict]:
    """Every interval-shaped field, by `dataset.field` without the suffix."""
    path = resources.files("vitai") / "semantics" / "bands.toml"
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    out = {}
    for name, body in sorted(raw.get("band", {}).items()):
        out[name] = {
            "kind": body["kind"],
            # Present rather than absent on a non-band, so a consumer reads one
            # shape and a missing key never has to be told from a null one.
            "basis": body.get("basis"),
            "covers": body.get("covers"),
            "says": body["says"],
            "basis_says": BASES.get(body.get("basis", ""), None),
            "covers_says": COVERS.get(body.get("covers", ""), None),
        }
    return out


def unresolved(axis: str, word: str) -> str | None:
    """Why `word` is not a member of `axis`, or None. Raises on a bad axis."""
    vocabulary = AXES[axis]
    if word not in vocabulary:
        return (f"'{word}' is not one of {', '.join(sorted(vocabulary))} - a "
                f"vocabulary whose members are free text is prose with a "
                f"colon in front")
    return None


def band_for(dataset: str, field: str) -> dict | None:
    """The band on `dataset.field`, or None where the record knows no width.

    NONE IS AN ANSWER AND NOT A GAP. It is #402's third state - estimated,
    width unknown - and it is the honest description of nearly every field
    here, including the one the issue was raised about. There is deliberately
    no path through this function that invents one.
    """
    entry = declaration().get(f"{dataset}.{field}")
    return entry if entry and entry["kind"] == "band" else None
