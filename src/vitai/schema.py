"""Health-domain dataset schemas.

Conventions: ISO-8601 dates; units in the key name (kg, _km, _s, _g, _h);
null for unknown, never omit a key; one object per line.

`validate_record` is deliberately practical rather than exhaustive: it exists
so an LLM (or a tired human) appending lines gets caught on the mistakes that
actually corrupt a record - missing keys, bad dates, wrong types, unknown
session types - not to enforce ceremony.
"""

from __future__ import annotations

from datetime import date, datetime

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
    # `hip_pain` is RETIRED at generation 2 in favour of `pain` + `pain_site`:
    # the hip was this record's founding injury, but a record that can only
    # describe one joint cannot describe a second one. Old lines keep it and
    # keep validating; the engine reads them as pain at site "hip" (see
    # `canonical_daily`). New lines write `pain`/`pain_site` instead.
    # `pain_site` is a closed vocabulary (semantics/body_sites.toml) and
    # `pain_side` post-coordinates laterality rather than baking it into the
    # site name - the HL7 FHIR / openEHR pattern. See anatomy.py.
    "daily": ["date", "steps", "distance_km", "active_min", "kcal_out", "kcal_in",
              "protein_g", "sleep_h", "rhr", "hip_pain", "alcohol", "note",
              "source", "mood", "feel", "coverage", "pain", "pain_site",
              "pain_side"],
    # `location` is RETIRED at generation 2, split into `place` (coarse, and
    # deliberately coarse - "home"/"work"/a travel slug, never an address) and
    # `route` (a personal slug the athlete names). Free text could not be
    # grouped, compared, or safely shared.
    "sessions": ["date", "type", "distance_km", "duration_s", "avg_hr", "max_hr",
                 "cadence", "kcal", "location", "rpe", "note",
                 "source", "start_time", "elevation_m", "setting", "route",
                 "place", "with", "context", "planned", "weather"],
    # Third data tier: MODEL-INFERRED knowledge. Append-only like everything
    # else, but carries provenance (model, evidence, confidence) because it is
    # neither ground truth (observed) nor rebuildable (derived). The engine
    # projects it; it never feeds the deterministic number path.
    # `depends_on` (gen 2) is the JTMS justification link: the claim ids this
    # inference rests on. Retracting one of those claims retracts the
    # inference with it, rather than leaving a stale belief behind whose
    # evidence quietly no longer exists.
    "inferences": ["date", "kind", "statement", "confidence", "model",
                   "evidence", "note", "depends_on"],
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
    # --- increment 2 -------------------------------------------------------
    # Sparse ANCHOR-class reads that do not come off the scale: a tape measure,
    # a DEXA scan, an InBody. Anchors top the resolution precedence ladder and,
    # like weight, are read as TENDENCIES over a sparse trend - never as a
    # single point. `body_fat_pct` measured BY the scale already rides the
    # `weight` line (gen-2, G36/G37); this dataset is for the other instruments.
    "measurements": ["date", "kind", "value", "source", "note"],
    # --- increment 3: the medical layer (G11) ------------------------------
    # One condition's whole lifecycle shares a `slug`: onset, the visit, the
    # restriction, the resolution. Appending a line advances the episode; the
    # latest line dated on or before a day IS the state on that day, so
    # "was I gated last Tuesday" is answerable without re-reading prose.
    #
    # `severity` is read by the ENGINE, not only the coach - it is the input to
    # the deterministic severity-to-action mapping in safety.py. `restricts`
    # names the activity classes an episode gates. `provider_type` is coarse on
    # purpose: which KIND of clinician, never which clinician.
    "medical": ["date", "slug", "kind", "title", "body_site", "severity",
                "status", "resolved_date", "restricts", "provider_type",
                "source", "note"],
    # Dated situational mode (G34): what was going on around the athlete. The
    # engine uses it to explain missingness rather than flag it - an absent
    # weigh-in in a week with no scale is not a lapse - and the coach uses it
    # to constrain what it asks for. Effective-dated like all policy (P2).
    "context": ["date", "mode", "facilities", "place", "source", "note"],
    # What the ATHLETE said, in their own words. Deliberately NOT `inferences`,
    # which is MODEL-inferred and carries a `model` field: filing a first-hand
    # statement there would launder the athlete's own claim as engine output,
    # which is P3 inverted. A journal entry is an OBSERVATION of a statement -
    # that it was said, on a date, is ground truth even when what was said is a
    # worry, a guess or an aspiration.
    #
    # `about` links loosely to a goal slug, a metric name or a body site, so a
    # worry can be found again from the thing it concerns. `confidence` is how
    # FIRMLY it was expressed - a passing "maybe I should" is not a decision -
    # never how likely it is to be true. `status` lets a worry be resolved, or a
    # grain of a goal be superseded once it becomes a real goal.
    "journal": ["date", "kind", "text", "about", "source", "confidence",
                "status", "note"],
}

