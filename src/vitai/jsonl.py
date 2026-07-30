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

from .clocks import now_stamp, order_key
from .schema import CURRENT_GENERATION, IDENTITY_KEY, KEYS, validate_record


class DataError(Exception):
    """A malformed line (retained for callers that choose to raise)."""


def append(data_dir: Path, name: str, rec: dict,
           now: datetime | None = None) -> dict:
    """Append one line, stamping the clocks the machine owns. Returns the row.

    This exists because `recorded_at` is worthless as a tie-break if callers
    have to remember it. Every row in this record is written by a hand-rolled
    script - three of them in one day - and a field a caller must remember to
    set will be absent exactly when two rows land on the same date, which is
    the only moment it was needed. So the stamping is the API, not a
    convention.

    What it does, in order:

    1. REFUSES a caller-supplied `recorded_at`. Transaction time is the one
       value in the record that must not be authored - a clock you can write
       is not a clock, it is another opinion. This is the boundary where that
       can actually be enforced, so it is enforced here rather than guessed
       at by the validator.
    2. Fills missing keys with null, honouring "null for unknown, never omit".
    3. Stamps `_gen` to the dataset's current generation, which is the
       convention the schema has documented since G25 and nothing enforced.
    4. VALIDATES before writing. An append-only file cannot be un-appended,
       so a bad line must be refused at the door rather than corrected later
       by a superseding line that should never have been needed.
    5. Checks the stamp is not older than the last stamped row in the file.
       Transaction time is monotonic by construction; if it is not, the clock
       moved backwards and the tie-break it exists to provide is unsound.
    """
    if name not in KEYS:
        raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
    if "recorded_at" in rec:
        raise ValueError(
            "recorded_at is machine-set and must not be supplied - it is the "
            "one clock in the record that cannot be authored. Remove it and "
            "let append stamp it.")

    row = {k: rec.get(k) for k in KEYS[name]}
    if unknown := sorted(set(rec) - set(KEYS[name]) - {"supersedes", "_gen"}):
        raise ValueError(f"unknown key(s) for {name}: {', '.join(unknown)}")
    for meta in ("supersedes", "_gen"):
        if meta in rec:
            row[meta] = rec[meta]
    row["_gen"] = row.get("_gen") or CURRENT_GENERATION[name]
    row["recorded_at"] = now_stamp(now)

    if problems := validate_record(name, row):
        raise DataError(f"refusing to append an invalid {name} line: "
                        + "; ".join(problems))

    path = data_dir / f"{name}.jsonl"
    existing, _ = read_lines(path)
    prior = [r.get("recorded_at") for _, r in existing
             if r.get("recorded_at") is not None]
    if prior and max(prior) > row["recorded_at"]:
        raise DataError(
            f"recorded_at {row['recorded_at']} precedes the last stamped row "
            f"({max(prior)}) - transaction time must not go backwards, or it "
            "cannot order anything. Check the system clock.")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def line_key(dataset: str, rec: dict) -> str:
    """The reference a `supersedes` on a later line would use to name this one."""
    if (ident := IDENTITY_KEY.get(dataset)) is not None:
        return f"{rec.get(ident, '')}@{rec.get('date')}"
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


def load(data_dir: Path, name: str) -> list[dict]:
    """Records from <data_dir>/<name>.jsonl with supersedes applied.

    Malformed lines are QUARANTINED (dropped) so a build proceeds from the
    good rows; use `load_report` if you need to know what was quarantined.
    """
    records, _ = load_report(data_dir, name)
    return records


def load_report(data_dir: Path, name: str) -> tuple[list[dict], list[str]]:
    """Like `load`, but also returns the parse errors that were quarantined."""
    rows, errors = read_lines(data_dir / f"{name}.jsonl")
    # Walk backwards so a line can only be superseded by a LATER one. This
    # matters for the identity datasets, where a same-day correction shares its
    # slug and date with the line it replaces and would otherwise supersede
    # itself. A superseded line still passes its own reference on, so a chain
    # (A superseded by B, B superseded by C) retires A as well as B.
    records: list[dict] = []
    refs: set[str] = set()
    for _, r in reversed(rows):
        dropped = line_key(name, r) in refs
        if r.get("supersedes"):
            refs.add(r["supersedes"])
        if not dropped:
            records.append(r)
    records.reverse()
    return records, errors


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
    for r in sorted(records, key=order_key):
        if (slug := r.get(ident)) is not None:
            out[str(slug)] = r
    return out
