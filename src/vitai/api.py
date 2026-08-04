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

import shutil
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from statistics import mean

from . import __version__
from .config import Config, load_config, policy_digest
from .contributions import compute_contributions, goal_progress
from .db import CONTRACT_VERSION, build_db
from .clocks import is_aware
from .jsonl import EVENT_DATASETS, append, append_many, load
from . import query
from .policy import (State, context_on, days_between, events_on, plan_churn,
                     state)
from .report import build_report
from .resolution import live_inferences, resolve, retractions
from .safety import (
    DISCLAIMER, active_episodes, banner, escalations, gates_on, hold_gates,
    is_gated, urgent_now,
)
from .schema import CURRENT_GENERATION, KEYS
from .verdicts import compute_verdicts


class Vitai:
    """Read/derive interface over one user's content repo."""

    def __init__(self, root: Path | str, as_of: datetime | None = None,
                 on: date | None = None):
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

        `on` is the SECOND clock, and it is a different question: the
        valid-time viewpoint, the day the engine is answering AS. `as_of`
        says what was known; `on` says when. Staleness needs both, because
        recomputing an old artifact varies the cutoff and must hold the
        viewpoint - otherwise every week-old report diffs against its
        month-later self trivially, because life continued, and "later" gets
        reported as "the record no longer supports this" (#134).

        RESOLVED ONCE, here. Eleven call sites across ten methods read
        `date.today()` for themselves, which meant a single build straddling
        midnight answered two different questions, no caller could pin the
        viewpoint without passing it to every method, and there was nothing
        for an artifact to record. This class is the boundary: below it,
        nothing reachable from here reads the wall clock.

        One exception, named because an unnamed one is a lie: `window()`
        defaults to the last logged session rather than to a viewpoint, which
        is deliberate - a window over a record that stops in March should not
        be seven empty days in August. The viewpoint is only its fallback for
        a record with no sessions at all.

        And `as_of` reconstructs DATA, with policy covered only as far as
        policy is data. A threshold with a dated `thresholds.jsonl` row on or
        before the date IS in the record and IS filtered by the cutoff. A key
        with no such row falls through to `vitai.toml`, which has no history,
        so that part of the answer is judged by today - see `policy_digest`
        and #148.
        """
        self.root = Path(root)
        self.as_of = as_of
        # VALIDATED, for the same reason `as_of` is, and by a shared function
        # so that every door onto the viewpoint applies the same rule. The
        # first cut validated here and re-normalised inline in `situation()`,
        # which accepted a `datetime` the constructor rejects for a stated
        # reason - the same value refused at one door and taken at the next.
        self.on = _viewpoint(on) or date.today()
        # WHETHER ANYONE ASKED (#207). `self.on` cannot answer it: a caller
        # who passes today's date and a caller who passes nothing end up
        # holding the same value, and only one of them made a choice. `build`
        # needs the difference, because an unqualified build must be a
        # function of the record and a requested one must be honoured exactly.
        self._on_requested = on is not None
        # Per-instance read cache. See `_forget`.
        self._loaded: dict[str, list[dict]] = {}
        self._resolved: dict | None = None
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

    @property
    def policy(self) -> str:
        """The digest of the policy this record does NOT hold (#148).

        `as_of` reconstructs data. It cannot reconstruct `vitai.toml`, which
        has no history, so two reconstructions taken under different configs
        differ for a reason that is not in the record. This is what makes
        that detectable.
        """
        return policy_digest(self.config)

    def append(self, name: str, record: dict) -> dict:
        """Append one line to a dataset, stamping the machine-owned clocks.

        The WRITE half of P9, and the reason `recorded_at` is trustworthy: a
        field every caller must remember to set is absent exactly when it
        matters. Raises if the caller supplies `recorded_at`, fills missing
        keys with null, stamps `_gen`, and validates before writing - an
        append-only file cannot be un-appended.
        """
        # `emissions` has ONE door, and it is not this one. `assert_delivery`
        # stamps the contract in force and the delivering surface, and a row
        # arriving through the generic append could name its own: an assertion
        # filed as having been made under a shape that was never current, which
        # the replay that checks whether it still holds would then compare
        # against the wrong meaning.
        if name in EVENT_DATASETS:
            raise ValueError(
                f"{name} is written by `assert_delivery`, which stamps the "
                f"contract and the surface. Appending directly would let a "
                f"caller name either")
        self._forget()
        return append(self.root / "data", name, record,
                      device=self.config.device)

    def append_many(self, name: str, records: list[dict]) -> list[dict]:
        """Append many rows in one pass - what a bulk import should call.

        Reads the file once, stamps each row strictly past the one before it,
        validates every row before writing any, and writes in a single open.
        Looping over `append` re-parses a growing file per row.
        """
        # `emissions` has ONE door, and it is not this one. `assert_delivery`
        # stamps the contract in force and the delivering surface, and a row
        # arriving through the generic append could name its own: an assertion
        # filed as having been made under a shape that was never current, which
        # the replay that checks whether it still holds would then compare
        # against the wrong meaning.
        if name in EVENT_DATASETS:
            raise ValueError(
                f"{name} is written by `assert_delivery`, which stamps the "
                f"contract and the surface. Appending directly would let a "
                f"caller name either")
        self._forget()
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

    # --- pure functions the CLI used to reach for directly (#158) ----------
    #
    # Each of these is a formatting or interpretation rule that belongs to the
    # engine: what a failed attempt IS, what a meal item's energy IS, which
    # way a route ran, what a recovery phrase decodes to. The CLI imported
    # them from their modules, which meant an agent rendering the same things
    # had to know which module answers which question, and every one of those
    # is a private detail that will move.
    #
    # STATIC where they take no record, because requiring a content repo to
    # decode a phrase would be a privilege the interface should not have.

    @staticmethod
    def is_failed_attempt(row: dict) -> bool:
        """A set that was attempted and not completed (contract 14).

        THE case that dataset exists for: "0 reps" reads as nothing happened,
        and a failed attempt is the most informative set in a progression.
        """
        from .sets import is_failed_attempt
        return is_failed_attempt(row)

    @staticmethod
    def item_energy(row: dict):
        """kcal for one meal item, DERIVED from its quantity (contract 15)."""
        from .meals import item_energy
        return item_energy(row)

    @staticmethod
    def quantity_range(row: dict):
        """(lo, point, hi) grams for a meal item, or None.

        The range IS the confidence statement, so a consumer that collapses
        it to the point has thrown away the only thing that said how sure the
        estimate was.
        """
        from .meals import quantity_range
        return quantity_range(row)

    @staticmethod
    def modifier_axes() -> dict:
        """The axes a set's configuration is described on (#99).

        `categorical` are free labels; `machine_scoped` are numbers that mean
        NOTHING without the machine that scoped them - `level 15` on its own
        is the confident wrong answer #60 was filed about. A consumer
        rendering a set needs to know which is which, and had to import a
        private module to find out.
        """
        from .modifiers import CATEGORICAL, MACHINE_SCOPED
        return {"categorical": tuple(CATEGORICAL),
                "machine_scoped": tuple(MACHINE_SCOPED)}

    @staticmethod
    def compass(bearing: float) -> str:
        """A bearing as a compass point."""
        from .route import compass
        return compass(bearing)

    @staticmethod
    def new_recovery_key() -> tuple[bytes, str]:
        """A fresh key and its checksummed paper phrase (#107)."""
        from .recovery import generate, to_phrase
        key = generate()
        return key, to_phrase(key)

    @staticmethod
    def key_from_phrase(typed: str) -> tuple[bytes | None, str | None]:
        """Decode a recovery phrase. Returns (key, problem); one is None.

        The half that matters is the refusal: the failure mode is not "never
        wrote it down", it is "believed they wrote it down correctly".
        """
        from .recovery import from_phrase
        return from_phrase(typed)

    def manifest(self) -> dict:
        """The artifacts this record still holds, by content address.

        Live rows only: a removal is a tombstone, and REMOVED IS NOT MISSING
        (contract 13). Exposed because `vitai artifact ls` derived it from
        `artifacts.live_manifest` directly (#158), so an agent listing the
        evidence had to know which module answers that and which rows to drop.
        """
        from .artifacts import live_manifest
        return live_manifest(self.dataset("artifacts"))

    def why_absent(self, ref: str) -> str:
        """Deleted, lost, or never here. Three different facts, said plainly.

        A consumer that renders all three as "missing" turns a retention
        decision into a data-loss alarm, which contract 13 names as the thing
        not to get wrong - so the engine answers it rather than each client.
        """
        from .artifacts import live_manifest, removed_refs
        rows = self.dataset("artifacts")
        if ref in removed_refs(rows):
            removals = [r for r in rows
                        if r.get("sha256") == ref and r.get("removed")]
            why = ((removals[-1].get("reason") or "no reason recorded")
                   if removals else "")
            return (f"the athlete deleted it ({why}). The value it backed "
                    "stands")
        if ref in live_manifest(rows):
            return ("the manifest holds it and the store does not, so the "
                    "bytes were lost rather than deleted. Adding the same "
                    "artifact again repairs it")
        return "no manifest row has ever mentioned this hash"

    @staticmethod
    def is_reference(ref: str) -> bool:
        """Is this a content address rather than a path? (contract 13)"""
        from .artifacts import is_reference
        return is_reference(ref)

    @staticmethod
    def artifact_faults(findings: list[dict]) -> list[dict]:
        """The findings that are FAILURES, of the ones `verify_artifacts`
        returns. Only a claim the evidence can no longer back is a fault: a
        deliberate removal, an orphan and a not-yet-cited artifact are all
        reported and none of them is broken."""
        from .artifacts import faults
        return faults(findings)

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
        self._forget()
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
            on or self.on.isoformat())
        row = self.append("artifacts", {"date": when, "sha256": ref,
                                        "removed": True, "reason": reason})
        self.artifacts.drop(ref)
        self._forget()
        return row

    def verify_artifacts(self) -> list[dict]:
        """Fixity and referential integrity, in both directions."""
        from .artifacts import verify
        return verify(self.artifacts, self.datasets())

    def dataset(self, name: str) -> list[dict]:
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        if name not in self._loaded:
            self._loaded[name] = load(self.root / "data", name,
                                      as_of=self.as_of)
        return self._loaded[name]

    def datasets(self) -> dict[str, list[dict]]:
        """Raw claims, exactly as recorded. See `canonical()` for adjudicated."""
        return {name: self.dataset(name) for name in KEYS}

    def _forget(self) -> None:
        """Drop the per-instance read cache. Called by every write path.

        The cache exists because `situation()` is meant to be called per agent
        turn, and one call was loading every dataset file over two hundred
        times and running full resolution three times - each of those counts
        scaling with the record. An instance is a VIEW of the record at one
        cutoff, so caching a read is honest; a write through this instance is
        the one thing that makes the view stale, and it says so here rather
        than leaving the next reader to discover it.
        """
        self._loaded.clear()
        self._resolved = None

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
        if self._resolved is None:
            cfg = self.config
            self._resolved = resolve(self._converged(),
                                     precedence=cfg.precedence,
                                     source_order=cfg.source_order)
        return self._resolved

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
                          on or self.on)

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
        """Totals over the last N calendar days, grouped by session type.

        The end defaults to the last logged session, NOT to the viewpoint: a
        window over a record that stops in March should not be seven empty
        days in August. `fallback` is only for a record with no sessions at
        all, where the function otherwise read the wall clock - a pinned
        instance on an empty repo returned today's real week.
        """
        return query.window(self.canonical(), days, on=on, fallback=self.on)

    def ramp(self, type: str = "run", metric: str = "distance_km") -> dict:
        """Week-on-week volume with its base-size caveat attached (G27)."""
        return query.ramp(self.canonical(), type=type, metric=metric)

    # --- the safety layer (G28) ----------------------------------------------
    # Read straight from the record rather than from resolution: an escalation
    # must not depend on a precedence ladder resolving the way someone expected.

    def episodes(self, on: date | str | None = None) -> list[dict]:
        """Medical episodes open on a date."""
        return active_episodes(self.dataset("medical"), on or self.on)

    def gates(self, on: date | str | None = None) -> list[dict]:
        """What is blocked on a date, and why. Deterministic, not advisory.

        Includes gates raised by a clinical HOLD: a hold is not a louder
        warning, it is a suspension of training advice, and routing it through
        the gate mechanism is what makes that enforceable rather than polite.

        A gate with a precondition carries a `status` of `cleared`, `blocked`
        or `check_not_done` - three states, because "your leg said no today"
        and "you have not asked it yet" are different facts.
        """
        when = on or self.on
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
        return urgent_now(self.safety(on), on=on or self.on)

    def safety_banner(self, on: date | str | None = None,
                      every: bool = False) -> str:
        """The fixed escalation text; empty when clear.

        `every` renders EVERY escalation the record justifies rather than only
        the fast-path ones. The CLI's `safety --all` had this and the API did
        not, so it reached for `safety.banner` directly (#158) - and this text
        is reviewed, fixed and never model-authored, which makes "who may
        render it" a question the engine should answer rather than each
        consumer.
        """
        return banner(self.safety(on) if every else self.urgent(on))

    def verdicts(self, today: date | None = None) -> list[dict]:
        d = self.canonical()
        # `today=on`, not `today=today`, for the reason `rollup` records
        # below: the un-defaulted parameter leaves the pinned viewpoint on the
        # floor. It mattered less when nothing downstream read the clock; it
        # matters now, because a refusal cannot say whether a source is still
        # due without knowing when "still" is, and with no viewpoint every one
        # of them silently answers `no_input` (#202).
        on = today or self.on
        return compute_verdicts(self.config, d["weight"], d["daily"],
                                d["sessions"], today=on,
                                goals=d["goals"], thresholds=d["thresholds"],
                                medical=d["medical"])

    def rollup(self, today: date | None = None) -> str:
        d = self.canonical()
        # THE SAME DEFAULT `build` USES (#207), because this renders the same
        # artifact. Left on the wall clock, `rollup()` stamped "Generated
        # <today>" while the `weekly.md` written by `build()` beside it said
        # the record's own date - two renderings of one report disagreeing
        # about when they were made.
        on = today or (self.on if self._on_requested
                       else self.last_recorded() or self.on)
        # `today=on`, not `today=today`. Passing the un-defaulted parameter
        # left `build_report` to fall back to its own `date.today()`, so the
        # report itself was still dated by the wall clock while every table
        # around it honoured the pinned viewpoint - a rollup that disagreed
        # with its own contents, and the one artifact #134 most needs to be
        # reproducible.
        return build_report(self.config, d["weight"], d["daily"],
                            d["sessions"], today=on,
                            gates=self.gates(on),
                            escalations=self.urgent(on),
                            events=self.events(on))

    def state(self, on: date | str) -> State:
        """The goals and thresholds in force on a date - as-of reconstruction.

        PARTIAL: it returns the dated rows in force, and a key with no dated
        row on or before this date is simply absent rather than falling back
        to `vitai.toml`. The caller that overlays it onto the config gets the
        toml value for that key - today's, not the date's (#148).

        The question this exists to answer: "looking at a day three months
        ago, what was I actually aiming at THEN?"
        """
        d = self.datasets()
        return state(d["goals"], d["thresholds"], on)

    def goals(self, today: date | None = None) -> list[dict]:
        """Per-goal standing as of `today`: counted progress, %, dates."""
        d = self.datasets()
        on = (today or self.on).isoformat()
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
                                                            self.on.isoformat())
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

    def _derivations(self, resolved: dict, today: date | None = None,
                     cfg: Config | None = None) -> dict[str, list[dict]]:
        d = resolved["canonical"]
        cfg = self.config if cfg is None else cfg
        contributions, milestones = compute_contributions(
            d["goals"], d["thresholds"], d["daily"], d["sessions"])
        verdicts = compute_verdicts(cfg, d["weight"], d["daily"],
                                    d["sessions"], today=today,
                                    goals=d["goals"], thresholds=d["thresholds"],
                                    medical=d["medical"])
        on = (today or self.on).isoformat()
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

    def last_recorded(self) -> date | None:
        """The latest `date` any row in this record carries (#207).

        The record's own horizon, used as the build's viewpoint when nobody
        named one. A record is a closed thing: what it contains does not
        change because a build ran on a Tuesday, and every other derivation
        here is a pure function of appended facts.

        NARROWER THAN "the last day this record speaks about", deliberately.
        `events.event_date` and `regimes.to_date` legitimately run ahead of
        the last row - a race declared in June for September - so the record
        does say things about later days. This is the last day it has a ROW
        for, which is the horizon a build's visibility questions turn on.

        PARSED, NOT COMPARED AS TEXT. `date.fromisoformat` accepts ISO week
        dates and the basic format as well as the extended one, and neither
        sorts chronologically against the others: `2030-W01-1` outranks every
        extended date in its year on the letter W alone, and `20300101` beats
        `2030-12-31` on the fifth character. A string maximum over a record
        holding one such row picked a date months early, which put the build
        back on a viewpoint where nothing was in force - the exact symptom
        this function exists to remove.

        A date this cannot parse is SKIPPED rather than raised on. The loader
        promises a build proceeds from the good rows, and taking a record that
        built yesterday and refusing it today would break that for the sake of
        a horizon one row could not contribute to anyway.

        Returns None for a record with no usable dates, which has no horizon
        and nothing whose visibility a viewpoint could decide.
        """
        seen = []
        for rows in self.datasets().values():
            for r in rows:
                raw = r.get("date")
                if not isinstance(raw, str):
                    continue
                try:
                    seen.append(date.fromisoformat(raw[:10]))
                except ValueError:
                    continue
        return max(seen) if seen else None

    def build(self, today: date | None = None) -> Path:
        """Rebuild derived/: SQLite read model (incl. verdicts) + weekly.md.

        Resolution runs FIRST and once: the primary tables carry canonical
        rows, so a consumer reading `daily` gets adjudicated truth without
        having to know the resolution rules.
        """
        # THE BUILD'S VIEWPOINT IS THE RECORD'S, unless somebody named one
        # (#207). `goal_progress` is materialised against it, so defaulting to
        # the wall clock meant two people building the same record on
        # different days got different databases, with nothing in either one
        # recording the choice - the example corpus shipped an empty
        # `goal_progress` beside 109 contribution rows.
        #
        # An explicit `today=` or `on=` still wins, because "what does this
        # look like now" is a real question. What changes is the answer when
        # nobody asked it.
        on = today or (self.on if self._on_requested
                       else self.last_recorded() or self.on)
        resolved = self.resolution()
        d = dict(resolved["canonical"])
        # An inference whose justification was retracted stops being presented
        # as current knowledge, though the line itself remains in the file.
        d["inferences"] = live_inferences(self.datasets())
        # ONE config for the whole build. `self.config` re-reads vitai.toml on
        # every access, so the verdicts were computed under one read and
        # stamped with the digest of a later one. Edit the toml between them
        # and the read model records an identity claim that is simply false -
        # worse than the absence this is careful not to be misread as.
        cfg = self.config
        derivations = self._derivations(resolved, today=on, cfg=cfg)
        derived = self.root / "derived"
        db = build_db(derived, d, verdicts=derivations["verdicts"],
                      derivations=derivations, policy=policy_digest(cfg),
                      built_on=on.isoformat())
        (derived / "weekly.md").write_text(
            build_report(self.config, d["weight"], d["daily"], d["sessions"],
                         today=on, gates=derivations["gates"],
                         escalations=urgent_now(derivations["escalations"],
                                                on=on),
                         events=self.events(on)),
            encoding="utf-8", newline="\n")
        return db

    @staticmethod
    def conform(kind: str, impl) -> dict:
        """Run a contract suite against an implementation, bundled or not.

        Exposed here because #158's acceptance says no CLI command may contain
        logic absent from the API, and this one did: running the suite existed
        only in `cmd_conform`. That is the wrong capability to leave CLI-only,
        because `conform.py`'s whole argument is that a third party can check
        their own implementation on the same terms the bundled ones are
        checked, and "shell out and parse the printed lines" is not the same
        terms.

        Takes an IMPLEMENTATION rather than a name, and `implementation()`
        resolves names, because they fail differently: a name that is neither
        bundled nor a dotted path is a typo, and an import that blows up is a
        broken implementation. Folding both into one call meant one except
        clause covered the suite run too, so a TypeError from deep inside a
        third party's transport was reported as "could not construct" - which
        names the wrong thing and hides a traceback worth seeing.

        STATIC on purpose: conformance is about an implementation, not about a
        record, and requiring a content repo to check a transport would be a
        privilege the interface should not have.

        Returns `{"findings": [...], "failures": [...], "ok": bool}`.
        """
        from . import conform as suites
        suite = {"transport": suites.transport, "custody": suites.custody}
        if kind not in suite:
            raise ValueError(f"kind must be transport or custody, not {kind!r}")
        findings = suite[kind](impl)
        failures = suites.failures(findings)
        return {"findings": findings, "failures": failures,
                "ok": not failures}

    @staticmethod
    def implementation(kind: str, spec: str, at: Path | str):
        """A bundled name or a dotted path, with no difference in privilege.

        The bundled implementations are reached the same way anyone else's
        are: resolved by name, constructed, handed to the same suite. If the
        golden path had a shortcut here, the interface would be decoration.
        """
        from . import sync
        where = Path(at)
        bundled = {
            "transport": {
                "directory": lambda: sync.DirectoryTransport(where),
                "memory": sync.MemoryTransport,
                "mirror": lambda: sync.MirrorTransport(
                    sync.DirectoryTransport(where), sync.MemoryTransport()),
            },
            "custody": {
                "file": lambda: sync.FileCustody(where / "key"),
                "env": lambda: sync.EnvCustody("VITAI_KEY"),
            },
        }[kind]
        if spec in bundled:
            return bundled[spec]()
        module, _, attr = spec.rpartition(".")
        if not module:
            raise ValueError(
                f"{spec!r} is neither a bundled {kind} "
                f"({', '.join(sorted(bundled))}) nor a dotted path to one")
        import importlib
        return getattr(importlib.import_module(module), attr)()

    # --- write parity (#158 rung 4) -------------------------------------
    #
    # The vocabulary already exists and is in live use. What was missing is
    # that a consumer could reach it without hand-writing JSONL, which meant
    # every agent re-implemented the provenance stamping and each one got a
    # slightly different answer about what a spoken number IS.

    # What the ENGINE stamps and a caller may never assert. `recorded_at` and
    # `device` are already refused by `append_many` for the same reason; the
    # other two are refused because a caller that could set them could file a
    # recollection as a device reading, and the ladder ranks `stated-in-chat`
    # ABOVE a connector export (#140, #167).
    NARRATIVE = {"capture": "narrative", "source": "stated-in-chat"}
    # AN ALLOWLIST, because a denylist on a write path is wrong by
    # construction. The first cut enumerated what a caller may NOT set and
    # left everything unlisted open, which fails silently every time the
    # schema grows. What rode through it:
    #
    #   `supersedes`  the record's only DESTRUCTIVE primitive. A narrative
    #                 claim could permanently retire a device reading, with
    #                 provenance saying the athlete stated it.
    #   `origin`      corroboration built out of nothing: setting it made a
    #                 chat claim count as an INDEPENDENT witness, which is
    #                 exactly what `provenance.py` exists to prevent.
    #   `path`, `origin_evidence`, `artifact`, `type_source`, `_gen`
    #
    # So everything a caller may NOT set is named, and the quantities are
    # checked against the dataset's own keys. A provenance field added
    # tomorrow lands here rather than silently becoming settable.
    NOT_A_QUANTITY = frozenset({
        "recorded_at", "device", "capture", "source", "read_by", "_gen",
        "origin", "path", "origin_evidence", "artifact", "modelled",
        "type_source", "activity_source",
        "supersedes",
        "note",
    })

    # What a caller may state about an assertion. Everything else on the row
    # is the ENGINE's to stamp, and an allowlist rather than a denylist because
    # the denylist version of this on `claim` let `supersedes` through: a
    # forgotten key on a write path is a capability nobody decided to grant.
    EMISSION_FIELDS = frozenset({
        "date", "kind", "metric", "week", "statement", "basis_claims",
        "policy_asof"})

    def assert_delivery(self, rows: list[dict], surface: str) -> int:
        """Record that these assertions were SURFACED to the athlete.

        Phase 3 of the uncertainty proposal, 01-schema 8b. Called at DELIVERY
        time by whatever showed the athlete a judgement, and never at build:
        build is a pure function of the record, and a build that appended to
        the record would make a rebuild non-idempotent, which is the
        record-is-input / database-is-disposable split this engine rests on.

        WHY DELIVERY RATHER THAN COMPUTATION. A computed verdict is
        rebuildable, so logging every one would duplicate the derived tier
        into the ground-truth tier and grow without bound on every rebuild.
        "The engine asserted X to the athlete on day T" is an event in the
        world: not rebuildable, bounded by actual use, and the only kind of
        assertion that had a consequence worth retracting later. An unseen
        verdict was never acted on.

        `contract`, `recorded_at` and `device` are STAMPED HERE and cannot be
        supplied. A caller that could name its own contract version could file
        an assertion as having been made under a shape that was not in force,
        and the replay that checks whether it still holds would compare
        against the wrong meaning.

        The residual risk, recorded rather than papered over: a consumer that
        renders a judgement and does not call this produces an assertion the
        record cannot later retract. That is accepted, because the alternative
        - logging computation instead of delivery - records the wrong event.

        Returns how many rows were appended.
        """
        if not str(surface or "").strip():
            raise ValueError(
                "surface names WHICH consumer delivered these, and an "
                "assertion whose deliverer is unknown cannot be attributed "
                "when it turns out to have been wrong")
        out = []
        for row in rows or []:
            unknown = sorted(set(row) - self.EMISSION_FIELDS)
            if unknown:
                raise ValueError(
                    f"assert_delivery does not take {', '.join(unknown)}. "
                    f"`contract`, `recorded_at` and `device` are stamped by "
                    f"the engine at emission, and the rest is not an "
                    f"emission field")
            out.append({**row, "surface": str(surface).strip(),
                        "contract": CONTRACT_VERSION})
        if not out:
            return 0
        self._forget()
        append_many(self.root / "data", "emissions", out,
                    device=self.config.device)
        return len(out)

    def claim(self, dataset: str, values: dict, said: str | None = None,
              read_by: str = "athlete", corrects: str | None = None,
              on: date | str | None = None) -> dict:
        """Append ONE claim the athlete stated, with provenance the engine sets.

        A spoken rep count becomes a line carrying `capture: narrative`,
        `source: stated-in-chat` and a `recorded_at` the engine sets. The
        caller supplies the quantities and nothing else.

        REFUSAL IS THE POINT, and it belongs here rather than in each agent.
        "Some push-ups" is not a rep count, and the place to decide that once
        is the engine: an agent that validates for itself is an agent that
        will eventually decide "some" means three. A value this cannot accept
        raises with the engine's own reason, which is a sentence an agent can
        relay rather than a code it has to interpret.

        `said` is the athlete's own words, kept verbatim in `note`. Not
        decoration: it is the only record of what the number was derived
        FROM, and #168 exists because a qualification has nowhere else to sit.

        `read_by` is required by the engine whenever the capture involved
        somebody reading, and narrative does - the engine refused the first
        version of this method for exactly that reason. It defaults to
        `athlete` because the commonest case is the athlete saying a number
        they know. An agent transcribing what it heard should pass `model`,
        and the difference is worth carrying: RECORDING who read is not
        ranking who read, and #140 deliberately declined to rank people while
        keeping the field.
        """
        if dataset not in KEYS:
            raise KeyError(f"unknown dataset {dataset!r}; "
                           f"one of {sorted(KEYS)}")
        refused = sorted(k for k in values if k in self.NOT_A_QUANTITY)
        if refused:
            hints = {"read_by": "the `read_by` parameter",
                     "supersedes": "the `corrects` parameter",
                     "note": "the `said` parameter"}
            named = [f"{k} (use {hints[k]})" if k in hints else k
                     for k in refused]
            raise ValueError(
                f"not a quantity: {', '.join(named)}. A caller supplies what "
                "was stated and nothing else - one that could set these could "
                "file a recollection as a device reading, manufacture an "
                "independent witness out of nothing, or retire a measurement")
        unknown = sorted(set(values) - set(KEYS[dataset]))
        if unknown:
            raise ValueError(f"{dataset} has no field(s) "
                             f"{', '.join(unknown)}")
        if not {k: v for k, v in values.items()
                if k != "date" and v is not None}:
            # An all-null row is permanent junk in an append-only record, and
            # it is the likeliest agent slip: the quantity went into `said`
            # instead of into a field.
            raise ValueError(
                f"no quantity was stated for {dataset}. If the athlete said "
                "something no number can honestly be taken from, append it "
                "with `said()` rather than an empty row")
        from .provenance import READERS
        if read_by not in READERS:
            raise ValueError(f"read_by is one of {', '.join(READERS)}, "
                             f"got {read_by!r}")
        row = dict(values)
        row.update(self.NARRATIVE)
        row["read_by"] = read_by
        if said is not None:
            said = str(said).strip()
            if not said:
                raise ValueError("said was given and is empty; omit it rather "
                                 "than recording that nothing was said")
            row["note"] = said
        if corrects is not None:
            # EXPLICIT, because it is destructive: a supersede retires the
            # line it names on every future load, and a caller that reached
            # it by putting a key in a dict would not have decided to.
            row["supersedes"] = corrects
        # The VIEWPOINT is the write date. Worth knowing rather than
        # discovering: an engine pinned to a past date for a historical
        # question stamps a claim with that date. Pass `on` to say otherwise.
        when = on if on is not None else self.on
        if isinstance(when, str):
            when = date.fromisoformat(when)
        row.setdefault("date", when.isoformat())
        return self.append(dataset, row)

    def said(self, text: str, kind: str = "claim",
             about: str | None = None, on: date | str | None = None) -> dict:
        """Append what the athlete SAID, when no number can be taken from it.

        The other half of the refusal, and the half that makes refusing safe.
        Zero guessed numbers, but always exactly one appended line: a rule
        that answers "I did some push-ups" by writing nothing hands the record
        to whichever tool is willing to write the sentence down, and an
        account of a session nobody measured is the capture this product
        exists for.

        Lands in `journal`, where the athlete's own words live: their
        statements are observations of a STATEMENT rather than engine
        inferences, which is why they have their own dataset instead of
        sitting in `inferences` (P3, no laundering in either direction).
        """
        text = str(text or "").strip()
        if not text:
            raise ValueError("nothing was said; there is no claim to append")
        when = on if on is not None else self.on
        if isinstance(when, str):
            when = date.fromisoformat(when)
        return self.append("journal", {
            "date": when.isoformat(),
            "kind": kind,
            "text": text,
            "about": about,
            "source": "stated-in-chat",
            "confidence": None,
            "status": None,
            "note": None,
        })

    def load_report(self) -> dict:
        """What a load of this record SAW: counts, quarantined lines, warnings.

        `cmd_build` derived all three itself (#158), which meant an agent
        could rebuild a record and had no way to learn that eleven lines had
        been quarantined on the way. G26 is that a malformed line never aborts
        a read - it is skipped and REPORTED - and a report only one consumer
        can reach is half of that rule.

        Warnings are schema complaints about lines that loaded: they do not
        stop a build, and `validate()` is where they are problems.
        """
        from .jsonl import load_report as _load
        from .schema import validate_record

        counts: dict[str, int] = {}
        quarantined: list[str] = []
        warnings: list[str] = []
        for name in KEYS:
            records, errors = _load(self.root / "data", name)
            counts[name] = len(records)
            quarantined += errors
            for rec in records:
                warnings += [f"{name}.jsonl {rec.get('date')}: {p}"
                             for p in validate_record(name, rec)]
        return {"counts": counts, "quarantined": quarantined,
                "warnings": warnings}

    def validate(self) -> dict:
        """Every problem and every advisory in this record.

        Moved here from `cmd_validate` (#158): it existed only in the CLI, so
        an agent could not ask whether a record was sound without shelling out
        and parsing prose. P9 says the CLI is a harness over this, and for
        this capability there was nothing to harness.

        Returns `{"problems": [...], "advisories": [...], "ok": bool}`. It
        RAISES NOTHING and exits nothing: deciding what a problem means is the
        caller's, and a library that calls `sys.exit` cannot be used by one.

        Problems fail a build; advisories never do. The distinction is
        load-bearing and is the engine's, not the caller's: an advisory
        describes a row that is legal and already on disk, and making those
        errors would demand a migration before the record could be built at
        all (#38).
        """
        from .devices import stream_paths
        from .jsonl import read_lines
        from .schema import (corrections_that_did_not_apply,
                             impossible_claim_problems, recorded_at_problems,
                             period_advisories, polarity_advisories,
                             supersedes_problems,
                             timestamp_advisories,
                             unranked_source_problems,
                             unstamped_after_the_clock_started,
                             validate_record)

        cfg = self.config
        ranked = set(cfg.source_order) | {
            s for ladder in cfg.precedence.values() for s in ladder}
        problems: list[str] = []
        advisories: list[str] = []

        for name in KEYS:
            # EVERY device file, not just the plain one (#105). Reading only
            # `<name>.jsonl` meant a malformed or invalid line in
            # `<name>.laptop.jsonl` passed clean and was then quarantined by
            # the build, and monotonicity, unranked sources and supersedes
            # ambiguity were all skipped for every device stream - precisely
            # when the union makes cross-file collisions likelier.
            #
            # Per FILE for the per-line checks, so a message names the file
            # the reader has to open. The file-level checks below run over the
            # merged stream, because monotonicity across a union is the
            # question that actually matters once a second device exists.
            rows: list[tuple[int, dict]] = []
            for path in stream_paths(self.root / "data", name):
                found, parse_errors = read_lines(path)
                # G26: report EVERY malformed line.
                problems += [f"MALFORMED: {e}" for e in parse_errors]
                for n, rec in found:
                    problems += [f"{path.name} line {n}: {p}"
                                 for p in validate_record(name, rec)]
                # PER FILE, unlike the checks below: the rule is "this file's
                # clock started", and a file is what has a clock.
                advisories += unstamped_after_the_clock_started(path.name,
                                                                found)
                rows += found
            # File-level: transaction time must be monotonic and tie-free
            # (#37). Neither is a property of any single line.
            problems += recorded_at_problems(name, rows)
            problems += unranked_source_problems(name, rows, ranked)
            problems += impossible_claim_problems(name, rows)
            problems += supersedes_problems(name, rows)
            advisories += corrections_that_did_not_apply(name, rows)
            advisories += timestamp_advisories(name, rows)
            if name == "goals":
                advisories += polarity_advisories(rows)
                advisories += period_advisories(rows)
            # A missing track file is NOT a missing session: the session is
            # the fact and the track is an attachment, so a broken pointer is
            # reported and never fails the build (#43).
            for n, rec in rows:
                if (t := rec.get("track")) and not (self.root / str(t)).exists():
                    advisories.append(
                        f"{name}.jsonl line {n}: track {t!r} is not in this "
                        "repo - the session stands, but its geometry cannot "
                        "be rebuilt")

        return {"problems": problems, "advisories": advisories,
                "ok": not problems}

    def accept_inferences(self, rows: list[dict]) -> int:
        """Append validated inference rows and rebuild. Returns the count.

        Separate from `infer()` because running a model and COMMITTING what it
        said are two different acts, and folding them together meant the rows
        were on disk before any caller had seen them: if the rebuild raised,
        the CLI had appended lines it never echoed, and the echo exists so a
        script can log exactly what it committed.
        """
        from .inference import append_inferences
        appended = append_inferences(self.root, rows)
        # The rows went in through a MODULE function, which has no instance to
        # tell, so the read cache still holds the record as it was before the
        # append. `infer()` warms that cache on the way here, so the rebuild
        # was running over stale datasets - and now that the build takes its
        # viewpoint from the record, a stale read would stamp `built_on` with
        # a horizon the record no longer has, which is worse than a missing
        # row because it asserts something.
        self._forget()
        self.build()
        return appended

    def infer(self, today: date | None = None) -> dict:
        """Run the opt-in inference layer. A model reads; the engine decides.

        Moved here from `cmd_infer` (#158), same reason as `validate`. P4 is
        unchanged and unchangeable: nothing a model produces becomes a number,
        a severity or a verdict, and every candidate is validated before it
        can be appended.

        Returns `{"accepted": [...], "rejected": [...]}` and APPENDS NOTHING.
        `rejected` carries the reasons rather than a count, because an agent
        that cannot see WHY a candidate was refused will simply send it again.
        Commit the accepted rows with `accept_inferences()`.
        """
        from .config import load_inference_config
        from .inference import backend_from_config, run_inference

        cfg = load_inference_config(self.root)
        if not cfg:
            raise ValueError(
                "no [inference] section in vitai.toml - inference is opt-in; "
                "see the template for claude-cli / openai-compatible examples")
        data = self.datasets()
        valid, errors = run_inference(
            self.root, backend_from_config(cfg), self.rollup(),
            data["daily"], data["sessions"], data["inferences"],
            today or self.on,
            max_items=int(cfg.get("max_items", 5)))
        return {"accepted": valid, "rejected": errors}

    def situation(self, on: date | str | None = None,
                  recent: int = 14) -> dict:  # noqa: C901
        """Everything a consumer needs before it says anything. ONE call.

        #158's second rung. The alternative it replaces is fifteen calls a
        consumer stitches together, which is fifteen chances to stitch it
        wrong - and the stitching is exactly the work that must not be
        duplicated per consumer, because each one gets it subtly differently
        and none of them is the engine.

        Shaped for something that has to DECIDE, not for something that has to
        display. So it leads with what would stop a decision (the refusals),
        it says what it could not answer rather than omitting it, and it
        carries the two numbers a consumer must gate on before trusting any of
        the rest.

        ALMOST NOTHING HERE IS NEW, and the exception is named rather than
        glossed: every value is an existing engine surface, assembled, except
        `unresolved.last_seen`, which is a max over dates computed here. That
        one is engine-side arithmetic over engine data, which is allowed - the
        rule is that the CLIENT does not derive - but it is new, and a
        docstring claiming otherwise would be the kind of small false sentence
        this codebase spends its comments preventing.

        `last_seen` answers HOW STALE, not what is missing. The coverage
        ledger that could answer the second question is #93 and does not
        exist; inventing one here would be a number nobody authorised.

        If a consumer wants something this does not carry, the answer is a
        change to the engine rather than arithmetic on the way out, which is
        the same rule the read model already lives under.
        """
        when = _viewpoint(on) or self.on
        report = self.validate()

        # LEADS with what stops a decision. A brief that opens with a rate
        # line and mentions the gate further down has already failed the one
        # job it has, because the reader may act on the first paragraph.
        gates = self.gates(when)
        escalations = self.safety(when)

        # EVERY derived section is guarded, not just one. `validate()` above
        # has already enumerated a non-numeric weight WITHOUT raising, by
        # design; a brief that then crashed while formatting that same value
        # would be withholding the diagnosis it is holding, on exactly the
        # record that needs it most. The first cut guarded `status` alone and
        # the crash simply moved to `rollup`.
        #
        # Guarded, never swallowed: each failure is named in `unavailable`, so
        # a consumer can tell "the engine could not answer this" from "the
        # answer is empty". Absence is a claim here as everywhere else.
        unavailable: dict[str, str] = {}

        def section(name, fn, empty):
            try:
                return fn()
            except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
                unavailable[name] = f"{type(e).__name__}: {e}"
                return empty

        status = section("status", lambda: self.status(when),
                         {"line": None, "on": when.isoformat()})

        canonical = self.canonical()
        # AT OR BEFORE the viewpoint, and `recent > 0` guarded. "Recent
        # sessions" in a brief pinned to May must not contain June, and
        # `[-0:]` is the whole list rather than none of it.
        horizon = when.isoformat()
        dated = [r for r in canonical.get("sessions") or []
                 if str(r.get("date") or "") <= horizon]
        sessions = dated[-recent:] if recent > 0 else []

        # "What is stale and what is missing", per the issue. Stated as the
        # engine's own advisories plus the last date each dataset carries -
        # NOT as a coverage verdict, because a coverage ledger is #93 and does
        # not exist yet, and inventing one here would be a number nobody
        # authorised.
        last_seen = {}
        for name, rows in canonical.items():
            dates = [d for r in rows
                     if (d := str(r.get("date") or "")) and d <= horizon]
            last_seen[name] = max(dates) if dates else None

        return {
            # A consumer gates on these before trusting anything below.
            "schema": schema(),
            "policy": self.policy,
            "on": when.isoformat(),
            "as_of": self.as_of.isoformat() if self.as_of else None,

            # What would stop a decision, first.
            "gates": gates,
            "escalations": escalations,
            "banner": self.safety_banner(when),
            "worries": self.open_worries(),

            # What is true now. `status` is guarded because it formats
            # numbers, and `validate()` above has ALREADY reported a
            # non-numeric weight without raising - so a brief that crashed
            # here would be withholding the very problems it is holding, on a
            # record whose damage it had just finished enumerating.
            "status": status,
            "goals": section("goals", lambda: self.goals(when), []),
            "context": section("context", lambda: self.context(when), None),
            "sessions": sessions,
            "rollup": section("rollup", lambda: self.rollup(when), None),

            # What the engine will not vouch for. Present even when empty, so
            # a consumer that renders it cannot mistake "no problems" for "not
            # asked" - the same reason absence is a claim everywhere else.
            "unresolved": {
                "problems": report["problems"],
                "advisories": report["advisories"],
                "last_seen": last_seen,
                "duplicate_captures": self.duplicate_captures(),
                "conservation": self.conservation(),
                "retracted": self.retractions(),
                # Which sections the engine could not compute, and why.
                "unavailable": unavailable,
            },
        }

    def status(self, on: date | str | None = None) -> dict:
        """The one-line state, with everything the line used to compute itself.

        P9 says the CLI is a thin harness over this API and never a separate
        code path (#158). `cmd_status` was the standing counter-example: it
        loaded the datasets itself, derived a seven-day rate and a direction
        word, and read tripwire count out of `derived/weekly.md` by string
        prefix - none of which existed here, so no agent could obtain what
        the CLI printed without reimplementing it.

        Worse than duplicated: DIVERGED. The CLI's version still opened with
        "no weight data yet" on an empty record, which is exactly the
        weight-first behaviour `status_line` was rewritten to remove (G62/G64)
        - an athlete who had refused a weight goal was told at every session
        that she had failed to weigh herself.

        Returns the parts, not a sentence, because a consumer that has to
        decide something needs the rate rather than the phrase containing it.
        """
        when = _viewpoint(on) or self.on
        # THE VIEWPOINT REACHES THE NUMBERS, not just the label. The first cut
        # took no argument at all, so a brief pinned to May carried a rate
        # computed over weight points dated in June and reported `on` twice
        # with two different answers in one document.
        pts = sorted((w["date"], w["kg"]) for w in self.dataset("weight")
                     if w.get("kg") is not None
                     and str(w.get("date") or "") <= when.isoformat())
        out = {
            "line": self.status_line(),
            "on": when.isoformat(),
            "rate_kg_per_week": None,
            "direction": None,
            "mean_kg_7d": None,
            "tripwires": None,
            "disclaimer": DISCLAIMER,
        }
        if len(pts) >= 8:
            vals = [v for _, v in pts[-7:]]
            prev = [v for _, v in pts[-14:-7]] or vals
            days = (datetime.fromisoformat(pts[-1][0])
                    - datetime.fromisoformat(pts[-8][0])).days
            if days:
                rate = (mean(prev) - mean(vals)) / days * 7
                out["rate_kg_per_week"] = rate
                out["mean_kg_7d"] = mean(vals)
                # G69, the same rule the rollup uses: a bare signed rate reads
                # backwards to anyone who has not memorised that positive
                # means losing. The WORD is the engine's, not the caller's.
                out["direction"] = ("losing" if rate > 0 else
                                    "gaining" if rate < 0 else "holding")
        weekly = self.root / "derived" / "weekly.md"
        if weekly.exists():
            out["tripwires"] = sum(
                1 for ln in weekly.read_text(encoding="utf-8").splitlines()
                if ln.startswith("- **"))
        return out

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


