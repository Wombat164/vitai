"""The standard has no history (#148, the half `policy_digest` only made visible).

`as_of` reconstructs the record at an instant by filtering on `recorded_at`.
That is right for everything the record HOLDS. Thresholds live in `vitai.toml`,
outside the append-only record: dated `thresholds` rows overlay it per week,
and a week with no row is judged by whatever the file says TODAY.

So editing a floor in September silently re-judges every earlier week that
lacked an explicit row, and a reconstruction of March returns March's data
under September's policy. Not a staleness problem - a correctness one, in
`as_of` itself and in every historical verdict already produced.

MEASURED, NOT ARGUED, and the first version of this number was wrong: 775
distinct judged weeks across nine of the ten shipped personas, and not one
dated threshold row anywhere in the corpus. The gap is total.

Two halves, and the issue says they are not alternatives. `policy_digest`
shipped the first - a content hash, so a comparison across a config change is
detectable rather than silently wrong. This is the second: say which keys are
in that state, and give the record a way to stop being in it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from vitai.api import Vitai
from vitai.config import THRESHOLD_TYPES

PERSONAS = Path(__file__).resolve().parent / "fixtures" / "personas"


def record(tmp_path: Path, toml: str, thresholds: list[dict] | None = None) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        json.dumps({"date": "2030-05-01", "steps": 9000, "source": "manual"}) + "\n",
        encoding="utf-8")
    if thresholds:
        (root / "data" / "thresholds.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in thresholds), encoding="utf-8")
    return Vitai(root)


# --- naming the gap ------------------------------------------------------------

def test_a_configured_threshold_with_no_dated_row_is_named(tmp_path):
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    assert v.undated_policy() == {"steps_floor": 8000}


def test_a_threshold_the_record_dates_is_not(tmp_path):
    """The overlay works where a row exists - that was the G14 fix, and this
    is only about the weeks it does not reach."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n",
               [{"date": "2030-04-01", "key": "steps_floor", "value": 7000,
                 "change_kind": "change", "set_by": "athlete",
                 "reason": "starting floor", "note": None}])
    assert v.undated_policy() == {}


def test_a_threshold_nobody_configured_is_not_a_gap(tmp_path):
    """Absence of a policy is not a policy with no history. A record that has
    never set a floor is not being judged by one."""
    v = record(tmp_path, "")
    assert v.undated_policy() == {}


def test_every_threshold_key_is_covered(tmp_path):
    """A sixth key added to `THRESHOLD_TYPES` must not slip past this."""
    toml = "[tripwires]\n" + "\n".join(
        f"{key} = {2 if caster is int else 2.0}"
        for key, caster in THRESHOLD_TYPES.items())
    v = record(tmp_path, toml + "\n")
    assert set(v.undated_policy()) == set(THRESHOLD_TYPES)


def test_the_gap_is_reported_to_a_consumer(tmp_path):
    """It is no use as an internal accessor - the whole defect is that the
    answer looked confident. It sits beside what is stale and what is
    missing, because that is what it is."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    brief = v.situation(on="2030-05-01")
    assert brief["unresolved"]["undated_policy"] == {"steps_floor": 8000}


def test_the_shipped_corpus_has_the_gap():
    """Against the real personas rather than a fixture written to show it."""
    v = Vitai(PERSONAS / "yasmin")
    assert v.undated_policy(), "yasmin configures a floor nothing dates"


# --- and closing it -------------------------------------------------------------

def test_pinning_dates_what_the_file_already_said(tmp_path):
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    written = v.pin_policy()
    assert [(r["key"], r["value"]) for r in written] == [("steps_floor", 8000)]
    assert Vitai(v.root).undated_policy() == {}


def test_pinning_twice_writes_nothing_the_second_time(tmp_path):
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    assert v.pin_policy()
    assert Vitai(v.root).pin_policy() == []


def test_pinning_manufactures_no_churn(tmp_path):
    """`change_kind` is `change`, and that costs nothing here: a pinned key has
    no dated row by construction, so the line is the first in its chain, and
    `_edits` diffs consecutive lines with the declaration excluded. Reading it
    as the athlete changing their mind would be a false signal on the surface
    built to catch real ones."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    before = len(v.churn())
    v.pin_policy()
    assert len(Vitai(v.root).churn()) == before


def test_it_pins_forward_and_never_backwards(tmp_path):
    """The toml has no past - that IS the defect - and writing one from its
    present state would bury the defect under a fabrication that reads exactly
    like a record. The row is dated the record's own horizon, and says nothing
    about the weeks before it."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    written = v.pin_policy()
    assert written[0]["date"] == v.on.isoformat()
    assert len(written) == 1, "one row, not one per historical week"


def test_a_pinned_row_carries_who_and_why(tmp_path):
    """`onboard`, not `athlete`. Nobody stated this on this date, and
    `plan_churn` copies the author onto its rows - so claiming the athlete
    would put their name on an assertion the engine composed. Not `derived`
    either: nothing was computed. A value seeded from setup material is what
    `onboard` means."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    row = v.pin_policy(reason="dated during a review")[0]
    assert row["set_by"] == "onboard"
    assert row["change_kind"] == "change", (
        "a correction asserts the previous line never reflected a real "
        "intention, and there is no previous line")
    assert row["reason"] == "dated during a review"
    assert row["recorded_at"], "stamped by the writer, like every append"


def test_pinning_does_not_change_a_single_verdict(tmp_path):
    """It moves what the toml already says into a place that can be dated. If
    a number moved, this would be editing policy rather than recording it."""
    rows = [{"date": f"2030-05-{d:02d}", "steps": 9000 + d * 10,
             "source": "manual"} for d in range(1, 20)]
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\nsteps_floor = 8000\n',
        encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    before = Vitai(root).verdicts()
    Vitai(root).pin_policy()
    after = Vitai(root).verdicts()
    assert before == after


