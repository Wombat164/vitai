"""vitai CLI: init | build | validate | status | verdicts | goals | infer.

Run from (or point --root at) a content repo produced by `vitai init`.

The CLI is a harness over `vitai.api`, never a second code path (P9): every
command here is a thin rendering of one API method.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__
from .api import (Vitai, absence, can_emit, init, parse_time, schema,
                  this_build)
from .jsonl import DataError
from .schema import KEYS
from .db import DERIVED_TABLES


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
    elif row.get("observed") is not None:
        # A LEVEL goal (#273). This branch has to come before the `counted is
        # None` one below, because a level goal always has a null `counted` -
        # so without it the primary human surface printed "not scored here"
        # about the very goal the level shape was added to score, which is the
        # P9 half of the fix landing nowhere.
        polarity = row.get("polarity") or "floor"
        room, observed = row.get("room_left"), row["observed"]
        if polarity == "ceiling" and room is not None:
            head = (f"{observed:g}, aiming for {target:g} or under"
                    + (f" - OVER by {abs(room):g}" if row.get("breach")
                       else f" - {room:g} to spare"))
        elif polarity == "floor" and room is not None:
            head = (f"{observed:g}, aiming for {target:g} or over"
                    + (f" - {abs(room):g} to go" if row.get("breach")
                       else f" - {room:g} clear"))
        else:
            head = f"{observed:g}, aiming for {target:g}"
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
    # BOTH NUMBERS, and the bucket one no longer decides whether either shows.
    # `milestones` counts THIS bucket, so a goal with 33 crossed milestones
    # printed nothing here - 0 is falsy - and a goal with 3 printed "3
    # milestone(s)" as if that were the total (#330).
    if row.get("milestones_total"):
        bits.append(f"{row['milestones']} milestone(s) this period, "
                    f"{row['milestones_total']} in all")
    if phrase := _fmt_deadline(row):
        bits.append(phrase)
    dates = f"set {row.get('declared')}"
    if row.get("last_edited") and row["last_edited"] != row.get("declared"):
        dates += f", last moved {row['last_edited']}"
    return f"{' - '.join(bits)}\n    {dates}" + (
        f"\n    why: {row['motivator']}" if row.get("motivator") else "")


def cmd_instruments(args: argparse.Namespace) -> None:
    """Which instrument reported as each origin, on a date."""
    v = Vitai(_root(args))
    if args.origin:
        found = v.instrument(args.origin)
        rows = [found] if found else []
    else:
        rows = v.instruments()
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        # NOT AN ERROR, and the wording matters. An unregistered origin still
        # renders everywhere it did before; the register adds a name to an
        # identity that already works without one.
        who = f"{args.origin!r} is" if args.origin else "no origin is"
        print(f"{who} registered on this date. Readings still carry their "
              f"origin, so nothing is lost - the register adds a name and a "
              f"provenance, and one line is enough to be useful")
        return
    for row in rows:
        span = f"{row.get('from_date')} to {row.get('to_date') or 'now'}"
        made = " ".join(str(row.get(k)) for k in ("maker", "model")
                        if row.get(k))
        label = row.get("name") or row.get("origin")
        print(f"{str(row.get('origin')):<18} {label}"
              f"{'  (' + made + ')' if made else ''}  [{span}]")


def cmd_phases(args: argparse.Namespace) -> None:
    """A harness over `Vitai.phases` (#212)."""
    v = Vitai(_root(args))
    rows = v.phases(dataset=args.dataset, on=args.on)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no row in this record carries a time to place in a day")
        return
    unanchored = [r for r in rows if r["phase"] is None]
    for row in rows:
        # PARSED, NOT SLICED. Taking characters off the end of an
        # offset-aware stamp prints "00+00" rather than a time.
        when = parse_time(row["at"]) if len(str(row["at"])) > 5 else None
        at = f"{when.hour:02d}:{when.minute:02d}" if when else row["at"]
        phase = row["phase"] or "-"
        print(f"{row['date']}  {row['dataset']:<9} {at}  {phase}")
    if unanchored:
        # SAID, NOT LEFT TO BE COUNTED. A consumer that has to notice the
        # dashes is one that will read them as a small number.
        #
        # ONE SENTENCE, because there is one case. A row whose waking cannot
        # be compared with its own time never gets an anchor in the first
        # place - `phases` only reports one it could use - so "no phase" and
        # "no usable waking" are the same set. A second message for the
        # refused case would be a branch nothing can reach, which is worse
        # than a message that is slightly coarse.
        print(f"\n{len(unanchored)} of {len(rows)} have no phase: nothing the "
              f"engine can compare with those times says when the athlete "
              f"woke, and the clock is not an answer to that")


def cmd_capabilities(args: argparse.Namespace) -> None:
    """What each instrument is competent at, as the record states it."""
    v = Vitai(_root(args))
    if args.origin and args.measures:
        rows = [v.capability(args.origin, args.measures,
                             condition=args.condition)]
    else:
        rows = v.capabilities()
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no instrument has a stated capability - every one answers "
              "'unknown', which is not a gap in the engine but a gap in the "
              "record, and it is the honest answer until somebody says "
              "otherwise")
        return
    for row in rows:
        scope = f" ({row['condition']})" if row.get("condition") else ""
        line = (f"{row.get('origin')}: {row.get('measures')}{scope}"
                f" - {row.get('competence')}")
        if row.get("basis"):
            line += f", by {row['basis']}"
        print(line)
        if row.get("construct"):
            print(f"    actually measures: {row['construct']}")
        if row.get("note"):
            print(f"    {row['note']}")


