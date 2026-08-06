"""Health-domain dataset schemas.

Conventions: ISO-8601 dates; units in the key name (kg, _km, _s, _g, _h);
null for unknown, never omit a key; one object per line.

`validate_record` is deliberately practical rather than exhaustive: it exists
so an LLM (or a tired human) appending lines gets caught on the mistakes that
actually corrupt a record - missing keys, bad dates, wrong types, unknown
session types - not to enforce ceremony.
"""

from __future__ import annotations

import re

from datetime import date, datetime

from .clocks import (is_aware, is_stamp, order_key,  # noqa: F401
                     parse_time, stamp_instant)
from .artifacts import is_reference
from .provenance import capture_problems
from .modifiers import problems as modifier_problems
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
               "capture", "read_by", "modelled", "artifact", "device"],
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
              "origin_evidence", "capture", "read_by", "modelled", "artifact", "device"],
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
                 "modelled", "type_source", "artifact", "device"],
    # Third data tier: MODEL-INFERRED knowledge. Append-only like everything
    # else, but carries provenance (model, evidence, confidence) because it is
    # neither ground truth (observed) nor rebuildable (derived). The engine
    # projects it; it never feeds the deterministic number path.
    # `depends_on` (gen 2) is the JTMS justification link: the claim ids this
    # inference rests on. Retracting one of those claims retracts the
    # inference with it, rather than leaving a stale belief behind whose
    # evidence quietly no longer exists.
    "inferences": ["date", "kind", "statement", "confidence", "model",
                   "evidence", "note", "depends_on", "recorded_at", "device"],
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
              "note", "event", "deadline_kind", "verification",
              "change_kind", "recorded_at", "device"],
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
               "immovable", "place", "status", "set_by", "reason", "note", "recorded_at", "device"],
    # G14/G20: every threshold is effective-dated, so editing one today can
    # never silently re-score a past week. `change_kind` separates a genuine
    # policy CHANGE from a CORRECTION of a mis-entered number (G31) - only the
    # former is churn, and only the former can be suspiciously timed.
    "thresholds": ["date", "key", "value", "change_kind", "set_by", "reason",
                   "note", "recorded_at", "device"],
    # A recorded accomplishment worth keeping. Distinct from a MILESTONE, which
    # the engine derives; `source` carries authorship (G31) so a hand-logged
    # race finish is never confused with an engine-derived crossing.
    # `occurred_date` is the same event-versus-entry split as `medical`'s
    # `onset_date`: a race finished in March and written up in July belongs on
    # the day it happened. Named differently on purpose - an achievement is a
    # point event that OCCURRED, an episode has an ONSET that opens a window.
    "achievements": ["date", "title", "goal", "source", "note", "occurred_date",
                     "recorded_at", "device"],
    # --- increment 2 -------------------------------------------------------
    # Sparse ANCHOR-class reads that do not come off the scale: a tape measure,
    # a DEXA scan, an InBody. Anchors top the resolution precedence ladder and,
    # like weight, are read as TENDENCIES over a sparse trend - never as a
    # single point. `body_fat_pct` measured BY the scale already rides the
    # `weight` line (gen-2, G36/G37); this dataset is for the other instruments.
    "measurements": ["date", "kind", "value", "source", "note", "recorded_at",
                     "origin", "path", "origin_evidence", "capture",
                     "read_by", "modelled", "artifact", "device"],
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
             "capture", "read_by",
             # A generation of their own (#99): how the set was CONFIGURED.
             # The NUMBER is deliberately not written here - `recorded_at`
             # already consumed one for `sets`, so a comment naming a
             # generation goes stale the moment anything else lands, and an
             # external writer transcribing it would stamp rows that owe keys
             # they cannot have. `key_generation("sets", "equipment")` is the
             # answer. Flat nullable
             # columns rather than a nested `modifiers` blob - the repo's
             # shape is one flat object per line, `KEY_GENERATION` exists so
             # a later increment can add nullable columns without
             # invalidating a single existing line, and the read model gets
             # queryable columns for free.
             #
             # `resistance_level`, `seat_pos`, `pad_pos` and `lever_pos` are
             # MACHINE-SCOPED: ordinals on one manufacturer's scale, which
             # require `machine` and may never be compared across machines.
             # `angle_deg` is portable, which is why it carries its unit.
             "equipment", "angle_class", "angle_deg",
             "resistance_level", "seat_pos", "pad_pos", "lever_pos", "device"],
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
              "origin", "path", "origin_evidence", "capture", "read_by", "device"],
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
                "restriction", "recorded_at", "device"],
    # The result of a named check, on a day (G28 gate mechanics). A rehab plan
    # says "5 gentle hops before each run; pain in the hip means do not run
    # today" - a gate CONDITIONAL on a test performed that morning. Without
    # this the whole instruction sits in a note where no rule can read it,
    # which is the prose problem G28 exists to solve, one level down.
    "checks": ["date", "slug", "result", "value", "source", "note", "recorded_at", "device"],
    # Dated situational mode (G34): what was going on around the athlete. The
    # engine uses it to explain missingness rather than flag it - an absent
    # weigh-in in a week with no scale is not a lapse - and the coach uses it
    # to constrain what it asks for. Effective-dated like all policy (P2).
    "context": ["date", "mode", "facilities", "place", "source", "note", "recorded_at", "device"],
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
                  "recorded_at", "device"],
    "journal": ["date", "kind", "text", "about", "source", "confidence",
                "status", "note", "recorded_at", "device"],
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

# One value for now, and closed on purpose: a regime says a span of claims was
# unanchored. Widening it is a claim about a NEW way a record can be wrong,
# which should be argued rather than typed.
REGIME_KINDS = {"unanchored"}

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
# WHICH DIRECTION COUNTS AS PROGRESS (#200). Orthogonal to `policy`, which says
# whether progress may run backwards, and to the teleology axis, which says
# what KIND of thing a goal is. Three separate questions; they do not share a
# field.
#
# Both policies mean "more counts", so before this a cap was scored as an
# accumulation and exceeding it read as excelling: a 1200 kcal limit held at
# 1100 for a week reported 641.7% and minted four celebratory milestones.
#
#   floor     at or above the value; below is the miss
#   ceiling   at or below; above is the miss
#   band      between two values; either side is a miss, and they differ
#   approach  converge on a value from wherever you start; the sign is not
#             the measure, the distance is
GOAL_POLARITIES = {"floor", "ceiling", "band", "approach"}

# ABSENT IS A FLOOR, and that is a migration statement rather than a taste.
# Both existing policies already mean "more counts", so reading an unstated
# polarity as a floor scores every existing row exactly as it scores today.
# Nothing re-scores, and no row has to be edited to keep the answer it had.
DEFAULT_POLARITY = "floor"


def polarity_of(goal: dict) -> str:
    """The declared polarity, or the one absence means."""
    return str(goal.get("polarity") or DEFAULT_POLARITY)
# `proposed` is a GRAIN of a goal: mentioned, not committed. Without it a
# half-formed intention has nowhere to live except prose, and the coach
# cannot tell an aspiration from a decision - which matters, because
# treating a musing as a commitment is how an athlete ends up held to
# something they never actually chose.
# RETIRED at the generation below in favour of the two vocabularies that
# follow (#235). Kept, and kept validating, because every goal line written
# before the split carries it and an old line is not wrong (G25).
GOAL_STATUSES = {"proposed", "active", "paused", "achieved", "abandoned"}

# TWO AXES, because the old list mixed them and that mixture is #199's
# two-scoring-systems bug at the vocabulary level. `achieved` was an
# achievement value living in a lifecycle list: `goals` held the lifecycle
# axis, `verdicts` held the achievement axis, they were built by different
# code, and the shipped demo had them disagreeing about steps. One object with
# two columns rather than two subsystems. FHIR split these in 2014 and the
# names below follow it, which is also where three values we were about to
# invent separately already live.
#
# WHERE THE GOAL IS IN ITS OWN LIFE. Declared by the athlete: a goal becomes
# active because he says so, and never because the arithmetic moved.
LIFECYCLE_STATUSES = {"proposed", "planned", "accepted", "active", "on_hold",
                      "completed", "cancelled", "rejected"}

# HOW IT IS GOING AGAINST ITS TARGET. Derived, never authored: a goals line is
# a declaration, so this lands on the progress row rather than in the record.
#
# A SHORTER LIST THAN FHIR'S, and deliberately: every value here has something
# that emits it. `improving` and `worsening` need a trend, and a progress row
# is a snapshot with no previous value to compare against; `no_change` is the
# approach-goal reading of standing still, which needs polarity (#200). Adding
# them now would put words in a closed vocabulary that nothing can produce,
# which is the specified-and-never-written class (#204) arriving in the
# vocabulary that was meant to fix a different one. They land with their
# producers.
# `not_attainable` is absent for the same reason: FHIR means "not possible to
# be met", which is the modal claim G58's declaration-time feasibility gate
# makes. A deadline that passed with the target unmet is `not_achieved` - "has
# not been met" - and calling it not-attainable would be using the word for
# the case it is not for.
ACHIEVEMENT_STATUSES = {"in_progress", "no_progress", "achieved",
                        "sustaining", "not_achieved"}

