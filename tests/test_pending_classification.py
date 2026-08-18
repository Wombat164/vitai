"""A correction cannot be recognised before it is appended (#425).

FALSIFY-FIRST ARTIFACT: the tests below fail against the engine as it is, and
they encode the finding rather than the fix. Written before any change so that
what was measured is on the record whatever happens to the fix.

WHAT #425 SAID, AND WHAT IS ACTUALLY TRUE. The issue reasons that an importer's
rows legally carry no `recorded_at`, so a guard asking `_later` classifies every
incoming row AMBIGUOUS. Measured against this engine, the shape is sharper and
partly different:

  * `append_many` STAMPS BEFORE IT GUARDS. Inside it, rows get their
    `recorded_at` (jsonl.py, the `now_stamp(now, after=high_water)` line) and
    only then is `_corrections_that_would_not_apply` consulted. So the WRITE
    path is not broken: appending a declared correction over a held row works
    and retires it. Verified by execution, both declared and undeclared.

  * THE HOLE IS THAT NOTHING PUBLIC CAN ASK BEFORE THE WRITE, and the private
    function that looks like the answer gives the WRONG one on legal input.
    Called directly with unstamped rows - which is exactly what an importer
    holds, and what the client-side guard mirrors -
    `_corrections_that_would_not_apply` refuses a correction that names its
    target, with "this write is stamped None".

So the path #425 points at as the one that works - `supersedes`, a correction
that DECLARES itself rather than being inferred from a clock - is refused
before the append that would accept it. The ordering field does not exist yet
at the moment the ordering question is asked, and the engine asks it anyway
instead of modelling the stamp it is about to assign.

Synthetic data only. The 1,354 -> 3,091 day is #425's own fixture: a
MyFitnessPal day exported at lunchtime and completed after dinner.
"""

from __future__ import annotations

import pytest

from vitai.cli import main
from vitai.jsonl import append_many, load

HELD, COMPLETED = 1354, 3091
DAY, SOURCE = "2030-05-01", "mfp-export"


def _repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root / "data"


def _daily(**kw):
    """A daily row as an importer legally prepares it: NO `recorded_at`.

    Supplying one is refused outright - "the one clock in the record that
    cannot be authored" - so this is not an omission, it is the only legal
    shape a pending row has.
    """
    row = {"date": DAY, "kcal_in": None, "source": SOURCE, "note": None,
           "steps": None, "_gen": 8}
    row.update(kw)
    return row


def test_the_write_path_accepts_a_declared_correction(tmp_path):
    """The half that already works, and it is worth pinning before touching
    anything: `append_many` stamps and then guards, so the correction applies
    and the stale row goes."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    append_many(data, "daily",
                [_daily(kcal_in=COMPLETED, supersedes=f"{DAY}/{SOURCE}")],
                device="phone")
    live = load(data, "daily")
    assert [r["kcal_in"] for r in live] == [COMPLETED], live


def test_an_undeclared_restatement_is_two_claims_not_a_correction(tmp_path):
    """Also already true, and the other half of the answer: a row that does not
    NAME its target retires nothing. Both claims live and resolution picks
    between them - which is the engine behaving correctly, not a hole."""
    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    append_many(data, "daily", [_daily(kcal_in=COMPLETED)], device="phone")
    assert sorted(r["kcal_in"] for r in load(data, "daily")) == [HELD, COMPLETED]


def test_asking_before_the_write_gives_the_answer_the_write_gives(tmp_path):
    """THE DEFECT. An importer must be able to ask what the append will do
    BEFORE it writes, and the answer must match what the append then does.

    Today the only thing that answers is private and compares a stamp the
    pending row cannot legally carry, so it refuses a correction the very next
    line would accept. FAILS against the engine as it is.
    """
    from vitai.jsonl import pending_problems

    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    pending = [_daily(kcal_in=COMPLETED, supersedes=f"{DAY}/{SOURCE}")]

    assert pending_problems(data, "daily", pending) == [], (
        "the engine refused, before the write, a correction the write accepts")
    append_many(data, "daily", pending, device="phone")
    assert [r["kcal_in"] for r in load(data, "daily")] == [COMPLETED]


def test_the_private_guard_no_longer_refuses_an_unstamped_correction(tmp_path):
    """The same defect at the function the client-side guard mirrors, so the
    fix is not merely a new name in front of the old answer."""
    from vitai.jsonl import _corrections_that_would_not_apply

    data = _repo(tmp_path)
    append_many(data, "daily", [_daily(kcal_in=HELD)], device="phone")
    problems = _corrections_that_would_not_apply(
        data, "daily", [_daily(kcal_in=COMPLETED,
                               supersedes=f"{DAY}/{SOURCE}")])
    assert problems == [], problems


def test_a_correction_a_peer_stamped_ahead_of_is_still_refused(tmp_path):
    """AND THE REFUSAL MUST SURVIVE THE FIX. The guard exists for a row another
    writer stamped ahead of this one, and modelling this device's stamp must
    not silence that - which is the #391 view-dependence trap wearing different
    clothes. Marked xfail only because it cannot be written until the fix
    exists; it is the control on it.
    """
    pytest.skip("control for the fix; see the PR - written once the modelled "
                "stamp exists so it can be shown to still fire")