def cmd_comparability(args: argparse.Namespace) -> None:
    """Are these two instruments on the same footing for this field? (#33)"""
    v = Vitai(_root(args))
    if not (args.field and args.origin_a and args.origin_b):
        sys.exit("comparability needs --field, --origin-a and --origin-b: a "
                 "comparability question is always about one field and a "
                 "pair of instruments, never asked of all of them at once")
    row = v.comparability(args.field, args.origin_a, args.origin_b)
    if args.json:
        print(json.dumps(row))
        return
    print(f"{args.origin_a} vs {args.origin_b}, {args.field}: {row['status']}")
    if row.get("bias") is not None:
        print(f"    offset: {row['bias']}")
    if row.get("spread") is not None:
        print(f"    spread: {row['spread']}")
    if row.get("basis"):
        print(f"    basis: {row['basis']}")
    if row.get("overlap_ref"):
        print(f"    overlap: {row['overlap_ref']}")
    if row.get("note"):
        print(f"    {row['note']}")


def cmd_milestones(args: argparse.Namespace) -> None:
    """Every milestone rung a goal has this period, passed or not."""
    rows = Vitai(_root(args)).milestone_ladder(slug=args.slug)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no goal has a milestone ladder - one needs a live floor goal "
              "with a target, scored by this engine. Caps, approaches, daily "
              "buckets, finished or abandoned goals, and anything the engine "
              "does not score (weight-based, or verified somewhere else) have "
              "no rungs")
        return
    for goal in sorted({r["goal"] for r in rows}):
        rungs = [r for r in rows if r["goal"] == goal]
        print(f"{goal}  (period {rungs[0]['period']})")
        for r in rungs:
            mark = "x" if r["passed"] else (">" if r["next"] else " ")
            when = f"  passed {r['passed_on']}" if r["passed"] else ""
            print(f"  [{mark}] {r['fraction']:.0%} of {r['target']:g}"
                  f" = {r['value']:g}{when}")


def cmd_crossings(args: argparse.Namespace) -> None:
    """Round-number, personal-first and band milestones: no goal required
    (#370)."""
    rows = Vitai(_root(args)).crossings()
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no crossings - the record has fewer than two weight readings, "
              "or none of them cross a multiple of 5 kg, cross a "
              "population-reference boundary, or set a new personal high "
              "or low")
        return
    for r in rows:
        # TWO SENTENCE SHAPES, because one template said the wrong thing
        # about one of them. Every row carries a `previous_value` and a
        # `previous_date`, and they mean different things depending on
        # `kind`: on a personal first it is the record this reading beat, and
        # on a round number OR a band crossing it is the last time the series
        # was on the side it just arrived at - `band` reuses `round_number`'s
        # sentence rather than getting a third one, because its evidence pair
        # means exactly the same thing (`crossings._last_on_destination_side`
        # backs both).
        #
        # Printed as one "(was X on DATE)" they read alike, and the round
        # number reads as its own opposite: "down to 80 (was 75)" looks like a
        # five-kilo gain, when 75 is the last reading BELOW 80 and the fact
        # being reported is that the athlete is under 80 for the first time
        # since then. This is the sentence the whole feature exists to make
        # sayable - "first below 80 since February" - so it is worth saying in
        # those words rather than leaving a reader to reconstruct it.
        #
        # A `band` ROW'S `value` IS A NUMBER, NEVER A NAME - the ruling this
        # function must never route around (`docs/medical-boundary.md`,
        # `crossings.py`'s "THE BAND CROSSING"). This branch prints the
        # boundary exactly the way it prints a round-number rung: as a bare
        # figure beside `metric`, "first bmi below 30 since <date>" - a bound
        # stated as a bound, class (a), with no category word anywhere in the
        # template for one to hide in. `tests/test_crossings.py` renders this
        # sentence over the whole persona corpus and fails if one ever does.
        side = "below" if r["direction"] == "down" else "above"
        if r["kind"] in ("round_number", "band"):
            if r["previous_date"] is None:
                said = (f"{r['metric']} {side} {r['value']:g} for the first "
                        f"time in this record")
            else:
                said = (f"first {r['metric']} {side} {r['value']:g} since "
                        f"{r['previous_date']}")
        else:
            arrow = "low" if r["direction"] == "down" else "high"
            was = (f", beating {r['previous_value']:g} on {r['previous_date']}"
                   if r["previous_date"] is not None else "")
            said = f"{r['metric']} {arrow} of {r['value']:g}{was}"
        print(f"{r['date']}  {r['kind']:<14}  {said}")


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