# Journal entry kinds. `claim` is the athlete asserting a fact about
# themselves (checkable against the record); `worry` is a concern worth
# surfacing later; `idea` is an unformed intention; `preference` shapes what
# the coach may propose; `question` is something they asked that deserves an
# answer when the data can give one.
JOURNAL_KINDS = {"claim", "worry", "idea", "preference", "question", "note"}
JOURNAL_STATUSES = {"open", "resolved", "superseded", "declined"}
# `daily` arrives with polarity (#200) rather than after it, because without
# it polarity gives a WRONG answer on the case that motivated it. A cap is
# almost always a per-day limit; with no daily bucket the score accumulates
# over the whole period, so seven compliant days at 1100 against a 1200 cap
# read as breaching it by 6500. The old defect said a breach was a triumph;
# scoring it that way would have said a compliant week was a breach, which is
# not an improvement, it is the same error facing the other way.
GOAL_PERIODS = {"none", "daily", "weekly", "monthly", "quarterly", "yearly"}
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

# WHAT HAPPENED WHEN THE DATE ARRIVED (#139), which `status` cannot say.
#
# A confirmed, immovable, priority-a race passed with no session row. Its
# status is still `confirmed` and will stay that way forever, so three
# genuinely different things read identically: a race that happened and
# produced no data, a race the athlete did not go to, and a race that never
# took place. The first is the COMMON one, because a race day is exactly when
# logging is least likely.
#
# A SECOND AXIS, not more values on the first - the same split #235 made for
# goals, where `status` mixed where a goal was in its life with how it was
# going. `status` is what the fixture IS (still tentative, confirmed, called
# off in advance); `outcome` is what became of it. A cancelled race is
# expressible today and stays that way; what had no home is a date that
# arrived.
#
# Semantics from FHIR `Appointment.status`, which draws exactly this line:
# `fulfilled` for one that took place and `noshow` for one the person did not
# attend. Our slugs are spelled for a reader of this record and `fhir` records
# the term they map to, the same way `semantics/statistics.toml` carries its
# IEEE terms - a mapping stated in a field can be checked, one implied by a
# slug cannot.
#
# ABSENT MEANS NOBODY HAS SAID, and that is the ordinary state of a future
# fixture. It must never be read as "did not happen": a consumer that renders
# an unanswered outcome as a miss accuses an athlete of skipping a race that
# has not happened yet.
EVENT_OUTCOMES = {"took_place", "did_not_attend"}
EVENT_OUTCOME_FHIR = {"took_place": "fulfilled", "did_not_attend": "noshow"}


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


# --- how a set was configured (#99) -------------------------------------------
# Its OWN generation, and additive: every column is nullable, so a line
# written before modifiers existed still validates untouched. The number is
# whatever `CURRENT_GENERATION` has reached - not a literal, because
# `recorded_at` already took one for this dataset and a hardcoded 2 would
# make wild rows owe seven keys.
# Appended last for the reason written beside the artifact block - a
# generation block appends, and a new field never lands ahead of one already
# in the wild.
CURRENT_GENERATION["sets"] += 1
for _k in ("equipment", "angle_class", "angle_deg", "resistance_level",
           "seat_pos", "pad_pos", "lever_pos"):
    KEY_GENERATION.setdefault("sets", {})[_k] = CURRENT_GENERATION["sets"]


# --- which machine wrote the line down (#105) ----------------------------------
# On EVERY dataset, like `recorded_at`, and for the same reason: it describes
# the write rather than the observation, so a caller must never have to
# remember it. Additive and nullable - a record written before multi-device
# support has no device, and "nobody said" is the correct reading.
#
# Beside `source`, never inside it: `source` says which INSTRUMENT observed
# the value, `device` says which MACHINE wrote the line down. Conflating them
# would make a phone and a laptop look like two instruments, which is the
# false-corroboration defect #35 exists to prevent.
#
# Appended last, per the rule beside the artifact block: a generation block
# appends, and a new field never lands ahead of one already in the wild.
for _ds in KEYS:
    CURRENT_GENERATION[_ds] = CURRENT_GENERATION.get(_ds, 1) + 1
    KEY_GENERATION.setdefault(_ds, {})["device"] = CURRENT_GENERATION[_ds]


# --- two new datasets (#171 track 2) -----------------------------------------
#
# DECLARED AFTER the generation blocks above, deliberately. Those loops append
# a generation to every dataset in `KEYS`, which is right for a field arriving
# into a dataset already in the wild and wrong for a dataset that has never
# existed: a new one has nothing in the wild, so every key of it is founding,
# and letting the loops reach it would have stamped `regimes` at generation 3
# with keys claiming to be later additions to a history it does not have.
KEYS["protocols"] = [
    # What a measurement's CONDITIONS were. A slug naming the procedure,
    # defined here in the athlete's own words. Optional and OPEN: a slug used
    # before it is defined is legal and validate advises, because a record
    # that refused an undefined slug would make writing one down cost more
    # than not bothering.
    "date", "slug", "text", "supersedes", "recorded_at", "device",
]
KEYS["regimes"] = [
    # An interval during which a whole class of claims was UNANCHORED: an
    # ill-defined measurand honestly restated, ending at a discoverable
    # instant. High trust, low accuracy, sustained, which is the empirical
    # proof that those two axes are separate.
    #
    # Distinct from a per-observation qualification (#168): that is one
    # suspect reading, this is a bounded span of them.
    "date", "from_date", "to_date", "dataset", "field", "kind", "source",
    "text", "anchored_by", "note", "recorded_at", "device", "supersedes",
]
KEYS["emissions"] = [
    # WHAT THE ENGINE TOLD THE ATHLETE, and when. Phase 3 of the uncertainty
    # proposal, 01-schema 8b.
    #
    # The asymmetry this closes: retracting an input empties the interval, but
    # the interval was CONSUMED - verdicts and warnings were computed from it
    # and acted on. Retraction propagated to the input and stopped, because
    # verdicts are rebuilt into the database and overwritten, so nothing could
    # answer "what did it tell me last week, and does that still hold".
    #
    # SURFACED ASSERTIONS ONLY, and the distinction is the whole design. A
    # computed verdict is rebuildable, and logging every one of them would
    # duplicate the derived tier into the ground-truth tier, make rebuild
    # non-idempotent, and grow without bound on every rebuild. "The engine
    # asserted X to the athlete on day T" is an EVENT IN THE WORLD: not
    # rebuildable, bounded by actual use, and the only kind that had a
    # consequence worth retracting. An unseen verdict was never acted on.
    #
    # Written at DELIVERY time by `api.assert_delivery`, never at build. Build
    # stays a pure function of the record.
    #
    # TWO DEVIATIONS FROM 01-schema 8b, recorded rather than silently taken.
    # The spec types `contract` as an integer; it is stored as the STRING the
    # rest of the engine uses, because `CONTRACT_VERSION` and `meta.contract`
    # are strings and a third spelling of one number is a conversion waiting
    # to be got wrong. And the spec's read-side derivations, `basis_retracted`
    # and `still_holds`, are NOT here: they are the next rung, and
    # `still_holds` is additionally blocked on #148 (replaying an assertion
    # needs the policy in force at its date, not today's). This dataset
    # records; checking what it recorded comes after.
    "date", "kind", "metric", "week", "statement", "basis_claims",
    "policy_asof", "contract", "surface", "recorded_at", "device",
]
KEYS["plans"] = [
    # WHAT A DAY WAS MEANT TO BE (#221). The state work can explain why
    # training did not happen and there was nothing to attach the explanation
    # to: an absence is not an object, and no state can point at a gap.
    #
    # NOT A SESSION, and this is the whole reason for a dataset. `sessions`
    # means THIS HAPPENED, and every count, weekly total and load figure
    # depends on it - a skipped row there sums to zero and counts as one,
    # corrupting every one of them silently. So a plan is its own row and a
    # session cites the plan it fulfilled.
    #
    # This retires `sessions.planned`, which is null on every row of every
    # record and every persona corpus - 1692 and 2698 respectively. That reads
    # as neglect and is not: the field lives on a session row, a session that
    # did not happen has none, and the only case it exists to serve is the one
    # case it structurally cannot represent.
    #
    # IDENTITY IS A SLUG, like `goals`, `events`, `protocols` and `medical`. A
    # plan is RESOLVED LATER - created unresolved, becoming completed or
    # skipped afterwards, which in an append-only record is a second row about
    # the same plan - so the identity has to be stable while `outcome` moves,
    # and a composite of attributes cannot be: the attribute that changes is
    # the one being recorded. Two 5 km runs planned on one day, morning and
    # evening, are identical on every other field.
    # NO `target`. The issue's shape lists one, for "duration, distance,
    # load" - three quantities that a single field can only hold as prose,
    # and `target` already means a NUMBER on `goals`, so the name would carry
    # two types across two datasets. What a plan prescribes is #226's
    # question, which is about a template rather than a row; `activity` says
    # what was intended and that is what this dataset needs to attach a state
    # to. Adding a shape later is additive.
    "date", "slug", "for_date", "for_phase", "activity", "setting",
    "tier", "serves", "set_by", "requires", "outcome", "reason",
    "session_ref", "note", "supersedes", "recorded_at", "device",
]
for _ds in ("protocols", "regimes", "emissions", "plans"):
    CURRENT_GENERATION[_ds] = 1