SESSION_TYPES = {"run", "gym_a", "gym_b", "walk", "test", "other"}
INFERENCE_KINDS = {"pattern", "risk", "recommendation", "observation", "question"}

# Generation-2 vocabularies. All are COARSE on purpose: a closed, small set is
# groupable and comparable, and (for `place` and `weather`) carries far less
# about the athlete than the free text it replaces.
FEELS = {"fun", "neutral", "chore"}
COVERAGES = {"full", "partial", "manual"}
SETTINGS = {"outdoor", "indoor", "treadmill", "home"}
SESSION_CONTEXTS = {"commute", "family", "social", "solo", "club"}
WEATHERS = {"dry", "rain", "hot", "cold", "wind"}
MEASUREMENT_KINDS = {"body_fat_pct", "waist_cm", "hip_cm", "chest_cm",
                     "thigh_cm", "arm_cm", "neck_cm", "other"}
CONTEXT_MODES = {"normal", "vacation", "work", "conference", "weekend",
                 "social", "deadline", "heatwave", "travel", "illness"}

# Datasets whose lines are keyed by a stable identity rather than date/source:
# a supersedes chain runs per slug, and the LAST line for a slug is its head.
IDENTITY_KEY: dict[str, str] = {"goals": "slug", "thresholds": "key",
                                "medical": "slug"}

# --- the medical layer (increment 3) -----------------------------------------
MEDICAL_KINDS = {"visit", "injury", "symptom", "lab", "medication", "restriction"}
MEDICAL_STATUSES = {"active", "monitoring", "resolved"}
PROVIDER_TYPES = {"gp", "physio", "specialist", "other"}

# The severity ladder the ENGINE reads. `red_flag` is not a stronger adjective
# than `severe` - it is a different kind of thing: a claim that this needs a
# clinician now, which fires a hardcoded escalation rather than a coaching
# adjustment. The engine has its own independent red-flag triggers too (see
# safety.py), so an LLM can only ever ADD an escalation, never remove one.
SEVERITIES = {"none", "mild", "moderate", "severe", "red_flag"}

# Activity classes an episode can gate. Closed, so a gate is machine-checkable
# against a session rather than a sentence someone has to interpret.
ACTIVITY_CLASSES = {"run", "walk", "gym", "impact", "upper_body", "lower_body",
                    "all"}

GOAL_POLICIES = {"monotonic", "guarded"}
# `proposed` is a GRAIN of a goal: mentioned, not committed. Without it a
# half-formed intention has nowhere to live except prose, and the coach
# cannot tell an aspiration from a decision - which matters, because
# treating a musing as a commitment is how an athlete ends up held to
# something they never actually chose.
GOAL_STATUSES = {"proposed", "active", "paused", "achieved", "abandoned"}

# Journal entry kinds. `claim` is the athlete asserting a fact about
# themselves (checkable against the record); `worry` is a concern worth
# surfacing later; `idea` is an unformed intention; `preference` shapes what
# the coach may propose; `question` is something they asked that deserves an
# answer when the data can give one.
JOURNAL_KINDS = {"claim", "worry", "idea", "preference", "question", "note"}
JOURNAL_STATUSES = {"open", "resolved", "superseded", "declined"}
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
    "weight": {"body_fat_pct": 2, "kg_lo": 2, "kg_hi": 2,
               "body_fat_lo": 2, "body_fat_hi": 2},
    "daily": {"source": 2, "mood": 2, "feel": 2, "coverage": 2,
              "pain": 2, "pain_site": 2, "pain_side": 2},
    "sessions": {"source": 2, "start_time": 2, "elevation_m": 2, "setting": 2,
                 "route": 2, "place": 2, "with": 2, "context": 2,
                 "planned": 2, "weather": 2},
    "inferences": {"depends_on": 2},
}