def cmd_pin_policy(args: argparse.Namespace) -> None:
    """Give the toml's thresholds the dated history the data already has (#148).

    `as_of` reconstructs the record at an instant by filtering on
    `recorded_at`, which is right for everything the record holds. Thresholds
    live in `vitai.toml`, outside it: a week with no dated row is judged by
    whatever the file says today, so editing a floor in September re-judges
    every earlier week that lacked one - silently, and including reconstructions.

    `--dry-run` lists the keys that have no dated row ANYWHERE and writes
    nothing. Without it, one row per key is appended, dated the record's own
    horizon.

    IT PROTECTS NOTHING ALREADY JUDGED. A weekly verdict takes the policy in
    force at its Monday and the row is dated the last day the record has, so
    protection starts the Monday after: on the day you pin, zero already-judged
    weeks are covered. The past cannot be pinned and must not be - the toml has
    no history, which is the defect, and writing one from its present state
    would bury it under a fabrication that reads exactly like a record.

    `situation`'s `undated_policy` answers the neighbouring question - what has
    no policy in force AT A VIEWPOINT - which stays true for the weeks before a
    pin however often you run this.
    """
    v = Vitai(_root(args))
    pending = v.never_dated_policy()
    if not pending:
        print("every configured threshold already has a dated row.")
        return
    if args.dry_run:
        for key, value in sorted(pending.items()):
            print(f"{key} = {value}   (no dated row; judged by vitai.toml today)")
        print(f"\n{len(pending)} key(s). Run without --dry-run to pin them "
              f"from {v.on.isoformat()}.")
        return
    for row in v.pin_policy(reason=args.reason):
        print(json.dumps(row))


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


def cmd_derived(args: argparse.Namespace) -> None:
    """A harness over `Vitai.derived()`. One derived table's rows (#267).

    The same shape as `dataset`, deliberately: #267 asked for a public read
    path for `best_efforts` and said it should follow the convention already
    being established rather than invent a second one.

    Keyed by the name the CONTRACT gives the table, because that is the name a
    consumer has. Several of these were reachable only under another - and
    `best_efforts` under none at all, which left a private attribute, a direct
    query against the table this contract exists to insulate consumers from,
    or re-parsing the tracks.
    """
    v = Vitai(_root(args))
    rows = v.derived(args.table)
    if args.json:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return
    if not rows:
        # An empty derived table is a real answer: nothing in this record
        # produced one. Distinct from a table that does not exist, which the
        # name check above already refused.
        print(f"{args.table}: no rows - nothing in this record produces any")
        return
    print(f"{args.table}: {len(rows)} row(s)")
    # From the ROWS, and with no "N of M" denominator. The declared column
    # inventory lives in `DERIVED_TABLES`, which is engine-side: printing a
    # count against it would have been a fact the CLI could state and an
    # agent could not ask for, which is the #158 asymmetry this command
    # exists to close. The names below are a property of these rows and say
    # so. `vitai schema --json` publishes the declared shape for datasets.
    columns = sorted({c for r in rows for c in r if r[c] is not None})
    print(f"columns carrying a value on at least one row: "
          f"{', '.join(columns)}")
    print("--json for the rows; these are BUILD OUTPUT, rebuilt from the "
          "record every time, never a place to write")