IDENTITY_KEY["protocols"] = "slug"
IDENTITY_KEY["plans"] = "slug"

# WHAT MAKES RECORDING AN INTENTION SAFE (#221). If every plan counts equally,
# writing down "maybe a run tonight" and not running damages an adherence
# figure - so the athlete stops writing them down and the record loses the
# material that would have explained his week. A design that penalises honesty
# trains dishonesty, which is the failure the regime work already names.
#
# Discriminated by WHAT THE PLAN SERVES rather than by how committed it felt:
# feeling is not recoverable later and a link to a goal is.
#
# NOT AUTHORSHIP. `set_by` carries that, on the same row, with the vocabulary
# `goals`, `events` and `thresholds` already use - a coach-set plan and a
# self-set plan can both be binding. FHIR's `CarePlan.intent`
# (proposal|plan|order) was proposed for this axis and is declined for that
# reason: it is an authorisation hierarchy, which is the thing `set_by`
# already says.
PLAN_TIERS = {"programme", "committed", "provisional"}

# HOW A PLAN RESOLVED. Largely FHIR's `CarePlan.activity.detail.status`, with
# one value that is genuinely ours.
#
# `did_not_activate` - the precondition never held. "I would run if it were
# not raining; it rained." That is not skipped: the plan never became live, so
# there was nothing to skip, and without the value a cautious athlete who
# writes down a condition is punished for the forecast.
#
# `abandoned` produces BOTH a session row for what was done and a plan
# resolved as abandoned. They are not exclusive.
#
# `unresolved` is the default AND THE ENGINE MUST NEVER FILL IT IN. Silence is
# not a lapse: an athlete who has not answered has said nothing, and a record
# that reads that as a missed session is inventing a fact about him.
PLAN_OUTCOMES = {"completed", "skipped", "abandoned", "substituted",
                 "did_not_activate", "unresolved"}

# WHY, orthogonal to how. From COM-B (Michie, van Stralen & West 2011,
# Implement Sci 6:42), which classifies behaviour barriers on three axes with
# two subtypes each - adopted because a two-value `gated | chosen` collapses
# them, and `chosen` swallowed both motivation subtypes plus half of
# capability, which have opposite coaching consequences.
#
# A CLASSIFICATION, NEVER A SCORE. COM-B is not a measurement instrument and
# nothing here totals it, ranks it or trends it.
#
# Two values are not COM-B's. `displaced` is the case neither gated nor
# chosen: no decision was taken and the window closed while the athlete was
# doing something else. `declined` is G82 - not telling you is a permanent,
# legitimate answer, and an axis without it forces a reason out of someone who
# has said they will not give one.
PLAN_REASONS = {
    "capability_physical",        # pain, exhaustion, injury
    "capability_psychological",   # did not know how to adapt the session
    "opportunity_physical",       # gym shut, no kit, no time
    "opportunity_social",         # partner unavailable, childcare
    "motivation_reflective",      # a deliberate taper - the achievement case
    "motivation_automatic",       # could not face it
    "displaced",                  # the window was consumed, no decision taken
    "declined",                   # not telling you (G82, permanent)
    "unresolved",                 # nothing said; never engine-filled
}


# --- protocol: the conditions a measurement was taken under (#171) -----------
#
# The distinguishing feature of a well-anchored measurement is that it names
# its conditions. This extends the anchor concept the engine already has
# (`resolution.QUANTITY_CLASS` marks weight and measurements as anchors): a
# protocol-anchored measurement is an anchor, and a span between anchors under
# no protocol is an unanchored interval.
#
# THE EPISTEMIC RULE, and it is load-bearing: a row with NO protocol is a
# different epistemic class from one with a protocol, not a row with a missing
# optional field. The unprotocolled row carries the measurand's full
# DEFINITIONAL uncertainty, which for body mass dominates instrument error by
# an order of magnitude - phase 0 measured exactly that.
#
# Appended last, per the standing rule: a generation block appends, and a new
# field never lands ahead of one already in the wild.
for _ds in ("weight", "measurements"):
    CURRENT_GENERATION[_ds] += 1
    KEY_GENERATION.setdefault(_ds, {})["protocol"] = CURRENT_GENERATION[_ds]
    KEYS[_ds].append("protocol")


# --- derivation lineage (#170) ----------------------------------------------
#
# A value computed from other rows must be able to NAME them. Without that, a
# correction to an input leaves every value derived from it standing, and
# nothing can say which numbers are now resting on a claim the record has
# retracted.
#
# DECLARED lineage only. The semiring-provenance result is that declared
# lineage is sufficient to DETECT staleness; re-execution is needed only to
# correct drift, and this engine does not re-execute.
#
# The ids are `identity.row_ref` grammar rather than `claim_id`, which is what
# the proposal named: #181 shipped in between, and `claim_id` cannot name a
# set or a meal item uniquely - it collided on 8 of 11 `sets` rows in the demo
# corpus. A lineage pointing at three rows is not lineage.
for _ds in ("weight", "daily", "sessions", "measurements", "sets", "meals"):
    CURRENT_GENERATION[_ds] += 1
    for _k in ("derived_from", "derived_op"):
        KEY_GENERATION.setdefault(_ds, {})[_k] = CURRENT_GENERATION[_ds]
        KEYS[_ds].append(_k)

# --- the rest of the macros, and the two sleep instants -----------------------
# MACROS (#188). Energy and protein were the founding pair because they are what
# a cut is steered by. Everything else the athlete actually logs - fat,
# carbohydrate, fibre, sugar, sodium - had nowhere to land and ended up in
# `note` as prose, which is where data goes when the schema has no room. The
# day-level figures are TOTALS; per-item composition lives on `meals`.
#
# `sodium_mg` and `sodium_mg_100g` carry the unit in the name because sodium is
# conventionally reported in milligrams while every macro beside it is grams,
# and a bare `sodium_g` would be misread by exactly the reader not thinking
# about it. The `meals` half costs nothing today - the dataset is empty on every
# record we know of - and would cost a real migration later, which is the whole
# argument for doing both halves in one change.
#
# NOT a polarity, and deliberately not one: a floor (protein, fibre) and a
# ceiling (sodium, added sugar) are the same shape HERE, because this is an
# observation, not a target. Which direction is good belongs to the goal that
# names the metric, and is a separate piece of work.
for _ds, _keys in (
    ("daily", ("fat_g", "carb_g", "fibre_g", "sugar_g", "sodium_mg")),
    ("meals", ("fibre_100g", "sugar_100g", "sodium_mg_100g")),
):
    CURRENT_GENERATION[_ds] += 1
    for _k in _keys:
        KEY_GENERATION.setdefault(_ds, {})[_k] = CURRENT_GENERATION[_ds]
        KEYS[_ds].append(_k)

# SLEEP INSTANTS (#190). `sleep_h` is a duration and throws away WHEN. These two
# are what a day boundary can be anchored to (G61), and what makes "how much of
# tonight is left to eat in" answerable at all. Offset-bearing, the same shape
# as `sessions.start_time`, because 23:40 local means a different thing in two
# zones - and a night that crosses a zone is exactly when the anchor matters.
#
# A SEPARATE generation from the macros above, though they ship together: they
# are unrelated facts, and a row that carries one has said nothing about the
# other. Keeping these is additive and cheap; SPENDING them on a subjective day
# boundary rewrites every bucketed number in the engine and is deliberately a
# different piece of work (#203).
CURRENT_GENERATION["daily"] += 1
for _k in ("sleep_start", "sleep_end"):
    KEY_GENERATION["daily"][_k] = CURRENT_GENERATION["daily"]
    KEYS["daily"].append(_k)


# --- goal polarity (#200) ---------------------------------------------------
#
# WHICH DIRECTION COUNTS AS PROGRESS. Appended, so a goal line written before
# this keeps validating and scores exactly as it did: absent reads as `floor`,
# which is what both existing policies already mean.
CURRENT_GENERATION["goals"] += 1
for _k in ("polarity", "target_hi"):
    KEY_GENERATION.setdefault("goals", {})[_k] = CURRENT_GENERATION["goals"]
    KEYS["goals"].append(_k)


