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
from .contributions import (_standing, compute_contributions,
                            goal_progress)
from .crossings import compute_crossings
from .db import CONTRACT_VERSION, DERIVED_TABLES, build_db
from . import builds as _builds
# Re-exported deliberately: the CLI reads them from here and the MCP adapter
# reaches a rootless tool by `getattr` on this module, so the API surface is
# where they have to live. Written as redundant aliases to say that is
# intentional rather than a stray import.
from .builds import ABSENCE_MEANINGS
from .builds import absence as absence
from .builds import can_emit as can_emit
from .builds import this_build as this_build
from .clocks import comparable, day_phase, is_aware, ordering_rule, phase_rule
# Re-exported for the CLI, which must reach the engine only through this
# module: `cmd_phases` prints a wall-clock time and slicing characters
# off an offset-aware stamp prints "00+00" instead of one.
from .clocks import parse_time as parse_time
from .jsonl import EVENT_DATASETS, append, append_many, load
from . import query
from .policy import (State, capability, comparability, context_on,
                     days_between, events_on, plan_churn, state)
from .report import build_report
from .resolution import live_inferences, resolve, retractions
from .safety import (
    DISCLAIMER, active_episodes, banner, escalations, gates_on, hold_gates,
    is_gated, may, urgent_now,
)
from .schema import (CURRENT_GENERATION, KEYS, aliases_for, coarse,
                     day_phases, units)
from .verdicts import compute_verdicts
from .questions import open_questions
from .weeks import session_weeks


# WHERE A PRECISE TIME LIVES, per dataset. Only these two have one; a dataset
# with no time in it has no phase, which is a different answer from an empty
# result and is why asking about one raises rather than returning nothing.
PHASE_FIELD = {"weight": "measured_at", "sessions": "start_time"}


