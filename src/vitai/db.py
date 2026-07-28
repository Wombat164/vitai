"""SQLite read model: rebuilt from zero on every build, never a store.

The table set IS the public contract a game/dashboard reads (see
ARCHITECTURE.md "The platform"): one table per dataset plus `verdicts`
(weekly goal-attainment rows) and `meta` (contract version).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import KEYS

# Bump when a table/column changes shape; consumers check meta.contract.
CONTRACT_VERSION = "1"

_TEXT_COLS = {"date", "type", "source", "location", "note",
              "kind", "statement", "model", "evidence",
              "week", "metric", "verdict"}

VERDICT_KEYS = ["week", "metric", "value", "target", "verdict"]


def _cols(keys: list[str]) -> str:
    return ", ".join(f"{k} TEXT" if k in _TEXT_COLS else f"{k} REAL" for k in keys)


def build_db(derived: Path, datasets: dict[str, list[dict]],
             verdicts: list[dict] | None = None) -> Path:
    derived.mkdir(exist_ok=True)
    db = derived / "health.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    try:
        for table, keys in KEYS.items():
            con.execute(f"CREATE TABLE {table}({_cols(keys)})")
            rows = datasets.get(table) or []
            if rows:
                con.executemany(
                    f"INSERT INTO {table} VALUES ({','.join('?' * len(keys))})",
                    [tuple(_cell(r.get(k)) for k in keys) for r in rows],
                )
        con.execute(f"CREATE TABLE verdicts({_cols(VERDICT_KEYS)})")
        if verdicts:
            con.executemany(
                f"INSERT INTO verdicts VALUES ({','.join('?' * len(VERDICT_KEYS))})",
                [tuple(_cell(r.get(k)) for k in VERDICT_KEYS) for r in verdicts],
            )
        con.execute("CREATE TABLE meta(key TEXT, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('contract', ?)", (CONTRACT_VERSION,))
        con.commit()
    finally:
        con.close()
    return db


def _cell(v: object) -> object:
    if isinstance(v, bool):
        return int(v)
    return v
