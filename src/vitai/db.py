"""SQLite read model: rebuilt from zero on every build, never a store.

The table set IS the public contract a game/dashboard reads (see
ARCHITECTURE.md "The platform"): one table per dataset plus `verdicts`
(weekly goal-attainment rows) and `meta` (contract version, and the
policy digest of the config the record does not hold).
"""

from __future__ import annotations

import json
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
# 14: the set as an atom (#97) - a `sets` table, one row per SET, because
#     three facts had nowhere to live: an attempted load that could not be
#     completed (`reps_attempted` 1, `reps_completed` 0), whether a set was
#     taken to failure, and what kind of number a load is. Two things a
#     consumer must not get wrong. A NULL `failure` means UNSTATED and MUST
#     NOT be read as maximal - a set logged against a stated max read as one
#     and was not, and that is the defect this dataset exists for. And a
#     `load` under `load_type: machine_stack` is a PIN NUMBER, not a mass:
#     66 on two machines is two different loads, so it is never comparable
#     across machines and never rendered in kilograms.
#     Also in 14: `rpe` widens from integer to numeric across every dataset
#     that carries it, `sessions` included. Half points are standard on the
#     RIR-anchored scale. Strictly looser, so no row that validated before
#     stops validating.
# 15: the itemised meal estimate (#96) - a `meals` table, one row per
#     INGREDIENT of a photographed meal, with a gram estimate, a gram RANGE,
#     and the per-100 g composition figures as the food table gave them
#     alongside the table's name. Three things a consumer must not get wrong.
#     Energy and macros are DERIVED from the quantity and are not columns: an
#     item whose portion is corrected must not keep a figure computed from the
#     old one. There is NO confidence column and there will not be one - the
#     range IS the confidence statement, and a number there would be a decimal
#     point pretending to be calibration. And A MEAL IS NOT A DAY: these rows
#     never feed `daily.kcal_in`, a total must never be rendered without its
#     range, and a consumer that sums meals into a day is asserting the
#     athlete ate nothing they did not photograph.
# 16: multi-device writes (#105) - `device` on EVERY dataset, naming the
#     machine that wrote the line down. Distinct from `source`, which names
#     the instrument that observed the value: a phone and a laptop are not two
#     instruments, and conflating them would manufacture corroboration out of
#     a sync (#35). Readers now take `<dataset>.<device>.jsonl` alongside
#     `<dataset>.jsonl` and union them, so ONE consumer-visible thing changes:
#     a dataset may contain rows written by several machines, ordered by
#     (recorded_at, device, position), and that order is TOTAL - two devices
#     rebuilding the same file set produce byte-identical output. A consumer
#     must not treat two rows describing one event from two devices as two
#     events; `duplicate_captures()` reports them and the engine never merges
#     them silently.
# 17: `meta` gains a `policy` row (#148) - a content hash of the config that
#     is NOT in the append-only record. Additive, and a contract-16 reader
#     that only selects `key='contract'` is unaffected; the bump is here
#     because `meta` was documented as carrying the contract version and
#     nothing else, so a consumer selecting the whole table saw one row and
#     may now see two. What it buys: a reconstruction judged under one
#     `vitai.toml` and one judged under another are not comparable, and until
#     now nothing said so. Thresholds without a dated row fall through to
#     whatever the toml says TODAY, so editing one silently re-judges every
#     historical week that lacked one. This does not fix that - it makes it
#     detectable rather than invisible. OPTIONAL at 17: `build_db` omits the
#     row when no digest is supplied, so absence means "built without one",
#     NOT "pre-17" and not "no policy". Every build the engine itself drives
#     writes it; a consumer must read `contract` to know the shape and must
#     not infer a build's age from this row missing.
# 18: `verdicts.reason` (#177) - `no_data` was one word for four states, and
#     the distinction was recoverable only by inspecting which fields were
#     null: both absent meant the input was missing, target absent meant no
#     policy was configured, both present meant the measurement could not
#     support a judgement. A fourth state did not use the word at all: a
#     contraindicated or suppressed metric had its row DELETED, which a
#     consumer cannot tell from a metric nobody computed.
#
#     Now the verdict answers "can a judgement be rendered" and `reason`
#     answers "why not": one of no_input, no_policy, not_supported,
#     contraindicated, suppressed. ADDITIVE and appended, so a consumer that
#     ignores it sees exactly the previous behaviour - except that a
#     suppressed metric now appears as a labelled row rather than as an
#     absence, which is the doctrine everywhere else in this engine and was
#     not honoured at the verdict layer.
# 19: protocol and regimes (#171 track 2) - `protocol` on weight and
#     measurements names the CONDITIONS a measurement was taken under, and a
#     row without one is a different epistemic class rather than a row with a
#     missing optional field: it carries the measurand's full definitional
#     uncertainty, which for body mass dominates instrument error. Plus two
#     policy datasets: `protocols` defines the slugs in the athlete's own
#     words, and `regimes` declares a bounded interval whose claims were
#     UNANCHORED. A consumer must not read an emptied interval as missing
#     data: the claims are still in `claims`, what ended is their standing as
#     values, and nothing is filled in behind them because the measurement
#     that ended a regime is evidence the earlier claims were unanchored
#     rather than evidence of what the true values were.
#     RENUMBERED from 18: #177 merged first, and the contract follows
#     MERGE order rather than issue order.
# 20: DECLARED derivation lineage. `derived_from` names the row references an
#     emitted value stands on and `derived_op` says how, in the athlete's own
#     words. Both are declared rather than executable: a consumer must not
#     read `derived_op` as a formula it can re-run, and the engine does not
#     re-run it either. Two consequences a consumer may rely on. A derived
#     value NEVER corroborates its own inputs, so rows standing on a shared
#     input count as one witness in `independent_sources` however many rows
#     they are. And a value whose input the record later retracted raises a
#     `stale_derivation` tripwire, which reports rather than corrects: the
#     stale number stays, visibly flagged, because an engine that cannot
#     re-run the derivation cannot produce a right answer and a confident
#     wrong one is worse than a flagged old one.
# 21: `emissions`, the engine's memory of what it TOLD the athlete. Phase 3
#     of the uncertainty proposal. Pass-through and append-only, never
#     resolved: two assertions made on one day are two events, not a
#     contested value.
#
#     SURFACED assertions only, written at delivery time by
#     `api.assert_delivery` and never at build. A consumer must not read this
#     as the set of verdicts the engine computed - it is the set it DELIVERED,
#     and a judgement nobody was shown had no consequence to retract. A
#     consumer that renders judgements and does not call `assert_delivery`
#     produces assertions the record cannot later retract; that is the
#     accepted residual risk, because logging computation instead of delivery
#     records the wrong event.
#
#     `basis_claims` is a JSON array in a TEXT column, like `derived_from`.
# 22: a `pending` refusal reason, and `due` on a refusal row. `no_input` said
#     the record holds nothing, which is true and cannot tell an athlete that
#     nothing will ever come apart from a source that delivers in four hours.
#     `pending` says the question is answerable and not yet, and carries WHEN.
#
#     THE DEGRADATION IS PART OF THE CONTRACT. A refusal is `pending` only
#     while the expected arrival is ahead. Once it passes, the reason drops
#     back to `no_input` and KEEPS `due`, so a consumer can report a source as
#     late rather than repeating that the answer is coming. A metric that
#     stayed pending forever would be a broken connector nobody noticed.
#
#     `due` is derived from the source's OWN arrivals, never declared: a
#     source with no established cadence produces `no_input`, exactly as
#     today.
# 23: goal POLARITY. `monotonic` and `guarded` both meant "more counts", so a
#     cap was scored as an accumulation: 1100 kcal a day against a 1200 limit
#     reported 641.7% for the week and minted four milestones for breaching
#     it. `polarity` says which direction is progress - floor, ceiling, band
#     or approach - and `target_hi` carries a band's upper bound.
#
#     WHAT A CONSUMER MUST NOT ASSUME: that `progress_pct` is always there. It
#     is the FLOOR's measure and is null for every other polarity, because a
#     percentage of a limit consumed is the figure that read as success.
#     A ceiling reports `headroom`, a band reports `headroom` and which side
#     it fell off, an approach reports `distance`, and `breach` says under or
#     over wherever the question has an answer.
#
#     Absent polarity reads as `floor`, so no existing row re-scores and no
#     row has to be edited to keep the answer it had. Rows whose title says
#     cap or limit while scoring as a floor now raise a validate ADVISORY
#     rather than having to be found by hand.
CONTRACT_VERSION = "23"

