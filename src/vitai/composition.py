"""What the scale cannot see: fat and fat-free mass, derived (#46, G36).

`schema.py` states the intent plainly - `kg` and `body_fat_pct` are the
OBSERVED atoms, and fat mass and fat-free mass are DERIVED from them, never
stored. The decision was recorded and then not built.

WHY IT EARNS ITS PLACE. A weight goal is a proxy. What an athlete usually
wants is less fat, and scale weight is a lossy stand-in that also moves with
water, glycogen and muscle. During a deficit the quantity that must not fall
much is fat-free mass, and losing it is the failure mode a scale cannot see:
two cuts ending at the same weight can be opposite outcomes, and a weight-only
view says one went down and one went up and stops there.

THE PART THAT MUST NOT BE SKIPPED, and the reason this is mostly a refusal.
Both outputs are arithmetic on a bioimpedance estimate, which moves with
hydration, recent food and recent exercise. Exact arithmetic on an input that
cannot support it, presented as a measurement, is the same failure as a 0 m
elevation from GPS noise or a 0 per cent goal from an unstated scope.

SO THE BAND COMES FROM THE RECORD, NOT FROM THE LITERATURE. A published
repeatability figure for consumer bioimpedance would be this engine asserting
a number about somebody else's hardware - the per-source accuracy claim it
refuses everywhere else. `kg_lo`/`kg_hi` and `body_fat_lo`/`body_fat_hi`
already exist for exactly this, and this is where they earn their place: a
change is resolvable when the two readings' fat-mass INTERVALS DO NOT OVERLAP,
which needs no constant at all.

A reading that declares no band cannot support that test, so the decomposition
is still stated and the CHANGE is declined. Not a number, not a guess, and not
a silent zero.
"""

from __future__ import annotations

from datetime import date

# The interval a value covers, or None where the row declared no band.
Band = tuple[float, float] | None


def _band(point: float | None, lo: float | None, hi: float | None) -> Band:
    """A declared interval, or None. A half-declared band is not a band: a row
    with a floor and no ceiling bounds nothing, and treating the point as the
    missing end would invent the half the athlete did not state."""
    if point is None or lo is None or hi is None:
        return None
    return (float(min(lo, hi)), float(max(lo, hi)))


def fat_mass(rec: dict) -> float | None:
    """Kilograms of fat, or None where the row cannot say."""
    kg, pct = rec.get("kg"), rec.get("body_fat_pct")
    if kg is None or pct is None:
        return None
    return float(kg) * float(pct) / 100.0


def fat_free_mass(rec: dict) -> float | None:
    """Kilograms of everything else."""
    fat = fat_mass(rec)
    return None if fat is None else float(rec["kg"]) - fat


def fat_mass_band(rec: dict) -> Band:
    """The interval fat mass covers, given the bands the row declared.

    Both ends move together: the low end is the lightest weight at the lowest
    fat share, the high end the heaviest at the highest. That is wider than
    propagating one band alone, and the wider answer is the honest one - the
    two uncertainties are not known to cancel.
    """
    kg = _band(rec.get("kg"), rec.get("kg_lo"), rec.get("kg_hi"))
    pct = _band(rec.get("body_fat_pct"), rec.get("body_fat_lo"),
                rec.get("body_fat_hi"))
    if kg is None or pct is None:
        return None
    return (kg[0] * pct[0] / 100.0, kg[1] * pct[1] / 100.0)


def _overlap(a: Band, b: Band) -> bool:
    return a is not None and b is not None and a[0] <= b[1] and b[0] <= a[1]


def decompose(first: dict, last: dict) -> dict | None:
    """How a weight change divided between fat and everything else.

    Returns None where either reading cannot be decomposed at all - a row with
    no `body_fat_pct` is simply absent from this, never imputed.

    `resolvable` is the whole discipline. It is True only where both readings
    declared a band AND those bands do not overlap; False where they overlap;
    and None where the record did not say, which is a third answer rather than
    a cautious False. The share of the change is emitted only when the change
    is resolvable, because a percentage of a difference the instrument cannot
    see is a figure invented by division.
    """
    if fat_mass(first) is None or fat_mass(last) is None:
        return None
    fat_from, fat_to = fat_mass(first), fat_mass(last)
    lean_from, lean_to = fat_free_mass(first), fat_free_mass(last)
    total = float(last["kg"]) - float(first["kg"])
    bands = (fat_mass_band(first), fat_mass_band(last))
    resolvable = None if None in bands else not _overlap(*bands)

    out = {
        "from": first.get("date"), "to": last.get("date"),
        "kg_change": round(total, 2),
        "fat_change": round(fat_to - fat_from, 2),
        "fat_free_change": round(lean_to - lean_from, 2),
        "resolvable": resolvable,
        "fat_share": None,
    }
    if resolvable and total:
        out["fat_share"] = round((fat_to - fat_from) / total * 100.0, 1)
    return out


def endpoints(rows: list[dict], within_days: int | None = None,
              today: date | None = None) -> tuple[dict, dict] | None:
    """The first and last readings that can be decomposed at all.

    Ordered by the day they describe, because a decomposition is a statement
    about a period rather than about the order two rows were written in.
    """
    usable = sorted((r for r in rows if fat_mass(r) is not None),
                    key=lambda r: str(r.get("date") or ""))
    if len(usable) < 2:
        return None
    return usable[0], usable[-1]
