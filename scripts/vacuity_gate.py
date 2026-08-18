#!/usr/bin/env python3
"""A test that ran, passed, and executed none of its own assertions (#424).

## Why

Three of these were found by hand and every one had been green for months.
`test_units.py` guarded on a registry key no entry uses; the G69 rate guard was
keyed to a string the rollup stopped emitting, leaving a SAFETY property
unheld while the suite reported it covered; `test_a_refusal_carries_no_numerator`
asserted only inside a branch its own fixture never produced. #412 and #418
were the same family one layer down.

The common shape is not a bug in any of them. It is that **a check reports
"pass" for two different states** - the property held, and the property was
never looked at - and nothing distinguishes them. A guard keyed to one spelling
of an output is retired silently by the next renderer change, and the suite
goes on saying it is covered.

## What this measures

The suite under `coverage run --source=tests`, then every `assert` line inside
every `test_*` function cross-referenced against the lines that actually ran. A
test whose body executed and whose every `assert` line did not is reported.

## Why a register and not a red build

**A zero-iteration loop is sometimes correct.** `test_retirement_removal.py`
is the honest case: every `KEY_REMOVAL` entry is unscheduled, so the corpus
scan legitimately has nothing to examine, and its vacuity is asserted by a
companion rather than accidental. A gate that failed on it would be a gate
whose fix is to delete the finding.

So this is the `test_field_population.py` shape: an ALLOWLIST that fails
closed. An unregistered finding is a red build. A registered one has to say
whether it is A DECISION or A GAP, and has to LEAVE the register the day it
gains an executed assertion - or the register rots into the list of excuses
every register here is careful not to be.

## What it deliberately does not do

**It does not report a test with no `assert` statements of its own.** Plenty
here assert through a helper - `_expect_problem(...)`, `pytest.raises` - and
calling those a finding would be a gate crying wolf on its first run. The cost
is real and stated: a test whose only inline assert never runs while its helper
asserts do is invisible here.

**It does not measure `src/`.** Whether the engine's branches are covered is a
different question with a different answer, and this one is about the checks.

## The cost, stated

One coverage run of the suite, in its own CI job. #424 named that cost when it
deferred this gate, and it is the reason this is a separate job rather than a
step inside `tests`: the four-leg matrix would pay it four times for one
answer.

    coverage run --source=tests -m pytest -q
    python scripts/vacuity_gate.py

Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# Tests that legitimately execute no assertion of their own, and why. An entry
# must commit to A DECISION or A GAP, and must leave the day the test starts
# asserting. EMPTY TODAY, deliberately: #431 repaired the four this issue
# found, and an empty allowlist is the state a fail-closed gate should ship in.
# The machinery is exercised by `tests/test_vacuity_gate.py` against synthetic
# input rather than by whatever happens to be broken today.
VACUOUS: tuple[tuple[str, tuple[str, ...]], ...] = ()


def cases_in(tree: ast.Module) -> list[tuple[str, int, set[int], set[int]]]:
    """(name, line, body lines, assert lines) for every test in one module.

    NOT NAMED `test_...`, and the first two drafts were. pytest collects on the
    `test*` prefix, so both `test_functions` and `tests_in` were picked up as
    tests the moment a test module imported them, each demanding a `tree`
    fixture nobody defines. A gate whose helpers pytest collects is a gate that
    cannot be unit-tested, which is how it would have shipped unexercised.

    NESTED FUNCTIONS COUNT AS THE TEST'S OWN. A helper defined inside the test
    body is part of it, and its asserts are the test's assertions by any
    reading a reviewer would give.
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        body = {n.lineno for stmt in node.body for n in ast.walk(stmt)
                if hasattr(n, "lineno")}
        asserts = {n.lineno for n in ast.walk(node)
                   if isinstance(n, ast.Assert)}
        out.append((node.name, node.lineno, body, asserts))
    return out


