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

from datetime import date
from pathlib import Path

from .config import Config, load_config
from .db import build_db
from .jsonl import load
from .report import build_report
from .schema import KEYS
from .verdicts import compute_verdicts


class Vitai:
    """Read/derive interface over one user's content repo."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        if not (self.root / "data").is_dir():
            raise FileNotFoundError(
                f"{self.root} is not a vitai content repo (no data/ directory)")

    @property
    def config(self) -> Config:
        return load_config(self.root)

    def dataset(self, name: str) -> list[dict]:
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        return load(self.root / "data", name)

    def datasets(self) -> dict[str, list[dict]]:
        return {name: self.dataset(name) for name in KEYS}

    def verdicts(self, today: date | None = None) -> list[dict]:
        d = self.datasets()
        return compute_verdicts(self.config, d["weight"], d["daily"],
                                d["sessions"], today=today)

    def rollup(self, today: date | None = None) -> str:
        d = self.datasets()
        return build_report(self.config, d["weight"], d["daily"],
                            d["sessions"], today=today)

    def build(self, today: date | None = None) -> Path:
        """Rebuild derived/: SQLite read model (incl. verdicts) + weekly.md."""
        d = self.datasets()
        rows = compute_verdicts(self.config, d["weight"], d["daily"],
                                d["sessions"], today=today)
        derived = self.root / "derived"
        db = build_db(derived, d, verdicts=rows)
        (derived / "weekly.md").write_text(
            build_report(self.config, d["weight"], d["daily"], d["sessions"],
                         today=today),
            encoding="utf-8", newline="\n")
        return db

    def status_line(self) -> str:
        pts = sorted((w["date"], w["kg"]) for w in self.dataset("weight")
                     if w.get("kg") is not None)
        if not pts:
            return "no weight data yet"
        d, kg = pts[-1]
        return f"{kg:.1f} kg ({d})"
