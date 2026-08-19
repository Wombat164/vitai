"""Does this record's own energy balance explain its own weight change? (#458)

#457 built #372's WIDTH and left the CENTRE, and filed #458 with an acceptance
gate: a proposed centre must sit inside the observed p10..p90 for that horizon.
Measuring it first is what this file exists to do, and the gate as filed cannot
be run - see `docs/proposals/weight-outlook.md` for the argument and the
numbers. What ships instead is the instrument that decides, and it never states
a centre.

THE CONTROL AT THE BOTTOM IS THE LOAD-BEARING TEST. Every other test here can
be satisfied by a function that answers "no" to everything, which is the exact
failure this surface is most likely to have: its honest answer on every record
this repo holds IS no. So a record whose weight is generated FROM its energy
balance is constructed here, and the measurement has to find it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from vitai.api import Vitai, init

DEMO = "examples/demo"
PERSONAS = Path(__file__).parent / "fixtures" / "personas"

# Every record in this repo, by what it can say about a modelled centre.
#
# THE FINDING, PINNED. Thirteen of sixteen hold not one complete seven-day
# window - a window needs `kcal_in` AND `kcal_out` on all seven days and a
# weigh-in at each end. The three that do answer NO: knowing the record's own
# energy balance does not narrow its own weight change, even with the energy
# density fitted to that record rather than taken from the literature.
#
# It is a register rather than an assertion about physiology, because it
# cannot be one: `examples/generate_demo.py` draws weight from
# `kg -= 0.05 * (0.7 + 0.6 * rng.random())` and energy from
# `rng.gauss(2850, 220)` and `rng.gauss(2065, 260)`, three unrelated streams.
# `nora` draws `kcal_in` from `rng.uniform(2050, 2200)` beside a weight series
# it never sees. The correlation is zero BY CONSTRUCTION, so this corpus can
# neither confirm nor refute an energy model - which is itself the reason the
# gate #458 proposed cannot be run.
ANSWERS_NO = {"examples/demo", "nora", "stefan"}
CANNOT_ANSWER = {"bea", "derek", "hana", "ines", "maja", "marcus", "otto",
                 "priya", "rachel", "sofia", "tom", "vera", "yasmin"}


def _roots():
    yield DEMO, Path(DEMO)
    for root in sorted(PERSONAS.iterdir()):
        if root.is_dir() and root.name != "_gen":
            yield root.name, root


def _coupled(tmp_path, n=140, density=7700.0, jitter=0.05):
    """A record whose weight IS its cumulative energy balance, plus noise.

    THE POSITIVE CONTROL. Deterministic rather than random - a fixture whose
    seed decides whether a test passes is not a control - so the balance walks
    a fixed cycle and the weigh-in noise walks another.
    """
    root = init(tmp_path / "coupled")
    v = Vitai(root)
    first = date.fromisoformat("2030-01-01")
    kg, wobble = 92.0, (0.0, jitter, -jitter, jitter / 2, -jitter / 2)
    for i in range(n):
        when = (first + timedelta(days=i)).isoformat()
        # A deficit that swings widely day to day, so the weekly sums differ
        # enough for a seven-day window to carry a signal.
        out = 2600 + 400 * ((i * 7) % 11) / 10
        into = 1900 + 900 * ((i * 5) % 13) / 12
        kg -= (out - into) / density
        v.append("daily", {"date": when, "kcal_out": round(out),
                           "kcal_in": round(into)})
        v.append("weight", {"date": when,
                            "kg": round(kg + wobble[i % len(wobble)], 2)})
    return v


# ------------------------------------------------------------------ the defect

def test_nothing_says_whether_a_centre_could_be_earned():
    """The gap, asserted rather than described. #458's acceptance gate is a
    property nobody can evaluate: there is no surface that says whether this
    record's energy balance explains its weight change at all."""
    assert hasattr(Vitai, "energy_agreement"), (
        "no engine surface answers whether a modelled centre could beat the "
        "record's own median, so the gate #458 proposed cannot be applied to "
        "any model anybody proposes")


# ------------------------------------------------------------- the corpus fact

def test_no_record_in_this_repository_supports_a_modelled_centre():
    """The finding, pinned in both directions.

    A record moving out of `CANNOT_ANSWER` means logging coverage grew, and a
    record moving out of `ANSWERS_NO` means an energy model started to earn
    its place - both are news, and both should fail this test rather than pass
    quietly.
    """
    answered, refused = set(), set()
    for name, root in _roots():
        out = Vitai(root).energy_agreement()
        (refused if out["refused"] else answered).add(name)
        if not out["refused"]:
            assert out["explains"] is False, (name, out)
    assert answered == ANSWERS_NO, sorted(answered)
    assert refused == CANNOT_ANSWER, sorted(refused)


def test_the_reason_most_records_cannot_answer_is_coverage_not_the_model():
    """Which distinguishes "the model failed" from "the model was never
    tried", and they are different facts about a record."""
    for name in sorted(CANNOT_ANSWER):
        out = Vitai(PERSONAS / name).energy_agreement()
        assert out["complete"] < out["possible"] or out["complete"] == 0, out
        assert "window" in out["refused"], (name, out["refused"])


# ------------------------------------------------------------- the measurement

