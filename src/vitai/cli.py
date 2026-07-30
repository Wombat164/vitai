"""vitai CLI: init | build | validate | status | verdicts | goals | infer.

Run from (or point --root at) a content repo produced by `vitai init`.

The CLI is a harness over `vitai.api`, never a second code path (P9): every
command here is a thin rendering of one API method.
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
from .safety import banner
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
    v = Vitai(root)
    on = date.fromisoformat(args.on) if getattr(args, "on", None) else None
    db = v.build(today=on)
    counts = " - ".join(f"{name}: {len(data[name])}" for name in DATASETS)
    tail = ""
    if quarantined:
        tail += f"; {len(quarantined)} malformed line(s) quarantined"
    if warned:
        tail += f"; {warned} schema warning(s), run `vitai validate`"
    print(f"Built {db.name} (incl. verdicts) and weekly.md ({counts}){tail}")

    # THE FAST PATH (G28). The weekly rollup is the right cadence for coaching
    # and the wrong one for danger: something logged on a Tuesday cannot wait
    # until Sunday to be read. Anything urgent dated today prints here, on
    # stderr, the moment the record is rebuilt - before any coaching output
    # exists to bury it.
    if urgent := v.urgent(on):
        print(banner(urgent), file=sys.stderr)
    gates = v.gates(on)
    if gates:
        blocked = sorted({c for g in gates
                          for c in str(g["restricts"]).split()})
        print(f"GATED today: {', '.join(blocked)} "
              f"({len(gates)} gate(s)) - see `vitai safety`", file=sys.stderr)


def cmd_verdicts(args: argparse.Namespace) -> None:
    """Weekly goal-attainment rows as JSONL - the game/dashboard contract."""
    root = _root(args)
    for row in Vitai(root).verdicts():
        print(json.dumps(row))


def _fmt_goal(row: dict) -> str:
    """One goal line: what it is, how far in, and when it was last moved."""
    target, counted, pct = row.get("target"), row.get("counted"), row.get("progress_pct")
    if row.get("metric") == "external":
        head = f"tracked in {row.get('tracker')}"
    elif target is None:
        head = f"{counted:g} logged (no target)"
    else:
        head = f"{counted:g}/{target:g}" + (f" ({pct:.0f}%)" if pct is not None else "")
    bits = [f"{row['slug']}: {head}"]
    if row.get("policy") == "guarded" and row.get("unbudgeted"):
        bits.append(f"{row['unbudgeted']:g} unbudgeted")
    if row.get("milestones"):
        bits.append(f"{row['milestones']} milestone(s)")
    if row.get("deadline"):
        bits.append(f"by {row['deadline']}")
    dates = f"set {row.get('declared')}"
    if row.get("last_edited") and row["last_edited"] != row.get("declared"):
        dates += f", last moved {row['last_edited']}"
    return f"{' - '.join(bits)}\n    {dates}" + (
        f"\n    why: {row['motivator']}" if row.get("motivator") else "")


def cmd_goals(args: argparse.Namespace) -> None:
    """Active goals with progress, dates, and each event's contribution."""
    root = _root(args)
    v = Vitai(root)
    today = date.fromisoformat(args.on) if args.on else None
    rows = v.goals(today=today)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    active = [r for r in rows if r.get("status") == "active"]
    if not active:
        print("no active goals - append lines to data/goals.jsonl "
              "(the vitai-onboard skill writes them)")
        return
    for row in active:
        print(_fmt_goal(row))
    contributions = v.contributions()
    recent = [c for c in contributions[-args.recent:]] if args.recent else []
    if recent:
        print("\nrecent contributions:")
        for c in recent:
            mark = {"advances": "+", "partial": "~", "unbudgeted": "0",
                    "regresses": "-", "neutral": "."}.get(c["contribution"], "?")
            print(f"  {c['date']} {mark} {c['goal']}: {c['metric']}={c['value']:g}"
                  f" counted {c['counted']:g} ({c['contribution']})")
    flagged = [e for e in v.churn(today=today) if e.get("suspicious")]
    if flagged:
        print("\nworth a question:")
        for e in flagged:
            why = e.get("reason") or "no reason given"
            print(f"  {e['date']} {e['slug']} loosened "
                  f"{e['before']:g} -> {e['after']:g} after a miss ({why})")


