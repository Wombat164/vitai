"""The gate that finds a check reporting "pass" for a property nobody looked at.

#422 found that `changelog_gate.py` was the one gate of five no test ran, so
`pytest -q` was green whether it passed or not. This file is that lesson
applied on the day the seventh gate lands, and it has a second job the others
do not: `scripts/vacuity_gate.py` is the ONE gate `pytest -q` cannot run over
this repo, because its input is the completed run it would be part of. So the
rule is exercised here against inputs this repo does not contain, and CI's
`vacuity` job is what runs it over the real thing.

Which is the same argument the gate itself makes about the tests it reports.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import vacuity_gate  # noqa: E402
from vacuity_gate import (  # noqa: E402
    asserted_nothing,
    measure,
    register_problems,
    cases_in,
)


def _tests(source: str):
    return cases_in(ast.parse(source))


# --- the rule ------------------------------------------------------------------

VACUOUS_SOURCE = '''
def test_guarded_on_something_that_never_happens(rows):
    for row in rows:
        if row.get("never"):
            assert row["never"] == 1
'''

REAL_SOURCE = '''
def test_it_checks_something(rows):
    assert rows
'''


def test_a_test_that_ran_and_asserted_nothing_is_reported():
    """The finding, in the shape all four of #424's had: a body that runs and
    an assertion under a guard that never opens."""
    tests = _tests(VACUOUS_SOURCE)
    body_only = {2, 3, 4}          # the for and the if, not the assert on 5
    assert asserted_nothing(tests, body_only) == [
        ("test_guarded_on_something_that_never_happens", 2)]


def test_a_test_whose_assertion_ran_is_not_reported():
    tests = _tests(VACUOUS_SOURCE)
    assert asserted_nothing(tests, {2, 3, 4, 5}) == []


def test_a_test_that_never_ran_is_not_reported():
    """Skipped and deselected tests are not findings. A gate that reported
    every skip would be a gate whose first run cries wolf, and #424's own
    objection - a zero-iteration loop is sometimes correct - applies here
    before it applies to the register."""
    assert asserted_nothing(_tests(VACUOUS_SOURCE), set()) == []
    assert asserted_nothing(_tests(REAL_SOURCE), set()) == []


def test_a_test_asserting_only_through_a_helper_is_not_reported():
    """THE STATED LIMIT, held by a test rather than by the docstring alone.
    Plenty here assert through `_expect_problem(...)` or `pytest.raises`, and
    calling those findings would be a gate nobody keeps."""
    source = '''
def test_via_helper(v):
    _expect_problem(v, "boom")
'''
    tests = _tests(source)
    assert tests and not tests[0][3], "the fixture must have no inline assert"
    assert asserted_nothing(tests, {2, 3}) == []


def test_an_assertion_inside_a_nested_helper_counts_as_the_test_s_own():
    """A helper DEFINED IN the test body is part of the test by any reading a
    reviewer would give, so its assert line is one of the test's."""
    source = '''
def test_with_a_local_helper(rows):
    def check(row):
        assert row
    for row in rows:
        check(row)
'''
    tests = _tests(source)
    assert tests[0][3] == {4}, "the nested assert is the test's own"
    assert asserted_nothing(tests, {2, 3, 5, 6}) == [
        ("test_with_a_local_helper", 2)]
    assert asserted_nothing(tests, {2, 3, 4, 5, 6}) == []


def test_a_helper_that_is_not_a_test_is_not_measured():
    """`cases_in` keys on the `test_` prefix, which is what pytest
    collects. A module-level helper with a dead assert is not a check that
    reports pass."""
    source = '''
def helper(rows):
    if rows.get("never"):
        assert False
'''
    assert _tests(source) == []


# --- the register --------------------------------------------------------------

def test_the_register_is_empty_and_that_is_the_shipping_state():
    """Not a pin on which tests are vacuous - #424's four were repaired in
    #431, and an allowlist that fails closed should ship empty. It is here so
    that filling it is a deliberate edit with a reason attached."""
    assert vacuity_gate.VACUOUS == ()


