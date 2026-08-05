#!/usr/bin/env python3
"""A deterministic lint on what the engine is allowed to depend on.

## Why

Two of CLAUDE.md's non-negotiables are about dependencies, and until now both
were declared and neither was checked:

- **stdlib-only.** The engine ships with an empty `dependencies` list, and the
  promise a reader takes from that is that installing vitai installs nothing
  else. Nothing enforced it. One `import requests` in a module nobody reviews
  closely would have broken the promise silently, and the failure would have
  surfaced at a user's install rather than in CI.
- **The build is network-free** (reworded 2026-08-05, #264). Nothing is fetched
  while a build runs; network exists only in capture-side tools, gated by the
  permission model, and never during a build.

The second is the one with a history. The old rule said "no network" flatly,
which was contradicted by decisions already taken (#84's resolver ladder,
#224's asking channel, G46's gated lookups), so the wording was corrected to
say what was always meant. **A rule that has just been widened is exactly the
rule that needs a check**, because the widening is what creates room to drift
into. #263's rule states it generally: no declared limit without a derivation
or a check, and this is the check for these two.

## What it enforces

**1. Nothing under `src/vitai/` imports a non-stdlib package.**

Membership is `sys.stdlib_module_names`, which is the interpreter's own answer
rather than a hand-maintained list that would go stale at each Python release.
Intra-package imports are resolved and exempt.

**2. Network-capable modules are confined to a named allowlist.**

`urllib`, `socket`, `http` and friends are stdlib, so check 1 waves them
through. They are the whole point of check 2. `subprocess` is on the list too,
and deliberately: shelling out reaches the network as effectively as a socket
does, and the `claude-cli` backend does exactly that.

**3. The build closure cannot reach an allowlisted module.**

This is the check that carries the rule. Confinement alone would let
`inference` be imported by `db` tomorrow, and then a build would be one call
away from a network round-trip with every gate still green. So the closure of
intra-package imports from the build's own entry point is computed, and no
module in it may reach a module holding network capability.

Note what this does and does not prove. Importing `urllib` is not calling it,
so a passing gate is not proof that no build ever opens a socket - that would
need a runtime check. What it proves is that the *capability* is not present in
the build's import closure, which is the structural half, and it is the half
that a refactor breaks silently.

## What it deliberately does not do

**It does not check `tests/` or `scripts/`.** Development dependencies are a
different question with a different answer: CLAUDE.md itself mandates pytest,
and ruff runs in CI. The promise is about what a user installs, so the surface
is what ships.

**It does not ban network capability from the package.** `vitai infer` exists,
it is opt-in behind an `[inference]` section, and fencing it is the design
rather than a compromise with it. The gate records where the fence is so that
moving it is a visible edit.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "vitai"

# The module the build enters through. `db.build` is what `vitai build` calls
# and what the read model is produced by; its closure is the build path.
BUILD_ENTRY = "db"

# Modules that can reach the network, directly or by proxy. `subprocess` is
# here because a shelled-out CLI is a network client wearing a process's
# clothes, which is precisely what the claude-cli backend is.
NETWORK_MODULES = frozenset({
    "asyncio", "ftplib", "http", "imaplib", "poplib", "smtplib", "socket",
    "socketserver", "ssl", "subprocess", "telnetlib", "urllib", "webbrowser",
    "xmlrpc",
})

# A module may hold network capability only with a reason, and the reason is
# read by a human. Adding an entry is the visible edit that moving the fence
# should require.
NETWORK_ALLOW: dict[str, str] = {
    "inference": (
        "vitai infer, the one place the intelligence layer enters through code. "
        "Opt-in behind an [inference] section, output is schema-validated and "
        "append-only, and no verdict, rollup or rate ever reads an inference. "
        "Must stay unreachable from the build closure, which check 3 asserts."
    ),
}


def _module_name(path: Path) -> str:
    return path.stem


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """Return (absolute top-level modules, intra-package modules)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute: set[str] = set()
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `from . import x` names the modules in `names`;
                # `from .x import y` names the module in `module`.
                if node.module:
                    local.add(node.module.split(".")[0])
                else:
                    local.update(a.name for a in node.names)
            elif node.module:
                absolute.add(node.module.split(".")[0])
    return absolute, local


def analyse(
    pkg: Path,
    build_entry: str = BUILD_ENTRY,
    allow: dict[str, str] | None = None,
) -> list[str]:
    """Return the findings for a package tree. Pure: reads files, no exit.

    Split out from `main` so the gate's own rules are testable against a
    synthetic package rather than only against this repo, which passes and so
    exercises none of the failure paths.
    """
    allow = NETWORK_ALLOW if allow is None else allow
    files = sorted(p for p in pkg.rglob("*.py") if "__pycache__" not in p.parts)
    if not files:
        return [f"no modules found under {pkg}"]

    absolute: dict[str, set[str]] = {}
    graph: dict[str, set[str]] = {}
    for path in files:
        name = _module_name(path)
        abs_imports, local_imports = _imports(path)
        absolute[name] = abs_imports
        graph[name] = local_imports

    findings: list[str] = []

    # 1. stdlib only.
    for name in sorted(absolute):
        for mod in sorted(absolute[name]):
            if mod == "vitai" or mod in graph:
                continue
            if mod not in sys.stdlib_module_names:
                findings.append(
                    f"{name}.py imports third-party module {mod!r}; "
                    f"the engine is stdlib-only (CLAUDE.md)"
                )

    # 2. network capability is confined to the allowlist.
    holders: set[str] = set()
    for name in sorted(absolute):
        touched = sorted(absolute[name] & NETWORK_MODULES)
        if not touched:
            continue
        holders.add(name)
        if name not in allow:
            findings.append(
                f"{name}.py imports network-capable {', '.join(touched)}; "
                f"add it to NETWORK_ALLOW with a reason, or move the capability"
            )

    # An allowlist entry that stopped being true is as much a defect as a
    # missing one: it reads as a fence where there is no longer a gate.
    for name in sorted(allow):
        if name not in graph:
            findings.append(
                f"NETWORK_ALLOW names {name!r}, which is not a module in the package"
            )
        elif name not in holders:
            findings.append(
                f"NETWORK_ALLOW names {name!r}, which no longer imports anything "
                f"network-capable; remove the entry so the list keeps meaning something"
            )

    # 3. the build closure reaches no capability holder.
    if build_entry not in graph:
        findings.append(f"build entry {build_entry!r} is not a module in the package")
    else:
        seen: set[str] = set()
        stack = [build_entry]
        while stack:
            current = stack.pop()
            for dep in graph.get(current, ()):
                if dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
        for name in sorted(seen & holders):
            findings.append(
                f"the build closure reaches {name!r}, which holds network capability; "
                f"the build is network-free (CLAUDE.md, #264)"
            )

    return findings


def main() -> int:
    findings = analyse(PKG)
    modules = len([p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts])

    if findings:
        print("dependency gate: FINDINGS", file=sys.stderr)
        for line in findings:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(
        f"dependency gate: clean "
        f"({modules} modules, stdlib-only, "
        f"network capability confined to {', '.join(sorted(NETWORK_ALLOW)) or 'nothing'}, "
        f"build closure offline)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
