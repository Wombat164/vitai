"""The weekly rollup: weight trend + rate verdict, training by week, tripwires.

Every threshold comes from vitai.toml (see config.py); an absent threshold
silently disables its section rather than guessing a default. The rollup is
the interface between the engine and the intelligence layer: the LLM judges
on these lines and never recomputes them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from .weeks import week_of
from .clocks import protocol_seam, timing_caveat, weigh_in_timing
from .composition import decompose, endpoints
from .config import Config, phase_rate_for
from .verdicts import open_day_in
from .vocab import session_classes


# Beyond this, two readings are not a week apart and no weekly rate exists
# between them - the engine refuses rather than dividing a five-month drift by
# seven (#68). Twice the nominal window: a fortnight's gap still reads as a
# rate, a month's does not.
MAX_RATE_SPAN_DAYS = 14

# Above this the rate is computed but SAYS it is thin, which is G27's maturity
# signal applied to the line the athlete actually reads.
COLD_SPAN_DAYS = 9


def over_days(observed: int, window: int) -> str:
    """" over 3 of the last 7 days", or "" where the window is complete (#93).

    A MEAN WITH NO STATED POPULATION READS AS A CLAIM ABOUT THE WINDOW. "Steps
    12,000/day avg - floor met" over a week the athlete logged three times is
    a floor met on three days, rendered identically to a floor met on seven -
    and the coverage line below it, saying "daily: 7", actively reinforces the
    wrong reading.

    SILENT WHEN COMPLETE, because a phrase on every line is a phrase nobody
    reads, and the marked minority is legible precisely because the unmarked
    majority is quiet.

    NO THRESHOLD AND NO ADJECTIVE. It does not say "sparse" or "thin" or
    decline below some count: the engine has no published basis for where thin
    begins, and this repo has been bitten twice by cutoffs it invented. It
    states the fraction and stops.
    """
    if observed >= window or observed <= 0:
        return ""
    return f" over {observed} of the last {window} days"


def within_days(rows: list[dict], today: date, days: int,
                field: str) -> list[dict]:
    """Rows carrying `field`, within `days` CALENDAR days of `today` (G30).

    An entry-count slice is not a window. `steps[-7:]` means "the last seven
    rows that happen to have steps", and with three step rows in eighteen
    months that spanned January 2025 to July 2026 and printed as a current
    average (#68). G30 is tagged SHIPPED for calendar-day windows; the fix
    reached the weight rolling average and not the tripwire section.
    """
    first = today - timedelta(days=days - 1)
    out = []
    for r in rows:
        if r.get(field) is None:
            continue
        when = _as_day(r.get("date"))
        if when is not None and first <= when <= today:
            out.append(r)
    return out


def unreadable_dates(rows: list[dict], today: date, field: str) -> int:
    """Rows carrying `field` that no window can see: dated after `today`, or
    unparseable.

    A calendar window silently drops both, and silence is the wrong direction
    for a tripwire. A device with a skewed clock writing tomorrow's date would
    have taken a pain reading out of every window it belongs to, and nobody
    would have known. As-of correctness is kept - a report never reads rows
    dated after its own date - but the fact that rows were skipped is stated.
    """
    return sum(1 for r in rows if r.get(field) is not None
               and ((when := _as_day(r.get("date"))) is None or when > today))


def _as_day(value: object) -> date | None:
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def _rolling(points: list[tuple[str, float]], window: int = 7) -> list[tuple[str, float | None]]:
    """Trailing mean over a CALENDAR-DAY window (G30/G27): each point averages
    values dated within the last `window` days, NOT the last `window` list
    entries. With irregular logging a "7d avg" must mean 7 real days, not 7
    weigh-ins that might span three weeks - otherwise every "the trend, not a
    single point" number is silently mis-scoped."""
    out = []
    dated = [(datetime.fromisoformat(d).date(), v) for d, v in points]
    for d_iso, _ in points:
        d = datetime.fromisoformat(d_iso).date()
        lo = d - timedelta(days=window - 1)
        vals = [v for dd, v in dated if lo <= dd <= d and v is not None]
        out.append((d_iso, mean(vals) if vals else None))
    return out


def _avg_on_or_before(roll: dict[str, float | None], iso: str, target_day: date) -> float | None:
    """The rolling average as of the latest point on/before target_day - so the
    rate compares two calendar-separated windows, not two Nth-from-last entries."""
    best = None
    for d_iso, v in roll.items():
        d = datetime.fromisoformat(d_iso).date()
        if d <= target_day and v is not None:
            if best is None or d > best[0]:
                best = (d, v)
    return best[1] if best else None


def _week_key(d: str) -> str:
    # ONE definition of a week, in `weeks` (#208). It was four copies of the
    # arithmetic and TWO contracts: this one raises on a value that is not a
    # date, `query`'s returns "". `week_of` is the raising half, so nothing
    # about this caller changes.
    return week_of(d)


def build_report(cfg: Config, weight: list[dict], daily: list[dict],
                 sessions: list[dict], today: date | None = None,
                 gates: list[dict] | None = None,
                 escalations: list[dict] | None = None,
                 events: list[dict] | None = None,
                 raw_daily: list[dict] | None = None) -> str:
    today = today or date.today()
    # #186 SECTION 3, "wherever it is shown". The tripwire block does not read
    # the verdict rows - it re-derives its own seven-day figures from `daily` -
    # so the column added to `verdicts` does not reach this page, and an open
    # week rendered exactly like a finished one here after the flag shipped.
    #
    # RAW, for the reason the verdicts use raw: the canonicaliser picks one
    # claim per day, and a watch that calls the day `full` outvotes the app
    # still logging it. The suffix goes on the three alerts built from the same
    # seven-day window and nowhere else - the weight rate is built from the
    # weight ladder, where `coverage` cannot reach it.
    #
    # THE PAIN GATE IS IN THAT SET and was missed on the first pass, for the
    # third time in this issue: the verdict row carried the flag while the
    # alert built from the same window did not, so the page and the table
    # disagreed about one record.
    open_window = open_day_in(within_days(raw_daily if raw_daily is not None
                                          else daily, today, 7, "date"))
    still_open = " (day still open)" if open_window else ""
    gates = gates or []
    escalations = escalations or []
    events = events or []
    # WHAT IS BLOCKING, THEN WHAT FIRED, THEN THE TABLES (#76). Measured on a
    # live record, 83 per cent of this document was one table and everything
    # actionable was in its last thirteen lines - below the fold by a factor of
    # twenty, in a document a reader has been trained by bulk to skim. #40
    # already reasons about this: an alert that fires every day is worse than
    # none because it teaches the reader to skip. Here it is not repetition
    # that trains the skip, it is volume, and the effect is the same.
    head: list[str] = []
    L = ["", "## Weight", ""]

    if weight:
        pts = sorted((w["date"], w["kg"]) for w in weight if w.get("kg") is not None)
        roll = dict(_rolling(pts))
        L += ["| Date | kg | 7d avg |", "|---|---|---|"]
        for d, kg in pts[-14:]:
            r = roll.get(d)
            L.append(f"| {d} | {kg:.1f} | {r:.1f} |" if r else f"| {d} | {kg:.1f} | - |")
        # Rate over a CALENDAR week (G30): compare the rolling avg now against
        # the rolling avg ~7 days ago, not the 8th-from-last entry (which under
        # irregular logging could be a month back).
        last_day = datetime.fromisoformat(pts[-1][0]).date()
        week_ago = last_day - timedelta(days=7)
        v1 = roll[pts[-1][0]]
        v0 = _avg_on_or_before(roll, pts[-1][0], week_ago)
        if v0 is not None and v1 is not None:
            # actual calendar days between the two anchor points (>=1)
            anchor0 = max((datetime.fromisoformat(d).date()
                           for d, v in roll.items()
                           if datetime.fromisoformat(d).date() <= week_ago and v is not None),
                          default=None)
            days = (last_day - anchor0).days if anchor0 else 0
            if days > MAX_RATE_SPAN_DAYS:
                # A span this long is not a weekly rate, it is two readings
                # with a hole between them (#68). The live case printed
                # "gaining 0.28 kg/week" from readings 170 days apart, to an
                # athlete in a cut - who would reasonably conclude the cut
                # had failed. The right output is not a different number, it
                # is a refusal that says why.
                L += ["", f"**Rate:** NOT READABLE - the two readings behind "
                          f"this are {days} days apart, so there is no week "
                          "to compute a weekly rate over.",
                      "", "> Weigh in a few times over a fortnight and this "
                          "line comes back."]
            elif days:
                rate = (v0 - v1) / days * 7
                target = phase_rate_for(cfg, v1)
                # G69: never render a bare signed quantity whose plain reading
                # inverts its meaning. This line showed `+1.10 kg/week` to an
                # athlete who had LOST 1.5 kg, because positive means losing
                # here. For a scale-anxious under-eater that misreading is
                # actively dangerous, so the direction is stated in words and
                # the sign is a detail rather than the message.
                direction = ("losing" if rate > 0 else
                             "gaining" if rate < 0 else "holding")
                # THE WORD, AND NOT THE FIGURE (#185, contract 32). This line
                # printed "losing 0.45 kg/week", and the engine has measured
                # that it cannot stand behind that number: the pre-registered
                # run put the median `u_rate / half-band` at 1.74 and found
                # more than half of scored weeks admit no verdict word at all.
                #
                # `verdicts` says so in a column - `answers: direction` on
                # this metric - and the rollup went on printing two decimal
                # places anyway. A contract the engine's own most-read
                # artifact does not honour is a contract nobody has to.
                #
                # The direction, the target and the verdict all stay. What
                # goes is the one part the measurement cannot support, and
                # G69's reason for putting the direction in words in the first
                # place was that the sign is a detail rather than the message.
                phrase = direction if rate else "holding steady"
                # BACK TO WHAT `v0` ACTUALLY STANDS ON. `v0` is a trailing
                # 7-day mean at `anchor0`, so it reaches up to six days before
                # it - and scoping the window to `anchor0..last` let a seam the
                # rate is literally standing on go unseen. Measured: a protocol
                # change four days before `anchor0` printed "FAST - raise
                # intake", a deficit instruction manufactured entirely by the
                # change, while `compute_verdicts` refused the same week. Two
                # surfaces disagreeing about one record is the defect this
                # whole change is about. The #37 timing check shares the bound
                # and inherits the fix.
                reach = (anchor0 - timedelta(days=6)).isoformat() if anchor0 else ""
                window = [w for w in weight
                          if w.get("kg") is not None
                          and anchor0 and reach <= w["date"] <= pts[-1][0]]
                timing = weigh_in_timing(window)
                # #37: do not print an actionable verdict beside a caveat
                # saying the number is noise. "SLOW - check logging" tells an
                # athlete to cut harder, and if the slowness is an artifact of
                # weighing at 19:00 half the week, that is the engine driving
                # a real deficit off a clock. P3: confidence never launders
                # upward, and a crisp verdict on an unreadable number is
                # exactly that.
                unreadable = (timing["known"] and not timing["unknown"]
                              and timing["drift_kg"] >= abs(rate))
                # The seam is checked FIRST and reported instead, because the
                # two say different things to a reader. "Weigh-in times vary"
                # is a habit to tighten; a protocol change is a boundary the
                # rate simply does not cross, and telling somebody to weigh
                # more consistently would be advice about the wrong thing.
                seam = protocol_seam(window)
                # G27: a thin sample owes doubt. `ramp` already caveats its
                # base size; the rate line - the number actually read every
                # week - did not.
                span = (f" over {days} days" if days != 7 else "")
                if days > COLD_SPAN_DAYS:
                    span += ", a thin sample"
                if seam["seam"]:
                    # NO DIRECTION WORD BESIDE IT, and no target line. Saying
                    # "gaining, and also NOT COMPARABLE" hands the reader the
                    # number's meaning and then withdraws it, which is the
                    # laundering G69 removed from the magnitude. If the rate
                    # cannot be compared, the direction is not a finding
                    # either: it is the protocol change, in words.
                    #
                    # PRINTED WITH OR WITHOUT A TARGET. A record with no phase
                    # configured still deserves to know its trend crossed a
                    # seam - #37's timing caveat already prints unconditionally
                    # and this is the same class of statement.
                    L += ["", "**Rate:** NOT COMPARABLE - the weigh-in "
                              "protocol changed over this window "
                              f"({' then '.join(seam['protocols'])}), so the "
                              "two ends measure different things.",
                          "", "> Weigh in the same way for a fortnight and "
                              "this line comes back."]
                elif target is not None:
                    verdict = ("NOT READABLE - weigh-in times vary too much"
                               if unreadable
                               else "ON TARGET" if abs(rate - target) <= 0.25
                               else "FAST - raise intake" if rate > target
                               else "SLOW - check logging")
                    L += ["", f"**Rate:** {phrase}{span}, against a target of "
                              f"losing {target:.2f} kg/week - **{verdict}**",
                          "", "> Judge on this line, never a single morning."]
                else:
                    L += ["", f"**Rate:** {phrase}{span} "
                              "(no phase targets configured)"]
                # #37: a rate read across weigh-ins taken at different times
                # of day is partly reporting the clock. Body mass swings about
                # a kilogram between morning-fasted and evening, so an
                # unrecorded drift from evening to morning weigh-ins can
                # manufacture a whole week of apparent progress - a fabricated
                # number in the P4 sense, and the caveat IS the payload.
                if caveat := timing_caveat(timing, rate):
                    L += ["", f"> {caveat}"]
    else:
        L.append("_No weight data - and that is a valid way to use this._")

    # G64: an athlete whose only real data is a phone step count had fourteen
    # days of it render precisely nowhere. What someone actually logs is what
    # the rollup should be about.
    step_days = [(d["date"], d["steps"]) for d in daily
                 if d.get("steps") is not None]
    recent = [(r["date"], r["steps"])
              for r in within_days(daily, today, 14, "steps")]
    if step_days:
        L += ["", "## Steps", ""]
        if recent:
            avg = mean(s for _, s in recent)
            best = max(recent, key=lambda p: p[1])
            L += [f"- {avg:,.0f}/day average over the last 14 days "
                  f"({len(recent)} logged)",
                  f"- best day {best[1]:,} on {best[0]}"]
        else:
            # Nothing in the window is a fact worth stating. Averaging
            # whatever rows exist instead - which is what the entry-count
            # slice did - printed a figure spanning January 2025 to July 2026
            # as a current average (#68).
            L.append("- nothing logged in the last 14 days")
        L.append(f"- {len(step_days)} days logged in total")

    # WHAT THE SCALE CANNOT SEE (#46, G36). Derived here and never stored, and
    # mostly a refusal: both figures are arithmetic on a bioimpedance estimate,
    # and the band that decides whether a change is real comes from the row's
    # own `kg_lo`/`body_fat_lo` rather than from a published repeatability
    # figure about somebody else's hardware.
    pair = endpoints(weight)
    if pair and (split := decompose(*pair)):
        L += ["", "## Composition", ""]
        L.append(f"- {split['from']} to {split['to']}: "
                 f"{split['kg_change']:+.1f} kg overall")
        if split["resolvable"]:
            L += [f"- fat {split['fat_change']:+.1f} kg, everything else "
                  f"{split['fat_free_change']:+.1f} kg",
                  f"- {split['fat_share']:.0f}% of the change was fat"]
        elif split["resolvable"] is False:
            L.append("- NOT RESOLVABLE - the two readings' fat-mass ranges "
                     "overlap, so the record cannot say which way fat moved")
        else:
            L.append("- fat and fat-free are not separable: these readings "
                     "carry no range, so nothing here can say whether a "
                     "change this size is real")

    L += ["", "## Training by week", ""]
    # A WEEK OF CYCLING IS NOT A WEEK OF NOTHING (#76). The columns counted
    # running and strength, and every other session still created its week
    # through the defaultdict - so a 20 km ride, a swim and a walk each
    # rendered `| 0.0 | 0 | 0 | - | - |`, identical to a week the athlete did
    # not train at all.
    #
    # Which is why the issue's ask to suppress all-zero rows is not the fix it
    # looks like: on the record it was measured against, most of those rows
    # are weeks somebody trained in a way this table could not describe, and
    # hiding them would delete the evidence rather than the noise. So the
    # table gained a column for everything else, and a row of zeros now means
    # what it says.
    by_week: dict[str, dict] = defaultdict(
        lambda: {"km": 0.0, "runs": 0, "gym": 0, "other": 0, "hr": []})
    for s in sessions:
        w = by_week[_week_key(s["date"])]
        if s.get("type") in ("run", "test"):
            w["km"] += s.get("distance_km") or 0
            w["runs"] += 1
            if s.get("type") == "run" and s.get("avg_hr"):
                w["hr"].append(s["avg_hr"])
        elif "strength" in session_classes(s.get("type")):
            w["gym"] += 1
        else:
            w["other"] += 1
    if by_week:
        # BOUNDED, because a weekly rollup is read weekly. The full series
        # went back seven years on the record this was measured on, 267 rows
        # of which the reader needed the last few.
        shown = sorted(by_week)[-cfg.rollup_weeks:] if cfg.rollup_weeks else sorted(by_week)
        hidden = len(by_week) - len(shown)
        L += ["| Week of | km | Runs | Gym | Other | Avg HR | Easy-cap? |",
              "|---|---|---|---|---|---|---|"]
        for wk in shown:
            v = by_week[wk]
            hr = round(mean(v["hr"])) if v["hr"] else None
            if hr is None or cfg.easy_hr_cap is None:
                flag = "-"
            else:
                flag = "OK" if hr <= cfg.easy_hr_cap else f"OVER +{hr - cfg.easy_hr_cap}"
            L.append(f"| {wk} | {v['km']:.1f} | {v['runs']} | {v['gym']} | "
                     f"{v['other']} | {hr or '-'} | {flag} |")
        if hidden:
            L += ["", f"_{hidden} earlier week(s) not shown._"]
        if cfg.easy_hr_cap is not None:
            # THE CAP IS TODAY'S AND THE RECORD CANNOT DATE IT. It lives in
            # `vitai.toml`, which has no history, so annotating a week with
            # `OVER +2` asserts a comparison that was never made at the time -
            # on the reported record, against a run from seven years earlier.
            # Said once here rather than implied on every row.
            L += ["", f"_Easy-cap compares against the cap configured today "
                      f"({cfg.easy_hr_cap}), which the record cannot date._"]
    else:
        L.append("_No sessions._")

    head += ["", "## Tripwires", ""]
    alerts: list[str] = []
    if cfg.rhr_baseline is not None:
        rhrs = [(r["date"], r["rhr"]) for r in within_days(daily, today, 7, "rhr")]
        if len(rhrs) >= 3:
            recent = mean(v for _, v in rhrs)
            if recent > cfg.rhr_baseline + 5:
                alerts.append(f"**Resting HR {recent:.0f}"
                              f"{over_days(len(rhrs), 7)}** - more than 5 "
                              f"over baseline {cfg.rhr_baseline}{still_open}")
    if cfg.pain_gate is not None:
        # `pain` only. These are CANONICAL rows, so a legacy `hip_pain` line
        # arrives already mapped forward, and the fallback that used to sit
        # here was a second copy of a map that had already run (#126).
        def _pain_of(d: dict):
            return d.get("pain")

        logged = [d for d in daily if _pain_of(d) is not None
                  and _as_day(d.get("date"))]
        painful = [d for d in logged
                   if today - timedelta(days=6) <= _as_day(d["date"]) <= today]
        # NOT `or "hip"` (#126). A row with a score and no site is invalid
        # and reported as such, but it still loads, and defaulting it to the
        # retired field's joint made the prose name a body part the record
        # never did - while the gate beside it said "unspecified site". The
        # same disagreement this issue is about, from the other side.
        scored = [(_pain_of(d), d.get("pain_site") or "unspecified site")
                  for d in painful]
        if scored and max(p for p, _ in scored) > cfg.pain_gate:
            worst, site = max(scored, key=lambda s: s[0])
            alerts.append(f"**Pain {worst}/10 at {site}** - gate fired: "
                          f"no loaded work at that site{still_open}")
        elif not scored and logged:
            # A calendar window is right for "is this current", and wrong as a
            # way to make an unresolved reading disappear. Someone who logs
            # pain only when it happens would have had a 8/10 go silent on day
            # eight with no trace. Say when it last was instead - that is not
            # a current gate, and it does not pretend to be.
            last = max(logged, key=lambda d: _as_day(d["date"]))
            if (score := _pain_of(last)) > cfg.pain_gate:
                ago = (today - _as_day(last["date"])).days
                alerts.append(
                    f"Pain {score}/10 at "
                    f"{last.get('pain_site') or 'unspecified site'} was "
                    # NO SUFFIX. This branch fires only when the seven-day
                    # window is EMPTY, so no open day inside it can be moving
                    # this figure - it reports a reading from before the
                    # window, and marking it would claim a bearing the record
                    # does not have.
                    f"last logged {ago} days ago and nothing since - not a "
                    "current gate, but it was never recorded as resolved")
    if cfg.sleep_floor_h is not None:
        sleeps = [r["sleep_h"] for r in within_days(daily, today, 7, "sleep_h")]
        if sleeps and mean(sleeps) < cfg.sleep_floor_h:
            alerts.append(f"**Sleep {mean(sleeps):.1f}h avg"
                          f"{over_days(len(sleeps), 7)}** - under the "
                          f"{cfg.sleep_floor_h:.0f}h floor{still_open}")
    if cfg.steps_floor is not None:
        steps = [r["steps"] for r in within_days(daily, today, 7, "steps")]
        if steps:
            avg = mean(steps)
            met = avg >= cfg.steps_floor
            verdict = "floor met" if met else f"below the {cfg.steps_floor:,} floor"
            alerts.append(f"Steps {avg:,.0f}/day avg"
                          f"{over_days(len(steps), 7)} - {verdict}{still_open}")
    skipped = sum(unreadable_dates(daily, today, f)
                  for f in ("rhr", "sleep_h", "steps", "pain"))
    if skipped:
        alerts.append(f"{skipped} row(s) carry a date this report cannot read "
                      "or that falls after it - check the source's clock; they "
                      "were not counted above")
    head += [f"- {a}" for a in alerts] or ["- Nothing firing."]

    # Gates outrank tripwires and sit above them in the reader's eye for a
    # reason: a tripwire is something to discuss, a gate is something that is
    # already decided. The coach may explain one; it may not talk one away.
    #
    # THE COMMENT SAID THAT AND THE CODE DID THE OPPOSITE. Gates were emitted
    # after tripwires, so on the shipped demo `## Gates` rendered at line 56
    # and `## Tripwires` at 52. Built into `gate_lines` and spliced in above
    # them now, which is what this paragraph has been claiming.
    gate_lines = ["", "## Gates", ""]
    if gates:
        for g in gates:
            gate_lines.append(f"- **{g['restricts']} blocked** - {g['reason']}")
        gate_lines += ["", "> A gate clears when the record says the episode "
                           "resolved, not by argument."]
    else:
        gate_lines.append("- Nothing gated.")

    safety_lines: list[str] = []
    if escalations:
        safety_lines += ["", "## Safety", ""]
        for e in escalations:
            safety_lines.append(
                f"- **{e['level'].upper()}** {e['date']} - {e['detail']}")
        safety_lines += ["", "> " + escalations[0]["action"]]
    head = safety_lines + gate_lines + head

    # G86: a fixture is what a plan is built backwards FROM, so it belongs in
    # the rollup as a countdown rather than buried in the goal list. Only what
    # is still ahead is shown - a race last March is history, not a plan.
    ahead = [e for e in events
             if (e.get("days_away") is not None and e["days_away"] >= 0)]
    if ahead:
        L += ["", "## Coming up", ""]
        for e in ahead:
            away = e["days_away"]
            when = "today" if away == 0 else f"in {away} day{'s' * (away != 1)}"
            fixed = " - fixed date" if e.get("immovable") else ""
            L.append(f"- **{e.get('title')}** {when} "
                     f"({e.get('event_date')}){fixed}")

    L += ["", "## Coverage", "",
          f"- weight: {len(weight)} - daily: {len(daily)} - sessions: {len(sessions)}",
          "", "> Sparse and continuous beats rich and abandoned."]
    return "\n".join(
        ["# Weekly rollup", "",
         f"Generated {today.isoformat()} - derived, do not edit."]
        + head + L) + "\n"
