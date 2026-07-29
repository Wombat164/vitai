"""Health-domain dataset schemas.

Conventions: ISO-8601 dates; units in the key name (kg, _km, _s, _g, _h);
null for unknown, never omit a key; one object per line.

`validate_record` is deliberately practical rather than exhaustive: it exists
so an LLM (or a tired human) appending lines gets caught on the mistakes that
actually corrupt a record - missing keys, bad dates, wrong types, unknown
session types - not to enforce ceremony.
"""

from __future__ import annotations

from datetime import date

# dataset -> ordered keys (column order for the SQLite read model)
KEYS: dict[str, list[str]] = {
    # `kg` + `body_fat_pct` are the OBSERVED atoms; fat mass and fat-free mass
    # are DERIVED from them in the report layer (G36), never stored - scale
    # weight is a lossy proxy for the goal-relevant quantity (fat), so the
    # decomposition is rebuildable, not ground truth. `*_lo`/`*_hi` carry the
    # instrument's measurement-uncertainty band (G37): a wide band (bioimpedance
    # FFM, a jittery scale) downgrades trust in that reading without discarding
    # it. All gen-2 (see KEY_GENERATION); gen-1 weight lines predate them.
    "weight": ["date", "kg", "source", "note", "body_fat_pct",
               "kg_lo", "kg_hi", "body_fat_lo", "body_fat_hi"],
    "daily": ["date", "steps", "distance_km", "active_min", "kcal_out", "kcal_in",
              "protein_g", "sleep_h", "rhr", "hip_pain", "alcohol", "note"],
    "sessions": ["date", "type", "distance_km", "duration_s", "avg_hr", "max_hr",
                 "cadence", "kcal", "location", "rpe", "note"],
    # Third data tier: MODEL-INFERRED knowledge. Append-only like everything
    # else, but carries provenance (model, evidence, confidence) because it is
    # neither ground truth (observed) nor rebuildable (derived). The engine
    # projects it; it never feeds the deterministic number path.
    "inferences": ["date", "kind", "statement", "confidence", "model",
                   "evidence", "note"],
    # --- policy datasets (increment 1) --------------------------------------
    # These are DATED POLICY, not observations: what the athlete was aiming at,
    # and when. A goal is edited by appending a new line with the same `slug`
    # (see IDENTITY_KEY); the chain of lines IS the edit history, so "when was
    # this set / last changed / loosened" is queryable instead of lost (G6).
    # `date` is the declaration/edit date - the day the policy takes effect.
    #
    # `metric` names a `daily`/`sessions` column, or the literal "external" for
    # a goal another app owns (a segment crown, a language streak) - vitai
    # models, tracks and reinforces it via `tracker` but never auto-verdicts it
    # (G19). `policy` is the contribution rule (G18): "monotonic" means more
    # always counts; "guarded" means volume beyond `guard_pct` above the recent
    # baseline is unbudgeted ramp - it does NOT advance the goal.
    #
    # `dataset` + `session_type` SCOPE which events feed the goal. They matter
    # because one metric name can mean two things: `distance_km` is walking on
    # a `daily` line and running on a `sessions` line, so an unscoped running
    # goal would quietly count the athlete's commute. Null means "any".
    "goals": ["date", "slug", "title", "metric", "dataset", "session_type",
              "tracker", "target", "policy", "guard_pct", "period",
              "on_period_end", "deadline", "status", "motivator", "rationale",
              "on_success", "on_miss", "accountability", "set_by", "reason",
              "note"],
    # G14/G20: every threshold is effective-dated, so editing one today can
    # never silently re-score a past week. `change_kind` separates a genuine
    # policy CHANGE from a CORRECTION of a mis-entered number (G31) - only the
    # former is churn, and only the former can be suspiciously timed.
    "thresholds": ["date", "key", "value", "change_kind", "set_by", "reason",
                   "note"],
    # A recorded accomplishment worth keeping. Distinct from a MILESTONE, which
    # the engine derives; `source` carries authorship (G31) so a hand-logged
    # race finish is never confused with an engine-derived crossing.
    "achievements": ["date", "title", "goal", "source", "note"],
}

SESSION_TYPES = {"run", "gym_a", "gym_b", "walk", "test", "other"}
INFERENCE_KINDS = {"pattern", "risk", "recommendation", "observation", "question"}

# Datasets whose lines are keyed by a stable identity rather than date/source:
# a supersedes chain runs per slug, and the LAST line for a slug is its head.
IDENTITY_KEY: dict[str, str] = {"goals": "slug", "thresholds": "key"}

GOAL_POLICIES = {"monotonic", "guarded"}
GOAL_STATUSES = {"active", "paused", "achieved", "abandoned"}
GOAL_PERIODS = {"none", "weekly", "monthly", "quarterly", "yearly"}
ON_PERIOD_END = {"reset", "carry", "escalate"}
CHANGE_KINDS = {"change", "correction"}
AUTHORS = {"athlete", "coach", "onboard", "derived"}
EXTERNAL_METRIC = "external"