def asserted_nothing(tests: list[tuple[str, int, set[int], set[int]]],
                     executed: set[int]) -> list[tuple[str, int]]:
    """Tests whose body ran and whose every `assert` line did not.

    A PURE FUNCTION over two line sets, so the rule can be shown to fail
    against input this repo does not contain - which is the whole subject of
    the issue this gate closes. A measurement exercised only by the corpus it
    measures is one whose failure nobody has seen.

    THREE STATES, NOT TWO. A test with no `assert` of its own is not reported
    (it asserts through a helper); a test whose body never ran is not reported
    (it was skipped, or deselected); only a test that RAN and asserted nothing
    is.
    """
    return [(name, line) for name, line, body, asserts in tests
            if asserts and (body & executed) and not (asserts & executed)]


def _flat_register() -> list[str]:
    return [name for _reason, names in VACUOUS for name in names]


def register_problems(known: set[str]) -> list[str]:
    """The register's own rules, checked against the tests that exist.

    BACK-PRESSURE IN BOTH DIRECTIONS, on `test_field_population`'s pattern: an
    entry naming no test is a typo that silently exempts nothing, and a reason
    that commits to neither kind is an excuse with better prose.
    """
    out = []
    flat = _flat_register()
    for entry in sorted(set(flat) - known):
        out.append(f"VACUOUS names {entry!r}, which is no test in tests/")
    for name in sorted({n for n in flat if flat.count(n) > 1}):
        out.append(f"VACUOUS holds {name!r} twice - one fact, one entry")
    seen: set[str] = set()
    for reason, names in VACUOUS:
        if not reason.startswith(("A DECISION", "A GAP")):
            out.append(f"{names} must commit: an entry that says neither "
                       "A DECISION nor A GAP is an excuse with better prose")
        if reason in seen:
            out.append(f"{names} reuses a reason written for something else")
        seen.add(reason)
    return out


def measure(executed_by_file: dict[Path, set[int]]) -> tuple[list[str], set[str]]:
    """(findings, every test that ran) as `file::name` over the whole suite."""
    findings, ran = [], set()
    for path in sorted(TESTS.rglob("test_*.py")):
        lines = executed_by_file.get(path.resolve())
        if not lines:
            continue
        tests = cases_in(ast.parse(path.read_text(encoding="utf-8")))
        rel = path.relative_to(ROOT)
        for name, line, body, _asserts in tests:
            if body & lines:
                ran.add(f"{rel}::{name}")
        for name, line in asserted_nothing(tests, lines):
            findings.append(f"{rel}:{line}::{name}")
    return sorted(findings), ran


def _executed(basename: Path) -> dict[Path, set[int]]:
    from coverage import CoverageData

    data = CoverageData(basename=str(basename))
    data.read()
    return {Path(f).resolve(): set(data.lines(f) or [])
            for f in data.measured_files()}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    basename = Path(argv[0]) if argv else ROOT / ".coverage"

    if not any(basename.parent.glob(basename.name + "*")):
        # FAILS CLOSED ON MISSING INPUT. A gate that passes when it was handed
        # nothing to measure is a decorative CI step, which is the exact shape
        # this gate exists to find.
        print(f"no coverage data at {basename} - run "
              "`coverage run --source=tests -m pytest -q` first", file=sys.stderr)
        return 1

    executed = _executed(basename)
    if not any(TESTS in p.parents for p in executed):
        print(f"{basename} measured no file under {TESTS} - it was collected "
              "with the wrong --source, and this gate would report nothing",
              file=sys.stderr)
        return 1

    findings, ran = measure(executed)
    problems = register_problems({name.split("::", 1)[1] for name in ran}
                                 | {p.stem for p in TESTS.rglob("test_*.py")})

    registered = set(_flat_register())
    new = [f for f in findings if f.split("::", 1)[1] not in registered]
    stale = sorted(registered - {f.split("::", 1)[1] for f in findings})

    for line in problems:
        print(f"REGISTER: {line}", file=sys.stderr)
    for line in new:
        print(f"ASSERTED NOTHING: {line}", file=sys.stderr)
    for line in stale:
        print(f"STALE: {line} now executes an assertion - remove it from "
              "VACUOUS", file=sys.stderr)

    if problems or new or stale:
        print(f"\n{len(new)} unregistered, {len(stale)} stale, "
              f"{len(problems)} register problem(s). A test that runs and "
              "asserts nothing reports 'pass' for a property nobody looked "
              "at - repair it, or register it with the reason.", file=sys.stderr)
        return 1

    print(f"{len(ran)} tests ran; none of them asserted nothing "
          f"({len(registered)} registered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