def _as_of(written: str | None) -> datetime | None:
    """The knowledge cutoff, parsed and refused where it cannot be trusted.

    AWARE ONLY, which the constructor already insists on and the reason is
    worth repeating at the edge: a naive cutoff compares against aware stamps
    by guessing a zone, and the guess is the local one, so the same command
    returns a different record on two machines. A bare date is accepted and
    read as the start of that day in UTC, because "what did the record know on
    the 3rd" is the question a person actually asks and refusing it over a
    missing timezone would be pedantry at the wrong moment.
    """
    if not written:
        return None
    text = written.strip()
    if len(text) == 10:
        text += "T00:00:00+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        sys.exit(f"--as-of takes an ISO instant, got {written!r}. A date "
                 "(2030-06-01) is read as the start of that day in UTC")
    if stamp.tzinfo is None:
        sys.exit(f"--as-of {written!r} names no timezone, and a naive cutoff "
                 "compares against aware stamps by guessing one - which makes "
                 "the same command answer differently on two machines. Add an "
                 "offset, or pass a bare date to mean UTC midnight")
    return stamp


def cmd_dataset(args: argparse.Namespace) -> None:
    """A harness over `Vitai.dataset()`. One dataset's live rows (#258).

    The language-agnostic half of the answer. An engine-side consumer calls
    the method; anything else shells out to this rather than reading the
    JSONL and finishing the correction rule itself, which is the path that
    deleted a row and its correction together.

    The default is a SUMMARY and `--json` is the rows, following every other
    read command here. It is deliberately not a rendering of the rows: there
    are nineteen dataset shapes and inventing a line format for each would
    put a lossy view where the record should be. What it reports instead is
    what a consumer checking its own reimplementation needs - how many rows
    survive, over what span, and what was quarantined on the way.
    """
    v = Vitai(_root(args), as_of=_as_of(getattr(args, "as_of", None)))
    rows = v.dataset(args.name)
    if args.json:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        # ON STDERR, so the JSONL stream stays parseable, and on this path as
        # well as the prose one. The consumer #258 is about is a script, and
        # warning only the human reader would have left the quarantine signal
        # exactly where it was never seen.
        if errors := v.load_report()["quarantined"]:
            print(f"NOTE: {len(errors)} unparseable line(s) quarantined "
                  f"somewhere in this record - `vitai validate` names them",
                  file=sys.stderr)
        return
    # Both of these come through doors an agent has too. Reaching into
    # `jsonl.load_report` and `schema.META_KEYS` directly was quicker and it
    # put two facts in the CLI that MCP could not ask for, which is the
    # #158 acceptance criterion failing in the direction nobody checks.
    errors = v.load_report()["quarantined"]
    declared = set(schema()["fields"][args.name])
    if not rows:
        print(f"{args.name}: no live rows")
    else:
        dates = sorted(str(r["date"]) for r in rows if r.get("date"))
        span = f", {dates[0]} to {dates[-1]}" if dates else ""
        print(f"{args.name}: {len(rows)} live row(s){span}")
        # The UNION across rows, counted against the DECLARED shape rather
        # than presented as one. A field one row carries is not a field every
        # row carries, and the engine's own list is the answer to "what may
        # this dataset hold" - reading it off the data would report this
        # record's habits as the schema (#257 publishes the real one).
        carried = {k for r in rows for k in r if r[k] is not None}
        print(f"carrying a value on at least one row "
              f"({len(carried & declared)} of {len(declared)} declared "
              f"fields): {', '.join(sorted(carried & declared))}")
    if errors:
        # Quarantined lines are DROPPED, not raised, so a read proceeds from
        # the good rows. Saying nothing here would let a partial answer read
        # as a complete one. Record-wide rather than per dataset, and worded
        # that way: the loader returns one flat list. Each entry does begin
        # with its file name, so this COULD be split per dataset - but only
        # by parsing a message format nothing contracts, which is a coupling
        # that breaks silently the day the wording changes.
        print(f"NOTE: {len(errors)} unparseable line(s) quarantined somewhere "
              f"in this record - `vitai validate` names them")
    print("--json for the rows, with supersedes already applied; "
          "`vitai schema --json` for the declared shape and types")


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
        # WHAT BECAME OF IT (#139). A fixture whose date has passed and whose
        # outcome nobody recorded says nothing here, which is the honest
        # rendering: unanswered is not "did not happen", and printing a miss
        # for a race nobody has reported on accuses the athlete of skipping
        # something the record simply does not know about.
        if outcome := row.get("outcome"):
            bits.append({"took_place": "took place",
                         "did_not_attend": "did not attend"}.get(
                             str(outcome), str(outcome)))
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
        # `stream` says WHICH OF THE THREE this line is, and `kind` is the
        # row's own. They were one key, and the row won: a tripwire and a
        # retraction both carry `kind`, so `{"kind": "retraction", **row}`
        # relabelled itself out of existence and a consumer could not tell the
        # three streams apart. Added beside rather than instead, because
        # explanations carry no `kind` of their own and something may be
        # reading the one case where the label did survive.
        for row in expl:
            print(json.dumps({"kind": "resolution", **row,
                              "stream": "resolution"}))
        for row in trips:
            print(json.dumps({"kind": "conservation", **row,
                              "stream": "tripwire"}))
        for row in rets:
            print(json.dumps({"kind": "retraction", **row,
                              "stream": "retraction"}))
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


