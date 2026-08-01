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

from .clocks import (is_aware, is_stamp, order_key,  # noqa: F401
                     parse_time, stamp_instant)
from .artifacts import is_reference
from .provenance import capture_problems
from .sets import problems as set_problems
from .meals import problems as meal_problems
from .provenance import problems as provenance_problems
from .provenance import value_kind_problems

# dataset -> ordered keys (column order for the SQLite read model)
KEYS: dict[str, list[str]] = {
    # `kg` + `body_fat_pct` are the OBSERVED atoms; fat mass and fat-free mass
    # are DERIVED from them in the report layer (G36), never stored - scale
    # weight is a lossy proxy for the goal-relevant quantity (fat), so the
    # decomposition is rebuildable, not ground truth. `*_lo`/`*_hi` carry the
    # instrument's measurement-uncertainty band (G37): a wide band (bioimpedance
    # FFM, a jittery scale) downgrades trust in that reading without discarding
    # it. All gen-2 (see KEY_GENERATION); gen-1 weight lines predate them.
    #
    # `measured_at` is OBSERVATION time - HH:MM local, the same shape as
    # `sessions.start_time`, because a weigh-in is a point measurement. It
    # matters more than it looks: body mass swings about a kilogram between
    # morning-fasted and evening, so an unrecorded drift from evening to
    # morning weigh-ins manufactures a week of apparent progress. Absent stays
    # absent - the engine never infers a probable weigh-in time, it says the
    # rate could not be checked.
    "weight": ["date", "kg", "source", "note", "body_fat_pct",
               "kg_lo", "kg_hi", "body_fat_lo", "body_fat_hi", "measured_at",
               "recorded_at", "origin", "path", "origin_evidence",
               "capture", "read_by", "modelled", "artifact"],
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
              "pain_side", "recorded_at", "origin", "path",
              "origin_evidence", "capture", "read_by", "modelled", "artifact"],
    # `location` is RETIRED at generation 2, split into `place` (coarse, and
    # deliberately coarse - "home"/"work"/a travel slug, never an address) and
    # `route` (a personal slug the athlete names). Free text could not be
    # grouped, compared, or safely shared.
    #
    # `track` / `activity_id` / `activity_source` are TWO different things,
    # post-coordinated rather than crammed into one field (#43). `track` is a
    # LOCAL ARTIFACT - a repo-relative path to the stored GPX/FIT/TCX, which
    # is what `vitai route` reads. `activity_id` is an EXTERNAL IDENTITY - the
    # id a platform assigned - which is what dedupes a re-run import. They
    # have different lifetimes: an archive can be re-laid-out without the id
    # changing, and an id is meaningless once you leave the platform while the
    # file stays readable.
    #
    # `activity_source` names who ASSIGNED the id, which is not necessarily
    # who recorded the activity - Strava re-exporting a Polar-recorded run
    # gives an id that is evidence of relaying, not of recording (#35).
    #
    # `activity_id` is also the only per-row IDENTITY a session has. Without
    # it, two runs on one day from one source share a `supersedes` reference,
    # so correcting either retires both - silent data loss of exactly the kind
    # #16 exists to prevent.
    "sessions": ["date", "type", "distance_km", "duration_s", "avg_hr", "max_hr",
                 "cadence", "kcal", "location", "rpe", "note",
                 "source", "start_time", "elevation_m", "setting", "route",
                 "place", "with", "context", "planned", "weather", "recorded_at",
                 "track", "activity_id", "activity_source",
                 "origin", "path", "origin_evidence", "capture", "read_by",
                 "modelled", "type_source", "artifact"],
    # Third data tier: MODEL-INFERRED knowledge. Append-only like everything
    # else, but carries provenance (model, evidence, confidence) because it is
    # neither ground truth (observed) nor rebuildable (derived). The engine
    # projects it; it never feeds the deterministic number path.
    # `depends_on` (gen 2) is the JTMS justification link: the claim ids this
    # inference rests on. Retracting one of those claims retracts the
    # inference with it, rather than leaving a stale belief behind whose
    # evidence quietly no longer exists.
    "inferences": ["date", "kind", "statement", "confidence", "model",
                   "evidence", "note", "depends_on", "recorded_at"],
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
    #
    # `deadline_kind` (gen 2) is the difference between a race date and a date
    # the athlete invented. Without it G20's churn logic flags a legitimately
    # moved soft deadline as goalpost-moving, which is an accusation about a
    # commitment nobody else ever held them to (G86). `event` anchors the goal
    # to a real-world fixture, which makes the deadline hard by derivation -
    # an organiser's date is not the athlete's to move.
    #
    # `verification` says WHO can ever settle this goal: the engine
    # (`measured`), another app (`external`, the G19 case), or nobody at all
    # (`attested`). An attested goal - "enjoy running again", "be the parent
    # who joins in" - has no metric and never will, and G83 found that is
    # almost always what athletes say they would be sad to lose.
    #
    # `change_kind` mirrors `thresholds` (G31): a correction of a mis-entered
    # line is not the athlete changing their mind, and counting it as churn
    # manufactures a plan-stability problem that does not exist.
    "goals": ["date", "slug", "title", "metric", "dataset", "session_type",
              "tracker", "target", "policy", "guard_pct", "period",
              "on_period_end", "deadline", "status", "motivator", "rationale",
              "on_success", "on_miss", "accountability", "set_by", "reason",
              "note", "event", "deadline_kind", "verification", "change_kind", "recorded_at"],
    # A dated real-world FIXTURE, and the thing a plan is built backwards from
    # (G86). Distinct from a MILESTONE, which the engine derives as a fraction
    # of a target: a milestone is a consequence of progress, an event happens
    # whether the athlete is ready or not.
    #
    # `date` is when the line was written (effective-dating, P2, like every
    # other policy dataset); `event_date` is when the fixture actually falls,
    # which is usually in the future. Collapsing the two would make a race
    # declared today invisible to `state()` until the day it happened.
    #
    # `immovable` is a property of the EVENT (the organiser sets the date);
    # `deadline_kind` is a property of a GOAL. They are related but not the
    # same field - a soft goal may still be anchored to a hard fixture.
    "events": ["date", "slug", "title", "kind", "event_date", "priority",
               "immovable", "place", "status", "set_by", "reason", "note", "recorded_at"],
    # G14/G20: every threshold is effective-dated, so editing one today can
    # never silently re-score a past week. `change_kind` separates a genuine
    # policy CHANGE from a CORRECTION of a mis-entered number (G31) - only the
    # former is churn, and only the former can be suspiciously timed.
    "thresholds": ["date", "key", "value", "change_kind", "set_by", "reason",
                   "note", "recorded_at"],
    # A recorded accomplishment worth keeping. Distinct from a MILESTONE, which
    # the engine derives; `source` carries authorship (G31) so a hand-logged
    # race finish is never confused with an engine-derived crossing.
    # `occurred_date` is the same event-versus-entry split as `medical`'s
    # `onset_date`: a race finished in March and written up in July belongs on
    # the day it happened. Named differently on purpose - an achievement is a
    # point event that OCCURRED, an episode has an ONSET that opens a window.
    "achievements": ["date", "title", "goal", "source", "note", "occurred_date", "recorded_at"],
    # --- increment 2 -------------------------------------------------------
    # Sparse ANCHOR-class reads that do not come off the scale: a tape measure,
    # a DEXA scan, an InBody. Anchors top the resolution precedence ladder and,
    # like weight, are read as TENDENCIES over a sparse trend - never as a
    # single point. `body_fat_pct` measured BY the scale already rides the
    # `weight` line (gen-2, G36/G37); this dataset is for the other instruments.
    "measurements": ["date", "kind", "value", "source", "note", "recorded_at",
                     "origin", "path", "origin_evidence", "capture",
                     "read_by", "modelled", "artifact"],
    # One row per SET (#97). The set is the atom: anything coarser cannot say
    # that a load was attempted and not completed, or that a set stopped
    # short of failure - and both of those produced wrong readings of a real
    # record within a day of each other.
    #
    # `reps_attempted` vs `reps_completed` is the first distinction:
    # attempted counts reps INITIATED. A failed top set is
    # `reps_attempted: 1, reps_completed: 0`, which is a different fact from
    # no row at all.
    #
    # `failure` is three states rather than a flag, because "to failure" is
    # ambiguous across all three. Null means UNSTATED and must never be read
    # as maximal.
    #
    # `block`/`round`/`index` carry loop membership: without them a 5-round
    # circuit is 25 unrelated rows. `set_index` rather than the spec's
    # `index`, stated rather than silently changed: `index` is a SQL reserved
    # word and the read model refuses to build with it, the same way `table`
    # did one increment ago. `session_start` links a set to its
    # session by (date, start_time) - offset-bearing per the clocks canon,
    # and NOT called `session`, which would imply an identity `sessions` does
    # not have (#43).
    "sets": ["date", "session_start", "exercise", "block", "round",
             "set_index",
             "reps_completed", "reps_attempted", "load", "load_type",
             "load_unit", "machine", "set_type", "failure", "rir", "rpe",
             "rest_s", "tempo", "duration_s", "side", "note",
             "source", "recorded_at", "origin", "path", "origin_evidence",
             "capture", "read_by"],
    # One row per ITEM of a meal, never per dish (#96). A dish-level number
    # cannot be corrected, cannot be questioned and cannot say which part it
    # is unsure about - and the total is the least defensible part of a photo
    # estimate, so it is derived here and never stored.
    #
    # `grams_lo`/`grams_hi` carry the part a photograph cannot settle. There
    # is NO confidence field: no corpus of photo-estimated meals scored
    # against weighed truth exists, so a number there would be a decimal point
    # pretending to be calibration. The range IS the confidence statement.
    #
    # The per-100 g figures are what the TABLE said, stored beside the name of
    # the table. `food_table` rather than `table`, which is a SQL reserved
    # word: the read model refused to build. A composition table is an
    # external fact that gets revised, so
    # a row holding only a gram count would silently re-price a two-year-old
    # meal the day an update shipped.
    "meals": ["date", "meal", "item", "grams", "grams_lo", "grams_hi",
              "kcal_100g", "protein_100g", "fat_100g", "carb_100g",
              "food_table", "note", "source", "recorded_at",
              "origin", "path", "origin_evidence", "capture", "read_by"],
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
    #
    # `date` is WHEN THIS WAS WRITTEN; `onset_date` is when the episode began
    # in the world. They were one field, which meant backfilling any history -
    # an old injury, a diagnosis from years ago, a surgery - was rejected
    # ("resolved_date precedes onset"), and the workaround of back-dating the
    # row destroyed the only record of when it was entered. Both matter: P2
    # needs the entry date (what was known when), and the episode window needs
    # the onset. Absent, onset defaults to `date`, so nothing existing moves.
    #
    # `precondition` names a daily check that must PASS before the gate lifts.
    "medical": ["date", "slug", "kind", "title", "body_site", "severity",
                "status", "resolved_date", "restricts", "provider_type",
                "source", "note", "expects", "onset_date", "precondition",
                "restriction", "recorded_at"],
    # The result of a named check, on a day (G28 gate mechanics). A rehab plan
    # says "5 gentle hops before each run; pain in the hip means do not run
    # today" - a gate CONDITIONAL on a test performed that morning. Without
    # this the whole instruction sits in a note where no rule can read it,
    # which is the prose problem G28 exists to solve, one level down.
    "checks": ["date", "slug", "result", "value", "source", "note", "recorded_at"],
    # Dated situational mode (G34): what was going on around the athlete. The
    # engine uses it to explain missingness rather than flag it - an absent
    # weigh-in in a week with no scale is not a lapse - and the coach uses it
    # to constrain what it asks for. Effective-dated like all policy (P2).
    "context": ["date", "mode", "facilities", "place", "source", "note", "recorded_at"],
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
    # The manifest for the content-addressed artifact store (#80). Its own
    # dataset rather than a column, because ONE artifact backs SEVERAL rows -
    # a single console photograph carries distance, pace, power and stroke
    # rate - so the reference is many-to-one.
    #
    # `removed` is a TOMBSTONE. The store is append-only, so a deletion cannot
    # rewrite the observation that cites an artifact and should not want to:
    # appending "the athlete deleted this" keeps a retention decision
    # distinguishable from data loss, which are completely different facts.
    "artifacts": ["date", "sha256", "media_type", "bytes", "captured_at",
                  "origin", "kind", "note", "removed", "reason",
                  "recorded_at"],
    "journal": ["date", "kind", "text", "about", "source", "confidence",
                "status", "note", "recorded_at"],
}

