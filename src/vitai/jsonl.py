"""Append-only JSONL with supersedes resolution.

The contract (see ARCHITECTURE.md section 2):
- one JSON object per line; lines starting with // are comments
- a line is never edited; a correction is appended with
  "supersedes": "<date>/<source>" and the superseded line is dropped on load
- last valid record wins
"""

from __future__ import annotations

import json
from pathlib import Path


class DataError(Exception):
    """A malformed line, reported with file and line number."""


def read_lines(path: Path) -> list[tuple[int, dict]]:
    """All records in file order as (line_number, record). Raises DataError."""
    if not path.exists():
        return []
    out: list[tuple[int, dict]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise DataError(f"{path.name} line {n}: {e}") from e
        if not isinstance(rec, dict):
            raise DataError(f"{path.name} line {n}: expected a JSON object")
        out.append((n, rec))
    return out


def load(data_dir: Path, name: str) -> list[dict]:
    """Records from <data_dir>/<name>.jsonl with supersedes applied."""
    rows = read_lines(data_dir / f"{name}.jsonl")
    superseded = {r["supersedes"] for _, r in rows if r.get("supersedes")}
    return [
        r for _, r in rows
        if f"{r.get('date')}/{r.get('source', '')}" not in superseded
    ]