# --- schema generations (G25) ------------------------------------------------
# A key is REQUIRED on a line only if the key's introduction generation is <=
# the line's own generation (its `_gen` field, default 1). This lets an additive
# nullable field land in a later increment WITHOUT invalidating every line
# written before the field existed - the code-verified time bomb the whole-model
# redteam found. Founding keys are generation 1 (implicit). When a field is
# added in a future increment, register its generation here and bump
# CURRENT_GENERATION for that dataset; new writes stamp `_gen = current`.
KEY_GENERATION: dict[str, dict[str, int]] = {
    # dataset -> {key: generation it was introduced}. Keys absent here are gen 1.
    # e.g. increment 2 will add:  "daily": {"mood": 2, "feel": 2, "coverage": 2}
    "weight": {"body_fat_pct": 2, "kg_lo": 2, "kg_hi": 2,
               "body_fat_lo": 2, "body_fat_hi": 2},
}
CURRENT_GENERATION: dict[str, int] = {name: 1 for name in KEYS}
CURRENT_GENERATION["weight"] = 2


def key_generation(dataset: str, key: str) -> int:
    """Generation a key was introduced in (1 = founding)."""
    return KEY_GENERATION.get(dataset, {}).get(key, 1)


def line_generation(rec: dict) -> int:
    """A line's own schema generation - its `_gen` field, default 1 (legacy
    lines predate the marker and are held only to the founding schema)."""
    g = rec.get("_gen", 1)
    return g if isinstance(g, int) and not isinstance(g, bool) and g >= 1 else 1

# key -> allowed python types when not null (bool checked before int: bool is int)
_NUMERIC = (int, float)
_TYPES: dict[str, tuple[type, ...]] = {
    "kg": _NUMERIC, "steps": (int,), "distance_km": _NUMERIC, "active_min": (int,),
    "kcal_out": (int,), "kcal_in": (int,), "protein_g": _NUMERIC, "sleep_h": _NUMERIC,
    "rhr": (int,), "hip_pain": (int,), "duration_s": (int,), "avg_hr": (int,),
    "max_hr": (int,), "cadence": (int,), "kcal": _NUMERIC, "rpe": (int,),
    "confidence": _NUMERIC,
    "body_fat_pct": _NUMERIC, "kg_lo": _NUMERIC, "kg_hi": _NUMERIC,
    "body_fat_lo": _NUMERIC, "body_fat_hi": _NUMERIC,
    "target": _NUMERIC, "guard_pct": _NUMERIC, "value": _NUMERIC,
}

# extra keys that are always legal (the supersedes mechanic + schema generation)
META_KEYS = {"supersedes", "_gen"}


def _bad_date(v: object) -> bool:
    if not isinstance(v, str):
        return True
    try:
        date.fromisoformat(v)
        return False
    except ValueError:
        return True


def validate_record(dataset: str, rec: dict) -> list[str]:
    """Problems with one record; empty list means valid."""
    problems: list[str] = []
    keys = KEYS[dataset]
    line_gen = line_generation(rec)
    if "_gen" in rec and line_generation(rec) != rec["_gen"]:
        problems.append(f"'_gen' must be a positive integer, got {rec['_gen']!r}")
    for k in keys:
        # A key is required only if it existed at this line's generation; a
        # newer key legitimately absent from an older line is NOT missing.
        if k not in rec and key_generation(dataset, k) <= line_gen:
            problems.append(f"missing key '{k}' (use null for unknown, never omit)")
    for k in rec:
        if k not in keys and k not in META_KEYS:
            problems.append(f"unknown key '{k}'")
    if _bad_date(rec.get("date")):
        problems.append(f"bad date {rec.get('date')!r} (ISO-8601 YYYY-MM-DD)")
    for k, types in _TYPES.items():
        if k in keys and (v := rec.get(k)) is not None and k in rec:
            if isinstance(v, bool) or not isinstance(v, types):
                problems.append(f"'{k}' should be a number or null, got {v!r}")
    if dataset == "weight":
        if (bf := rec.get("body_fat_pct")) is not None and not isinstance(bf, bool):
            if isinstance(bf, _NUMERIC) and not 0 < bf < 100:
                problems.append(f"'body_fat_pct' is a 0-100 percentage, got {bf!r}")
        # measurement band (G37): lo <= point <= hi when all three are present
        for point, lo, hi in (("kg", "kg_lo", "kg_hi"),
                              ("body_fat_pct", "body_fat_lo", "body_fat_hi")):
            p, a, b = rec.get(point), rec.get(lo), rec.get(hi)
            if all(isinstance(v, _NUMERIC) and not isinstance(v, bool)
                   for v in (p, a, b)) and not a <= p <= b:
                problems.append(f"band out of order: {lo}<={point}<={hi} "
                                f"violated ({a} <= {p} <= {b})")
    if dataset == "daily" and (a := rec.get("alcohol")) is not None:
        if not isinstance(a, bool):
            problems.append(f"'alcohol' should be true/false/null, got {a!r}")
    if dataset == "sessions" and rec.get("type") not in SESSION_TYPES:
        problems.append(f"'type' must be one of {sorted(SESSION_TYPES)}, got {rec.get('type')!r}")
    if dataset == "daily" and (p := rec.get("hip_pain")) is not None:
        if isinstance(p, int) and not isinstance(p, bool) and not 0 <= p <= 10:
            problems.append(f"'hip_pain' is a 0-10 scale, got {p!r}")
    if dataset == "inferences":
        if rec.get("kind") not in INFERENCE_KINDS:
            problems.append(f"'kind' must be one of {sorted(INFERENCE_KINDS)}, "
                            f"got {rec.get('kind')!r}")
        if (c := rec.get("confidence")) is not None:
            if isinstance(c, bool) or not isinstance(c, _NUMERIC) or not 0 <= c <= 1:
                problems.append(f"'confidence' is 0-1 or null, got {c!r}")
        for k in ("statement", "model"):
            if not isinstance(rec.get(k), str) or not rec.get(k):
                problems.append(f"'{k}' must be a non-empty string")
    problems += _validate_policy(dataset, rec)
    return problems


