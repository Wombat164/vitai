"""vitai CLI: init | build | validate | status.

Run from (or point --root at) a content repo produced by `vitai init`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from importlib import resources
from pathlib import Path
from statistics import mean

from . import __version__
from .config import load_config
from .db import build_db
from .jsonl import DataError, load, read_lines
from .report import build_report
from .schema import KEYS, validate_record

DATASETS = list(KEYS)


def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    if not (root / "data").is_dir():
        sys.exit(f"{root} is not a vitai content repo (no data/ directory). "
                 f"Run `vitai init <path>` first, or pass --root.")
    return root


def cmd_init(args: argparse.Namespace) -> None:
    target = Path(args.path).resolve()
    if target.exists() and any(p.name != ".git" for p in target.iterdir()):
        sys.exit(f"{target} exists and is not empty - refusing to overwrite.")
    target.mkdir(parents=True, exist_ok=True)
    tpl = resources.files("vitai") / "templates"
    for entry in tpl.iterdir():
        with resources.as_file(entry) as src:
            shutil.copy(src, target / entry.name)
    (target / "data").mkdir(exist_ok=True)
    for name in DATASETS:
        (target / "data" / f"{name}.jsonl").touch()
    (target / "derived").mkdir(exist_ok=True)
    print(f"Initialised vitai content repo at {target}")
    print("Next: fill profile.md, tune vitai.toml, keep this repo PRIVATE, "
          "then append data lines and run `vitai build`.")


def _load_all(root: Path) -> dict[str, list[dict]]:
    try:
        return {name: load(root / "data", name) for name in DATASETS}
    except DataError as e:
        sys.exit(f"data error: {e}")


def cmd_build(args: argparse.Namespace) -> None:
    root = _root(args)
    cfg = load_config(root)
    data = _load_all(root)
    warned = 0
    for name in DATASETS:
        for rec in data[name]:
            for p in validate_record(name, rec):
                print(f"warning: {name}.jsonl {rec.get('date')}: {p}", file=sys.stderr)
                warned += 1
    derived = root / "derived"
    db = build_db(derived, data)
    (derived / "weekly.md").write_text(
        build_report(cfg, data["weight"], data["daily"], data["sessions"]),
        encoding="utf-8", newline="\n",
    )
    counts = " - ".join(f"{name}: {len(data[name])}" for name in DATASETS)
    print(f"Built {db.name} and weekly.md ({counts})"
          + (f"; {warned} schema warning(s), run `vitai validate`" if warned else ""))


def cmd_validate(args: argparse.Namespace) -> None:
    root = _root(args)
    problems = 0
    for name in DATASETS:
        path = root / "data" / f"{name}.jsonl"
        try:
            rows = read_lines(path)
        except DataError as e:
            print(f"ERROR: {e}")
            problems += 1
            continue
        for n, rec in rows:
            for p in validate_record(name, rec):
                print(f"{name}.jsonl line {n}: {p}")
                problems += 1
    if problems:
        sys.exit(f"{problems} problem(s). Fix by APPENDING corrections "
                 f"(supersedes), never by editing lines.")
    print("all data lines valid")


def cmd_status(args: argparse.Namespace) -> None:
    root = _root(args)
    data = _load_all(root)
    pts = sorted((w["date"], w["kg"]) for w in data["weight"] if w.get("kg") is not None)
    if not pts:
        print("no weight data yet - weight.jsonl alone still carries the primary goal")
        return
    d, kg = pts[-1]
    line = f"{kg:.1f} kg ({d})"
    if len(pts) >= 8:
        vals = [v for _, v in pts[-7:]]
        prev = [v for _, v in pts[-14:-7]] or vals
        days = (datetime.fromisoformat(pts[-1][0]) - datetime.fromisoformat(pts[-8][0])).days
        if days:
            rate = (mean(prev) - mean(vals)) / days * 7
            line += f" - 7d avg {mean(vals):.1f}, rate {rate:+.2f} kg/week"
    weekly = root / "derived" / "weekly.md"
    if weekly.exists():
        firing = [ln[2:] for ln in weekly.read_text(encoding="utf-8").splitlines()
                  if ln.startswith("- **")]
        line += f" - tripwires: {len(firing) or 'none'}"
    print(line)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="vitai", description=__doc__)
    ap.add_argument("--version", action="version", version=f"vitai {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="stamp a private content repo skeleton")
    p.add_argument("path")
    p.set_defaults(fn=cmd_init)

    for name, fn, help_ in [
        ("build", cmd_build, "data/*.jsonl -> derived/ (SQLite + weekly rollup)"),
        ("validate", cmd_validate, "schema-check every data line"),
        ("status", cmd_status, "one-line state: latest weight, rate, tripwires"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=".", help="content repo root (default: cwd)")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