def _last_waking(wakings: list, at) -> object:
    """The most recent waking at or before `at`, or None.

    NOT THE ONE SHARING A CALENDAR DATE. A night worker who wakes at 16:00 and
    trains at 02:00 has that session dated to the next day, so a date lookup
    anchors it to a waking that has not happened yet.

    Mixed naive and aware wakings cannot be ordered against each other, so
    each is compared to `at` individually and the comparison that cannot be
    made is skipped rather than guessed (#38).
    """
    if at is None:
        return None
    # A NAIVE TIME IS READ AGAINST THE WAKING'S WALL CLOCK. `comparable`
    # refuses naive against aware and is right to: it will not invent the
    # missing offset. But a weigh-in written "07:06" and a waking written
    # "05:59+00:00" are the same athlete's clock on the same morning, and
    # reading the waking's wall clock puts both in one frame by construction -
    # the case `comparable` already sanctions for two naive stamps.
    #
    # Applied to ANY naive time, not just a bare HH:MM. The first cut keyed on
    # the string being five characters long, so "07:06" was placed and
    # "2030-05-01T18:30:00" - the same clock in the same epistemic position -
    # was refused. Same fact, opposite answers, on a formatting detail.
    #
    # What it assumes, stated because nothing checks it: that the waking's
    # recorded offset is the one the naive time was written in. True of an
    # athlete in one place; false for one who travelled between waking and
    # weighing, and a connector writing sleep_end in UTC for an athlete who
    # is not shifts every boundary by their offset.
    local = at.tzinfo is None
    best = None
    for up in wakings:
        candidate = up.replace(tzinfo=None) if local else up
        _, _, ok = comparable(candidate, at)
        if not ok or candidate > at:
            continue
        if best is None or candidate > best:
            best = candidate
    return best


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
        # ONE VIEWPOINT, EVERYWHERE (#207, and the split it left behind).
        # `build` and `rollup` took theirs from the record while every query
        # surface took the wall clock, so the API and the read model built
        # from the same record disagreed - `goals()` answered zero rows for
        # every fixture in this repo while the built `goal_progress` was full.
        #
        # The record's own horizon is now the default for all of them, and the
        # reason it is safe for the SAFETY surfaces is the one that decided
        # it: answering "what is blocked" as of the last day the record knows
        # about is over-restrictive when a record is stale, while the wall
        # clock silently assumes nothing has changed since the last row. Both
        # are assumptions; only one of them errs toward keeping a gate shut.
        #
        # RESOLVED LAZILY, because finding the horizon reads every dataset and
        # a constructor that did I/O would make `Vitai(root)` expensive for
        # callers that never ask.
        self._on_given = _viewpoint(on)
        self._on_resolved: date | None = None
        # THE CLOCK IS READ HERE AND NOWHERE BELOW. A record with no dated
        # rows has no horizon to take a viewpoint from, and the fallback has
        # to come from somewhere - but reading it lazily would put a
        # `date.today()` deep in the engine, which is exactly what the
        # boundary rule forbids and what a test catches.
        # Only when it will be needed. A caller who named a viewpoint has
        # already answered the question, and reading the clock anyway would
        # make an engine pinned to a past date touch the outside world for a
        # value it never uses.
        self._clock = None if self._on_given is not None else date.today()
        # Per-instance read cache. See `_forget`.
        self._loaded: dict[str, list[dict]] = {}
        # The same rows with their precise tier intact (#205). Two caches
        # rather than one projection per read: the coarsening runs once at
        # load, so no read path can skip it and none pays for it twice.
        self._precise: dict[str, list[dict]] = {}
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
        # COARSENED ON THE WAY BACK OUT (#205). The caller supplied the value,
        # so this withholds nothing it does not already have - which is the
        # argument for leaving it, and it is not enough. An echo is printed by
        # `vitai append` and returned by the MCP `claim` tool, so a harness
        # that logs every tool result logs the address without anything ever
        # naming a release. The write path is not a reason to be a second
        # egress surface.
        return coarse(name, append(self.root / "data", name, record,
                                   device=self.config.device))

    def undated_policy(self, on: date | str | None = None) -> dict:
        """Threshold keys the toml sets and the record has no dated row for.

        THE HALF OF #148 THAT `policy_digest` ONLY MADE DETECTABLE. `as_of`
        reconstructs the record at an instant by filtering on `recorded_at`,
        which is right for everything the record HOLDS. Thresholds live in
        `vitai.toml`, outside the append-only record: dated `thresholds` rows
        overlay it per week, and a week with no row is judged by whatever the
        file says TODAY. So editing a floor in September silently re-judges
        every earlier week that lacked an explicit row, and a reconstruction of
        March returns March's data under September's policy.

        Measured on the shipped corpus rather than argued: 225 judged weeks
        across three personas, and not one dated threshold row anywhere. The
        gap is total, not partial.

        Returns `{key: value}` for the keys in that state - the ones a
        consumer is being handed a verdict about whose standard has no history.
        """
        from .config import THRESHOLD_TYPES
        from .policy import state as policy_state

        when = _viewpoint(on) if on is not None else self.on
        held = policy_state(self.dataset("goals"), self.dataset("thresholds"),
                            when).thresholds
        cfg = self.config
        out = {}
        for key, caster in THRESHOLD_TYPES.items():
            value = getattr(cfg, key, None)
            if value is None or key in held:
                continue
            try:
                out[key] = caster(value)
            except (TypeError, ValueError):
                # A toml value the engine cannot type is a fault in the file,
                # reported by `validate`, and it is not an undated policy - it
                # is not a policy. Passing it through put uncastable text into
                # a consumer's payload and killed `pin-policy` mid-command.
                continue
        return out

    def never_dated_policy(self) -> dict:
        """Threshold keys with no dated row ANYWHERE, at any date.

        A DIFFERENT QUESTION FROM `undated_policy`, and conflating them was a
        defect. That one asks what is undated AT A VIEWPOINT, which is the
        right question for reporting: a week judged before the athlete first
        declared a floor was judged by the toml, and a consumer looking at that
        week should be told so.

        WITH `on` GONE THE TWO NOW COINCIDE for every input a caller can
        reach, and a mutation swapping this for `undated_policy` in
        `pin_policy` passes - which is worth stating rather than papering over
        with a test that proves nothing. They coincide because the horizon
        includes the thresholds rows' own dates, so a dated row is always in
        force at it. The distinction is kept because it is the question a write
        must ask whatever the default happens to make true, and because
        restoring an `on` parameter would silently re-open the defect below.

        This is the question a WRITE has to ask. Pinning on the first answer
        let `pin_policy(on=<a date before an existing row>)` insert a line in
        front of the athlete's own declaration - and `plan_churn` diffs
        consecutive lines with the declaration excluded, so their first
        statement of a floor turned into a flagged LOOSENING, on the surface
        built to catch quiet retreats. The engine rewriting how an athlete's
        line reads is the one thing an append must never manage.
        """
        from .config import THRESHOLD_TYPES

        ever = {str(r.get("key")) for r in self.dataset("thresholds")
                if r.get("key") and r.get("date")}
        cfg = self.config
        out = {}
        for key, caster in THRESHOLD_TYPES.items():
            value = getattr(cfg, key, None)
            if value is None or key in ever:
                continue
            try:
                out[key] = caster(value)
            except (TypeError, ValueError):
                # A value the engine cannot type is a fault in the file, not a
                # policy waiting to be dated. Passing it through killed
                # `pin-policy` mid-command on a validation error the caller
                # could do nothing about from here.
                continue
        return out

    def pin_policy(self, reason: str = "pinned from vitai.toml") -> list[dict]:
        """Give the toml's thresholds the dated history data already has.

        Appends one `thresholds` row per key from `never_dated_policy`, dated
        the record's own horizon, so a later edit to the file stops reaching
        weeks FROM THAT DATE FORWARD.

        IT PROTECTS NOTHING ALREADY JUDGED, and the first version of this
        docstring said otherwise. The row is dated the horizon - the last day
        the record has a row for - and a weekly verdict takes the policy in
        force at its Monday, so protection starts the Monday after. On the day
        you pin, the number of already-judged weeks protected is exactly zero.
        The past cannot be pinned and must not be: the toml has no history,
        which is the defect, and writing one from its present state would bury
        the defect under a fabrication that reads exactly like a record.

        NO `on` PARAMETER, deliberately. An explicit past date is how the first
        version inserted a line in front of the athlete's own declaration.
        There is no legitimate use for pinning a policy at a date the record
        did not reach, and offering one made a foot-gun out of an argument.

        EXPLICIT, NEVER A BUILD SIDE EFFECT. The engine writes to the record
        only when asked - `assert_delivery` is the precedent - and a build that
        appended to the athlete's files would make `vitai build` unrepeatable.

        REFUSES UNDER A KNOWLEDGE CUTOFF. `as_of` filters what this instance
        can SEE, and the file it writes to is not filtered - so a pin through a
        cutoff earlier than an existing pin cannot see that pin and writes a
        second identical row into a file that cannot be un-appended. A write
        whose content is computed from a partial view has no business landing
        in the whole record.

        `set_by` is `onboard`. Not `athlete`: nobody stated this on this date,
        and `plan_churn` copies the author onto its rows, so claiming the
        athlete would put their name on an assertion the engine composed. Not
        `derived` either - nothing was computed. It is a value seeded from
        setup material, which is what `onboard` means.
        """
        if self.as_of is not None:
            raise ValueError(
                "pin_policy writes to the whole record and this instance can "
                "only see part of it (as_of is set). Open the record without "
                "a cutoff to pin its policy.")
        pending = self.never_dated_policy()
        if not pending:
            return []
        when = self.on
        return self.append_many("thresholds", [
            {"date": when.isoformat(), "key": key, "value": value,
             # `change`, not `correction`: a correction asserts the previous
             # line never reflected a real intention, and there is no previous
             # line. It costs no churn either - `never_dated_policy` returns
             # only keys with no row at all, so this is first in its chain and
             # `_edits` excludes the declaration.
             "change_kind": "change", "set_by": "onboard",
             "reason": reason}
            for key, value in sorted(pending.items())])

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
        return [coarse(name, r) for r in append_many(
            self.root / "data", name, records, device=self.config.device)]

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
        """One dataset's live rows: everything recorded, superseded rows gone.

        THE SUPPORTED WAY TO READ A DATASET, said here because the obvious
        alternative is wrong in a way that looks right. Applying `supersedes`
        by hand means getting chains, corrections that correct corrections,
        and the event datasets that never retire at all each correct
        separately. A consumer that tried it dropped every row sharing a
        reference's key, and - not a variant of that bug - dropped each
        correction along with its target, because a correction carries the
        same `<date>/<source>` as the row it names. The record got shorter
        every time someone fixed a typo, and one at a time it looked like
        nothing (#258).

        Rows are raw CLAIMS: what each source said, not what the engine
        decided between them where two disagree. For the adjudicated view,
        one canonical record per quantity per date, use `canonical()`.

        Malformed lines are quarantined rather than raised, so a read
        proceeds from the good rows; `Vitai.load_report()` names what was
        dropped. THAT method and not `jsonl.load_report`, which is the
        internal one - pointing a consumer at a private module is how this
        docstring's own issue started. Honours this instance's `as_of`, so a
        reconstruction reads
        the record as it stood at that instant rather than as it stands now.
        """
        return self._rows(name)

    def _rows(self, name: str, precise: bool = False) -> list[dict]:
        """THE ONE PLACE THE PRECISE TIER IS DECIDED (#205).

        The gate belongs at the boundary rather than at the call site, because
        a gate implemented per-caller is correct in the callers somebody
        remembered. Counted before writing this: twenty-five public methods
        hand a caller the same dict that came off the JSONL line, the CLI adds
        thirty-five print sites over them and MCP one, and both the SQLite
        build and the LLM prompt take their rows from `datasets()`. Every one
        of those reads through here.

        So the DEFAULT PROJECTION STRUCTURALLY CANNOT CARRY the precise tier:
        it is dropped once, at load, and every surface downstream inherits it
        without being taught anything. The precise rows are kept beside it and
        reachable only by naming a release, which is `precise()`.

        The engine's own arithmetic reads this door too, and that is fine
        rather than lucky: nothing computes on a precise tier, and a field the
        maths needed would be a field this classification should not hold. If
        one ever is, it wants an internal reader here and a reason written
        down, not a quiet exception.
        """
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        if name not in self._precise:
            self._precise[name] = load(self.root / "data", name,
                                       as_of=self.as_of)
            self._loaded[name] = [coarse(name, r) for r in self._precise[name]]
        return self._precise[name] if precise else self._loaded[name]

    def precise(self, name: str, release: str) -> list[dict]:
        """One dataset WITH its precise tier, for a named release.

        The other path, and the only one. `release` says what this release is
        for, and it is required because #205's third commitment is that
        permission is per-use rather than a standing flag: a setting toggled
        once and never revisited is a checkbox, not consent. A caller that
        cannot say what it is about to do with an address has not decided to
        do it.

        WHAT THIS DOES NOT YET DO, said plainly rather than implied by
        silence: it does not ask anybody, and it does not record the release.
        The asking is a permission layer this does not build, and the record
        of what left belongs with the dataset that already records what left
        rather than in a second log of its own. Until both exist, `release` is
        a string the caller must compose and a reviewer can grep for - which
        is weaker than a control and stronger than an unnamed accessor.
        """
        if not str(release or "").strip():
            raise ValueError(
                "precise() needs a release naming what this is for. The "
                "precise tier is the one thing here that cannot be un-leaked, "
                "so the call that reaches for it says why")
        return self._rows(name, precise=True)

    def datasets(self) -> dict[str, list[dict]]:
        """Every dataset's live rows, keyed by name. `dataset()` for one.

        Raw claims with supersedes applied, exactly as `dataset()` returns
        them and subject to the same caveats. See `canonical()` for the
        adjudicated view.
        """
        return {name: self.dataset(name) for name in KEYS}

    @property
    def on(self) -> date:
        """The viewpoint every surface answers from.

        What the caller asked for, or the last day this record has a row for.
        Falls back to the wall clock only for a record with no dated rows,
        which has no horizon and nothing whose visibility a viewpoint decides.
        """
        if self._on_given is not None:
            return self._on_given
        if self._on_resolved is None:
            self._on_resolved = self.last_recorded() or self._clock
        return self._on_resolved

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
        self._precise.clear()
        self._resolved = None
        # The horizon moves when a row is appended, so the viewpoint a caller
        # did not name has to be found again.
        self._on_resolved = None

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
            # `set_index` IS BLOCK-SCOPED - "the set's position in its
            # block" - so what orders a session depends on whether a block was
            # stated (#230).
            #
            # WITH one, the counters order everything: a swim medley is four
            # lengths of four strokes in a fixed order, and sorting the name
            # first returned backstroke, breaststroke, butterfly, front crawl.
            # Alphabetical, and not an order anybody swam.
            #
            # WITHOUT one, the exercise is the only scope those indices have,
            # and comparing them across movements invents an order: three
            # deadlifts and three benches numbered 1-3 each interleave into a
            # superset nobody performed. A block-less session is NORMAL, so
            # this is not an edge case, and the name goes back in front where
            # it is doing real work.
            blockless = r.get("block") is None
            name = str(r.get("exercise") or "")
            return (str(r.get("date") or ""),
                    (r.get("session_start") is None,
                     str(r.get("session_start") or "")),
                    counter(r.get("block")),
                    name if blockless else "",
                    *(counter(r.get(k)) for k in ("round", "set_index")),
                    name)

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

    def corrections(self, dataset: str | None = None) -> list[dict]:
        """What each correction in this record actually did (#143).

        `retractions` says a claim came down and what brought it down.
        `dataset` returns the survivor. Neither says WHICH FIELDS MOVED, WHICH
        WAY, or HOW LONG the record held the value it later withdrew - and the
        row that lost is sitting in the file with all three in it.

        ASKED, NEVER RAISED, and that is the design rather than an oversight.
        This does not enter the build's findings and emits no message, no
        severity and no verdict word: a run of same-direction corrections is a
        fact about a file, and the engine bringing it up unprompted would be
        an accusation about a person whatever words it chose. `corrections.py`
        carries the whole argument, including why the count cannot tell an
        honest back-fill from a flattering one and does not pretend to.

        Reads the RAW lines, because the row a correction retired is exactly
        the row `dataset()` removes - so this is the one surface here that
        deliberately does not go through the read door, and the reason is that
        the door drops the half it exists to show.
        """
        from .corrections import characterise

        names = [dataset] if dataset is not None else list(KEYS)
        if dataset is not None and dataset not in KEYS:
            raise KeyError(f"unknown dataset {dataset!r}; one of {sorted(KEYS)}")
        out: list[dict] = []
        for name in names:
            out += characterise(self.root / "data", name)
        # Grouped by dataset, and WITHIN a dataset left in the order
        # `characterise` produced: transaction order, which is the order the
        # runs were counted in. Sorting the lot by `date` looked tidier and
        # put a back-dated correction above the one it followed, so a reader
        # saw `run 2` printed above `run 1`.
        return out

    def route(self, gpx_path, barometric: bool = False):
        """Deterministic tier-1 geometry for one GPS or TCX track (G40).

        Same track in, same numbers out - and each carries the parameter that
        produced it, in `.params`. Never compute route geometry outside this
        call: an improvised script is not reproducible and its numbers are not
        evidence (G85 extended to algorithms).
        """
        from .route import analyse, read_track
        return analyse(read_track(gpx_path), barometric=barometric)

    def best_effort(self, gpx_path, distance_m: float = 10000):
        """The fastest contiguous `distance_m` of one track, or None.

        The question a runner actually asks - "what is my best 10k" - and one
        no field in the record could answer. `sessions` holds a distance and a
        duration, so a 10.48 km run and a 9.74 km run are comparable on
        neither, and a pace would have to be computed from both. The answer
        lives inside the track or nowhere.

        None means the track is shorter than the window or carries no times.
        That is "the record cannot answer this", not zero.

        Read `.basis` before quoting the result. `device` means the window was
        measured against the watch's own cumulative distance, which is an
        observation; `derived` means against the haversine sum, which is not.

        NOT PERSISTED to the read model, so a client cannot reach it (#247).
        """
        from .route import best_effort, read_track
        return best_effort(read_track(gpx_path), distance_m)

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
        # THE MAPS, PASSED FORWARD (#325). Contract 40 and 42 derived which
        # feed and which instrument supplied each field of a merged row, and
        # nothing read them - so the per-value `source` this returns was the
        # whole row's label, which on a merged row is true of none of its
        # fields. One resolution pass already computes both.
        resolved = self.resolution()
        return query.check(resolved["canonical"], when, metric, float(says),
                           type=type, tolerance=tol,
                           provenance=resolved["provenance"])

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

    def questions(self, on: date | str | None = None) -> list[dict]:
        """What the record does not know about what is coming (#224).

        The floor of the asking channel and deliberately nothing above it: a
        deterministic derivation, computable with no model configured, no
        network, no permission layer and no budget.

        DERIVE FEW, DO NOT GENERATE MANY AND SUPPRESS. Every question here
        hangs off a plan that is still ahead, so a record with nothing planned
        produces nothing to ask - by construction, rather than by a filter
        that could be relaxed or left switched off. The engine's urge to ask
        peaks exactly where asking is least welcome, and that property has to
        hold with the budget layer unbuilt.

        IT DOES NOT ASK ANYBODY. There is no surface here that speaks and
        `nudge_ok` is not read; a decline needs somewhere of its own to live
        and lands with whatever asks. `questions.py` carries the whole
        argument, including why the wording is not the engine's to write.
        """
        when = on or self.on
        if isinstance(when, str):
            when = date.fromisoformat(when)
        # `gates` is passed as a FUNCTION, because a clearance has to be
        # judged on the day the thing is planned for rather than on the
        # day somebody asked (#224).
        return open_questions(self.plans(when), self.gates, when)

    def gated(self, activity: str, on: date | str | None = None) -> bool:
        """Is this activity class or session type blocked on a date?

        A BOOL, so an activity nobody has classified comes back False - not
        gated, which reads as permitted. `may()` is the answer that can say
        "nobody has said", and a safety question should be asked there.
        """
        return is_gated(self.gates(on), activity)

    def may(self, activity: str, on: date | str | None = None) -> dict:
        """May this be done today: blocked, allowed, or nobody has said.

        The question a gated athlete actually has. "Am I allowed to run", "is
        walking gated" and "can I bike instead" got the same paragraph,
        because `restricts: impact` was all the gate said and nothing resolved
        it per activity (#275).

        The mapping was never missing: `semantics/session_types.toml` declares
        that a run is `impact` and a walk is not, and the resolver has read it
        correctly all along. What was missing was a way to ask, and a third
        answer for an activity the registry does not know - which `gated()`
        returns as False, and which a consumer must refuse on rather than read
        as allowed.

        Carries the gates that decided it and their own text, so a client can
        show why without inventing the reasoning or paraphrasing a gate.
        """
        return may(self.gates(on), activity)

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
        """Weekly goal attainment: one dict per (week, metric), ISO weeks.

        Each row carries `week`, `metric`, `value`, `target`, the `goal` it
        serves, and a `verdict` from a closed vocabulary - `on_target`,
        `ahead`, `behind`, `no_data`. Where the verdict is `no_data` the row
        also says WHY in `reason`, because one word covered four different
        states distinguishable only by which fields were null (#177). A
        `pending` reason means the question is answerable and not yet, and
        carries `due`: the day the source is expected by, after which the
        reason drops back to `no_input` and the row keeps `due` so a late
        source reads as late rather than as still coming (#202).

        `statistic` says what KIND of number `value` is and `window_days`
        over what population, both from contract 29. They are not decoration:
        one column carried a maximum, a between-window change, a composite
        index and six averages, and `steps` at 9752 for a week is the DAILY
        AVERAGE, so a consumer totalling it reports a week five thousand
        steps a day short of the one that happened. `pain_gate` is the WORST
        day. The safety floors are means over fourteen days on a row keyed by
        one week, which is why the population is stated rather than inferred
        from `week`. Both are null on a refusal, which has no number.

        `today` is the viewpoint, and it defaults to this instance's - not to
        the wall clock. The same rows populate the read model's `verdicts`
        table, so a SQL consumer and an API consumer see one answer.
        """
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
                                medical=d["medical"],
                                raw_daily=self.dataset("daily"),
                                comparability=self.dataset("comparability"))

    def rollup(self, today: date | None = None) -> str:
        """The weekly report as Markdown - the same text `build` writes out.

        Returns the text rather than a path, and writes nothing: `build()`
        is what puts them in `derived/weekly.md`. Weight with its rolling
        average and rate, training by week, the tripwires, the gates and
        escalations in force, and how sparse the record is.

        `today` is the viewpoint, defaulting to this instance's, and it dates
        the report as well as bounding it - a rollup whose header disagreed
        with its own contents is the defect the comments below record.
        """
        d = self.canonical()
        # THE SAME DEFAULT `build` USES (#207), because this renders the same
        # artifact. Left on the wall clock, `rollup()` stamped "Generated
        # <today>" while the `weekly.md` written by `build()` beside it said
        # the record's own date - two renderings of one report disagreeing
        # about when they were made.
        on = today or self.on
        # `today=on`, not `today=today`. Passing the un-defaulted parameter
        # left `build_report` to fall back to its own `date.today()`, so the
        # report itself was still dated by the wall clock while every table
        # around it honoured the pinned viewpoint - a rollup that disagreed
        # with its own contents, and the one artifact #134 most needs to be
        # reproducible.
        return build_report(self.config, d["weight"], d["daily"],
                            d["sessions"], today=on,
                            raw_daily=self.dataset("daily"),
                            gates=self.gates(on),
                            escalations=self.urgent(on),
                            events=self.events(on),
                            comparability=self.dataset("comparability"))

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
        # CANONICAL for the level read, raw for everything else. This method
        # computes over raw claims and the read model's table computes over
        # resolved rows, which is a divergence that predates this change and
        # is not its to settle - but a LEVEL goal reads one row and reports
        # it, so on the raw path it would score a claim the precedence ladder
        # explicitly demotes. A memory-logged figure beating the scale it
        # contradicts is the #140 finding arriving through a new door.
        return goal_progress(d["goals"], d["thresholds"], d["daily"],
                             d["sessions"], on, events=d["events"],
                             weight=self.canonical("weight"))

    def project(self, dataset: str, values: dict,
                on: date | str | None = None) -> list[dict]:
        """If I do this, what then? A proposed act, against declared goals.

        "Can I open that bag of crisps" is not a status question. Everything
        else here reports what IS; this reports what WOULD BE, which is the
        register people actually use with a partner or a coach (#193).

        NUTRITION ONLY, AND STATEMENT ONLY, and the boundary is the whole
        design. The purpose sentence says this engine logs nutrition and
        BUILDS TRAINING PROGRAMMES - two different entitlements in one breath.
        So this says what a proposed intake would do to a target the athlete
        declared, and never whether to. The training half is in scope for
        advice and is not built here; an app that answered both in the same
        voice would have quietly widened its own purpose.

        A HYPOTHETICAL IS NOT A CLAIM. Nothing here writes: no append, no
        resolution, no rollup, no emission. The append path already refuses
        caller-supplied provenance; a projection needs the stronger property
        of not being written at all, and `test_a_projection_leaves_the_record
        _byte_identical` is what holds it.

        Arithmetic on the athlete's own numbers, against his own declared
        target. Nothing is imported and nothing is looked up: a projection
        built from a food table would be a figure about somebody else.

        Returns one row per affected goal, carrying `now`, `proposed` and
        `projected`. `projection` is true on every one, because a number that
        could be mistaken for something the record holds is the one thing this
        must never produce.

        NO `answers` TOKEN, deliberately. Contract 32's axis is keyed on
        VERDICT METRICS - `intake_floor`, `weight_rate` - and a goal names a
        record FIELD. Mapping one onto the other here would be inventing a
        field-level vocabulary at the call site, which is the silent default
        that field was closed-world to prevent. What can be said without
        inventing anything: this is one logged quantity against a target the
        athlete declared, which is the shape contract 32 calls a magnitude for
        `intake_floor`.
        """
        if dataset not in KEYS:
            raise KeyError(f"unknown dataset {dataset!r}; one of {sorted(KEYS)}")
        if dataset != "daily":
            raise ValueError(
                f"projection is nutrition-only for now: {dataset!r} is not "
                "`daily`. The purpose sentence permits programming TRAINING, "
                "which is a wider entitlement and its own work (#193)")
        unknown = sorted(set(values) - set(KEYS[dataset]))
        if unknown:
            raise KeyError(
                f"{dataset} has no {unknown}. A projection is arithmetic on "
                "this record's own fields; a quantity it has never seen is "
                "one the athlete has to state before it can be projected")

        when = _viewpoint(on) or self.on
        rows = []
        for goal in self.goals(when):
            if goal.get("period") != "daily" or goal.get("dataset") != dataset:
                continue
            proposed = values.get(str(goal.get("metric")))
            if not isinstance(proposed, (int, float)) or isinstance(
                    proposed, bool):
                continue
            counted = goal.get("counted")
            projected = (counted or 0) + float(proposed)
            standing = _standing(
                {"polarity": goal.get("polarity"),
                 "target_hi": goal.get("target_hi")},
                projected, goal.get("target"))
            rows.append({
                "projection": True,
                "slug": goal.get("slug"),
                "metric": goal.get("metric"),
                "polarity": goal.get("polarity"),
                "target": goal.get("target"),
                "now": counted,
                "proposed": float(proposed),
                "projected": round(projected, 3),
                "room_left": standing["room_left"],
                "breach": standing["breach"],
                "progress_pct": standing["progress_pct"],
                "distance": standing["distance"],
            })
        return rows

    def plans(self, on: date | str | None = None) -> list[dict]:
        """What days were MEANT to be, resolved and unresolved (#221).

        Ordered by the day the plan is FOR rather than the day it was made,
        because that is the axis a reader is asking about, with the phase
        breaking a tie so two plans for one day keep the order they were
        intended in.

        SILENCE IS NOT A LAPSE. An `unresolved` plan is one nobody has
        answered about, and this never fills one in. A consumer counting
        adherence over these rows must state how many were unresolved or it
        repeats the defect that let a mostly-unjudgeable record display
        near-perfect adherence.

        `overdue` is the one thing computed here: the plan's day has passed
        and it is still unanswered. That is a fact about the RECORD - a
        question outstanding - and not a fact about the athlete, which is why
        it is not called missed.
        """
        when = _viewpoint(on) or self.on
        rows = []
        for plan in self.dataset("plans"):
            for_date = str(plan.get("for_date") or "")
            rows.append(dict(plan, overdue=bool(
                for_date and for_date < when.isoformat()
                and plan.get("outcome") in (None, "unresolved"))))
        # FROM THE REGISTRY, not from a dict written here (#212). This was
        # three values inline - `morning`, `afternoon`, `evening` - which is
        # a vocabulary living inside one consumer: no entry in `semantics/`,
        # no validation on the field, and `night` unaddable without finding
        # this line. Open mHealth's `part-of-day` has four, and a plan for a
        # night shift sorted alongside one with no phase at all.
        phases = {slug: n for n, slug in enumerate(day_phases())}
        return sorted(rows, key=lambda r: (
            str(r.get("for_date") or ""),
            phases.get(str(r.get("for_phase") or ""), 9),
            str(r.get("slug") or "")))

    def plan_for(self, session: dict) -> dict | None:
        """The plan a session fulfilled, or None where it cites no plan.

        The SESSION cites the plan and not the other way round - the direction
        FHIR arrived at in R5 when it replaced `activity.detail` with
        `plannedActivityReference` and `performedActivity`. Here the citation
        lives on the plan as `session_ref`, so this walks it backwards.
        """
        ref = str(session.get("date") or "")
        if not ref:
            return None
        for plan in self.dataset("plans"):
            if str(plan.get("session_ref") or "") == ref:
                return plan
        return None

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

    def milestone_ladder(self, slug: str | None = None) -> list[dict]:
        """Every milestone a goal has THIS BUCKET, passed or not (#330).

        `milestones()` returns a row per milestone crossed, which answers what
        was passed and when. A client drawing a milestone surface needs the
        rest too: how many rungs there are, which are still ahead, and which
        is next. Without that it can only say "3 milestones", and a bare count
        on a screen is worse than silence because it advertises detail the
        surface cannot reach.

        THIS BUCKET, NOT ALL OF HISTORY, and measuring is what settled it. A
        weekly floor goal crosses 25% most weeks: `marcus`'s `weekly-volume`
        has 33 crossings against four fractions, so a lifetime ladder would
        collapse 33 real events into four rungs and call the goal three
        quarters done forever. Milestones key on (slug, bucket, fraction)
        because the achievement is "a quarter of the way through THIS week",
        and the ladder has to mean the same thing the minting does.

        The bucket is on every row, so a consumer never has to infer which
        period it is looking at. A goal with no bucket-scoped period - one
        scored over all of time - gets its whole ladder here, which is the
        same rule with one bucket.

        DERIVED, NEVER STORED, and nothing is asked of the athlete: the ladder
        is `MILESTONE_FRACTIONS` against a target the goal already declares.
        Published rather than left to the consumer for the reason `units` and
        `aliases` are - a client slicing a target into quarters itself is
        copying a rule this engine owns, and the copy is wrong the day the
        tuple changes.

        Per rung: `fraction`, the `value` it sits at, whether it is `passed`,
        `passed_on` where it is, and `next` for the lowest unpassed one.
        Ordered by fraction, so drawing it is a loop.

        `value` COMES FROM THE TARGET IN FORCE NOW, and `passed_target` says
        what the crossing was measured against, because those come apart: this
        athlete's target moved 95 to 90, so a rung sitting at 22.5 today was
        crossed at 23.75. Reporting only one of them would make a client
        render a date against a number that never applied on it.

        ONLY GOALS THAT MINT. A goal the engine refuses to mint for - an
        approach with no baseline, a cap, a daily bucket, a completed goal -
        gets an EMPTY ladder rather than an invented one, for the reasons
        `_milestones` records. An empty list says "this goal has no milestone
        surface"; a ladder of quarters would say something the engine has
        deliberately declined to say.
        """
        from .contributions import MILESTONE_FRACTIONS, mints_milestones

        # NO `today` PARAMETER, and the first cut shipped one. It was
        # unwitnessed - removing it passed the whole suite - and worse, it
        # could not work: `goals(on)` reconstructs as of a date while
        # `milestones()` is full history, so asking for a Monday returned
        # crossings from the Tuesday after. A mixed-epoch row in an engine
        # whose whole point is keeping the two clocks apart. The ladder reads
        # this instance's viewpoint, which `Vitai(on=...)` already sets.
        #
        # `goals()` IS the progress table, so one call gives the goals in
        # force, the bucket each is scored in, and how far each has got.
        standing = self.goals()
        crossed: dict[tuple[str, object, float], dict] = {}
        for m in self.milestones():
            # ONE ROW PER KEY, so there is nothing to tie-break: `_milestones`
            # dedupes on exactly (slug, bucket, fraction) through its `minted`
            # set. The first cut kept the earliest of several, which looked
            # careful and was unreachable - flipping it to the latest passed
            # every test, because the case cannot arise.
            crossed[(str(m["goal"]), m["period"], float(m["fraction"]))] = m

        out: list[dict] = []
        for goal in standing:
            name = str(goal.get("slug") or "")
            if slug is not None and name != slug:
                continue
            # TWO GATES, because `mints_milestones` is fed two different
            # shapes and only answers about one. The minter passes it a goal
            # DECLARATION; here it gets a progress ROW, so the lifecycle key
            # it reads is absent and every cancelled and proposed goal walked
            # through. Measured on the corpus: seven of eleven ladders were
            # for goals that have never minted a milestone and four for goals
            # that never can.
            #
            # The engine published "next milestone: 16.5 kg" against a
            # body-weight goal whose own progress row carries a NULL
            # `progress_pct`, because `goal_progress` deliberately refuses to
            # score it. A derived surface may not answer a question the table
            # it derives from has declined.
            if not mints_milestones(goal):
                continue
            # SCOREABLE AND LIVE. A null `counted` is the progress table
            # saying it did not score this goal - weight-scoped, externally
            # verified, or fed by a dataset the contribution engine does not
            # read - and a ladder over a number that does not exist is an
            # invented surface. A cancelled or proposed goal is not being
            # pursued, and rendering its rungs beside a live goal's is how
            # `yasmin`'s two abandoned attempts read exactly like her current
            # one.
            if goal.get("counted") is None:
                continue
            if str(goal.get("lifecycle_status") or "") != "active":
                continue
            target = float(goal["target"])
            bucket = goal.get("bucket")
            # A FLOW goal accumulates into `counted`; a LEVEL goal reports its
            # latest observation in `observed` (#273). Whichever side holds
            # the number is how the two shapes are told apart, and the rung
            # question - has progress reached this value - is the same either
            # way.
            #
            # NO `observed` FALLBACK, and the commit before this one kept one
            # while admitting it was untested. Review made it fire, and what
            # it did was absurd: a "stay above 60 kg" goal reported all four
            # rungs - 15, 30, 45, 60 kg - permanently passed, because the
            # athlete did not climb to 61 kg from zero. Fractions of a LEVEL
            # are meaningless without a baseline, which is the same reason
            # `_milestones` refuses approach goals outright. The scoreability
            # gate above already excludes every level goal in the corpus; this
            # removes the branch that would have invented a ladder for one.
            reached = float(goal["counted"])
            rungs = []
            for frac in MILESTONE_FRACTIONS:
                hit = crossed.get((name, bucket, frac))
                value = round(target * frac, 3)
                rungs.append({
                    "goal": name,
                    "period": bucket,
                    "fraction": frac,
                    "value": value,
                    "target": target,
                    "reached": reached,
                    "passed": reached >= value,
                    # ONLY ON A PASSED RUNG. A target raised mid-bucket
                    # leaves a crossing at a fraction whose value the athlete
                    # is now BELOW, and reporting its date beside
                    # `passed: false` shipped a row that was simultaneously
                    # unpassed, dated and next.
                    "passed_on": hit["date"] if (hit and reached >= value)
                    else None,
                    "passed_target": hit["target"] if (hit and reached >= value)
                    else None,
                    "label": hit["label"] if (hit and reached >= value) else None,
                    "next": False,
                })
            for rung in rungs:
                if not rung["passed"]:
                    rung["next"] = True
                    break
            out += rungs
        return out

    def crossings(self) -> list[dict]:
        """Round-number and personal-first milestones, goal-independent and
        history-wide (#370).

        NOT `milestones()`. That table needs a declared goal and a fraction
        of its target; "you broke 80 kg" and "that is your lowest ever" are
        true or false of the weight series alone, goal or no goal, and
        `milestones`' columns have nowhere honest to put either fact.

        WEIGHT ONLY, TODAY. `crossings.compute_crossings` takes the field to
        read as a parameter rather than assuming `kg` internally, so a second
        metric is a second call elsewhere rather than a rewrite of that
        function - but this accessor is the one and only place that
        parameter is bound, because `kg` is the sole metric #370 asks for.

        CANONICAL, NOT RAW. `self.canonical("weight")` is the same adjudicated
        series `report.py` builds its trend from - one row per date - so a
        day resolved from two competing sources counts once here too.
        """
        return compute_crossings(self.canonical("weight"), metric="kg")

    def capability(self, origin: str, measures: str,
                   on: date | str | None = None,
                   condition: str | None = None) -> dict:
        """What an instrument was competent at, as of a date (#171).

        Never None. An instrument nobody has written a capability row for
        answers `unknown`, which is a value in the vocabulary rather than a
        null a consumer has to interpret - and distinct from `absent`, which
        says the instrument does not observe this at all.

        NO DEFAULT OUTSIDE THE RECORD. A capability table shipped in
        `semantics/` would make every unstated instrument resolve to whatever
        this build says today, which is #148's defect exactly: there,
        baselines lived in a mutable file, dated rows overlaid it, and a week
        with no row was judged under today's policy.

        `condition` scopes the question. A wrist sensor can measure heart rate
        seated and be a proxy for it at threshold, so a statement is about one
        instrument measuring one thing under one condition.
        """
        return capability(self.dataset("capabilities"), origin, measures,
                          on or self.on, condition=condition)

    def capabilities(self, on: date | str | None = None) -> list[dict]:
        """Every capability statement in force, most recently dated first.

        The stated ones only. Everything unstated is `unknown` and there is no
        list of it - the set of instruments nobody has said anything about is
        not a thing the record holds.
        """
        from .policy import _in_force

        when = (on or self.on)
        when_s = when.isoformat() if isinstance(when, date) else str(when)
        rows = _in_force(self.dataset("capabilities"), "capabilities", when_s)
        return sorted(rows.values(),
                      key=lambda r: (str(r.get("date") or ""),
                                     str(r.get("origin") or ""),
                                     str(r.get("measures") or "")),
                      reverse=True)

    def comparability(self, field: str, origin_a: str, origin_b: str,
                      on: date | str | None = None) -> dict:
        """Are these two instruments on the same footing for this field? (#33)

        Never None. Silence answers `not_comparable`, which is a value in the
        vocabulary rather than a null a consumer has to interpret - and it is
        #33's own acceptance criterion, not an engineering default: deriving
        a trend across a source change needs an explicit statement that the
        two sides are on the same footing, never an assumption because both
        are called weight.

        NO DEFAULT OUTSIDE THE RECORD, `capability`'s own reasoning one
        dataset over: a comparability table shipped in `semantics/` would
        make every unstated pair resolve to whatever this build says today.

        ORDER-INSENSITIVE. Asking about `(origin_a, origin_b)` answers
        exactly as asking about `(origin_b, origin_a)` would, because
        whether two instruments agree is one fact about the pair and not
        about which one a caller happened to name first.
        """
        return comparability(self.dataset("comparability"), field, origin_a,
                             origin_b, on or self.on)

    def instrument(self, origin: str,
                   on: date | str | None = None) -> dict | None:
        """The instrument reporting as `origin` on `on`, or None (#311).

        None means unregistered, and a caller should render what it renders
        today. The register adds a name and a provenance to an identity that
        already works without one, so an empty register must not read as a
        populated one.
        """
        from .policy import instrument as resolve_instrument

        return resolve_instrument(self.dataset("instruments"), origin,
                                  on or self.on)

    def instruments(self, on: date | str | None = None) -> list[dict]:
        """Every instrument reporting on `on`, by origin.

        DATED, not the whole register. Asking for "my instruments" on a date
        in 2027 must not list the watch bought in 2030 - which is the same
        rule the resolver enforces, and listing them undated would be the way
        round it.
        """
        from .policy import instrument as resolve_instrument

        rows = self.dataset("instruments")
        seen = sorted({str(r.get("origin")) for r in rows if r.get("origin")})
        found = [resolve_instrument(rows, origin, on or self.on)
                 for origin in seen]
        return [r for r in found if r is not None]

    def phases(self, dataset: str | None = None,
               on: date | str | None = None) -> list[dict]:
        """What part of the athlete's own day each timed row fell in (#212).

        THE COARSE TIER, derived from the precise one and from nothing else.
        `weight.measured_at` and `sessions.start_time` are the measured data
        that exists - 97% and 99% populated in the shipped corpus - and the
        athlete's sleep is what says which part of whose day they are in.

        `phase` is None wherever the anchor is missing, and the row still
        comes back so a consumer can see how much of the record is
        unanchored rather than reading an absence as a small number. That is
        the half a returned list of only-the-answerable rows would hide.

        NOT STORED, deliberately and for now. The issue argues for deriving at
        write and storing, on the grounds that a value computed on the way out
        can be computed wrongly on the way out - which is right, and the
        decision that governs this says the athlete's timestamps PROPOSE and
        sleep CONFIRMS, so an unconfirmed phase is not a fact to write down.
        Storing the confirmed ones needs a channel for the athlete to confirm
        the rest, which is #224's work. Until then this computes and says what
        it is anchored on, and nothing in the record claims a phase it cannot
        support.
        """
        # EVERY WAKING, IN ORDER, because the anchor is not "the sleep row
        # sharing this calendar date". That is a midnight-anchored lookup
        # under an athlete-anchored rule, and it fails the one athlete the
        # rule exists for: a night worker who wakes at 16:00 and trains at
        # 02:00 has that session dated to the NEXT day, so keying on the date
        # anchors it to a waking that has not happened yet and calls ten hours
        # into her day "night".
        wakings = sorted(
            filter(None, (parse_time(r.get("sleep_end"))
                          for r in self.dataset("daily"))))
        if dataset is not None and dataset not in PHASE_FIELD:
            raise KeyError(
                f"no timed field on {dataset!r}; phases are derived for "
                f"{sorted(PHASE_FIELD)}. A dataset with no time in it has no "
                f"phase, and returning nothing would say this record has no "
                f"timed rows at all")
        wanted = tuple(PHASE_FIELD) if dataset is None else (dataset,)
        when = on if on is not None else None
        when_s = (when.isoformat() if isinstance(when, date)
                  else str(when) if when is not None else None)
        out: list[dict] = []
        for name in wanted:
            field = PHASE_FIELD[name]
            for row in self.dataset(name):
                at = row.get(field)
                if not at or (when_s is not None and row["date"] != when_s):
                    continue
                # `measured_at` is HH:MM local and `start_time` is a full
                # stamp. Both are the athlete's wall clock, so a bare time is
                # read against its own row's date.
                stamp = at if len(str(at)) > 5 else f"{row['date']}T{at}:00"
                anchor = _last_waking(wakings, parse_time(stamp))
                # A BARE LOCAL TIME IS COMPARED AGAINST THE ANCHOR'S LOCAL
                # WALL CLOCK, not against its instant. `comparable` refuses
                # naive against aware, correctly: it will not invent the
                # missing offset. But a weigh-in written "07:06" and a waking
                # written "05:59+00:00" are the SAME athlete's clock on the
                # same morning, and reading the anchor's wall clock puts both
                # in one frame by construction - which is the case `comparable`
                # already sanctions for two naive stamps. Without this every
                # weigh-in in the corpus is unanchored, which is 260 of the
                # 700 timed rows in one persona and the whole dataset the
                # issue was raised about.
                anchor = anchor.isoformat() if anchor is not None else None
                out.append({
                    "dataset": name, "date": row["date"], "at": at,
                    "phase": day_phase(stamp, anchor),
                    "anchored_on": anchor,
                })
        return sorted(out, key=lambda r: (r["date"], r["dataset"], str(r["at"])))

    def churn(self, today: date | None = None) -> list[dict]:
        """Policy edits, with the loosening-after-a-miss flag (G20)."""
        d = self.datasets()
        return plan_churn(d["goals"], d["thresholds"], self.verdicts(today=today),
                          events=d["events"])

    def derived(self, name: str) -> list[dict]:
        """One DERIVED table's rows, by the name the contract gives it.

        The read model's tables are the consumer contract, and a consumer
        reads that contract by TABLE NAME. `best_efforts` had no public path
        at all, so the only ways in were a private attribute, a direct query
        against the table this contract exists to insulate consumers from, or
        re-parsing the tracks - at which point the number is the caller's
        claim rather than this engine's (#267, and #257 three weeks earlier).

        THESE ARE NOT ALIASES FOR THE NAMED ACCESSORS, and the difference is
        not cosmetic. `goals()` computes `goal_progress` over `datasets()` -
        RAW claims - while this returns the table, computed over the resolved
        canonical rows. On a record where one session reached it twice, the
        two report different progress against the same goal, because the raw
        read counts the duplicate. `contributions()` differs the same way and
        `churn()` will as soon as a contested goal or threshold row exists.
        Which of the two is right is a live question and not this method's to
        settle; what this method owes a caller is to say they differ. Only
        `resolution()` and `retractions()` return the same objects.

        Rows are the derivation's own output, which may carry MORE than the
        table declares: `resolution` rows carry `by_capture` and `gates` rows
        carry `restriction`, neither of which is in the contract's column
        list, so SQLite drops them and this does not. The declared columns are
        the contract; the extras are visible here and must not be relied on.

        What DOES survive intact is anything saying what kind of number a
        value is - `best_efforts.basis` above all. `device` means measured
        against the watch's own cumulative distance and `derived` means
        against the engine's haversine sum; on a real 11 km track the two
        differ by twenty seconds over ten kilometres, so a time quoted
        without it has thrown away its own epistemic class.

        Computed fresh on every call. A cache here was stale the moment
        `vitai.toml` changed under it - `verdicts()` re-reads the config per
        call, so a cached `derived("verdicts")` disagreed with it after a
        threshold edit with no write in between, which is two answers to one
        question from one instance.
        """
        if name not in DERIVED_TABLES:
            raise KeyError(f"unknown derived table {name!r}; one of "
                           f"{sorted(DERIVED_TABLES)}")
        return self._derivations(self.resolution(), today=self.on).get(
            name) or []

    def session_weeks(self, on: date | str | None = None) -> list[dict]:
        """How far and how often, per week, per the engine's type vocabulary.

        The chart every client draws and none of them should compute. One row
        per (week, type), plus a row per week with no sessions so a gap reads
        as a gap rather than as time compressing - `sessions` is 0 there.

        Counts what was LOGGED. A week of zeros says the record holds nothing
        for it, which is not the same fact as a week nothing happened in, and
        the engine cannot tell those apart without coverage. `distance_km` and
        `duration_s` sum only the rows carrying one and are null where none
        did, so a count of 3 beside a distance drawn from 1 is what a partly
        logged week honestly looks like.

        Same rows as the read model's `session_weeks` table.
        """
        d = self.canonical()
        when = on if on is not None else self.on
        return session_weeks(d["sessions"], when)

    def _best_efforts(self, sessions: list[dict]) -> list[dict]:
        """The fastest 1k, 5k, 10k, half and full of every stored track (#247).

        THE QUESTION A RUNNER ASKS FIRST, and one no field could answer:
        `sessions` holds a distance and a duration, so a 10.48 km run and a
        9.74 km run are comparable on neither, and a pace computed from both
        averages the warm-up in. The answer lives inside the track or nowhere,
        and a client that went looking for it had to parse the GPX itself -
        at which point the number is the client's claim rather than this
        engine's.

        `basis` SURVIVES INTO THE ROW, and it is the load-bearing column.
        `device` means the window was measured against the watch's own
        cumulative distance, which is an observation; `derived` means against
        the haversine sum this engine computes, which is not. A consumer that
        cannot tell them apart reads both as a time trial.

        `seconds` is ELAPSED. A stop inside the window counts, because
        excluding it would be the engine deciding which pauses were real -
        which is why the column is not called `moving_time`.

        Each track is parsed ONCE per build however many sessions name it. A
        record with a thousand runs pays for a thousand parses on every build,
        and the answer there is a cache keyed by track content rather than
        skipping the work; that is a measurement question and is not guessed
        at here.
        """
        from .route import best_efforts, read_track

        seen: dict[str, list[dict]] = {}
        out: list[dict] = []
        for row in sessions:
            ref = row.get("track")
            if not ref or ref in seen:
                continue
            path = self.root / str(ref)
            if not path.exists():
                # A broken pointer is reported by `validate` and never fails a
                # build (#43): the session is the fact and the track is an
                # attachment.
                seen[str(ref)] = []
                continue
            try:
                efforts = best_efforts(read_track(path))
            except Exception:
                seen[str(ref)] = []
                continue
            seen[str(ref)] = [{
                "track": str(ref), "date": row.get("date"),
                "distance_m": e.distance_m, "seconds": round(e.seconds, 3),
                "start": e.start.isoformat(), "end": e.end.isoformat(),
                "basis": e.basis} for e in efforts]
            out += seen[str(ref)]
        return sorted(out, key=lambda r: (r["track"], r["distance_m"]))

    def _derivations(self, resolved: dict, today: date | None = None,
                     cfg: Config | None = None) -> dict[str, list[dict]]:
        d = resolved["canonical"]
        cfg = self.config if cfg is None else cfg
        contributions, milestones = compute_contributions(
            d["goals"], d["thresholds"], d["daily"], d["sessions"])
        verdicts = compute_verdicts(cfg, d["weight"], d["daily"],
                                    d["sessions"], today=today,
                                    goals=d["goals"], thresholds=d["thresholds"],
                                    medical=d["medical"],
                                    raw_daily=self.dataset("daily"),
                                    comparability=self.dataset("comparability"))
        on = (today or self.on).isoformat()
        return {
            "session_weeks": session_weeks(d["sessions"], on),
            "best_efforts": self._best_efforts(d["sessions"]),
            "verdicts": verdicts,
            "contributions": contributions,
            "milestones": milestones,
            # #370: computed directly off `resolved`'s own canonical rows,
            # the same reason `contributions`/`milestones` above are - so a
            # build and `crossings()` never see two different resolutions of
            # one record because one read `self.resolution()` a second time.
            "crossings": compute_crossings(d["weight"], metric="kg"),
            "plan_churn": plan_churn(d["goals"], d["thresholds"], verdicts,
                                     events=d["events"]),
            "goal_progress": goal_progress(d["goals"], d["thresholds"],
                                           d["daily"], d["sessions"], on,
                                           events=d["events"],
                                           weight=d["weight"]),
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
        on = today or self.on
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
                         today=on, raw_daily=self.dataset("daily"),
                         gates=derivations["gates"],
                         escalations=urgent_now(derivations["escalations"],
                                                on=on),
                         events=self.events(on),
                         comparability=self.dataset("comparability")),
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
        from .schema import (corrections_awaiting_their_target,
                             corrections_that_did_not_apply,
                             impossible_claim_problems, recorded_at_problems,
                             period_advisories, polarity_advisories,
                             protocol_pin_advisories,
                             side_advisories,
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
        # Kept for `protocol_pin_advisories` below, which needs `protocols`
        # rows while validating `weight` and `measurements` - and `protocols`
        # is registered into `KEYS` after both of them (#171 track 2 landed
        # long after the founding datasets), so it has not been read yet at
        # the point in this loop where weight or measurements is reached.
        # Deferring the call to after the loop, once every dataset has been
        # read once, is cheaper and simpler than re-reading protocols.jsonl
        # a second time to get it early.
        dataset_rows: dict[str, list[tuple[int, dict]]] = {}

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
                    found_problems = validate_record(name, rec)
                    if not found_problems:
                        continue
                    # ALREADY CORRECTED IS NOT STILL WRONG (#245). A problem
                    # on a line a later line has replaced describes a mistake
                    # that was already caught. It cannot be fixed, because the
                    # line cannot be edited, so reporting it as a problem
                    # means the number can never reach zero - and a validator
                    # whose output can never reach zero is one people stop
                    # reading, including for the problems that ARE actionable.
                    #
                    # Not silenced: the line really is malformed and the log
                    # really does contain it, and a record that hid its own
                    # history of mistakes would be a worse record. It is
                    # reported quietly, and says which line replaced it.
                    by = _superseded_by(name, rec, found)
                    if by is not None:
                        advisories += [
                            f"{path.name} line {n} (already corrected by line "
                            f"{by}): {p}" for p in found_problems]
                    else:
                        problems += [f"{path.name} line {n}: {p}"
                                     for p in found_problems]
                # PER FILE, unlike the checks below: the rule is "this file's
                # clock started", and a file is what has a clock.
                advisories += unstamped_after_the_clock_started(path.name,
                                                                found)
                rows += found
            dataset_rows[name] = rows
            # File-level: transaction time must be monotonic and tie-free
            # (#37). Neither is a property of any single line.
            problems += recorded_at_problems(name, rows)
            problems += unranked_source_problems(name, rows, ranked)
            problems += impossible_claim_problems(name, rows)
            # ADVISORY since #239, and the demotion is the point of that
            # change. While one reference retired every matching line, an
            # ambiguous correction DELETED data, and failing the build was
            # proportionate to that. It now retires one row deterministically
            # - the most recent - so what is left is that the author may have
            # meant another. That is worth saying and not worth refusing a
            # build over, and a record whose only fault is a shape the engine
            # already handles has no legal path to green (#38).
            advisories += supersedes_problems(name, rows)
            # A PROBLEM, NOT AN ADVISORY (#210). A correction that landed and
            # retired nothing leaves the value it was meant to replace in
            # place, and the write reported success - so silence here is the
            # thing that made all three recorded instances invisible. The
            # append path refuses new ones; this is how the ones already in a
            # record stop being a note somebody has to notice.
            #
            # It is repairable, which is what makes refusing fair: appending
            # the correction again clears the one that sorted too early,
            # because a reference retires earlier corrections naming it as
            # well as its target.
            # TWO CAUSES, TWO CATEGORIES (#210). A correction whose target is
            # here and survived anyway leaves the wrong value in place and no
            # waiting fixes it - a problem. A correction whose target has not
            # synced yet is the ordinary mid-sync state and applies itself
            # when the other writer's file lands - an advisory. Escalating
            # both together made an ordinary offline-first record fail.
            problems += corrections_that_did_not_apply(name, rows)
            advisories += corrections_awaiting_their_target(name, rows)
            advisories += timestamp_advisories(name, rows)
            if name == "goals":
                advisories += polarity_advisories(rows)
                advisories += period_advisories(rows)
            if name == "medical":
                advisories += side_advisories(rows)
            # A missing track file is NOT a missing session: the session is
            # the fact and the track is an attachment, so a broken pointer is
            # reported and never fails the build (#43).
            for n, rec in rows:
                if (t := rec.get("track")) and not (self.root / str(t)).exists():
                    advisories.append(
                        f"{name}.jsonl line {n}: track {t!r} is not in this "
                        "repo - the session stands, but its geometry cannot "
                        "be rebuilt")

        protocol_rows = dataset_rows.get("protocols", [])
        for ds in ("weight", "measurements"):
            advisories += protocol_pin_advisories(
                ds, dataset_rows.get(ds, []), protocol_rows)

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

        # WHICH KIND OF CHANNEL LAST SAID ANYTHING (#146). `last_seen` above is
        # per DATASET and answers how stale each one is. This is the other cut:
        # a record where the watches keep syncing and every line the athlete
        # wrote himself stopped a month ago is not the same record as one where
        # nothing is happening, and `last_seen` cannot tell them apart because
        # both channels write into the same datasets.
        #
        # Read over the RAW rows, not the canonical ones. Resolution picks one
        # claim per contest and discards the rest, so a manual line that lost
        # to a device line would take the athlete's own voice out of the count
        # - the silence would be the ladder's, not his.
        from .provenance import channel_liveness
        # THE DATASET MAPPING, not a flat list: `journal` and `checks` have no
        # `capture` column, and their initiative is a property of the dataset.
        # Flattened, the one dataset that is nothing but the athlete writing
        # sentences was invisible to the axis that asks whether he wrote.
        #
        # GUARDED like every other derived section (see this method's own rule
        # above), so a failure here is named in `unavailable` rather than
        # taking down a brief whose whole job is to still answer.
        channels = section("channels", lambda: channel_liveness(
            self.datasets(), horizon), {})

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
                "channels": channels,
                # THE STANDARD WITH NO HISTORY (#148). Every threshold here is
                # one the toml sets and the record has never dated, so every
                # verdict against it - including one reconstructed for a week
                # two years ago - was judged by the file as it is right now.
                # Editing it re-judges that history silently.
                #
                # Reported beside what is stale and what is missing, because
                # that is what it is: `policy_digest` made the difference
                # detectable and this says which keys it applies to. `vitai
                # pin-policy` stops it happening to weeks from the pin date
                # forward; nothing can protect the weeks already judged, and a
                # backfill from the file's present state would be a fabricated
                # history rather than a fix.
                "undated_policy": section(
                    "undated_policy", lambda: self.undated_policy(when), {}),
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
            # WHAT THAT MEAN IS ACTUALLY OVER (#209). `mean_kg_7d` is the mean
            # of the last seven WEIGH-INS, not of seven days, and on a record
            # with a weekly weigh-in those seven points span six weeks - so a
            # client rendering it as "7d avg" describes a window the record
            # never used. The issue records that exact mistake in a client and
            # the engine was making it too, in the field's own name.
            #
            # The value does not change: a consumer already reading it keeps
            # the number it had. What arrives beside it is the span, so the
            # label can be right.
            "mean_kg_span_days": None,
            "mean_kg_points": None,
            "rate_span_days": None,
            "rate_unobserved_days": None,
            "tripwires": None,
            "disclaimer": DISCLAIMER,
        }
        if len(pts) >= 8:
            recent, earlier = pts[-7:], pts[-14:-7] or pts[-7:]
            vals = [v for _, v in recent]
            prev = [v for _, v in earlier]
            # THE DENOMINATOR HAS TO MEASURE THE SAME THING THE NUMERATOR DOES
            # (#142). It divided by the days between the eighth-from-last
            # weigh-in and the last, while the numerator compares the mean of
            # the last seven against the mean of the seven before them - two
            # different spans. Where weigh-ins are dense they are near enough
            # the same; where they are not they are unrelated, and on a real
            # corpus the comparison reached over 221 days while the divisor
            # counted 116.
            #
            # Two block means are separated by the distance between their
            # CENTRES, which is what this now divides by. On flat clusters
            # either side of a fourteen-month silence the old arithmetic
            # reported losing 3.43 kg/week - a rate nobody could have lost,
            # from a record in which no observed reading ever changed.
            days = _days_between_centres(earlier, recent)
            if days:
                rate = (mean(prev) - mean(vals)) / days * 7
                out["rate_kg_per_week"] = rate
                out["mean_kg_7d"] = mean(vals)
                out["mean_kg_points"] = len(vals)
                out["mean_kg_span_days"] = (
                    datetime.fromisoformat(pts[-1][0])
                    - datetime.fromisoformat(pts[-7][0])).days
                # WHAT THE RATE ITSELF REACHES OVER, and the largest stretch
                # inside it that nobody observed. `mean_kg_span_days` was
                # added (#209) so a consumer could stop mislabelling the
                # MEAN's window, and the rate then had no span published at
                # all - so a figure reaching over 221 days was rendered
                # against a label saying 114.
                #
                # FACTS, NOT A VERDICT. Whether a rate over a span containing a
                # hole should be reported at all is a refusal predicate this
                # project has already decided belongs to the uncertainty work
                # rather than to a threshold picked here. What the engine can
                # say without inventing anything is how far the figure reaches
                # and how much of that reach it never saw.
                out["rate_span_days"] = (
                    datetime.fromisoformat(recent[-1][0])
                    - datetime.fromisoformat(earlier[0][0])).days
                out["rate_unobserved_days"] = _widest_gap(earlier + recent)
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

        # A CALENDAR WINDOW, NOT THE LAST SEVEN ROWS (#33 item 5, G30). This
        # took `steps[-7:]`, which means "the seven most recent rows that
        # happen to carry steps" - and on a sparse record those can span
        # years. Measured on a record whose steps are 1200 in 2020, 1400 in
        # 2020, 1500 in 2021, 1800 in 2024 and ~9100 last week, this line read
        #
        #     4,743 steps/day over the last 7 logged days (2026-08-07)
        #
        # which is half the athlete's actual figure, dated three days ago so it
        # reads as current, and dragged there by a phone they stopped using six
        # years earlier. That is #33's own sentence - a 2020 smartphone step
        # count must never move a 2026 figure - and G30 is the rule it breaks:
        # "an entry-count slice is not a window".
        #
        # THE WINDOW IS THE ENGINE'S OWN. `within_days` is what the report's
        # tripwires already use, and `over_days` is how it already says what
        # fraction of the window was logged, so a mean never renders as a claim
        # about days nobody recorded.
        from .report import over_days, within_days

        daily = self.dataset("daily")
        window = within_days(daily, self.on, 7, "steps")
        if window:
            vals = [r["steps"] for r in window]
            return (f"{sum(vals) / len(vals):,.0f} steps/day"
                    f"{over_days(len(vals), 7)}")

        # NOTHING IN THE WINDOW IS ITS OWN ANSWER, and a better one than a
        # six-year mean. Saying when the record last held a step count is a
        # fact; averaging across the gap would be the defect above, relabelled.
        logged = sorted(r["date"] for r in daily if r.get("steps") is not None)
        if logged:
            return (f"no steps logged in the last 7 days "
                    f"(last was {logged[-1]})")

        days = [r for r in self.dataset("daily") if r.get("date")]
        if days:
            return f"{len(days)} days logged (latest {days[-1]['date']})"
        return "nothing logged yet - one number is a complete day"


