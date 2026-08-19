"""Can the measurement behind `weight_rate`'s refusal be checked at all? (#460)

`verdicts.ANSWERS_BY_METRIC` scores `weight_rate` as a DIRECTION for EVERY
record. The evidence is a pre-registered run on ONE: median `u_rate / half-band`
of 1.74, more than half of scored weeks admitting no verdict word, twelve
verdict flips. That judgement is load-bearing three ways over - it is why a
client may not print a rate, why #457 publishes p10 and p90 rather than a
forecast, and why #458 was decided against.

THE COUNTING SCRIPT WAS NEVER IN THIS REPOSITORY. `docs/proposals/uncertainty/
00-phase0-experiment.md` says so in as many words: "a ~60-line script in the
private record's tooling directory (never in the public repo)". So the number
has never been reproducible here, and nothing could tell whether it holds on a
second record.

This file holds the reproduction to the spec, and the corpus census to what it
finds. THE CONTROL AT THE BOTTOM IS THE LOAD-BEARING ONE: a record built with a
known within-week dispersion has to come back with the ratio that dispersion
implies, or the census above is a column of numbers nobody has checked.
"""

from __future__ import annotations

import json
import statistics as st
import subprocess
import sys
from datetime import date, timedelta
from math import sqrt
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.rate_uncertainty import REPLICATES
from vitai.verdicts import RATE_DECISION_BAND

DEMO = "examples/demo"
PERSONAS = Path(__file__).parent / "fixtures" / "personas"

# What the four measurable records come back with. Median `u_rate / half-band`,
# to two places.
#
# PINNED IN BOTH DIRECTIONS. A record joining `MEASURABLE` means a fixture
# started weighing three times in some week, which is news; one leaving means
# it stopped. And the ratios themselves are the answer to #460 - if they move,
# the thing this issue asks about has moved.
MEASURABLE = {"examples/demo": 0.68, "nora": 0.75, "sofia": 0.71, "tom": 2.55}

# Records where a phase target exists as well, so the refusal predicate can be
# evaluated: `nora` states none, so its weeks are measurable and not judgeable.
JUDGED = {"examples/demo", "sofia", "tom"}

PRE_REGISTERED = 1.74


def _roots():
    yield DEMO, Path(DEMO)
    for root in sorted(PERSONAS.iterdir()):
        if root.is_dir() and root.name != "_gen":
            yield root.name, root


def _weekly(tmp_path, weeks: int, sd_pattern, per_week: int = 3,
            start: float = 80.0, drop: float = 0.4):
    """A record weighed `per_week` times a week with a known dispersion."""
    v = Vitai(init(tmp_path / "r"))
    first = date.fromisoformat("2030-01-07")          # a Monday
    for w in range(weeks):
        for i in range(per_week):
            when = first + timedelta(days=w * 7 + i)
            v.append("weight", {"date": when.isoformat(),
                                "kg": round(start - w * drop
                                            + sd_pattern[i % len(sd_pattern)],
                                            3)})
    return v


# ------------------------------------------------------------------ the defect

def test_nothing_here_can_check_the_measurement_the_policy_rests_on():
    """The gap, asserted rather than described. The script that produced 1.74
    was in a private tooling directory by design, so no second record has ever
    been asked the same question."""
    assert hasattr(Vitai, "rate_uncertainty"), (
        "no engine surface reproduces the phase-0 weight_rate uncertainty "
        "measurement, so the judgement that every record's rate is a "
        "direction rests on a run nobody else can repeat")


# ------------------------------------------------------------- the estimator

def test_it_follows_the_pre_registered_estimator(tmp_path):
    """Re-derived here from the spec rather than from the module under test.

    `u_wk = SD_within_week / sqrt(n)` for a week of three or more readings;
    `u_rate = sqrt(u_prev^2 + u_cur^2)`; the ratio is against the half-band
    `verdicts.RATE_DECISION_BAND`, which is the same constant the verdict uses.
    """
    v = _weekly(tmp_path, weeks=6, sd_pattern=(-0.3, 0.0, 0.3))
    out = v.rate_uncertainty()
    u_wk = st.stdev([-0.3, 0.0, 0.3]) / sqrt(3)
    expected = sqrt(2 * u_wk ** 2) / RATE_DECISION_BAND
    assert out["median_ratio"] == pytest.approx(expected, abs=0.01)
    assert out["half_band"] == RATE_DECISION_BAND


def test_a_wider_weigh_in_scatter_gives_a_wider_ratio(tmp_path):
    """A ratio that did not move with the dispersion would be reporting a
    constant. It is the whole quantity."""
    tight = _weekly(tmp_path / "a", 6, (-0.05, 0.0, 0.05)).rate_uncertainty()
    loose = _weekly(tmp_path / "b", 6, (-0.6, 0.0, 0.6)).rate_uncertainty()
    assert loose["median_ratio"] > 5 * tight["median_ratio"]


def test_the_expanded_ratio_is_the_standard_one_times_the_coverage_factor():
    """Both are published because the repository's own prose disagrees about
    which one 1.74 is - see the docstring of `rate_uncertainty`."""
    out = Vitai(DEMO).rate_uncertainty()
    assert out["median_expanded_ratio"] == pytest.approx(
        out["median_ratio"] * out["coverage_factor"], abs=0.01)