def _viewpoint(on):
    """Normalise and validate a valid-time viewpoint. Shared by every door.

    A `str` is the natural call, since every per-call `on` in this class takes
    `date | str`. A `datetime` is the obvious slip, because `as_of` right next
    door is one, and it is worse: `datetime` subclasses `date`, so it passes
    every `isinstance(on, date)` check in the codebase and dies much later
    comparing a datetime to a date.
    """
    if on is None:
        return None
    if isinstance(on, str):
        return date.fromisoformat(on)
    if isinstance(on, datetime):
        raise TypeError(
            "on must be a date, not a datetime: it is the valid-time "
            "viewpoint - the DAY the engine answers as - and a time of day "
            "would compare against dates it can never equal. The cutoff that "
            "does take an instant is as_of")
    if not isinstance(on, date):
        raise TypeError(f"on must be a date or an ISO date string, "
                        f"not {type(on).__name__}")
    return on


def init(path: str | Path) -> Path:
    """Stamp a new content repo, and return where it landed.

    #158, acceptance criterion 1: no CLI command may hold logic the API lacks,
    because a capability the CLI can reach is one an agent cannot. This one hid
    from the import-surface guard for a while - it scaffolds with `shutil` and
    `importlib.resources` rather than by importing an engine module, so it
    tripped nothing while being the one capability an agent had to shell out
    for. Creating a record is where a client STARTS, so needing a subprocess
    for it is tier 1 failing at the first step.

    Scoped honestly: this closes the gap for a caller that can import the
    engine. `mcp.TOOLS` names METHODS on `Vitai`, so an MCP-attached agent
    still cannot reach this one, and whether it should be able to create
    directories at a path of its choosing is a policy question rather than an
    oversight.

    A module function rather than a method, and NOT for the reason `schema` is
    one: `schema` takes no root, while a root is this function's whole
    argument. The reason here is that `Vitai` represents an existing record,
    and this is what runs when there is not one yet.

    REFUSES a non-empty directory rather than merging into it. Initialising
    over a record could bury an append-only history under a template.
    """
    target = Path(path).resolve()
    if target.exists() and any(p.name != ".git" for p in target.iterdir()):
        raise FileExistsError(
            f"{target} exists and is not empty - refusing to overwrite. "
            "Initialising over an existing record could bury an append-only "
            "history under a template, which is the one thing this engine "
            "must never do.")
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
    # `derived/` is REBUILDABLE and must never be synced or committed (#105).
    # The database rebuilds from `data/*.jsonl` in seconds, so syncing it
    # would make a disposable file load-bearing - and SQLite's main file and
    # its WAL are separate files that must stay consistent, so a client that
    # uploads them independently produces a database that is corrupt rather
    # than merely stale. Written here rather than shipped as a template
    # dotfile, for the same reason `.gitattributes` is: packaging globs skip
    # dotfiles.
    (target / ".gitignore").write_text(
        "# Rebuilt by `vitai build` from data/*.jsonl. Never sync or commit\n"
        "# this: it is derived, and a synced SQLite file is corrupt rather\n"
        "# than merely stale.\n"
        "derived/\n"
        "\n"
        "# Artifacts are personal data (#80). Keep them, but decide\n"
        "# deliberately how - git-lfs, a sibling directory, an object store -\n"
        "# rather than by a default nobody chose.\n"
        "artifacts/\n",
        encoding="utf-8", newline="\n")
    (target / "data").mkdir(exist_ok=True)
    for name in KEYS:
        (target / "data" / f"{name}.jsonl").touch()
    (target / "derived").mkdir(exist_ok=True)
    return target