def _superseded_by(dataset: str, rec: dict,
                   rows: list[tuple[int, dict]]) -> int | None:
    """The line that replaced this one, or None if it still stands (#245).

    TWO WAYS A LINE STOPS DETERMINING THE RECORD, and a record uses whichever
    its dataset supports.

    `supersedes` names a line and retires it. And for an identity-keyed
    dataset - `goals`, `medical`, `thresholds` - a later row with the same
    slug simply wins, which is the documented effective-dating pattern and the
    only one available there: four rows of one goal share a line key, so a
    reference retires the most recent rather than the one below it, and no
    sequence of appends reaches the earliest.

    Returns the LINE NUMBER rather than a flag, because "already corrected" is
    only useful if the reader can see by what.
    """
    from .jsonl import identity_of, line_key

    ident = identity_of(dataset, rec)
    for n, other in rows:
        if other is rec:
            continue
        if str(other.get("supersedes") or "") == line_key(dataset, rec):
            return n
    if ident is None:
        return None
    # Effective-dating: the LAST row for this identity is the one in force.
    same = [n for n, other in rows if identity_of(dataset, other) == ident]
    return same[-1] if same and same[-1] != _line_of(rec, rows) else None


def _line_of(rec: dict, rows: list[tuple[int, dict]]) -> int | None:
    for n, other in rows:
        if other is rec:
            return n
    return None


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


