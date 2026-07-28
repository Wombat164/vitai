"""vitai CLI: init | build | validate | status.

Run from (or point --root at) a content repo produced by `vitai init`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from statistics import mean

from . import __version__
from .api import Vitai
from .config import load_inference_config
from .inference import append_inferences, backend_from_config, run_inference
from .jsonl import load_report, read_lines
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
    # G26: pin LF on the append-only JSONL so a Windows<->Linux repo does not
    # bury the supersedes audit trail under CRLF phantom diffs. Written here
    # rather than shipped as a template dotfile (packaging globs skip dotfiles).
    (target / ".gitattributes").write_text(
        "* text=auto\n*.jsonl text eol=lf\n*.md text eol=lf\n",
        encoding="utf-8", newline="\n")
    (target / "data").mkdir(exist_ok=True)
    for name in DATASETS:
        (target / "data" / f"{name}.jsonl").touch()
    (target / "derived").mkdir(exist_ok=True)
    print(f"Initialised vitai content repo at {target}")
    print("Next: fill profile.md, tune vitai.toml, keep this repo PRIVATE, "
          "then append data lines and run `vitai build`.")


def _load_all(root: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """Load every dataset, quarantining malformed lines (G26). Returns the
    records plus the list of parse errors that were skipped, so the build
    proceeds from the good rows instead of one bad byte aborting everything."""
    data, quarantined = {}, []
    for name in DATASETS:
        recs, errors = load_report(root / "data", name)
        data[name] = recs
        quarantined += errors
    return data, quarantined


def cmd_build(args: argparse.Namespace) -> None:
    root = _root(args)
    data, quarantined = _load_all(root)
    for q in quarantined:
        print(f"quarantined (malformed, skipped): {q}", file=sys.stderr)
    warned = 0
    for name in DATASETS:
        for rec in data[name]:
            for p in validate_record(name, rec):
                print(f"warning: {name}.jsonl {rec.get('date')}: {p}", file=sys.stderr)
                warned += 1
    db = Vitai(root).build()
    counts = " - ".join(f"{name}: {len(data[name])}" for name in DATASETS)
    tail = ""
    if quarantined:
        tail += f"; {len(quarantined)} malformed line(s) quarantined"
    if warned:
        tail += f"; {warned} schema warning(s), run `vitai validate`"
    print(f"Built {db.name} (incl. verdicts) and weekly.md ({counts}){tail}")


def cmd_verdicts(args: argparse.Namespace) -> None:
    """Weekly goal-attainment rows as JSONL - the game/dashboard contract."""
    root = _root(args)
    for row in Vitai(root).verdicts():
        print(json.dumps(row))


def cmd_infer(args: argparse.Namespace) -> None:
    """Opt-in intelligence layer: a model reads the record, validated new
    knowledge is appended to data/inferences.jsonl. Never touches numbers."""
    root = _root(args)
    inf_cfg = load_inference_config(root)
    if not inf_cfg:
        sys.exit("no [inference] section in vitai.toml - inference is opt-in; "
                 "see the template for claude-cli / openai-compatible examples")
    backend = backend_from_config(inf_cfg)
    v = Vitai(root)
    data = v.datasets()
    valid, errors = run_inference(
        root, backend, v.rollup(), data["daily"], data["sessions"],
        data["inferences"], date.today(),
        max_items=int(inf_cfg.get("max_items", 5)))
    for e in errors:
        print(f"rejected: {e}", file=sys.stderr)
    if not valid:
        sys.exit("no valid inferences produced" + (f" ({len(errors)} rejected)" if errors else ""))
    for rec in valid:
        print(json.dumps(rec))
    if args.dry_run:
        print(f"(dry run: {len(valid)} inference(s) NOT appended)", file=sys.stderr)
        return
    n = append_inferences(root, valid)
    v.build()
    print(f"appended {n} inference(s) to data/inferences.jsonl and rebuilt derived/",
          file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> None:
    root = _root(args)
    problems = 0
    for name in DATASETS:
        path = root / "data" / f"{name}.jsonl"
        rows, parse_errors = read_lines(path)
        for e in parse_errors:  # G26: report EVERY malformed line, not just the first
            print(f"MALFORMED: {e}")
            problems += 1
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
    data, _ = _load_all(root)
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
        ("build", cmd_build, "data/*.jsonl -> derived/ (SQLite incl. verdicts + weekly rollup)"),
        ("validate", cmd_validate, "schema-check every data line"),
        ("status", cmd_status, "one-line state: latest weight, rate, tripwires"),
        ("verdicts", cmd_verdicts, "weekly goal-attainment rows as JSONL (the platform contract)"),
        ("infer", cmd_infer, "opt-in: model reads the record, appends validated inferences"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=".", help="content repo root (default: cwd)")
        if name == "infer":
            p.add_argument("--dry-run", action="store_true",
                           help="print validated inferences without appending")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