_TEXT_COLS = {"derived_from", "derived_op",  # both TEXT: `derived_op = "7"`
              # under REAL affinity silently becomes 7.0, which is the defect
              # the `activity_id` note below already warns about
              #
              # `contract` is a version STRING and `policy_asof` an ISO date;
              # both are digits and hyphens, so REAL affinity would turn "21"
              # into 21.0 and lose the distinction. `statement`, `week` and
              # `metric` are already below, on other datasets.
              "basis_claims", "surface", "policy_asof", "contract",
              # `polarity` and `breach` are words; a band's bounds are numbers
              # and stay numeric.
              "polarity", "breach",
              # `due` is an ISO date too (#202).
              "due",
              "date", "type", "source", "location", "note",
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
              # #105: which machine wrote the line down
              "device",
              # #80: the artifact store. `sha256` and `artifact` MUST be TEXT
              # for the same reason `activity_id` is - a content address is an
              # opaque token, and REAL affinity would mangle one silently.
              # `bytes` stays numeric so a consumer can sum held storage.
              "sha256", "artifact", "media_type", "captured_at",
# #97: the set. `exercise`, `machine` and `tempo` are labels;
              # the reps, loads and counters stay numeric.
              "exercise", "machine", "load_type", "load_unit", "set_type",
              "failure", "side", "tempo", "session_start",
# #96: the itemised meal estimate. The per-100 g figures and the
              # gram range stay numeric; only the labels are TEXT.
              "meal", "item", "food_table",
# #99: the categorical modifier axes. The parametric ones stay
              # numeric - including the machine-scoped ordinals, which ARE
              # numbers, just not comparable ones.
              "equipment", "angle_class"}

