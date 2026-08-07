"""What the scale cannot see (#46, G36).

`schema.py` stated the intent plainly - `kg` and `body_fat_pct` are the
OBSERVED atoms, fat mass and fat-free mass are DERIVED and never stored - and
then nothing was built.

A weight goal is a proxy. What an athlete usually wants is less fat, and scale
weight is a lossy stand-in that also moves with water, glycogen and muscle.
Two cuts ending at the same weight can be opposite outcomes, and a weight-only
view says one went down and one went up and stops there.

MOSTLY A REFUSAL, and that is the half worth guarding. Both figures are
arithmetic on a bioimpedance estimate, and exact arithmetic on an input that
cannot support it, presented as a measurement, is the failure this project
names elsewhere as a 0 m elevation from GPS noise.

THE BAND COMES FROM THE RECORD, NOT FROM THE LITERATURE. A published
repeatability figure for consumer bioimpedance would be this engine asserting
a number about somebody else's hardware, which it refuses everywhere else.
`kg_lo`/`kg_hi` and `body_fat_lo`/`body_fat_hi` already existed with no
consumer at all - they are the band, and a change is resolvable when the two
readings' fat-mass intervals do not overlap. No constant anywhere.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.composition import (decompose, endpoints, fat_free_mass, fat_mass,
                               fat_mass_band)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _reading(kg: float, pct: float, *, band: float = 0.6, day: str = "2030-01-01",
             kg_band: float = 0.1) -> dict:
    return {"date": day, "kg": kg, "body_fat_pct": pct,
            "kg_lo": kg - kg_band, "kg_hi": kg + kg_band,
            "body_fat_lo": pct - band, "body_fat_hi": pct + band}


def _bare(kg: float, pct: float, day: str = "2030-01-01") -> dict:
    return {"date": day, "kg": kg, "body_fat_pct": pct}


# --- derived, never stored ------------------------------------------------

def test_fat_and_fat_free_are_derived_from_the_two_atoms():
    rec = _bare(80.0, 20.0)

    assert fat_mass(rec) == 16.0
    assert fat_free_mass(rec) == 64.0


def test_neither_is_a_field():
    """G36 as written: the atoms are observed and these are computed on
    demand. A stored decomposition would go stale the moment either atom was
    corrected."""
    from vitai.schema import KEYS

    assert "fat_mass" not in KEYS["weight"]
    assert "fat_free_mass" not in KEYS["weight"]


def test_a_reading_without_a_composition_is_absent_rather_than_imputed():
    """Most rows in most records are a mass and nothing else. Filling in a
    body-fat share for them would be the engine inventing the input."""
    assert fat_mass({"date": "2030-01-01", "kg": 80.0}) is None
    assert decompose({"date": "2030-01-01", "kg": 80.0}, _bare(78.0, 19.0)) is None


def test_the_endpoints_skip_rows_that_cannot_be_decomposed():
    rows = [_bare(88.0, 24.0, "2030-01-01"),
            {"date": "2030-02-01", "kg": 84.0},
            _bare(80.0, 19.0, "2030-03-01")]

    first, last = endpoints(rows)

    assert (first["date"], last["date"]) == ("2030-01-01", "2030-03-01")


def test_two_readings_are_needed():
    assert endpoints([_bare(80.0, 20.0)]) is None
    assert endpoints([]) is None


# --- the refusal ----------------------------------------------------------

def test_a_change_the_instrument_cannot_see_is_not_a_number():
    """The two readings' fat-mass ranges overlap, so the record cannot say
    which way fat moved. Reporting a share here would be a percentage of a
    difference nothing observed."""
    split = decompose(_reading(88.0, 24.0, day="2030-01-01"),
                      _reading(87.6, 23.9, day="2030-03-01"))

    assert split["resolvable"] is False
    assert split["fat_share"] is None


def test_a_change_larger_than_the_band_is_reported():
    """And this is the finding a weight-only view cannot produce."""
    split = decompose(_reading(88.0, 24.0, day="2030-01-01"),
                      _reading(80.0, 19.0, day="2030-09-01"))

    assert split["resolvable"] is True
    assert split["fat_change"] < 0
    assert 70 <= split["fat_share"] <= 80


def test_a_reading_with_no_band_declines_rather_than_assuming_one():
    """A THIRD ANSWER, not a cautious False. The record did not say what the
    reading's range was, so nothing here can say whether a change is real -
    and treating that as "not resolvable" would blame the instrument for the
    record's silence."""
    split = decompose(_bare(88.0, 24.0, "2030-01-01"),
                      _bare(80.0, 19.0, "2030-09-01"))

    assert split["resolvable"] is None
    assert split["fat_share"] is None
    assert split["fat_change"] < 0


