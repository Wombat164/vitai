"""What this record's weight has actually done over an elapsed interval (#372).

THE ASK was a forward band for weight from the regime plus `kcal_in` and
`kcal_out`. THE DECISION (operator, 2026-08-12) moved the WIDTH off the energy
inputs entirely: it is "the residual scatter of the athlete's own weigh-in
series around its own trend", measured rather than borrowed, because no
published 24-hour expenditure validation exists for wrist-optical devices of
this class and any daily uncertainty term would be extrapolated from bout data
and presented as though it were sourced.

THIS FILE HOLDS THE MEASUREMENT TO BEING ONE. Every number the outlook states
is re-derived here from `canonical()` by a second route, and the two gates that
decide whether a horizon may be stated at all - the independent-window count
and the sample size a quantile needs to be interior - are checked to bite.

THE CONSISTENCY GATE at the bottom is the one that matters most and is not
like the others. `verdicts.ANSWERS_BY_METRIC` scores `weight_rate` as a
DIRECTION rather than a number because this project's pre-registered run
measured the median 95 per cent half-width of a week-over-week rate at 1.74
times the entire decision half-band. An outlook that drew a one-week band
NARROWER than that band would be the same engine claiming, one surface over, a
precision it had already measured away. So the seven-day horizon is asserted
to be wider than the band `weight_rate` is judged against, on the engine's own
constant, and the day this stops holding one of the two is wrong.
"""

from __future__ import annotations

import json
import statistics as st
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.verdicts import RATE_DECISION_BAND

DEMO = "examples/demo"
PERSONAS = Path(__file__).parent / "fixtures" / "personas"


def _series(root=DEMO) -> list[tuple[date, float]]:
    """One value per date, from the engine's own resolution, second route."""
    rows = [r for r in (Vitai(root).canonical().get("weight") or [])
            if r.get("kg") is not None]
    return sorted((date.fromisoformat(r["date"]), float(r["kg"])) for r in rows)


def _changes(series, days: int) -> list[float]:
    index = dict(series)
    out = []
    for when, kg in series:
        later = index.get(when + timedelta(days=days))
        if later is not None:
            out.append(later - kg)
    return sorted(out)


def _record(tmp_path, points, **extra):
    """A record holding exactly these (date, kg) readings."""
    root = init(tmp_path / "r")
    v = Vitai(root)
    for when, kg in points:
        v.append("weight", {"date": when, "kg": kg, **extra})
    return v


def _straight(start: str, n: int, step: float, wobble=(0.0,)):
    """`n` daily readings falling by `step`, with a repeating wobble on top."""
    first = date.fromisoformat(start)
    return [((first + timedelta(days=i)).isoformat(),
             round(80.0 - i * step + wobble[i % len(wobble)], 3))
            for i in range(n)]


# --------------------------------------------------------------- the defect

def test_nothing_states_an_earned_width_today():
    """The gap, asserted rather than described.

    A client drawing a drift cone has to choose a width, and every width
    available to it today is one it invented: this engine publishes the
    readings and no statement about how far apart they run.
    """
    assert hasattr(Vitai, "weight_outlook"), (
        "no engine surface states what this record's own weight has done over "
        "an elapsed interval, so the width of any cone drawn from it is a "
        "number the client chose")


# ------------------------------------------------------- measured, not modelled

def test_every_horizon_restates_what_the_record_did():
    """Re-derived by a second route, from `canonical()` rather than from the
    module under test. A centre that came from a model rather than from the
    readings would part company with this immediately."""
    out = Vitai(DEMO).weight_outlook()
    assert out["horizons"], out
    for row in out["horizons"]:
        seen = _changes(_series(), row["days"])
        assert row["observed"] == len(seen), row["days"]
        assert row["change"] == pytest.approx(st.median(seen), abs=1e-9), row
        assert row["change_p10"] == pytest.approx(seen[int(0.10 * (len(seen) - 1))])
        assert row["change_p90"] == pytest.approx(seen[int(0.90 * (len(seen) - 1))])