def cmd_corrections(args: argparse.Namespace) -> None:
    """A harness over `Vitai.corrections()`. What each correction did (#143).

    STATES AND DOES NOT CHARACTERISE THE PERSON, and this is the one surface
    in the feature where the engine composes words at all - so it is the one
    that had to be got right and the one that was got wrong first.

    THE COUNT IS PRINTED THE SAME WAY WHATEVER IT IS. The first version wrote
    `[down, 3 in a row down]` above a run of one and `[down]` below it: a
    threshold, with emphasis on the far side of it, which is exactly where a
    number becomes a verdict. The docstring at the time claimed there was no
    threshold. Now every move prints `run N`, N is 1 when it is 1, and the
    only thing that changes across a sequence is the digit.
    """
    rows = Vitai(_root(args)).corrections(args.dataset)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        print("no corrections in this record - nothing has been superseded")
        return
    for row in rows:
        held = ("unknown" if row["lag_days"] is None
                else f"{row['lag_days']:g} day(s)")
        print(f"{row['date']} {row['dataset']} {row['row']} "
              f"corrects {row['corrects']} ({row['target_date']}), "
              f"held {held}")
        for move in row["moved"]:
            print(f"    {move['field']}: {move['was']!r} -> {move['now']!r} "
                  f"[{move['direction']}, run {move['same_direction_run']}]")
        # Only where it did not already appear as a field that moved: the
        # note is usually part of the correction, and printing it twice reads
        # as two facts.
        if row["note"] and not any(m["field"] == "note" for m in row["moved"]):
            print(f"    note: {row['note']}")


def cmd_questions(args: argparse.Namespace) -> None:
    """A harness over `Vitai.questions()`. What the record does not know (#224).

    IT PRINTS A SET, NOT A PROMPT. Every field is a slug, a date or a closed
    vocabulary, and nothing here is phrased as a question to a person - "no
    question may imply a duty" lives in phrasing, so the wording belongs to
    whatever asks. This command says what is open; it does not open a
    conversation.
    """
    rows = Vitai(_root(args)).questions(args.on)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        return
    if not rows:
        # Worded to avoid ending a wrapped line on a bare quoted `planned`:
        # the field-population register measures "read" by looking for the
        # quoted key name in a consumer, and `sessions.planned` is retired -
        # so an accident of line wrapping claimed a reader it does not have.
        print("nothing open - the record holds what it needs for everything "
              "still ahead")
        return
    for row in rows:
        if row["kind"] == "waking":
            # NO `bears_on`: a waking question has one axis, not two - the
            # dataset it would resolve IS what it bears on, already in
            # `about`. Forcing a second copy of the same value into a field
            # meant for a different plan's activity would be padding a shape
            # that does not fit rather than describing the one that does.
            print(f"{row['for_date']} {row['about']}: waking "
                  f"{', '.join(row['resolves'])} (settled by "
                  f"{row['settled_by']})")
            continue
        print(f"{row['for_date']} {row['about']}: {row['kind']} "
              f"{row['subject']} (settled by {row['settled_by']}, bears on "
              f"{row['bears_on']})")


def cmd_project(args: argparse.Namespace) -> None:
    """A harness over `Vitai.project()`. If I do this, what then (#193)?

    STATES AND DOES NOT ADVISE. The purpose sentence covers logging nutrition
    and building training programmes, so a projected intake gets the record
    and nothing further - what it would do to a target the athlete declared,
    and no verdict on whether to. The athlete cannot be expected to feel that
    difference; the boundary is the app's to hold.
    """
    v = Vitai(_root(args))
    values = {}
    for pair in args.values:
        field, _, raw = pair.partition("=")
        if not _:
            sys.exit(f"expected field=number, got {pair!r}")
        try:
            values[field] = float(raw)
        except ValueError:
            sys.exit(f"{raw!r} is not a number - a projection is arithmetic "
                     f"on this record's own quantities")
    try:
        rows = v.project(args.dataset, values, args.on)
    except (KeyError, ValueError) as e:
        sys.exit(str(e))
    if args.json:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return
    if not rows:
        print("nothing declared that this would move - a projection needs a "
              "goal with a daily period on the dataset being projected")
        return
    for row in rows:
        head = (f"{row['slug']}: {row['now']:g} now, "
                f"{row['projected']:g} if you do")
        if row["polarity"] == "ceiling" and row["room_left"] is not None:
            head += (f" - OVER the {row['target']:g} you declared by "
                     f"{abs(row['room_left']):g}" if row["breach"]
                     else f" - {row['room_left']:g} still under "
                          f"the {row['target']:g} you declared")
        elif row["room_left"] is not None:
            head += (f" - {abs(row['room_left']):g} short of the "
                     f"{row['target']:g} you declared" if row["breach"]
                     else f" - past the {row['target']:g} you declared")
        print(head)
    print("A projection, not a record: nothing here has been written down, "
          "and what to do about it is yours.")


