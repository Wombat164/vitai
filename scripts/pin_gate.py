#!/usr/bin/env python3
"""Every input CI resolves is pinned, and every place stating a pin agrees (#416).

## Why

`loadline`'s `main` went red for two days and nobody noticed. Its CI re-emits a
committed artifact from a pinned copy of this engine and diffs it, so absorbing
a contract moved what the engine emits and invalidated the committed copy from
the other side of a pin. The fix that stuck there was not bumping the pin - it
was making one local check hold the contract across all five places that state
it, before a push.

This repo does not have that shape, and #416 verified it by execution rather
than by reading: every committed-artifact-versus-re-derivation pair in `vitai`
derives from an input in THIS repo and runs on EVERY pull request, so the PR
that moves the input is the PR that goes red. That is the correct design and it
is unchanged here.

What the audit found is the same family pointing the other way. None of these
can make a committed artifact stale. They are places where CI's answer can
change with NO COMMIT AT ALL:

- `pip install ruff` and `pip install -e . pytest`. A ruff release adding a
  rule inside the `E`/`F`/`W` prefixes turns `main` red with nothing having
  changed. `pyproject.toml` says the ruff config is "pinned explicitly so
  local and CI ruff versions agree on the rule set", which is true of the
  `select` list and reads like a version pin.
- `pypa/gh-action-pypi-publish@release/v1` - a MOVING TAG, in a repo where
  every other action is SHA-pinned with a version comment.
- `node-version: 22` and `runs-on: ubuntu-22.04` in the wiki deploy - one a
  floating minor, the other a runner label GitHub retires on its own schedule.

**An answer that can change with no commit is a check whose result is not
attributable to anything.** A green run means "these versions passed", and if
nothing records which versions those were, it means nothing that survives the
day.

## What it enforces

1. **No workflow installs an unpinned package.** A `pip install` line may name
   `-e .`, a flag, or `-r <file>`; a bare package name is refused. This is an
   ALLOWLIST rather than a list of packages to watch, because a denylist would
   pass the next tool somebody adds - which is exactly how `ruff` and `pytest`
   got here.
2. **Every requirements file a workflow installs from is fully pinned**, every
   line `name==version`.
3. **Every `uses:` is a 40-hex commit SHA with a version comment.** A tag,
   moving or not, is a name somebody else can repoint.
4. **Every `node-version:` is an exact `x.y.z`.**
5. **Every `runs-on:` label is registered here with a reason.** Both answers
   are defensible and neither is safe by default: a floating label moves under
   you, and a dated label retires under you with nothing to bump it. What is
   not defensible is picking one without saying which and why, which is how
   `ubuntu-22.04` ended up in one workflow and `ubuntu-latest` in the others.
6. **`uv.lock` states the same version and `requires-python` as
   `pyproject.toml`.** The lock is a derived artifact and a repo-wide grep
   finds `uv.lock` / `uv lock` nowhere outside the file itself, so nothing
   re-derives it and nothing compares it: it cannot go red, only quietly
   wrong. This is the inverse of the loadline trap and the cheapest honest
   answer to it. Deleting the file is the other one, and is the maintainer's
   call rather than a gate's.
7. **`CONTRIBUTING.md` documents the same install a developer needs**, so the
   local toolchain and CI's cannot drift apart silently. The point of a pin is
   that everybody has it.
8. **Every gate CI runs is named in the documents that tell a human what to
   run before pushing**, and the `ruff` invocation is the same string
   everywhere. This is the half the loadline incident actually turned on: the
   fix that stuck there was not bumping a pin, it was one local check holding
   the contract across all five places that state it. Three documents here
   said `ruff check src tests` while CI ran `ruff check .` - so a developer
   who followed the docs got a clean lint over two directories and read it as
   a fact about the repo, which is the same misreading that widening the CI
   scope was meant to end. `RELEASING.md` likewise listed three of the six
   hygiene steps, which makes the other three CI-only, and #389 already spent
   a change on why a CI-only check is one nobody can run.

## What it deliberately does not do

**It does not check that a pin is CURRENT.** That would pass today and fail
tomorrow with no commit, which is the defect this gate exists to remove -
`contract_literal_gate.py` declines the same thing for the same reason.
Dependabot proposes bumps; this says the answer is written down.

**It does not read `pyproject.toml`'s `dependencies`.** That list stays empty
and `dependency_gate.py` is what holds it. Development dependencies are a
different question with a different answer.

**It does not pin `npm ci`.** Verified rather than assumed: the wiki build
fetches Quartz at a pinned commit and that tree ships a `package-lock.json`,
which is what `npm ci` installs from, exactly. The float there was the node
runtime, and rule 4 is that.

## Why it reads YAML with regular expressions

Because it has to. The `hygiene` job installs `requirements-dev.txt` and
nothing else, so a gate that imported a YAML parser would need a dependency
added to the very file it exists to keep small - and a gate that cannot run
until its own dependency resolves is a gate with a resolution step in front of
it. The rules here are all line-shaped (`uses:`, `run: pip install`,
`node-version:`, `runs-on:`), which is the shape regexes are honest about. A
rule needing the document TREE belongs in a different check with a different
install.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Runner labels, each with the reason it is the one chosen. Rule 5.
RUNNERS: dict[str, str] = {
    "ubuntu-latest": (
        "GitHub keeps this current, so it moves - and moving is the lesser of "
        "two evils here, because a dated label is retired on GitHub's "
        "schedule and nothing in this repo would bump it. The jobs that run "
        "on it install their own toolchain from a pinned requirements file, "
        "so what the image supplies is a kernel and a shell."),
    "windows-latest": (
        "Same reasoning, and the matrix leg it carries is the point: this "
        "engine writes files and reads dates, and both are where a "
        "Windows-only defect lives. There is no dated Windows label worth "
        "pinning to instead."),
}

# `uses:` values exempt from the SHA rule. Empty, and meant to stay that way:
# a local action (`./.github/actions/x`) would go here if one is ever written.
USES_EXEMPT: dict[str, str] = {}

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NODE_RE = re.compile(r"^\d+\.\d+\.\d+$")
PIN_RE = re.compile(r"^[A-Za-z0-9._-]+==[A-Za-z0-9._+!-]+$")


def _workflow_lines() -> list[tuple[Path, int, str]]:
    out = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            out.append((path, n, line))
    return out


def check_uses(lines) -> list[str]:
    """Rule 3: a SHA and a version comment, or it is a name someone can move."""
    out = []
    for path, n, line in lines:
        m = re.match(r"\s*-?\s*uses:\s*(\S+)", line)
        if not m:
            continue
        ref = m.group(1)
        if ref in USES_EXEMPT:
            continue
        if "@" not in ref:
            out.append(f"{path.name}:{n}: `uses: {ref}` names no version at all")
            continue
        name, _, at = ref.partition("@")
        if not SHA_RE.match(at):
            out.append(
                f"{path.name}:{n}: `uses: {ref}` is pinned to {at!r}, which is "
                f"a tag - and a tag is a name its owner can repoint under you. "
                f"Every other action in this repo is pinned to a 40-hex commit "
                f"SHA with a `# vX.Y.Z` comment; pin this one the same way")
            continue
        if not re.search(r"#\s*v?\d", line):
            out.append(
                f"{path.name}:{n}: `uses: {name}` is SHA-pinned with no version "
                f"comment, so nothing readable says what it is pinned TO")
    return out


def check_pip_installs(lines) -> list[str]:
    """Rules 1 and 2: nothing unpinned enters a runner."""
    out = []
    wanted_files: set[str] = set()
    for path, n, line in lines:
        m = re.search(r"pip install\s+(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        tokens = rest.split()
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ("-e", "--editable"):
                i += 2
                continue
            if tok in ("-r", "--requirement"):
                if i + 1 < len(tokens):
                    wanted_files.add(tokens[i + 1])
                i += 2
                continue
            if tok.startswith("-"):
                i += 1
                continue
            if PIN_RE.match(tok):
                out.append(
                    f"{path.name}:{n}: `{tok}` is pinned inline. Put it in a "
                    f"requirements file instead - a pin stated in a workflow "
                    f"is one dependabot's pip ecosystem cannot see, which is "
                    f"how the unpinned versions survived")
                i += 1
                continue
            out.append(
                f"{path.name}:{n}: `pip install {tok}` is unpinned, so this "
                f"job's answer can change with no commit. Install from a "
                f"requirements file: `-r requirements-dev.txt`")
            i += 1

    for name in sorted(wanted_files):
        req = ROOT / name
        if not req.is_file():
            out.append(f"a workflow installs from {name}, which does not exist")
            continue
        for n, line in enumerate(req.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.split("#", 1)[0].strip()
            if not stripped:
                continue
            if not PIN_RE.match(stripped):
                out.append(
                    f"{name}:{n}: {stripped!r} is not an exact `name==version` "
                    f"pin, so what CI installs is decided at install time")
    return out


def check_runtime_versions(lines) -> list[str]:
    """Rules 4 and 5."""
    out = []
    for path, n, line in lines:
        m = re.search(r"node-version:\s*['\"]?([^'\"\s#]+)", line)
        if m and not NODE_RE.match(m.group(1)):
            out.append(
                f"{path.name}:{n}: `node-version: {m.group(1)}` floats - the "
                f"runtime that builds the site can change with no commit. Pin "
                f"`x.y.z`")
        m = re.search(r"runs-on:\s*(\S+)", line)
        if m:
            label = m.group(1)
            if label.startswith("${{"):
                continue  # a matrix value; the matrix entries are checked below
            if label not in RUNNERS:
                out.append(
                    f"{path.name}:{n}: runner {label!r} is not in "
                    f"`RUNNERS` in this gate. Add it with the reason it is "
                    f"the right one - a floating label moves under you and a "
                    f"dated label retires under you, and the repo should say "
                    f"which it accepts rather than have both by accident")
        m = re.search(r"os:\s*\[(.*)\]", line)
        if m:
            for label in [v.strip() for v in m.group(1).split(",")]:
                if label and label not in RUNNERS:
                    out.append(
                        f"{path.name}:{n}: matrix runner {label!r} is not in "
                        f"`RUNNERS` in this gate. Add it with its reason")
    return out


def check_uv_lock() -> list[str]:
    """Rule 6: the orphan derived artifact gets one comparison it can fail."""
    lock = ROOT / "uv.lock"
    if not lock.is_file():
        return []
    text = lock.read_text(encoding="utf-8")
    proj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    out = []

    want_version = re.search(r'^version = "([^"]+)"', proj, re.M)
    got_version = re.search(r'name = "vitai"\nversion = "([^"]+)"', text)
    if want_version and got_version and want_version.group(1) != got_version.group(1):
        out.append(
            f"uv.lock records vitai {got_version.group(1)} and pyproject.toml "
            f"says {want_version.group(1)}. Nothing else in this repo reads "
            f"uv.lock, so without this line it would disagree silently - "
            f"regenerate it with `uv lock`, or delete it")

    want_py = re.search(r'^requires-python = "([^"]+)"', proj, re.M)
    got_py = re.search(r'^requires-python = "([^"]+)"', text, re.M)
    if want_py and got_py and want_py.group(1) != got_py.group(1):
        out.append(
            f"uv.lock requires-python is {got_py.group(1)!r} and "
            f"pyproject.toml says {want_py.group(1)!r}")
    return out


def check_contributing() -> list[str]:
    """Rule 7: the documented local setup installs what CI installs.

    A pin only does its job if the person who runs `ruff check` before pushing
    has the same ruff. `CONTRIBUTING.md` said `pip install -e . pytest ruff`,
    which is the unpinned shape one surface over from CI.
    """
    doc = ROOT / "CONTRIBUTING.md"
    if not doc.is_file():
        return []
    text = doc.read_text(encoding="utf-8")
    out = []
    if "requirements-dev.txt" not in text:
        out.append(
            "CONTRIBUTING.md never mentions requirements-dev.txt, so the setup "
            "it documents resolves different versions than CI does. A pin "
            "only holds if the local toolchain is the same one")
    for bad in re.findall(r"pip install [^\n]*", text):
        tokens = bad.split()[2:]
        loose = [t for t in tokens
                 if not t.startswith("-") and t != "." and not PIN_RE.match(t)
                 and not t.endswith(".txt")]
        if loose:
            out.append(
                f"CONTRIBUTING.md documents `{bad}`, which installs "
                f"{', '.join(loose)} unpinned")
    return out


# The documents that tell a human what to run before pushing. Rule 8.
PRE_PUSH_DOCS = ("RELEASING.md", "CONTRIBUTING.md",
                 ".github/PULL_REQUEST_TEMPLATE.md")


def check_gates_are_runnable_locally() -> list[str]:
    """Rule 8: a check that exists only in CI is a check nobody can run.

    Two halves, and the second is the one that bites. That every gate script
    is WIRED INTO CI is the obvious half. That every gate CI runs is NAMED
    where a human is told what to run is the half that drifts, because adding
    a gate to `ci.yml` is a complete-looking change on its own.
    """
    out = []
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    docs = {name: (ROOT / name).read_text(encoding="utf-8")
            for name in PRE_PUSH_DOCS if (ROOT / name).is_file()}

    for script in sorted((ROOT / "scripts").glob("*_gate.py")):
        rel = f"scripts/{script.name}"
        if rel not in ci:
            out.append(
                f"{rel} exists and `ci.yml` never runs it - a gate with no "
                f"caller is the shape #418 was filed for")
        named_in = [name for name, text in docs.items() if rel in text]
        if not named_in:
            out.append(
                f"{rel} runs in CI and no pre-push document names it "
                f"({', '.join(PRE_PUSH_DOCS)}), so it can only fail after a "
                f"push. #389 already paid for this once")
        stem = script.stem
        exercised = [p for p in sorted((ROOT / "tests").glob("*.py"))
                     if stem in p.read_text(encoding="utf-8")]
        if not exercised:
            out.append(
                f"{rel} is run by CI and by no test, so `pytest -q` is green "
                f"whether it passes or not. Add a test that runs it over this "
                f"repo - four of the five gates already have one")

    # One ruff invocation, everywhere. The scope is the whole argument: `ruff
    # check src tests` let a line sit over the limit in `examples/` while CI
    # reported the repo clean.
    ci_ruff = re.search(r"run:\s*(ruff check [^\n]*)", ci)
    if ci_ruff:
        want = ci_ruff.group(1).strip()
        for name, text in docs.items():
            for found in re.findall(r"ruff check [^\n`]*", text):
                found = found.split("#", 1)[0]
                if found.strip() != want:
                    out.append(
                        f"{name} says `{found.strip()}` and ci.yml runs "
                        f"`{want}`. A narrower local lint is a clean run that "
                        f"says something true about part of the repo and is "
                        f"read as a fact about the repo")
    return out


def main() -> int:
    lines = _workflow_lines()
    problems = (check_uses(lines) + check_pip_installs(lines)
                + check_runtime_versions(lines) + check_uv_lock()
                + check_contributing() + check_gates_are_runnable_locally())
    if problems:
        print("pin gate: FAIL")
        for p in problems:
            print("  " + p)
        print(f"\n{len(problems)} input(s) CI resolves at run time rather than "
              "reads from the repo. An answer that can change with no commit "
              "is a check whose result is not attributable to anything.")
        return 1
    print(f"pin gate: clean ({len(lines)} workflow lines, "
          f"{len(RUNNERS)} registered runner(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