def test_the_width_moves_with_the_record_rather_than_being_a_constant(tmp_path):
    """A band that does not move with the data has failed whatever its width.

    Two records with the same trend and different scatter, and the only thing
    that may differ in the answer is how wide it is.
    """
    quiet = _record(tmp_path / "a", _straight("2030-01-01", 90, 0.02,
                                              (0.0, 0.05, -0.05)))
    noisy = _record(tmp_path / "b", _straight("2030-01-01", 90, 0.02,
                                              (0.0, 0.60, -0.60)))
    a = quiet.weight_outlook(days=7)["horizons"][-1]
    b = noisy.weight_outlook(days=7)["horizons"][-1]
    assert a["days"] == b["days"] == 7
    assert (b["change_p90"] - b["change_p10"]) > (a["change_p90"] - a["change_p10"])


def test_the_centre_moves_with_the_horizon(tmp_path):
    """A record losing weight steadily says so more strongly at 14 days than
    at one, and an outlook whose centre stood still would be reporting the
    scatter and calling it a forecast."""
    v = _record(tmp_path, _straight("2030-01-01", 120, 0.05))
    rows = {r["days"]: r["change"] for r in v.weight_outlook(days=14)["horizons"]}
    assert rows[14] < rows[7] < rows[1] < 0


# ------------------------------------------------------------------ coverage

def test_coverage_is_the_independent_window_count_and_not_the_pair_count():
    """The two counts, and only one of them is a sample size.

    Pairs at a 14-day horizon overlap almost completely - a 90-day record
    holds dozens of them and six independent fortnights - so publishing the
    pair count alone would report an effective sample of six as one of dozens.
    Both are stated and the gate is on the smaller.
    """
    out = Vitai(DEMO).weight_outlook()
    series = _series()
    index = dict(series)
    for row in out["horizons"]:
        d = row["days"]
        starts = [when for when, _ in series
                  if (when + timedelta(days=d)) in index]
        # The same greedy tiling, written out here rather than imported, so
        # this is a second opinion and not a restatement.
        count, free_from = 0, None
        for start in sorted(starts):
            if free_from is None or start >= free_from:
                count += 1
                free_from = start + timedelta(days=d)
        assert row["windows"] == count, row
        assert row["windows"] >= 3, row
        assert row["windows"] <= row["observed"], row
        if d > 2:
            assert row["observed"] > row["windows"], row


def test_a_gap_cannot_flatter_the_coverage_count(tmp_path):
    """The reason the count is tiled rather than divided.

    Twelve readings in a fortnight and twelve more a year later span 380 days.
    `span // 7` would call that 54 independent weeks; the record speaks to a
    handful, and every pair it holds comes from inside one of the two
    clusters.
    """
    early = _straight("2030-01-01", 12, 0.02)
    late = _straight("2031-01-16", 12, 0.02)
    v = _record(tmp_path, early + late)
    out = v.weight_outlook(days=7)
    span = out["span_days"]
    assert span > 370
    for row in out["horizons"]:
        assert row["windows"] < span // row["days"], row


def test_a_horizon_the_record_cannot_support_is_absent_rather_than_narrow(tmp_path):
    """Absent, never a zero-width row. A horizon nothing was measured over has
    no width to report, and reporting one would be the fabricated precision
    this whole issue exists to refuse."""
    v = _record(tmp_path, _straight("2030-01-01", 21, 0.05))
    out = v.weight_outlook()
    stated = {r["days"] for r in out["horizons"]}
    assert stated, out
    assert max(stated) <= 20 // 3, stated
    assert 14 not in stated


def test_a_quantile_that_would_be_an_extreme_is_not_published():
    """#411 settled that observed extrema are not a coverage interval: the
    minimum of a sample can only fall as days arrive, so it says nothing about
    the next reading. A tenth percentile IS the minimum until the sample
    reaches eleven, which is where a horizon starts being stated - the
    smallest sample in which both published quantiles are interior, derived
    from the quantile definition rather than chosen."""
    for row in Vitai(DEMO).weight_outlook()["horizons"]:
        assert row["observed"] >= 11, row
        assert int(0.10 * (row["observed"] - 1)) >= 1, row
        assert int(0.90 * (row["observed"] - 1)) <= row["observed"] - 2, row


# ------------------------------------------------------------------ refusals