def cmd_resolve(args: argparse.Namespace) -> None:
    """Show the adjudication: which source won each contested field, and why.

    Deliberately a ROUTINE command rather than an error report (G29). The
    athlete should always be able to ask why the record says what it says.
    """
    root = _root(args)
    res = Vitai(root).resolution()
    expl = res["explanations"]
    trips = res["tripwires"]
    rets = Vitai(root).retractions()
    if args.date:
        expl = [e for e in expl if e["date"] == args.date]
        trips = [t for t in trips if t["date"] == args.date]
        rets = [r for r in rets if r["date"] == args.date]
    if args.json:
        for row in expl:
            print(json.dumps({"kind": "resolution", **row}))
        for row in trips:
            print(json.dumps({"kind": "conservation", **row}))
        for row in rets:
            print(json.dumps({"kind": "retraction", **row}))
        return

    if not expl:
        print("nothing contested - every quantity had a single witness")
    else:
        print(f"resolved {len(expl)} contested field(s):")
        for e in expl:
            mark = "!" if e.get("disagreed") else " "
            print(f" {mark} {e['date']} {e['dataset']}.{e['field']}: "
                  f"{e['chosen_source']}={e['chosen_value']} "
                  f"over {e['over_source']}={e['over_value']}")
            print(f"     {e['reason']}")
    if trips:
        print("\nconservation tripwires (flagged, never auto-fixed):")
        for t in trips:
            print(f"  {t['date']} [{t['severity']}] {t['kind']}: {t['detail']}")
    if rets:
        print("\nretracted:")
        for r in rets:
            arrow = f" (cascaded from {r['cascaded_from']})" if r["cascaded_from"] else ""
            print(f"  {r['date']} {r['kind']} {r['claim_id']}{arrow}: {r['reason']}")


def cmd_safety(args: argparse.Namespace) -> None:
    """The escalation surface. Exits 2 while anything urgent stands.

    A non-zero exit is deliberate: it makes "is this athlete safe to train
    today" answerable by a script, a cron job or a game backend without
    parsing prose. Nothing here is generated - the text is fixed in
    `safety.py` and the same string appears wherever it surfaces.
    """
    root = _root(args)
    v = Vitai(root)
    on = date.fromisoformat(args.on) if args.on else date.today()
    rows = v.safety(on) if args.all else v.urgent(on)
    if args.json:
        for row in rows:
            print(json.dumps(row))
    elif rows:
        print(banner(rows), end="")
    else:
        print("no active safety escalations")

    gates = v.gates(on)
    if gates and not args.json:
        print("gates in force:")
        for g in gates:
            print(f"  [{g['severity'] or 'unset'}] {g['slug']}: blocks "
                  f"{g['restricts']} - {g['reason']}")
    elif gates:
        for g in gates:
            print(json.dumps({"kind": "gate", **g}))

    if any(r["level"] in ("emergency", "urgent") for r in rows):
        raise SystemExit(2)


def cmd_journal(args: argparse.Namespace) -> None:
    """What the athlete said, and what is still open."""
    rows = Vitai(args.root).journal(kind=args.kind, status=args.status,
                                    about=args.about)
    if not rows:
        print("nothing recorded matching that filter")
        return
    for r in rows:
        conf = r.get("confidence")
        firmness = "" if conf is None else f" [{float(conf):.0%} firm]"
        about = f" ({r['about']})" if r.get("about") else ""
        state = r.get("status") or "open"
        print(f"[{' ' if state == 'open' else 'x'}] {r['date']}  "
              f"{r['kind']:<10}{about}{firmness}")
        print(f"      {r['text']}")
    openw = [r for r in rows if (r.get("status") or "open") == "open"
             and r.get("kind") == "worry"]
    if openw:
        print(f"\n{len(openw)} open worry(ies) - these outrank the rate line.")