# The mirror of KEY_GENERATION: the generation at which a key stopped being
# required. A retired key stays LEGAL forever (an old line that carries it is
# not wrong, and must keep validating), but a line written at or after the
# retirement generation is not expected to carry it. Without this, replacing
# `hip_pain` with `pain` would force every new line to keep writing the field
# it replaced - a schema that can only ever grow.
KEY_RETIREMENT: dict[str, dict[str, int]] = {
    "daily": {"hip_pain": 2},
    "sessions": {"location": 2},
}

CURRENT_GENERATION: dict[str, int] = {name: 1 for name in KEYS}
for _ds in ("weight", "daily", "sessions", "inferences"):
    CURRENT_GENERATION[_ds] = 2


def key_generation(dataset: str, key: str) -> int:
    """Generation a key was introduced in (1 = founding)."""
    return KEY_GENERATION.get(dataset, {}).get(key, 1)


def key_retirement(dataset: str, key: str) -> int | None:
    """Generation a key stopped being required, or None if it is still current."""
    return KEY_RETIREMENT.get(dataset, {}).get(key)


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
    "mood": (int,), "pain": (int,), "elevation_m": _NUMERIC,
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


def _bad_time(v: object) -> bool:
    """An ISO-8601 timestamp, offset optional but strongly preferred.

    The offset is what makes two platforms' claims about the same run
    comparable across a timezone change (F3's day-boundary rule), so the
    resolution layer's time-intersect match needs it.
    """
    if not isinstance(v, str):
        return True
    try:
        datetime.fromisoformat(v)
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
        # A key is required only if it existed at this line's generation AND
        # had not yet been retired by it. A newer key legitimately absent from
        # an older line is NOT missing, and neither is a retired key absent
        # from a newer one.
        if k in rec or key_generation(dataset, k) > line_gen:
            continue
        retired = key_retirement(dataset, k)
        if retired is None or line_gen < retired:
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
    if dataset == "daily":
        for k in ("hip_pain", "pain", "mood"):
            if (p := rec.get(k)) is not None and isinstance(p, int) \
                    and not isinstance(p, bool) and not 0 <= p <= 10:
                problems.append(f"'{k}' is a 0-10 scale, got {p!r}")
        problems += _enum(rec, "feel", FEELS, optional=True)
        problems += _enum(rec, "coverage", COVERAGES, optional=True)
        # A site without a score says nothing, and a NON-ZERO score without a
        # site is the ambiguity `pain_site` exists to remove. Zero needs no
        # body part: "nothing hurt today" is a complete statement, and it is
        # deliberately distinct from null, which means nobody looked.
        if (p := rec.get("pain")) is not None and p and not rec.get("pain_site"):
            problems.append("'pain' needs a 'pain_site' (which body part)")
        if rec.get("pain_site") and rec.get("pain") is None \
                and rec.get("hip_pain") is None:
            problems.append("'pain_site' without a 'pain' score says nothing")
        problems += _validate_pain_location(rec)
    if dataset == "sessions":
        problems += _enum(rec, "setting", SETTINGS, optional=True)
        problems += _enum(rec, "context", SESSION_CONTEXTS, optional=True)
        problems += _enum(rec, "weather", WEATHERS, optional=True)
        if (st := rec.get("start_time")) is not None and _bad_time(st):
            problems.append(f"bad start_time {st!r} (ISO-8601, e.g. "
                            "'2030-05-01T07:12:00+02:00')")
        if (p := rec.get("planned")) is not None and not isinstance(p, str):
            problems.append(f"'planned' is a goal/plan slug or null, got {p!r}")
    if dataset == "measurements":
        problems += _enum(rec, "kind", MEASUREMENT_KINDS)
        if rec.get("value") is None:
            problems.append("'value' is required (a measurement with no "
                            "number is not a measurement)")
        if rec.get("kind") == "body_fat_pct" and (v := rec.get("value")) is not None:
            if isinstance(v, _NUMERIC) and not isinstance(v, bool) \
                    and not 0 < v < 100:
                problems.append(f"'body_fat_pct' is a 0-100 percentage, got {v!r}")
    if dataset == "context":
        problems += _enum(rec, "mode", CONTEXT_MODES)
    if dataset == "medical":
        problems += _validate_medical(rec)
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
    if dataset == "journal":
        problems += _enum(rec, "kind", JOURNAL_KINDS)
        problems += _enum(rec, "status", JOURNAL_STATUSES, optional=True)
        if not isinstance(rec.get("text"), str) or not rec.get("text").strip():
            problems.append("'text' must be a non-empty string - a journal "
                            "entry with no words is not an entry")
        if (c := rec.get("confidence")) is not None:
            if isinstance(c, bool) or not isinstance(c, _NUMERIC) or not 0 <= c <= 1:
                problems.append(f"'confidence' is 0-1 or null, got {c!r}")
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