def test_one_reading_is_refused_rather_than_answered(tmp_path):
    v = _record(tmp_path, [("2030-01-01", 80.0)])
    out = v.weight_outlook()
    assert out["horizons"] == []
    assert out["refused"]


def test_a_protocol_seam_refuses_the_outlook(tmp_path):
    """The same refusal `weight_rate` already makes, for the same reason: two
    endpoints under different protocols are not two readings of one
    measurand, and averaging across them is not a series."""
    points = _straight("2030-01-01", 90, 0.02)
    v = init(tmp_path / "r")
    eng = Vitai(v)
    for i, (when, kg) in enumerate(points):
        eng.append("weight", {"date": when, "kg": kg,
                              "protocol": "fasted" if i < 45 else "fed"})
    out = eng.weight_outlook()
    assert out["horizons"] == []
    assert "protocol" in (out["refused"] or "")


def test_an_instrument_seam_refuses_unless_the_record_declares_comparable(tmp_path):
    """And silence does not lift it, which is the rule `weight_rate` already
    holds: a stated `offset` is a measured difference and not a licence to
    span it."""
    points = _straight("2030-01-01", 90, 0.02)
    eng = Vitai(init(tmp_path / "r"))
    for i, (when, kg) in enumerate(points):
        eng.append("weight", {"date": when, "kg": kg,
                              "origin": "scale" if i < 45 else "dexa"})
    out = eng.weight_outlook()
    assert out["horizons"] == []
    assert "instrument" in (out["refused"] or "")


def test_the_demo_answers_because_the_record_declared_the_pair_comparable():
    """The control on the two refusals above: the demo carries both a `scale`
    and a `dexa` reading of `kg` AND a `comparability` row declaring them one
    series, so it answers. Without that row this would refuse, and a refusal
    that fires on every record is indistinguishable from a broken feature."""
    out = Vitai(DEMO).weight_outlook()
    assert out["refused"] is None
    assert out["horizons"]


# --------------------------------------------------------------- what it says

def test_the_edges_are_named_as_quantiles_rather_than_as_a_coverage_interval():
    """A label is a claim (#400). `lo` and `hi` on a forward statement read as
    "the weight will be in here", which is a probability claim about the next
    reading that a handful of independent windows cannot support. `p10` and
    `p90` say what they are: where this record's own changes have fallen."""
    row = Vitai(DEMO).weight_outlook(days=7)["horizons"][0]
    assert {"change_p10", "change_p90", "kg_p10", "kg_p90"} <= set(row)
    assert not {"lo", "hi", "change_lo", "change_hi"} & set(row)


def test_the_anchor_and_the_change_agree():
    """Both spellings are published, so no client has to decide which reading
    the cone starts from - and they are held to each other here, because two
    spellings of one fact are two places for it to drift."""
    out = Vitai(DEMO).weight_outlook()
    for row in out["horizons"]:
        assert row["kg"] == pytest.approx(out["anchor_kg"] + row["change"])
        assert row["kg_p10"] == pytest.approx(out["anchor_kg"] + row["change_p10"])
        assert row["kg_p90"] == pytest.approx(out["anchor_kg"] + row["change_p90"])


def test_it_is_marked_as_derived_and_names_what_derived_it():
    """Contract 34's rule: a computed number says it was computed and by
    what, so a reader never meets it as an observation."""
    out = Vitai(DEMO).weight_outlook()
    assert out["derived_by"]
    assert out["modelled"] is False, (
        "the centre and the edges are order statistics of readings this record "
        "holds - nothing was modelled, and saying otherwise would borrow the "
        "excuse a model gets for being wrong")


# ------------------------------------------------------- the consistency gate

