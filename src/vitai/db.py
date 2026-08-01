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
# 3: increment 2 - measurements/context datasets, gen-2 provenance and context
#    fields on daily/sessions, and the resolution layer: primary tables now
#    hold CANONICAL rows, with raw claims in *_claims and the adjudication in
#    resolution/justifications/conservation/retractions.
# 4: increment 3 - the medical dataset, plus the safety layer's outputs:
#    `gates` (what is blocked today and why) and `escalations` (deterministic
#    severity-to-action). A consumer that renders training suggestions MUST
#    read `gates`, or it will propose activity the record has blocked.
# 5: gate mechanics - `checks` dataset, `onset_date`/`precondition` on
#    medical, `occurred_date` on achievements, and `status`/`precondition`
#    columns on `gates`. A consumer reading `gates` MUST now check `status`:
#    a row with status `cleared` is reported but does NOT block.
# 6: goals (G86/#26) - the `events` dataset (dated real-world fixtures a plan
#    is built backwards from), `deadline_kind`/`event`/`verification`/
#    `change_kind` on goals, and `deadline_kind` on `plan_churn`. TWO changes
#    a consumer must act on: a `goal_progress` row with `verification` of
#    `attested` has no metric, no target and no progress and MUST NOT be
#    rendered as 0% - it is a goal nothing can ever measure, not a goal going
#    badly; and a `plan_churn` row is only a retreat from a deadline when
#    `deadline_kind` is `hard`, so a consumer that reads `deadline_pushed`
#    alone will accuse the athlete of gaming a date they invented.
# 7: the clocks (#37) - `recorded_at` (transaction time) on EVERY dataset and
#    `measured_at` (observation time) on weight. Resolution now orders by
#    (date, recorded_at) instead of falling back to file position. A consumer
#    that reconstructs history MUST order by both, or a same-date correction
#    resolves by whatever order the rows happen to be in - and a `weight_rate`
#    verdict may now be `nodata` because the weigh-in times behind it are
#    spread widely enough to account for the rate.
# 8: goal scope (#36) - `goal_progress` gains `dataset` (the scope the goal
#    actually draws from, INFERRED from the metric where the row left it
#    unset) and `scope` (`declared` | `inferred` | `ambiguous` | `undeclared`).
#    A consumer must not read an unset `dataset` as "the default": unstated and
#    stated-as-daily are different, and a goal whose scope the engine cannot
#    feed reports null progress rather than 0.
# 9: the track foreign key (#43) - `track` (repo-relative path to the stored
#    GPX/FIT/TCX), `activity_id` (the platform's opaque id) and
#    `activity_source` (who ASSIGNED that id, which is not necessarily who
#    recorded it) on `sessions`. `activity_id` is also the per-row identity a
#    session previously lacked, so a correction can name one of two runs on a
#    day instead of retiring both. It is TEXT and must never be read as a
#    number: leading zeros and ids past 2^53 both occur.
# 10: provenance as a CHAIN (#35/#51) - `origin` (what observed reality),
#    `path` (the ordered hops it travelled) and `origin_evidence` on the
#    observation datasets, plus a `provenance` table carrying, per resolved
#    row, how many INDEPENDENT instruments observed it and what the journey
#    could have done to it. TWO things a consumer must change: `witnesses` on
#    `justifications` and `explanations` now counts distinct ORIGINS rather
#    than rows, so N platforms carrying one device's file is 1; and a
#    `resolution` row carries `independent`, which is false when the two
#    values are one measurement seen at two points on one pipe - that spread
#    measures pipeline fidelity and must never be read as agreement.
# 11: the acquisition axis (#77/#78) - `capture` (how a value was acquired)
#     and `read_by` (who did the reading, where one happened) on the
#     observation datasets, plus `origin`/`path`/`origin_evidence` finally
#     reaching `sessions`. `provenance.trust` gains a `transcribed` level: a
#     photograph of a console read by a model is an inference over an
#     artifact, not a reading of an instrument, and MUST NOT be rendered as
#     device-measured.
#     ALSO 11, shipped in the same build: resolution audit (#73). It was
#     briefly numbered 12 here, but no database ever emitted a 12 - the two
#     changes merged within an hour of each other and both went out under 11,
#     so a consumer gating on 11 gets both. Renumbered to say what shipped
#     rather than what was intended. `resolution` gains `discarded` (every claim
#     that lost, not only the runner-up) and `unattributed_loser`, and a new
#     `unattributed_claim_lost` tripwire. A consumer showing a canonical value
#     can now say what it beat; before this, a resolved value had no way to
#     say it had beaten anything at all.
# 12: was it measured at all (#49, #88) - `modelled` on the observation
#     datasets names the FIELDS on a row that are model outputs rather than
#     observations, and `type_source` on `sessions` says how a categorical
#     label was assigned. A consumer summing a column MUST check `modelled`:
#     an inflated estimate reaching a deficit reads ON TARGET while the scale
#     goes up. A `type` carrying `vendor-classified` is a third-party model's
#     guess, not something the athlete or a device asserted.
CONTRACT_VERSION = "13"
#     rather than what was intended. `resolution` gains `discarded` (every
#     claim that lost, not only the runner-up) and `unattributed_loser`, and a
#     `unattributed_claim_lost` tripwire. A consumer showing a canonical value
#     can now say what it beat; before this, a resolved value had no way to
#     say it had beaten anything at all.
# 13: the artifact store (#80) - an `artifacts` manifest table (one row per
#     kept file: hash, media type, size, why it was kept) and an `artifact`
#     reference on weight, daily, sessions and measurements, so the evidence a
#     value was read FROM survives alongside the value. Two things a consumer
#     must not get wrong. A reference is a content address (`sha256:...`), not
#     a path, so it cannot drift from the row citing it - and resolving one to
#     bytes is a LOCAL lookup: the manifest travels in the read model, the
#     artifacts do not, and nothing in this contract authorises transmitting
#     one. And REMOVED IS NOT MISSING: an artifact the athlete deleted leaves a
#     tombstone with a reason, and a consumer that renders that as broken
#     evidence has turned a retention decision into a data-loss alarm.
CONTRACT_VERSION = "13"

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
              "declared", "last_edited",
              # increment 2: provenance, context, resolution.
              # `mood`/`pain` and the two resolution VALUES stay numeric-
              # affinity on purpose - a claim's value may be a number, and
              # TEXT affinity would stringify it for every consumer.
              "feel", "coverage", "pain_site", "pain_side", "start_time", "setting",
              "route", "place", "with", "context", "planned", "weather",
              "facilities", "mode", "depends_on",
              "claim_id", "merged_into", "retracted_by", "cascaded_from",
              "field", "chosen_source", "over_source",
              "tier", "quantity_class", "severity", "detail",
              # increment 3: the medical layer and the safety outputs
              "title", "body_site", "status", "resolved_date", "restricts",
              "provider_type", "source_kind", "escalation", "level", "trigger",
              "action", "onset_date", "precondition", "occurred_date",
              "result",
              # #35/#51: the provenance chain.
              "origin", "path", "origin_evidence", "trust", "chain", "compares",
              "capture", "read_by",
              "discarded",
              "modelled", "type_source",
              "scope",
              # #43. `activity_id` MUST be TEXT: a REAL-affinity column
              # converts "9914203377" to a float, which destroys leading
              # zeros and any id past 2^53 - silently, and in exactly the
              # field whose whole job is to be an opaque token.
              "track", "activity_id", "activity_source",
              # G86: events, and the goal fields that anchor to them.
              "event_date", "priority", "event", "deadline_kind",
              "verification",
              # #37: the three clocks
              "recorded_at", "measured_at",
              # #80: the artifact store. `sha256` and `artifact` MUST be TEXT
              # for the same reason `activity_id` is - a content address is an
              # opaque token, and REAL affinity would mangle one silently.
              # `bytes` stays numeric so a consumer can sum held storage.
              "sha256", "artifact", "media_type", "captured_at"}

