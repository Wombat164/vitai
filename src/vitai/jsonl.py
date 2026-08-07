"""Append-only JSONL with supersedes resolution.

The contract (see ARCHITECTURE.md section 2):
- one JSON object per line; lines starting with // are comments
- rows are APPENDED through `append`, which stamps the machine-owned clocks
- a line is never edited; a correction is appended with
  "supersedes": "<date>/<source>" and the superseded line is dropped on load
- last valid record wins

Identity-keyed datasets (goals, thresholds) supersede by SLUG, not by
date/source: the reference is "<slug>@<date>". This makes the two ways of
revising a policy line mean different things, which increment 1 depends on:

- appending a new line with the same slug and NO supersedes is a dated
  CHANGE - both lines stay, and the chain is the auditable edit history
  (when the goal was declared, when it was last moved, and by whom);
- appending WITH supersedes is a CORRECTION - the referenced line was wrong
  and is dropped, exactly as for an observation.

Only the first is churn (G20). Collapsing the two would make "I typo'd the
target" indistinguishable from "I loosened the target after a bad week".

Parse resilience (G26): a single malformed line NEVER aborts the whole build.
`read_lines` returns the good rows plus a list of per-line error strings;
callers decide whether to quarantine (build: keep going) or report and fail
(validate: surface every problem). One bad byte must never silence the coach.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .clocks import (CLOCK_SKEW_TOLERANCE, now_stamp, order_key,
                     stamp_instant)
from .schema import (CURRENT_GENERATION, IDENTITY_KEY, KEYS, META_KEYS,
                     SEQUENCED, validate_record)


class DataError(Exception):
    """A malformed line (retained for callers that choose to raise)."""


def append(data_dir: Path, name: str, rec: dict,
           now: datetime | None = None, device: str | None = None) -> dict:
    """Append one line, stamping the clocks the machine owns. Returns the row.

    This exists because `recorded_at` is worthless as a tie-break if callers
    have to remember it. Every row in this record is written by a hand-rolled
    script - three of them in one day - and a field a caller must remember to
    set will be absent exactly when two rows land on the same date, which is
    the only moment it was needed. So the stamping is the API, not a
    convention.

    See `append_many` for the batch form, which is what a bulk import should
    use: this one re-reads the file to find the clock's high-water mark, so a
    loop over it is quadratic.
    """
    return append_many(data_dir, name, [rec], now=now, device=device)[0]


def append_many(data_dir: Path, name: str, records: list[dict],
                now: datetime | None = None,
                device: str | None = None) -> list[dict]:
    """Append many lines in one pass. The primitive bulk import actually wants.

    Bulk is the normal write pattern here - every source so far arrives as
    hundreds of rows in a tight loop - so the file is read ONCE to find where
    the clock got to, every row is stamped strictly past the one before it, and
    the whole batch is written in a single open. Looping over `append` instead
    re-parses a growing file per row, which is quadratic and gets slow exactly
    when the import is largest.

    What it does, in order:

    1. REFUSES a caller-supplied `recorded_at`. Transaction time is the one
       value in the record that must not be authored - a clock you can write
       is not a clock, it is another opinion. This is the boundary where that
       can actually be enforced, so it is enforced here rather than guessed
       at by the validator.
    2. Fills missing keys with null, honouring "null for unknown, never omit".
    3. Stamps `_gen` to the dataset's current generation, which is the
       convention the schema has documented since G25 and nothing enforced.
    4. Stamps `recorded_at` STRICTLY past the previous row - including the
       previous row of this same batch. Not merely "not older": equal is the
       failure case, because a tie orders nothing, and a write loop hits ties
       constantly (#44).
    5. VALIDATES EVERY ROW BEFORE WRITING ANY. An append-only file cannot be
       un-appended, so a batch with one bad row writes nothing at all rather
       than leaving a caller to work out how far it got.
    """
    if name not in KEYS:
        raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")

    # THIS device's file, and its high-water mark is read from that file
    # alone. Actor-per-file dissolves the skew problem rather than solving it:
    # a phone whose clock sits a minute behind the laptop never compares
    # against the laptop's stamps, because it never reads the laptop's file.
    # `CLOCK_SKEW_TOLERANCE` goes back to its real job - catching a device
    # whose OWN clock jumped backwards - and stops rejecting writes for a
    # reason that was never about this device (#105).
    from .devices import write_path

    path = write_path(data_dir, name, device)
    existing, _ = read_lines(path)
    prior = [i for i in (stamp_instant(r.get("recorded_at"))
                         for _, r in existing) if i is not None]
    high_water = max(prior) if prior else None

    wall = (now or datetime.now()).astimezone()
    if high_water is not None and wall < high_water - CLOCK_SKEW_TOLERANCE:
        raise DataError(
            f"the system clock reads {wall.isoformat(timespec='seconds')} but "
            f"{name}.jsonl already holds a row stamped "
            f"{high_water.isoformat(timespec='seconds')} - transaction time "
            "must not go backwards, and a gap this large means the clock is "
            "wrong rather than merely coarse. Fix the clock; appending now "
            "would bury the problem under stamps that look plausible.")

    # EVERY stream, for the position alone, and counted ONCE. The clock above
    # is read from this device's file by design (#105); a position among rows
    # sharing a key is a fact about the whole record, and counting only this
    # file would hand two devices the same number for the same key. Rescanning
    # per row would be quadratic, which is the shape #210's own check was
    # rewritten to remove.
    #
    # `max(count, highest + 1)` RATHER THAN A BARE COUNT. A count is right only
    # when the rows arrive in order. Sync three devices out of order and a
    # machine holding positions 3 and 4 but not 0 to 2 counts two rows and
    # stamps 2, colliding with a row it can see the proof of - the record says
    # five rows exist and the count says otherwise. Taking the higher of the
    # two uses what is already on screen.
    seq_next: dict[str, int] = {}
    if name in SEQUENCED:
        counts: dict[str, int] = {}
        highest: dict[str, int] = {}
        for _, held_row in _read_streams(data_dir, name)[0]:
            key = line_key(name, held_row)
            counts[key] = counts.get(key, 0) + 1
            if (seen := position_of(held_row)) is not None:
                highest[key] = max(highest.get(key, -1), seen)
        # Both halves computed over the whole record before either is used, so
        # the answer does not depend on the order the rows were visited in.
        # Folding them together per row gave a number that was never wrong but
        # was not the stated formula either - it skipped past a gap twice.
        seq_next = {key: max(count, highest.get(key, -1) + 1)
                    for key, count in counts.items()}

    rows: list[dict] = []
    for n, rec in enumerate(records, 1):
        if "device" in rec:
            # Machine-set, like `recorded_at`. A caller could otherwise write
            # a row into the plain file asserting it came from the phone, or
            # contradict the configured device and be silently overruled -
            # either way "device is metadata about the WRITE" stops being
            # enforceable and becomes a convention.
            raise ValueError(
                "device is machine-set and must not be supplied - it names "
                "the machine doing the writing, which the writer knows and "
                "the caller cannot assert. Set [device] slug in vitai.toml")
        if "seq" in rec:
            raise ValueError(
                "seq is machine-set and must not be supplied - it is this "
                "row's position among the rows already sharing its key, and a "
                "writer that could choose its own position could name a row "
                "that was never there. Append the row and read the seq back "
                "off what comes out (#239).")
        if "recorded_at" in rec:
            raise ValueError(
                "recorded_at is machine-set and must not be supplied - it is "
                "the one clock in the record that cannot be authored. Remove "
                "it and let append stamp it.\n"
                "\n"
                "If you are trying to make a row sort AFTER one already held, "
                "you do not need to: this path stamps every write later than "
                "everything in its own file. If the row you are correcting "
                "was stamped ahead of this machine by another writer, the "
                "append is refused with that as the reason rather than "
                "landing and retiring nothing (#210). What you may author is "
                "VALID time - `date`, and `measured_at` or `start_time` where "
                "the dataset has them - which says when the thing happened "
                "rather than when the record learnt it.")
        if unknown := sorted(set(rec) - set(KEYS[name]) - META_KEYS):
            raise ValueError(
                f"unknown key(s) for {name}"
                + (f" (row {n})" if len(records) > 1 else "")
                + f": {', '.join(unknown)}")
        row = {k: rec.get(k) for k in KEYS[name]}
        for meta in sorted(META_KEYS):
            if meta in rec:
                row[meta] = rec[meta]
        row["_gen"] = row.get("_gen") or CURRENT_GENERATION[name]
        stamp = now_stamp(now, after=high_water)
        row["recorded_at"] = stamp
        if device:
            # Metadata about the WRITE, beside `source` rather than inside it:
            # `source` says which instrument observed the value, `device` says
            # which machine wrote the line down. Conflating them would make a
            # phone and a laptop look like two instruments (#35).
            row["device"] = device
        high_water = stamp_instant(stamp)
        # After `date` and `source` are on the row, because those are what the
        # key is made of, and counting the pending rows too so a bulk import of
        # ten sessions on one day numbers them 0..9 rather than handing every
        # one of them the same position.
        if name in SEQUENCED:
            key = line_key(name, row)
            row["seq"] = seq_next.get(key, 0)
            seq_next[key] = row["seq"] + 1
        if problems := validate_record(name, row):
            raise DataError(
                f"refusing to append an invalid {name} line"
                + (f" (row {n} of {len(records)}; nothing was written)"
                   if len(records) > 1 else "")
                + ": " + "; ".join(problems))
        rows.append(row)

    # A CORRECTION THAT WOULD RETIRE NOTHING IS REFUSED HERE, before it is
    # written (#210).
    #
    # The failure this closes is silent in all three of its recorded
    # instances: the correction lands, `retire` walks past it, both rows stay
    # live, and `validate` reports an ADVISORY - so the write reports success
    # and the old value is what every reader sees. It is reachable through
    # this path, not only through hand-written lines: a row another writer
    # stamped ahead of this machine's clock is a target a correction written
    # now sorts BEFORE, and nothing said so.
    #
    # The direction of the harm is always the same. A correction that does
    # nothing leaves the value it was meant to replace in place, and a caller
    # cannot tell that from success.
    #
    # ASKED OF `retire` RATHER THAN RE-DERIVED, which is that function's own
    # recorded lesson: working the ordering rules out a second time got three
    # cases wrong, and asking is exact.
    if rows:
        problems = _corrections_that_would_not_apply(data_dir, name, rows)
        if problems:
            raise DataError(
                f"refusing to append to {name}: " + "; ".join(problems))

    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))
    return rows


# Datasets whose identity fields spell a null as an empty string rather than
# as the literal "None".
#
# The legacy single-slug datasets MUST keep "None". A row with an explicit
# null slug has always keyed that way, and an existing goals or medical file
# may hold a `supersedes` naming that spelling; rendering it "" instead
# orphans the reference and silently UN-RETIRES the line it corrected on the
# next load. A dataset with no rows in the wild has no such history to
# protect, so it gets the readable spelling - and `sets` needs it, because
# three of its five identity fields are legitimately null on the ordinary
# logging path (bodyweight sets, no session row, no circuit).
#
# The test for membership is "has this dataset ever been written to disk
# anywhere", NOT "is the tuple form nicer to read". `goals`, `thresholds`,
# `medical` and `events` are permanently excluded on that basis and no
# argument about readability moves them; a dataset introduced from here on
# belongs in this set. Stated as a rule because a list is what goes wrong
# when the next person adds a dataset and copies whichever branch is shorter.
_BLANK_NULL = frozenset({"sets", "meals"})


def identity_of(dataset: str, rec: dict) -> str | None:
    """How this row's identity renders, or None if the dataset has no identity.

    THE one renderer. Three functions used to spell a set's identity three
    different ways - `line_key` as `None/push-up/None/None/1`, a helper in
    `sets.py` as `/push-up///1`, and `heads` by refusing the row outright -
    so a `supersedes` computed one way named nothing when read another. That
    is #43 pointing the other way: a correction that matches no line, failing
    quietly, on the common case rather than an edge one.
    """
    ident = IDENTITY_KEY.get(dataset)
    if ident is None:
        return None
    fields = (ident,) if isinstance(ident, str) else ident
    blank = "" if dataset in _BLANK_NULL else "None"
    parts = []
    for field in fields:
        if field not in rec:
            parts.append("")
        elif rec[field] is None:
            parts.append(blank)
        else:
            parts.append(str(rec[field]))
    return "/".join(parts)


def line_key(dataset: str, rec: dict) -> str:
    """The reference a `supersedes` on a later line would use to name this one.

    A session with an `activity_id` is named by it (#43). Without one, two
    runs on the same day from the same watch share a key, so a `supersedes`
    aimed at either RETIRES BOTH - two real activities collapsing into one,
    which is the silent data loss #16 exists to prevent, arriving through the
    correction path instead of the merge path. `validate` reports a reference
    that matches more than one line, so the remaining ambiguity is loud.
    """
    if (named := identity_of(dataset, rec)) is not None:
        return f"{named}@{rec.get('date')}"
    if dataset == "sessions" and (aid := rec.get("activity_id")):
        return f"{aid}@{rec.get('date')}"
    return f"{rec.get('date')}/{rec.get('source', '')}"


def read_lines(path: Path) -> tuple[list[tuple[int, dict]], list[str]]:
    """Parse a JSONL file resiliently.

    Returns (good_rows, errors): good_rows is [(line_number, record)] in file
    order; errors is a list of "<file> line N: <reason>" strings for malformed
    lines. Never raises on a bad line - the caller chooses what to do.
    """
    if not path.exists():
        return [], []
    out: list[tuple[int, dict]] = []
    errors: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{path.name} line {n}: {e}")
            continue
        if not isinstance(rec, dict):
            errors.append(f"{path.name} line {n}: expected a JSON object")
            continue
        out.append((n, rec))
    return out, errors


def known_by(rec: dict, cutoff: datetime) -> bool:
    """Was this line already written at `cutoff`? Transaction-time only.

    THE KNOWLEDGE QUESTION, and it is not the valid-time one. `date` says when
    something became true and is legitimately backdated; `recorded_at` says
    when the line was written and is machine-set and monotonic. A context line
    appended in April about a February event is valid-time February and
    transaction-time April, so a reconstruction of what was known in March must
    exclude it while still placing it in February once it arrives.

    An UNSTAMPED line always survives a cutoff, following the same rule the
    clocks canon uses for ordering: absent sorts before present. A legacy line
    has no transaction time because it predates the clock, not because it was
    written later, and dropping it would empty a legacy corpus rather than
    reconstruct it.
    """
    stamp = stamp_instant(rec.get("recorded_at"))
    return stamp is None or stamp <= cutoff


def _read_streams(data_dir: Path, name: str
                  ) -> tuple[list[tuple[int, dict]], list[str]]:
    """Read and merge every device file for one dataset.

    The merge is a set UNION over disjoint files - no two devices write the
    same one - so nothing here has to reconcile content. That is the property
    the whole topology exists to produce, and it is what lets a sync transport
    stay content-blind.
    """
    from .devices import device_of, merge, stream_paths

    paths = stream_paths(data_dir, name)
    if not paths:
        return [], []
    streams, errors = [], []
    for path in paths:
        rows, problems = read_lines(path)
        errors += problems
        streams.append((device_of(path, name), [r for _, r in rows]))
    # ONE code path, single- or multi-actor. A short-circuit for the single
    # case parsed the file twice and, worse, ordered it differently - so
    # syncing in an EMPTY second file re-ordered an existing record's mixed
    # stamped and unstamped rows, which can change what a `supersedes`
    # retires. `merge` is stable and absent-first, so one stream comes back
    # in exactly its file order.
    return list(enumerate(merge(streams, name), 1)), errors


def load(data_dir: Path, name: str,
         as_of: datetime | None = None) -> list[dict]:
    """Records from <data_dir>/<name>.jsonl with supersedes applied.

    Malformed lines are QUARANTINED (dropped) so a build proceeds from the
    good rows; use `load_report` if you need to know what was quarantined.

    `as_of` reconstructs what the RECORD contained at an instant. That covers
    the dated `thresholds.jsonl` rows too, which are as-of like any dataset.
    What it cannot cover is the `vitai.toml` FALLBACK a key with no dated row
    lands on, because the toml has no history (#148). See `load_report`.
    """
    records, _ = load_report(data_dir, name, as_of=as_of)
    return records


def load_report(data_dir: Path, name: str,
                as_of: datetime | None = None) -> tuple[list[dict], list[str]]:
    """Like `load`, but also returns the parse errors that were quarantined.

    `as_of` is a KNOWLEDGE CUTOFF: only lines written at or before that
    instant are returned, so the result is what the record said then rather
    than what it says now with hindsight applied.

    THE FILTER RUNS BEFORE THE SUPERSEDES WALK, and the order is the whole
    correctness argument. A correction written after the cutoff had not been
    made yet, so it must not retire the line it corrects: filtering afterwards
    would apply a future retraction to a past reconstruction and produce a
    state the record never held.
    """
    # EVERY device's file, unioned into one deterministic sequence. A record
    # with a single `<name>.jsonl` is the same code path with one actor whose
    # name is nothing, so nothing about an existing record changes (#105).
    rows, errors = _read_streams(data_dir, name)
    if as_of is not None:
        rows = [(i, r) for i, r in rows if known_by(r, as_of)]
    return retire(name, [r for _, r in rows]), errors


# Datasets where a correction is meaningless because a row is an EVENT rather
# than a claim about a value. `emissions` records that the engine told the
# athlete something on a day: two on one day are two things that were said, and
# a later row cannot make an earlier one not have been said.
#
# This needs its own list because `line_key` falls back to `date/source` and
# `emissions` has no `source`, so every emission on one day shares the key
# `"<date>/"`. One `supersedes` line naming that key would have retired the
# whole day's assertions - the record forgetting what it told someone, which is
# the exact failure this dataset exists to prevent.
EVENT_DATASETS = frozenset({"emissions"})


def _spell(ref: tuple[str, int | None]) -> str:
    """A (key, position) reference as a person would write it in a message."""
    key, pos = ref
    return repr(key) if pos is None else f"{key!r} position {pos}"


def _targets_retired(dataset: str,
                     rows: list[dict]) -> set[tuple[str, int | None]]:
    """The references whose actual TARGET went, not merely whose ref was spent.

    `retire` reports a reference as applied when it retires ANY row, including
    an earlier dead correction naming the same key - so a repair that clears a
    failed correction and leaves the real value standing counts as applied,
    which turns a loud wrong state into a quiet one. What matters is whether a
    row that is NOT itself a correction of that reference disappeared.

    ONE retire for the whole batch. Asking per reference meant two retires
    each over the full dataset, which took 57 seconds for a thousand
    corrections over twenty thousand rows - and a bulk re-import is exactly
    the shape #210 describes, so a check that makes the ordinary case
    unusable is not a check anybody keeps.
    """
    gone = {id(r) for r in rows} - {id(r) for r in retire(dataset, rows)}
    out: set[tuple[str, int | None]] = set()
    for row in rows:
        if id(row) not in gone:
            continue
        if not row.get("supersedes"):
            out.add((line_key(dataset, row), None))
        # AND UNDER ITS POSITION, where it has one, WITHOUT the `supersedes`
        # guard above (#239). That guard exists because a bare reference cannot
        # tell "the target went" from "an earlier dead correction of the same
        # key went", and counting the second as applied turns a loud wrong
        # state quiet. A NARROWED reference names one row, so its
        # disappearance is unambiguous - and keeping the guard would mean a
        # correction aimed at a row that itself corrects a DIFFERENT key looked
        # unspent, refusing a write that was about to apply.
        if (pos := position_of(row)) is not None:
            out.add((line_key(dataset, row), pos))
    return out


def _corrections_that_would_not_apply(data_dir: Path, name: str,
                                      pending: list[dict]) -> list[str]:
    """Which of these corrections would land and retire nothing (#210).

    Checked against the MERGED order rather than this device's file, because
    that is the order `retire` walks and the whole hazard is a row another
    writer stamped ahead of this one.

    THE WHOLE BATCH AT ONCE. Checking each row against the held rows alone
    answers a question the write never asks: a correction whose target is
    created by a sibling row in the same batch was skipped entirely, so a
    bulk import emitting a correction before its target landed the exact dud
    this refuses - and a batch that WOULD have worked could be refused for a
    conflict its siblings resolve.

    ONLY WHERE THE TARGET EXISTS. A reference matching no row at all is a
    different situation and stays allowed: a record that syncs writer by
    writer legitimately holds a correction whose target has not arrived, and
    refusing that would make offline-first writing impossible. It repairs
    itself when the target lands.

    AND ONLY WHERE CORRECTION IS POSSIBLE AT ALL. An event dataset is never
    retired - a later row cannot make an earlier one not have been said - so a
    reference there is not defeated by ordering, it is meaningless. Refusing
    it with an ordering explanation would send a writer to fix a clock over a
    row that no clock can help.
    """
    from .devices import merge

    existing, _ = _read_streams(data_dir, name)
    held = [r for _, r in existing]
    # HELD AND PENDING BOTH. A correction whose target arrives in the SAME
    # batch was invisible when this looked at held rows alone, so a bulk
    # import emitting a correction before its target landed the exact dud
    # this refuses - and reported success. Whether the sibling actually
    # retires it is then decided by the merged order like everything else,
    # so a batch written target-first still applies and is accepted.
    def _target_exists(ref: str) -> bool:
        """Is there a row for this reference that is not a correction of it?

        A correction usually SHARES ITS TARGET'S KEY - same date, same source
        - so asking whether any row has that key answers yes for the
        correction itself, and a reference whose target has not synced looked
        present. That turned the offline-first case into a refusal.
        """
        key, pos = ref
        return any(line_key(name, r) == key
                   and (pos is None or position_of(r) == pos)
                   and target_of(r) != ref
                   for r in held + pending)

    refs = {t for r in pending if (t := target_of(r)) is not None}
    refs = {ref for ref in refs if _target_exists(ref)}
    if not refs:
        return []

    if name in EVENT_DATASETS:
        return [f"{name} is an event dataset and is never retired: a later "
                f"row cannot make an earlier one not have been said, so "
                f"{sorted(_spell(r) for r in refs)} would retire nothing "
                f"here whatever it is "
                f"stamped. Append the correction as its own row without "
                f"'supersedes'"]

    # ONE merge and one retire per reference, over held plus every pending
    # row - which is the state the write actually produces.
    by_device: dict[str, list[dict]] = {}
    for row in pending:
        by_device.setdefault(str(row.get("device") or ""), []).append(row)
    would_be = merge([("", held)] + sorted(by_device.items()), name)

    retired = _targets_retired(name, would_be)
    out = []
    # `None` and an int are not comparable, so a batch mixing a bare and a
    # narrowed correction of one key raised a TypeError here - on the HAPPY
    # path, because this sort runs before the applied filter below.
    for ref in sorted(refs, key=lambda t: (t[0], t[1] is not None, t[1] or 0)):
        if ref in retired:
            continue
        key, pos = ref
        blocking = max((str(r.get("recorded_at") or "") for r in held
                        if line_key(name, r) == key
                        and (pos is None or position_of(r) == pos)), default="")
        stamps = ", ".join(sorted(str(r.get("recorded_at")) for r in pending
                                  if target_of(r) == ref))
        out.append(
            f"a correction naming {_spell(ref)} would retire nothing. The row it "
            f"names is stamped {blocking} and this write is stamped {stamps}, "
            f"so the correction sorts before its target and `retire` walks "
            f"past it. It would land, report success, and leave the value it "
            f"was meant to replace in place - which is what makes this "
            f"failure invisible. Nothing appended from this machine can "
            f"correct that row until its clock passes that stamp")
    return out


def position_of(rec: dict) -> int | None:
    """This row's stored position, or None where it has none (#239)."""
    seq = rec.get("seq")
    return seq if isinstance(seq, int) and not isinstance(seq, bool) else None


def target_of(rec: dict) -> tuple[str, int | None] | None:
    """What a row's `supersedes` names: a key, and optionally a position.

    TWO FIELDS AND NEVER A PARSED SUFFIX. The obvious shape is to spell the
    position into the reference as `K#n` and ask the reader to take it apart.
    That crams two orthogonal facts into one identifier - which is what #280
    already refused for `derived_by` - and here it fails outright, because
    nothing stops a bare key containing the separator: `activity_id` is
    validated as an opaque string, `source` is not content-checked at all, and
    a `meals` identity is free text. `2030-05-01/watch#2` is a legal bare key
    AND a legal narrowed one, and syntax cannot tell them apart.

    Disambiguating by lookup - is this string some row's bare key? - is worse
    again, because it makes THE MEANING OF A STORED REFERENCE DEPEND ON WHAT
    ELSE IS IN VIEW. Measured against the engine before this change: a
    reference whose target had not synced yet was read as a position and
    retired an unrelated row, and a reference that had already applied flipped
    back to bare when a row with a matching source arrived, resurrecting what
    it had retired. In an append-only record a written reference has to mean
    one thing forever, and a field does what a parsed string cannot.
    """
    ref = rec.get("supersedes")
    if not str(ref or "").strip():
        return None
    narrow = rec.get("supersedes_seq")
    return (str(ref),
            narrow if isinstance(narrow, int) and not isinstance(narrow, bool)
            else None)


def retire(dataset: str, rows: list[dict], applied: set | None = None
           ) -> list[dict]:
    """`rows` with every superseded line dropped, in order.

    `applied` collects the references that actually retired something. A
    correction that spent its reference DID apply; one that did not is the
    dead line `schema.corrections_that_did_not_apply` reports. Asking retire
    is exact, where inferring it from what survives stopped being possible the
    moment one reference stopped retiring every match.

    Walk backwards so a line can only be superseded by a LATER one. This
    matters for the identity datasets, where a same-day correction shares its
    slug and date with the line it replaces and would otherwise supersede
    itself. A superseded line still passes its own reference on, so a chain
    (A superseded by B, B superseded by C) retires A as well as B.

    Shared with `schema.supersedes_problems`, which needs to know which
    corrections ACTUALLY APPLIED. Deriving that from the ordering rules a
    second time got three cases wrong; asking the same function is exact.
    """
    if dataset in EVENT_DATASETS:
        return list(rows)
    # WHAT ONE REFERENCE RETIRES (#239). The old rule dropped EVERY row whose
    # key matched, and `line_key` falls back to `<date>/<source>`, so one
    # correction aimed at one of ten sessions on a day retired all ten. On a
    # live record seven sessions in ten shared a key with something, so that
    # was the ordinary case rather than an edge, and it is the silent data
    # loss #16 exists to prevent arriving through the correction path.
    #
    # Walking backwards, a reference to K now retires:
    #
    #   - every EARLIER ROW THAT IS ITSELF A CORRECTION NAMING K. Two
    #     corrections naming one reference are the same intent expressed
    #     twice; the later wins and takes the earlier with it. That is what
    #     brings a chain down, and what lets a re-appended repair clear a
    #     correction that sorted too early to apply. A row retired that way
    #     does NOT fire its own reference again - counting it twice would
    #     retire a second, unrelated row, which is the original harm coming
    #     back through the repair path.
    #   - and ONE other row keyed K: the most recent, which is the one a
    #     correction written straight afterwards means. The rest of the day
    #     survives. A row that corrects a DIFFERENT key is still an ordinary
    #     row here and is eligible.
    #
    # NO POSITIONAL ORDINALS. An earlier cut named rows `K#0`, `K#1` so an
    # author could point at one exactly. Ordinals assigned at read time are
    # positions in the MERGED order, and `devices.merge` orders by
    # `(recorded_at, device, position)` - so a phone syncing a row stamped
    # earlier inserts ahead of rows already there and renumbers the group.
    # A reference written last week then names a different row, and something
    # already retired comes back. `identity` records the same weakness for its
    # own scheme. Naming an earlier row exactly needs an ordinal STORED on the
    # row, the way `sets` carries `set_index`, which is a schema change and
    # only reaches rows written after it.
    #
    # A POSITION NARROWS A REFERENCE (#239). A correction carrying
    # `supersedes_seq` retires the row of that key whose stored `seq` matches,
    # and only that row - so a chain of five rows sharing a key can be repaired
    # from the middle, which no bare reference could reach. It does not consume
    # the "one other row keyed K" budget, because it is not asking for
    # whichever row is most recent; it is asking for that one.
    #
    # `supersedes` itself is untouched in every record and every reading, and
    # that is a property of the SHAPE rather than of care taken here: nothing
    # is parsed, so nothing can be parsed wrongly.
    records: list[dict] = []
    one: dict[str, int] = {}
    want: dict[tuple[str, int], int] = {}
    chained: set[tuple[str, int | None]] = set()
    spent: set[tuple[str, int | None]] = set()
    for r in reversed(rows):
        base = line_key(dataset, r)
        seat = (base, pos) if (pos := position_of(r)) is not None else None
        target = target_of(r)
        ref = target[0] if target else None
        # THE WHOLE TARGET, NOT THE KEY (#239). "Two corrections naming one
        # reference are the same intent expressed twice" is true of two BARE
        # references, and false the moment a position is on one of them: a
        # correction of position 1 and a correction of position 2 are two
        # different intents that happen to share a key. Keying this on the
        # string dropped the earlier of them and brought its target's value
        # back, silently, with `validate` reporting nothing - which is the
        # data loss through the correction path that this whole issue is about.
        superseded_correction = target is not None and target in chained
        consumed = None
        if superseded_correction:
            dropped, consumed = True, target
        elif seat is not None and want.get(seat, 0) > 0:
            want[seat] -= 1
            dropped, consumed = True, (base, pos)
        elif ref != base and one.get(base, 0) > 0:
            one[base] -= 1
            dropped, consumed = True, (base, None)
        else:
            dropped = False
        # A correction retired as a duplicate of a later one does not also
        # spend its reference; anything else still does, so a chain through
        # several keys comes down whole.
        if dropped and consumed is not None:
            spent.add(consumed)
        if target is not None and not superseded_correction:
            chained.add(target)
            if target[1] is not None:
                want[target] = want.get(target, 0) + 1
            else:
                one[ref] = one.get(ref, 0) + 1
        if not dropped:
            records.append(r)
    records.reverse()
    if applied is not None:
        applied.update(spent)
    return records


def heads(records: list[dict], dataset: str) -> dict[str, dict]:
    """Current line per identity, for an identity-keyed dataset.

    The head is the LAST line for a slug in file order, which for an
    append-only file is the most recent edit. Returns {} for a dataset that
    is not identity-keyed.
    """
    ident = IDENTITY_KEY.get(dataset)
    if ident is None:
        return {}
    out: dict[str, dict] = {}
    # Ordered by (date, recorded_at) rather than file position: an ordering a
    # formatter can change is not an ordering (#37). The sort is STABLE and
    # the key is constant across unstamped rows, so a legacy file resolves in
    # exactly the file order it always did.
    fields = (ident,) if isinstance(ident, str) else ident
    for r in sorted(records, key=order_key):
        # ANY identity field present, and `identity_of` for the spelling. The
        # previous `all(... is not None)` DROPPED every set without a session
        # start, a block and a round - the ordinary logging path, not an edge
        # case - so those rows had no head at all. Requiring one field keeps
        # the old single-slug behaviour exactly (that field, or nothing) and
        # stops a tuple dataset losing its common rows.
        if any(r.get(f) is not None for f in fields):
            out[identity_of(dataset, r) or ""] = r
    return out