# --- what a subjective number is out of (#246) -------------------------------
#
# POST-COORDINATED beside the value rather than fixed per field. A stored
# `rpe: 7` is "quite light" on Borg's 6-20 and "very hard" on CR10, and
# nothing in the record said which - so the difference, which is the whole
# signal, was unrecoverable. Fixing one scale per field in the schema would be
# cheaper and would force that choice on every record including imported ones,
# and a vendor export may well use the other.
#
# ABSENT MEANS UNSTATED. No reader may invent a denominator: rendering "4 out
# of 10" against an undeclared scale asserts a bound the record never carried.
for _ds, _keys in (("sessions", ("rpe_scale",)), ("sets", ("rpe_scale",)),
                   ("daily", ("mood_scale", "pain_scale"))):
    CURRENT_GENERATION[_ds] += 1
    for _k in _keys:
        KEY_GENERATION.setdefault(_ds, {})[_k] = CURRENT_GENERATION[_ds]
        KEYS[_ds].append(_k)
# --- what became of a fixture (#139) ----------------------------------------
CURRENT_GENERATION["events"] += 1
KEY_GENERATION.setdefault("events", {})["outcome"] = \
    CURRENT_GENERATION["events"]
KEYS["events"].append("outcome")

# --- which side an episode is on (#145) --------------------------------------
#
# `daily` has carried `pain_side` since generation 2, added so laterality
# POST-COORDINATES rather than being baked into a site name, which is the FHIR
# and openEHR pattern. `medical` had no equivalent, so a left-knee episode and
# a right-knee episode were the same episode.
#
# That matters for a restriction rather than for tidiness: gating "the knee"
# bans a movement the athlete performs perfectly well on the other leg, and
# over-restriction is its own harm - which the restriction vocabulary already
# says in as many words.
#
# OPTIONAL, and the reason is the whole point of this mechanism. Requiring a
# side would refuse every episode already written, and an episode entered
# before the field existed never owed one. `validate` advises where a paired
# site carries no side; it does not refuse.
CURRENT_GENERATION["medical"] += 1
KEY_GENERATION.setdefault("medical", {})["body_side"] = \
    CURRENT_GENERATION["medical"]
KEYS["medical"].append("body_side")

# --- goal lifecycle, split from achievement (#235) ---------------------------
#
# `status` mixed two axes. `lifecycle_status` takes over the one the athlete
# declares; the achievement axis is DERIVED and lives on the progress row,
# not here, because a goals line is a declaration and the engine does not get
# to write its opinion into one.
CURRENT_GENERATION["goals"] += 1
KEY_GENERATION.setdefault("goals", {})["lifecycle_status"] = \
    CURRENT_GENERATION["goals"]
KEYS["goals"].append("lifecycle_status")
# G25's other half: `status` stops being EXPECTED here and stays legal
# forever. An old line carrying it validates unchanged and reads forward
# through the one canonicaliser in `policy`.
KEY_RETIREMENT.setdefault("goals", {})["status"] = CURRENT_GENERATION["goals"]

# --- a plan is not a session (#221) ------------------------------------------
#
# `sessions.planned` is RETIRED, and stays legal forever like every retired
# key. It is null on 1692 of 1692 rows in a live record and on 0 of 2698
# persona session rows across nine people and three years, which reads as
# neglect and is not: the field lives on a session row, a session that did not
# happen has none, and the only case it exists to serve is the one case it
# structurally cannot represent. Every non-null value it will ever hold
# describes a plan that was followed.
#
# `session_ref` on a plan is the direction that works - the plan is the object
# and the session cites it, which is where FHIR arrived independently when R5
# replaced `activity.detail` with `plannedActivityReference` and
# `performedActivity`.
CURRENT_GENERATION["sessions"] += 1
KEY_RETIREMENT.setdefault("sessions", {})["planned"] = \
    CURRENT_GENERATION["sessions"]


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
    "fibre_100g": _NUMERIC, "sugar_100g": _NUMERIC, "sodium_mg_100g": _NUMERIC,
    # Day totals. `sodium_mg` is milligrams; every other macro here is grams.
    "fat_g": _NUMERIC, "carb_g": _NUMERIC, "fibre_g": _NUMERIC,
    "sugar_g": _NUMERIC, "sodium_mg": _NUMERIC,
    "body_fat_pct": _NUMERIC, "kg_lo": _NUMERIC, "kg_hi": _NUMERIC,
    "body_fat_lo": _NUMERIC, "body_fat_hi": _NUMERIC,
    "target": _NUMERIC, "target_hi": _NUMERIC, "guard_pct": _NUMERIC,
    "value": _NUMERIC,
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


SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# A row that names its lineage has been COMPUTED, and must say so. Without
# this a derived value is indistinguishable from an observation, which is the
# laundering the whole provenance layer exists to prevent.
DERIVED_CAPTURES = {"derived", "derived_external"}


EMISSION_KINDS = ("verdict", "warning", "plan", "requirement")


def _emission_problems(rec: dict) -> list[str]:
    """Checks on a surfaced assertion (01-schema 8b).

    STRICTER THAN MOST DATASETS HERE, and deliberately. Elsewhere a missing
    field is an athlete who did not write something down, and refusing it
    would make recording cost more than not bothering. This dataset is written
    by a PROGRAM at delivery time, so a missing field is a consumer bug, and
    the row's whole purpose is to be quotable later without recompute. An
    assertion that cannot say what it asserted is worse than no row: it
    records that something was said and loses what.
    """
    out = []
    kind = rec.get("kind")
    if kind not in EMISSION_KINDS:
        out.append(f"'kind' is one of {', '.join(EMISSION_KINDS)}, got "
                   f"{kind!r}")
    for field in ("statement", "surface", "policy_asof"):
        if not str(rec.get(field) or "").strip():
            out.append(f"'{field}' is required on an emission: a row that "
                       f"cannot say what was asserted, who delivered it, or "
                       f"under which policy cannot be checked against later "
                       f"knowledge, which is the only reason the row exists")
    # SHAPES, not just presence. A `policy_asof` of "banana" satisfies "is not
    # blank" and satisfies nothing else: the replay that reads it has to
    # resolve it to a date, and discovering that at replay time is discovering
    # it after the assertion has already been acted on.
    if (asof := rec.get("policy_asof")) and _bad_date(str(asof)):
        out.append(f"'policy_asof' is an ISO date naming the policy in force "
                   f"when this was computed, got {asof!r}")
    if (wk := rec.get("week")) is not None:
        if _bad_date(str(wk)):
            out.append(f"'week' is an ISO date, got {wk!r}")
        elif date.fromisoformat(str(wk)).weekday() != 0:
            out.append(f"'week' is the MONDAY of the week the assertion was "
                       f"about, and {wk!r} is not a Monday. The engine buckets "
                       "on Monday, so any other day names a week that does "
                       "not line up with the one that was judged")
    if (surf := rec.get("surface")) and not SLUG_RE.match(str(surf)):
        out.append(f"'surface' is a lowercase-kebab slug naming the consumer "
                   f"that delivered this, got {surf!r}")
    if (c := rec.get("contract")) is None or isinstance(c, bool) or not (
            isinstance(c, int) or str(c).isdigit()):
        out.append(f"'contract' is the contract version at emission, got "
                   f"{c!r}. Without it a replay cannot know whether the "
                   "statement still means what it meant")
    basis = rec.get("basis_claims")
    if basis is not None:
        if not isinstance(basis, (list, tuple)):
            out.append(f"'basis_claims' is a list of claim ids, got {basis!r}")
        elif any(not isinstance(b, str) or ":" not in b for b in basis):
            out.append("'basis_claims' takes claim ids, and one of these is "
                       "not one")
    return out


def _lineage_problems(dataset: str, rec: dict) -> list[str]:
    """Checks on `derived_from` and `derived_op` (#170)."""
    # Through the alias layer, not against the raw string. `derived` and
    # `derived_external` each carry aliases the registry resolves, and a row
    # written `capture: "athlete-derived"` is a correctly-captured derived row
    # that a raw comparison would reject.
    from .provenance import capture_of

    out = []
    lineage, op = rec.get("derived_from"), rec.get("derived_op")
    if lineage is None:
        if op is not None:
            out.append("'derived_op' says HOW a value was computed and means "
                       "nothing without 'derived_from' saying from what")
        return out
    if not isinstance(lineage, (list, tuple)) or not lineage:
        out.append("'derived_from' is a non-empty list of row references; a "
                   "row that names no input has not declared a lineage")
        return out
    for ref in lineage:
        if not isinstance(ref, str) or ref.count(":") < 1:
            out.append(f"'derived_from' takes row references, got {ref!r}")
    # NO SELF-REFERENCE CHECK HERE, and the reason is worth stating because
    # the check looks obviously correct. `row_ref` numbers a row by its
    # position among the rows sharing its date and source, and this function
    # sees ONE record with no set around it, so it computes ordinal 0 for
    # every row. A second same-day same-source reading deriving from the first
    # therefore names a reference identical to the one computed for itself -
    # a true lineage, rejected. The set-aware check lives in
    # `resolution.derivation_cycles`, which has the real ordinals.
    if capture_of(rec) not in DERIVED_CAPTURES:
        out.append(
            f"a row with 'derived_from' was COMPUTED, so its capture is one "
            f"of {', '.join(sorted(DERIVED_CAPTURES))}, got "
            f"{rec.get('capture')!r}. A derived value that renders as an "
            "observation is the laundering the provenance layer exists to "
            "prevent")
    return out