# Sourced from semantics/session_types.toml (G85): a curated registry, not a
# set written from one athlete's examples. Retired values (`gym_a`, `gym_b`)
# stay legal and resolve forward - see vocab.is_retired / resolve_session_type.
def _session_types() -> set[str]:
    from .vocab import registry, retired
    return set(registry("session_types").get("types") or {}) | set(
        retired("session_types"))


SESSION_TYPES = _session_types()
INFERENCE_KINDS = {"pattern", "risk", "recommendation", "observation", "question"}

# Generation-2 vocabularies. All are COARSE on purpose: a closed, small set is
# groupable and comparable, and (for `place` and `weather`) carries far less
# about the athlete than the free text it replaces.
FEELS = {"fun", "neutral", "chore"}
COVERAGES = {"full", "partial", "manual"}
# Sourced from semantics/settings.toml (#53): WHERE an activity happened, as
# its own axis, so `other` + `outdoor` expresses the catchall a vendor would
# pre-coordinate into `OTHER_OUTDOOR`. Retired values stay legal.
def _settings() -> set[str]:
    from .vocab import registry, retired
    return set(registry("settings").get("settings") or {}) | set(
        retired("settings"))


SETTINGS = _settings()
SESSION_CONTEXTS = {"commute", "family", "social", "solo", "club"}
WEATHERS = {"dry", "rain", "hot", "cold", "wind"}
MEASUREMENT_KINDS = {"body_fat_pct", "waist_cm", "hip_cm", "chest_cm",
                     "thigh_cm", "arm_cm", "neck_cm", "other"}
