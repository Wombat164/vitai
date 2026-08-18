"""A retirement with no end is permanent surface area (#126, G89 part four).

`KEY_RETIREMENT` records when a key stopped being EXPECTED. Nothing recorded
when it stops being CARRIED, which is #126's third item: every adopter inherits
the field, its validation branch and the reader machinery behind it, for a
shape only a handful of records ever wrote.

`KEY_REMOVAL` is that missing half, and the interesting property is that every
entry in it is UNSCHEDULED. A register whose live rows all take one branch is
a register whose other branches have never run, so the controls here build the
schedules that do not exist yet rather than reading only what is committed.
That is the difference between a check and a promise, and #126 is an issue
about a promise (a comment saying the mapping had already happened, beside a
line doing it again).

WHAT IS DELIBERATELY NOT HERE. No control asserts that a particular key is
unscheduled today. That would make scheduling one - the whole point of the
register - fail a test whose name says nothing about scheduling, and the fix
would be to delete it. The rules below constrain what a schedule may SAY, not
whether one exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.schema import (
    CURRENT_GENERATION,
    KEY_REMOVAL,
    KEY_RETIREMENT,
    KEYS,
    removal_plan,
    removal_problems,
)

PERSONAS = Path(__file__).parent / "fixtures" / "personas"
DEMO = Path(__file__).parent.parent / "examples" / "demo"


def _records() -> list[Path]:
    return [d for d in sorted(PERSONAS.iterdir())
            if d.is_dir() and (d / "vitai.toml").exists()] + [DEMO]


def _rows(root: Path, dataset: str) -> list[dict]:
    path = root / "data" / f"{dataset}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line
            in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _carried(dataset: str, key: str) -> int:
    """Corpus rows that actually write this retired key."""
    return sum(1 for root in _records() for row in _rows(root, dataset)
               if row.get(key) is not None)


# --- the live register --------------------------------------------------------

def test_every_retired_key_states_a_removal_decision() -> None:
    """The fail-closed half. A key retired without one goes back to being
    carried indefinitely by default, which is the state #126 describes."""
    problems = removal_problems(KEY_RETIREMENT, KEY_REMOVAL,
                                CURRENT_GENERATION, KEYS)
    assert problems == [], problems


def test_the_register_covers_every_retirement_and_nothing_else() -> None:
    """Back-pressure both ways, so the register cannot drift into a list of
    keys that once existed. A retirement reverted must take its entry with it.
    """
    retired = {(ds, k) for ds, keys in KEY_RETIREMENT.items() for k in keys}
    planned = {(ds, k) for ds, keys in KEY_REMOVAL.items() for k in keys}
    assert retired == planned, retired ^ planned


def test_the_accessor_answers_for_a_retired_key_and_none_otherwise() -> None:
    assert removal_plan("daily", "hip_pain") is not None
    assert removal_plan("daily", "steps") is None
    assert removal_plan("nosuchdataset", "hip_pain") is None


# --- what a reason has to be --------------------------------------------------
#
# Lifted from `test_fixture_coverage`'s DEMO_OMITS controls, which exist
# because the first version of that register was close to theatre: a word count
# alone is satisfied by fourteen words saying nothing, and duplication is the
# failure a word count cannot see.

def test_each_reason_says_something_worth_reading() -> None:
    for (dataset, key), (_gen, why) in sorted(
            ((ds, k), v) for ds, keys in KEY_REMOVAL.items()
            for k, v in keys.items()):
        assert len(why.split()) >= 15, (dataset, key, why)


def test_no_two_reasons_are_the_same() -> None:
    """The copy-paste case. A key added by duplicating the entry above it
    inherits a precondition that was true of something else, and this register
    exists precisely so somebody had to think about THIS key."""
    seen: dict[str, tuple[str, str]] = {}
    for dataset, keys in sorted(KEY_REMOVAL.items()):
        for key, (_gen, why) in sorted(keys.items()):
            assert why not in seen, (dataset, key, seen.get(why))
            seen[why] = (dataset, key)


# --- the branches the live register does not exercise -------------------------
#
# Each builds the register it needs. `removal_problems` is pure and takes its
# registers as arguments for exactly this reason: every one of these cases is
# unreachable through `KEY_REMOVAL` as committed.

_RETIRED = {"daily": {"hip_pain": 2}}
_CURRENT = {"daily": 14}
_KEYS = {"daily": ["date", "hip_pain", "pain"]}


def test_a_retirement_with_no_removal_decision_is_a_finding() -> None:
    problems = removal_problems(_RETIRED, {}, _CURRENT, _KEYS)
    assert len(problems) == 1
    assert "states no removal decision" in problems[0]


def test_a_removal_decision_for_a_key_that_is_not_retired_is_a_finding() -> None:
    problems = removal_problems(
        {}, {"daily": {"hip_pain": (None, "x" * 80)}}, _CURRENT, _KEYS)
    assert len(problems) == 1
    assert "is not retired" in problems[0]


def test_a_reason_that_says_nothing_is_a_finding() -> None:
    problems = removal_problems(
        _RETIRED, {"daily": {"hip_pain": (None, "   ")}}, _CURRENT, _KEYS)
    assert any("states no reason" in p for p in problems), problems


def test_removal_before_retirement_is_a_finding() -> None:
    """A key cannot leave in a generation earlier than the one that stopped
    expecting it - that ordering is what makes an old line legal in between."""
    problems = removal_problems(
        _RETIRED, {"daily": {"hip_pain": (2, "y" * 80)}}, _CURRENT, _KEYS)
    assert any("cannot leave before it stopped being expected" in p
               for p in problems), problems


