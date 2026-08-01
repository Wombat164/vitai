"""An itemised meal estimate, with a range that never collapses (#96).

A photograph of a meal should produce an ITEMISED estimate, not a single
number. Every app that does photo estimation hands back one confident total,
and the total is the least defensible part of the answer: it cannot be
corrected, cannot be questioned, and cannot say which part it is unsure about.

## What the image settles, and what it does not

Worked end to end on a real meal, which is where the split comes from:

- **Composition is what a photograph settles WELL.** A description said
  "crispy chicken" and was read as breaded, at ~280 kcal/100 g. The image
  showed caramelised skin with visible meat grain - crispy-skinned thigh, at
  ~240. The picture corrected the food.
- **Portions are what a photograph settles BADLY.** With no scale reference
  beyond a fork and a plate, 30 g of chicken either way is 72 kcal. No amount
  of model effort on the pixels recovers that; one question does.
- **A photograph can corroborate independently.** The athlete said no
  dressing; the leaves are matte, and a second bowl in the same frame carries
  obvious creamy dressing. Same light, same shot. That is ~250-350 kcal not
  eaten, settled in-frame rather than on trust.

So asking is a first-class step rather than a fallback, and the range on an
item is the honest output of the part the image cannot settle.

## Why the composition figures live on the row

An item stores what the table SAID - kcal and macros per 100 g - plus the name
of the table it came from. The energy of the item is then derived from the
quantity, never stored (the same rule as pace and totals everywhere else).

That looks like duplication and is not. A composition table is an EXTERNAL
fact that changes: entries get revised, and a record that stored only
`table: "usda"` and a gram count would silently re-price a meal from two years
ago the day the table shipped an update. Storing the figures used makes the
row reproducible, and storing the table name makes it auditable.

It also means this module ships no food data and takes no position on which
table to use - a licence question, and a real one.

**The distinction that matters, so nobody vendors past it by accident.** Open
Food Facts is ODbL, and the share-alike attaches to the DATABASE rather than
to code that queries it. Bundling OFF entries into a shipped `foods.toml`
would make that derived table ODbL and bind every fork of this MIT engine.
Querying it at runtime, or an athlete pointing the engine at their own copy,
does not. USDA FoodData Central is public domain and carries no such
condition; CIQUAL, NEVO and NUBEL are regionally far better for prepared food
and each have their own terms, which is a check to make before copying rather
than after.

Storing the figures on the row is what keeps that a choice: the record holds
what some table said, this module holds no table at all, and the decision can
be made once and written down.

## No numeric confidence, ever

There is no corpus of photo-estimated meals scored against weighed truth, so
a `0.6` here would be a decimal point pretending to be calibration. **The
range IS the confidence statement** (P4).

## A meal is not a day

The one that bites. `stated-in-chat` outranks `mfp-export` in the precedence
ladder, so writing a meal estimate into `daily.kcal_in` DISPLACES an itemised
whole-day entry from the athlete's own logger when it arrives. Meal estimates
therefore live here and are never summed into `kcal_in` by this engine. When
both exist, `day_disagreements` REPORTS the pair - a partial day and a whole
day are different quantities, and the comparison is informative precisely
because neither is a correction of the other.
"""

from __future__ import annotations

from math import isfinite

DATASET = "meals"

# Per-100 g composition, as the table gave it, and what each contributes.
MACROS = ("protein_g", "fat_g", "carb_g")
_PER_100 = {"kcal": "kcal_100g", "protein_g": "protein_100g",
            "fat_g": "fat_100g", "carb_g": "carb_100g"}

# The energy an athlete would have to be wrong about before the split between
# two readings of a meal matters more than the total. Below this, saying which
# item dominates the range is noise.
NARRATIVE_FLOOR_KCAL = 15.0


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def quantity_range(row: dict) -> tuple[float, float, float] | None:
    """(lo, estimate, hi) grams for one item, or None if no quantity is stated.

    A row with no `grams_lo`/`grams_hi` is a point estimate that nobody has
    bounded, which is treated as a zero-width range rather than as certainty:
    the caller can see the width is zero and that it was never widened.
    """
    point = _num(row.get("grams"))
    if point is None:
        return None
    lo = _num(row.get("grams_lo"))
    hi = _num(row.get("grams_hi"))
    return (point if lo is None else lo, point, point if hi is None else hi)