CONTEXT_MODES = {"normal", "vacation", "work", "conference", "weekend",
                 "social", "deadline", "heatwave", "travel", "illness"}

# Datasets whose lines are keyed by a stable identity rather than date/source:
# a supersedes chain runs per slug, and the LAST line for a slug is its head.
#
# A TUPLE where one field is not enough. `sets` is the case that forced it:
# many sets share a date and a source, so a `supersedes` correcting set 2 of
# 4 retired all four - the #43 defect, which cost real data once already.
#
# `meals` keys the same way for the same reason: every item of one
# photographed plate shares a date and a source, so a `supersedes`
# correcting the chicken retired the olives and the tomato with it.
IDENTITY_KEY: dict[str, str | tuple[str, ...]] = {
    "goals": "slug", "thresholds": "key", "medical": "slug", "events": "slug",
    "sets": ("session_start", "exercise", "block", "round", "set_index"),
    "meals": ("meal", "item")}

# --- the medical layer (increment 3) -----------------------------------------
# `state` (G57) is a physiological condition rather than an illness -
# breastfeeding, pregnancy, postpartum. It is not something to resolve or treat,
# but it changes what the numbers MEAN: a deficit that is unremarkable normally
# is contraindicated while nursing.
MEDICAL_KINDS = {"visit", "injury", "symptom", "lab", "medication",
                 "restriction", "state"}

# What a state or medication tells the engine to EXPECT (G57/G72). This is the
# difference between a number that is alarming and the same number that is the
# treatment working: rapid loss on a GLP-1 agonist is the drug doing its job,
# and firing a rate tripwire at it tells a succeeding athlete she is failing.
#
# A modifier may RAISE a floor or suppress a rule that would misfire. It may
# never silence an absolute floor - the asymmetry that keeps the safety layer
# honest holds here too.
EXPECTATIONS = {
    "elevated_requirement",   # nursing, pregnancy: needs MORE, not less
    "rapid_loss",             # expected on this medication; do not alarm
    "appetite_suppression",   # low intake is involuntary, not restriction
    "lean_mass_risk",         # the risk that replaces the one we suppressed
}
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
def _activity_classes() -> set[str]:
    from .vocab import registry, retired
    return set(registry("restrictions").get("activity") or {}) | set(
        retired("restrictions"))


ACTIVITY_CLASSES = _activity_classes()

# Datasets a goal may scope its contributing events to.
GOAL_DATASETS = {"daily", "sessions", "weight", "measurements"}

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

# A deadline is HARD (externally owned - a race, a scan, a wedding) or SOFT
# (self-imposed, a direction of travel, movable at no cost to anyone). Kept as
# a closed pair in code rather than a registry because it is not a sample of
# the author's cases: it is the complete answer to one binary question, "may
# the athlete move this date". A registry exists so a vocabulary can grow past
# what the developer imagined; there is no third kind of deadline to discover.
DEADLINE_KINDS = {"hard", "soft"}

# Who can ever settle a goal. `measured` is the engine, from the record;
# `external` is another app (G19 - a segment crown, a language streak);
# `attested` is NOBODY - "I want to enjoy running again" has no metric and
# never will, and the engine must be able to hold a goal it can never verdict.
MEASURED, EXTERNAL, ATTESTED = "measured", "external", "attested"
VERIFICATIONS = {MEASURED, EXTERNAL, ATTESTED}

# Event status, taken verbatim from RFC 5545 (iCalendar) VEVENT STATUS. A
# TENTATIVE fixture is not something to taper into, and a CANCELLED one must
# stay on the record rather than vanish - the entry is history either way.
EVENT_STATUSES = {"tentative", "confirmed", "cancelled"}


# Event kinds and priorities are OPEN axes (an athlete will have a fixture we
# never imagined), so they live in semantics/events.toml - registry, not code.
def _event_kinds() -> set[str]:
    from .vocab import registry, retired
    return set(registry("events").get("kinds") or {}) | set(retired("events"))


