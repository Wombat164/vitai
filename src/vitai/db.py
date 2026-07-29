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
# 2: increment 1 - goals/thresholds/achievements datasets, the contributions,
#    milestones, plan_churn and goal_progress derivations, and a `goal` column
#    linking each verdict row to the goal it serves.
CONTRACT_VERSION = "2"

_TEXT_COLS = {"date", "type", "source", "location", "note",
              "kind", "statement", "model", "evidence",
              "week", "metric", "verdict",
              # policy datasets
              "slug", "title", "tracker", "policy", "period", "on_period_end",
              "deadline", "status", "motivator", "rationale", "on_success",
              "on_miss", "accountability", "set_by", "reason", "key",
              "change_kind", "goal",
              # derivations
              "dataset", "contribution", "label", "bucket", "direction",
              "declared", "last_edited"}

VERDICT_KEYS = ["week", "metric", "value", "target", "verdict", "goal"]

# Derived tables (rebuilt every build, like everything else in derived/).
CONTRIBUTION_KEYS = ["date", "goal", "metric", "dataset", "period", "value",
                     "counted", "contribution", "headroom"]
MILESTONE_KEYS = ["date", "goal", "period", "fraction", "value", "target", "label"]
CHURN_KEYS = ["date", "slug", "kind", "metric", "edit_no", "before", "after",
              "direction", "deadline_pushed", "reason", "set_by", "suspicious",
              "unexplained"]
PROGRESS_KEYS = ["slug", "title", "metric", "policy", "status", "period",
                 "bucket", "target", "counted", "unbudgeted", "progress_pct",
                 "declared", "last_edited", "deadline", "motivator", "tracker",
                 "milestones"]

DERIVED_TABLES: dict[str, list[str]] = {
    "verdicts": VERDICT_KEYS,
    "contributions": CONTRIBUTION_KEYS,
    "milestones": MILESTONE_KEYS,
    "plan_churn": CHURN_KEYS,
    "goal_progress": PROGRESS_KEYS,
}


def _cols(keys: list[str]) -> str:
    return ", ".join(f"{k} TEXT" if k in _TEXT_COLS else f"{k} REAL" for k in keys)


def build_db(derived: Path, datasets: dict[str, list[dict]],
             verdicts: list[dict] | None = None,
             derivations: dict[str, list[dict]] | None = None) -> Path:
    """Write the read model. `derivations` carries the computed tables
    (contributions, milestones, plan_churn, goal_progress); `verdicts` stays a
    named argument because it predates them and callers pass it positionally."""
    derived.mkdir(exist_ok=True)
    db = derived / "health.db"
    db.unlink(missing_ok=True)
    computed = dict(derivations or {})
    computed["verdicts"] = list(verdicts or [])
    con = sqlite3.connect(db)
    try:
        for table, keys in KEYS.items():
            _table(con, table, keys, datasets.get(table) or [])
        for table, keys in DERIVED_TABLES.items():
            _table(con, table, keys, computed.get(table) or [])
        con.execute("CREATE TABLE meta(key TEXT, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('contract', ?)", (CONTRACT_VERSION,))
        con.commit()
    finally:
        con.close()
    return db


def _table(con: sqlite3.Connection, table: str, keys: list[str],
           rows: list[dict]) -> None:
    con.execute(f"CREATE TABLE {table}({_cols(keys)})")
    if rows:
        con.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' * len(keys))})",
            [tuple(_cell(r.get(k)) for k in keys) for r in rows],
        )


def _cell(v: object) -> object:
    if isinstance(v, bool):
        return int(v)
    return v
