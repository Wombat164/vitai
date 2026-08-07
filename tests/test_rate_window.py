"""A rate measured over a window the record actually covers (#142).

Every logged weight delta in one persona is negative and the regain is
entirely inside the unlogged gaps. No individual row is wrong: each is a real
reading, honestly recorded, passing every check the engine has. The bias is a
property of WHICH days got logged, and it is invisible at row level by
construction.

The first sub-gap that files under - "no rule against trending across a hole"
- turned out to be sharper than filed. THE NUMERATOR AND THE DENOMINATOR
MEASURED DIFFERENT SPANS. `status()` compares the mean of the last seven
weigh-ins against the mean of the seven before them, and divided by the days
between the eighth-from-last weigh-in and the last. Where weigh-ins are dense
those are near enough the same window; where they are not, they are unrelated.

WHAT THIS DOES NOT DO, because the project has already decided it. `weight_rate`
answers `direction` rather than a magnitude, and `verdicts.py` records why: the
pre-registered run measured a median `u_rate / half-band` of 1.74, and its own
conclusion was that the decision unit is wrong and a REFUSAL PREDICATE ships
with the uncertainty work rather than as a threshold picked in passing. So
nothing here decides whether a rate over a span containing a hole is usable.
It fixes the arithmetic, and it publishes the two facts a consumer - or that
predicate, later - needs to decide: how far the figure reaches, and how much of
that reach nobody observed.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from vitai.api import Vitai, init

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
YASMIN = ROOT / "tests" / "fixtures" / "personas" / "yasmin"


def _clusters(tmp_path: Path, first_kg: float, second_kg: float,
              apart_days: int = 424) -> Vitai:
    """Eight flat readings, a silence, eight more. Nothing inside either
    cluster ever changes, so no rate was ever observed."""
    v = Vitai(init(tmp_path / "content"))
    start = date(2029, 1, 1)
    for n in range(8):
        v.append("weight", {"date": (start + timedelta(days=n)).isoformat(),
                            "kg": first_kg, "source": "scale"})
    for n in range(8):
        when = start + timedelta(days=apart_days + n)
        v.append("weight", {"date": when.isoformat(), "kg": second_kg,
                            "source": "scale"})
    return v


def test_the_rate_is_not_a_figure_nobody_could_have_lost(tmp_path):
    """THE REPORTED DEFECT. Every reading inside each cluster is flat, so
    nothing was ever observed changing at any rate - and the engine reported
    losing 3.43 kg/week, because the numerator straddled 425 days while the
    denominator counted 7."""
    st = _clusters(tmp_path, 92.0, 88.0).status(date(2030, 3, 8))

    assert st["rate_kg_per_week"] < 0.2, st["rate_kg_per_week"]


def test_four_kilos_over_fourteen_months_is_the_rate_that_says(tmp_path):
    """And the figure it does give is the honest one: 4 kg across the span the
    two blocks are actually separated by."""
    st = _clusters(tmp_path, 92.0, 88.0).status(date(2030, 3, 8))

    assert round(st["rate_kg_per_week"], 2) == 0.07
    assert st["rate_span_days"] > 400


def test_the_denominator_measures_what_the_numerator_compares(tmp_path):
    """Two block means are separated by the distance between their CENTRES.
    Dividing by the distance between two single points is a different span,
    and the two diverge exactly where the weigh-ins are sparse."""
    v = _clusters(tmp_path, 90.0, 90.0)

    st = v.status(date(2030, 3, 8))

    # Nothing changed between the blocks, so the rate is zero whatever the
    # denominator is - what this pins is that the span is the blocks' own.
    assert st["rate_kg_per_week"] == 0.0
    assert st["rate_span_days"] > 400


def test_the_rate_carries_its_own_span(tmp_path):
    """`mean_kg_span_days` was added (#209) so a consumer could stop
    mislabelling the MEAN's window. The rate then had no span published at
    all, so a figure reaching over 221 days was rendered against a label
    saying 114."""
    st = _clusters(tmp_path, 92.0, 88.0).status(date(2030, 3, 8))

    assert st["mean_kg_span_days"] == 6
    assert st["rate_span_days"] != st["mean_kg_span_days"]


def test_it_says_how_much_of_that_span_nobody_observed(tmp_path):
    """A FACT, NOT A VERDICT. The engine does not decide whether a hole makes
    the figure unusable - that is the refusal predicate the uncertainty work
    owns. It says how much of the reach it never saw and leaves the decision
    where it can be made."""
    st = _clusters(tmp_path, 92.0, 88.0).status(date(2030, 3, 8))

    assert st["rate_unobserved_days"] > 400
    assert st["rate_unobserved_days"] < st["rate_span_days"]


def test_it_still_reports_the_rate_rather_than_refusing(tmp_path):
    """DELIBERATE, and the opposite of what a reader might expect from the
    issue. `weight_rate` already answers `direction` rather than a magnitude,
    and this project's own measurement concluded that the refusal predicate
    ships with the uncertainty work rather than as a threshold chosen here.
    Removing the figure would also leave a client unable to compute anything,
    which is the split #185 recorded: prose honours the contract, data carries
    it."""
    st = _clusters(tmp_path, 92.0, 88.0).status(date(2030, 3, 8))

    assert st["rate_kg_per_week"] is not None
    assert st["direction"] in ("losing", "gaining", "holding")


def test_a_dense_record_is_barely_changed(tmp_path):
    """The property that makes this a repair rather than a rewrite: where the
    weigh-ins are dense, the old span and the new one are near enough the same
    and the figure barely moves."""
    v = Vitai(init(tmp_path / "content"))
    for n in range(16):
        v.append("weight", {"date": (date(2030, 5, 1) + timedelta(days=n)).isoformat(),
                            "kg": 90.0 - n * 0.1, "source": "scale"})

    st = v.status(date(2030, 5, 16))

    assert round(st["rate_kg_per_week"], 2) == 0.7
    assert st["rate_unobserved_days"] == 1
    assert abs(st["rate_span_days"] - st["mean_kg_span_days"]) <= 8


def test_the_shipped_corpus_carries_the_case(tmp_path):
    """#204's corollary, and the persona that found it. yasmin's record has
    holes measured in hundreds of days, so a fixture that only held dense
    records would exercise the case where the defect does not appear."""
    st = Vitai(YASMIN).status()

    assert st["rate_span_days"] > 200
    assert st["rate_unobserved_days"] > 0
    assert st["rate_span_days"] != st["mean_kg_span_days"]


def test_a_record_too_short_to_have_a_rate_says_so(tmp_path):
    """Both new fields are None rather than zero where there is no rate: a
    span of zero and no span at all are different facts, and a consumer
    reading zero would render a window."""
    v = Vitai(init(tmp_path / "content"))
    v.append("weight", {"date": "2030-05-01", "kg": 90.0, "source": "scale"})

    st = v.status(date(2030, 5, 1))

    assert st["rate_kg_per_week"] is None
    assert st["rate_span_days"] is None
    assert st["rate_unobserved_days"] is None


def test_the_demo_publishes_both_beside_the_rate():
    """The shape a consumer reads. If the figure ships without them the
    consumer is back to inferring the window, which is what #209 was for."""
    st = Vitai(DEMO).status("2030-06-30")

    assert st["rate_kg_per_week"] is not None
    assert isinstance(st["rate_span_days"], int)
    assert isinstance(st["rate_unobserved_days"], int)