def _protocol_problems(rec: dict) -> list[str]:
    out = []
    if not SLUG_RE.match(str(rec.get("slug") or "")):
        out.append(f"'slug' is a lowercase-kebab identifier, got "
                   f"{rec.get('slug')!r}")
    if not str(rec.get("text") or "").strip():
        out.append("'text' says what the procedure IS, in the athlete's own "
                   "words. A slug with no definition is a name for something "
                   "nobody wrote down")
    return out


def _regime_problems(rec: dict) -> list[str]:
    """A regime is a bounded interval, and the bounds are the whole point."""
    out = []
    if rec.get("kind") not in REGIME_KINDS:
        out.append(f"'kind' is one of {', '.join(sorted(REGIME_KINDS))}, got "
                   f"{rec.get('kind')!r}")
    first, last = rec.get("from_date"), rec.get("to_date")
    for name, value in (("from_date", first), ("to_date", last)):
        if not isinstance(value, str) or not DATE_RE.match(value):
            out.append(f"'{name}' is an ISO date, got {value!r}")
    if isinstance(first, str) and isinstance(last, str) and last < first:
        out.append(f"'to_date' {last} is before 'from_date' {first}; a regime "
                   "is an interval and an interval that ends before it starts "
                   "empties nothing")
    if rec.get("dataset") not in KEYS:
        out.append(f"'dataset' names a dataset to scope to, got "
                   f"{rec.get('dataset')!r}")
    elif rec.get("field") not in KEYS[str(rec["dataset"])]:
        out.append(f"'field' {rec.get('field')!r} is not a column of "
                   f"{rec['dataset']}")
    if not str(rec.get("text") or "").strip():
        out.append("'text' is the athlete's own account of the interval. A "
                   "regime empties real days, and doing that without saying "
                   "why leaves a hole nobody can read later")
    return out


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
    if (dev := rec.get("device")) is not None:
        from .devices import is_slug
        if not is_slug(dev):
            problems.append(
                f"'device' is a slug naming the machine that wrote this line "
                f"(lowercase, digits, hyphens), got {dev!r} - it becomes part "
                "of a filename, so a dot or a separator would make the "
                "dataset ambiguous")
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
    if "derived_from" in keys:
        problems += _lineage_problems(dataset, rec)
    if dataset == "protocols":
        problems += _protocol_problems(rec)
    if dataset == "regimes":
        problems += _regime_problems(rec)
    if dataset == "emissions":
        problems += _emission_problems(rec)
    problems += _scale_problems(dataset, rec)
    if dataset in ("weight", "measurements") and rec.get("protocol") is not None:
        if not SLUG_RE.match(str(rec["protocol"])):
            problems.append(
                f"'protocol' is a lowercase-kebab slug, got "
                f"{rec['protocol']!r}. The slug does not have to be DEFINED "
                "yet - an undefined one is legal and validate only advises - "
                "but it has to be a slug")
    if dataset == "plans":
        problems += _validate_plan(rec)
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
        problems += modifier_problems(rec)
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
        # The sleep instants take the same shape as `sessions.start_time`.
        # Checked here rather than trusted, because a sleep boundary that
        # cannot be parsed is worse than one that is absent: absence is
        # honest, and a bad instant would be silently dropped to null by every
        # reader and then read as "the athlete did not sleep".
        for k in ("sleep_start", "sleep_end"):
            if (t := rec.get(k)) is not None and _bad_time(t):
                problems.append(f"bad {k} {t!r} (ISO-8601, e.g. "
                                "2026-08-01T23:40:00+02:00)")
        # A sleep that ends before it starts is a transcription error, not a
        # short night. Deliberately NOT a duration check: the engine has no
        # business saying how long a night should be, and a 3-hour night is a
        # fact about the athlete rather than a fault in the row.
        _ss, _se = rec.get("sleep_start"), rec.get("sleep_end")
        if _ss and _se and not _bad_time(_ss) and not _bad_time(_se) \
                and parse_time(_se) <= parse_time(_ss):
            problems.append(f"'sleep_end' {_se!r} is not after 'sleep_start' {_ss!r}")
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


# The intake floor a declared target may not be set beneath. Imported from
# `safety` at call time rather than restated here: one number, one owner, and
# a restated constant is a second definition waiting to drift from the first.
# Which value each `_scale` column governs.
SCALED_FIELDS = {"rpe_scale": "rpe", "mood_scale": "mood",
                 "pain_scale": "pain"}


def scales() -> dict:
    """The registered scales, by slug."""
    from .vocab import registry
    return registry("scales").get("scales") or {}


def statistics() -> dict:
    """The registered descriptive statistics, by slug (#261 layer 1)."""
    from .vocab import registry
    return registry("statistics").get("statistics") or {}


def _scale_problems(dataset: str, rec: dict) -> list[str]:
    """A declared scale must be one we know, and the value must fit it (#246).

    Declaring a scale is what makes the number interpretable, so a scale that
    bounds nothing is worse than none: it reads as though the question was
    settled. The range check is the point of declaring.
    """
    out = []
    known = scales()
    for column, field in SCALED_FIELDS.items():
        if column not in KEYS.get(dataset, []):
            continue
        declared = rec.get(column)
        if declared is None:
            continue
        if rec.get(field) is None:
            out.append(f"{column!r} declares what {field!r} is out of, and "
                       f"there is no {field!r} on this line")
            continue
        spec = known.get(str(declared))
        if spec is None:
            out.append(f"{declared!r} is not a scale this engine knows; one "
                       f"of {', '.join(sorted(known))}. Every scale here is "
                       "published prior art with a citation")
            continue
        value = rec.get(field)
        if isinstance(value, _NUMERIC) and not isinstance(value, bool):
            if not spec["min"] <= value <= spec["max"]:
                out.append(f"{field!r} is {value!r}, outside {declared} "
                           f"({spec['min']} to {spec['max']}). A value its own "
                           "declared scale cannot hold means one of the two is "
                           "wrong, and the engine cannot tell which")
    return out


def _floor_problems(rec: dict) -> list[str]:
    """A target declared under a safety floor is refused (#191).

    Adding a nutrition target with no declaration gate creates a new way to
    state an unmeetable number and then be told you are behind it every
    period, which is the alarm-fatigue failure arriving through the front
    door. The floor is not suppressible - it fires from defaults whatever the
    athlete configures - so a target beneath it does not lower the bar, it
    just guarantees the two disagree forever.

    ONLY WHAT IS CHECKABLE HERE. The energy floor is a constant, so a daily
    `kcal_in` target below it is refusable at declaration. The PROTEIN floor
    is per kilogram of bodyweight, and this function sees one record with no
    record around it, so a grams-per-day target cannot be compared against it
    without the athlete's weight. That half needs the set-aware gate G58 asks
    for and is deliberately not guessed at here.
    """
    from .safety import INTAKE_FLOOR_KCAL

    if rec.get("metric") != "kcal_in" or rec.get("period") != "daily":
        return []
    target = rec.get("target")
    if not isinstance(target, _NUMERIC) or isinstance(target, bool):
        return []
    if target > INTAKE_FLOOR_KCAL:
        return []
    return [f"a daily 'kcal_in' target of {target:g} is at or below the "
            f"{INTAKE_FLOOR_KCAL:g} kcal safety floor, which cannot be "
            "switched off by declaring one. Scoring against it would report a "
            "miss every day for hitting the number, while the floor reported "
            "a miss for the same days at the same time"]


def _band_problems(rec: dict) -> list[str]:
    """`target_hi` belongs to a band and to nothing else (#200).

    A band is the one polarity with two bounds, and both of its misses are
    real: under and over are different failures with different remedies. On any
    other polarity a second bound is a value nothing reads, which is the
    "specified and never written" shape from the other direction - written and
    never read.
    """
    hi, polarity = rec.get("target_hi"), rec.get("polarity")
    if polarity == "band":
        if hi is None or rec.get("target") is None:
            return ["a band needs both bounds: 'target' is the low one and "
                    "'target_hi' the high one, and a band with one edge is a "
                    "floor or a ceiling wearing the wrong word"]
        if not isinstance(hi, _NUMERIC) or isinstance(hi, bool):
            return [f"'target_hi' is the band's upper bound and must be a "
                    f"number, got {hi!r}"]
        lo = rec.get("target")
        if isinstance(lo, _NUMERIC) and isinstance(hi, _NUMERIC) and (
                not isinstance(lo, bool) and not isinstance(hi, bool)
                and hi <= lo):
            return [f"a band runs from 'target' up to 'target_hi', so "
                    f"{hi!r} must be above {lo!r}"]
        return []
    if hi is not None:
        return [f"'target_hi' is the upper bound of a BAND, and this goal is "
                f"{polarity or 'a floor'}. Only a band has two bounds"]
    return []