def test_a_half_declared_band_is_not_a_band():
    """A row with a floor and no ceiling bounds nothing, and taking the point
    estimate as the missing end would invent the half nobody stated."""
    rec = {"date": "2030-01-01", "kg": 80.0, "body_fat_pct": 20.0,
           "kg_lo": 79.9, "kg_hi": 80.1, "body_fat_lo": 19.4}

    assert fat_mass_band(rec) is None


def test_the_band_widens_with_both_uncertainties():
    """Both ends move together: the lightest weight at the lowest share, the
    heaviest at the highest. Wider than propagating one alone, and the wider
    answer is the honest one - the two are not known to cancel."""
    narrow = fat_mass_band(_reading(80.0, 20.0, band=0.2, kg_band=0.05))
    wide = fat_mass_band(_reading(80.0, 20.0, band=2.0, kg_band=1.0))

    assert wide[1] - wide[0] > narrow[1] - narrow[0]


def test_no_repeatability_constant_appears_anywhere():
    """The band is the record's. A published figure for consumer bioimpedance
    would be this engine asserting an accuracy claim about hardware it has
    never seen, which is the per-source accuracy claim it refuses everywhere
    else."""
    source = (Path(__file__).resolve().parents[1]
              / "src" / "vitai" / "composition.py").read_text()

    for smell in ("2.5", "3.0", "REPEATABILITY", "NOISE_FLOOR", "TOLERANCE"):
        assert smell not in source, smell


# --- what a reader sees ---------------------------------------------------

def test_the_rollup_says_how_the_change_divided():
    """The section a weight-only view cannot produce."""
    text = Vitai(DEMO).rollup(date(2030, 6, 30))

    assert "## Composition" in text
    assert "of the change was fat" in text


def test_the_rollup_says_not_resolvable_rather_than_a_number(tmp_path):
    """The refusal has to reach the page, or the discipline lives only in a
    function nobody reads."""
    from vitai.api import init

    v = Vitai(init(tmp_path / "content"))
    for day, kg, pct in (("2030-05-01", 88.0, 24.0), ("2030-05-20", 87.6, 23.9)):
        v.append("weight", {"date": day, "kg": kg, "source": "dexa",
                            "body_fat_pct": pct, "kg_lo": kg - 0.1,
                            "kg_hi": kg + 0.1, "body_fat_lo": pct - 0.6,
                            "body_fat_hi": pct + 0.6})

    text = v.rollup(date(2030, 6, 1))

    assert "NOT RESOLVABLE" in text
    assert "of the change was fat" not in text


def test_a_record_with_no_composition_gets_no_section(tmp_path):
    """Most records. A section saying nothing is the bulk #76 has just spent a
    PR removing."""
    from vitai.api import init

    v = Vitai(init(tmp_path / "content"))
    v.append("weight", {"date": "2030-05-01", "kg": 80.0, "source": "scale"})

    assert "## Composition" not in v.rollup(date(2030, 6, 1))


def test_the_shipped_record_carries_the_bands():
    """#204's corollary, and these five fields had no writer in any fixture -
    so a decomposition tested only on synthetic rows would prove nothing about
    the shape a real reading arrives in."""
    banded = [r for r in Vitai(DEMO).dataset("weight")
              if r.get("body_fat_pct") is not None]

    assert len(banded) >= 2
    for row in banded:
        assert fat_mass_band(row) is not None