def _validate_medical(rec: dict) -> list[str]:
    """One line of a medical episode.

    Stricter than the observation datasets, deliberately: this is the input to
    a safety decision, so a malformed line must fail loudly at `vitai validate`
    rather than silently produce no gate. A missing gate is the failure mode
    that matters here - the athlete trains on an injury nobody flagged.
    """
    from .anatomy import is_site, known_sites

    problems: list[str] = []
    for key in ("slug", "title"):
        if not isinstance(rec.get(key), str) or not rec.get(key):
            problems.append(f"'{key}' must be a non-empty string")
    problems += _enum(rec, "kind", MEDICAL_KINDS)
    problems += _enum(rec, "status", MEDICAL_STATUSES)
    problems += _enum(rec, "severity", SEVERITIES)
    problems += _enum(rec, "provider_type", PROVIDER_TYPES, optional=True)

    if (site := rec.get("body_site")) is not None and not is_site(site):
        problems.append(f"unknown 'body_site' {site!r} - use one of "
                        f"{', '.join(known_sites())} (semantics/body_sites.toml)")
    if (rd := rec.get("resolved_date")) is not None:
        if _bad_date(rd):
            problems.append(f"bad resolved_date {rd!r} (ISO-8601 YYYY-MM-DD)")
        elif isinstance(rec.get("date"), str) and not _bad_date(rec["date"]) \
                and rd < rec["date"]:
            problems.append(f"resolved_date {rd} precedes onset {rec['date']}")
    # A resolved episode without a closing date leaves the window open forever,
    # which quietly breaks forgiveness maths downstream (a day is excused iff it
    # falls inside an episode window).
    if rec.get("status") == "resolved" and not rec.get("resolved_date"):
        problems.append("a resolved episode needs a 'resolved_date' "
                        "(it closes the episode window)")
    if rec.get("status") != "resolved" and rec.get("resolved_date"):
        problems.append("'resolved_date' set but status is not 'resolved'")

    for cls in _restriction_classes(rec):
        if cls not in ACTIVITY_CLASSES:
            problems.append(f"unknown activity class {cls!r} in 'restricts' - "
                            f"use one of {sorted(ACTIVITY_CLASSES)}")
    return problems


def _restriction_classes(rec: dict) -> list[str]:
    """Activity classes named by a `restricts` field (comma or space separated)."""
    raw = rec.get("restricts")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [p.strip() for p in str(raw).replace(",", " ").split() if p.strip()]


def _validate_pain_location(rec: dict) -> list[str]:
    """`pain_site` against the curated registry, `pain_side` against anatomy.

    Imported lazily so `schema` stays importable without touching the
    filesystem - validation is the only thing that needs the registry, and a
    schema module that reads a file on import is a schema module that fails
    in odd places.
    """
    from .anatomy import SIDES, describe, is_paired, is_site, known_sites, resolve

    problems: list[str] = []
    site = rec.get("pain_site")
    side = rec.get("pain_side")

    if site and not is_site(site):
        problems.append(
            f"unknown 'pain_site' {site!r} - use one of {', '.join(known_sites())} "
            "(or an alias the registry knows; add one in semantics/body_sites.toml "
            "rather than inventing a site here)")
        return problems

    if side is not None and side not in SIDES:
        problems.append(f"'pain_side' must be one of {sorted(SIDES)} or null, "
                        f"got {side!r}")
    if side is not None and not site:
        problems.append("'pain_side' without a 'pain_site' says nothing")

    if site and rec.get("pain"):
        # A paired structure without a side is not actionable: "my knee hurts"
        # does not tell a coach which knee to stop loading. Midline sites take
        # no side at all, and claiming one would be a false precision.
        if is_paired(site) and side is None:
            problems.append(
                f"'{resolve(site)}' exists on both sides - set 'pain_side' to "
                "left, right or bilateral")
        if not is_paired(site) and side is not None:
            problems.append(
                f"'{resolve(site)}' is a midline site ({describe(site)}) and "
                "takes no 'pain_side'")
    return problems


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
