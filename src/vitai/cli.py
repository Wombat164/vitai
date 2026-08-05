"""vitai CLI: init | build | validate | status | verdicts | goals | infer.

Run from (or point --root at) a content repo produced by `vitai init`.

The CLI is a harness over `vitai.api`, never a second code path (P9): every
command here is a thin rendering of one API method.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .api import Vitai, init, schema
from .jsonl import DataError


def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    if not (root / "data").is_dir():
        sys.exit(f"{root} is not a vitai content repo (no data/ directory). "
                 f"Run `vitai init <path>` first, or pass --root.")
    return root


def cmd_init(args: argparse.Namespace) -> None:
    """Harness over `api.init`: arguments in, refusal translated, two lines out.

    The translation is the only thing here that is not plumbing. `init` raises
    so a library caller can catch; a CLI has to become an exit status.
    """
    try:
        target = init(args.path)
    except FileExistsError as e:
        sys.exit(str(e))
    print(f"Initialised vitai content repo at {target}")
    print("Next: fill profile.md, tune vitai.toml, keep this repo PRIVATE, "
          "then append data lines and run `vitai build`.")

def cmd_build(args: argparse.Namespace) -> None:
    """A harness over `Vitai.load_report()` and `Vitai.build()`."""
    v = Vitai(_root(args))
    report = v.load_report()
    for q in report["quarantined"]:
        print(f"quarantined (malformed, skipped): {q}", file=sys.stderr)
    for w in report["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    on = date.fromisoformat(args.on) if getattr(args, "on", None) else None
    db = v.build(today=on)
    counts = " - ".join(f"{name}: {n}" for name, n in report["counts"].items())
    tail = ""
    if report["quarantined"]:
        tail += (f"; {len(report['quarantined'])} malformed line(s) "
                 "quarantined")
    if report["warnings"]:
        tail += (f"; {len(report['warnings'])} schema warning(s), run "
                 "`vitai validate`")
    print(f"Built {db.name} (incl. verdicts) and weekly.md ({counts}){tail}")

    # THE FAST PATH (G28). The weekly rollup is the right cadence for coaching
    # and the wrong one for danger: something logged on a Tuesday cannot wait
    # until Sunday to be read. Anything urgent dated today prints here, on
    # stderr, the moment the record is rebuilt - before any coaching output
    # exists to bury it.
    if fast := v.safety_banner(on):
        print(fast, file=sys.stderr)
    gates = v.gates(on)
    if gates:
        blocked = sorted({c for g in gates
                          if g.get("status") != "cleared"
                          for c in str(g["restricts"]).split()})
        print(f"GATED today: {', '.join(blocked)} "
              f"({len(gates)} gate(s)) - see `vitai safety`", file=sys.stderr)


def cmd_verdicts(args: argparse.Namespace) -> None:
    """Weekly goal-attainment rows as JSONL - the game/dashboard contract."""
    root = _root(args)
    for row in Vitai(root).verdicts():
        print(json.dumps(row))


def _fmt_deadline(row: dict) -> str:
    """The deadline phrase: a hard date gets a countdown, a soft one does not.

    The wording carries the distinction rather than a label the reader has to
    decode. A hard date is externally owned and the plan is built backwards
    from it, so "12 days to" is the useful framing; a soft date is a direction
    of travel, and counting down to one the athlete invented manufactures an
    urgency nobody asked for (G86).
    """
    when, kind, away = (row.get("deadline"), row.get("deadline_kind"),
                        row.get("days_to_deadline"))
    if not when:
        return ""
    anchor = f" ({row['event']})" if row.get("event") else ""
    if kind == "hard" and away is not None:
        if away < 0:
            return f"{-away} day(s) past {when}{anchor}"
        return f"{away} day(s) to {when}{anchor} - fixed"
    if kind == "soft":
        return f"aiming at {when}{anchor}"
    return f"by {when}{anchor}"


def _fmt_goal(row: dict) -> str:
    """One goal line: what it is, how far in, and when it was last moved."""
    target, counted, pct = row.get("target"), row.get("counted"), row.get("progress_pct")
    if row.get("verification") == "attested":
        # An attested goal has no measure and never will. Rendering it as
        # "0/0" or "0%" would report a goal nothing can score as a goal going
        # badly, which is the opposite of what it is (G86/G83).
        head = "your word is the measure"
    elif row.get("metric") == "external" or row.get("verification") == "external":
        head = f"tracked in {row.get('tracker')}"
    elif counted is None:
        # A goal scoped to a dataset the contribution engine cannot read.
        # Saying "0%" here would report a goal it cannot see as a goal going
        # badly, which is the same error as rendering an attested one at 0%.
        # The scope is named so this reads as a limitation of the engine
        # rather than as a fact about the athlete.
        where = row.get("dataset") or "an unknown source"
        via = " (inferred from the metric)" if row.get("scope") == "inferred" else ""
        # `target` is required on an active measured goal, so it is normally
        # present here - but a paused one need not have it, and formatting a
        # null with :g raises rather than degrading.
        aim = f"target {target:g}" if target is not None else "no target"
        head = (f"{aim} - not scored here; it is tracked in "
                f"{where}{via}, which this engine does not count from")
    elif target is None:
        head = f"{counted:g} logged (no target)"
    else:
        # PER POLARITY (#200). A percentage is the floor's measure; sending a
        # ceiling down the same branch printed "7700/1200" for a breached cap
        # and dropped every field that says so, which reads indistinguishably
        # from a floor doing well.
        polarity = row.get("polarity") or "floor"
        room, breach = row.get("room_left"), row.get("breach")
        if polarity == "ceiling" and room is not None:
            head = (f"{counted:g} against a cap of {target:g}"
                    + (f" - OVER by {abs(room):g}" if breach
                       else f" - {room:g} to spare"))
        elif polarity == "band" and row.get("target_hi") is not None:
            head = (f"{counted:g}, aiming for {target:g} to "
                    f"{row['target_hi']:g}"
                    + (f" - {breach.upper()}" if breach else " - inside"))
        elif polarity == "approach" and row.get("distance") is not None:
            head = (f"{counted:g}, aiming for {target:g} - "
                    f"{row['distance']:g} away")
        else:
            head = f"{counted:g}/{target:g}" + (
                f" ({pct:.0f}%)" if pct is not None else "")
    bits = [f"{row['slug']}: {head}"]
    if row.get("policy") == "guarded" and row.get("unbudgeted"):
        bits.append(f"{row['unbudgeted']:g} unbudgeted")
    if row.get("milestones"):
        bits.append(f"{row['milestones']} milestone(s)")
    if phrase := _fmt_deadline(row):
        bits.append(phrase)
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


def cmd_append(args: argparse.Namespace) -> None:
    """Append a JSON object to a dataset, with the clocks stamped for you.

    Reads JSONL from stdin - one object per line - so it composes with the
    scripts that actually write this record, and so a bulk import is one
    invocation rather than one per row. A single object on its own is the
    same thing with one line.

    The rows written are echoed back, stamps included, so a script can log
    exactly what it committed rather than what it intended to. Nothing is
    written unless every row validates.
    """
    root = _root(args)
    recs = []
    for n, line in enumerate(sys.stdin.read().splitlines(), 1):
        if not (line := line.strip()) or line.startswith("//"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"stdin line {n} is not valid JSON: {e}")
        if not isinstance(rec, dict):
            sys.exit(f"stdin line {n}: expected a JSON object per line")
        recs.append(rec)
    if not recs:
        sys.exit("nothing on stdin - expected one JSON object per line")
    try:
        for row in Vitai(root).append_many(args.dataset, recs):
            print(json.dumps(row))
    except (ValueError, KeyError, DataError) as e:
        sys.exit(str(e).strip("'"))


def cmd_events(args: argparse.Namespace) -> None:
    """Dated real-world fixtures, soonest first - what the plan aims at."""
    root = _root(args)
    on = args.on or date.today().isoformat()
    rows = Vitai(root).events(on)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no events - append lines to data/events.jsonl "
              "(a race, a scan, a wedding: what the plan is built around)")
        return
    for row in rows:
        away = row.get("days_away")
        if away is None:
            when = str(row.get("event_date"))
        elif away < 0:
            when = f"{row.get('event_date')} ({-away} day(s) ago)"
        else:
            when = f"{row.get('event_date')} (in {away} day(s))"
        bits = [f"{row.get('slug')}: {row.get('title')} - {when}"]
        if row.get("kind"):
            bits.append(str(row["kind"]))
        if row.get("priority"):
            bits.append(f"priority {row['priority']}")
        if row.get("immovable"):
            bits.append("fixed date")
        if row.get("status") == "tentative":
            bits.append("not yet confirmed")
        print(" - ".join(bits))


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
    elif text := v.safety_banner(on, every=args.all):
        print(text, end="")
    else:
        print("no active safety escalations")

    gates = v.gates(on)
    if gates and not args.json:
        print("gates in force:")
        for g in gates:
            state = g.get("status") or "blocked"
            verb = {"cleared": "LIFTED today for",
                    "check_not_done": "blocks (check not done)",
                    "blocked": "blocks"}.get(state, "blocks")
            print(f"  [{g['severity'] or 'unset'}] {g['slug']}: {verb} "
                  f"{g['restricts']} - {g['reason']}")
        pending = [g for g in gates if g.get("status") == "check_not_done"]
        if pending:
            print("\nchecks not done today:")
            for g in pending:
                print(f"  {g['precondition']} - until it is recorded, "
                      f"{g['restricts']} stays gated")
    elif gates:
        for g in gates:
            print(json.dumps({"kind": "gate", **g}))

    if any(r["level"] in ("emergency", "urgent") for r in rows):
        raise SystemExit(2)


def cmd_artifact(args: argparse.Namespace) -> None:
    """A harness over the artifact surface. Keep, retrieve and check the
    evidence a value was read from (#80)."""
    v = Vitai(_root(args))

    if args.action == "ls":
        held = v.manifest()
        wanted = [r for r in held.values()
                  if not args.date or r.get("date") == args.date]
        if not wanted:
            print("no artifacts held" + (f" for {args.date}" if args.date else ""))
            return
        for r in sorted(wanted, key=lambda r: str(r.get("date") or "")):
            # `is not None`, not truthiness: an empty artifact is exactly what
            # a truncated capture looks like, and printing it as "size
            # unknown" hides the one number that would say so.
            size = ("size unknown" if r.get("bytes") is None
                    else f"{r['bytes']:,} bytes")
            print(f"{r['sha256'][:19]}...  {r.get('date')}  "
                  f"{r.get('media_type') or '?'}  {size}"
                  + (f"  {r['note']}" if r.get("note") else ""))
        return

    if args.action == "get":
        if not v.is_reference(args.ref):
            sys.exit(f"{args.ref!r} is not a content address. An artifact is "
                     f"addressed by 'sha256:<64 lowercase hex>' and never by "
                     "a path - see `vitai artifact ls`")
        if not args.out:
            sys.exit("`vitai artifact get` needs --out. An artifact is "
                     "personal data, so where it lands is not something this "
                     "command should guess")
        payload = v.artifacts.get(args.ref)
        if payload is None:
            # Answered here rather than pointing at `verify`, which has
            # nothing to say about a hash no row mentions.
            sys.exit(f"{args.ref[:19]}... is not in the store: "
                     + v.why_absent(args.ref))
        Path(args.out).write_bytes(payload)
        print(f"wrote {len(payload):,} bytes to {args.out}")
        return

    findings = v.verify_artifacts()
    held = len(v.manifest())
    if not findings:
        print(f"{held} artifact(s), all present and intact")
        return
    for f in findings:
        print(f"{f['kind'].upper():17} {f['ref'][:19]}...  {f['detail']}")
    # Only a claim the evidence can no longer back is a failure. A deliberate
    # removal, an orphan and a not-yet-cited artifact all get printed and none
    # of them exits non-zero: see FAULTS in artifacts.py for why.
    broken = v.artifact_faults(findings)
    if not broken:
        print(f"{held} artifact(s), all present and intact; "
              f"{len(findings)} note(s) above")
        return
    sys.exit(f"{len(broken)} artifact(s) can no longer back the values citing them")
def cmd_sets(args: argparse.Namespace) -> None:
    """Logged sets (#97) and the reads over them (#100)."""
    v = Vitai(_root(args))
    if getattr(args, "action", "list") != "list":
        _sets_read(v, args)
        return
    rows = v.sets(args.on)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no sets logged" + (f" on {args.on}" if args.on else ""))
        return
    for row in rows:
        print(_set_line(row))


def _sets_read(v: Vitai, args: argparse.Namespace) -> None:
    """The derivations (#100). Half of this is printing refusals."""
    if args.action in ("progression", "working-weight") and not args.exercise:
        sys.exit(f"`vitai sets {args.action}` needs an exercise to be about")

    if args.action == "working-weight":
        got = v.working_weight(args.exercise)
        if got.get("load") is None:
            # `.get`, not `[...]`: every decline carries a reason now, but a
            # KeyError here would take down the verb on the commonest case
            # there is - a bodyweight movement, which has no load figure at
            # all. A missing reason prints as one.
            print(got.get("detail") or "no working weight for this exercise")
            return
        # The failure state travels WITH the number: "80 kg for 8" means
        # something different depending on whether 8 was all there was.
        ended = (f"{got['failure']} failure" if got.get("failure")
                 else "endpoint unstated, so this is not a maximum")
        print(f"{got['exercise']}: {got['load']:g} [{got['scale']}] x "
              f"{got['reps']} on {got['date']} - {ended}")
        _maturity(got.get("sessions", 0))
        return

    if args.action == "progression":
        got = v.set_progression(args.exercise, args.machine)
        for finding in got["findings"]:
            print(f"{finding['kind'].upper()}: {finding['detail']}")
        for point in got["points"]:
            load = f"{point['load']:g} [{point['scale']}]" if point["load"] \
                is not None else point["scale"]
            mark = "" if point["maximal_evidence"] else "  (not a maximum)"
            reps = ("FAILED" if not point["reps_completed"]
                    and (point["reps_attempted"] or 0) else
                    f"{point['reps_completed']} reps")
            print(f"{point['date']}  {load} x {reps}{mark}")
        if got["points"]:
            _maturity(got.get("sessions", 0))
        return

    if args.action == "volume":
        got = v.set_volume(args.on)
        for row in got["by_exercise"]:
            failed = (f", {row['failed_attempts']} failed attempt(s)"
                      if row["failed_attempts"] else "")
            print(f"{row['exercise']}: {row['sets']} sets, "
                  f"{row['reps']} reps{failed}")
        print(f"total: {got['sets']} sets, {got['reps']} reps")
        return

    got = v.set_tonnage(args.on)
    for row in got["by_scale"]:
        basis = "modelled" if "modelled" in row["basis"] else "measured"
        print(f"{row['scale']}: {row['tonnage']:,.0f} over {row['sets']} "
              f"set(s) [{basis}]")
    for finding in got["findings"]:
        print(f"{finding['kind'].upper()}: {finding['detail']}")


def _maturity(sessions: int) -> None:
    """P3/G27: a trend over two sessions does not get a year-of-data voice."""
    if sessions < 3:
        print(f"({sessions} session(s) - too thin to read as a trend)")


def _set_line(row: dict) -> str:
    """One set, said the way the athlete would say it."""
    done = row.get("reps_completed")
    tried = row.get("reps_attempted")
    if Vitai.is_failed_attempt(row):
        # THE case this dataset exists for. "0 reps" reads as nothing
        # happened; a failed attempt is the most informative set in a stack
        # progression and has to read like one.
        reps = "FAILED"
    elif done is not None and tried is not None and tried > done:
        reps = f"{done} of {tried} attempted"
    elif not done and not tried and not row.get("duration_s"):
        # `validate` rejects this row, but rejection does not stop a file
        # loading - so the display path has to be honest about it too, rather
        # than printing "0 reps" and letting it read as a set that happened.
        reps = "nothing recorded"
    elif done is not None:
        reps = f"{done} reps"
    elif row.get("duration_s") is not None:
        reps = f"{row['duration_s']}s"
    else:
        reps = "?"
    load = ""
    if row.get("load") is not None:
        unit = row.get("load_unit") or ("stack" if row.get("load_type")
                                        == "machine_stack" else "kg")
        load = f" @ {row['load']:g} {unit}"
        if row.get("load_type") == "machine_stack":
            # A stack number is not a mass, so it never prints without the
            # machine it is a number about (#60).
            load += f" on {row.get('machine') or 'an unnamed machine'}"
        elif row.get("load_type") == "bodyweight_plus":
            load += " added"
        elif row.get("load_type") == "assisted":
            load += " assistance"
    elif row.get("load_type") == "bodyweight":
        load = " @ bodyweight"
    where = []
    if row.get("block") is not None:
        where.append(f"block {row['block']}")
    if row.get("round") is not None:
        where.append(f"round {row['round']}")
    if row.get("set_index") is not None:
        where.append(f"set {row['set_index']}")
    tail = f" [{', '.join(where)}]" if where else ""
    # UNSTATED prints as unstated. A set that says nothing about how it ended
    # must not read as one taken to failure - that is the defect that turned
    # 13 reps into a maximum it was not.
    ended = (f", {row['failure']} failure" if row.get("failure")
             else ", endpoint unstated")
    effort = ""
    if row.get("rir") is not None:
        effort = f", {row['rir']} in reserve"
    elif row.get("rpe") is not None:
        effort = f", RPE {row['rpe']:g}"
    return (f"{row.get('date')} {row.get('exercise')}: {reps}{load}"
            f"{_config(row)}{ended}{effort}{tail}")


def cmd_meals(args: argparse.Namespace) -> None:
    """Itemised meal estimates (#96): never a bare number."""
    v = Vitai(_root(args))
    meals = v.meals(args.on)
    if args.json:
        for m in meals:
            print(json.dumps(m))
        return
    if not meals:
        print("no meal estimates" + (f" for {args.on}" if args.on else ""))
        return
    for m in meals:
        kcal = m["kcal"]
        # ALWAYS the range, never the midpoint alone. A single number here is
        # the defect the whole dataset exists to prevent.
        head = f"{m['date']} {m['meal']}: {kcal['lo']:.0f}-{kcal['hi']:.0f} kcal"
        if kcal.get("buffer_pct"):
            raw = kcal["unbuffered"]
            head += (f" (incl. the stated +{kcal['buffer_pct']:g}% buffer; "
                     f"{raw['lo']:.0f}-{raw['hi']:.0f} before it)")
        print(head)
        for row in m["items"]:
            span = _item_line(row)
            print(f"  {span}")
        macros = ", ".join(
            f"{m[k]['lo']:.0f}-{m[k]['hi']:.0f} {k[:-2] if k.endswith('_g') else k}"
            for k in ("protein_g", "fat_g", "carb_g"))
        print(f"  macros: {macros}")
        if not kcal["complete"]:
            print(f"  {kcal['unpriced']} item(s) not priced - this total is "
                  "short by however much they were")
        if (d := m["dominant"]) and d["share"] > 0.4:
            print(f"  most of the range is {d['item']}: {d['width']:.0f} of "
                  f"{d['of_total']:.0f} kcal. Settling that one collapses it")
        for q in m["questions"]:
            print(f"  ask: {q['item']} - {q['why']}")
    for row in v.meal_day_disagreements():
        if args.on and row["date"] != args.on:
            continue
        print(row["detail"])


def _item_line(row: dict) -> str:
    grams = Vitai.quantity_range(row)
    energy = Vitai.item_energy(row)
    where = f" [{row['food_table']}]" if row.get("food_table") else ""
    if grams is None:
        return f"{row.get('item')}: quantity unknown{where}"
    # An unbounded estimate must not render identically to a settled one. A
    # point with no range is a GUESS nobody has bounded, and printing
    # "150 g, 195 kcal" the same way a weighed item prints is the bare-number
    # defect this whole dataset exists to prevent, one row down.
    unbounded = row.get("grams_lo") is None or row.get("grams_hi") is None
    span = (f"{grams[0]:.0f}-{grams[2]:.0f} g" if grams[2] > grams[0]
            else f"{grams[1]:.0f} g")
    if unbounded:
        span += " (unbounded)"
    if energy is None:
        return f"{row.get('item')}: {span}, not priced{where}"
    kcal = (f"{energy[0]:.0f}-{energy[2]:.0f}" if energy[2] > energy[0]
            else f"{energy[1]:.0f}")
    return f"{row.get('item')}: {span}, {kcal} kcal{where}"


def _config(row: dict) -> str:
    """How the set was configured (#99), said the way the athlete would.

    A machine-scoped number NEVER prints without its machine - `level 15` on
    its own is the confident wrong answer #60 was filed about, and the
    rendering is where a reader would pick it up.
    """
    axes = Vitai.modifier_axes()

    def number(value: object) -> str:
        # `validate` reports a modifier of the wrong type but does not stop
        # the file loading, so `:g` on a string raised and took down the whole
        # listing. A bool is worse than a crash: `True` formatted as an
        # ordinal prints "level 1", which is a plausible wrong answer.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{value!r} (not a number)"
        return f"{value:g}"

    bits = [str(row[axis]) for axis in axes["categorical"]
            if row.get(axis)]
    if row.get("angle_deg") is not None:
        bits.append(f"{number(row['angle_deg'])} deg")
    for field in axes["machine_scoped"]:
        if row.get(field) is None:
            continue
        where = row.get("machine") or "an unnamed machine"
        bits.append(f"{field.replace('_', ' ')} {number(row[field])} on {where}")
    return f", {', '.join(bits)}" if bits else ""


def cmd_key(args: argparse.Namespace) -> None:
    """Generate a recovery key, or check a phrase against its checksum (#107).

    `check` is the half that matters. The failure mode is not "never wrote it
    down" - it is "believed they wrote it down correctly", and a phrase is
    only a backup once something has confirmed it reads back.
    """
    if args.action == "new":
        key, phrase = Vitai.new_recovery_key()
        print("Write BOTH of these down. They will not be shown again.\n")
        print(f"  phrase (for paper): {phrase}")
        print(f"  key (for a password manager): {key.hex()}\n")
        print("Then run `vitai key check` and type the phrase from the PAPER "
              "copy - not from this screen. A phrase you have not read back "
              "is not a backup, and there is no recovery path by design.")
        return

    # STDIN by default. Passing the phrase as an argument writes the key
    # itself into shell history and shows it in `ps` for the life of the
    # process - which is a poor way to treat a secret in a module whose
    # premise is that nobody else can read it.
    if args.phrase:
        print("note: a phrase given as an argument is now in your shell "
              "history and was visible to other processes. Type it at the "
              "prompt instead next time.", file=sys.stderr)
        typed = " ".join(args.phrase)
    else:
        print("Type the recovery phrase from your paper copy:", file=sys.stderr)
        typed = sys.stdin.readline()
    key, problem = Vitai.key_from_phrase(typed)
    if key is None:
        sys.exit(problem)
    print("this phrase checks out")


def cmd_conform(args: argparse.Namespace) -> None:
    """A harness over `Vitai.conform()`. Runs a contract against an
    implementation (#108).

    The deliverable of the whole layering: a written contract produces
    implementations that mostly work and fail strangely; a suite produces
    implementations that either pass or do not.
    """
    import tempfile

    if not args.transport and not args.custody:
        sys.exit("`vitai conform` needs --transport or --custody")
    at = Path(args.at) if args.at else Path(tempfile.mkdtemp())
    failed = 0
    for kind, spec in (("transport", args.transport),
                       ("custody", args.custody)):
        if not spec:
            continue
        # Two failures, two messages. A name that is neither bundled nor a
        # dotted path is a typo and already says so; wrapping it in "could not
        # construct" printed the spec twice and named the wrong problem. And
        # only CONSTRUCTION is guarded: an error from inside the suite is an
        # implementation defect and deserves its traceback.
        try:
            impl = Vitai.implementation(kind, spec, at)
        except ValueError as e:
            sys.exit(str(e))
        except (ImportError, AttributeError, TypeError) as e:
            sys.exit(f"could not construct {spec!r}: {e}")
        result = Vitai.conform(kind, impl)
        for finding in result["findings"]:
            mark = "ok  " if finding["ok"] else "FAIL"
            print(f"{mark} {kind}: {finding['case']}"
                  + (f" - {finding['detail']}" if finding["detail"] else ""))
        failed += len(result["failures"])
    if failed:
        sys.exit(f"{failed} contract case(s) failed. An implementation that "
                 "does not pass is one the engine cannot use safely, and the "
                 "bundled ones run this same suite with no privileged access")
    print("conformance: clean")


def cmd_route(args: argparse.Namespace) -> None:
    """Tier-1 geometry for a GPS track, with the parameters that produced it."""
    v = Vitai(args.root)
    if not args.gpx and not args.session:
        sys.exit("give a .gpx path or --session <activity_id|date>")
    if args.against:
        verdict, sim = v.same_route(args.gpx, args.against)
        print(f"same route: {'YES' if verdict else 'NO'}  (LCSS similarity "
              f"{sim:.2f})")
        return
    if args.session:
        try:
            s = v.session_route(args.session, barometric=args.barometric)
        except (KeyError, FileNotFoundError) as e:
            sys.exit(str(e).strip("'"))
    else:
        s = v.route(args.gpx, barometric=args.barometric)
    if args.json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(s), default=str))
        return
    if s.suspect:
        # #48: a file spanning eight days is not one activity. Say so before
        # the numbers, not after - the geometry below is still computed, and
        # a reader who has already absorbed it will not un-absorb it.
        print("THIS MAY NOT BE ONE ACTIVITY:")
        for reason in s.suspect:
            print(f"  - {reason}")
        print()
    km = s.distance_m / 1000
    if s.distance_source == "device":
        gap = (f"; ours derives {s.distance_derived_m / 1000:.2f} km, "
               f"{s.distance_disagreement_pct:+.1f}%"
               if s.distance_disagreement_pct is not None else "")
        print(f"{km:.2f} km  (the device's own figure{gap})")
    else:
        print(f"{km:.2f} km  (derived here - no device figure in this file; "
              f"{s.points_used} of {s.points_raw} fixes used after cleaning, "
              f"raw sum would read {s.distance_raw_m / 1000:.2f} km)")
    if s.duration_s:
        mins = s.duration_s / 60
        print(f"{mins:.0f} min" + (f"  ({mins / km:.1f} min/km)" if km else ""))
    print(f"shape: {s.shape}  (retrace similarity {s.retrace_similarity:.2f})")
    print(f"start-end gap {s.start_end_gap_m:.0f} m; furthest "
          f"{s.furthest_m:.0f} m"
          + (f" {v.compass(s.bearing_deg)}" if s.bearing_deg is not None else ""))
    if s.elevation_gain_m is not None:
        print(f"elevation gain {s.elevation_gain_m:.0f} m "
              f"(climbs under {s.params['climb_threshold_m']:.0f} m ignored)")
    print(f"stops: {len(s.stops)}")
    for st in s.stops:
        when = st.start.strftime("%H:%M") if st.start else "?"
        print(f"  {when} for {st.seconds:.0f}s")


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
    """A harness over `Vitai.infer()`. Opt-in intelligence layer: a model
    reads the record, validated new knowledge is appended to
    data/inferences.jsonl. Never touches numbers."""
    engine = Vitai(_root(args))
    try:
        out = engine.infer()
    except ValueError as e:
        sys.exit(str(e))
    for e in out["rejected"]:
        print(f"rejected: {e}", file=sys.stderr)
    if not out["accepted"]:
        sys.exit("no valid inferences produced"
                 + (f" ({len(out['rejected'])} rejected)"
                    if out["rejected"] else ""))
    # ECHOED BEFORE COMMITTED. This ordering is the point of the echo: a
    # script logs exactly what it committed, and rows that landed before
    # anything printed them are rows nobody can reconcile if the rebuild
    # then fails.
    for rec in out["accepted"]:
        print(json.dumps(rec))
    if args.dry_run:
        print(f"(dry run: {len(out['accepted'])} inference(s) NOT appended)",
              file=sys.stderr)
        return
    n = engine.accept_inferences(out["accepted"])
    print(f"appended {n} inference(s) to data/inferences.jsonl "
          "and rebuilt derived/", file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> None:
    """A harness over `Vitai.validate()`. Every rule lives there (#158)."""
    report = Vitai(_root(args)).validate()
    for problem in report["problems"]:
        print(problem)
    # Advisories are NOT problems and never fail the build: they describe rows
    # that are legal but not what new writes should look like. Printed after
    # the errors so a real failure is not buried under housekeeping.
    for advisory in report["advisories"]:
        print(f"ADVISORY: {advisory}")
    if not report["ok"]:
        sys.exit(f"{len(report['problems'])} problem(s). Fix by APPENDING "
                 f"corrections (supersedes), never by editing lines.")
    n = len(report["advisories"])
    print("all data lines valid" + (f" ({n} advisory/advisories)" if n else ""))


def cmd_situation(args: argparse.Namespace) -> None:
    """A harness over `Vitai.situation()`. The whole brief, as JSON.

    JSON and not prose, because the caller is an agent or a client rather than
    a reader: #158's complaint is that the only way to obtain this today is to
    shell out and parse sentences, and printing sentences here would leave
    that exactly where it was.
    """
    # The viewpoint goes to the CONSTRUCTOR as well. Passing it only to
    # `situation()` left every surface that reads `self.on` answering as today
    # inside a brief labelled with another date.
    on = date.fromisoformat(args.on) if args.on else None
    print(json.dumps(Vitai(_root(args), on=on).situation(recent=args.recent),
                     indent=2, sort_keys=True, default=str))
def cmd_mcp(args: argparse.Namespace) -> None:
    """A harness over `vitai.mcp.serve`. Speaks MCP on stdio.

    Nothing is printed here: the protocol owns stdout, and a stray line
    corrupts the stream.
    """
    from .mcp import serve
    sys.exit(serve(_root(args)))


def cmd_claim(args: argparse.Namespace) -> None:
    """A harness over `Vitai.claim()` and `Vitai.said()`.

    Two shapes because there are two acts (#158): a stated quantity, and an
    utterance no quantity can honestly be taken from. Writing nothing for the
    second is what hands the record to whichever tool is willing to write the
    sentence down.
    """
    on = date.fromisoformat(args.on) if args.on else None
    engine = Vitai(_root(args), on=on)
    # Forgetting --dataset used to DISCARD the stated quantities and exit 0:
    # the number the athlete said vanished while the tool reported success,
    # which for an agent driving this is the worst possible shape of failure.
    if args.value and not args.dataset:
        sys.exit(f"{len(args.value)} quantity/quantities given with no "
                 "--dataset to put them in. Add --dataset, or move the "
                 "number into --said if it was only spoken")
    try:
        if args.dataset:
            values = {}
            for pair in args.value:
                if "=" not in pair:
                    sys.exit(f"{pair!r} is not field=value")
                field, _, raw = pair.partition("=")
                try:
                    values[field] = json.loads(raw)
                except json.JSONDecodeError:
                    values[field] = raw
            row = engine.claim(args.dataset, values, said=args.said,
                               read_by=args.read_by, corrects=args.corrects)
        else:
            if not args.said:
                sys.exit("give --said (what was stated), and --dataset with "
                         "field=value pairs if a quantity was stated too")
            row = engine.said(args.said, kind=args.kind, about=args.about)
    except (ValueError, DataError) as e:
        # The engine's own sentence. An agent can relay it; a code would have
        # to be interpreted, and every interpreter would differ.
        sys.exit(str(e))
    except KeyError as e:
        # `KeyError` stringifies with its own quotes, so relaying it verbatim
        # delivered the engine's sentence wearing quotation marks.
        sys.exit(e.args[0] if e.args else str(e))
    print(json.dumps(row, sort_keys=True))


def cmd_status(args: argparse.Namespace) -> None:
    """A harness over `Vitai.status()`.

    This function was #158's named counter-example to P9: it loaded the
    datasets itself, derived the rate and the direction word, and read the
    tripwire count out of `derived/weekly.md` by string prefix. None of that
    existed in the API, so no agent could obtain what this printed without
    reimplementing it - and the copy had DIVERGED, still opening with "no
    weight data yet" on an empty record, which is the weight-first behaviour
    `status_line` was rewritten to remove (G62/G64).
    """
    st = Vitai(_root(args)).status()
    line = st["line"]
    if st["rate_kg_per_week"] is not None:
        trend = (f"{st['direction']} {abs(st['rate_kg_per_week']):.2f} kg/week"
                 if st["rate_kg_per_week"] else "holding steady")
        line += f" - 7d avg {st['mean_kg_7d']:.1f}, {trend}"
    if st["tripwires"] is not None:
        line += f" - tripwires: {st['tripwires'] or 'none'}"
    print(line)
    # Tier 1 (#110): always present, never fires. A disclaimer that interrupts
    # gets dismissed; one that is simply always there gets read once and stays
    # true. This is the artefact carrying the weight, so it goes where the
    # athlete looks most often rather than where it is least in the way.
    print(st["disclaimer"])


def cmd_schema(args: argparse.Namespace) -> None:
    """A harness over `api.schema()`.

    Takes no `--root`, deliberately: the contract and the generations are
    properties of the installed ENGINE and not of anyone's record, and giving
    this a root would invite a reader to think a different repo could answer
    differently.
    """
    shape = schema()
    if args.json:
        print(json.dumps(shape, indent=2, sort_keys=True))
        return
    print(f"engine   {shape['engine']}  (provenance only, never a gate)")
    print(f"contract {shape['contract']}  (the read model a consumer gates on)")
    print("generations:")
    for name in sorted(shape["generations"]):
        gen = shape["generations"][name]
        n = len(shape["fields"].get(name, {}))
        print(f"  {name:<14} {gen}  ({n} fields)")
    # The field TABLE is hundreds of rows and belongs in `--json`, which is
    # what a consumer building a projection reads. Printing the count here so
    # the human surface says the data exists rather than hiding it (#257).
    total = sum(len(v) for v in shape["fields"].values())
    print(f"fields   {total} across {len(shape['fields'])} datasets"
          f"  (types, affinity and container in --json)")


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
        ("situation", cmd_situation,
         "the whole brief as JSON: refusals first, then state, then what is "
         "unresolved (#158)"),
        ("mcp", cmd_mcp,
         "speak MCP on stdio, so an off-the-shelf agent can attach (#158)"),
        ("claim", cmd_claim,
         "append what the athlete stated, with provenance the engine stamps"),
        ("verdicts", cmd_verdicts, "weekly goal-attainment rows as JSONL (the platform contract)"),
        ("goals", cmd_goals, "active goals: progress, dates, contributions, flagged edits"),
        ("append", cmd_append,
         "append JSONL rows from stdin, stamping recorded_at and _gen"),
        ("events", cmd_events,
         "dated fixtures the plan is built backwards from (races, scans, dates)"),
        ("resolve", cmd_resolve, "which source won each contested field, and why"),
        ("safety", cmd_safety, "active escalations and gates (exits 2 if urgent)"),
        ("context", cmd_context, "the situational mode in force on a date"),
        ("check", cmd_check, "adjudicate a stated value against the record"),
        ("day", cmd_day, "everything the record holds for one date"),
        ("window", cmd_window, "totals over the last N calendar days"),
        ("ramp", cmd_ramp, "week-on-week volume, with its base-size caveat"),
        ("artifact", cmd_artifact,
         "keep, retrieve and check the evidence a value was read from"),
        ("route", cmd_route,
         "deterministic geometry for a GPS track (distance, shape, stops)"),
        ("sets", cmd_sets,
         "logged sets, in the order they were performed"),
        ("meals", cmd_meals,
         "itemised meal estimates, with the range and the open questions"),
        ("key", cmd_key,
         "generate a recovery key, or check a phrase you have written down"),
        ("conform", cmd_conform,
         "run the transport or custody contract against an implementation"),
        ("journal", cmd_journal,
         "what the athlete said: claims, worries, ideas, what is still open"),
        ("infer", cmd_infer, "opt-in: model reads the record, appends validated inferences"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=".", help="content repo root (default: cwd)")
        if name == "situation":
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the valid-time viewpoint (default: today)")
            p.add_argument("--recent", type=int, default=14,
                           help="how many recent sessions to carry (default: 14)")
        if name == "claim":
            p.add_argument("--dataset", help="dataset for a stated QUANTITY; "
                                             "omit for an utterance only")
            p.add_argument("--said", help="the athlete's own words, verbatim")
            p.add_argument("--read-by", dest="read_by", default="athlete",
                           help="who read it: athlete, model, human-other")
            p.add_argument("--corrects", metavar="DATE/SOURCE",
                           help="retire the line this names (destructive)")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the date the claim is ABOUT (default: today)")
            p.add_argument("--kind", default="claim",
                           help="utterance kind: claim, worry, idea, "
                                "preference, question, note")
            p.add_argument("--about", help="what the utterance refers to")
            p.add_argument("value", nargs="*", metavar="field=value",
                           help="the quantities stated")
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
        if name == "append":
            p.add_argument("dataset", help="which dataset to append to")
        if name == "key":
            p.add_argument("action", choices=("new", "check"))
            p.add_argument("phrase", nargs="*",
                           help="the phrase to check, as written down")
        if name == "conform":
            p.add_argument("--transport", metavar="IMPL",
                           help="dotted path to a Transport, or 'directory' "
                                "/ 'memory' for the bundled ones")
            p.add_argument("--custody", metavar="IMPL",
                           help="dotted path to a Custody, or 'file' / 'env'")
            p.add_argument("--at", metavar="PATH",
                           help="where a directory transport or file custody "
                                "lives (default: a temporary directory)")
        if name == "sets":
            p.add_argument("action", nargs="?", default="list",
                           choices=("list", "progression", "working-weight",
                                    "volume", "tonnage"))
            p.add_argument("exercise", nargs="?",
                           help="which movement (progression, working-weight)")
            p.add_argument("--machine", help="scope a progression to one machine")
            p.add_argument("--on", metavar="YYYY-MM-DD", help="only this date")
            p.add_argument("--json", action="store_true",
                           help="emit set rows as JSONL instead of prose")
        if name == "meals":
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="only this date")
            p.add_argument("--json", action="store_true",
                           help="emit meal rows as JSONL instead of prose")
        if name == "events":
            p.add_argument("--json", action="store_true",
                           help="emit event rows as JSONL instead of prose")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the day to count down from (default: today)")
        if name == "resolve":
            p.add_argument("--json", action="store_true",
                           help="emit resolution rows as JSONL")
            p.add_argument("--date", metavar="YYYY-MM-DD",
                           help="only this date")
        if name == "artifact":
            p.add_argument("action", choices=("ls", "get", "verify"))
            p.add_argument("ref", nargs="?", help="sha256:<64 hex>")
            # No default on purpose. A default lands personal bytes in
            # whatever directory the command was run from, which for anyone
            # developing vitai is a checkout of this PUBLIC repo. Naming the
            # destination is one word and it is the athlete's decision.
            p.add_argument("--out", metavar="PATH",
                           help="where `get` writes the bytes (required)")
            p.add_argument("--date", metavar="YYYY-MM-DD")
        if name == "route":
            p.add_argument("gpx", nargs="?",
                           help="path to a .gpx track (or use --session)")
            p.add_argument("--session", metavar="REF",
                           help="analyse the track a SESSION names, by "
                                "activity_id or date, resolved from the record")
            p.add_argument("--against", metavar="GPX",
                           help="compare with another track: same route or not")
            p.add_argument("--barometric", action="store_true",
                           help="track came from a barometric altimeter "
                                "(uses the 2 m climb threshold, not 10 m)")
            p.add_argument("--json", action="store_true",
                           help="emit the full stats object as JSON")
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

    # Registered OUTSIDE the loop above, which gives every command a `--root`.
    # This one has none, deliberately: see `cmd_schema`.
    p = sub.add_parser(
        "schema",
        help="the contract version and dataset generations this engine emits")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_schema)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