def test_a_build_does_not_pin_anything_by_itself(tmp_path):
    """EXPLICIT, NEVER A SIDE EFFECT. The engine writes to the record only when
    asked - `assert_delivery` is the precedent - and a build that quietly
    appended to the athlete's files would make `vitai build` unrepeatable and
    put the engine's opinion into a record that is theirs."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    v.build()
    assert v.undated_policy() == {"steps_floor": 8000}
    assert not (v.root / "data" / "thresholds.jsonl").exists()


# --- through the CLI ------------------------------------------------------------

def _cli(root: Path, *args) -> str:
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "pin-policy", "--root", str(root), *args],
        capture_output=True, text=True, check=True)
    return out.stdout


def test_the_cli_dry_run_writes_nothing(tmp_path):
    src = PERSONAS / "yasmin"
    root = tmp_path / "y"
    shutil.copytree(src, root)
    before = (root / "data" / "thresholds.jsonl").exists()
    out = _cli(root, "--dry-run")
    assert "sleep_floor_h" in out
    assert "judged by vitai.toml today" in out
    assert (root / "data" / "thresholds.jsonl").exists() == before


def test_the_cli_pins_and_then_says_there_is_nothing_left(tmp_path):
    root = tmp_path / "y"
    shutil.copytree(PERSONAS / "yasmin", root)
    written = _cli(root)
    assert json.loads(written.splitlines()[0])["key"] == "sleep_floor_h"
    assert "already has a dated row" in _cli(root)


# --- what the review found the first version would do ------------------------

def test_pinning_never_writes_in_front_of_an_athletes_own_line(tmp_path):
    """THE ONE AN APPEND MUST NEVER MANAGE. The first version took an `on`
    parameter and asked "is anything in force at this date", so pinning at a
    date BEFORE an existing declaration inserted a line in front of it - and
    `plan_churn` diffs consecutive lines with the declaration excluded, so the
    athlete's first statement of a floor became a flagged LOOSENING on the
    surface built to catch quiet retreats.

    The write now asks a different question - is there a dated row ANYWHERE -
    and there is no `on` parameter at all, because no legitimate use for one
    survived the question."""
    import inspect
    assert "on" not in inspect.signature(Vitai.pin_policy).parameters

    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n",
               [{"date": "2030-05-10", "key": "steps_floor", "value": 7000,
                 "change_kind": "change", "set_by": "athlete",
                 "reason": "starting floor", "note": None}])
    before = v.churn()
    assert v.never_dated_policy() == {}, "the key HAS a dated row"
    assert v.pin_policy() == []
    assert Vitai(v.root).churn() == before


def test_the_two_questions_are_not_the_same_question(tmp_path):
    """`undated_policy` is for REPORTING and is viewpoint-relative: a week
    judged before the athlete first declared a floor was judged by the toml,
    and a consumer looking at that week is owed that. `never_dated_policy` is
    what a WRITE must ask. Conflating them is what produced the defect above."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n",
               [{"date": "2030-05-10", "key": "steps_floor", "value": 7000,
                 "change_kind": "change", "set_by": "athlete",
                 "reason": "starting floor", "note": None}])
    assert v.undated_policy(on="2030-05-01") == {"steps_floor": 8000}
    assert v.never_dated_policy() == {}


def test_it_refuses_to_write_through_a_knowledge_cutoff(tmp_path):
    """`as_of` filters what this instance can SEE and the file it writes to is
    not filtered, so a pin through a cutoff earlier than an existing pin cannot
    see that pin and appends a second identical row - into a file that cannot
    be un-appended. A write whose content is computed from a partial view has
    no business landing in the whole record."""
    import datetime as dt

    import pytest

    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\n")
    v.pin_policy()
    cutoff = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    blind = Vitai(v.root, as_of=cutoff)
    assert blind.never_dated_policy() == {"steps_floor": 8000}, "it cannot see it"
    with pytest.raises(ValueError, match="as_of"):
        blind.pin_policy()
    assert len(Vitai(v.root).dataset("thresholds")) == 1


def test_a_toml_value_the_engine_cannot_type_is_not_an_undated_policy(tmp_path):
    """It is not a policy at all - it is a fault in the file, which `validate`
    reports. Passing it through put uncastable text into a consumer's payload
    and killed `pin-policy` mid-command on a validation error."""
    v = record(tmp_path, '[tripwires]\nsteps_floor = "80OO"\n')
    assert v.undated_policy() == {}
    assert v.never_dated_policy() == {}
    assert v.pin_policy() == []


def test_several_keys_pin_in_a_stable_order(tmp_path):
    """The single-key fixture gave the sort no coverage at all."""
    v = record(tmp_path, "[tripwires]\nsteps_floor = 8000\nsleep_floor_h = 7.0\n"
                         "pain_gate = 3\n")
    keys = [r["key"] for r in v.pin_policy()]
    assert keys == sorted(keys)
    assert set(keys) == {"pain_gate", "sleep_floor_h", "steps_floor"}


def test_the_measured_gap_is_what_the_corpus_actually_holds():
    """The figure this was justified with was wrong, and a number advertised as
    measured that the corpus contradicts is the defect class this repo keeps
    catching."""
    personas = sorted(p for p in PERSONAS.iterdir() if (p / "vitai.toml").exists())
    assert len(personas) >= 10
    with_gap = [p.name for p in personas if Vitai(p).never_dated_policy()]
    assert len(with_gap) >= 9, with_gap
    assert not any((p / "data" / "thresholds.jsonl").exists() for p in personas), \
        "not one dated threshold row anywhere in the corpus"
