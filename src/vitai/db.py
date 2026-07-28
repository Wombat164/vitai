"""SQLite read model: rebuilt from zero on every build, never a store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import KEYS


def build_db(derived: Path, datasets: dict[str, list[dict]]) -> Path:
    derived.mkdir(exist_ok=True)
    db = derived / "health.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    try:
        for table, keys in KEYS.items():
            cols = ", ".join(f"{k} TEXT" if k in ("date", "type", "source", "location", "note")
                             else f"{k} REAL" for k in keys)
            con.execute(f"CREATE TABLE {table}({cols})")
            rows = datasets.get(table) or []
            if rows:
                con.executemany(
                    f"INSERT INTO {table} VALUES ({','.join('?' * len(keys))})",
                    [tuple(_cell(r.get(k)) for k in keys) for r in rows],
                )
        con.commit()
    finally:
        con.close()
    return db


def _cell(v: object) -> object:
    if isinstance(v, bool):
        return int(v)
    return v
