"""Row identity: the primitive #168, #169 and #170 all need.

Three issues converging on one missing thing is usually the sign that the
missing thing is one piece rather than three. A qualification has to name the
observation it qualifies, a relayed reading has to name which reading it was,
and a derived value has to name the rows it came from. None of them can be
built on a reference that points at more than one row.
"""

import json

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.identity import (ambiguous, identifiable, refs, row_ref,
                            unidentifiable_datasets)


def test_it_uses_the_identity_the_schema_already_declares():
    """`IDENTITY_KEY` says a set is (session_start, exercise, block, round,
    set_index). Date and source cannot tell two sets of one session apart, and
    measured on the demo corpus that collided on 8 of 11 rows."""
    a = {"session_start": "2030-05-26T10:30:00+02:00", "exercise": "push-up",
         "block": None, "round": 1, "set_index": 1, "date": "2030-05-26",
         "source": "athlete"}
    b = dict(a, set_index=2)
    assert row_ref("sets", a) != row_ref("sets", b)
    assert identifiable("sets")


def test_it_is_derived_from_content_and_not_from_position():
    """Stable across rebuilds is the whole requirement. A reference computed
    from where a row sits would move whenever a file was regenerated, and #37
    established that an ordering a formatter can change is not an ordering."""
    row = {"date": "2030-05-01", "kg": 80.0, "source": "scale"}
    assert row_ref("weight", row) == row_ref("weight", dict(row))
    assert row_ref("weight", row) == "weight:2030-05-01:scale"


def test_a_missing_source_does_not_collapse_two_rows_into_one():
    """`unknown` is a value, not a hole. Two rows with nothing said about
    their source are still two rows."""
    rows = [{"date": "2030-05-01", "kg": 80.0, "source": None},
            {"date": "2030-05-01", "kg": 80.4, "source": None}]
    assert len(set(refs("weight", rows))) == 2


def test_repeats_are_disambiguated_by_ordinal():
    rows = [{"date": "2030-05-01", "kg": 80.0, "source": "scale"},
            {"date": "2030-05-01", "kg": 80.4, "source": "scale"}]
    got = refs("weight", rows)
    assert len(set(got)) == 2
    assert got[0] == "weight:2030-05-01:scale"


def test_the_ordinal_is_reported_as_an_ambiguity_rather_than_hidden():
    """The honest weakness, named here rather than discovered later. Two
    readings from one scale on one morning are distinguishable only by their
    order in the file, and file order is not a property the record
    guarantees - #164 found a correction silently failing for exactly that.
    A caller targeting one of these is targeting a position.
    """
    rows = [{"date": "2030-05-01", "kg": 80.0, "source": "scale"},
            {"date": "2030-05-01", "kg": 80.4, "source": "scale"}]
    found = ambiguous("weight", rows)
    assert found == [{"ref": "weight:2030-05-01:scale", "rows": 2}]


def test_an_unambiguous_dataset_reports_nothing():
    rows = [{"date": "2030-05-01", "kg": 80.0, "source": "scale"},
            {"date": "2030-05-02", "kg": 80.4, "source": "scale"}]
    assert ambiguous("weight", rows) == []


def test_the_gap_is_countable_rather_than_argued_about():
    """Which datasets can repeat under one reference. This is the list
    #169's `client_record_id` would shorten, and stating it means the
    remaining work is a number rather than an opinion."""
    gap = unidentifiable_datasets()
    assert "weight" in gap and "sessions" in gap
    assert "sets" not in gap and "goals" not in gap


def test_every_row_of_the_demo_corpus_is_nameable(tmp_path):
    """The measurement that motivated this, as a test. `claim_id` gave 3
    distinct references for 11 `sets` rows and 1 for 5 `meals`."""
    from pathlib import Path
    engine = Vitai(Path(__file__).resolve().parents[1] / "examples" / "demo")
    for dataset in ("weight", "daily", "sessions", "measurements", "sets",
                    "meals"):
        rows = engine.dataset(dataset)
        if not rows:
            continue
        assert len(set(refs(dataset, rows))) == len(rows), dataset


def test_a_reference_survives_a_rebuild(tmp_path):
    """Stability is the property everything else rests on: a qualification
    written today must still point at the same reading next year."""
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2026-05-{d:02d}", "kg": 80.0 + d, "source": "scale",
         "note": None, "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "measured_at": None})
        for d in range(1, 5)) + "\n", encoding="utf-8")
    before = refs("weight", Vitai(root).dataset("weight"))
    Vitai(root).build()
    after = refs("weight", Vitai(root).dataset("weight"))
    assert before == after


def test_a_colon_in_a_value_cannot_forge_another_rows_reference():
    """References are joined with colons, so a value containing one could
    otherwise be made to spell a different row's name."""
    honest = {"date": "2030-05-01", "kg": 80.0, "source": "scale"}
    sneaky = {"date": "2030-05-01", "kg": 80.0, "source": "scale:x"}
    assert row_ref("weight", honest) != row_ref("weight", sneaky)


def test_it_refuses_nothing_and_computes_nothing():
    """A reference is a name. It reads no config, runs no resolution and has
    no opinion about which row is better."""
    import inspect

    from vitai import identity
    source = inspect.getsource(identity)
    for forbidden in ("resolve(", "precedence", "verdict", "config"):
        assert forbidden not in source, forbidden