def cmd_may(args: argparse.Namespace) -> None:
    """A harness over `Vitai.may()`. May this be done today (#275)?

    NON-ZERO ON ANYTHING BUT `allowed`. A shell that read exit 0 as permission
    would turn "nobody has said" into a green light, which is the whole
    failure this command exists to stop.

    2 for blocked, matching `vitai safety`, and 3 for unknown - separate
    because argparse also exits 2 on a usage error, so a script checking only
    the code could not tell a refusal from a typo'd flag, and the two want
    different handling.
    """
    v = Vitai(_root(args))
    out = v.may(args.activity, args.on)
    if args.json:
        print(json.dumps(out, sort_keys=True))
    elif out["verdict"] == "blocked":
        print(f"{out['activity']}: BLOCKED - {out['reason']}")
        print(f"  matched: {', '.join(out.get('matched', []))} "
              f"(gate: {', '.join(str(g) for g in out['gates'])})")
    elif out["verdict"] == "unknown":
        print(f"{out['activity']}: NOBODY HAS SAID - {out['reason']}")
    else:
        print(f"{out['activity']}: allowed - {out['reason']}")
        print(f"  falls under: {', '.join(out['classes'])}")
    if out["verdict"] != "allowed":
        sys.exit(2 if out["verdict"] == "blocked" else 3)


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
    if s.grade_adjusted is not None:
        g = s.grade_adjusted
        # PRINTED, because a metric the human rendering never shows is one
        # only a reader of `--json` knows exists.
        print(f"grade adjusted {g['adjusted_m'] / 1000:.2f} km "
              f"(x{g['multiplier']:.3f}, {g['basis']})")
        if g["covered_pct"] < 95:
            print(f"  over {g['covered_pct']:.0f}% of the route - the rest "
                  f"carries no elevation or is steeper than the curve covers")
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


def cmd_plan(args: argparse.Namespace) -> None:
    """A harness over `Vitai.plan()`. Every rule lives there (#368).

    A separate command from `claim`, mirroring the separate method: a plan is
    a third act, decided rather than acquired, and `plan` is the one door
    that writes it with its own provenance instead of the acquisition
    vocabulary `claim` stamps.
    """
    on = date.fromisoformat(args.on) if args.on else None
    engine = Vitai(_root(args), on=on)
    values = {}
    for pair in args.value:
        if "=" not in pair:
            sys.exit(f"{pair!r} is not field=value")
        field, _, raw = pair.partition("=")
        try:
            values[field] = json.loads(raw)
        except json.JSONDecodeError:
            values[field] = raw
    try:
        row = engine.plan(values, set_by=args.set_by, corrects=args.corrects)
    except (ValueError, DataError) as e:
        # The engine's own sentence, exactly as `claim` relays it - including
        # the one `claim(dataset="plans", ...)` now raises, naming this
        # command as the way in.
        sys.exit(str(e))
    except KeyError as e:
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
        # THE WORD, NOT THE FIGURE (#185, contract 32). `verdicts` says
        # `answers: direction` on `weight_rate`, the rollup stopped printing
        # the magnitude in #283, and this line went on printing it - which
        # left the engine honouring its own contract on one prose surface and
        # not the other. The mean above keeps its number: contract 32 calls
        # that a magnitude, and the span beside it is what makes it readable.
        trend = (st["direction"] if st["rate_kg_per_week"]
                 else "holding steady")
        # THE SPAN THE MEAN ACTUALLY COVERS, not the one its field is named
        # after (#209). Printing "7d avg" over six weeks of weigh-ins is the
        # mislabel this issue catches a client making, and the CLI was making
        # it from the engine's own field name.
        span = st.get("mean_kg_span_days")
        label = f"{span}d avg" if span else "avg"
        line += (f" - {label} {st['mean_kg_7d']:.1f} "
                 f"({st.get('mean_kg_points')} weigh-ins), {trend}")
    if st["tripwires"] is not None:
        line += f" - tripwires: {st['tripwires'] or 'none'}"
    print(line)
    # Tier 1 (#110): always present, never fires. A disclaimer that interrupts
    # gets dismissed; one that is simply always there gets read once and stays
    # true. This is the artefact carrying the weight, so it goes where the
    # athlete looks most often rather than where it is least in the way.
    print(st["disclaimer"])


