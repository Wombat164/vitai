"""Every reporting check in `schema` runs during `validate`, or says why not (#418).

`overlapping_instrument_problems` was written, documented, and exercised in five
places by `tests/test_instruments.py`, and `api.validate` never called it. A
repo-wide grep found it in the module that defines it and in the file that tests
it, nowhere else. So it was green, it was maintained, and it had never once run
over anybody's record - which is indistinguishable, from outside, from having
found nothing wrong.

THAT IS THE CLASS, AND THIS FILE IS THE CLASS-LEVEL FIX. Repairing the one
instance leaves the next writer free to add a cross-row check, test it
thoroughly, and forget the one line that dispatches it - and nothing would go
red, because a check that never runs reports no problems.

MEASURED BY EXECUTION, NEVER BY NAME-APPEARANCE, and that is the whole design.
The obvious version of this test reads `api.py` and asks whether each function's
NAME occurs inside `validate`. That is precisely the defect #412 was filed for
one layer up: the population register asked whether a key's name appeared in a
module and counted the WRITER as a reader. A name in a source file is a claim
about dispatch; a call recorded while `validate()` runs is dispatch. So this
wraps every candidate on the module object, runs a real record through
`Vitai.validate`, and asserts on what was actually invoked.

Wrapping on the module object is what makes that work: `api.validate` imports
its checks from `.schema` INSIDE the function body, so the name is resolved at
call time and the wrapper is what it finds. A check reached indirectly - through
`validate_record`, as `absence_problems` is - is recorded the same way, because
that call is a module-global lookup too. Neither is asserted here as a claim
about the import style; the test measures whichever path exists and fails if
none does.

The registry below is an ALLOWLIST and it fails closed. A check that is neither
observed nor registered fails the test; the way to add one is to dispatch it or
to write down why it is not dispatched. A denylist would have let the next
forgotten validator through by default, which is how this one survived.
"""

from __future__ import annotations

import functools
import inspect
import shutil
from pathlib import Path

import pytest

from vitai import schema
from vitai.api import Vitai

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"

# Not dispatched by `Vitai.validate`, each with the reason it is not. Anything
# here must still be a real function in `vitai.schema` - a stale entry is a
# tombstone that quietly shrinks the gate, so it is checked too.
NOT_DISPATCHED_BY_VALIDATE: dict[str, str] = {
    "aliases_for": (
        "Not a check. It returns the spellings a term is known by, and it "
        "shares the `list[str]` shape the reporting checks use rather than "
        "the meaning. Registered rather than filtered out by name, because a "
        "filter tuned to exclude this one would exclude the next check that "
        "happens to be named like a lookup."),
    "ambiguous_aliases": (
        "Not a check, and a SUBSTRING away from looking like one. It returns "
        "`dict[str, list[str]]` - the words that name more than one measurand, "
        "mapped to the fields they could mean - and `_candidates()` matches on "
        "`\"list[str]\" in str(annotation)`, which that contains. Registered "
        "rather than tightening the match, for the reason `aliases_for` is "
        "registered: a rule tuned to exclude this one would exclude the next "
        "check whose annotation is a container of complaints. It is published "
        "through `schema()` and gated by `test_ambiguous_aliases.py`, not by "
        "`validate` - a record cannot make it say anything, because it reads "
        "the registry, which is the same in every install."),
    "removal_problems": (
        "A CI gate over the schema's OWN TABLES, not over a record. It reads "
        "`KEY_RETIREMENT`, `KEY_REMOVAL`, `CURRENT_GENERATION` and `KEYS`, "
        "which are the same in every install, so a record cannot make it say "
        "anything a suite run has not already said. It is dispatched from "
        "`tests/test_retirement_removal.py`, over the LIVE registers and not "
        "only over synthetic ones, which is the part that makes it fire."),
}


def _candidates() -> dict[str, object]:
    """Public functions of `vitai.schema` that RETURN A REPORT.

    Structural, not by name. `list[str]` is what this module's reporting
    convention returns - a list of complaints, empty when there is nothing to
    say - and picking candidates by that shape rather than by a `_problems` /
    `_advisories` suffix means a check named something else is still in scope.
    Two of the fourteen currently dispatched do not carry either suffix
    (`corrections_that_did_not_apply`, `unstamped_after_the_clock_started`),
    which is the evidence that a suffix rule would already have holes.

    Private helpers are out of scope on purpose: `_regime_problems` and its
    fifteen siblings are the per-dataset arms of `validate_record`, dispatched
    by a table inside it, and asserting on them would be asserting on that
    table's contents rather than on whether the module's checks run.
    """
    out = {}
    for name, value in vars(schema).items():
        if name.startswith("_") or not inspect.isfunction(value):
            continue
        if value.__module__ != schema.__name__:
            continue
        try:
            annotation = inspect.signature(value).return_annotation
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
        if "list[str]" in str(annotation):
            out[name] = value
    return out