def _lifecycle(rec: dict) -> str | None:
    """The goal's lifecycle, successor first (#235).

    Schema validation cannot import `policy` - `policy` imports this module -
    so the forward map is applied through a thin local reader rather than
    duplicated. `policy.LIFECYCLE_FORWARD` remains the one table; this is the
    second CALLER of it, not a second copy, which is the distinction G89's
    hip_pain instance turned on.
    """
    from .policy import LIFECYCLE_FORWARD
    declared = rec.get("lifecycle_status")
    if declared:
        return str(declared)
    old = rec.get("status")
    return LIFECYCLE_FORWARD.get(str(old), str(old)) if old else None


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
    problems: list[str] = []
    for key in ("slug", "title"):
        if not isinstance(rec.get(key), str) or not rec.get(key):
            problems.append(f"'{key}' must be a non-empty string")
    problems += _enum(rec, "kind", MEDICAL_KINDS)
    problems += _enum(rec, "status", MEDICAL_STATUSES)
    if rec.get("kind") == "visit" and _dated_after_it_was_written(rec):
        # A `visit` records a visit that HAPPENED - a fact with a date, and
        # useful provenance for whatever was said there. A row dated in the
        # future is an appointment, which is a plan, and vitai does not own
        # the record owner's plans for their own body (#110).
        #
        # Held as data it becomes a to-do nobody can complete inside the tool,
        # re-raised at every review until it is noise to be dismissed. Nothing
        # in consumer fitness tracks an appointment as an open item; that is a
        # care-plan feature and it lives where a clinician owns the list.
        problems.append(
            f"a 'visit' dated {rec.get('date')!r} is in the future, so it is "
            "an appointment rather than a visit. This record holds what "
            "happened; record the visit once it has")
    problems += _enum(rec, "severity", SEVERITIES)
    problems += _enum(rec, "provider_type", PROVIDER_TYPES, optional=True)

    # The SAME rule `daily` uses, called rather than mirrored (#145), with one
    # difference stated rather than left to be discovered: a side is OPTIONAL
    # here. Requiring one would refuse every episode already written, and an
    # episode entered before the field existed never owed a side. What a
    # paired site with no side gets instead is an advisory - see
    # `side_advisories` - because "the knee" still does not say which knee to
    # stop loading. A midline site takes no side at all, and that is refused.
    problems += _validate_location(rec, "body_site", "body_side",
                                   needs_side=False)
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


def _dated_after_it_was_written(rec: dict) -> bool:
    """Is this row's valid time after its transaction time?

    "In the future" measured against the RECORD's own clocks rather than
    against today. Comparing to `date.today()` would make a row's validity
    depend on when it is read - the same line valid this morning and invalid
    tomorrow - which breaks the determinism the whole engine rests on, and
    would fail every 2030-dated fixture in the repo for being prescient.

    Transaction time is the honest comparison anyway, and the record already
    carries it: a visit whose `date` is after the moment the line was WRITTEN
    is a visit that had not happened when it was recorded. That is exactly
    what an appointment is.

    A FULL DAY of slack, because the two clocks are not on one calendar. The
    visit's `date` is a calendar day where it happened; `recorded_at` carries
    the writing machine's offset. A visit at 00:30 in UTC+13, written minutes
    later on a laptop still on +02:00, is the same instant on two different
    days - and rejecting that as an appointment would be wrong about a visit
    that had already happened. No offset pair on Earth spans more than 26
    hours, so one day of tolerance removes the whole class.

    The cost is that a same-day appointment passes. That is accepted: this
    catches the unambiguous case, and a check that also fired on real visits
    would be argued away rather than fixed.

    Absent `recorded_at` means absent: a legacy row predating the clocks
    cannot be judged, and guessing would retroactively invalidate history.
    """
    stamp = rec.get("recorded_at")
    if not stamp:
        return False
    try:
        when = date.fromisoformat(str(rec.get("date")))
        written = date.fromisoformat(str(stamp)[:10])
    except (TypeError, ValueError):
        return False
    return (when - written).days > 1


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


def side_advisories(rows: list[tuple[int, dict]]) -> list[str]:
    """Episodes on a paired site that do not say which one (#145).

    The field is optional and stays optional - requiring it would refuse every
    episode already written, and one entered before it existed never owed a
    side. But an open episode on a paired site with no side is the exact case
    #145 is about: a gate on "the knee" bans a movement the athlete performs
    perfectly well on the other leg, and over-restriction is its own harm.

    ADVISORY, never a problem, and only where the episode can still GATE. A
    resolved episode restricts nothing, so naming its side changes no answer,
    and repeating the note once per line of one episode is noise about a
    decision already taken.

    Written because it was CLAIMED. Two comments said `validate` advises on
    this while nothing did, which is the specified-and-never-written defect
    this repo keeps finding in other people's work.
    """
    from .anatomy import is_paired, resolve

    latest: dict = {}
    for n, rec in rows:
        if rec.get("slug"):
            latest[rec["slug"]] = (n, rec)

    out = []
    for n, rec in latest.values():
        site = rec.get("body_site")
        if not site or rec.get("body_side") or not is_paired(site):
            continue
        if rec.get("status") in ("resolved", "cancelled"):
            continue
        if not rec.get("restricts") and not rec.get("restriction"):
            continue
        out.append(
            f"line {n}: episode {rec.get('slug')!r} is on the "
            f"{resolve(site)}, which exists on both sides, and does not say "
            f"which. A gate naming only the site restricts the limb that is "
            f"fine as well; set 'body_side' to left, right or bilateral")
    return out


def _validate_plan(rec: dict) -> list[str]:
    """A plan row, and the three rules that keep it from lying (#221)."""
    problems = []
    if not SLUG_RE.match(str(rec.get("slug") or "")):
        problems.append(
            "'slug' is a plan's IDENTITY and is required: a plan is resolved "
            "later, so a second row about the same plan needs something "
            "stable to name it by, and every other field can repeat")
    problems += _enum(rec, "tier", PLAN_TIERS)
    problems += _enum(rec, "outcome", PLAN_OUTCOMES, optional=True)
    problems += _enum(rec, "reason", PLAN_REASONS, optional=True)
    problems += _enum(rec, "set_by", AUTHORS, optional=True)
    if (when := rec.get("for_date")) is None or _bad_date(str(when)):
        problems.append(
            f"'for_date' is the day the plan is FOR, ISO-8601, got {when!r}. "
            "It is distinct from 'date', the day the plan was made: a plan "
            "made a week ahead and one made that morning are different "
            "commitments")

    # A PROGRAMME PLAN SERVES SOMETHING, which is what makes the tier
    # discriminable later. Tier is decided by what a plan serves rather than
    # by how committed it felt, because feeling is not recoverable and a link
    # is - so a programme plan naming nothing has thrown away the only
    # evidence for its own tier.
    if rec.get("tier") == "programme" and not rec.get("serves"):
        problems.append(
            "a 'programme' plan serves a declared goal or instrument and must "
            "name it in 'serves' - the tier is decided by what the plan "
            "serves, so one that names nothing cannot be told from a "
            "'committed' plan later")

    # `did_not_activate` MEANS A CONDITION NEVER HELD, so there has to be a
    # condition. Without one the value says a plan failed to become live with
    # nothing that could have made it live, which is `skipped` wearing a
    # kinder word - and the whole point of the value is that a cautious
    # athlete who writes a condition down is not punished for the forecast.
    if rec.get("outcome") == "did_not_activate" and not rec.get("requires"):
        problems.append(
            "'did_not_activate' says the plan's precondition never held, so "
            "'requires' has to name one. A plan with no condition that never "
            "activated is a skipped plan")

    # SILENCE IS NOT A LAPSE. An unresolved plan has not been answered, and a
    # reason beside it would be the engine or the writer supplying an
    # explanation for something nobody has yet said happened.
    if rec.get("outcome") in (None, "unresolved") and rec.get("reason") not in (
            None, "unresolved"):
        problems.append(
            f"'reason' explains an OUTCOME and this plan has none yet (got "
            f"reason {rec.get('reason')!r}). An unresolved plan is one nobody "
            "has answered about, and a record that explains a non-event has "
            "invented it")
    return problems


def _validate_event_outcome(rec: dict) -> list[str]:
    """An outcome is about a date that has ARRIVED (#139).

    Two things the pair must not be able to say. An outcome on a fixture still
    in the future asserts what became of something that has not happened, and
    an outcome on a fixture cancelled in advance says it both did not take
    place and took place - the two axes contradicting each other rather than
    describing different things.
    """
    outcome = rec.get("outcome")
    if outcome is None:
        return []
    problems = []
    when, line = rec.get("event_date") or rec.get("date"), rec.get("date")
    # PARSED, not compared as text. `date.fromisoformat` accepts basic form
    # (`20300915`) and week dates (`2030-W20-1`), so `'-' < '0'` let a future
    # outcome through and refused a past one written in the other spelling.
    both = None
    if when and line and not _bad_date(str(when)) and not _bad_date(str(line)):
        both = (date.fromisoformat(str(when)), date.fromisoformat(str(line)))
    if both and both[0] > both[1]:
        problems.append(
            f"'outcome' says what became of this fixture, and {when!r} is "
            "later than the day this line was written. A date still to come "
            "has no outcome; leave it null until it has arrived")
    if rec.get("status") == "cancelled":
        problems.append(
            "a cancelled fixture did not take place, so it has no 'outcome' - "
            "`status` already says what became of it")
    return problems