def test_an_entry_naming_no_test_is_refused():
    """A typo silently exempts nothing and hides a real finding - the same
    rule `test_the_registers_name_real_fields` holds one file over."""
    problems = _with_register(
        (("A GAP. placeholder.", ("test_that_does_not_exist",)),),
        known={"test_something_real"})
    assert any("no test" in p for p in problems), problems


def test_an_entry_that_commits_to_neither_kind_is_refused():
    problems = _with_register(
        (("it is fine, honestly", ("test_something_real",)),),
        known={"test_something_real"})
    assert any("must commit" in p for p in problems), problems


def test_two_entries_may_not_share_a_reason():
    """The copy-paste case: a group added by duplicating the one above it
    inherits an explanation written for something else."""
    reason = "A DECISION. The corpus has no case for it."
    problems = _with_register(
        ((reason, ("test_a",)), (reason, ("test_b",))),
        known={"test_a", "test_b"})
    assert any("reuses a reason" in p for p in problems), problems


def test_one_fact_gets_one_entry():
    problems = _with_register(
        (("A GAP. one.", ("test_a",)), ("A GAP. two.", ("test_a",))),
        known={"test_a"})
    assert any("twice" in p for p in problems), problems


def test_a_well_formed_register_reports_nothing():
    assert _with_register(
        (("A DECISION. The register it scans is all-unscheduled, and a "
          "companion asserts that vacuity rather than leaving it accidental.",
          ("test_a",)),),
        known={"test_a"}) == []


def _with_register(register, known: set[str]) -> list[str]:
    original = vacuity_gate.VACUOUS
    vacuity_gate.VACUOUS = register
    try:
        return register_problems(known)
    finally:
        vacuity_gate.VACUOUS = original


# --- over this repo's real test files ------------------------------------------

def test_the_ast_half_runs_over_every_test_file_in_this_repo():
    """The rule is exercised above against synthetic sources; this is the file
    walk, over the real tree, so a syntax the parser mishandles or a file the
    glob misses is found here rather than in CI.

    EVERY FILE HANDED A FULL LINE SET, so nothing can be reported: what is
    being checked is that the walk reaches the files and finds the tests, not
    what it concludes about them.
    """
    everything = {path.resolve(): set(range(1, 20_000))
                  for path in (ROOT / "tests").rglob("test_*.py")}
    findings, ran = measure(everything)
    assert not findings, findings
    assert len(ran) > 500, (
        f"the walk found {len(ran)} tests in a suite of thousands - it is "
        "reaching almost none of the tree")
    assert any(name.endswith("::test_the_ast_half_runs_over_every_test_file_"
                             "in_this_repo") for name in ran), (
        "the walk did not find this very test, so it is not reading this file")


def test_a_file_with_no_coverage_data_is_skipped_not_reported():
    """A test file the run never imported says nothing about its assertions.
    Reporting one would make every deselected module a finding."""
    findings, ran = measure({})
    assert findings == [] and ran == set()


# --- the gate fails closed -----------------------------------------------------

def test_missing_coverage_data_is_a_failure_not_a_pass(tmp_path, capsys):
    """THE ONE THAT MATTERS MOST. A gate that passes when handed nothing to
    measure is a decorative CI step, which is the exact shape this gate exists
    to find. It would also be the easy accident: the `coverage run` step ahead
    of it fails, and a gate returning 0 turns that into a green build."""
    assert vacuity_gate.main([str(tmp_path / "nothing-here")]) == 1
    assert "no coverage data" in capsys.readouterr().err


def test_data_measuring_no_test_file_is_a_failure(tmp_path, capsys):
    """The subtler accident: a run collected with the wrong `--source`, so the
    data is real, the gate reads it, and it reports nothing because it was
    handed nothing about `tests/`."""
    pytest.importorskip("coverage")
    from coverage import CoverageData

    basename = tmp_path / ".coverage"
    data = CoverageData(basename=str(basename))
    data.add_lines({str(ROOT / "src" / "vitai" / "report.py"): [1, 2, 3]})
    data.write()

    assert vacuity_gate.main([str(basename)]) == 1
    assert "measured no file under" in capsys.readouterr().err