def _event_priorities() -> set[str]:
    from .vocab import registry
    return set(registry("events").get("priority") or {})


EVENT_KINDS = _event_kinds()
EVENT_PRIORITIES = _event_priorities()

# A daily check has three outcomes, and the third is the point: NOT-DONE IS
# NOT PASS. An athlete who never ran the hop test is not cleared by silence,
# and a coach should be able to say "you have not done the check today"
# rather than assuming either outcome. Absence of a record reads as not_done
# too - the explicit value exists so "I skipped it" can be stated rather than
# inferred from a gap.
CHECK_RESULTS = {"pass", "fail", "not_done"}
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
    "medical": {"expects": 2, "onset_date": 2, "precondition": 2,
                "restriction": 3},
    "achievements": {"occurred_date": 2},
    # G86/G31. The first time `goals` has moved off the founding generation,
    # so this is the G25 case the whole mechanism exists for: a gen-1 goal
    # line written before any of these fields existed must keep validating and
    # must resolve to exactly the same state it did before.
    "goals": {"event": 2, "deadline_kind": 2, "verification": 2,
              "change_kind": 2},
}

# The mirror of KEY_GENERATION: the generation at which a key stopped being
# required. A retired key stays LEGAL forever (an old line that carries it is
# not wrong, and must keep validating), but a line written at or after the
# retirement generation is not expected to carry it. Without this, replacing
# `hip_pain` with `pain` would force every new line to keep writing the field
# it replaced - a schema that can only ever grow.
# G89: RETIRING A KEY IS A THREE-PART CHANGE. Listing it here is part one and
# it is the easy part. Part two is that forward mapping happens in exactly ONE
# canonicaliser, not re-implemented at each reader. Part three is that every
# lookup, filter, dispatch key and comparison naming the old key tries the
# SUCCESSOR FIRST, with the old name as fallback.
#
# Part three is the one that gets missed, and it fails silently: the pain
# verdict resolved its goal by exact match on `hip_pain`, so an athlete who
# had only ever written `pain` got the right number with no goal attached,
# which renders identically to having declared no goal. The legacy path is
# always the one under test, because retirement exists to keep it working.
# Grep the retired name across the whole tree before calling this done.
KEY_RETIREMENT: dict[str, dict[str, int]] = {
    "daily": {"hip_pain": 2},
    "sessions": {"location": 2},
}

CURRENT_GENERATION: dict[str, int] = {name: 1 for name in KEYS}
for _ds in ("weight", "daily", "sessions", "inferences", "medical",
            "achievements", "goals"):
    CURRENT_GENERATION[_ds] = 2
# Generation 3 adds the post-coordinated `restriction` spec to medical.
CURRENT_GENERATION["medical"] = 3

# --- transaction time (#37) ---------------------------------------------------
# `recorded_at` lands on EVERY dataset at once - the largest schema move so
# far - so its generation is registered as "one past whatever each dataset was
# already at", which is precisely what an additive field on all of them means.
#
# Derived rather than transcribed on purpose: thirteen hand-written generation
# numbers is thirteen chances to typo one, and a wrong generation here does
# not fail loudly - it silently starts REQUIRING a field on lines that predate
# it, which is the exact G25 time bomb the mechanism exists to defuse.
for _ds, _gen in list(CURRENT_GENERATION.items()):
    KEY_GENERATION.setdefault(_ds, {})["recorded_at"] = _gen + 1
    CURRENT_GENERATION[_ds] = _gen + 1
# Observation time on weight rides the same generation as the field above.
KEY_GENERATION["weight"]["measured_at"] = CURRENT_GENERATION["weight"]

# The track pointer and the external identity beside it (#43).
CURRENT_GENERATION["sessions"] += 1
for _k in ("track", "activity_id", "activity_source"):
    KEY_GENERATION["sessions"][_k] = CURRENT_GENERATION["sessions"]

# --- provenance as a chain (#35/#51) -------------------------------------------
# `origin` is what observed reality and `path` is the ordered hops it
# travelled; the existing `source` remains the TERMINUS, how it entered this
# record. `source` was being asked to answer all three, which is how
# `fitbit-api+mfp-export` came to read as two sources agreeing when
# MyFitnessPal had received those weights from Fitbit.
#
# Registered AFTER the block above, so `sessions` lands one generation past
# the track fields rather than sharing theirs.
for _ds in ("weight", "daily", "sessions", "measurements"):
    CURRENT_GENERATION[_ds] += 1
    for _k in ("origin", "path", "origin_evidence"):
        KEY_GENERATION.setdefault(_ds, {})[_k] = CURRENT_GENERATION[_ds]

# --- how a value was acquired (#77/#78) ---------------------------------------
# `capture` is a property of the ACQUISITION EVENT rather than of the chain: a
# photo-read and a BLE-read of one console on one evening are two claims with
# one origin and two captures.
#
# `sessions` gains `origin`/`path`/`origin_evidence` as COLUMNS here: #51
# registered their generations for sessions but never added them to `KEYS`,
# and sessions is exactly where multi-instrument claims collide.
#
# Critically, sessions ADVANCES to a new generation rather than reusing the
# one #51 already consumed. It was already at that generation, so a row an
# existing deployment had appended and stamped with it would suddenly owe
# five keys it cannot have - the exact G25 time bomb the mechanism exists to
# defuse, arriving through a restructuring rather than a new field.
for _ds in ("weight", "daily", "sessions", "measurements"):
    CURRENT_GENERATION[_ds] += 1
    _new = ["capture", "read_by"]
    if _ds == "sessions":
        _new += ["origin", "path", "origin_evidence"]
    for _k in _new:
        KEY_GENERATION[_ds][_k] = CURRENT_GENERATION[_ds]
# --- was it measured at all? (#49, #88) ---------------------------------------
# Its OWN generation on top of #78's above, for the reason #78 was filed:
# that generation has now shipped, so a row an existing deployment stamped
# with it must not suddenly owe keys it cannot have.
# `modelled` names the fields on a row that are model outputs; `type_source`
# says how a categorical label was assigned. Both answer "was this observed",
# which origin and capture do not.
for _ds in ("weight", "daily", "sessions", "measurements"):
    CURRENT_GENERATION[_ds] += 1
    _new = ["modelled"] + (["type_source"] if _ds == "sessions" else [])
    for _k in _new:
        KEY_GENERATION[_ds][_k] = CURRENT_GENERATION[_ds]