def item_energy(row: dict, field: str = "kcal") -> tuple[float, float, float] | None:
    """(lo, estimate, hi) for one item and one nutrient, derived from grams.

    Derived rather than stored, like every other computable quantity in this
    record: an item whose gram estimate is corrected must not keep an energy
    figure computed from the old one.
    """
    grams = quantity_range(row)
    per_100 = _num(row.get(_PER_100[field]))
    if grams is None or per_100 is None:
        return None
    return tuple(g * per_100 / 100.0 for g in grams)  # type: ignore[return-value]


def meal_total(rows: list[dict], field: str = "kcal") -> dict:
    """The itemised sum, WITH its range - the only form this is ever reported.

    `unpriced` is the count of items nobody could price. They are named rather
    than dropped: a total that silently omits the olive oil is wrong in the
    direction that matters most, and an item present with no composition is a
    lookup that has not happened yet, not an item that contributes nothing.
    """
    lo = est = hi = 0.0
    priced = unpriced = 0
    for row in rows:
        span = item_energy(row, field)
        if span is None:
            unpriced += 1
            continue
        priced += 1
        lo += span[0]
        est += span[1]
        hi += span[2]
    return {"field": field, "lo": lo, "estimate": est, "hi": hi,
            "width": hi - lo, "items": len(rows), "priced": priced,
            "unpriced": unpriced,
            "complete": unpriced == 0 and priced > 0}


def dominant_uncertainty(rows: list[dict], field: str = "kcal") -> dict | None:
    """Which item contributes most of the total's width, and how much of it.

    The narrative half of the requirement. "600, give or take 90" is less
    useful than "600, and 70 of the 90 is how much chicken is on the plate" -
    the second tells the athlete which single question would collapse the
    range, which is the whole point of estimating item by item.
    """
    widths = []
    for row in rows:
        span = item_energy(row, field)
        if span is not None and span[2] - span[0] > 0:
            widths.append((span[2] - span[0], row))
    if not widths:
        return None
    total = sum(w for w, _ in widths)
    width, row = max(widths, key=lambda t: t[0])
    if total < NARRATIVE_FLOOR_KCAL:
        return None
    return {"item": row.get("item"), "width": width, "of_total": total,
            "share": width / total if total else 0.0}


def unsettled(rows: list[dict]) -> list[dict]:
    """Items whose quantity nobody has pinned down - each one a QUESTION.

    Asking is a first-class step, not a fallback, and a specific question
    ("how many olives") removes more error than any refinement of the image
    analysis. This names the item and what is missing; the wording of the
    question belongs to the skill, which can see the photograph.
    """
    out = []
    for row in rows:
        grams = quantity_range(row)
        if grams is None:
            out.append({"item": row.get("item"), "missing": "quantity",
                        "why": "no quantity is stated at all"})
        elif row.get("grams_lo") is None or row.get("grams_hi") is None:
            out.append({"item": row.get("item"), "missing": "range",
                        "why": ("a point estimate that was never bounded"
                                if grams[2] - grams[0] == 0
                                else "bounded on one side only")})
    return out


def buffered(total: dict, pct: float | None) -> dict:
    """Apply the athlete's stated intake buffer - policy, not a model output.

    Under-counting intake is the error that stalls a deficit while looking
    like adherence, so an athlete may choose to carry a margin. That is a
    stated policy applied to EVERY meal or to none: a buffer on some and not
    others corrupts every comparison in the series, which is why it lives in
    config rather than in a judgement call per meal.

    The unbuffered figures are kept beside the buffered ones. A number the
    athlete cannot decompose back into what was estimated and what was policy
    is a number they cannot check.
    """
    if pct is None:
        return {**total, "buffer_pct": None}
    if not isfinite(pct) or pct < 0:
        # A negative buffer inverts the range (lo > hi) and a NaN makes every
        # figure NaN, both silently. A stated policy that cannot be applied is
        # a configuration error, not a number to propagate.
        raise ValueError(
            f"intake_buffer_pct is a margin in percent and cannot be negative "
            f"or non-finite, got {pct!r}")
    factor = 1.0 + pct / 100.0
    return {**total,
            "lo": total["lo"] * factor, "estimate": total["estimate"] * factor,
            "hi": total["hi"] * factor, "width": total["width"] * factor,
            "buffer_pct": pct,
            "unbuffered": {k: total[k] for k in ("lo", "estimate", "hi")}}