def test_the_comparison_is_against_the_record_own_median():
    """The null is #457's answer, and it has to be, or "the model helps" would
    be measured against nothing. Re-derived here from `weight_outlook`, which
    shares no code path with this."""
    out = Vitai(DEMO).energy_agreement(days=7)
    week = [r for r in Vitai(DEMO).weight_outlook(days=7)["horizons"]
            if r["days"] == 7][0]
    # The outlook's spread runs over EVERY 7-day pair; this one runs over the
    # pairs whose week is fully logged, so they are close rather than equal -
    # and the point is that they are the same statistic on the same series.
    assert out["null_spread"] == pytest.approx(
        week["change_p90"] - week["change_p10"], abs=0.35)


def test_the_model_is_fitted_to_the_record_and_still_does_not_help():
    """GENEROUS ON PURPOSE. The literature 7700 kcal/kg is not what is tested:
    the energy density is fitted to this record by least squares, so the
    comparison is against the BEST constant-density model that exists for it.
    A family that cannot beat a median at its own best cannot beat it at
    7700."""
    out = Vitai(DEMO).energy_agreement()
    assert out["explains"] is False
    assert out["fitted_spread"] >= out["null_spread"] - 0.05
    assert abs(out["correlation"]) < 0.2, out


def test_the_implied_density_is_published_and_is_not_a_usable_constant():
    """It is the successor to "the 7700 rule is 60 per cent out", measured
    rather than hand-calculated on one span - and on this record the fit lands
    at five times the literature figure with a correlation of nearly zero,
    which is what a slope through noise looks like."""
    out = Vitai(DEMO).energy_agreement()
    assert out["implied_kcal_per_kg"] is not None
    assert abs(out["implied_kcal_per_kg"]) > 20000, out
    assert "correlation" in out, "the slope must never be published alone"


def test_the_two_floors_are_the_ones_the_outlook_already_uses(tmp_path):
    """Not a third pair of numbers. A quantile needs eleven samples to be
    interior and three disjoint stretches is `overlaps`' floor, and this
    surface reports the same two statistics over the same series."""
    from vitai.outlook import SAMPLE_FLOOR, WINDOW_FLOOR
    out = Vitai(DEMO).energy_agreement()
    assert out["complete"] >= SAMPLE_FLOOR
    assert out["windows"] >= WINDOW_FLOOR


def test_a_seam_refuses_it_for_the_reason_it_refuses_the_outlook(tmp_path):
    """A protocol change under the series means the two ends of a window are
    not two readings of one measurand, so the change across it is not a change
    and no model can be scored against it."""
    v = _coupled(tmp_path)
    assert v.energy_agreement()["explains"] is True
    marked = Vitai(init(tmp_path / "seamed"))
    rows = sorted(v.canonical("weight"), key=lambda r: r["date"])
    daily = sorted(v.canonical("daily"), key=lambda r: r["date"])
    for i, r in enumerate(rows):
        marked.append("weight", {"date": r["date"], "kg": r["kg"],
                                 "protocol": "fasted" if i < 70 else "fed"})
    for r in daily:
        marked.append("daily", {"date": r["date"], "kcal_out": r["kcal_out"],
                                "kcal_in": r["kcal_in"]})
    out = marked.energy_agreement()
    assert out["refused"] and "protocol" in out["refused"]


# ---------------------------------------------------------------- the control

def test_a_record_whose_weight_is_its_energy_balance_is_found(tmp_path):
    """THE CONTROL ON EVERYTHING ABOVE.

    Every other test here is satisfied by a function that answers no, and no
    is the honest answer on every record this repository holds - so without
    this one the whole surface could be a constant and the corpus register
    would still pass.

    A record is built whose weight IS its cumulative balance at 7700 kcal/kg
    plus a fixed weigh-in wobble. The measurement has to find it, recover the
    density it was built with, and say so.
    """
    out = _coupled(tmp_path).energy_agreement()
    assert out["refused"] is None
    assert out["explains"] is True
    assert out["correlation"] < -0.7, out
    # The density it was built with, recovered to within two per cent from
    # readings that never carried it - which is the whole claim, and a
    # stronger one than the spread comparison it implies.
    assert out["implied_kcal_per_kg"] == pytest.approx(7700, rel=0.02)
    assert out["fitted_spread"] < out["null_spread"]


def test_the_control_can_also_recover_a_different_density(tmp_path):
    """And it is not reading 7700 off a constant somewhere: a record built at
    a different energy density comes back at that one."""
    out = _coupled(tmp_path, density=5500.0).energy_agreement()
    assert out["explains"] is True
    assert out["implied_kcal_per_kg"] == pytest.approx(5500, rel=0.02)


def test_enough_weigh_in_noise_hides_a_real_coupling(tmp_path):
    """The other half of the control. A record that genuinely IS its energy
    balance, weighed badly enough, stops being detectable - so `explains` is a
    statement about what this record can show and never about physiology."""
    out = _coupled(tmp_path, jitter=3.0).energy_agreement()
    assert out["refused"] is None
    assert out["explains"] is False


# --------------------------------------------------------------------- P9

def test_the_cli_and_the_api_answer_the_same_thing():
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "energy-agreement",
                          "--root", DEMO, "--json"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == Vitai(DEMO).energy_agreement()


def test_it_never_states_a_centre():
    """The whole point. This surface says whether a centre could be earned and
    never what it would be - a key holding a predicted change would be read as
    one, whatever the docstring said."""
    out = Vitai(DEMO).energy_agreement()
    for key in out:
        assert "centre" not in key and "predict" not in key, key
    assert "kg" not in out