def _type_names(types: tuple[type, ...] | None) -> list[str] | None:
    """Python types -> JSON-transportable names. `None` means unconstrained.

    Names rather than the classes themselves, because the consumers that need
    this most are not in Python. A connector written in another language has
    the identical problem and cannot import anything, which #257 flags.
    """
    if types is None:
        return None
    if types == (int,):
        return ["integer"]
    if set(types) == {int, float}:
        return ["number"]
    return sorted({t.__name__ for t in types})


def _days_between_centres(earlier: list, recent: list) -> int:
    """Days between the mean dates of two blocks of weigh-ins (#142).

    Two block means are separated by the distance between their centres. The
    engine divided by the distance between two single points instead - the
    eighth-from-last weigh-in and the last - which is a different span from
    the one the numerator compares, and diverges exactly where the weigh-ins
    are sparse.
    """
    def centre(block: list) -> float:
        return mean(datetime.fromisoformat(when).timestamp()
                    for when, _ in block)

    return round((centre(recent) - centre(earlier)) / 86400)


def _widest_gap(points: list) -> int:
    """The longest stretch between consecutive weigh-ins in a block.

    A FACT RATHER THAN A VERDICT. It says how much of the span the figure
    reaches over was never observed; it does not say whether that makes the
    figure unusable, which is a refusal predicate the uncertainty work owns.
    """
    days = sorted(datetime.fromisoformat(when) for when, _ in points)
    return max((int((b - a).total_seconds() // 86400)
                for a, b in zip(days, days[1:])), default=0)


def field_types(dataset: str | None = None) -> dict:
    """What each field of each dataset may hold, and how it is projected.

    Per field: `types` (the primitives legal when the value is not null, or
    `null` where the engine constrains nothing), `affinity` (the SQLite column
    type this engine gives it), and `container` (true where the value is a
    list, JSON-encoded into a TEXT column).

    #257. `KEYS` was already public and is the documented way to check that a
    writer is not inventing columns. The TYPES were not: they sat in
    `schema._TYPES`, and the affinity in `db._TEXT_COLS`, both private. So a
    consumer building a queryable projection - close to the first thing any
    consumer wants - could check its column NAMES against the engine and had
    to guess or copy everything else.

    One did copy, and the copy went several increments stale: `coverage`,
    `mood`, `feel`, `pain` and five macro fields were in the record and reached
    no query, while nothing reported a problem because from the engine's side
    nothing was wrong. **Half a derivation is not a derivation**, and the half
    that is missing is the half that goes stale silently.

    `container` is the third field rather than something inferable, because a
    list and a string are both TEXT on arrival and a consumer that reads a JSON
    array as a scalar drops the field rather than failing.
    """
    from .db import LIST_COLS, column_affinity
    from .schema import SENSITIVE, _TYPES, display_name, sensitivity

    names = [dataset] if dataset is not None else list(KEYS)
    if dataset is not None and dataset not in KEYS:
        raise KeyError(f"unknown dataset {dataset!r}; known: {sorted(KEYS)}")

    out: dict[str, dict] = {}
    for name in names:
        pairs = SENSITIVE.get(name, {})
        out[name] = {
            field: {
                "types": _type_names(_TYPES.get(field)),
                "affinity": column_affinity(field),
                "container": field in LIST_COLS,
                # #205, and it is the one entry here a consumer must not read
                # past. A field with a coarse companion HAS NO COLUMN in the
                # read model and is absent from the default projection, so an
                # accessor published so consumers stop guessing would be
                # advertising a column that does not exist. `coarse_companion`
                # names the field that does, and null means this field is not
                # sensitive rather than that it is sensitive with no partner.
                "coarse_companion": pairs.get(field),
                # WHAT KIND OF DISCLOSURE THIS FIELD IS (#299). A client
                # gating egress was keeping a hand-written map of these and
                # could not keep it right: the copy is wrong the day a field
                # is added here, and its fallback gave an unknown field the
                # most permissive class - so a new field shipped to everybody
                # and the release log filed it as harmless.
                #
                # Published rather than internal for the reason the rest of
                # this accessor is: it exists because consumers were guessing.
                "sensitivity": sensitivity(name, field),
                # WHAT THE NUMBER IS IN, and the same argument one more time
                # (#310). A client kept a hand-written `{distance_km: "km",
                # rhr: "bpm"}` map, which is a copy of a fact this engine
                # validates against - and a client guessing a unit from a name
                # suffix is one rename away from printing kilometres as
                # seconds, since nothing says which names carry a unit.
                #
                # `{}` for a field with no quantity. Otherwise a UCUM code, a
                # named ordinal scale, or a REFERENCE to the field whose units
                # this takes - a goal's target is in the units of its metric,
                # and answering that with a constant would be wrong
                # confidently. A code, never a conversion: converting needs a
                # dependency this engine does not ship.
                "units": units(name, field),
                # AND WHAT A PERSON CALLS IT. Nobody asks how their rhr was.
                # This map cannot be derived from anything - it is about
                # English - and the client copy of it failed SILENTLY: a
                # question naming a metric the list had forgotten matched no
                # topic and fell through to a standing fact pack.
                "aliases": aliases_for(field),
                # AND THE ONE NAME TO PRINT (#331). `aliases` is for
                # recognition and has no entry that is a display name: it is a
                # SET, published in registry order, and every word in it was
                # chosen to be matched rather than to be printed - `kcal_out`
                # holds "burned". `units.label` is not one either: it names the
                # UNIT, and `kcal_in` and `kcal_out` both answer
                # "kilocalories".
                #
                # So a client softened the field name's underscores, which
                # invents nothing and is obviously the same token, and got
                # "kcal in". The engine knows which of `burned`, `calories
                # out`, `energy out` and `expenditure` it would use in its own
                # prose; a consumer cannot.
                "display_name": display_name(name, field),
            }
            for field in KEYS[name]
        }
    return out


def session_types() -> dict:
    """Every session type, and what a person calls it (#350).

    The activity half of the vocabulary a client otherwise reinvents. The
    metric half already comes from `aliases`: a client hand-maintaining `rhr`
    and `resting` missed "pulse", which this engine publishes, so an athlete
    typing "pulse 52" matched nothing from a client holding the answer in
    another module. The set of session types was known - `vocab.session_types`
    exists - but no surface published it and the inflections were not
    published at all.

    Per type: `label` for display, `aliases` for recognition, and the vendor
    tokens under the vendor's own name.

    RECOGNITION IS NOT AN OFFER LIST, which #331 settled one vocabulary over
    and this repeats. `aliases` is what the engine will MATCH, and a client
    showing a person the names for an activity wants the ones a person says.
    Eight MyFitnessPal export strings were sitting in `aliases` - "running
    (jogging), 9 mph (6.5 min mile)" and its siblings - so a client offering
    suggestions from that list would have offered those. They now sit under
    `myfitnesspal`, which is where every other vendor's tokens already lived:
    `strava` and `healthkit` have had their own fields all along, and the
    registry declares them in `alias_fields` so the resolver still matches
    them. The distinction is DATA rather than a regex over a suffix.

    Their accepted spelling CHANGED, which is worth saying plainly rather than
    calling the move neutral. Those eight aliases carried a `(myfitnesspal)`
    suffix, added by hand as a provenance annotation when they were accepted;
    the vendor's export does not carry it and nothing here composes one. So
    the suffixed form resolved and the string a real export actually contains
    did not. Now it is the other way round, which fixes the import rather than
    preserving it.

    THE INFLECTIONS ARE PUBLISHED, which is the half the issue said was worth
    arguing about. They are a fact about English rather than about the record,
    which is an argument for leaving them to a client - except that every
    client needs the same ones, the set is closed, and getting them wrong
    files a session under the wrong type. No type carried a past-tense form
    before this: "running" resolved and "ran" did not, so the issue's own
    headline example was the one that failed.

    The rule is narrow, because a vocabulary that contains a word nobody says
    is one nobody can trust: a type gets a past tense where ORDINARY USE HAS
    ONE. `ran`, `swam`, `golfed`. Nothing was conjugated to fill the table, so
    the types with no natural form - `elliptical`, `yoga`, `tennis` - have
    none, and `tennised` is not a word this engine will match. Where a form is
    ambiguous across several types it goes wherever the registry already sends
    its present tense: `skated` and `skied` both land on `wintersport`,
    beside the `skating` and `ski` that were already there. That is a
    precedent this follows rather than one it sets, and it is a coarse answer
    - `skated` cannot tell ice from inline, and summer rollerblading landing
    under `wintersport` is a pre-existing oddity in that mapping, not one
    introduced here. The unambiguous spellings `ice skated` and `rollerbladed`
    resolve precisely.

    NOT ENGLISH-ONLY, and it would be wrong to say so: the registry already
    carries `schaatsen`, `voetbal`, `velomobiel`, `randonnee` and `langlauf`,
    added where someone had a use for them. That is five words rather than a
    policy, so a client working in another language still supplies most of its
    own, and there is no rule here about which languages belong.
    """
    from .vocab import registry

    data = registry("session_types")
    vendors = [f for f in (data.get("alias_fields") or [])]
    out: dict[str, dict] = {}
    for slug, meta in sorted((data.get("types") or {}).items()):
        entry = {"label": (meta or {}).get("label") or slug,
                 "aliases": list((meta or {}).get("aliases") or [])}
        for field in vendors:
            value = (meta or {}).get(field)
            if value:
                # A COPY, like `aliases` above. Handing back the registry's own
                # list let a consumer append to it and invent a session type
                # for the rest of the process, or clear it and stop every
                # import of that vendor resolving - silently, in the engine,
                # from a caller that only meant to tidy a display list. The
                # generations surface already had to learn this.
                entry[field] = list(value) if isinstance(value, list) else [value]
        out[slug] = entry
    return out


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
        # #257. Carried HERE rather than behind a fourth accessor so that CLI
        # and MCP reach it without either being taught anything: `vitai schema
        # --json` serialises this dict, and the MCP `schema` tool returns it.
        # A separate surface would have been a new place for parity to fail.
        "fields": field_types(),
        # HOW TO ORDER CLAIMS (#308), for the same reason and by the same
        # route. A client that persists claims outside the engine has to sort
        # them, and one re-derived the rule and got it wrong: it read an
        # append-only log's ends as its date range, which is ARRIVAL order.
        #
        # The rule was settled here across several contract versions and
        # expressed only in Python, so a consumer's options were to guess it,
        # hand-port it, or not hold claims at all. The third is the honest
        # answer and is where that client is heading, but it is not reachable
        # while the engine does not stamp client-held claims - so between now
        # and then, every client orders logs itself.
        "ordering": ordering_rule(),
        # WHICH PART OF WHOSE DAY (#212), published for the reason #308 was:
        # a client that has to reimplement this will anchor it on the clock,
        # which is right for everybody who sleeps at night and wrong for the
        # athlete it exists for.
        "phase_rule": phase_rule(),
        # THE ACTIVITY HALF OF THE VOCABULARY (#350), by the same route as
        # `fields` and for the same reason #257 gave: a separate accessor is a
        # new place for parity to fail. A client wiring its correction
        # vocabulary to the engine's could take the metric half from `aliases`
        # and had to invent the activity half - so "I swam 2k" was parsed
        # against a list every client reinvents slightly differently, and a
        # session type added here reached none of them.
        "session_types": session_types(),
        # WHAT THIS BUILD CAN EMIT (#335), by the same route and for the same
        # reason `cmd_schema` gives for taking no `--root`: it is a property
        # of the installed ENGINE rather than of anyone's record, so a
        # different content repo could not answer it differently.
        "builds": {
            "this": _builds.this_build(),
            "extras": _builds.extras(),
            "released": _builds.builds(),
            "absence_meanings": list(ABSENCE_MEANINGS),
        },
    }
