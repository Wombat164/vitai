"""Append-only JSONL with supersedes resolution.

The contract (see ARCHITECTURE.md section 2):
- one JSON object per line; lines starting with // are comments
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
from pathlib import Path

from .schema import IDENTITY_KEY


class DataError(Exception):
    """A malformed line (retained for callers that choose to raise)."""


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
    for r in records:
        if (slug := r.get(ident)) is not None:
            out[str(slug)] = r
    return out