# --------------------------------------------------------------- what it needs

def test_a_record_that_never_weighs_three_times_in_a_week_cannot_be_asked(tmp_path):
    """The binding constraint, and it is not a small one. The Type A estimator
    needs replicates, and a person who weighs once or twice a week supplies
    none - so the pooled fallback has nothing to pool either."""
    v = _weekly(tmp_path, weeks=8, sd_pattern=(0.0, 0.2), per_week=2)
    out = v.rate_uncertainty()
    assert out["median_ratio"] is None
    assert out["pooled_sd"] is None
    assert f"{REPLICATES} weigh-ins" in out["refused"]


def test_two_weigh_ins_a_week_still_work_once_some_week_has_three(tmp_path):
    """The pooled fallback the spec defines: `pooled_sd / sqrt(n)` where the
    week itself is too thin, pooled over every week that is not."""
    v = _weekly(tmp_path, weeks=6, sd_pattern=(-0.3, 0.0, 0.3))
    v.append("weight", {"date": "2030-02-25", "kg": 77.0})
    v.append("weight", {"date": "2030-02-26", "kg": 77.2})
    out = v.rate_uncertainty()
    assert out["pooled_sd"] is not None
    assert out["measurable"] >= 5


# ------------------------------------------------------------------ the corpus

def test_which_records_can_answer_the_question_at_all():
    """#460's first answer, and the uncomfortable one: twelve of sixteen
    cannot. No week in any of them holds three weigh-ins, so the estimator the
    whole policy rests on returns nothing for every week of every one."""
    measurable = {}
    for name, root in _roots():
        out = Vitai(root).rate_uncertainty()
        if out["median_ratio"] is not None:
            measurable[name] = round(out["median_ratio"], 2)
    assert measurable == MEASURABLE, measurable


def test_the_pre_registered_number_does_not_reproduce():
    """#460's second answer. 1.74 was measured on one record. On the four that
    can be asked here it is 0.68, 0.75, 0.71 and 2.55 - three of them at
    roughly two fifths of it and one at half again as much. Whatever else is
    true, the VALUE is a property of that record rather than of the metric."""
    ratios = sorted(MEASURABLE.values())
    assert not any(abs(r - PRE_REGISTERED) < 0.5 for r in ratios), ratios
    assert max(ratios) / min(ratios) > 3


def test_the_decision_reproduces_even_though_the_number_does_not():
    """#460's third answer, and the one that settles it.

    The refusal does not turn on 1.74. It turns on whether the interval
    crosses a band edge, which happens once the expanded half-width exceeds
    the half-band - a ratio above 1/1.96, or about 0.51. The lowest measured
    here is 0.68, a third above that line, so every record that can be judged
    refuses on most of its weeks.
    """
    for name in sorted(JUDGED):
        root = DEMO if name == DEMO else PERSONAS / name
        out = Vitai(root).rate_uncertainty()
        assert out["median_ratio"] > 1 / out["coverage_factor"], (name, out)
        assert out["refusal_rate"] > 0.60, (name, out)


def test_the_records_that_cannot_be_asked_include_every_ramp():
    """And that is luck rather than design, which is worth saying.

    #463 pinned four persona weight series flatter than the engine's own
    declared floor. A ramp has almost no within-week dispersion, so had any of
    them weighed three times in a week the estimator would have returned a
    ratio near zero and reported that a weekly rate is precisely resolvable.
    None of them does, so none of them is in the census - but the corpus's
    ability to answer this question is limited by the same defect (#462).
    """
    for name in ("hana", "ines", "stefan", "vera"):
        assert name not in MEASURABLE
        assert Vitai(PERSONAS / name).rate_uncertainty()["refused"]


# ---------------------------------------------------------------- the control

def test_a_record_built_with_a_known_dispersion_comes_back_with_it(tmp_path):
    """THE CONTROL ON THE CENSUS. Every number above is a column nobody has
    checked unless this passes: a record whose weekly scatter is constructed
    has to produce the ratio that scatter implies, at two different widths.
    """
    for pattern, in ((( -0.2, 0.0, 0.2),), ((-0.5, 0.0, 0.5),)):
        v = _weekly(tmp_path / f"w{pattern[1]}{pattern[2]}", 8, pattern)
        u_wk = st.stdev(pattern) / sqrt(3)
        want = sqrt(2 * u_wk ** 2) / RATE_DECISION_BAND
        assert v.rate_uncertainty()["median_ratio"] == pytest.approx(
            want, abs=0.01), pattern


def test_a_refusal_is_reachable_and_a_non_refusal_is_too(tmp_path):
    """A refusal rate of 100 per cent everywhere would satisfy the census and
    measure nothing. A record weighed precisely enough must not refuse."""
    v = _weekly(tmp_path, weeks=8, sd_pattern=(-0.01, 0.0, 0.01))
    out = v.rate_uncertainty()
    assert out["median_ratio"] < 1 / out["coverage_factor"]


# --------------------------------------------------------------------- P9

def test_the_cli_and_the_api_answer_the_same_thing():
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "rate-uncertainty",
                          "--root", DEMO, "--json"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == Vitai(DEMO).rate_uncertainty()