def _validate_pain_location(rec: dict) -> list[str]:
    """`pain_site` against the curated registry, `pain_side` against anatomy."""
    # BOTH flags follow `pain`, which is what this rule always did: a daily
    # row naming a midline site and a side with no pain score was legal, and
    # tightening that silently would fail lines already written, forever, with
    # no remedy but a correction.
    scored = bool(rec.get("pain"))
    return _validate_location(rec, "pain_site", "pain_side",
                              needs_side=scored, check_midline=scored)


def _validate_location(rec: dict, site_key: str, side_key: str,
                       needs_side: bool, check_midline: bool = True) -> list[str]:
    """One site-and-side rule, for every dataset that carries a pair (#145).

    `daily` had this and `medical` had no side at all, so a left-knee episode
    and a right-knee episode were the same episode - and gating "the knee"
    bans a movement the athlete performs perfectly well on the other leg,
    which is the over-restriction the restriction vocabulary already warns
    about.

    Written once rather than mirrored: two copies of a rule about paired
    anatomy are two chances for one of them to learn about a new midline site
    alone.

    Imported lazily so `schema` stays importable without touching the
    filesystem - validation is the only thing that needs the registry, and a
    schema module that reads a file on import is a schema module that fails
    in odd places.
    """
    from .anatomy import SIDES, describe, is_paired, is_site, known_sites, resolve

    problems: list[str] = []
    site = rec.get(site_key)
    side = rec.get(side_key)

    if site and not is_site(site):
        problems.append(
            f"unknown {site_key!r} {site!r} - use one of {', '.join(known_sites())} "
            "(or an alias the registry knows; add one in semantics/body_sites.toml "
            "rather than inventing a site here)")
        return problems

    if side is not None and side not in SIDES:
        problems.append(f"{side_key!r} must be one of {sorted(SIDES)} or null, "
                        f"got {side!r}")
    if side is not None and not site:
        problems.append(f"{side_key!r} without a {site_key!r} says nothing")

    if site and needs_side:
        # A paired structure without a side is not actionable: "my knee hurts"
        # does not tell a coach which knee to stop loading. Midline sites take
        # no side at all, and claiming one would be a false precision.
        if is_paired(site) and side is None:
            problems.append(
                f"'{resolve(site)}' exists on both sides - set {side_key!r} to "
                "left, right or bilateral")
    if check_midline and site and not is_paired(site) and side is not None:
        problems.append(
            f"'{resolve(site)}' is a midline site ({describe(site)}) and "
            f"takes no {side_key!r}")
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


def unstamped_after_the_clock_started(filename: str,
                                       rows: list[tuple[int, dict]]) -> list[str]:
    """Rows with no `recorded_at` dated inside the stamped era (#149).

    `known_by` lets an unstamped row survive every cutoff, which is deliberate
    and right: a legacy line lacks a transaction time by PREDATING the clock,
    and without the affordance `as_of` would empty a legacy corpus instead of
    reconstructing one.

    The hole is that engine writes are the only writes guaranteed to be
    stamped, and the format invites hand editing. A forgotten workout appended
    by hand with no stamp is visible at EVERY historical cutoff, so a
    reconstruction stops being stable - the one property `as_of` exists to
    provide - and the row is invisible as a special case, because it looks
    exactly like a legacy one.

    Keyed on the row's DATE against the earliest stamped date, not on its
    position in the file. File position was the obvious signal and is the
    wrong one: #37 established that an ordering a formatter can change is not
    an ordering, and the demo corpus is written sorted, so a
    position-based rule flags a legitimately regenerated file.

    An ADVISORY, for the same reason the naive-`start_time` check is one: a
    record that predates the clock is not wrong, and making this an error
    would make it unbuildable until every legacy row was rewritten - which
    is the migration the rule would be demanding.
    """
    stamped = [r for _, r in rows if r.get("recorded_at") is not None]
    if not stamped:
        return []  # a wholly unstamped file is a legacy corpus
    # And so is a MOSTLY unstamped one. The first cut asked only whether any
    # stamp existed, which made two stamped rows among fifty start a clock for
    # the whole file - the demo corpus, whose sessions arrived from an export
    # that does not stamp, with one stamped provenance pair. The question this
    # answers is which shape is the EXCEPTION here: where stamping is the
    # exception the file is not on the clock and there is nothing to say;
    # where the MISSING stamp is the exception, that row is the anomaly.
    if len(stamped) * 2 <= len(rows):
        return []
    # Empty dates excluded from the floor. A stamped row with no date made
    # `started` the empty string, so every legacy row sorted after it and the
    # message named a blank date - flagging rows written a decade before the
    # clock existed.
    dates = [d for r in stamped if (d := str(r.get("date") or ""))]
    if not dates:
        return []
    started = min(dates)
    late = sorted({d for _, r in rows
                   if r.get("recorded_at") is None
                   and (d := str(r.get("date") or "")) > started})
    if not late:
        return []
    # Dates, collected DIRECTLY. The first cut kept a list of line numbers and
    # re-selected the rows by `n in late` to recover the dates, which listed
    # every unrelated row sharing a line number and pushed real offenders out
    # of the truncation - an indirection that could only lose information.
    on = ", ".join(late[:8])
    return [f"{filename}: {len(late)} date(s) with no recorded_at, after "
            f"{started} when the clock was already running (on {on}"
            f"{', ...' if len(late) > 8 else ''}). A row that predates the "
            "clock is fine; one dated inside the stamped era was written by "
            "hand, and it stays visible at every historical cutoff - so every "
            "reconstruction of this record changes when it is recomputed"]


# Words that mean a goal counts DOWN. Deliberately a short, literal list: the
# point is to notice the obvious cases, not to parse intent.
_CAPPISH = ("cap", "limit", "under ", "below", "no more than", "at most",
            "max ")


def _still_open(rows: list[tuple[int, dict]]) -> set:
    """Slugs whose LATEST line is still scorable and still undeclared.

    A goal's lifecycle is its latest line's, not each line's, and its polarity
    likewise - the record is append-only, so a goal declared correctly today
    still holds the line that omitted it. Filtering per line meant a goal
    completed in one year and a goal cured by restatement both kept drawing
    the advisory forever, and in an append-only record the athlete has no
    remedy for it. Measured on the persona corpus: three advisories on one
    record, two of them for goals long since closed.
    """
    latest: dict = {}
    for _n, rec in rows:
        slug = rec.get("slug")
        if slug:
            latest[slug] = rec
    return {slug for slug, rec in latest.items()
            if _lifecycle(rec) in ("active", "proposed", "planned",
                                   "accepted", "on_hold")
            and not rec.get("polarity")}


def polarity_advisories(rows: list[tuple[int, dict]]) -> list[str]:
    """Goals whose words say cap and whose scoring says floor (#200).

    Polarity defaults to `floor` so that no existing row re-scores, which is
    the right migration and leaves a real hazard behind: a cap declared before
    polarity existed still scores as an accumulation, so holding under it
    reads as exceeding it.

    The issue's own remedy was that such rows are "identifiable by hand".
    Hunting them by hand is the part that does not survive contact with a
    growing record, so the engine points at them instead.

    ADVISORY, never a problem. A title is prose and prose is not a
    declaration: "cap the ramp at 10 percent" may well be a floor on volume
    with a separate guard, and refusing it would make the engine the author of
    a goal it only read the label of.
    """
    open_goals = _still_open(rows)
    out = []
    for n, rec in rows:
        if rec.get("polarity") or rec.get("target") is None:
            continue
        # Only rows that can still SCORE. An achieved or abandoned goal is
        # never counted, so the hazard the advisory describes does not exist
        # for it, and repeating the warning once per restatement line of the
        # same slug is noise about a decision already taken.
        #
        # THE GOAL's standing, not this line's. `status` retired on `goals`
        # at contract 25 and a line written since carries `lifecycle_status`,
        # so reading the old key alone silently skipped every goal written
        # after the split - inert for new lines ever since, which is the
        # specified-and-never-fires version of the defect (#273).
        if rec.get("slug") not in open_goals:
            continue
        title = str(rec.get("title") or "").lower()
        if any(w in title for w in _CAPPISH):
            out.append(
                f"line {n}: goal {rec.get('slug')!r} reads like a cap "
                f"({rec.get('title')!r}) and has no 'polarity', so it is "
                "scored as a floor - progress counts UP and holding under the "
                "value reads as exceeding it. Declare 'ceiling' if that is "
                "what it is")
    out += _anchor_polarity_advisories(rows)
    return out


