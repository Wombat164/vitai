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
from .contributions import compute_contributions, goal_progress
from .db import build_db
from .jsonl import load
from .policy import State, context_on, plan_churn, state
from .report import build_report
from .resolution import live_inferences, resolve, retractions
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
        """Raw claims, exactly as recorded. See `canonical()` for adjudicated."""
        return {name: self.dataset(name) for name in KEYS}

    def resolution(self) -> dict:
        """Run the resolution layer: canonical rows plus the audit trail.

        Everything the engine judges on comes from here, not from
        `datasets()` - a verdict computed over unresolved claims would double
        count every day the athlete happens to own two devices.
        """
        cfg = self.config
        return resolve(self.datasets(), precedence=cfg.precedence,
                       source_order=cfg.source_order)

    def canonical(self, name: str | None = None):
        """Adjudicated rows: one canonical record per quantity per date."""
        resolved = self.resolution()["canonical"]
        if name is None:
            return resolved
        if name not in KEYS:
            raise KeyError(f"unknown dataset {name!r}; one of {sorted(KEYS)}")
        return resolved[name]

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

    def context(self, on: date | str | None = None) -> dict | None:
        """The situational mode in force on a date (G34)."""
        return context_on(self.dataset("context"),
                          on or date.today())

    def verdicts(self, today: date | None = None) -> list[dict]:
        d = self.canonical()
        return compute_verdicts(self.config, d["weight"], d["daily"],
                                d["sessions"], today=today,
                                goals=d["goals"], thresholds=d["thresholds"])

    def rollup(self, today: date | None = None) -> str:
        d = self.canonical()
        return build_report(self.config, d["weight"], d["daily"],
                            d["sessions"], today=today)

    def state(self, on: date | str) -> State:
        """The goals and thresholds in force on a date - as-of reconstruction.

        The question this exists to answer: "looking at a day three months
        ago, what was I actually aiming at THEN?"
        """
        d = self.datasets()
        return state(d["goals"], d["thresholds"], on)

    def goals(self, today: date | None = None) -> list[dict]:
        """Per-goal standing as of `today`: counted progress, %, dates."""
        d = self.datasets()
        on = (today or date.today()).isoformat()
        return goal_progress(d["goals"], d["thresholds"], d["daily"],
                             d["sessions"], on)

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
        return plan_churn(d["goals"], d["thresholds"], self.verdicts(today=today))

    def _derivations(self, resolved: dict,
                     today: date | None = None) -> dict[str, list[dict]]:
        d = resolved["canonical"]
        contributions, milestones = compute_contributions(
            d["goals"], d["thresholds"], d["daily"], d["sessions"])
        verdicts = compute_verdicts(self.config, d["weight"], d["daily"],
                                    d["sessions"], today=today,
                                    goals=d["goals"], thresholds=d["thresholds"])
        on = (today or date.today()).isoformat()
        return {
            "verdicts": verdicts,
            "contributions": contributions,
            "milestones": milestones,
            "plan_churn": plan_churn(d["goals"], d["thresholds"], verdicts),
            "goal_progress": goal_progress(d["goals"], d["thresholds"],
                                           d["daily"], d["sessions"], on),
            "claims": resolved["claims"],
            "resolution": resolved["explanations"],
            "justifications": resolved["justifications"],
            "conservation": resolved["tripwires"],
            "retractions": retractions(self.datasets()),
        }

    def build(self, today: date | None = None) -> Path:
        """Rebuild derived/: SQLite read model (incl. verdicts) + weekly.md.

        Resolution runs FIRST and once: the primary tables carry canonical
        rows, so a consumer reading `daily` gets adjudicated truth without
        having to know the resolution rules.
        """
        resolved = self.resolution()
        d = dict(resolved["canonical"])
        # An inference whose justification was retracted stops being presented
        # as current knowledge, though the line itself remains in the file.
        d["inferences"] = live_inferences(self.datasets())
        derivations = self._derivations(resolved, today=today)
        derived = self.root / "derived"
        db = build_db(derived, d, verdicts=derivations["verdicts"],
                      derivations=derivations)
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