def cmd_context(args: argparse.Namespace) -> None:
    """The situational mode in force on a date."""
    root = _root(args)
    on = args.on or date.today().isoformat()
    current = Vitai(root).context(on)
    if current is None:
        print(f"no context recorded on or before {on}")
        return
    if args.json:
        print(json.dumps(current))
        return
    bits = [f"{on}: mode={current.get('mode')}"]
    for key in ("place", "facilities"):
        if current.get(key):
            bits.append(f"{key}={current[key]}")
    print(" - ".join(bits) + (f"\n  since {current.get('date')}"
                              if current.get("date") != on else ""))
    if current.get("note"):
        print(f"  {current['note']}")


def cmd_check(args: argparse.Namespace) -> None:
    """Adjudicate a stated value against the record. Exits 1 if REFUTED.

    The exit code exists so a skill can be held to the record mechanically
    rather than on its honour.
    """
    root = _root(args)
    result = Vitai(root).check(args.date, args.metric, args.says,
                               type=args.type, tolerance=args.tolerance)
    if args.json:
        print(json.dumps(result))
    elif result["verdict"] == "NOT-IN-RECORD":
        print(f"NOT-IN-RECORD: nothing recorded for {args.metric}"
              f"{' (' + args.type + ')' if args.type else ''} on {args.date}")
        print("  absence cannot refute a claim - the record simply does not say")
    else:
        total, delta = result["sum"], result["delta"]
        pct = result["delta_pct"]
        head = (f"{result['verdict']}: stated {args.says:g}, "
                f"record sum {total:g}")
        if result["verdict"] == "REFUTED":
            head += f" (delta {delta:+g}" + (f", {pct:+.1f}%)" if pct else ")")
        elif result["matched"] and result["matched"] != "single":
            head += f" - matched {result['matched']}"
        print(head)
        for v in result["values"]:
            label = f"{v['dataset']}" + (f"/{v['type']}" if v["type"] else "")
            print(f"  {label}: {v['value']:g}"
                  + (f" [{v['source']}]" if v.get("source") else ""))
    if result["verdict"] == "REFUTED":
        raise SystemExit(1)


def cmd_day(args: argparse.Namespace) -> None:
    """Everything the record holds for one date."""
    out = Vitai(_root(args)).day(args.date)
    if args.json:
        print(json.dumps(out))
        return
    print(f"# {out['date']}")
    for name, rows in out["datasets"].items():
        print(f"\n## {name}")
        for r in rows:
            fields = {k: v for k, v in sorted(r.items())
                      if v is not None and not k.startswith("_")
                      and k not in ("date",)}
            print("  " + ", ".join(f"{k}={v}" for k, v in fields.items()))
    if out["merged_claims"]:
        print("\n## merged away (not visible in the canonical rows)")
        for c in out["merged_claims"]:
            print(f"  {c['claim_id']} -> {c['merged_into']}")
    if out["gates"]:
        print("\n## gates")
        for g in out["gates"]:
            print(f"  blocks {g['restricts']} - {g['reason']}")


def cmd_window(args: argparse.Namespace) -> None:
    """Totals over the last N calendar days."""
    out = Vitai(_root(args)).window(args.days, on=args.on)
    if args.json:
        print(json.dumps(out))
        return
    print(f"{out['from']} to {out['to']} ({out['days']} calendar days, "
          f"{out['days_logged']} with a daily entry)")
    if not out["by_type"]:
        print("  no sessions in the window")
    for kind, slot in out["by_type"].items():
        bits = [f"{slot['sessions']} session(s)"]
        if slot["distance_km"]:
            bits.append(f"{slot['distance_km']:g} km")
        if slot["duration_s"]:
            bits.append(f"{slot['duration_s'] / 60:.0f} min")
        if slot["kcal"]:
            bits.append(f"{slot['kcal']:g} kcal")
        print(f"  {kind}: " + ", ".join(bits))