VERDICT_KEYS = ["week", "metric", "value", "target", "verdict", "goal"]

# Derived tables (rebuilt every build, like everything else in derived/).
CONTRIBUTION_KEYS = ["date", "goal", "metric", "dataset", "period", "value",
                     "counted", "contribution", "headroom"]
MILESTONE_KEYS = ["date", "goal", "period", "fraction", "value", "target", "label"]
CHURN_KEYS = ["date", "slug", "kind", "metric", "edit_no", "before", "after",
              "direction", "deadline_pushed", "deadline_kind", "reason",
              "set_by", "suspicious", "unexplained"]
PROGRESS_KEYS = ["slug", "title", "metric", "policy", "status", "period",
                 "bucket", "target", "counted", "unbudgeted", "progress_pct",
                 "dataset", "scope", "declared", "last_edited", "deadline",
                 "deadline_kind",
                 "days_to_deadline", "event", "verification", "motivator",
                 "tracker", "milestones"]

# Increment 2: the adjudication trail. Primary dataset tables hold CANONICAL
# rows; these say where those rows came from and what was overruled.
CLAIM_KEYS = ["claim_id", "dataset", "date", "source", "kind", "merged_into",
              "retracted"]
RESOLUTION_KEYS = ["date", "dataset", "field", "chosen_source", "chosen_value",
                   "over_source", "over_value", "witnesses", "reason",
                   "disagreed", "independent", "compares", "discarded",
                   "unattributed_loser"]
JUSTIFICATION_KEYS = ["date", "dataset", "field", "claim_id", "source", "tier",
                      "quantity_class", "witnesses", "origin", "trust"]
CONSERVATION_KEYS = ["date", "kind", "detail", "severity"]
RETRACTION_KEYS = ["date", "kind", "claim_id", "retracted_by", "reason",
                   "cascaded_from"]
# Increment 3. `gates` is the table a consumer must respect before suggesting
# any activity; `escalations` is the deterministic severity-to-action output.
GATE_KEYS = ["date", "source_kind", "slug", "restricts", "reason", "severity",
             "status", "precondition", "escalation"]
ESCALATION_KEYS = ["date", "level", "trigger", "detail", "action"]

PROVENANCE_KEYS = ["date", "dataset", "origin", "independent_sources",
                   "trust", "chain"]

DERIVED_TABLES: dict[str, list[str]] = {
    "provenance": PROVENANCE_KEYS,
    "verdicts": VERDICT_KEYS,
    "contributions": CONTRIBUTION_KEYS,
    "milestones": MILESTONE_KEYS,
    "plan_churn": CHURN_KEYS,
    "goal_progress": PROGRESS_KEYS,
    "claims": CLAIM_KEYS,
    "resolution": RESOLUTION_KEYS,
    "justifications": JUSTIFICATION_KEYS,
    "conservation": CONSERVATION_KEYS,
    "retractions": RETRACTION_KEYS,
    "gates": GATE_KEYS,
    "escalations": ESCALATION_KEYS,
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