# `reason` is APPENDED, so a consumer reading by name is unaffected and one
# reading positionally sees the new column last (#177). It is null on every
# judged row and never null on a refusal.
VERDICT_KEYS = ["week", "metric", "value", "target", "verdict", "goal",
                "reason", "due"]

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
                 "tracker", "milestones",
                 # Appended (#200), so a positional reader keeps every column
                 # it knew. `progress_pct` above is now the FLOOR's measure
                 # and is null for the other three polarities.
                 "polarity", "target_hi", "room_left", "distance", "breach"]

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
             derivations: dict[str, list[dict]] | None = None,
             policy: str | None = None) -> Path:
    """Write the read model. `derivations` carries the computed tables
    (contributions, milestones, plan_churn, goal_progress); `verdicts` stays a
    named argument because it predates them and callers pass it positionally.

    `policy` is `config.policy_digest(cfg)` - the hash of the policy the
    record does not hold (#148). Optional so a caller building a read model
    from datasets alone still works, and ABSENT rather than a placeholder
    when it is not supplied: a fixed string would read as "policy unchanged"
    across two builds that were judged differently, which is the one wrong
    answer this row exists to prevent."""
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
        if policy is not None:
            con.execute("INSERT INTO meta VALUES ('policy', ?)", (policy,))
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
    if isinstance(v, (list, tuple)):
        # `derived_from` is the first list-valued column (#170). JSON, with
        # separators pinned so the text does not depend on a default that can
        # change, and SORTED so that two rows naming the same inputs in a
        # different order compare equal as strings - the order an author
        # happened to type is not part of what the lineage says. A consumer
        # reads it with `json.loads`.
        return json.dumps(sorted(str(x) for x in v), separators=(",", ":"))
    return v