def test_a_schedule_that_has_passed_while_the_key_remains_is_a_finding() -> None:
    """THE CONTROL THIS REGISTER EXISTS FOR.

    A generation names the release at which the key leaves `KEYS`. If that
    release ships and the key is still there, the register has become a false
    promise, and nothing else in the engine reads a removal generation - so
    the failure is silent, which is the #126 shape exactly: the number is
    right, the linkage is not, and nothing looks broken.
    """
    problems = removal_problems(
        _RETIRED, {"daily": {"hip_pain": (10, "z" * 80)}}, _CURRENT, _KEYS)
    assert any("still in KEYS" in p for p in problems), problems


def test_a_schedule_that_has_passed_and_was_honoured_is_not_a_finding() -> None:
    """The other side of the one above, and it is what stops that check being
    "any schedule in the past fails". The key is gone from `KEYS`, which is
    what the generation promised, so there is nothing to report."""
    gone = {"daily": ["date", "pain"]}
    assert removal_problems(
        _RETIRED, {"daily": {"hip_pain": (10, "z" * 80)}}, _CURRENT, gone) == []


def test_a_schedule_still_ahead_is_not_a_finding() -> None:
    assert removal_problems(
        _RETIRED, {"daily": {"hip_pain": (99, "w" * 80)}}, _CURRENT, _KEYS) == []


# --- the precondition, measured rather than asserted --------------------------
#
# THE RULE IS A FUNCTION AND THE CORPUS IS ITS INPUT (#424). The scan below was
# an inline loop over the live register, every entry of which is unscheduled -
# so the loop body never ran, the assertion inside it never executed, and the
# suite reported the rule as covered. That is the same shape the three controls
# above are built to avoid, and it was the one check here without one.
#
# Nothing is pinned about WHICH entries are scheduled: the module docstring's
# rule stands, and scheduling a removal must not fail a test whose name says
# nothing about scheduling. What the control asserts is that the rule fires -
# against a register this repo does not contain.


def _scheduled_and_still_written(removals: dict,
                                 carried: dict[tuple[str, str], int]) -> list[str]:
    """Keys promised for removal that the corpus has not stopped writing.

    Removing a key from `KEYS` makes every line carrying it fail with an
    unknown-field error, so this pairing is a promise to break the corpus at
    that release.
    """
    return [f"{dataset}.{key}"
            for dataset, keys in sorted(removals.items())
            for key, (gen, _why) in sorted(keys.items())
            if gen is not None and carried.get((dataset, key), 0) > 0]


def test_the_schedule_scan_can_fail() -> None:
    """THE CONTROL THE OTHER THREE HAD AND THIS ONE DID NOT.

    Written against a scheduled removal, which `KEY_REMOVAL` has none of - so
    the branch the live scan cannot reach is reached here, and its failure has
    been seen at least once.
    """
    scheduled = {"daily": {"hip_pain": (14, "x" * 80)}}
    unscheduled = {"daily": {"hip_pain": (None, "x" * 80)}}

    assert _scheduled_and_still_written(
        scheduled, {("daily", "hip_pain"): 91}) == ["daily.hip_pain"], (
        "a scheduled key the corpus still writes is the whole finding")
    assert _scheduled_and_still_written(
        scheduled, {("daily", "hip_pain"): 0}) == [], (
        "a schedule the corpus has already been migrated off is fine")
    assert _scheduled_and_still_written(
        unscheduled, {("daily", "hip_pain"): 91}) == [], (
        "an unscheduled entry promises nothing, which is why the live scan "
        "examines nothing today")
    assert _scheduled_and_still_written(scheduled, {}) == [], (
        "a key no measurement reached counts as unwritten, so a broken corpus "
        "reader cannot manufacture a finding - the reverse direction is what "
        "`test_the_corpus_really_does_still_write_retired_keys` holds")



def test_a_key_the_shipped_corpus_still_writes_is_not_scheduled() -> None:
    """The engine cannot see anyone else's record, but it can see this one.

    Removing a key from `KEYS` makes every line carrying it fail with an
    unknown-field error. So a removal generation named while the repo's own
    corpus still writes the key is a promise to break the corpus at that
    release - and it would be found by the persona suite going red much later,
    with nothing pointing back here.
    """
    broken = _scheduled_and_still_written(
        KEY_REMOVAL, {(ds, k): _carried(ds, k)
                      for ds, keys in KEY_REMOVAL.items() for k in keys})
    assert broken == [], (
        f"{broken} are scheduled for removal and the corpus still writes them. "
        "Migrate the corpus first, or drop the schedule")


def test_the_corpus_really_does_still_write_retired_keys() -> None:
    """Guards the guard. Every entry is unscheduled today, so the check above
    passes by having nothing to examine; if the corpus also carried none of
    these keys, it would go on passing after a schedule was added and the rule
    it states would never have been exercised by anything.

    Asserting the SET rather than the counts: which keys survive in the corpus
    is the fact this rests on, and the counts move whenever a persona is
    regenerated.
    """
    carried = {(ds, k) for ds, keys in KEY_RETIREMENT.items() for k in keys
               if _carried(ds, k) > 0}
    assert carried, (
        "no corpus row writes any retired key, so the schedule rule above is "
        "vacuous and the register's stated precondition is no longer true")
    assert ("daily", "hip_pain") in carried, (
        "the corpus stopped writing the key #126 is about, which is either a "
        "migration worth scheduling a removal for or an accident")
