"""Why a value is missing, not just that it is (#402).

A null said only that nothing is there. These are different facts with opposite
consequences for a reader, and the record collapsed all of them into one:

    nobody measured it            ask again, or do not
    measured and rejected         the instrument is suspect, and the day is not
                                  evidence of a body that did nothing
    asked, and they declined      a permanent answer
    asked, and they do not know   answered; asking again is pointless
    it does not apply here        not a gap at all

THE OTHER HALF OF CONTRACT 49. `false_zero` exists because a dying watch
reported `steps: 0` for a day the athlete spent moving, and a fabricated
measurement averages as though it were observed. Retiring that zero leaves a
hole; without a reason the next reader re-derives the same confusion.

THE RULE THIS FILE EXISTS TO HOLD: a reason explains a hole and never fills
one. Everything else here is plumbing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vitai.db import column_affinity  # noqa: E402
from vitai.schema import (  # noqa: E402
    ABSENT_REASONS,
    CURRENT_GENERATION,
    KEYS,
    absent_fields,
    key_generation,
    sensitivity,
    validate_record,
)

# NOT `measurements`: it requires `value`, so an absent measurement is an
# absent ROW and there is no hole for a reason to explain. Asserted below.
OBSERVATION = ("weight", "daily", "sessions")


def row(dataset="weight", **over):
    rec = {k: None for k in KEYS[dataset]}
    rec.update({"date": "2030-01-01", "source": "scale",
                "_gen": CURRENT_GENERATION[dataset]})
    if dataset == "sessions":
        rec["type"] = "run"
    rec.update(over)
    return rec


# --- the rule ------------------------------------------------------------


def test_a_reason_explains_a_hole():
    assert validate_record(
        "weight", row(absent_fields="kg", absent_reason="unable-to-obtain")) == []


def test_a_reason_may_not_sit_beside_a_value():
    """THE ONE THAT MATTERS. A row saying "no reading was obtained" while
    carrying a reading makes two claims and offers no way to choose between
    them, and the tempting resolution - prefer the value, ignore the reason -
    is silent. #398 cured the same disease one layer down, where a fabricated
    zero averaged as though it had been observed."""
    problems = validate_record(
        "weight", row(kg=75.5, absent_fields="kg", absent_reason="error"))
    assert any("never fills one" in p for p in problems), problems


def test_absence_stays_absent_across_every_observation_dataset():
    for ds in OBSERVATION:
        field = {"weight": "kg", "daily": "steps", "sessions": "avg_hr"}[ds]
        ok = row(ds, absent_fields=field, absent_reason="not-performed")
        assert validate_record(ds, ok) == [], (ds, validate_record(ds, ok))
        bad = row(ds, absent_fields=field, absent_reason="not-performed")
        bad[field] = 1 if ds != "sessions" else 120
        assert any("never fills one" in p for p in validate_record(ds, bad)), ds


# --- both fields or neither ----------------------------------------------


def test_a_reason_with_no_fields_is_refused():
    """A reason attached to the whole row cannot be checked against anything,
    which is also why this is scoped to fields at all: `daily.coverage`
    already answers the row-level question."""
    problems = validate_record("weight", row(absent_reason="error"))
    assert any("absent_fields" in p for p in problems), problems


def test_fields_with_no_reason_are_refused():
    problems = validate_record("weight", row(absent_fields="kg"))
    assert any("absent_reason" in p for p in problems), problems


def test_neither_is_the_status_quo():
    """Additive under G25: a row that says nothing about absence is exactly as
    valid as it was before this field existed."""
    assert validate_record("weight", row(kg=75.5)) == []


# --- the vocabulary ------------------------------------------------------


def test_the_vocabulary_is_closed():
    problems = validate_record(
        "weight", row(absent_fields="kg", absent_reason="no-idea"))
    assert any("absent_reason' is one of" in p for p in problems), problems


@pytest.mark.parametrize("code", sorted(ABSENT_REASONS))
def test_every_code_is_usable(code):
    assert validate_record(
        "weight", row(absent_fields="kg", absent_reason=code)) == []


def test_the_codes_dropped_from_fhir_stay_dropped():
    """Each is dropped for its own reason and none of them is "we forgot".

    `unknown` and `not-asked` say what a NULL `absent_reason` already says, and
    a code meaning the same as the absence of a code is an in-band restatement
    of it - the disease #402's own review rejected in openEHR's `accuracy = -1`.

    `unsupported` is contract 44's `competence: absent` in a second spelling,
    and two spellings of one fact drift.

    The numeric sentinels encode values a typed column cannot hold, which is
    what contract 49 cured for `steps: 0`.
    """
    for code in ("unknown", "not-asked", "unsupported", "masked",
                 "not-permitted", "not-a-number", "as-text"):
        assert code not in ABSENT_REASONS
    # And the distinction that survives the two dropped ones: being asked and
    # not knowing is the opposite of silence, and the client's gap-tapping
    # flow needs to tell them apart.
    assert "asked-unknown" in ABSENT_REASONS
    assert "asked-declined" in ABSENT_REASONS


# --- the field list ------------------------------------------------------


def test_it_can_only_name_fields_this_dataset_has():
    problems = validate_record(
        "weight", row(absent_fields="vibes", absent_reason="error"))
    assert any("not a field on this dataset" in p for p in problems), problems


def test_it_cannot_name_itself():
    for naming in ("absent_fields", "absent_reason"):
        problems = validate_record(
            "weight", row(absent_fields=naming, absent_reason="error"))
        assert any("cannot name" in p for p in problems), (naming, problems)


def test_one_reason_covers_the_fields_it_names():
    """The deliberate limit. Absence usually has ONE cause that takes several
    fields with it - a watch that stops reporting takes steps, distance and
    heart rate together - so a per-field map would carry the same reason three
    times and invite the copies to drift."""
    rec = row("daily", absent_fields="steps distance_km active_min",
              absent_reason="unable-to-obtain")
    assert validate_record("daily", rec) == []
    assert absent_fields(rec) == {"steps", "distance_km", "active_min"}


def test_it_parses_the_way_modelled_does():
    """An author writing a row by hand should not have to remember a second
    convention for a second list of field names on the same row."""
    assert absent_fields({"absent_fields": "kg, body_fat_pct"}) == {
        "kg", "body_fat_pct"}
    assert absent_fields({"absent_fields": ""}) == set()
    assert absent_fields({}) == set()


# --- plumbing ------------------------------------------------------------


@pytest.mark.parametrize("dataset", OBSERVATION)
def test_it_is_additive_under_g25(dataset):
    gen = CURRENT_GENERATION[dataset]
    assert key_generation(dataset, "absent_reason") == gen
    assert key_generation(dataset, "absent_fields") == gen
    old = {k: None for k in KEYS[dataset] if key_generation(dataset, k) == 1}
    old.update({"date": "2030-01-01", "_gen": 1})
    if dataset == "sessions":
        old["type"] = "run"
    assert validate_record(dataset, old) == [], validate_record(dataset, old)


@pytest.mark.parametrize("dataset", OBSERVATION)
def test_neither_column_is_numeric(dataset):
    """`column_affinity` is the accessor #257 published so consumers stop
    guessing, and answering REAL for a column that never holds a number is the
    lie it exists to prevent."""
    assert "absent_reason" in KEYS[dataset]
    assert column_affinity("absent_fields") == "TEXT"
    assert column_affinity("absent_reason") == "TEXT"


def test_the_reason_is_classified_as_behavioural():
    """Not `reference`, though it is a closed vocabulary. Two of its six codes
    say why the ATHLETE did not provide a value - declined, or does not know -
    which is the behavioural class's own definition, and it is the same call
    `plans.reason` gets for the same reason. The field list beside it names
    columns and says nothing about anybody."""
    for ds in OBSERVATION:
        assert sensitivity(ds, "absent_reason") == "behavioural", ds
        assert sensitivity(ds, "absent_fields") == "reference", ds


def test_measurements_is_excluded_and_the_reason_is_structural():
    """An absent measurement is an absent ROW, not a row with a hole.

    `measurements` requires `value` - "a measurement with no number is not a
    measurement" - so there is nothing for a reason to attach to. The other
    three permit a row whose values are all null, which is exactly the case
    this field explains: a day that happened, a weigh-in attempted, a session
    recorded, with something missing from it.

    Asserted rather than left as a comment, because the obvious next change is
    somebody adding the field to every observation dataset for symmetry.
    """
    assert "absent_reason" not in KEYS["measurements"]
    assert "absent_fields" not in KEYS["measurements"]
    rec = {k: None for k in KEYS["measurements"]}
    rec.update({"date": "2030-01-01", "kind": "waist_cm",
                "_gen": CURRENT_GENERATION["measurements"]})
    assert any("value" in p for p in validate_record("measurements", rec))
