"""A correction is compared against the line it retires (#342).

`field_sources` (contract 40) and `field_origins` (contract 42) say which feed
and which instrument supplied each field of a MERGED row, and #340 reads them
forward. What was missing is the write-time check: a correction was compared
against nothing, so a line retiring an earlier one could disagree with it about
which instrument observed a value, and both survived.

The shape #325 narrates: a hand-merged console row supersedes a watch's line,
keeps its heart rate and energy figures, and stamps the console's `origin` on
them. Both lines are well-formed, the merge works as designed, and the record
ends up asserting that a rowing console observed a heart rate.

REPORTED, NOT REFUSED, as decided. A correction that changes a field's origin
is either the athlete fixing an attribution or two instruments being laundered
into one, and nothing in the record distinguishes them. Refusing would block
the legitimate case and the escape hatch would have to be invented in the same
change; the engine says what it sees and declines the inference, which is what
`explanations` does for a contest and what the seam work does for a rate.
"""

from __future__ import annotations

from pathlib import Path

from vitai.schema import KEYS, supersedes_problems

PERSONAS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "personas"


def session(**kw) -> dict:
    return {**{k: None for k in KEYS["sessions"]}, "date": "2030-05-01",
            "type": "row", "duration_s": 1800, **kw}


def advisories(rows: list[dict]) -> list[str]:
    return [p for p in supersedes_problems("sessions", list(enumerate(rows, 1)))
            if "different instrument" in p]


# --- the case the issue narrates ------------------------------------------------

def test_a_correction_carrying_values_under_a_new_instrument_is_reported():
    watch = session(source="polar", origin="polar-watch",
                    avg_hr=142, max_hr=168, kcal=310)
    merged = session(source="matrix-console", origin="matrix-rower",
                     avg_hr=142, max_hr=168, kcal=310, distance_km=8.1,
                     supersedes="2030-05-01/polar")
    got = advisories([watch, merged])
    assert len(got) == 1, got
    for field in ("avg_hr", "max_hr", "kcal"):
        assert field in got[0], (field, got[0])
    assert "'polar-watch' -> 'matrix-rower'" in got[0]


def test_it_says_what_to_do_instead():
    """The advice has to be takeable. Writing the carried values as their own
    line is what the engine already merges correctly."""
    watch = session(source="polar", origin="polar-watch", avg_hr=142)
    merged = session(source="matrix-console", origin="matrix-rower",
                     avg_hr=142, supersedes="2030-05-01/polar")
    assert "their own line" in advisories([watch, merged])[0]


def test_it_does_not_decide_which_origin_is_right():
    """Out of scope by the issue's own terms: the engine does not have that
    information and inventing a tiebreak is the failure this prevents."""
    watch = session(source="polar", origin="polar-watch", avg_hr=142)
    merged = session(source="matrix-console", origin="matrix-rower",
                     avg_hr=142, supersedes="2030-05-01/polar")
    got = advisories([watch, merged])[0]
    assert "cannot tell them apart" in got
    assert "reported rather than decided" in got


# --- and what it stays quiet about ---------------------------------------------

def test_a_correction_that_agrees_is_silent():
    watch = session(source="polar", origin="polar-watch", avg_hr=142)
    fixed = session(source="polar", origin="polar-watch", avg_hr=145,
                    supersedes="2030-05-01/polar")
    assert advisories([watch, fixed]) == []


def test_a_value_that_CHANGED_is_a_correction_of_the_value():
    """A changed figure says nothing about attribution - it is the ordinary
    case this path exists for. Only a value carried forward UNCHANGED under a
    new instrument has no innocent reading available to the engine.

    PER FIELD, which is what the issue asks for and what the first version of
    this test got wrong: it left `duration_s` identical in both rows and
    expected silence. The advisory was right and the test was not - a duration
    carried forward under a new instrument is exactly a field whose origin
    changed while its value did not. Every measurement differs here."""
    watch = session(source="polar", origin="polar-watch", avg_hr=142, kcal=310)
    console = session(source="matrix-console", origin="matrix-rower",
                      avg_hr=151, kcal=288, duration_s=1830,
                      supersedes="2030-05-01/polar")
    assert advisories([watch, console]) == []


def test_one_field_carried_forward_is_enough_to_report():
    """The corollary. A correction that fixes three figures and carries a
    fourth is still asserting a new instrument for that fourth."""
    watch = session(source="polar", origin="polar-watch", avg_hr=142, kcal=310)
    console = session(source="matrix-console", origin="matrix-rower",
                      avg_hr=151, kcal=310, duration_s=1830,
                      supersedes="2030-05-01/polar")
    got = advisories([watch, console])
    assert len(got) == 1 and "kcal" in got[0], got
    assert "avg_hr" not in got[0], "the changed one is not carried forward"


def test_silence_about_an_instrument_is_not_a_disagreement():
    """The rule `instrument_seam` and `is_independent` already keep: a row
    naming no instrument is not making a competing claim."""
    bare = session(source="polar", avg_hr=142)
    named = session(source="matrix-console", origin="matrix-rower",
                    avg_hr=142, supersedes="2030-05-01/polar")
    assert advisories([bare, named]) == []
    assert advisories([named, bare]) == []


def test_only_measurements_count():
    """The cut is the engine's own classification (#299) rather than a list
    written here: an instrument OBSERVES a measurement, not a date, a slug or
    a note. `type` is a reference and is carried forward by every correction."""
    watch = session(source="polar", origin="polar-watch", avg_hr=142,
                    note="same note")
    merged = session(source="matrix-console", origin="matrix-rower",
                     avg_hr=142, note="same note",
                     supersedes="2030-05-01/polar")
    got = advisories([watch, merged])[0]
    assert "avg_hr" in got
    assert "duration_s" in got, "a measurement, and legitimately reported"
    for field in ("type", "note", "date"):
        assert field not in got, (field, got)


def test_an_ambiguous_reference_is_left_to_the_advisory_that_owns_it():
    """Where a reference matches several lines the engine already says it
    picked one and may have picked wrong. Comparing against a row the author
    did not mean would be a second guess on top of a first."""
    a = session(source="polar", origin="polar-watch", avg_hr=142, activity_id="A")
    b = session(source="polar", origin="polar-watch", avg_hr=142, activity_id="A")
    merged = session(source="matrix-console", origin="matrix-rower",
                     avg_hr=142, activity_id="A",
                     supersedes="A@2030-05-01")
    got = supersedes_problems("sessions", list(enumerate([a, b, merged], 1)))
    assert any("matches 2 lines" in p for p in got), got
    assert not [p for p in got if "different instrument" in p]


def test_the_corpus_raises_none():
    """No shipped record launders an instrument through a correction, so this
    ships with every persona silent - checked rather than assumed."""
    from vitai.api import Vitai

    for path in sorted(PERSONAS.iterdir()):
        if not (path / "vitai.toml").exists():
            continue
        report = Vitai(path).load_report()
        hits = [a for a in report.get("advisories", [])
                if "different instrument" in a]
        assert not hits, (path.name, hits)
