#!/usr/bin/env python3
"""A deterministic lint against hard-coded contract versions in tests.

## Why

A test that asserts `meta["contract"] == "24"` is not testing the contract, it
is testing a number. The behaviour it means to hold is that the read model
CARRIES the contract it was built under - and that behaviour does not change
when the number does.

The cost is real and was paid three times in one day. `CONTRACT_VERSION` moved
23 -> 24 -> 25 across three merges, and each move broke the same six assertions
in five files, none of which had anything to do with the change that bumped it.
Worse, the breakage arrives during a MERGE, when attention is on resolving a
conflict, and the obvious repair - edit the literal - is also the one that
guarantees the next bump does it again.

The number is also unknowable at branch time: contract version follows MERGE
order, not issue order, so two PRs written against 23 cannot both be right, and
whichever lands second was never wrong so much as unlucky. A literal encodes a
guess about merge order into a test.

## What it looks for

Two shapes, both taken from real occurrences:

  assert meta["contract"] == "24"
  assert meta(policy="abc") == {"contract": "24", "policy": "abc"}
  assert con.execute("... key='contract' ...").fetchone()[0] == "24"

so: a comparison where one side mentions `contract` and the other is a bare
numeric string, and a dict literal whose `contract` key holds one.

## What it deliberately does not do

No check that the literal EQUALS the current version - that would pass today
and fail tomorrow, which is the defect it exists to remove. The rule is that a
contract assertion compares against `CONTRACT_VERSION`, whatever that is.

It also does not look outside `tests/`. A literal in `docs/` is prose about a
particular contract and is often exactly right; the changelog names versions on
purpose.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
NUMERIC = re.compile(r"^\d+$")

# A file may be spared only with a reason, and the reason is read by a human.
# Nothing is spared today; the list exists so that sparing one is a visible
# edit rather than a quiet omission.
ALLOW: dict[str, str] = {}


def _is_numeric_str(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and bool(NUMERIC.match(node.value)))


def _mentions_contract(node: ast.AST, src: str) -> bool:
    try:
        seg = ast.get_source_segment(src, node) or ""
    except Exception:
        return False
    return "contract" in seg.lower()


def scan_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:                       # a broken test is not our finding
        return [f"{path.name}: could not parse ({exc.msg})"]
    out: list[str] = []
    for node in ast.walk(tree):
        # shape 1: <something about contract> == "24"
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            for i, side in enumerate(sides):
                if not _is_numeric_str(side):
                    continue
                others = sides[:i] + sides[i + 1:]
                if any(_mentions_contract(o, src) for o in others):
                    out.append(
                        f"{path.name}:{node.lineno}: contract compared against the "
                        f"literal {side.value!r} - compare against CONTRACT_VERSION, "
                        f"which does not change meaning when the number does")
        # shape 2: == {"contract": "24", ...}
        #
        # ONLY when the dict is a side of a comparison, i.e. an ASSERTION about
        # the build. A dict literal built as fixture data is a different thing
        # and is often deliberately wrong: `emissions` stores `contract` as a
        # FIELD, and its tests construct rows naming contract "5" and "21" as
        # spoofed payloads, checking that a row arriving through the generic
        # append door and naming its own contract is refused. Rewriting those
        # to CONTRACT_VERSION would delete the attack the test exists to make.
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                if not isinstance(side, ast.Dict):
                    continue
                for k, v in zip(side.keys, side.values):
                    if (isinstance(k, ast.Constant) and k.value == "contract"
                            and _is_numeric_str(v)):
                        out.append(
                            f"{path.name}:{node.lineno}: contract asserted as the "
                            f"literal {v.value!r} - use CONTRACT_VERSION")
    return out


def main() -> int:
    problems: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        if path.name in ALLOW:
            continue
        problems += scan_file(path)
    if problems:
        print("contract-literal gate: FAIL")
        for p in problems:
            print("  " + p)
        print(f"\n{len(problems)} hard-coded contract version(s). A contract "
              "assertion holds that the read model CARRIES its contract, not "
              "that the number is any particular value.")
        return 1
    print("contract-literal gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