def cmd_ramp(args: argparse.Namespace) -> None:
    """Week-on-week volume, with the base-size caveat."""
    out = Vitai(_root(args)).ramp(type=args.type, metric=args.metric)
    if args.json:
        print(json.dumps(out))
        return
    for wk in out["weeks"]:
        change = wk.get("change_pct")
        suffix = f"  ({change:+.1f}%)" if change is not None else ""
        print(f"  {wk['week']}  {wk['value']:g}{suffix}")
    # Printed LAST and always: a ramp % over a thin base is not a trend, and
    # the caveat is the engine's to state rather than the caller's to remember.
    print(f"\n{out['caveat']} [{out['maturity']}]")


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
            # G69, same rule as the rollup: a bare signed rate reads backwards
            # to anyone who has not memorised that positive means losing.
            direction = ("losing" if rate > 0 else
                         "gaining" if rate < 0 else "holding")
            trend = (f"{direction} {abs(rate):.2f} kg/week" if rate
                     else "holding steady")
            line += f" - 7d avg {mean(vals):.1f}, {trend}"
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
        ("goals", cmd_goals, "active goals: progress, dates, contributions, flagged edits"),
        ("resolve", cmd_resolve, "which source won each contested field, and why"),
        ("safety", cmd_safety, "active escalations and gates (exits 2 if urgent)"),
        ("context", cmd_context, "the situational mode in force on a date"),
        ("check", cmd_check, "adjudicate a stated value against the record"),
        ("day", cmd_day, "everything the record holds for one date"),
        ("window", cmd_window, "totals over the last N calendar days"),
        ("ramp", cmd_ramp, "week-on-week volume, with its base-size caveat"),
        ("journal", cmd_journal,
         "what the athlete said: claims, worries, ideas, what is still open"),
        ("infer", cmd_infer, "opt-in: model reads the record, appends validated inferences"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=".", help="content repo root (default: cwd)")
        if name == "infer":
            p.add_argument("--dry-run", action="store_true",
                           help="print validated inferences without appending")
        if name == "check":
            p.add_argument("--date", required=True, metavar="YYYY-MM-DD")
            p.add_argument("--metric", required=True,
                           help="e.g. distance_km, steps, kcal_in")
            p.add_argument("--says", required=True, type=float,
                           help="the value being claimed")
            p.add_argument("--type", help="scope to one session type, e.g. run")
            p.add_argument("--tolerance", type=float,
                           help="override the configured match tolerance")
            p.add_argument("--json", action="store_true")
        if name == "day":
            p.add_argument("--date", required=True, metavar="YYYY-MM-DD")
            p.add_argument("--json", action="store_true")
        if name == "window":
            p.add_argument("--days", type=int, default=7)
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the window's last day (default: latest logged)")
            p.add_argument("--json", action="store_true")
        if name == "ramp":
            p.add_argument("--type", default="run", help="session type")
            p.add_argument("--metric", default="distance_km")
            p.add_argument("--json", action="store_true")
        if name == "build":
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="evaluate gates, escalations and the rollup as "
                                "of this date (default: today)")
        if name == "goals":
            p.add_argument("--json", action="store_true",
                           help="emit goal rows as JSONL instead of prose")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="reconstruct goals as they stood on this date")
            p.add_argument("--recent", type=int, default=10, metavar="N",
                           help="show the last N per-goal contributions (0 = none)")
        if name == "resolve":
            p.add_argument("--json", action="store_true",
                           help="emit resolution rows as JSONL")
            p.add_argument("--date", metavar="YYYY-MM-DD",
                           help="only this date")
        if name == "journal":
            p.add_argument("--kind", default=None,
                           help="claim|worry|idea|preference|question|note")
            p.add_argument("--status", default=None,
                           help="open|resolved|superseded|declined")
            p.add_argument("--about", default=None,
                           help="goal slug, metric or body site")
        if name == "context":
            p.add_argument("--json", action="store_true",
                           help="emit the context line as JSON")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the date to reconstruct (default: today)")
        if name == "safety":
            p.add_argument("--json", action="store_true",
                           help="emit escalations and gates as JSONL")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the date to evaluate (default: today)")
            p.add_argument("--all", action="store_true",
                           help="every escalation in the record, not just "
                                "the ones needing attention now")
        p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
