"""What the engine will vouch for, beside what it will not (#185, #189).

An athlete asks "have I had enough protein today". Three things are being
asked and they are not equally answerable: protein against a target is one
logged quantity against a stated goal, and energy balance is a difference of
two inexact aggregates. Subtracting those does not average their errors, it
amplifies the relative one - two large separately-inexact numbers differencing
to a small one is the worst arithmetic available, and "400 kcal left" can
carry uncertainty larger than the figure.

The engine returned both with the same confidence and only one deserved it.

ONE FIELD WITH THE REFUSALS, which is what the merge of these two issues
settled: #177 already shipped a vocabulary for what the engine will not answer
and enforced totality in both directions, so this is the positive half of the
same question rather than a parallel table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.db import CONTRACT_VERSION, VERDICT_KEYS
from vitai.verdicts import (ANSWERS, ANSWERS_BY_METRIC, DIRECTION,
                            MAGNITUDE, _row)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def test_every_judged_row_says_what_it_is_good_for():
    """The register. A metric that ships unlabelled is one a client renders at
    whatever confidence it feels like."""
    rows = Vitai(DEMO).verdicts()
    assert rows

    unlabelled = sorted({r["metric"] for r in rows
                         if r["verdict"] != "no_data" and not r["answers"]})
    assert unlabelled == []


def test_a_row_with_no_number_vouches_for_nothing():
    """There is nothing for `answers` to describe. `reason` says why."""
    rows = [r for r in Vitai(DEMO).verdicts() if r["value"] is None]

    assert rows
    assert all(r["answers"] is None for r in rows)
    assert all(r["reason"] for r in rows)


def test_energy_availability_is_a_direction_and_not_a_number():
    """THE MOTIVATING CASE. It is (mean intake - exercise per day) / fat-free
    mass: expenditure carries 20 to over 90 per cent error in the validation
    literature, self-reported intake carries its own under-reporting, and the
    difference amplifies both rather than averaging them."""
    assert ANSWERS_BY_METRIC["energy_availability"] == DIRECTION


def test_the_rate_fails_on_measurement_rather_than_on_principle():
    """`weight_rate` is not a vendor estimate - it is two means of the same
    scale - and it still does not survive: this project's own pre-registered
    run put the median 95 per cent half-width at 1.74 times the entire
    decision half-band. Reporting it to three decimals claimed a precision
    already measured away."""
    judged = [r for r in Vitai(DEMO).verdicts()
              if r["metric"] == "weight_rate" and r["verdict"] != "no_data"]

    assert judged
    assert all(r["answers"] == DIRECTION for r in judged)


def test_the_shape_that_does_survive_keeps_its_number():
    """One logged or measured quantity against a stated policy. If everything
    became a direction the field would be a way of saying nothing."""
    by_metric = {}
    for r in Vitai(DEMO).verdicts():
        if r["verdict"] != "no_data":
            by_metric.setdefault(r["metric"], set()).add(r["answers"])

    for metric in ("protein_floor", "intake_floor", "steps", "sleep", "rhr"):
        assert by_metric[metric] == {MAGNITUDE}, metric


def test_the_same_question_answers_differently_for_two_nutrients():
    """The asymmetry the issue is about, and the reason it has to reach the
    client rather than being smoothed over: protein against a target survives
    and an energy budget does not."""
    assert ANSWERS_BY_METRIC["protein_floor"] == MAGNITUDE
    assert ANSWERS_BY_METRIC["energy_availability"] == DIRECTION


def test_a_caller_cannot_promise_a_magnitude_the_metric_cannot_carry():
    """Derived from the metric rather than passed in. A caller free to choose
    is a caller free to claim a figure for something that cannot support one,
    which is exactly the defect being fixed."""
    row = _row("2030-05-06", "energy_availability", 31.0, 30.0, "behind",
               statistic="composite-of-summaries", window_days=14)

    assert row["answers"] == DIRECTION


def test_the_vocabulary_is_closed():
    """A token nothing defines is a token a client will interpret."""
    rows = Vitai(DEMO).verdicts()

    assert ANSWERS == {MAGNITUDE, DIRECTION}
    assert all(r["answers"] in ANSWERS for r in rows if r["answers"])


def test_a_refusal_that_keeps_its_number_still_vouches_for_nothing():
    """The correction that mattered, and I had it backwards twice.

    A labelled refusal KEEPS its value - suppression is a label and never a
    deletion, and a rate whose weigh-in drift accounts for it is still a
    computed figure. My first cut keyed `answers` on the VALUE, so those rows
    came back `direction`: the engine vouching for ahead-or-behind on exactly
    the rows where it had just said the measurement cannot support a verdict.
    #185's own table is explicit - a refusal gets the reason and no number.
    """
    rows = Vitai(DEMO).verdicts()
    kept = [r for r in rows if r["verdict"] == "no_data"
            and r["value"] is not None]

    assert kept, "the demo must hold a labelled refusal that kept its value"
    for r in rows:
        assert (r["answers"] is not None) != (r["reason"] is not None), r
    # And the refusal that KEPT its number vouches for nothing anyway: not
    # even the sign is supported when weigh-in drift accounts for the rate.
    assert all(r["answers"] is None for r in kept)


def test_the_column_reaches_the_read_model(tmp_path):
    """A field written nowhere cannot be read by the consumer it exists for."""
    import shutil

    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    Vitai(root).build()

    con = sqlite3.connect(root / "derived" / "health.db")
    rows = con.execute("SELECT metric, answers FROM verdicts "
                       "WHERE verdict != 'no_data'").fetchall()
    affinity = {r[1]: r[2] for r in con.execute(
        "PRAGMA table_info(verdicts)").fetchall()}
    contract, = con.execute(
        "SELECT value FROM meta WHERE key='contract'").fetchone()
    con.close()

    assert rows and all(r[1] for r in rows)
    assert affinity["answers"] == "TEXT", (
        "a slug column with REAL affinity makes `column_affinity` lie")
    assert "answers" in VERDICT_KEYS
    assert contract == CONTRACT_VERSION


def test_a_positional_reader_keeps_every_column_it_knew():
    """Appended, like `reason`, `due`, `statistic` and `window_days` before
    it."""
    original = ["week", "metric", "value", "target", "verdict", "goal"]

    assert VERDICT_KEYS[:len(original)] == original
    # By prefix, not by index from the end: `[-1]` was a snapshot that broke
    # the moment the next column was appended, and it taught a consumer that a
    # positional read of the last column is stable, which is the opposite of
    # what this test is for.
    assert "answers" in VERDICT_KEYS[len(original):]


def test_the_deferred_half_shipped_beside_this_field_rather_than_inside_it():
    """`provisional` was reserved as the third value of `answers` - a day still
    open, so the number is "so far" rather than final - and the completeness
    work (#186) has now landed it as its own column instead.

    THEY ANSWER DIFFERENT QUESTIONS, which is why. `answers` says what
    RESOLUTION the engine will vouch for, and a provisional magnitude is still
    a magnitude: a number to render, marked not-final. As a third value it
    would make a consumer choose between knowing the figure is provisional and
    knowing it is a figure.
    """
    from vitai.db import VERDICT_KEYS as _KEYS

    assert "provisional" not in ANSWERS
    assert "provisional" in _KEYS

    # An earlier version put a `pytest.raises` here that fired on #177's
    # judgement-carries-no-reason guard - a rule that predates this change
    # and has nothing to do with day completeness. It would have passed on
    # the parent commit, which is the definition of proving nothing.
    assert ANSWERS == set(ANSWERS_BY_METRIC.values())


def test_a_new_metric_cannot_default_into_the_stronger_claim():
    """CLOSED WORLD, like `statistic` beside it.

    The first cut defaulted anything unlisted to `magnitude`, so a new metric
    would silently ship promising the number - which is the failure this field
    exists to fix, arriving through the door marked convenience. Flipping four
    of the assignments passed all 1601 tests, because only the uncontested
    ones were pinned.
    """
    with pytest.raises(ValueError) as raised:
        _row("2030-05-06", "invented", 42.0, 10.0, "behind",
             statistic="average", window_days=7)

    assert "what it is good for" in str(raised.value)


def test_every_metric_the_engine_emits_has_a_decision():
    """The register. A metric missing here raises at the row, so this is a
    check that the demo exercises the whole table rather than a restatement
    of it."""
    emitted = {r["metric"] for r in Vitai(DEMO).verdicts()}

    assert emitted <= set(ANSWERS_BY_METRIC), emitted - set(ANSWERS_BY_METRIC)


def test_the_contested_assignments_are_pinned_not_defaulted():
    """Each of these four was a judgement call against a cited source, and
    none of them was covered while `magnitude` was the default."""
    assert ANSWERS_BY_METRIC["easy_hr"] == DIRECTION
    assert ANSWERS_BY_METRIC["pain_gate"] == DIRECTION
    assert ANSWERS_BY_METRIC["weight_rate"] == DIRECTION
    assert ANSWERS_BY_METRIC["energy_availability"] == DIRECTION
    assert ANSWERS_BY_METRIC["symptom_chest_pain"] == MAGNITUDE