def test_the_one_week_band_is_wider_than_the_rate_it_refuses_to_state():
    """THE GATE THIS FEATURE HAS TO PASS TO BE ALLOWED TO EXIST.

    `weight_rate` is scored as a direction and not a number because the
    pre-registered run measured its median 95 per cent half-width at 1.74
    times the entire decision half-band. If this outlook drew a seven-day band
    narrower than that decision band, the engine would be claiming on one
    surface a resolution it had measured away on another, and one of the two
    would be wrong.

    Asserted as an INEQUALITY against the engine's own constant rather than
    against 1.74, which was measured on a different record: the finding that
    has to survive is that a week of this record's own change does not fit
    inside the band a weekly rate is judged in.
    """
    out = Vitai(DEMO).weight_outlook(days=7)
    week = [r for r in out["horizons"] if r["days"] == 7]
    assert week, out
    width = week[0]["change_p90"] - week[0]["change_p10"]
    # Against the engine's own constant rather than a copy of it, which is the
    # point of naming it: a copy would let the two surfaces drift apart
    # silently, which is the failure this test exists to prevent.
    band = 2 * RATE_DECISION_BAND
    assert width > band, (
        f"the seven-day band is {width:.2f} kg wide and the decision band "
        f"`weight_rate` is judged in is {band:.2f} kg. A band that fits "
        f"inside it would say this engine can resolve a weekly rate, which "
        f"it has a pre-registered measurement saying it cannot")


# --------------------------------------------------------------------- P9

def test_the_cli_and_the_api_answer_the_same_thing():
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "outlook",
                          "--root", DEMO, "--days", "7", "--json"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == Vitai(DEMO).weight_outlook(days=7)


# The four persona fixtures whose weight series is SMOOTHER than the band a
# weekly rate is judged in - a 7-day spread of 0.03 to 0.50 kg, which is 4 to
# 71 grams of day-to-day variation. No scale reports that and no person
# produces it: `vera` runs 59.18, 59.14, 59.14, 59.13, `hana` 71.40, 71.34,
# 71.29, 71.28. They are generated ramps with the noise left off.
#
# PINNED AS A REGISTER rather than skipped, because the list is the finding.
# Anything calibrated on these records is calibrated on a body that does not
# fluctuate, and a fixture regenerated with realistic scatter should make this
# test fail so somebody notices it got better.
SMOOTHER_THAN_THE_DECISION_BAND = {"hana", "ines", "stefan", "vera"}


def test_which_personas_carry_a_weight_series_no_scale_could_produce():
    """The conflict, measured and named rather than smoothed over.

    `weight_rate` is a direction and not a number for EVERY record, on a
    measurement taken on ONE. Over the corpus this outlook disagrees with that
    on four fixtures: their seven-day spread fits inside the band a weekly
    rate is judged in, so on those records the engine could resolve a weekly
    rate and refuses to.

    That is a fact about the fixtures rather than about the policy - a series
    stepping 40 grams a day with no scatter is a ramp, not a weigh-in series -
    and the demo, which does carry realistic scatter, sits at 1.8 times the
    decision band and corroborates the pre-registered 1.74 by a route that
    shares no arithmetic with it. But it is also the shape of a real question
    the blanket policy has never been asked, and it is written down here so it
    stays asked.
    """
    smooth = set()
    for root in sorted(PERSONAS.iterdir()):
        if not root.is_dir() or root.name == "_gen":
            continue
        week = [r for r in Vitai(root).weight_outlook(days=7)["horizons"]
                if r["days"] == 7]
        if week and (week[0]["change_p90"] - week[0]["change_p10"]
                     ) <= 2 * RATE_DECISION_BAND:
            smooth.add(root.name)
    assert smooth == SMOOTHER_THAN_THE_DECISION_BAND, (
        f"the set of personas whose weight series is smoother than a weekly "
        f"rate's decision band moved: {sorted(smooth)}. If a fixture gained "
        f"realistic scatter, take it out of the register. If one lost it, "
        f"that is a generator regression")


def test_a_record_that_qualifies_for_no_horizon_says_so():
    """Horizons are stated when and only when `refused` is None, so no client
    has to tell a seam refusal from an empty table by which key is falsy."""
    for root in sorted(PERSONAS.iterdir()):
        if not root.is_dir() or root.name == "_gen":
            continue
        out = Vitai(root).weight_outlook()
        assert bool(out["horizons"]) is (out["refused"] is None), root.name


def test_the_measurement_can_fail():
    """The control on the controls. A horizon table that came back empty for
    every record would satisfy several assertions above by vacuum."""
    assert len(Vitai(DEMO).weight_outlook()["horizons"]) >= 7