def cmd_can_emit(args: argparse.Namespace) -> None:
    """A harness over `api.can_emit` and `api.absence` (#335).

    No `--root`, for `cmd_schema`'s reason: what a build can produce is a
    property of the engine, not of a record.

    It prints BOTH answers because they are different questions and the
    difference is the whole issue. "Can this build emit it" is about an
    install. "What does an absence mean" is about a row, and needs to know
    which build wrote that row - which nothing records, so omitting `--build`
    answers `unknown` rather than quietly answering about the install in front
    of you.
    """
    field, build = args.field, args.build
    verdict = can_emit(field, build)
    means = absence(field, build)
    if args.json:
        # `build` IS NULL WHEN IT WAS NOT ASKED ABOUT. This printed
        # `build or this_build()`, so omitting --build produced
        # {"build": "0.5.0", "absence_means": "unknown"} while asking about
        # 0.5.0 explicitly produced "not_measured" - the same pair, two
        # answers, and the first a false statement about a build the registry
        # covers. The human-readable path said which question it had answered
        # and the machine-readable one, the path a script actually consumes,
        # quietly did not.
        print(json.dumps({"field": field, "build": build,
                          "reading_build": this_build(),
                          "can_emit": verdict, "absence_means": means},
                         indent=2, sort_keys=True))
        return
    who = f"build {build}" if build else f"this build ({this_build()})"
    print(f"{field}: {who} can emit it -> {verdict}")
    if build:
        print(f"an absence on a row written by {build} means -> {means}")
    else:
        print("an absence on a row means -> unknown, until something says "
              "which build wrote that row. Nothing does.")


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
        ("plan", cmd_plan,
         "append what a day was MEANT to be, with the plan's own provenance "
         "(set_by) - not claim's acquisition vocabulary (#368)"),
        ("verdicts", cmd_verdicts, "weekly goal-attainment rows as JSONL (the platform contract)"),
        ("goals", cmd_goals, "active goals: progress, dates, contributions, flagged edits"),
        ("phases", cmd_phases,
         "which part of the athlete's own day each timed row fell in (#212)"),
        ("capabilities", cmd_capabilities,
         "what each instrument is competent at, as the record states it (#171)"),
        ("comparability", cmd_comparability,
         "are two instruments on the same footing for one field, earned by "
         "overlap and never assumed (#33)"),
        ("instruments", cmd_instruments,
         "which instrument reported as each origin, on a date (#311)"),
        ("milestones", cmd_milestones,
         "the milestone rungs a goal has this period, passed and not (#330)"),
        ("crossings", cmd_crossings,
         "round-number and personal-first milestones over the weight "
         "series, no goal required (#370)"),
        ("append", cmd_append,
         "append JSONL rows from stdin, stamping recorded_at and _gen"),
        ("pin-policy", cmd_pin_policy,
         "date the toml's thresholds into the record so history stops moving"),
        ("dataset", cmd_dataset,
         "one dataset's live rows, with supersedes already applied (#258)"),
        ("derived", cmd_derived,
         "one DERIVED table's rows, by the name the contract gives it (#267)"),
        ("events", cmd_events,
         "dated fixtures the plan is built backwards from (races, scans, dates)"),
        ("resolve", cmd_resolve, "which source won each contested field, and why"),
        ("questions", cmd_questions,
         "what the record does not know about what is planned - derived, "
         "never asked (#224)"),
        ("corrections", cmd_corrections,
         "what each correction did: which fields moved, which way, and how "
         "long the record held the old value (#143)"),
        ("safety", cmd_safety, "active escalations and gates (exits 2 if urgent)"),
        ("project", cmd_project,
         "if I do this, what then - a proposed quantity against a declared "
         "target, stated and never written (#193)"),
        ("may", cmd_may,
         "may this activity be done today - blocked, allowed, or nobody has "
         "said (exits 2 unless allowed)"),
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
        if name == "plan":
            p.add_argument("--set-by", dest="set_by", default="athlete",
                           help="who decided: athlete, coach, onboard, derived")
            p.add_argument("--corrects", metavar="SLUG@DATE",
                           help="retire the plan row this names (destructive). "
                                "The date is the plan's own 'date', the day it "
                                "was WRITTEN - not 'for_date'. A plan is the "
                                "one dataset carrying both, and aiming this at "
                                "the wrong one matches nothing and appends "
                                "anyway")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the date the plan is WRITTEN on (default: "
                                "today); the day it is FOR is 'for_date' "
                                "among the field=value pairs, since the two "
                                "are different dates")
            p.add_argument("value", nargs="*", metavar="field=value",
                           help="the plan's fields, e.g. slug=evening-run "
                                "for_date=2026-08-10 activity=run tier=committed")
        if name == "infer":
            p.add_argument("--dry-run", action="store_true",
                           help="print validated inferences without appending")
        if name == "pin-policy":
            p.add_argument("--dry-run", action="store_true",
                           help="list the undated thresholds and write nothing")
            p.add_argument("--reason", default="pinned from vitai.toml",
                           help="why these were dated, recorded on each row")
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
        if name == "instruments":
            p.add_argument("--origin", help="ask about one origin")
            p.add_argument("--json", action="store_true",
                           help="emit rows as JSONL instead of prose")
        if name == "phases":
            p.add_argument("--dataset", help="only weight, or only sessions")
            p.add_argument("--on", help="only this date")
            p.add_argument("--json", action="store_true",
                           help="emit rows as JSONL instead of prose")
        if name == "capabilities":
            p.add_argument("--origin", help="ask about one instrument")
            p.add_argument("--measures", help="and one measurand")
            p.add_argument("--condition", help="under one condition")
            p.add_argument("--json", action="store_true",
                           help="emit rows as JSONL instead of prose")
        if name == "comparability":
            p.add_argument("--field", help="the field the two agree or not on")
            p.add_argument("--origin-a", help="the first instrument")
            p.add_argument("--origin-b", help="the second instrument")
            p.add_argument("--json", action="store_true",
                           help="emit the row as JSON instead of prose")
        if name == "milestones":
            p.add_argument("--slug", help="only this goal")
            p.add_argument("--json", action="store_true",
                           help="emit rungs as JSONL instead of prose")
        if name == "crossings":
            p.add_argument("--json", action="store_true",
                           help="emit crossing rows as JSONL instead of prose")
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
        if name == "questions":
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the day to ask about (default: the record's "
                                "own horizon)")
            p.add_argument("--json", action="store_true",
                           help="emit the open questions as JSONL")
        if name == "corrections":
            p.add_argument("dataset", nargs="?", choices=sorted(KEYS),
                           help="one dataset, or every dataset if omitted")
            p.add_argument("--json", action="store_true")
        if name == "project":
            p.add_argument("dataset", help="the dataset the act belongs to")
            p.add_argument("values", nargs="+", metavar="field=number",
                           help="the proposed quantity, e.g. kcal_in=500")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the day to project against")
            p.add_argument("--json", action="store_true")
        if name == "may":
            p.add_argument("activity",
                           help="a session type or activity class, e.g. walk")
            p.add_argument("--on", metavar="YYYY-MM-DD",
                           help="the day to ask about (default: the record's "
                                "own horizon)")
            p.add_argument("--json", action="store_true",
                           help="emit the verdict as JSON")
        if name == "derived":
            # From the engine's own table list, so a table added to the read
            # model is reachable here the same day rather than whenever
            # somebody remembers to widen a literal.
            p.add_argument("table", choices=sorted(DERIVED_TABLES),
                           help="which derived table to read")
            p.add_argument("--json", action="store_true",
                           help="emit the rows as JSONL")
        if name == "dataset":
            # The choices come from the engine, so an unknown name is refused
            # by argparse with the real list rather than by a KeyError after
            # a root has already been resolved.
            p.add_argument("name", choices=sorted(KEYS),
                           help="which dataset to read")
            p.add_argument("--json", action="store_true",
                           help="emit the live rows as JSONL")
            # `--as-of` and NOT `--on`, which the sibling read commands use.
            # They are different axes and the familiar spelling is the wrong
            # one here: `on` is the valid-time viewpoint, as of what DAY a
            # thing is judged, and this command judges nothing. `as_of` is the
            # transaction-time cutoff - what the record KNEW then - which is
            # the only one a raw-claims read has any use for (#269).
            p.add_argument("--as-of", metavar="INSTANT", dest="as_of",
                           help="knowledge cutoff: what the record KNEW at "
                                "that instant, ignoring everything appended "
                                "since. A bare date means UTC midnight. NOTE "
                                "(#148): thresholds with no dated row still "
                                "fall back to today's vitai.toml, so a "
                                "reconstruction is not yet policy-complete")
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

    # Rootless for the same reason.
    p = sub.add_parser(
        "can-emit",
        help="whether a build can produce a field, and what an absence means")
    p.add_argument("field")
    p.add_argument("--build", default=None,
                   help="the build that WROTE the row; omit to ask about "
                        "the install doing the reading")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_can_emit)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