# --- the artifact reference (#80) ---------------------------------------------
# LAST, because it is the newest change. Order matters here in a way that is
# easy to get wrong on a merge: placed above #49/#88's block instead, this
# takes the generation those fields already shipped under, and every demo and
# deployed row stamped with it suddenly owes an `artifact` key it cannot have.
# The rule is simply that a block appends - a new field never lands ahead of
# one already in the wild.
for _ds in ("weight", "daily", "sessions", "measurements"):
    CURRENT_GENERATION[_ds] += 1
    KEY_GENERATION[_ds]["artifact"] = CURRENT_GENERATION[_ds]


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
    "max_hr": (int,), "cadence": (int,), "kcal": _NUMERIC,
    "rpe": _NUMERIC,
    "confidence": _NUMERIC,
    # #96. Without these a quoted number - the ordinary hand-edit typo -
    # validates clean and then reads as null, so the biggest item on the
    # plate silently drops out of the total instead of being rejected.
    "grams": _NUMERIC, "grams_lo": _NUMERIC, "grams_hi": _NUMERIC,
    "kcal_100g": _NUMERIC, "protein_100g": _NUMERIC,
    "fat_100g": _NUMERIC, "carb_100g": _NUMERIC,
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


def _bad_hhmm(v: object) -> bool:
    """A local wall-clock time, HH:MM, 24-hour.

    Deliberately NOT `start_time`'s full offset-bearing timestamp, though both
    are observation time. A session has a duration and can cross a timezone,
    so it needs the offset to be comparable across platforms; a weigh-in is a
    point on a day the row already names, and the useful question about it is
    only ever "morning or evening". HH:MM is also what an athlete can answer
    from memory - "I weigh at seven" - and a format nobody can fill in
    accurately is a field that stays null.
    """
    if not isinstance(v, str):
        return True
    try:
        datetime.strptime(v, "%H:%M")
        return False
    except ValueError:
        return True


