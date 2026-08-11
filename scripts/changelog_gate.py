#!/usr/bin/env python3
"""A deterministic check on changelog fragments, and the tool that folds them in.

## Why

Every pull request appended its entry under the same heading at the top of
`CHANGELOG.md`, so any two open at once conflicted on the same lines. Four
times in two days - #339 against #340, #341 against #344, #345 against main -
and every one was additive, trivial, and resolved by keeping both entries in
landing order.

The cost was never the minute. It is that a conflict on a merge nobody needs to
think about teaches everyone to resolve conflicts without reading them, on a
repo where a superseding line disagreeing with the line it retires is a bug
worth its own issue (#342). A process that trains people to click through
conflicts is the wrong process to have around that work.

`## [Unreleased]` carries the marks: several `### Fixed` headings inside one
release block, because appending a new section is easier than merging into an
existing one when the file is contended.

So a pull request writes `changelog.d/<issue>.<category>.md` and never touches
`CHANGELOG.md`. Two branches cannot contend for one file unless they are
working the same issue in the same category, which is a conflict worth having.

## What this checks

Nothing about prose. A fragment is checked for the things a machine can decide:
that its name parses, that its category is one `CHANGELOG.md` declares, that it
is not empty, and that it is a markdown list rather than a paragraph - because
the assembler splices it under a heading and a paragraph would render wrong.

It also fails on a conflict marker anywhere in `CHANGELOG.md`, which is the
failure this whole scheme exists to end and which has reached a branch before.

Exit 0 = pass, 1 = fail.

    python scripts/changelog_gate.py             # check
    python scripts/changelog_gate.py --assemble  # fold fragments in, at release
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS = ROOT / "changelog.d"
CHANGELOG = ROOT / "CHANGELOG.md"

# The Keep a Changelog set, because that is the format CHANGELOG.md declares.
# Closed on purpose: an open vocabulary would mean a heading per author.
CATEGORIES = ("added", "changed", "deprecated", "removed", "fixed", "security")

NAME = re.compile(r"^(\d+)\.([a-z]+)\.md$")
CONFLICT = re.compile(r"^(<{7}|={7}|>{7})", re.MULTILINE)


def fragments() -> list[Path]:
    if not FRAGMENTS.is_dir():
        return []
    return sorted(p for p in FRAGMENTS.iterdir()
                  if p.is_file() and p.name != "README.md")


def check() -> list[str]:
    problems = []

    if CHANGELOG.is_file() and CONFLICT.search(CHANGELOG.read_text(encoding="utf-8")):
        problems.append(
            "CHANGELOG.md contains a conflict marker. That is the failure this "
            "scheme exists to end; do not commit a half-resolved merge.")

    for p in fragments():
        m = NAME.match(p.name)
        if not m:
            problems.append(
                f"{p.name}: name must be <issue>.<category>.md, e.g. "
                f"342.fixed.md")
            continue
        if m.group(2) not in CATEGORIES:
            problems.append(
                f"{p.name}: unknown category {m.group(2)!r}. One of: "
                f"{', '.join(CATEGORIES)}")
        body = p.read_text(encoding="utf-8").strip()
        if not body:
            problems.append(f"{p.name}: empty")
        elif not body.startswith("-"):
            problems.append(
                f"{p.name}: must be a markdown list item starting with '-'. "
                f"The assembler splices it under a heading, so a bare "
                f"paragraph renders as prose in the middle of a list.")
    return problems


def _unreleased_bounds(lines: list[str]) -> tuple[int, int]:
    """Where the `## [Unreleased]` block starts and ends."""
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("## [Unreleased]"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return start, end


def assemble() -> int:
    """Fold every fragment into `## [Unreleased]`, then delete what was used.

    A maintainer runs this once at release, with no branch open against them,
    which is the whole difference from every pull request editing one block.
    """
    frags = fragments()
    if not frags:
        print("no fragments to assemble")
        return 0

    lines = CHANGELOG.read_text(encoding="utf-8").split("\n")
    start, end = _unreleased_bounds(lines)

    by_cat: dict[str, list[str]] = {}
    for p in frags:
        m = NAME.match(p.name)
        if not m:
            continue
        by_cat.setdefault(m.group(2), []).append(
            (int(m.group(1)), p.read_text(encoding="utf-8").rstrip("\n")))

    block = lines[start:end]
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        entries = [text for _, text in sorted(by_cat[cat])]
        heading = f"### {cat.capitalize()}"
        # Under the LAST matching heading, so a fold reads in landing order
        # beside whatever is already there rather than jumping the queue.
        at = None
        for i, line in enumerate(block):
            if line.strip() == heading:
                at = i
        if at is None:
            # A new section goes at the end of the block, and keeps a blank
            # line after it: the next line is the previous release's `## `
            # heading, and a heading flush against a list item renders as part
            # of the list in some parsers.
            block += ["", heading, ""] + entries + [""]
        else:
            stop = len(block)
            for j in range(at + 1, len(block)):
                if block[j].startswith("### "):
                    stop = j
                    break
            while stop > at + 1 and not block[stop - 1].strip():
                stop -= 1
            block[stop:stop] = entries

    CHANGELOG.write_text("\n".join(lines[:start] + block + lines[end:]),
                         encoding="utf-8", newline="\n")
    for p in frags:
        p.unlink()
    print(f"assembled {len(frags)} fragment(s) into {CHANGELOG.name}")
    return 0


def main() -> int:
    if "--assemble" in sys.argv[1:]:
        return assemble()
    problems = check()
    if problems:
        print("changelog fragments:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print("\nSee changelog.d/README.md.", file=sys.stderr)
        return 1
    n = len(fragments())
    print(f"changelog gate: clean ({n} fragment(s) pending release)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