def schema() -> dict:
    """The SHAPE this engine emits: contract version and dataset generations.

    A property of the installed ENGINE rather than of any one record, so it
    takes no root and is a module function rather than a method on `Vitai`.

    #147. Anything that PINS against this engine needs these two numbers: a
    fixture corpus that must refuse to regenerate when the shape has moved
    past what it was authored against, a content repo recording which engine
    wrote it, a client checking an artifact is still readable. Every one of
    them had to reach into `db.CONTRACT_VERSION` and
    `schema.CURRENT_GENERATION`, which are private and will move.

    That is worse than inconvenient. A pin that reads private surface is a pin
    that breaks silently on an engine upgrade, which is exactly the failure the
    pin exists to prevent - the guard and the thing it guards against sharing a
    failure mode.

    `contract` versions the READ MODEL, the built SQLite shape a consumer gates
    on. `generations` versions the LINE SHAPE per dataset, which keys a row
    owed when it was written. They answer different questions and a consumer
    usually needs both. `engine` is provenance for a bug report and is
    deliberately NOT a gate: it moves for a docs fix and stands still while the
    schema moves, so a pin that gates on it is telling itself a comforting lie.
    """
    return {
        "engine": __version__,
        "contract": CONTRACT_VERSION,
        "generations": dict(CURRENT_GENERATION),
    }
