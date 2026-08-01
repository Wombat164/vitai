#!/usr/bin/env python3
"""Generate the synthetic persona corpora under `tests/fixtures/personas/`.

Each persona is a deterministic, stdlib-only Python builder (`_gen/<slug>.py`)
that returns a mapping from a repo-relative output path to file content. This
CLI writes that content to disk, or - with `--check` - regenerates it into a
temporary directory and diffs it against what is already committed, so CI can
prove the corpus has not drifted from the code that produced it (the same
mechanism `examples/generate_demo.py` uses for the shipped demo).

    python tests/fixtures/personas/generate.py                    # all personas
    python tests/fixtures/personas/generate.py --slug rachel      # one persona
    python tests/fixtures/personas/generate.py --check            # drift gate

No real person's data is ever in this repo.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _gen  # noqa: E402
from _gen import common  # noqa: E402

# Registry of personas this CLI knows how to build. Adding persona #2 through
# #8 (see .scratch/ARCS.md) means writing `_gen/<slug>.py` with its own
# `build(end) -> dict[str, str]` and adding one line here.
# Auto-discovered: every non-underscore module in _gen/ that exposes a
# build(end) callable is a persona. Adding a persona means adding its module
# (and its committed corpus); this file never needs editing for it.
def _discover() -> dict:
    import importlib
    import pkgutil

    found = {}
    for info in pkgutil.iter_modules(_gen.__path__):
        if info.name.startswith("_") or info.name == "common":
            continue
        mod = importlib.import_module(f"_gen.{info.name}")
        if callable(getattr(mod, "build", None)):
            found[info.name] = mod
    return found


SLUGS = _discover()

# Extensions compared by `--check`: the generated INPUTS. `derived/` is
# gitignored (binary SQLite built by `vitai build`) and is never part of a
# generator's own output, so it is never read here.
_COMPARABLE_SUFFIXES = (".jsonl", ".toml", ".gpx", ".tcx")


def _read_all(root: Path) -> dict[str, str]:
    """Every generated-input file under `root`, keyed by its path relative
    to `root` (posix-style), so it lines up with the keys a builder returns."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in _COMPARABLE_SUFFIXES:
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return out


def _files_for(slug: str, end: date) -> dict[str, str]:
    """A persona's complete generated output: its builder's files plus the
    emitted persona.toml (doctrine versioning), whose span is computed from
    the data rows themselves so the file cannot disagree with the record."""
    mod = SLUGS[slug]
    files = mod.build(end)
    dates = sorted(
        json.loads(line)["date"]
        for rel, text in files.items()
        if rel.startswith("data/") and rel.endswith(".jsonl")
        for line in text.splitlines() if line.strip()
    )
    files["persona.toml"] = common.persona_toml(
        slug, mod.PERSONA_VERSION, mod.SEED, (dates[0], dates[-1]))
    return files


def _write(slug: str, target: Path, end: date) -> None:
    files = _files_for(slug, end)
    for rel_path, text in files.items():
        path = target / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _check(slugs: list[str], end: date) -> int:
    drifted = False
    for slug in slugs:
        want = _files_for(slug, end)
        got = _read_all(HERE / slug)
        keys = set(want) | {k for k in got if k.endswith(_COMPARABLE_SUFFIXES)}
        drift = [k for k in sorted(keys) if want.get(k) != got.get(k)]
        if drift:
            print(f"{slug}: data DRIFTED from the generator: {drift}",
                  file=sys.stderr)
            drifted = True
    if drifted:
        print("run `python tests/fixtures/personas/generate.py` and commit.",
              file=sys.stderr)
        return 1
    print("persona data matches the generator")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default="all",
                    help="persona to build, or 'all' (default: all)")
    ap.add_argument("--end", default="2030-06-30", metavar="YYYY-MM-DD",
                    help="corpus end date (default: 2030-06-30)")
    ap.add_argument("--check", action="store_true",
                    help="diff the generator's output against what is "
                         "committed; exit 1 on drift, write nothing")
    args = ap.parse_args(argv)

    end = date.fromisoformat(args.end)
    if args.slug != "all" and args.slug not in SLUGS:
        print(f"unknown slug {args.slug!r}; one of {sorted(SLUGS)} or 'all'",
              file=sys.stderr)
        return 2
    slugs = sorted(SLUGS) if args.slug == "all" else [args.slug]
    print(common.assert_schema_unmoved())

    if args.check:
        return _check(slugs, end)

    for slug in slugs:
        target = HERE / slug
        _write(slug, target, end)
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