def _anchor_polarity_advisories(rows: list[tuple[int, dict]]) -> list[str]:
    """A LEVEL goal with no declared polarity (#273).

    The `floor` default is safe for a flow - more steps is progress, whoever
    wrote the goal - and unsafe for a level, where the direction is the whole
    content of the goal. "Down to 78 kg" defaulted to a floor, which scores
    as though more kilograms were progress, and the class is not obscure:
    losing weight is the motivating case of the whole record.

    NOT the title heuristic above, which needs the word `cap` to fire and
    would need `down to` and `under` and `below` and every phrasing after
    that. This fires on the SHAPE of the goal - a level metric with no
    direction declared - which is a fact about the row rather than a reading
    of its prose.

    Advisory rather than a problem, because old lines keep validating. The
    engine says the direction is undeclared; it does not decide it.
    """
    from .contributions import ANCHOR_DATASETS

    open_goals = _still_open(rows)
    out = []
    for n, rec in rows:
        if rec.get("polarity") or rec.get("target") is None:
            continue
        # See the note in `polarity_advisories`.
        if rec.get("slug") not in open_goals:
            continue
        metric = rec.get("metric")
        declared = rec.get("dataset")
        hosts = {ds for ds in ANCHOR_DATASETS
                 if isinstance(metric, str) and metric in KEYS.get(ds, ())}
        if declared is not None and declared not in ANCHOR_DATASETS:
            continue
        if not hosts:
            continue
        out.append(
            f"line {n}: goal {rec.get('slug')!r} names {metric!r}, which is a "
            f"LEVEL rather than something that accumulates, and has no "
            f"'polarity' - so it is scored as a floor and moving DOWN reads "
            f"as going backwards. Declare 'ceiling' to reach a level from "
            f"above, 'floor' from below")
    return out


def period_advisories(rows: list[tuple[int, dict]]) -> list[str]:
    """Ceilings measured against a total nobody meant (#200).

    A cap is nearly always a per-day limit. Scored over a period that
    accumulates, seven compliant days at 1100 against a 1200 cap read as
    breaching it by 6500 - the old defect facing the other way, and just as
    wrong. `daily` exists now, so this points at the rows that want it.

    ADVISORY, because a genuine period total is a legitimate thing to cap: a
    monthly alcohol budget is a ceiling on a sum and means exactly what it
    says.
    """
    out = []
    for n, rec in rows:
        if rec.get("polarity") != "ceiling" or rec.get("target") is None:
            continue
        # `_lifecycle` and not `status`, which retired at 25 - this one was
        # left inert when the other two were fixed, which is how a defect
        # survives its own diagnosis.
        if _lifecycle(rec) not in ("active", "proposed", "planned",
                                   "accepted", "on_hold"):
            continue
        if rec.get("tracker") == "sum" and rec.get("period") in (None, "none"):
            out.append(
                f"line {n}: goal {rec.get('slug')!r} caps a running total "
                "that never resets, so every logged day pushes it further "
                "over. If this is a per-day limit, set period to 'daily'")
    return out


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
    out: list[str] = []
    if dataset != "sessions":
        return out
    naive = [n for n, r in rows
             if r.get("start_time") and not is_aware(parse_time(r["start_time"]))]
    aware = [n for n, r in rows
             if r.get("start_time") and is_aware(parse_time(r["start_time"]))]
    if not naive or not aware:
        return out
    return out + [
            f"{dataset}.jsonl: {len(naive)} start_time value(s) are naive and "
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

    A bare `supersedes` retires the MOST RECENT line matching its reference
    (#239). It used to retire every one of them, which for a dataset with no
    per-row identity meant correcting one of ten sessions on a day deleted all
    ten - the same harm as a false merge, arriving through the correction
    path.

    So the ambiguity is no longer destructive, and it has not gone away: where
    several lines answer to one reference, the engine picks the newest and the
    author may have meant another. Reported rather than resolved, because the
    engine cannot know which was meant, and the fix is a vendor identity on
    the rows - which only reaches rows written after an importer supplies it.
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
                f"{len(hit)} lines ({', '.join(map(str, hit))}) - the most "
                "recent is the one retired, and it may not be the one meant. "
                "Give these rows a vendor identity (activity_id) so a "
                "correction can say which one it corrects")
        elif not hit:
            problems.append(
                f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches no "
                "line - nothing is being corrected, and the reference is "
                "probably mistyped")
    return problems


def corrections_that_did_not_apply(dataset: str,
                                   rows: list[tuple[int, dict]]) -> list[str]:
    """ADVISORY: a correction that is in the file and did nothing.

    `retire` walks BACKWARDS so a line can only be superseded by a LATER one,
    which is what stops a same-day correction sharing its target's key from
    superseding itself. "Later" means later in the MERGED order - `(recorded_at,
    device, position)`, with an unstamped row sorting first - and that order is
    not always the order the athlete wrote things in. An unstamped correction
    of a stamped line, a correction stamped a minute earlier than its target by
    a second device's clock, an unstamped correction in a device file whose
    slug sorts first: each is ordered BEFORE the line it corrects, so the walk
    reaches the target before it ever sees the reference and the target
    survives. The correction validates, reads correctly to a human, and does
    nothing. A typo fixed from 8.04 to 80.4 leaves 8.04 in the record.

    ASKED, NOT DERIVED. The first cut looked for the shape - unstamped
    correction, stamped target - and got three cases wrong in both directions.
    This runs the same retirement `load` runs and asks whether the correction
    survived ALONGSIDE something it was supposed to retire, which is the actual
    question and is exact.

    That also makes it self-clearing, which a build-failing version was not:
    the append that fixes the record - a fresh, engine-stamped correction -
    retires the dead line along with the value it was aiming at, and this goes
    quiet. An on-disk row that fails the build with no legal path to green is
    the #38 mistake, and append-only means editing the line is not a path.

    An ADVISORY for the same reason: the lines are already on disk, they are
    not malformed, and the record still builds. What was wrong was that
    nothing said so.
    """
    from .devices import merge
    from .jsonl import retire
    # IN MERGED ORDER, which is the whole point. `validate` hands these over
    # in FILE order, one device file after another, and in file order the
    # correction sits below its target and applies perfectly. The defect is
    # created by the reordering, so a check that skips it cannot see it.
    #
    # `merge` over a single unnamed stream is the same code path with one
    # actor, so a single-file record is ordered exactly as `load` orders it.
    lines = merge([("", [r for _, r in rows])], dataset)
    applied: set[str] = set()
    retire(dataset, lines, applied=applied)

    out = []
    seen: set[str] = set()
    for r in lines:
        if not (ref := r.get("supersedes")):
            continue
        ref = str(ref)
        # ASKED OF `retire`, not inferred from what survived (#239). The old
        # check counted anything still alive under the reference as proof the
        # correction did nothing - which was sound while one reference retired
        # every match, and became a false alarm the moment it retired one. A
        # surviving sibling is now the ordinary, intended outcome.
        if ref in applied or ref in seen:
            continue
        seen.add(ref)
        out.append(
            f"{dataset}: a correction of {ref!r} did "
            f"NOT apply - it retired nothing, so the value it was meant to "
            f"replace is what every reader sees. Either it sorted before the "
            f"line it corrects, which happens when a correction carries no "
            f"recorded_at and its target does, or the reference names no line "
            f"at all. Append the correction again with `vitai append` and the "
            f"engine will stamp it late enough to take effect")
    return out


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
        problems += _enum(rec, "status", GOAL_STATUSES, optional=True)
        problems += _enum(rec, "lifecycle_status", LIFECYCLE_STATUSES,
                          optional=True)
        if rec.get("status") is None and rec.get("lifecycle_status") is None:
            problems.append(
                "a goal needs a lifecycle: 'lifecycle_status' is one of "
                f"{', '.join(sorted(LIFECYCLE_STATUSES))}. A line written "
                "before the split may carry 'status' instead")
        problems += _enum(rec, "period", GOAL_PERIODS)
        problems += _enum(rec, "on_period_end", ON_PERIOD_END, optional=True)
        problems += _enum(rec, "set_by", AUTHORS, optional=True)
        problems += _enum(rec, "verification", VERIFICATIONS, optional=True)
        problems += _enum(rec, "deadline_kind", DEADLINE_KINDS, optional=True)
        problems += _enum(rec, "change_kind", CHANGE_KINDS, optional=True)
        problems += _enum(rec, "polarity", GOAL_POLARITIES, optional=True)
        problems += _band_problems(rec)
        problems += _floor_problems(rec)
        how = verification_of(rec)
        # An ATTESTED goal is the one case where a metric is not merely absent
        # but wrong to have. "I want to enjoy running again" is settled by the
        # athlete saying so and by nothing else, so a metric on it would be a
        # promise the engine cannot keep - it would start issuing verdicts on
        # a proxy nobody agreed was the goal (G86/G83).
        if how == ATTESTED:
            for k in ("metric", "target", "target_hi", "dataset", "session_type",
                      "period"):
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
                and _lifecycle(rec) == "active"):
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
        problems += _enum(rec, "outcome", EVENT_OUTCOMES, optional=True)
        problems += _validate_event_outcome(rec)
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