def by_meal(rows: list[dict], on: str | None = None) -> dict[str, list[dict]]:
    """Items grouped by (date, meal), optionally for one date."""
    out: dict[str, list[dict]] = {}
    for row in rows:
        if on and row.get("date") != on:
            continue
        out.setdefault(f"{row.get('date')} {row.get('meal') or 'unnamed'}",
                       []).append(row)
    return out


def day_disagreements(meal_rows: list[dict],
                      resolved_daily: list[dict]) -> list[dict]:
    """Where a day's meal estimates and a stated whole-day intake both exist.

    REPORTED, never resolved. A partial day and a whole day are different
    quantities: meals the athlete did not photograph are missing from one and
    present in the other, so the meal sum being lower is the expected case
    rather than a disagreement to adjudicate.

    This exists because the precedence ladder would happily "resolve" it the
    wrong way round. `stated-in-chat` outranks `mfp-export`, so a meal
    estimate written into `kcal_in` would displace an itemised whole-day entry
    from the athlete's own logger - a model's guess beating the athlete's own
    record, which is the #88 defect one domain over.

    THE INPUT CONTRACT, which used to live in one caller's comment (#152).
    `resolved_daily` is ADJUDICATED rows - one per date - not raw claims. The
    lookup was a dict comprehension, so with two sources on one day the answer
    was whichever row came last in file order, and file order for `daily` is
    (date, source): an ordering, but not a PRECEDENCE ordering. The same rows
    in the other order gave the other figure, silently.

    That inverts the function's own purpose. It exists to stop a meal estimate
    displacing the athlete's own whole-day figure, and handed raw claims it
    could quote the very figure precedence rejected - then compare an itemised
    estimate against it. Comparing against a superseded number is worse than
    not comparing.

    So ambiguity is REFUSED rather than resolved by luck. An invariant only
    one caller knows about is not an invariant; it is a coincidence with good
    documentation, and it survives exactly until somebody adds a second
    caller.
    """
    stated: dict[str, dict] = {}
    ambiguous: dict[str, list[dict]] = {}
    for row in resolved_daily:
        date = row.get("date")
        if not date or _num(row.get("kcal_in")) is None:
            continue
        # `str(date)` on BOTH sides. Testing the raw value against a
        # str-keyed dict meant a non-string date never matched, so the
        # ambiguity guard missed it and the dict comprehension's
        # last-writer-wins came straight back - the exact defect this is
        # fixing, surviving inside the fix.
        key = str(date)
        if key in stated:
            ambiguous.setdefault(key, [stated[key]]).append(row)
        stated[key] = row

    days = {str(r.get("date")) for r in meal_rows if r.get("date")}
    out = []
    # ONE date-ordered pass over the days with meals. Emitting the ambiguous
    # findings and then the normal ones gave a list that was sorted within
    # each group and out of order overall, so a reader scanning dates saw
    # September before January.
    #
    # Days only. This function reports where a day's meal estimates and a
    # stated intake BOTH exist, and an ambiguous daily row on a day with no
    # meals is not in its scope.
    for date in sorted(days):
        if date not in stated:
            continue
        if date not in ambiguous:
            rows = [r for r in meal_rows if str(r.get("date")) == date]
            total = meal_total(rows)
            day = _num(stated[date].get("kcal_in"))
            out.append({
                "date": date, "ambiguous": False,
                "meals_lo": total["lo"], "meals_hi": total["hi"],
                "stated": day, "stated_source": stated[date].get("source"),
                "meals_cover": total["complete"],
                "detail": (f"{len(rows)} estimated item(s) sum to "
                           f"{total['lo']:.0f}-{total['hi']:.0f} kcal; the "
                           f"day is logged at {day:.0f} by "
                           f"{stated[date].get('source') or 'an unnamed source'}"
                           ". A partial day is not a correction to a whole "
                           "one - neither figure supersedes the other")})
            continue
        candidates = ambiguous[date]
        sources = ", ".join(sorted(str(r.get("source") or "an unnamed source")
                                   for r in candidates))
        out.append({
            "date": date, "meals_lo": None, "meals_hi": None,
            "stated": None, "stated_source": None, "meals_cover": False,
            "ambiguous": True,
            "detail": (f"{len(candidates)} whole-day intake figures for "
                       f"{date} ({sources}), so there is no single stated day "
                       "to compare against. These are raw claims rather than "
                       "resolved rows - pass the canonical daily, because "
                       "picking one by file order would quote whichever "
                       "source name happens to sort later")})
    return out


