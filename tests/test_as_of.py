"""The knowledge cutoff: what the record said THEN, not what it says now.

Synthetic data only (public repo). Dates are in 2030 for the same reason the
rest of the suite uses them.

`clocks.py` promised this in its own docstring - telling "what the record said
on 30 July, as we understood it then" apart from "as we understand it now" -
and the record was bitemporal in storage while every evaluation path was
unitemporal. `recorded_at` was stamped rigorously and used only as an ordering
tie-break; nothing ever filtered on it.

The case that motivates it: a month of degraded data whose cause is filed six
weeks later. Under a cutoff inside those six weeks it reads unexplained, and
after it reads explained. Judging a decision and judging it with hindsight are
different questions, and an engine that cannot tell them apart will be trained
toward confident attribution by its own test suite.
"""
from datetime import datetime, timedelta, timezone

import pytest

from vitai.api import Vitai
from vitai.jsonl import known_by, load

UTC = timezone.utc


def at(day, hour=12):
    return datetime(2030, 4, day, hour, tzinfo=UTC)


def stamp(day, hour=12):
    return at(day, hour).isoformat()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "data").mkdir()

    def write(name, rows):
        import json
        (tmp_path / "data" / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path, write


# --- the primitive ----------------------------------------------------------

def test_an_unstamped_line_survives_every_cutoff():
    """Absent sorts before present, per the clocks canon. A legacy line has no
    transaction time because it predates the clock, not because it came later,
    and dropping it would empty a legacy corpus rather than reconstruct one."""
    assert known_by({"date": "2030-04-01"}, at(1)) is True


def test_a_line_written_after_the_cutoff_is_not_known():
    assert known_by({"recorded_at": stamp(20)}, at(10)) is False
    assert known_by({"recorded_at": stamp(5)}, at(10)) is True


def test_the_cutoff_is_inclusive_of_its_own_instant():
    assert known_by({"recorded_at": stamp(10)}, at(10)) is True


def test_offsets_compare_as_instants_not_as_text():
    """`+02:00` sorts after `+00:00` as a string no matter which came first."""
    later_wall_earlier_instant = {
        "recorded_at": datetime(2030, 4, 10, 13,
                                tzinfo=timezone(timedelta(hours=2))).isoformat()}
    assert known_by(later_wall_earlier_instant, at(10, 12)) is True


# --- the ordering that is the correctness argument --------------------------

def test_a_correction_written_after_the_cutoff_does_not_retire_its_target(repo):
    """THE reason the filter runs before the supersedes walk. Applying a future
    retraction to a past reconstruction produces a state the record never
    held."""
    root, write = repo
    write("weight", [
        {"date": "2030-04-01", "kg": 80.0, "source": "scale",
         "recorded_at": stamp(1)},
        {"date": "2030-04-01", "kg": 78.0, "source": "scale",
         "recorded_at": stamp(20), "supersedes": "2030-04-01/scale"},
    ])
    then = load(root / "data", "weight", as_of=at(10))
    assert [r["kg"] for r in then] == [80.0], "the correction had not happened yet"

    now = load(root / "data", "weight")
    assert [r["kg"] for r in now] == [78.0]


# --- the motivating case ----------------------------------------------------

def test_a_backdated_explanation_is_absent_before_it_was_filed(repo):
    """A context line appended in April about a February state is valid-time
    February and transaction-time April. Reconstructing March must not see it,
    and reconstructing May must."""
    root, write = repo
    write("context", [{"date": "2030-04-01", "mode": "travel",
                       "facilities": None, "place": None, "source": "athlete",
                       "note": None, "recorded_at": stamp(25)}])

    unexplained = Vitai(root, as_of=at(10)).dataset("context")
    assert unexplained == [], "the cause had not been disclosed yet"

    explained = Vitai(root, as_of=at(28)).dataset("context")
    assert len(explained) == 1 and explained[0]["mode"] == "travel"
    assert explained[0]["date"] == "2030-04-01", "valid time is unchanged"


def test_the_cutoff_reaches_every_dataset_through_one_thread(repo):
    """Threaded at `dataset()`, so resolution, verdicts, safety and the build
    inherit it rather than each remembering."""
    root, write = repo
    write("weight", [{"date": "2030-04-02", "kg": 80.0, "source": "scale",
                      "recorded_at": stamp(22)}])
    write("daily", [{"date": "2030-04-02", "steps": 9000, "source": "watch",
                     "recorded_at": stamp(22)}])
    early = Vitai(root, as_of=at(10)).datasets()
    assert early["weight"] == [] and early["daily"] == []
    late = Vitai(root, as_of=at(25)).datasets()
    assert len(late["weight"]) == 1 and len(late["daily"]) == 1


def test_no_cutoff_means_everything_known_now(repo):
    root, write = repo
    write("weight", [{"date": "2030-04-02", "kg": 80.0, "source": "scale",
                      "recorded_at": stamp(22)}])
    assert len(Vitai(root).dataset("weight")) == 1


# --- the guard --------------------------------------------------------------

def test_a_naive_cutoff_is_refused(repo):
    """It would be read in the local zone, so the same call would return
    different records on two machines."""
    root, _ = repo
    with pytest.raises(ValueError, match="explicit offset"):
        Vitai(root, as_of=datetime(2030, 4, 10, 12))