# SNAPSHOT AT IMPORT, before anything can be patched, and the reason is that
# the first draft of this file did not and passed vacuously. `_candidates()`
# picks functions by their return annotation; a recording wrapper does not
# carry one, so calling `_candidates()` again AFTER the patching returned an
# empty set and the gate asserted that nothing was unaccounted for - out of
# nothing. That is this file's own subject arriving in this file, and it was
# caught by `test_the_measurement_can_fail` below, which is why that test is
# not decoration.
CANDIDATES: dict[str, object] = _candidates()


def _recorder(called: set[str]):
    """Wrap a check so calling it is recorded, and stay honest about it.

    `functools.wraps` rather than a hand-copied `__name__`: it sets
    `__wrapped__`, so `inspect.signature` still reports the real signature and
    a wrapped check cannot silently drop out of a set built by inspecting
    signatures - which is exactly how the vacuous pass above happened.
    """

    def wrap(name, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            called.add(name)
            return func(*args, **kwargs)

        return wrapper

    return wrap


@pytest.fixture
def observed(tmp_path, monkeypatch) -> set[str]:
    """Which candidates `Vitai.validate` actually CALLED on a real record."""
    called: set[str] = set()
    wrap = _recorder(called)

    for name, func in CANDIDATES.items():
        monkeypatch.setattr(schema, name, wrap(name, func))

    # ON A COPY. `validate` reads, but the suite must leave the working tree
    # clean (CI runs `git diff --exit-code` for #322's reason), and a test that
    # points a `Vitai` at the shipped fixture is one refactor away from being
    # a test that writes to it.
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root)
    Vitai(root).validate()
    return called


def test_every_reporting_check_is_dispatched_or_registered(observed):
    """The gate. Not observed and not registered is a check nothing runs."""
    assert CANDIDATES, "the candidate set is empty, so this asserts nothing"
    unaccounted = sorted(
        set(CANDIDATES) - observed - set(NOT_DISPATCHED_BY_VALIDATE))
    assert not unaccounted, (
        "these checks in vitai.schema were never called while "
        "Vitai.validate() ran over the demo record, and nothing says why: "
        f"{unaccounted}. Dispatch them, or add an entry to "
        "NOT_DISPATCHED_BY_VALIDATE giving the reason. A check that is "
        "defined, tested and never dispatched reports no problems, which "
        "reads exactly like finding none.")


def test_overlapping_instruments_is_dispatched(observed):
    """The instance, pinned by name so the class-level test cannot lose it.

    `test_every_reporting_check_is_dispatched_or_registered` would go green
    again if somebody removed the dispatch and added a registry entry. This
    one says that for THIS check that is not an acceptable answer: it is a
    cross-row check over a record's own rows, which is the kind `validate`
    exists to run.
    """
    assert "overlapping_instrument_problems" in observed


def test_the_registry_holds_no_tombstones():
    """A registered name that no longer exists silently shrinks the gate."""
    gone = sorted(n for n in NOT_DISPATCHED_BY_VALIDATE
                  if n not in CANDIDATES)
    assert not gone, (
        f"NOT_DISPATCHED_BY_VALIDATE names {gone}, which vitai.schema no "
        "longer defines as a reporting check. Delete the entries.")


def test_every_registry_entry_states_a_reason():
    """An allowlist entry with no reason is a name somebody wanted skipped."""
    thin = sorted(n for n, why in NOT_DISPATCHED_BY_VALIDATE.items()
                  if len(str(why).strip()) < 40)
    assert not thin, f"these registry entries state no real reason: {thin}"


def test_the_measurement_can_fail(tmp_path, monkeypatch):
    """The control on the control.

    A dispatch census that reported everything as dispatched no matter what
    would pass every assertion above and measure nothing - which is the exact
    failure this file exists to catch, one level up. So: undispatch a check
    that IS dispatched, and the census must notice.

    It has already earned itself once. The first draft of this file rebuilt
    the candidate set after patching, the recording wrappers carried no return
    annotation, the set came back empty, and the gate passed on nothing. This
    test is what said so.
    """
    called: set[str] = set()
    wrap = _recorder(called)

    for name, func in CANDIDATES.items():
        if name == "recorded_at_problems":
            # Not wrapped: replaced by something that never records a call,
            # which is what "defined and never dispatched" looks like from
            # the census's side.
            monkeypatch.setattr(schema, name, lambda *a, **k: [])
            continue
        monkeypatch.setattr(schema, name, wrap(name, func))

    root = tmp_path / "demo"
    shutil.copytree(DEMO, root)
    Vitai(root).validate()

    assert "recorded_at_problems" not in called
    assert sorted(set(CANDIDATES) - called
                  - set(NOT_DISPATCHED_BY_VALIDATE)) == [
        "recorded_at_problems"]