def problems(rec: dict) -> list[str]:
    """Validation for one meal item."""
    out: list[str] = []
    if not str(rec.get("meal") or "").strip():
        # REQUIRED, for the same reason `set_index` is on `sets`. `item` is
        # required and this was not, so two items of the same name on one
        # date - two coffees, or one ingredient in two unnamed snacks - shared
        # an identity, and a `supersedes` naming either was ambiguous. A row
        # nobody can name is a row nobody can correct.
        #
        # It costs one word. An unnamed snack is `meal: "snack"`, which is
        # what the athlete would say anyway.
        out.append("'meal' names which meal this item belongs to - 'lunch', "
                   "'snack'. It is required because it is half of the row's "
                   "identity: without it two items of the same name on one "
                   "date cannot be told apart, so neither can be corrected")
    if not str(rec.get("item") or "").strip():
        out.append("'item' names the ingredient - the unit of estimate is the "
                   "ingredient, never the dish, because a dish-level number "
                   "cannot be corrected or questioned")
    grams = quantity_range(rec)
    lo, hi = _num(rec.get("grams_lo")), _num(rec.get("grams_hi"))
    if grams is not None and not grams[0] <= grams[1] <= grams[2]:
        out.append(f"quantity range out of order: grams_lo<=grams<=grams_hi "
                   f"violated ({grams[0]} <= {grams[1]} <= {grams[2]})")
    for key in ("grams", "grams_lo", "grams_hi"):
        value = _num(rec.get(key))
        if value is not None and value < 0:
            # A negative quantity passes the ordering check (-50 <= -50 <= -50)
            # and SUBTRACTS energy, so one mistyped row drags a plate's total
            # down by an arbitrary amount rather than failing.
            out.append(f"'{key}' is a quantity in grams and cannot be "
                       f"negative, got {rec.get(key)!r}")
    if (lo is not None or hi is not None) and _num(rec.get("grams")) is None:
        out.append("'grams_lo'/'grams_hi' bound an estimate, so they need a "
                   "'grams' to bound")
    if (lo is None) != (hi is None):
        # Half a range reads as a whole one: `quantity_range` substitutes the
        # point for the missing side, so 140-165-(none) prints as "140-165 g"
        # and the uncertainty in the OTHER direction is silently erased -
        # upwards, which is the direction that under-counts intake.
        out.append("a quantity range needs both 'grams_lo' and 'grams_hi': "
                   "one bound alone reads as a bounded estimate and hides the "
                   "uncertainty on the other side")
    for field, key in _PER_100.items():
        value = _num(rec.get(key))
        if value is not None and value < 0:
            out.append(f"'{key}' is per 100 g and cannot be negative, "
                       f"got {rec.get(key)!r}")
    priced = any(_num(rec.get(k)) is not None for k in _PER_100.values())
    if priced and not str(rec.get("food_table") or "").strip():
        # Per-item provenance, for the same reason `origin` exists: two items
        # in one meal can legitimately come from different tables, and a
        # composition figure whose source is unrecorded cannot be rechecked
        # when that table is revised.
        out.append("a composition figure needs a 'food_table' naming where it was "
                   "looked up (e.g. 'usda', 'ciqual', 'nubel')")
    return out