def _bad_time(v: object) -> bool:
    """An ISO-8601 timestamp. Offset-bearing is CANONICAL; naive is legacy.

    Both parse and both are accepted, and the distinction is stated here
    because the schema being silent about it is what made this dangerous: the
    validator's own example showed an offset while the record held naive rows
    from the Polar connector, and comparing the two shapes used to take the
    build down (#38). A writer following the documentation broke the engine.

    Comparison is now frame-aligned (`clocks.align`), so a mixed record
    builds. Naive stays LEGAL - an existing line is history, not an error, and
    offsets cannot be backfilled row by row anyway - but `vitai validate`
    reports naive timestamps as an advisory so a migration has something to
    work from. Offset-bearing is what new writes should carry: an offset is
    what makes an instant comparable across a timezone change, and naive local
    time is genuinely ambiguous during the autumn DST fold, when 02:30 happens
    twice and nothing in the value says which.
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
    problems += _validate_recorded_at(rec)
    for k, types in _TYPES.items():
        if k in keys and (v := rec.get(k)) is not None and k in rec:
            if isinstance(v, bool) or not isinstance(v, types):
                problems.append(f"'{k}' should be a number or null, got {v!r}")
    if dataset == "weight" and rec.get("measured_at") is not None and (
            _bad_hhmm(rec.get("measured_at"))):
        problems.append(f"bad measured_at {rec.get('measured_at')!r} - HH:MM "
                        "local, the same shape as sessions.start_time")
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
    if dataset in ("weight", "daily", "sessions", "measurements", "sets", "meals"):
        problems += provenance_problems(rec)
        problems += capture_problems(rec)
        problems += value_kind_problems(rec, KEYS[dataset])
        if (ref := rec.get("artifact")) is not None and not is_reference(ref):
            problems.append(
                f"'artifact' is a content address like "
                f"'sha256:<64 hex>', got {ref!r} - a filename would drift "
                "from the row that cites it, which is why this is a hash")
    if dataset == "sets":
        problems += set_problems(rec)
    if dataset == "meals":
        problems += meal_problems(rec)
    if dataset == "sessions":
        problems += _validate_track(rec)
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
    if (od := rec.get("onset_date")) is not None and _bad_date(od):
        problems.append(f"bad onset_date {od!r} (ISO-8601 YYYY-MM-DD)")
    if (rd := rec.get("resolved_date")) is not None:
        # Compared against ONSET, not the entry date. Recording a 2025 injury
        # today is ordinary backfill, and the old rule rejected it outright.
        began = onset_of(rec)
        if _bad_date(rd):
            problems.append(f"bad resolved_date {rd!r} (ISO-8601 YYYY-MM-DD)")
        elif isinstance(began, str) and not _bad_date(began) and rd < began:
            problems.append(f"resolved_date {rd} precedes onset {began}")
    # A resolved episode without a closing date leaves the window open forever,
    # which quietly breaks forgiveness maths downstream (a day is excused iff it
    # falls inside an episode window).
    if rec.get("status") == "resolved" and not rec.get("resolved_date"):
        problems.append("a resolved episode needs a 'resolved_date' "
                        "(it closes the episode window)")
    if rec.get("status") != "resolved" and rec.get("resolved_date"):
        problems.append("'resolved_date' set but status is not 'resolved'")

    from .vocab import restriction_problems
    for cls in _restriction_classes(rec):
        if cls not in ACTIVITY_CLASSES:
            problems.append(f"unknown activity class {cls!r} in 'restricts' - "
                            f"use one of {sorted(ACTIVITY_CLASSES)}")
    # The post-coordinated form (G85). `restricts` stays the coarse projection
    # a consumer already reads; `restriction` says what the clinician actually
    # said, on separate axes, so "no loaded hip work" can leave squats alone.
    problems += restriction_problems(rec.get("restriction"))
    for token in _tokens(rec.get("expects")):
        if token not in EXPECTATIONS:
            problems.append(f"unknown expectation {token!r} in 'expects' - "
                            f"use one of {sorted(EXPECTATIONS)}")
    if (pre := rec.get("precondition")) is not None:
        if not isinstance(pre, str) or not pre:
            problems.append("'precondition' names a daily check, e.g. 'hop-test'")
        elif not rec.get("restricts"):
            problems.append("'precondition' without 'restricts' gates nothing - "
                            "a check that lifts no restriction is just a note")
    return problems


def onset_of(rec: dict) -> object:
    """When the episode BEGAN, falling back to when it was written.

    The two are different questions and the record needs both: `date` answers
    "when did we learn this" (which is what P2's as-of reconstruction reads),
    `onset_date` answers "when did it start" (which is what the episode window
    and any forgiveness maths read).
    """
    return rec.get("onset_date") or rec.get("date")


def occurred_of(rec: dict) -> object:
    """When an achievement HAPPENED, falling back to when it was written."""
    return rec.get("occurred_date") or rec.get("date")


def _tokens(raw: object) -> list[str]:
    """Comma- or space-separated slugs from a multi-value text field."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [p.strip() for p in str(raw).replace(",", " ").split() if p.strip()]


def _restriction_classes(rec: dict) -> list[str]:
    """Activity classes named by a `restricts` field (comma or space separated)."""
    return _tokens(rec.get("restricts"))


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


def _validate_track(rec: dict) -> list[str]:
    """The track pointer and the external identity it sits beside (#43)."""
    problems: list[str] = []
    track = rec.get("track")
    if track is not None:
        if not isinstance(track, str) or not track.strip():
            problems.append("'track' is a repo-relative path to the stored "
                            "track file, or null")
        else:
            # An absolute path leaks a username and a machine layout into a
            # record meant to be portable, and it breaks a rebuild anywhere
            # else - a determinism violation, not merely untidy.
            first = track.replace("\\", "/").split("/")[0]
            slashed = track.replace("\\", "/")
            if (slashed.startswith("/") or track.startswith("~")
                    or slashed.startswith("//")          # UNC \\server\share
                    or (len(first) == 2 and first[1] == ":")):
                problems.append(
                    f"'track' must be repo-relative, got {track!r} - an "
                    "absolute path leaks a machine layout and cannot be "
                    "rebuilt anywhere else")
            if ".." in track.replace("\\", "/").split("/"):
                problems.append(f"'track' must stay inside the repo, got {track!r}")
    for key in ("activity_id", "activity_source"):
        if (v := rec.get(key)) is not None and (
                not isinstance(v, str) or not v.strip()):
            # Never coerced to a number: leading zeros and non-numeric ids
            # both exist in the wild, and a platform's id is an opaque token.
            problems.append(f"'{key}' is an opaque string, or null (got {v!r})")
    if rec.get("activity_source") is not None and rec.get("activity_id") is None:
        problems.append("'activity_source' names who assigned 'activity_id', "
                        "so it needs one")
    return problems


def _validate_recorded_at(rec: dict) -> list[str]:
    """Transaction time must be ISO 8601 and carry an explicit offset (#37).

    SHAPE only, deliberately. The three properties this clock needs are
    enforced at the three layers that can actually see them:

    - shape, here, per line;
    - MONOTONICITY, per file, in `vitai validate` - which is the durable
      integrity check, because a hand-edited or forged stamp almost always
      lands out of order and no per-line rule could ever notice;
    - machine ownership, at the append boundary, where a caller-supplied
      value can be refused outright.

    Not checked here: "is it in the future". Tempting, and wrong - every
    fixture and the whole demo are deliberately dated 2030 so a synthetic
    record can never be mistaken for a real one, and a wall-clock comparison
    would reject the repo's own test corpus while catching nothing that
    monotonicity does not.
    """
    stamp = rec.get("recorded_at")
    if stamp is None:
        return []
    if not is_stamp(stamp):
        return [f"bad recorded_at {stamp!r} - ISO 8601 with an explicit UTC "
                "offset (e.g. 2026-07-31T14:32:05+02:00), machine-set on "
                "append and never authored"]
    return []


def timestamp_advisories(dataset: str, rows: list[tuple[int, dict]]) -> list[str]:
    """Naive `start_time` values: legal, but not what new writes should carry.

    An ADVISORY rather than a problem, deliberately. These rows are already on
    disk and are not wrong - and making them an error would make the record
    unbuildable from the first converted row until the last, which is the very
    thing that blocks the migration it would be demanding (#38).

    Reported only where both shapes coexist in one dataset. A record that is
    uniformly naive is internally consistent and has nothing to act on yet;
    it is the mixture that costs something, because every comparison across it
    rests on an assumed offset.
    """
    if dataset != "sessions":
        return []
    naive = [n for n, r in rows
             if r.get("start_time") and not is_aware(parse_time(r["start_time"]))]
    aware = [n for n, r in rows
             if r.get("start_time") and is_aware(parse_time(r["start_time"]))]
    if not naive or not aware:
        return []
    return [f"{dataset}.jsonl: {len(naive)} start_time value(s) are naive and "
            f"{len(aware)} carry an offset (first naive: line {naive[0]}). "
            "Both are legal and the build handles the mixture, but every "
            "comparison between the two shapes rests on an assumed offset. "
            "Offset-bearing is canonical - naive local time cannot say which "
            "02:30 it means on the night the clocks go back"]


def unranked_source_problems(dataset: str, rows: list[tuple[int, dict]],
                             known: set[str]) -> list[str]:
    """Source terms the precedence ladder has never heard of (#73).

    An unranked term sorts LAST, below every configured source, and nothing
    says so. That is almost always a typo or a term missing from config
    rather than a deliberate demotion to worst-in-the-record - and it cost a
    real day: `context.jsonl` wrote `source: "stated-in-chat"`, the daily
    ladder had never heard of it, and a 20,336-step day resolved its energy
    burn to a vendor's figure over the athlete's own. That day flipped from a
    reported surplus to a deficit.

    Cheap and deterministic: it needs only the data and the config, and it
    catches the mistake at the door rather than after a rebuild.
    """
    if not known or dataset not in RESOLVED_BY_SOURCE:
        return []
    seen: dict[str, int] = {}
    for n, r in rows:
        if (src := r.get("source")) and str(src) not in known:
            seen.setdefault(str(src), n)
    return [f"{dataset}.jsonl line {n}: source {src!r} is not in the "
            "precedence ladder, so every value on this line sorts below every "
            "configured source. Add it to [resolution] source_order - putting "
            "it LAST is how you say 'trust this least' deliberately - or fix "
            "the spelling"
            for src, n in sorted(seen.items())]


# Datasets whose rows compete by source. Policy datasets carry a `source` too,
# but it records authorship rather than entering a precedence contest.
RESOLVED_BY_SOURCE = ("weight", "daily", "sessions", "measurements")
def impossible_claim_problems(dataset: str,
                              rows: list[tuple[int, dict]]) -> list[str]:
    """Values an instrument physically cannot have observed (#79).

    Not a resolution tie - a tie is two instruments disagreeing, and this is
    one instrument claiming something it has no sensor for. A scale reporting
    distance is not a contest to adjudicate, it is a row that cannot be true
    as written, and `source` being free text meant nothing knew a scale from
    a watch.

    A DENY list held at the KIND level, so a registry gap produces silence
    rather than a finding against the record - the direction that costs
    nothing when it is wrong.
    """
    from .provenance import denied_fields, impossible_claims, resolve_source
    checkable = [f for f in KEYS[dataset] if f in denied_fields()]
    if not checkable:
        return []
    out: list[str] = []
    for n, r in rows:
        if bad := impossible_claims(r, checkable):
            out.append(
                f"{dataset}.jsonl line {n}: source {r.get('source')!r} "
                f"({resolve_source(r.get('source'))}) cannot observe "
                f"{', '.join(bad)} - either the source is wrong or the value "
                "came from somewhere else")
    return out


def supersedes_problems(dataset: str, rows: list[tuple[int, dict]]) -> list[str]:
    """A correction that cannot say WHICH line it corrects (#43).

    `supersedes` retires every line matching its reference, and for a dataset
    with no per-row identity that can be more than one: two runs on a day from
    one watch share `<date>/<source>`, so correcting either silently deletes
    both. That is the same harm as a false merge - two activities becoming
    one - arriving through the correction path.

    Reported rather than resolved, because the engine cannot know which was
    meant. The fix is to give the rows an identity (`activity_id` on
    sessions), and this says so.
    """
    from .jsonl import line_key
    problems: list[str] = []
    by_key: dict[str, list[int]] = {}
    for n, r in rows:
        by_key.setdefault(line_key(dataset, r), []).append(n)
    superseding = {n for n, r in rows if r.get("supersedes")}
    for n, r in rows:
        if not (ref := r.get("supersedes")):
            continue
        # Rows that are themselves corrections are excluded from the count. A
        # CHAIN (A superseded by B, B superseded by C) legitimately shares one
        # reference and retires all of it - that is documented behaviour, not
        # ambiguity. What this catches is two rows that were never the same
        # thing answering to one key, which is the case that loses data.
        hit = [m for m in by_key.get(str(ref), [])
               if m != n and m not in superseding]
        if len(hit) > 1:
            problems.append(
                f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches "
                f"{len(hit)} lines ({', '.join(map(str, hit))}) - a correction "
                "that cannot say which line it corrects would retire all of "
                "them. Give these rows an identity (activity_id) first")
        elif not hit:
            problems.append(
                f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches no "
                "line - nothing is being corrected, and the reference is "
                "probably mistyped")
    return problems


def recorded_at_problems(dataset: str, rows: list[tuple[int, dict]]) -> list[str]:
    """File-level checks on transaction time: monotonic, and no exact ties.

    Monotonicity is what makes `recorded_at` an ordering rather than a
    decoration. It is a property of the FILE, not of any line, so it cannot
    live in `validate_record` - and it is the check that actually catches a
    hand-authored stamp, since a human writing a plausible-looking value will
    almost never land it in the right place in the sequence.

    Any REPEATED stamp is reported, not only one shared by two rows on the same
    date. That narrower check is what let the real defect hide: a bulk import
    of 227 readings on 227 different dates stamped every row identically, and
    `validate` said the file was fine, because no two ties shared a date (#44).
    A serial appender cannot write two rows at one instant - a repeat means
    the clock is not doing its job, whatever the rows are dated.

    Comparison is by INSTANT rather than by text throughout: two stamps
    written either side of a timezone change are ordered by when they happened,
    not by how their offsets happen to sort as strings.

    Unstamped rows never tie - they legitimately share the "absent" key, which
    is what keeps the migration a read no-op.
    """
    problems: list[str] = []
    stamped = [(n, r, i) for n, r in rows
               if (i := stamp_instant(r.get("recorded_at"))) is not None]
    for (pn, prev, pi), (n, _cur, ci) in zip(stamped, stamped[1:]):
        if ci < pi:
            problems.append(
                f"{dataset}.jsonl line {n}: recorded_at "
                f"{_cur['recorded_at']!r} precedes line {pn}'s "
                f"{prev['recorded_at']!r} - transaction time is monotonic by "
                "construction, so an out-of-order stamp means the line was "
                "hand-written or the clock moved")
    seen: dict[datetime, int] = {}
    for n, r, i in stamped:
        if (first := seen.get(i)) is not None:
            problems.append(
                f"{dataset}.jsonl line {n}: recorded_at {r['recorded_at']!r} "
                f"is the same instant as line {first} - two rows cannot have "
                "been written at once, and a repeated stamp orders nothing, "
                "which is the only thing this field is for")
        seen.setdefault(i, n)
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
        problems += _enum(rec, "verification", VERIFICATIONS, optional=True)
        problems += _enum(rec, "deadline_kind", DEADLINE_KINDS, optional=True)
        problems += _enum(rec, "change_kind", CHANGE_KINDS, optional=True)
        how = verification_of(rec)
        # An ATTESTED goal is the one case where a metric is not merely absent
        # but wrong to have. "I want to enjoy running again" is settled by the
        # athlete saying so and by nothing else, so a metric on it would be a
        # promise the engine cannot keep - it would start issuing verdicts on
        # a proxy nobody agreed was the goal (G86/G83).
        if how == ATTESTED:
            for k in ("metric", "target", "dataset", "session_type", "period"):
                if rec.get(k) not in (None, "", "none"):
                    problems.append(
                        f"an attested goal is settled by the athlete's word alone, "
                        f"so it takes no {k!r} (got {rec.get(k)!r})")
        elif how == MEASURED and (not isinstance(rec.get("metric"), str)
                                  or not rec.get("metric")):
            # Only a MEASURED goal owes a metric. An external one is named by
            # its `tracker`, and an attested one has no measure at all.
            problems.append("'metric' must be a non-empty string "
                            f"(a dataset column or {EXTERNAL_METRIC!r}), or set "
                            f"'verification' to {ATTESTED!r} for a goal nothing "
                            "can ever measure")
        # The two ways of saying "another app owns this" must not disagree.
        if rec.get("verification") == EXTERNAL and rec.get("metric") not in (
                None, "", EXTERNAL_METRIC):
            problems.append(f"an external goal's 'metric' is {EXTERNAL_METRIC!r} "
                            f"or null, got {rec.get('metric')!r}")
        # A correction says the retired line was never valid policy. Unexplained,
        # it is indistinguishable from a quiet retreat wearing the right label -
        # which is the one way this field could be used to launder churn.
        if rec.get("change_kind") == "correction" and not rec.get("reason"):
            problems.append("a 'correction' needs a 'reason' - it asserts the "
                            "previous line never reflected a real intention, and "
                            "unexplained it cannot be told from a quiet retreat")
        # Hardness with nothing to be hard about is a field with no referent.
        if rec.get("deadline_kind") is not None and not (
                rec.get("deadline") or rec.get("event")):
            problems.append("'deadline_kind' needs a 'deadline' or an 'event' "
                            "to qualify")
        if (ev := rec.get("event")) is not None and (
                not isinstance(ev, str) or not ev):
            problems.append("'event' names an events.jsonl slug")
        # G86/G85: `dataset` used to scope only to daily|sessions, so a WEIGHT
        # goal - the most common goal in the domain - had nowhere to point.
        if (ds := rec.get("dataset")) is not None and ds not in GOAL_DATASETS:
            problems.append(f"'dataset' scopes to one of {sorted(GOAL_DATASETS)}, "
                            f"got {ds!r}")
        if (st := rec.get("session_type")) is not None and st not in SESSION_TYPES:
            problems.append(f"'session_type' must be one of {sorted(SESSION_TYPES)}, "
                            f"got {st!r}")
        # An external goal is tracked elsewhere, so it needs a pointer and
        # cannot carry an engine target; an internal goal needs a target to
        # verdict against. Guard percentage only means something when guarded.
        if how == EXTERNAL:
            if not isinstance(rec.get("tracker"), str) or not rec.get("tracker"):
                problems.append("an external goal needs 'tracker' (where it lives)")
        elif (how != ATTESTED and rec.get("target") is None
                and rec.get("status") == "active"):
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
        if (od := rec.get("occurred_date")) is not None and _bad_date(od):
            problems.append(f"bad occurred_date {od!r} (ISO-8601 YYYY-MM-DD)")
    if dataset == "artifacts":
        if not is_reference(rec.get("sha256")):
            problems.append(f"'sha256' is a content address like "
                            f"'sha256:<64 hex>', got {rec.get('sha256')!r}")
        if (n := rec.get("bytes")) is not None and (
                not isinstance(n, int) or isinstance(n, bool) or n < 0):
            problems.append(f"'bytes' is a non-negative integer, got {n!r}")
        if (rm := rec.get("removed")) is not None and not isinstance(rm, bool):
            problems.append(f"'removed' should be true/false/null, got {rm!r}")
        if rec.get("removed") and not rec.get("reason"):
            problems.append("a removal needs a 'reason' - deleting evidence is "
                            "a decision worth recording, and it is what "
                            "distinguishes it from data loss")
    if dataset == "checks":
        if not isinstance(rec.get("slug"), str) or not rec.get("slug"):
            problems.append("'slug' must name the check, e.g. 'hop-test'")
        problems += _enum(rec, "result", CHECK_RESULTS)
        problems += _enum(rec, "source", AUTHORS, optional=True)
    if dataset == "events":
        for k in ("slug", "title"):
            if not isinstance(rec.get(k), str) or not rec.get(k):
                problems.append(f"'{k}' must be a non-empty string")
        problems += _enum(rec, "kind", EVENT_KINDS)
        problems += _enum(rec, "priority", EVENT_PRIORITIES, optional=True)
        problems += _enum(rec, "status", EVENT_STATUSES, optional=True)
        problems += _enum(rec, "set_by", AUTHORS, optional=True)
        # The whole point of the dataset: a fixture without a date is not a
        # fixture, and it is what everything else here is planned backwards from.
        if _bad_date(rec.get("event_date")):
            problems.append(f"bad event_date {rec.get('event_date')!r} - an event "
                            "needs the day it actually falls on (ISO-8601)")
        if (im := rec.get("immovable")) is not None and not isinstance(im, bool):
            problems.append(f"'immovable' should be true/false/null, got {im!r}")
    return problems


def verification_of(goal: dict) -> str:
    """Who can ever settle this goal - `measured`, `external` or `attested`.

    Read through a helper rather than off the field because `external` was
    expressed as a sentinel METRIC value (`metric: "external"`) before this
    field existed. Both spellings stay legal - an old line is history, not an
    error - and everything downstream asks this question instead of matching
    on the sentinel, which is how `report.py`'s `startswith("gym")` coupling
    happened one increment ago.
    """
    if (declared := goal.get("verification")) in VERIFICATIONS:
        return str(declared)
    if goal.get("metric") == EXTERNAL_METRIC:
        return EXTERNAL
    return MEASURED