def _enum(rec: dict, key: str, allowed: set[str], *,
          optional: bool = False) -> list[str]:
    """One closed-vocabulary check. `optional` lets the key be null."""
    v = rec.get(key)
    if v is None and optional:
        return []
    if v not in allowed:
        return [f"'{key}' must be one of {sorted(allowed)}, got {v!r}"]
    return []


def _validate_policy(dataset: str, rec: dict) -> list[str]:
    """Rules for the dated-policy datasets (goals/thresholds/achievements).

    Kept separate from the observation rules because policy lines answer a
    different question - not "what happened" but "what were we aiming at, and
    who decided that when" - and the identity/authorship fields are what make
    the edit history auditable.
    """
    problems: list[str] = []
    if dataset == "goals":
        for k in ("slug", "title"):
            if not isinstance(rec.get(k), str) or not rec.get(k):
                problems.append(f"'{k}' must be a non-empty string")
        problems += _enum(rec, "policy", GOAL_POLICIES)
        problems += _enum(rec, "status", GOAL_STATUSES)
        problems += _enum(rec, "period", GOAL_PERIODS)
        problems += _enum(rec, "on_period_end", ON_PERIOD_END, optional=True)
        problems += _enum(rec, "set_by", AUTHORS, optional=True)
        if not isinstance(rec.get("metric"), str) or not rec.get("metric"):
            problems.append("'metric' must be a non-empty string "
                            f"(a dataset column or {EXTERNAL_METRIC!r})")
        if (ds := rec.get("dataset")) is not None and ds not in ("daily", "sessions"):
            problems.append(f"'dataset' scopes to 'daily' or 'sessions', got {ds!r}")
        if (st := rec.get("session_type")) is not None and st not in SESSION_TYPES:
            problems.append(f"'session_type' must be one of {sorted(SESSION_TYPES)}, "
                            f"got {st!r}")
        # An external goal is tracked elsewhere, so it needs a pointer and
        # cannot carry an engine target; an internal goal needs a target to
        # verdict against. Guard percentage only means something when guarded.
        if rec.get("metric") == EXTERNAL_METRIC:
            if not isinstance(rec.get("tracker"), str) or not rec.get("tracker"):
                problems.append("an external goal needs 'tracker' (where it lives)")
        elif rec.get("target") is None and rec.get("status") == "active":
            problems.append("an active non-external goal needs a numeric 'target'")
        if rec.get("policy") == "guarded" and rec.get("guard_pct") is None:
            problems.append("a guarded goal needs 'guard_pct' (the ramp headroom)")
        if (g := rec.get("guard_pct")) is not None and not isinstance(g, bool):
            if isinstance(g, _NUMERIC) and g < 0:
                problems.append(f"'guard_pct' is a non-negative ratio, got {g!r}")
        if (dl := rec.get("deadline")) is not None and _bad_date(dl):
            problems.append(f"bad deadline {dl!r} (ISO-8601 YYYY-MM-DD)")
    if dataset == "thresholds":
        if not isinstance(rec.get("key"), str) or not rec.get("key"):
            problems.append("'key' must be a non-empty string")
        problems += _enum(rec, "change_kind", CHANGE_KINDS)
        problems += _enum(rec, "set_by", AUTHORS, optional=True)
        if rec.get("value") is None:
            problems.append("'value' is required (null retires nothing - "
                            "append a new line to change a threshold)")
    if dataset == "achievements":
        if not isinstance(rec.get("title"), str) or not rec.get("title"):
            problems.append("'title' must be a non-empty string")
        problems += _enum(rec, "source", AUTHORS)
    return problems
