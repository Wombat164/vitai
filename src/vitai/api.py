"""vitai as a library: the surface a game backend or dashboard builds on.

One `Vitai` instance wraps ONE user's content repo - the single-user store
is the atom. A multi-user host (a game with thousands of players) holds one
store per user and instantiates this class per request or per sync job:

    coach = Vitai(Path(f"/data/users/{user_id}"))
    coach.build()                      # refresh the read model
    rows = coach.verdicts()            # the game-economy input
    line = coach.status_line()         # one-line state

Scaling notes (see ARCHITECTURE.md "The platform"): per-user stores are
embarrassingly parallel (no shared write state, SQLite-per-tenant), per-user
deletable (GDPR = delete the directory), and the host's own aggregation
(leaderboards, economies) belongs in the HOST's database, built from these
verdicts - never by joining raw health records across users.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .config import Config, load_config
from .contributions import compute_contributions, goal_progress
from .db import build_db
from .clocks import is_aware
from .jsonl import append, append_many, load
from . import query
from .policy import (State, context_on, days_between, events_on, plan_churn,
                     state)
from .report import build_report
from .resolution import live_inferences, resolve, retractions
from .safety import (
    active_episodes, banner, escalations, gates_on, hold_gates, is_gated,
    urgent_now,
)
from .schema import KEYS
from .verdicts import compute_verdicts


class Vitai:
    """Read/derive interface over one user's content repo."""

    def __init__(self, root: Path | str, as_of: datetime | None = None):
        """`as_of` is a KNOWLEDGE CUTOFF, not a date filter.

        Without it the engine answers with everything it knows now. With it,
        the engine answers as it would have on that instant: only lines whose
        `recorded_at` precedes the cutoff are loaded, so a correction, an
        explanation or a backdated context line that arrived later is absent.

        This is the transaction-time question and it is not the one
        `goals_in_force(date)` answers. That asks which goals APPLIED on a
        date using everything known now; this asks what was KNOWN then. A
        month of degraded data whose cause is filed six weeks later reads as
        unexplained under a cutoff inside those six weeks and explained after,
        which is the difference between judging a decision and judging it with
        hindsight.

        Threaded through `dataset()`, so resolution, verdicts, safety and the
        build all inherit it rather than each needing to remember.
        """
        self.root = Path(root)
        self.as_of = as_of
        if as_of is not None and not is_aware(as_of):
            # A naive cutoff compares against aware stamps by guessing a zone,
            # and the guess is the local one, which makes the same call return
            # different records on two machines.
            raise ValueError(
                "as_of must carry an explicit offset: a naive cutoff would be "
                "interpreted in the local zone and give different answers on "
                "different machines")
        if not (self.root / "data").is_dir():
            raise FileNotFoundError(
                f"{self.root} is not a vitai content repo (no data/ directory)")

    @property
    def config(self) -> Config:
        return load_config(self.root)

    def append(self, name: str, record: dict) -> dict:
        """Append one line to a dataset, stamping the machine-owned clocks.

        The WRITE half of P9, and the reason `recorded_at` is trustworthy: a
        field every caller must remember to set is absent exactly when it
        matters. Raises if the caller supplies `recorded_at`, fills missing
        keys with null, stamps `_gen`, and validates before writing - an
        append-only file cannot be un-appended.
        """
        return append(self.root / "data", name, record,
                      device=self.config.device)

    def append_many(self, name: str, records: list[dict]) -> list[dict]:
        """Append many rows in one pass - what a bulk import should call.

        Reads the file once, stamps each row strictly past the one before it,
        validates every row before writing any, and writes in a single open.
        Looping over `append` re-parses a growing file per row.
        """
        return append_many(self.root / "data", name, records,
                           device=self.config.device)

    @property
    def artifacts(self):
        """The content-addressed store behind this record (#80).

        Local directory by default; the backend sits behind an interface
        because where binaries live is an operator decision about a private
        record, not an engine decision.
        """
        from .artifacts import DirectoryStore
        return DirectoryStore(self.root / "artifacts")

    def add_artifact(self, payload: bytes, media_type: str,
                     **fields) -> dict:
        """Store bytes and append their manifest row. Idempotent by content.

        Idempotent against what is HELD, not against every row ever written.
        A previously removed artifact that comes back is a new retention
        decision and gets its own row - reading the tombstone as "already
        there" would put the bytes back on disk while the manifest still said
        deleted, which is the one state the athlete cannot see and did not ask
        for.
        """
        from .artifacts import digest, live_manifest
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(
                "an artifact is bytes - read the file rather than passing its "
                f"name or contents as text (got {type(payload).__name__})")
        payload = bytes(payload)
        ref = digest(payload)
        held = live_manifest(self.dataset("artifacts"))
        if ref in held:
            # Storing again is what repairs a lost or corrupted artifact, so
            # it happens even when the row is already there. `put` is by
            # content, so this cannot write the wrong bytes to an address.
            self.artifacts.put(payload)
            return held[ref]
        # The row is appended BEFORE the bytes land, so a manifest row that
        # fails validation cannot leave personal bytes on disk that nothing in
        # the record points at. The reverse order fails towards an invisible
        # orphan; this order fails towards a `missing` finding that says so and
        # that adding the same artifact again repairs.
        row = self.append("artifacts", {
            "sha256": ref, "media_type": media_type,
            "bytes": len(payload), **fields})
        self.artifacts.put(payload)
        return row

    def remove_artifact(self, ref: str, reason: str,
                        on: date | str | None = None) -> dict:
        """TOMBSTONE the manifest row and drop the bytes.

        The citing observation is left alone: it is append-only, and
        rewriting it would lose the fact that a value once had evidence. The
        tombstone is what makes "the athlete deleted this" readable as a
        retention decision rather than as data loss.

        In that order. Dropping first and appending second means a tombstone
        that fails validation - a bad date, a missing reason - leaves the bytes
        gone with nothing recording why, and the record then reports permanent
        data loss for what was a deliberate deletion. Recording the decision
        first is recoverable; destroying the evidence first is not.
        """
        when = on.isoformat() if isinstance(on, date) else (
            on or date.today().isoformat())
        row = self.append("artifacts", {"date": when, "sha256": ref,
                                        "removed": True, "reason": reason})
        self.artifacts.drop(ref)
        return row

    def verify_artifacts(self) -> list[dict]:
        """Fixity and referential integrity, in both directions."""
        from .artifacts import verify
        return verify(self.artifacts, self.datasets())

    def dataset(self, name: str) -> list[dict]:
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        return load(self.root / "data", name, as_of=self.as_of)

    def datasets(self) -> dict[str, list[dict]]:
        """Raw claims, exactly as recorded. See `canonical()` for adjudicated."""
        return {name: self.dataset(name) for name in KEYS}

    def _converged(self) -> dict[str, list[dict]]:
        """Datasets with duplicate CAPTURES resolved to one row each (#105).

        Dedupe happens HERE, at build, rather than at write. A device that was
        offline still converges, because the resolution runs over whatever
        files are present whenever they arrive - and deduping at write would
        need the writer to have seen the other device's file, which is exactly
        the coupling actor-per-file exists to remove.

        The RECORD is untouched: `dataset()` still returns every line, because
        an append-only file cannot un-append and both rows are legitimate
        writes. Only the derived numbers converge, which is the point - a
        session captured on the laptop and again on the phone would otherwise
        double its distance in every figure downstream.
        """
        from .devices import deduplicate
        return {name: deduplicate(self.dataset(name), name)[0] for name in KEYS}

    def resolution(self) -> dict:
        """Run the resolution layer: canonical rows plus the audit trail.

        Everything the engine judges on comes from here, not from
        `datasets()` - a verdict computed over unresolved claims would double
        count every day the athlete happens to own two devices.
        """
        cfg = self.config
        return resolve(self._converged(), precedence=cfg.precedence,
                       source_order=cfg.source_order)

    def canonical(self, name: str | None = None):
        """Adjudicated rows: one canonical record per quantity per date."""
        resolved = self.resolution()["canonical"]
        if name is None:
            return resolved
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        return resolved[name]

    def provenance(self) -> list[dict]:
        """Per resolved row: how many INDEPENDENT instruments observed it,
        and what its journey could have done to it (#35/#51)."""
        return self.resolution()["provenance"]

    def sets(self, on: str | None = None) -> list[dict]:
        """Logged sets, in the order they were performed (#97).

        Ordered by (date, session_start, block, round, set_index) rather than
        by file position, because the order sets were PERFORMED in is the
        whole content of a block: 13, 12, 10 is a fatigue curve and 10, 12, 13
        is a warm-up. A row missing a counter sorts last within its group
        rather than first - an unnumbered set is one nobody placed, and
        placing it at the front would invent a claim about when it happened.
        """
        rows = [r for r in self.dataset("sets") if not on or r.get("date") == on]

        def where(r: dict) -> tuple:
            # Everything sorts LAST when unstated, including `session_start`:
            # a set nobody placed in a session did not therefore happen first,
            # and putting it at the front invents a claim about when it did.
            #
            # Counters are coerced through a (is_number, value) pair rather
            # than compared raw. `validate` reports a counter of the wrong
            # type but does not stop the file loading, and comparing an int
            # with a string raises - so one bad row would take down the whole
            # listing rather than sorting oddly.
            def counter(value: object) -> tuple:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return (1, 0.0, str(value if value is not None else ""))
                return (0, float(value), "")
            return (str(r.get("date") or ""),
                    (r.get("session_start") is None,
                     str(r.get("session_start") or "")),
                    str(r.get("exercise") or ""),
                    *(counter(r.get(k))
                      for k in ("block", "round", "set_index")))

        return sorted(rows, key=where)
    def meals(self, on: str | None = None) -> list[dict]:
        """Itemised meal estimates, each with its range and its questions (#96).

        One entry per meal, never a bare number: the total is the least
        defensible part of a photo estimate, so it is always reported with the
        range it came from, with the item that dominates that range named, and
        with the quantities nobody has settled listed as questions worth
        asking. A stated intake buffer is applied here if config carries one -
        policy, applied to every meal or to none.
        """
        from .meals import (buffered, by_meal, dominant_uncertainty,
                            meal_total, unsettled)
        pct = self.config.intake_buffer_pct
        out = []
        for label, rows in sorted(by_meal(self.dataset("meals"), on).items()):
            date, _, meal = label.partition(" ")
            out.append({
                "date": date, "meal": meal, "items": rows,
                "kcal": buffered(meal_total(rows, "kcal"), pct),
                **{m: meal_total(rows, m) for m in
                   ("protein_g", "fat_g", "carb_g")},
                "dominant": dominant_uncertainty(rows),
                "questions": unsettled(rows)})
        return out

    def meal_day_disagreements(self) -> list[dict]:
        """Days where meal estimates and a stated whole-day intake both exist.

        Reported, never resolved. A meal estimate must never displace the
        athlete's own whole-day figure - the precedence ladder would do
        exactly that, since `stated-in-chat` outranks a logger export.
        """
        from .meals import day_disagreements
        # CANONICAL daily, not the raw claims: with two sources on one day the
        # raw rows would quote whichever landed last in the file, which is
        # exactly the figure precedence decided AGAINST. Comparing against a
        # superseded number is worse than not comparing.
        return day_disagreements(self.dataset("meals"), self.canonical("daily"))

    def set_progression(self, exercise: str, machine: str | None = None) -> dict:
        """The (load, reps, failure) trajectory for one exercise (#100).

        Machine-scoped by default: sets of one exercise across two machines
        are two series, and splicing them describes neither.
        """
        from .progression import progression
        return progression(self.sets(), exercise, machine)

    def working_weight(self, exercise: str) -> dict:
        """The load currently being worked at, with its failure state."""
        from .progression import working_weight
        return working_weight(self.sets(), exercise)

    def set_volume(self, on: str | None = None) -> dict:
        """Sets and completed reps per exercise - the one scale-free figure."""
        from .progression import volume
        return volume(self.sets(on))

    def set_tonnage(self, on: str | None = None) -> dict:
        """Load x reps PER SCALE, with no grand total (#60).

        Bodyweight resolves against the athlete's weight TREND, through the
        resolution ladder, and the result is marked modelled rather than
        measured - it must never sit beside barbell kilos as an equal.
        """
        from .progression import tonnage
        return tonnage(self.sets(on), self.canonical("weight"))

    def devices(self) -> list[str]:
        """Every device that has written to this record.

        Read off the FILENAMES rather than the rows: a device that has only
        ever written legacy unstamped lines still owns a file, and the point
        of the topology is that the file layout is the truth about who writes
        what.
        """
        from .devices import device_of, stream_paths
        found = {device_of(p, name) for name in KEYS
                 for p in stream_paths(self.root / "data", name)}
        return sorted(d for d in found if d)

    def duplicate_captures(self) -> list[dict]:
        """One real event captured twice, from two devices (#105).

        Union does not deduplicate, and nothing else would notice: the same
        workout pulled from a vendor on the laptop and again on the phone is
        two rows describing one event, from two files, both legitimate
        appends. Reported rather than dropped - the athlete decides what to
        do, and a silent merge of two legitimate lines is the one thing an
        append-only record must not do on its own.
        """
        from .devices import duplicates, event_key
        out = []
        for name in KEYS:
            rows = self.dataset(name)
            for row in duplicates(rows, name):
                first = next(r for r in rows
                             if event_key(name, r) == event_key(name, row))
                out.append({
                    "dataset": name, "date": row.get("date"),
                    "device": row.get("device"),
                    "first_device": first.get("device"),
                    "key": event_key(name, row),
                    "detail": (f"a {name} row from "
                               f"{row.get('device') or 'an unnamed device'} "
                               "describes the same event as one from "
                               f"{first.get('device') or 'an unnamed device'} "
                               "- one happening, captured twice")})
        return out

    def explanations(self) -> list[dict]:
        """Which source won a contested field, and why (G29).

        Routine output, not an error channel: the athlete should be able to
        ask "why does the record say 2,443" and get an answer every time, not
        only when something went wrong.
        """
        return self.resolution()["explanations"]

    def conservation(self) -> list[dict]:
        """Conservation tripwires: flagged, never auto-fixed."""
        return self.resolution()["tripwires"]

    def retractions(self) -> list[dict]:
        """What stopped being true, and what fell with it (JTMS cascade)."""
        return retractions(self.datasets())

    def route(self, gpx_path, barometric: bool = False):
        """Deterministic tier-1 geometry for one GPS or TCX track (G40).

        Same track in, same numbers out - and each carries the parameter that
        produced it, in `.params`. Never compute route geometry outside this
        call: an improvised script is not reproducible and its numbers are not
        evidence (G85 extended to algorithms).
        """
        from .route import analyse, read_track
        return analyse(read_track(gpx_path), barometric=barometric)

    def sessions_with_tracks(self) -> list[dict]:
        """Sessions that name a stored track, soonest first (#43)."""
        return [r for r in self.canonical("sessions") if r.get("track")]

    def session_track(self, ref: str) -> Path:
        """The stored track for a session named by `activity_id` or by date.

        The link used to live in a prose note and be recovered by regex. As
        data it can be resolved, which is what lets route geometry rebuild
        from the record rather than from whatever path someone typed.
        """
        rows = [r for r in self.sessions_with_tracks()
                if str(r.get("activity_id") or "") == ref or r.get("date") == ref]
        if not rows:
            raise KeyError(f"no session with a track matches {ref!r} - give an "
                           "activity_id or a date")
        if len({r["track"] for r in rows}) > 1:
            named = ", ".join(sorted(str(r.get("activity_id") or r["date"])
                                     for r in rows))
            raise KeyError(f"{ref!r} matches {len(rows)} sessions with different "
                           f"tracks ({named}) - name one by activity_id")
        path = self.root / rows[0]["track"]
        if not path.exists():
            raise FileNotFoundError(
                f"session {ref!r} points at {rows[0]['track']!r}, which is not "
                "in this repo - the session is the fact, the track is an "
                "attachment, so this is a broken pointer rather than a missing "
                "activity")
        return path

    def session_route(self, ref: str, barometric: bool = False):
        """Tier-1 geometry for a session identified FROM THE RECORD (#43)."""
        return self.route(self.session_track(ref), barometric=barometric)

    def same_route(self, gpx_a, gpx_b):
        """(verdict, similarity) for two tracks - ordering-aware LCSS, so a
        route and its reverse are not confused (the defect of grid overlap)."""
        from .route import read_track, same_route as _same
        return _same(read_track(gpx_a), read_track(gpx_b))

    def journal(self, kind: str | None = None, status: str | None = None,
                about: str | None = None) -> list[dict]:
        """What the athlete SAID, filtered. Their words are observations of a
        statement, not engine inferences - which is why they live in their own
        dataset rather than in `inferences` (P3: no laundering in either
        direction). Sorted by date, then by text, so the order is stable."""
        rows = self.dataset("journal")
        if kind is not None:
            rows = [r for r in rows if r.get("kind") == kind]
        if status is not None:
            rows = [r for r in rows if r.get("status") == status]
        if about is not None:
            rows = [r for r in rows if r.get("about") == about]
        return sorted(rows, key=lambda r: (str(r.get("date")), str(r.get("text"))))

    def open_worries(self) -> list[dict]:
        """Worries nobody has closed. The coach reads these before opening with
        anything cheerful - an unaddressed concern outranks a rate line."""
        return [r for r in self.journal(kind="worry")
                if r.get("status") in (None, "open")]

    def context(self, on: date | str | None = None) -> dict | None:
        """The situational mode in force on a date (G34)."""
        return context_on(self.dataset("context"),
                          on or date.today())

    # --- factual query verbs --------------------------------------------------
    # A number should never be stated from memory - not by a person, and not by
    # a model narrating over the record.

    def check(self, on: date | str, metric: str, says: float,
              type: str | None = None, tolerance: float | None = None) -> dict:
        """Adjudicate a stated value against the record.

        An LLM's narration is as untrustworthy a source as any vendor
        estimate, and P1 says sources are claims the engine adjudicates. This
        applies that rule to the coach's own sentences.
        """
        when = on.isoformat() if isinstance(on, date) else str(on)
        tol = self.config.check_tolerance if tolerance is None else tolerance
        return query.check(self.canonical(), when, metric, float(says),
                           type=type, tolerance=tol)

    def day(self, on: date | str) -> dict:
        """Everything the record holds for one date, merged claims included."""
        when = on.isoformat() if isinstance(on, date) else str(on)
        resolved = self.resolution()
        return query.day(resolved["canonical"], when,
                         claims=resolved["claims"], gates=self.gates(when))

    def window(self, days: int = 7, on: date | str | None = None) -> dict:
        """Totals over the last N calendar days, grouped by session type."""
        return query.window(self.canonical(), days, on=on)

    def ramp(self, type: str = "run", metric: str = "distance_km") -> dict:
        """Week-on-week volume with its base-size caveat attached (G27)."""
        return query.ramp(self.canonical(), type=type, metric=metric)

    # --- the safety layer (G28) ----------------------------------------------
    # Read straight from the record rather than from resolution: an escalation
    # must not depend on a precedence ladder resolving the way someone expected.

    def episodes(self, on: date | str | None = None) -> list[dict]:
        """Medical episodes open on a date."""
        return active_episodes(self.dataset("medical"), on or date.today())

    def gates(self, on: date | str | None = None) -> list[dict]:
        """What is blocked on a date, and why. Deterministic, not advisory.

        Includes gates raised by a clinical HOLD: a hold is not a louder
        warning, it is a suspension of training advice, and routing it through
        the gate mechanism is what makes that enforceable rather than polite.

        A gate with a precondition carries a `status` of `cleared`, `blocked`
        or `check_not_done` - three states, because "your leg said no today"
        and "you have not asked it yet" are different facts.
        """
        when = on or date.today()
        rows = gates_on(self.dataset("medical"), when,
                        pain_gate=self.config.pain_gate,
                        daily=self.dataset("daily"),
                        checks=self.dataset("checks"))
        return rows + hold_gates(self.safety(when), when)

    def checks(self, on: date | str | None = None) -> list[dict]:
        """Daily check results, optionally for one date."""
        rows = self.dataset("checks")
        if on is None:
            return sorted(rows, key=lambda r: (str(r.get("date")),
                                               str(r.get("slug"))))
        when = on.isoformat() if isinstance(on, date) else str(on)
        return [r for r in rows if str(r.get("date")) == when]

    def pending_checks(self, on: date | str | None = None) -> list[dict]:
        """Checks a gate needs today that have not been recorded.

        This is what lets a coach say "you have not done the hop test today"
        instead of assuming either outcome.
        """
        return [g for g in self.gates(on) if g.get("status") == "check_not_done"]

    def gated(self, activity: str, on: date | str | None = None) -> bool:
        """Is this activity class or session type blocked on a date?"""
        return is_gated(self.gates(on), activity)

    def safety(self, on: date | str | None = None) -> list[dict]:
        """Every escalation the record justifies, most urgent first."""
        d = self.datasets()
        return escalations(d["medical"], d["daily"], d["weight"], d["sessions"],
                           on=on)

    def urgent(self, on: date | str | None = None) -> list[dict]:
        """The fast path: escalations that must not wait for the weekly rollup."""
        return urgent_now(self.safety(on), on=on or date.today())

    def safety_banner(self, on: date | str | None = None) -> str:
        """The fixed escalation text for the fast path; empty when clear."""
        return banner(self.urgent(on))

    def verdicts(self, today: date | None = None) -> list[dict]:
        d = self.canonical()
        return compute_verdicts(self.config, d["weight"], d["daily"],
                                d["sessions"], today=today,
                                goals=d["goals"], thresholds=d["thresholds"],
                                medical=d["medical"])

    def rollup(self, today: date | None = None) -> str:
        d = self.canonical()
        on = today or date.today()
        return build_report(self.config, d["weight"], d["daily"],
                            d["sessions"], today=today,
                            gates=self.gates(on),
                            escalations=self.urgent(on),
                            events=self.events(on))

    def state(self, on: date | str) -> State:
        """The goals and thresholds in force on a date - as-of reconstruction.

        The question this exists to answer: "looking at a day three months
        ago, what was I actually aiming at THEN?"
        """
        d = self.datasets()
        return state(d["goals"], d["thresholds"], on)

    def goals(self, today: date | None = None) -> list[dict]:
        """Per-goal standing as of `today`: counted progress, %, dates."""
        d = self.datasets()
        on = (today or date.today()).isoformat()
        return goal_progress(d["goals"], d["thresholds"], d["daily"],
                             d["sessions"], on, events=d["events"])

    def events(self, on: date | str | None = None) -> list[dict]:
        """Dated real-world fixtures known on a date, soonest first (G86).

        An event is what a plan is built backwards FROM - a race, a scan, a
        wedding - as distinct from a milestone, which the engine derives from
        progress already made. `days_away` is derived here rather than stored,
        and goes negative once the fixture has passed.
        """
        d = self.datasets()
        when = on.isoformat() if isinstance(on, date) else (on or
                                                            date.today().isoformat())
        return [dict(e, days_away=days_between(when, e.get("event_date")))
                for e in events_on(d["events"], when)]

    def contributions(self) -> list[dict]:
        """Every event judged against every goal it touched (G18 fan-out)."""
        d = self.datasets()
        return compute_contributions(d["goals"], d["thresholds"], d["daily"],
                                     d["sessions"])[0]

    def milestones(self) -> list[dict]:
        """Target fractions crossed by counted (in-policy) progress only."""
        d = self.datasets()
        return compute_contributions(d["goals"], d["thresholds"], d["daily"],
                                     d["sessions"])[1]

    def churn(self, today: date | None = None) -> list[dict]:
        """Policy edits, with the loosening-after-a-miss flag (G20)."""
        d = self.datasets()
        return plan_churn(d["goals"], d["thresholds"], self.verdicts(today=today),
                          events=d["events"])

    def _derivations(self, resolved: dict,
                     today: date | None = None) -> dict[str, list[dict]]:
        d = resolved["canonical"]
        contributions, milestones = compute_contributions(
            d["goals"], d["thresholds"], d["daily"], d["sessions"])
        verdicts = compute_verdicts(self.config, d["weight"], d["daily"],
                                    d["sessions"], today=today,
                                    goals=d["goals"], thresholds=d["thresholds"],
                                    medical=d["medical"])
        on = (today or date.today()).isoformat()
        return {
            "verdicts": verdicts,
            "contributions": contributions,
            "milestones": milestones,
            "plan_churn": plan_churn(d["goals"], d["thresholds"], verdicts,
                                     events=d["events"]),
            "goal_progress": goal_progress(d["goals"], d["thresholds"],
                                           d["daily"], d["sessions"], on,
                                           events=d["events"]),
            "claims": resolved["claims"],
            "provenance": resolved["provenance"],
            "resolution": resolved["explanations"],
            "justifications": resolved["justifications"],
            "conservation": resolved["tripwires"],
            "retractions": retractions(self.datasets()),
            # Safety reads the RAW record, not canonical rows: an escalation
            # must not be able to disappear because a precedence ladder picked
            # the other source's null.
            "gates": self.gates(on),
            "escalations": self.safety(),
        }

    def build(self, today: date | None = None) -> Path:
        """Rebuild derived/: SQLite read model (incl. verdicts) + weekly.md.

        Resolution runs FIRST and once: the primary tables carry canonical
        rows, so a consumer reading `daily` gets adjudicated truth without
        having to know the resolution rules.
        """
        resolved = self.resolution()
        d = dict(resolved["canonical"])
        # An inference whose justification was retracted stops being presented
        # as current knowledge, though the line itself remains in the file.
        d["inferences"] = live_inferences(self.datasets())
        derivations = self._derivations(resolved, today=today)
        derived = self.root / "derived"
        db = build_db(derived, d, verdicts=derivations["verdicts"],
                      derivations=derivations)
        (derived / "weekly.md").write_text(
            build_report(self.config, d["weight"], d["daily"], d["sessions"],
                         today=today, gates=derivations["gates"],
                         escalations=urgent_now(derivations["escalations"],
                                                on=today or date.today()),
                         events=self.events(today or date.today())),
            encoding="utf-8", newline="\n")
        return db

    def status_line(self) -> str:
        """One line of state, led by what the athlete actually tracks.

        Weight-first was architectural, not chosen, and it meant an athlete
        who had explicitly refused a weight goal opened every session being
        told she had failed to weigh herself (G62/G64). The record should
        report what is in it, not name the thing that is missing.
        """
        pts = sorted((w["date"], w["kg"]) for w in self.dataset("weight")
                     if w.get("kg") is not None)
        if pts:
            d, kg = pts[-1]
            return f"{kg:.1f} kg ({d})"

        steps = [(r["date"], r["steps"]) for r in self.dataset("daily")
                 if r.get("steps") is not None]
        if steps:
            recent = [s for _, s in steps[-7:]]
            return (f"{sum(recent) / len(recent):,.0f} steps/day over the last "
                    f"{len(recent)} logged days ({steps[-1][0]})")

        days = [r for r in self.dataset("daily") if r.get("date")]
        if days:
            return f"{len(days)} days logged (latest {days[-1]['date']})"
        return "nothing logged yet - one number is a complete day"
