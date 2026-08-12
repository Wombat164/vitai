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

from .clocks import (comparable, is_aware, is_stamp, order_key,  # noqa: F401
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
    # a field that names one joint can only ever describe that joint, and a
    # second site has nowhere to go. Old lines keep it and keep validating;
    # the engine reads them as pain at site "hip" (see `canonical_daily`), and
    # that is the ONLY place that mapping is written (#126). New lines write
    # `pain`/`pain_site` instead.
    #
    # WHAT THIS COMMENT USED TO SAY, recorded because the rule is easier to
    # follow with an instance attached: it named the injury a specific
    # person's, in a public repository, to explain a field. A schema comment
    # says what a field is and why it is retired. Whose body prompted it is a
    # fact about somebody, and it is not needed to read the code.
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
    # What an INSTRUMENT can and cannot measure, dated (#171).
    #
    # An instrument change is a confound that looks exactly like a
    # physiological one, and #33 shows the shape: a resting heart rate that
    # steps from 54 to 49 is either a training adaptation or a new optical
    # sensor. `origin` says which instrument observed a value and nothing said
    # what that instrument is competent at.
    #
    # CATEGORICAL, NEVER A NUMBER, which is this issue's own finding after
    # surveying what vendors publish: only power meters publish anything, those
    # cover the random term alone, field observation contradicts them by up to
    # twenty percent, and one vendor's marketed tolerance is half its own
    # service tolerance. A borrowed figure would be a confident wrong number
    # about confidence.
    #
    # KEYED ON `origin`, the identity the engine already uses for an
    # instrument - 27 call sites across `provenance`, `resolution`, `db` and
    # `query`. A device REGISTER (#311) later gives that string an entity with
    # an interval; this enriches the same identity rather than inventing a
    # second one.
    "capabilities": ["date", "origin", "measures", "competence", "construct",
                     "condition", "basis", "set_by", "note", "supersedes",
                     "recorded_at", "device"],
    # The ENTITY behind that identity (#311). `capabilities` says what an
    # instrument is competent at; this says what the instrument IS, and for
    # which stretch of time.
    #
    # NAMED FOR WHAT IT REGISTERS, and the issue's own word for it could not
    # be used. `device` is taken: it is on every dataset and names the MACHINE
    # THAT WROTE THE LINE DOWN (#105), which is the axis `source` and `origin`
    # are deliberately kept apart from - see the block below, which says that
    # conflating them "would make a phone and a laptop look like two
    # instruments". A `devices` dataset holding observing instruments would
    # manufacture exactly the confound this one exists to remove, under a name
    # promising the opposite.
    #
    # AN INTERVAL, NOT A ROW, which is the part most likely to be built wrong.
    # The join is not `origin -> instrument`, it is `(origin, date) ->
    # the instrument as it was then`. "My watch" in 2026 and "my watch" in
    # 2030 are different objects, and a lookup on the identity alone
    # attributes every historical reading to whatever is on the wrist now -
    # silently confident, wrong at the edges, invisible until someone checks
    # an old figure. `to_date` is open, because an instrument still in use has
    # no end date and inventing one would date its retirement to today.
    #
    # EVERYTHING OPTIONAL BUT THE IDENTITY AND THE START. A register that
    # demands nine fields per instrument decays to nothing within a year, and
    # then its coverage is patchy in a way nobody can see. One line is a
    # useful register; an unregistered origin resolves to nothing and reads
    # exactly as it does today.
    "instruments": ["date", "origin", "from_date", "to_date", "name", "maker",
                    "model", "source", "note", "supersedes", "recorded_at",
                    "device"],
    # Comparability EARNED BY OVERLAP, never asserted (#33 item 2, #171
    # section 4.1). The default is NOT COMPARABLE: deriving a trend across a
    # source change needs an explicit statement that the two sides are on
    # the same footing, never an assumption because both are called weight.
    #
    # A STATEMENT IN THE RECORD, keyed on a pair of instruments and a field,
    # whose only legal basis is an overlap OBSERVED IN THIS RECORD - a
    # period of simultaneous measurement from both instruments. Keyed on
    # `origin`, not "system": `origin` is the identity `capabilities` above
    # already keys on and 27 call sites already use for an instrument, and a
    # comparability statement is about that same identity on two rows.
    #
    # `status` is `comparable`, `offset` or `not_comparable`. An `offset`
    # row records that a cross-instrument difference was MEASURED and how
    # big it was; it is not a licence to apply that number to a reading,
    # which would be fabricating a measurement (P4) - the seam refusal (#33
    # item 3) lifts only for `comparable`, never for `offset`. `bias` and
    # `spread` are BOTH required beside `offset` (an offset with a measured
    # size and no reported spread is a number with no idea how firm it is,
    # and #171 settled that both are owed) - the same required-beside/
    # forbidden-beside shape `_capability_problems` already uses for
    # `construct`.
    #
    # THE TWO ARE NOT SYMMETRIC BESIDE `comparable`, and that is deliberate
    # rather than an oversight the way it read before this was reasoned
    # through (#373 review). `bias` beside `comparable` is a contradiction -
    # a MEASURED bias means the two instruments read differently by a known
    # amount, which is what `offset` is for, and forbidden here for the same
    # reason it is forbidden beside `not_comparable`: a number contradicting
    # its own status is a number about nothing. `spread` beside `comparable`
    # is not a contradiction - it says how tightly the two agreed over the
    # overlap, which is meaningful evidence about a pair the record has
    # already called comparable - so it stays permitted, and forbidden only
    # beside `not_comparable`, where nothing was measured to have a spread.
    #
    # `basis` is `overlap` and ONLY `overlap` - a closed vocabulary of one
    # value, because the whole point is that this cannot be asserted from a
    # datasheet, a vendor figure or an athlete's say-so. `overlap_ref` names
    # the period the overlap was observed in, required whenever `status`
    # says anything but silence (`comparable` or `offset`) - a `not_comparable`
    # row may be a bare refusal, since asserting a negative earns nothing.
    #
    # IDENTITY IS THE PAIR, resolved as unordered rather than stored that
    # way: `origin_a`/`origin_b` are two ordinary columns, and the resolver
    # in `policy.comparability` answers (a, b) and (b, a) identically, since
    # asking whether two instruments agree is one question regardless of
    # which one is named first. Two rows recorded with the origins swapped
    # are two independent identities as far as `supersedes` is concerned -
    # the resolver, not storage, is where the two are reconciled.
    "comparability": ["date", "field", "origin_a", "origin_b", "status",
                      "bias", "spread", "basis", "overlap_ref", "note",
                      "source", "supersedes", "recorded_at", "device"],
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
    # `rest_s` IS THE REST AFTER THIS SET, and this is the only place that says
    # so (#225). It was stated once, in a swimming aside in `exercises.toml` -
    # "the rest before the next is `rest_s`" - which is the same rule from the
    # other side and is a sport-specific comment doing a schema's job. A
    # direction nothing states is one two importers settle differently: the
    # same rest interval attaches to set 3 for one and set 4 for the other, and
    # the rows validate identically either way.
    #
    # AFTER rather than BEFORE, because it is what the athlete observes. The
    # set ends, the clock runs, the next one starts; a rest recorded before a
    # set cannot be known when that set's row is written. It also makes the
    # LAST set's `rest_s` meaningful - the rest before the next exercise - where
    # a before-rule would leave the first set of every block carrying a value
    # about a boundary it did not sit on.
    #
    # NOTHING READS IT YET, which is why this is a definition rather than a
    # change: `sets.py` validates it is a number and no consumer computes with
    # it. Stating the direction now costs nothing and stops the first consumer
    # inheriting an ambiguity that is invisible in the data.
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

# THE ONE COVERAGE VALUE THAT MEANS UNFINISHED. `full` and `manual` describe a
# day that was logged; only `partial` says the record knew there was more to
# come. Named rather than spelled at the reader, because a verdict turns on it
# (#186) and a literal in a comparison is how a vocabulary quietly grows a
# second spelling.
PARTIAL = "partial"

# WHAT AN INSTRUMENT IS COMPETENT AT (#171). Four values, and the issue is
# explicit that zero, unknown and wide are three different things and only one
# of them is a quantity:
#
#   measures  it observes this quantity, and the record has grounds to say so
#   proxy     it reports a DIFFERENT quantity under this name. A vendor's
#             resting heart rate observed running far above the continuous
#             nightly minimum is the live example: no uncertainty figure would
#             ever catch it, because every one of them assumes the right
#             quantity is being measured.
#   absent    it does not observe this at all, and a value under this name
#             came from somewhere else
#   unknown   nobody has said - and this is what SILENCE resolves to, which is
#             the whole of the #148 lesson. Baselines lived in a mutable file
#             outside the record, so a week with no dated row was judged by
#             whatever that file said today. A capability default in
#             `semantics/` would be the same defect one dataset over:
#             effective-dating that a default escapes is not effective-dating.
#             So there is no default. Silence resolves to a value IN the
#             vocabulary, which a consumer can see and act on.
# The coarse tier of a measurement's time (#212), from `semantics/day_phase.toml`.
# Adopted from Open mHealth's `part-of-day` rather than invented (G85).
#
# READ FROM THE REGISTRY rather than restated here, because `plans.for_phase`
# had the vocabulary HARDCODED INLINE in `api.py` as a sort key - three values,
# no registry entry, no validation, and a fourth value nobody could add without
# finding that line. A vocabulary that lives in one consumer is a vocabulary
# the next consumer invents again.
def day_phases() -> dict[str, dict]:
    """The part-of-day vocabulary, by slug."""
    from .vocab import registry

    return dict(registry("day_phase")["phase"])


COMPETENCES = {"measures", "proxy", "absent", "unknown"}
PROXY = "proxy"
UNKNOWN_COMPETENCE = "unknown"

# WHERE A CAPABILITY STATEMENT COMES FROM. Not a confidence score - a statement
# about how the claim was arrived at, so a reader can weigh it themselves.
#
# `overlap` is the one this engine can EARN: simultaneous dual recording, the
# established norm in the power-meter community. `stated` is the athlete or a
# manufacturer saying so, which is evidence and not measurement. `observed` is
# a pattern in this record short of a controlled overlap - the proxy case above
# was found that way.
#
# NO VENDOR FIGURES ANYWHERE, which this issue settled after surveying what is
# published: only power meters publish anything, those cover the random term
# alone, field observation contradicts them by up to twenty percent, and one
# vendor's marketed tolerance is half its own service tolerance.
CAPABILITY_BASES = {"overlap", "observed", "stated"}

# WHETHER TWO INSTRUMENTS' READINGS OF ONE FIELD CAN BE READ AS ONE SERIES
# (#33 item 2, #171 section 4.1). Three values, and only one of them is ever
# the answer silence resolves to:
#
#   comparable      the pair agrees closely enough that a series can span
#                    the seam between them
#   offset          a difference was MEASURED and how big it was is on the
#                    row; the two sides are still NOT one series - applying
#                    the number to a reading would be fabricating a
#                    measurement (P4), so this status still refuses a
#                    spanning derivation
#   not_comparable  nothing licenses treating the two as one series, stated
#                    or silent - and SILENCE RESOLVES HERE, never to
#                    `comparable`, which is the whole of #33's acceptance
#                    criterion
COMPARABLE, OFFSET, NOT_COMPARABLE = "comparable", "offset", "not_comparable"
COMPARABILITY_STATUSES = {COMPARABLE, OFFSET, NOT_COMPARABLE}

# THE ONLY LEGAL BASIS for a comparability row - a single value rather than a
# set, for the same reason `capabilities.basis` is a small vocabulary one
# tier stricter: comparability is earned by overlap or it is not earned.
# A row naming any other basis would be asserting comparability from a
# datasheet, an athlete's say-so or a vendor's marketing figure, which is
# exactly what this dataset exists to refuse - so nothing else validates.
OVERLAP_BASIS = "overlap"
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
    "meals": ("meal", "item"),
    # A capability statement is about one instrument measuring one thing under
    # one condition. All three are the identity: a watch can be competent at
    # steps and a proxy for sleep, and competent at heart rate seated while
    # only a proxy for it at threshold - so keying on the instrument alone
    # would make each new statement retire the last.
    "capabilities": ("origin", "measures", "condition"),
    # An instrument is one thing over one stretch of time, so the interval is
    # part of the identity: two watches that both reported as `garmin-watch`
    # are two rows, and neither retires the other.
    "instruments": ("origin", "from_date"),
    # A comparability statement is about a PAIR of instruments measuring one
    # field, and the pair - not either instrument alone - is the identity: a
    # scale can be declared comparable to a DEXA for `kg` and simultaneously
    # not comparable to a different scale for the same field, and both
    # statements have to survive independently. See `policy.comparability`
    # for why asking about the pair is ORDER-INSENSITIVE even though this
    # identity is not: two rows recorded with the origins swapped are two
    # independent identities here, and the resolver - not storage -
    # reconciles them.
    "comparability": ("field", "origin_a", "origin_b")}

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

# The severity ladder. `red_flag` is not a stronger adjective than `severe` -
# it is the only value on this ladder the ENGINE itself reads. Everything else
# here is written for a coach to weigh; `red_flag` is compared directly in
# `safety.py` and fires a hardcoded URGENT escalation that no coaching logic
# can trade against a training goal, on the affected activity. What the reader
# does with it is theirs: the field records that the engine has stopped
# programming there, not what anyone should do next. The engine has its own
# independent red-flag triggers too, so an LLM can only ever ADD an
# escalation, never remove one.
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

# --- G89 PART TWO, AS DATA: a retirement either maps forward or it does not ---
#
# The README's migration table, and the wiki reference beside it, both said
# `sessions.location` is read forward as `place`/`route` "the same as"
# `hip_pain` is read as `pain`. Nothing reads it forward. Nothing was lying:
# two retirements were assumed to be one kind of event, and only one of them
# is.
#
# A RENAME AND A SPLIT ARE DIFFERENT ANIMALS. `hip_pain` -> `pain` is a rename
# that widened: the old value is EXACTLY a valid new value, and site "hip" is
# recovered from the field's own name. `location` -> `place` + `route` is a
# split into different types, and the old value is a valid value of NEITHER -
# which is the entire reason the split happened. Free text could not be
# grouped or compared. And which successor a given string belongs in is a
# judgement, not a lookup: "canal path" could be either, and only the athlete
# knows.
#
# THE EGRESS ARGUMENT, STATED PRECISELY because a loose version of it is
# wrong. Free text in `location` is not hidden - it is a projected column and
# a consumer querying the table gets it. What mapping would change is WHICH
# field holds it: `place` is the coarse tier `coarse()` emits by default
# (#205), the one a caller reaches for when it wants the safe form. Free text
# is legible as free text under its own retired name; the same string under
# `place` is a coarse value by assertion. Moving it is not concealment either
# way - it is putting an unvetted string in the field whose contract is that
# it has been vetted.
#
# So for a split the honest answer is that nothing maps it, said out loud
# rather than left to be found by grep. Data, not prose, because prose is
# exactly what no check could contradict.
#
# EVERY ENTRY NAMES A CALLABLE, and the test reads its source for the retired
# key. Naming a table was the first version and it cannot be checked: any
# existing attribute satisfies a `hasattr`, so a future retirement could be
# registered as mapped, gate off the tripwire below, and recreate the silent
# drop with the register certifying it.
KEY_FORWARD: dict[str, dict[str, str]] = {
    "daily": {"hip_pain": "resolution.canonical_daily"},
    "goals": {"status": "policy.lifecycle_of"},
}

# The other kind. Each carries WHY nothing maps it and WHAT the athlete does
# instead, and the second is not boilerplate: the two terminal retirements
# here need opposite advice, and one message for both told the `planned` case
# to append a corrected session line, which is not where its successor lives.
TERMINAL_RETIREMENT: dict[str, dict[str, tuple[str, str]]] = {
    "sessions": {
        "location": (
            "split into `place` and `route`, which are different types rather "
            "than new spellings; free text is a valid value of neither, and "
            "choosing between them is the athlete's judgement, not a lookup",
            "append corrected session lines carrying `place`, `route` or "
            "both - the engine will not choose for you"),
        "planned": (
            "the successor points the other way (#221) - a plan is the object "
            "and a session cites it - so there is nothing on a session row "
            "for a forward map to write to",
            "append `plans` rows for the plans that were followed, each "
            "citing its session through `session_ref`"),
    },
}


def forward_map_for(dataset: str, key: str) -> str | None:
    """Who reads `key` forward, or None where nothing does and nothing should.

    None is an ANSWER here, not a gap. `terminal_retirement` says why.
    """
    return KEY_FORWARD.get(dataset, {}).get(key)


def terminal_retirement(dataset: str, key: str) -> tuple[str, str] | None:
    """Why this retired key is never read forward, and what to do instead."""
    return TERMINAL_RETIREMENT.get(dataset, {}).get(key)

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

# --- who computed it (#280) ---------------------------------------------------
#
# `derived_external` says the value was NOT computed by this engine and stops
# there, which was enough when there was one consumer. #158 settled that there
# are three consumption modes and that several clients will read one record on
# the same terms - and any of them may derive. Two clients computing a pace
# from `duration_s` and `distance_km` agree when both are right and differ when
# one has a bug, and the record could not tell them apart.
#
# The engine already takes this seriously where it controls it: `inferences`
# carries `model`, because WHICH model produced an inference is part of what
# the inference is. The same argument reaches a client that derives.
#
# TWO FIELDS, NOT A SLUG. `client-0.1.0-a3f2` crams orthogonal facts into one
# identifier a consumer then has to parse, which is the pre-coordination this
# schema refuses everywhere else. `derived_by` is what did the computing;
# `derived_build` is which build of it, and it is the half that makes a
# derivation auditable - a figure from version 0.1 and the same figure from
# 0.2 after the bug was fixed are different facts.
#
# NO INSTALL IDENTIFIER, and this is a decision rather than an omission. The
# issue raises it and answers itself: a stable per-install id is useful to the
# record and is also a tracking key. It answers no question a coach is asked,
# `device` already says which machine wrote a line down, and admitting it would
# need a rule about where it may travel - which is #205's two-tier work, not a
# field added in passing. Refusing is the reversible direction.
#
# `by-hand` IS A REAL VALUE, and the corpus is why. The single
# `derived_external` row in every fixture this repo ships is an athlete taking
# a mean of two weigh-ins ON PAPER. A field that could only name software
# would have had nothing to put there, and the absence would then have meant
# both "a person did it" and "software did it and did not say".
DERIVED_BY_HAND = "by-hand"

# THE KEYS ARE ADDED HERE AND THEIR GENERATION IS ASSIGNED AT THE END (#295).
# `KEYS` order is the read model's COLUMN order, so it stays exactly where it
# was; the generation NUMBER is what had to move, because it is assigned by
# file order and this block sits above two that already existed. See the note
# at the end of this section.
DERIVED_LINEAGE_DATASETS = ("weight", "daily", "sessions", "measurements",
                            "sets", "meals")
for _ds in DERIVED_LINEAGE_DATASETS:
    for _k in ("derived_by", "derived_build"):
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

# --- a generation is APPENDED, never inserted (#295) --------------------------
#
# `derived_by` and `derived_build` (#280) belong to the narrative several
# hundred lines above; their bump lives here, and the separation is the fix.
#
# A dataset's generation is how many bump blocks appear ABOVE a point in this
# file, and `_gen` is stamped into a line at append time and never rewritten -
# correctly, because it is a fact about what the schema was when the line was
# written. Put a new block above an existing one and every generation below it
# shifts up by one, so a number already sitting in a record starts denoting a
# LATER schema state than the one it was stamped under. G25's exemption,
# `line_generation(rec) < key_generation(...)`, then reads a line as owing a
# key that did not exist when it was written.
#
# That is what happened, and the failure was SILENT AND RETROACTIVE: nothing
# broke when the change merged, the record was correct, the engine was
# correct, and the two disagreed only when a reader compared them. On a real
# record it was 280 problems across 140 lines, none of them about the
# contents. And the remedy was unavailable - `_gen` cannot be rewritten, and
# appending corrections would restate hundreds of rows to absorb a numbering
# choice that was not the record's mistake.
#
# So the NUMBER moved down to where it belongs in merge order, which restores
# every one of the FIFTEEN numbers it moved - fourteen key generations and one
# RETIREMENT, `sessions.planned`, which shifts by the same mechanism and is the
# easiest of the fifteen to forget, because nothing about it looks like a key.
# Only the number: the keys are still appended to `KEYS` where they were,
# because that order is the read model's column order and moving it would be a
# consumer-visible change made in passing while fixing something else.
#
# WHY THIS IS SAFE FOR RECORDS ALREADY WRITTEN, argued on the right half. It is
# tempting to say that raising a generation only ever exempts more lines and
# therefore nothing can break. Relative to the engine that is deployed most of
# these numbers go DOWN, so that argument covers the wrong direction.
#
# The real one is an enumeration. Every `_gen` value reachable in the window
# between the insertion and this repair was stamped by an engine whose `KEYS`
# already contained these keys, so every line written in that window CARRIES
# what it now owes. Lines older than the window are exempt again. There is no
# reachable stamp left holding a line to a key it could not have had, and that
# is checked rather than asserted - `test_generation_numbering.py` builds the
# row shape each engine state could have produced and validates all of them.
#
# That file also pins the whole table, retirements included, so the next
# insertion fails at the point of insertion with the moved numbers named,
# rather than surfacing weeks later as a report about somebody's record.
for _ds in DERIVED_LINEAGE_DATASETS:
    CURRENT_GENERATION[_ds] += 1
    for _k in ("derived_by", "derived_build"):
        KEY_GENERATION.setdefault(_ds, {})[_k] = CURRENT_GENERATION[_ds]


# --- two tiers, and the coarse one is the default egress form (#205) ----------
#
# THE STANCE THAT CHANGES. The comment on `sessions` above says `place` is
# "coarse, and deliberately coarse - 'home'/'work'/a travel slug, never an
# address". That was privacy by not storing the thing: blunt, and it throws
# away real utility, because "outdoors" cannot tell the park an athlete likes
# from the one they avoid. `place` keeps that meaning and keeps its name.
# `place_precise` is the tier beside it, as precise as the athlete wants, and
# the sentence above is restated here rather than left contradicting the code.
#
# THE COARSE VALUE IS REQUIRED, NOT DERIVED, and the difference is worth being
# straight about. #205 asks for the coarse tier to be computed at append so
# that no read path can fail to produce one. For a numeric precise tier that
# is arithmetic and the engine could do it. For an address it is not: reducing
# "12 Some Street" to "home" needs either a lookup, which the build forbids,
# or a mapping only the athlete holds. So the engine refuses a precise value
# that arrives without its coarse companion, which buys the same invariant -
# a coarse answer exists for every precise one - without the engine
# pretending to a derivation it cannot perform. Guessed coarse values would be
# worse than none: they would be wrong in the direction of looking right.
#
# WHAT THIS COSTS, recorded rather than discovered. Storing the precise value
# creates a liability that not storing it did not. A precise value that leaks
# cannot be un-leaked, and the record's old stance was safe precisely because
# there was nothing to leak. This raises the claim from "we do not hold this"
# to "we hold it and it does not escape", which is a much stronger claim and
# has to actually hold - which is why the boundary and its controls are part
# of the same change rather than a follow-up.
#
# SENSITIVE maps dataset -> {precise key: the coarse key it must travel with}.
# Not a property of the dataset and not a property of the consumer: a field is
# sensitive or it is not, and every consumer gets the coarse tier unless it
# asked for the other one by name.
SENSITIVE: dict[str, dict[str, str]] = {}
for _ds in ("sessions", "context"):
    CURRENT_GENERATION[_ds] += 1
    KEYS[_ds] = KEYS[_ds] + ["place_precise"]
    KEY_GENERATION.setdefault(_ds, {})["place_precise"] = CURRENT_GENERATION[_ds]
    SENSITIVE[_ds] = {"place_precise": "place"}

PRECISE_KEYS: frozenset[str] = frozenset(
    k for pairs in SENSITIVE.values() for k in pairs)


def precise_keys(dataset: str) -> tuple[str, ...]:
    """The sensitive keys on a dataset, in KEYS order."""
    return tuple(k for k in KEYS.get(dataset, ()) if k in SENSITIVE.get(dataset, {}))


def coarse(dataset: str, rec: dict) -> dict:
    """One row with its precise tier absent.

    A NEW DICT EVERY TIME, never a mutation of the caller's. The engine's own
    arithmetic reads the same objects a consumer does, so coarsening in place
    would quietly change what the build computes over.

    The key is DROPPED rather than nulled, and on KEY PRESENCE rather than on
    the value being set. A null would be indistinguishable from an athlete who
    never wrote one, which is the difference between "you are not being shown
    this" and "there is nothing here" - and the engine writes null for a key it
    does not know rather than omitting it, so the null shape is the one a real
    row is likelier to carry.

    ALWAYS A COPY, including when there is nothing to drop. Returning the
    caller's own object for the untouched case was the obvious optimisation
    and it made the guarantee false: the coarse and precise caches then held
    THE SAME dicts for every row without a precise key, which is most of any
    record, so a consumer that took the precise view and annotated its rows -
    which is the consumer this path exists for - planted the value into the
    default projection for every later reader of that instance. Structurally
    cannot means structurally cannot.
    """
    drop = SENSITIVE.get(dataset)
    if not drop:
        # A COPY HERE TOO, and this branch is why the guarantee above was only
        # three quarters true. Eighteen of the twenty datasets have no
        # sensitive field at all, so this is the branch nearly every row takes,
        # and it returned the caller's own object - reinstating for `weight`
        # and `daily` exactly the sharing the comment above says structurally
        # cannot happen. `precise()` takes any dataset name, so both views of
        # `weight` handed back the same dicts and a consumer annotating one
        # wrote into the other.
        #
        # Nothing sensitive escaped, because a dataset in this branch has no
        # precise tier to escape. What was false was the guarantee, and a
        # guarantee that holds on the datasets somebody was thinking about is
        # the per-caller gate this whole feature exists to replace.
        return dict(rec)
    return {k: v for k, v in rec.items() if k not in drop}


def _sensitive_problems(dataset: str, rec: dict) -> list[str]:
    """A precise value with no coarse answer beside it (#205)."""
    out = []
    for precise, plain in SENSITIVE.get(dataset, {}).items():
        # NO GENERATION GUARD, and its absence is the decision. The obvious
        # shape here is the G25 skip every other new key gets - an older line
        # never owed it - and that skip is exactly wrong for this rule. It
        # fires only when the precise field HAS A VALUE, and a line carrying a
        # value was written by something that knew the field existed. The
        # guard would have let a line stamped with an old `_gen` carry an
        # address with no coarse answer beside it and pass, which is the one
        # row this rule exists to refuse. G25 still holds: a line without the
        # field is not touched here at all.
        if str(rec.get(precise) or "").strip() and not str(
                rec.get(plain) or "").strip():
            out.append(
                f"'{precise}' is the precise tier and needs '{plain}' beside "
                f"it. Everything that leaves this record sees the coarse "
                f"value, so a precise one with no coarse answer is a row that "
                f"cannot be shown to anybody at all")
    return out


# --- naming one row of several that share a key (#239) ------------------------
#
# `line_key` falls back to `<date>/<source>`, so two runs on one day from one
# watch share a name. Measured on a live record that was the ordinary case
# rather than an edge: 71 per cent of sessions and 93 per cent of journal rows
# shared a key with something.
#
# Contract 33 fixed what a reference RETIRES - one reference takes ONE other
# row, the most recent, which is what a correction written straight afterwards
# means. What stayed broken is naming an EARLIER one, and the cost is concrete:
# five rows of one key written as a chain cannot be repaired by appending at
# all. A reference retires the most recent; a second append naming the same key
# retires the FIRST APPEND rather than the next row down; and editing in place
# is what append-only forbids. Three of those five rows are unreachable by any
# sequence of writes.
#
# READ-TIME ORDINALS WERE BUILT AND REJECTED, and `test_line_keys.py` keeps the
# reproduction. Positions in the merged order renumber when a device syncs a
# row stamped earlier, so a reference written last week names a different row
# and something already retired comes back. What works is a position STORED on
# the row, the way `sets` carries `set_index`.
#
# ONLY WHERE THE KEY CAN COLLIDE. The identity-keyed datasets already name a
# row by a slug or a tuple, and `emissions` never retires at all, so a position
# there would be a column that answers nothing.
SEQUENCED = tuple(d for d in KEYS
                  if d not in IDENTITY_KEY and d != "emissions")
for _ds in SEQUENCED:
    # EVERY DATASET BUMPS, INCLUDING THE ONES STILL AT GENERATION ONE. The
    # first cut skipped those, reasoning that a dataset nothing has written
    # yet has no lines in the wild, so `seq` could be founding there.
    #
    # That is an assertion about somebody else's record, and it is not this
    # engine's to make. `regimes` is written by no fixture here and may be
    # written in a record I cannot see - and registering `seq` at generation 1
    # makes G25's exemption, `line_generation < key_generation`, false for
    # every line that could exist, so each one is held to a key that postdates
    # it. That is #295's failure mode exactly, committed while fixing #295's
    # neighbour.
    #
    # Bumping is free and the direction is the safe one: a key registered
    # above the founding generation can only ever EXEMPT more lines.
    CURRENT_GENERATION[_ds] += 1
    KEYS[_ds] = KEYS[_ds] + ["seq"]
    KEY_GENERATION.setdefault(_ds, {})["seq"] = CURRENT_GENERATION[_ds]

# --- a class per field, published (#299) ---------------------------------------
#
# A client that gates egress needs to know which fields are sensitive and how.
# It cannot ask, so it keeps a copy of this schema, and the copy is wrong the
# day a field is added here. Worse than wrong: the copy's fallback gives an
# unknown field the MOST PERMISSIVE class, so a field added here ships to every
# recipient the day it appears and the release log files it under the
# permissive class, which makes the leak invisible to a careful reader.
#
# A PER-FIELD-NAME MAP CANNOT BE RIGHT, and that is not a quality problem with
# the copy. `reason` appears on five datasets. On four it is free prose about
# why a policy changed. On `plans` it is the COM-B axis - `motivation_automatic`,
# `capability_physical`, `declined` - which is a claim about why somebody did
# not train, and is arguably the most sensitive field in the record. One name,
# two disclosures, and no map keyed on the name alone can say both.
#
# So the classification is per (dataset, field): a default by name, where a
# name means one thing everywhere, and an override where it does not.
#
# THE CLASSES ARE THE ENGINE'S FIRST ANSWER, and they are a judgement rather
# than a fact. What makes publishing them better than a consumer guessing is
# not that they are certainly right: it is that they are wrong in ONE place,
# reviewable, and cannot silently default.
SENSITIVITY_CLASSES = frozenset({
    "clinical",      # health state, injury, symptom, what it restricts
    "behavioural",   # why somebody did or did not do a thing; mood, intake
    "whereabouts",   # where the athlete is, was, or goes, and who with
    "narrative",     # free text somebody wrote
    "provenance",    # what observed a value, what relayed it, what wrote it
    "reference",     # slugs, keys, closed vocabularies, links between rows
    "measurement",   # the quantities
    "temporal",      # when
})

_BY_NAME: dict[str, str] = {}
for _cls, _names in {
    "temporal": """date recorded_at measured_at start_time captured_at
        occurred_date onset_date resolved_date event_date for_date from_date
        to_date week session_start sleep_start sleep_end deadline policy_asof
        for_phase""",
    "clinical": """body_site body_side severity restricts restriction
        precondition expects pain pain_site pain_side hip_pain
        provider_type""",
    "behavioural": """mood feel motivator rationale accountability alcohol
        coverage""",
    "whereabouts": """place place_precise location route track with facilities
        setting weather context""",
    "provenance": """source device origin path origin_evidence activity_id
        activity_source read_by capture derived_by derived_build derived_from
        derived_op modelled type_source model confidence evidence surface
        machine equipment tracker food_table protocol
        competence construct basis origin_a origin_b""",
    "narrative": """note text title statement about reason""",
    "reference": """slug key dataset field session_ref anchored_by goal event
        metric basis_claims depends_on supersedes contract sha256 media_type
        artifact exercise item meal block round set_index type session_type
        kind status outcome tier change_kind lifecycle_status polarity policy
        period verification deadline_kind set_by serves requires on_miss
        on_success on_period_end priority immovable removed result mode
        planned load_type load_unit set_type failure angle_class side
        rpe_scale mood_scale pain_scale activity
        seq supersedes_seq measures condition overlap_ref""",
    "measurement": """avg_power steps distance_km active_min kcal_out kcal_in
        protein_g
        sleep_h rhr kg body_fat_pct kg_lo kg_hi body_fat_lo body_fat_hi avg_hr
        max_hr cadence kcal elevation_m rpe duration_s rest_s rir load
        reps_attempted reps_completed value target target_hi guard_pct
        angle_deg lever_pos pad_pos seat_pos resistance_level tempo grams
        grams_lo grams_hi kcal_100g protein_100g carb_100g fat_100g fibre_100g
        sugar_100g sodium_mg_100g carb_g fat_g fibre_g sugar_g sodium_mg
        bytes bias spread""",
}.items():
    for _name in _names.split():
        _BY_NAME[_name] = _cls

# WHERE ONE NAME MEANS TWO THINGS. Small on purpose: an override is a place the
# name stopped carrying the meaning, and a long list of them would say the
# names are wrong rather than that this dataset is unusual.
SENSITIVITY_OVERRIDE: dict[str, dict[str, str]] = {
    # The COM-B axis, and the case that proves a per-name map cannot work.
    "plans": {"reason": "behavioural"},
    # Free text ABOUT an injury is not the same disclosure as free text about
    # a route, and neither is the closed vocabulary that says which injury.
    "medical": {"title": "clinical", "note": "clinical", "kind": "clinical",
                "status": "clinical"},
    # What a thing IS that observed a value, which is provenance - the same
    # class `origin`, `device` and `model` already carry. Scoped here rather
    # than added to the shared name map: `name` is the ambiguous one, since a
    # dataset naming a PERSON would want a different answer entirely, and a
    # global entry would hand that dataset a wrong class silently instead of
    # stopping it at this gate the way it stopped this one.
    "instruments": {"name": "provenance", "maker": "provenance"},
}


def units(dataset: str, field: str) -> dict:
    """What a field holds, as data rather than as a naming convention (#310).

    Returns `{}` for a field with no quantity - a date, a slug, a note - and
    otherwise a dict carrying `label` plus exactly ONE of:

      `ucum`      a fixed UCUM code, the same in every row
      `scale`     a named ordinal scale, which has no unit at all
      `unit_of`   the name of the FIELD whose units this takes
      `scale_of`  the name of the field naming this row's scale

    A CODE, NEVER A CONVERSION. UCUM is registry data here, the way FHIR binds
    `Quantity.code` and IEEE 1752 uses it; converting between units needs a
    runtime dependency this engine does not ship, and it is the consumer's
    arithmetic anyway. Publishing the code is a statement about the record;
    performing the conversion would be a claim about the world.
    """
    from .vocab import registry

    table = registry("units")
    entry = (table.get("override", {}).get(dataset, {}).get(field)
             or table.get("unit", {}).get(field))
    if not entry:
        return {}
    # `aliases` shares this table because both are facts about the same field
    # and one file is easier to keep right than two. It is published under its
    # own key, not inside this one: a unit is what the number is in, and an
    # alias is what a person calls it, and a consumer switching on the first
    # should not have to step over the second.
    return {k: v for k, v in entry.items() if k != "aliases"}


def aliases_for(field: str) -> list[str]:
    """The words a person uses for this field, or an empty list.

    ABOUT ENGLISH, and derivable from nothing. Nobody asks how their rhr was,
    and a client that hand-maintains this map is maintaining a copy of the
    engine's vocabulary that fails silently when it drifts: a question naming a
    metric the list has forgotten matches no topic at all.
    """
    from .vocab import registry

    entry = registry("units").get("unit", {}).get(field) or {}
    return [str(a) for a in entry.get("aliases") or []]


# The tokens a field name can carry that a person does not say out loud. A
# field whose name contains one of these needs a curated display name, and
# `test_display_names.py` fails the build if it does not have one - which is
# what stops the next `sleep_h` shipping as "sleep h".
# THE WORDS DERIVATION MAY PASS THROUGH, and this replaced a denylist.
#
# The first version listed what to REJECT - abbreviations - and review killed
# it with the PR's own headline example: `power_w` sailed straight through,
# because "w" was not on a list I had built by auditing the fields that
# already exist. A denylist derived from today's field set is by construction
# a list of what you already have. It cannot catch the next field, which is
# the only thing a gate is for.
#
# So this is an allowlist and it fails CLOSED. A new field introduces a token
# nobody has blessed, and the gate stops the build until someone either
# curates a display name for the field or adds the word here on purpose.
# `power_w`, `hrv_ms`, `temp_c`, `bp_sys`, `one_rm` and `ts_utc` all fail now;
# under the denylist fourteen of twenty plausible next fields passed.
#
# Being long is the point rather than a cost: every entry is a word somebody
# decided a person would read, and the list only grows by that decision.
PLAIN_WORDS = frozenset({
    # #171's dataset. Four ordinary words a person reads as themselves, added
    # deliberately because this is an ALLOWLIST: a new field fails the gate
    # until somebody says what it looks like at a reader.
    "competence", "condition", "construct", "measures",
    # #311's register. `model` and `origin` were already here; these two are
    # the rest of what a person calls a piece of kit.
    "maker", "name",
    # #33 item 2: the comparability dataset. Two ordinary words a person
    # reads as themselves.
    "bias", "spread",
    "about", "accountability", "activity", "alcohol", "anchored",
    "angle", "artifact", "at", "attempted", "basis", "block", "body",
    "build", "by", "bytes", "cadence", "capture", "captured", "change",
    "claims", "class", "completed", "confidence", "context", "contract",
    "coverage", "dataset", "date", "deadline", "depends", "derived",
    "device", "end", "equipment", "event", "evidence", "exercise",
    "expects", "facilities", "failure", "feel", "field", "food", "for",
    "from", "goal", "grams", "hip", "immovable", "index", "item", "key",
    "kind", "level", "lifecycle", "load", "location", "machine", "meal",
    "measured", "media", "metric", "miss", "mode", "model", "modelled",
    "mood", "motivator", "note", "occurred", "on", "onset", "origin",
    "outcome", "pain", "path", "period", "phase", "place", "planned",
    "polarity", "policy", "precondition", "priority", "protocol",
    "provider", "rationale", "read", "reason", "recorded", "removed",
    "reps", "requires", "resistance", "resolved", "restriction",
    "restricts", "result", "round", "route", "scale", "serves",
    "session", "set", "setting", "severity", "side", "site", "sleep",
    "source", "start", "statement", "status", "steps", "success",
    "supersedes", "surface", "table", "target", "tempo", "text", "tier",
    "time", "title", "track", "tracker", "type", "unit", "value",
    "verification", "weather", "week",
})


def display_name(dataset: str, field: str) -> str:
    """What to call this field on a surface a person reads (#331).

    NOT `aliases`, which is for RECOGNITION - it is what makes "resting heart
    rate" verify against `rhr`, and it is right for that. It is a SET, and no
    end of it is a display name: every word in it was chosen to be matched
    rather than printed, so `kcal_out` yields "calories out" in registry order
    and "burned" sorted, and `rir` yields the raw token or "left in the tank".

    NOT `units(...)["label"]` either, though the issue proposed it as the
    precedent. That label names the UNIT: `kcal_in` and `kcal_out` both answer
    "kilocalories", so a consumer using it would show two different fields the
    same word, and 306 of the engine's fields have no units entry at all.

    DERIVED WHERE DERIVATION IS HONEST, curated where it is not. Softening
    underscores is right for most field names - `pain_site` is "pain site" -
    and hand-writing those would be a second copy of the field list, which is
    the duplication this engine exists to prevent. What derivation cannot do
    is expand an abbreviation or a unit suffix, so those are registry data,
    and a gate refuses a new abbreviated field that has no entry.

    NO DATASET-SCOPED OVERRIDE, and the first version shipped one that could
    not be reached. The docstring advertised `[override.<dataset>.<field>]`
    while the code read `name_override`, so the documented shape was silently
    ignored and the implemented shape failed the registry's own table register
    - and deleting the branch entirely passed the whole suite. No field needs
    it today; when one does, it can arrive with a test.
    """
    from .vocab import registry

    table = registry("units")
    named = table.get("name", {}).get(field)
    if named:
        return str(named)
    return field.replace("_", " ")


def sensitivity(dataset: str, field: str) -> str:
    """The class this field belongs to. RAISES on one nobody has classified.

    NO DEFAULT, and that is the whole point rather than a strictness. The
    failure this exists to remove is a fallback standing in for a decision
    nobody made: a consumer's map gave an unknown field its most permissive
    class, so a field added here left the machine the day it appeared. A
    default here would move that failure one layer in and make it the
    engine's.

    #297 pinned the founding key set for the same reason - an unregistered key
    caught rather than defaulted - and `test_sensitivity.py` pins every pair,
    so a field added tomorrow fails at the point it is added.
    """
    if field in SENSITIVITY_OVERRIDE.get(dataset, {}):
        return SENSITIVITY_OVERRIDE[dataset][field]
    if field in _BY_NAME:
        return _BY_NAME[field]
    raise KeyError(
        f"{dataset}.{field} has no sensitivity class. A field with no class "
        f"cannot be gated, and defaulting one is how an unknown field ships "
        f"to everybody: classify it in `_BY_NAME`, or in "
        f"`SENSITIVITY_OVERRIDE[{dataset!r}]` if the name means something "
        f"different here than it does elsewhere (#299)")


# --- the measurement rather than the estimate (#91) ----------------------------
#
# `sessions` carries `cadence` and had nowhere to put watts, so any FIT ingest
# had to discard the one channel that is a MEASUREMENT rather than a vendor
# estimate. Everything else on a cycling row is modelled somewhere: `kcal` is
# an estimate from heart rate and mass, `distance_km` from wheel size or GPS.
# Power is read from a strain gauge.
#
# `avg_power` RATHER THAN `power`, which is what the issue asks for, and the
# deviation is small enough to state and reverse. A bare `power` is ambiguous
# between average, maximum and NORMALISED power, and normalised is the number
# cyclists actually quote - so half its readers would take it for one and half
# for the other, which is the pre-coordination this schema refuses elsewhere.
# `cadence` is bare and means the average, and it is the odd one out rather
# than the precedent to follow.
#
# NO `max_power` and no normalised power. Max is a spike a consumer can take
# from the track where one exists, and normalised power is a WEIGHTED
# derivation with a published algorithm and a rolling window - a figure this
# engine would be computing rather than recording, which is a different kind
# of field and wants deciding rather than adding in passing.
CURRENT_GENERATION["sessions"] += 1
KEYS["sessions"] = KEYS["sessions"] + ["avg_power"]
KEY_GENERATION.setdefault("sessions", {})["avg_power"] = \
    CURRENT_GENERATION["sessions"]


def key_generation(dataset: str, key: str) -> int:
    """Generation a key was introduced in (1 = founding)."""
    return KEY_GENERATION.get(dataset, {}).get(key, 1)


def key_retirement(dataset: str, key: str) -> int | None:
    """Generation a key stopped being required, or None if it is still current."""
    return KEY_RETIREMENT.get(dataset, {}).get(key)


def is_number(value: object) -> bool:
    """A real number the engine will compute with - and `True` is not one.

    ONE DEFINITION, and it was three, found by sweeping for duplicated bodies.
    `query`, `resolution` and `safety` each carried a byte-identical private
    copy, and `safety`'s decides whether a pain score reaches a gate. Three
    copies of a predicate do not disagree on the day they are written; they
    disagree the first time one of them learns something - a numeric string
    from an importer, say - and then a value is a number to the gate and not to
    the ladder, or the other way round.

    `bool` IS EXCLUDED, which is the whole reason this is a function rather
    than an `isinstance` call at each site. In Python `True` is an `int`, so a
    field carrying `true` would otherwise arrive at a threshold comparison as
    the number one, and `pain: true` would read as pain of 1 rather than as
    the type error it is.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
    "max_hr": (int,), "cadence": (int,), "avg_power": (int,),
    "kcal": _NUMERIC,
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
    # #373 review: neither was type-checked, so 'spread: "banana"' validated
    # clean beside a required-ness check that only asked whether the key was
    # present. Registered here rather than hand-rolled in
    # `_comparability_problems`, the same as every other numeric field.
    "bias": _NUMERIC, "spread": _NUMERIC,
}

# extra keys that are always legal (the supersedes mechanic + schema generation)
# `supersedes_seq` NARROWS `supersedes` and is meta for the same reason: it
# describes the correction rather than valuing the row (#239).
META_KEYS = {"supersedes", "supersedes_seq", "_gen"}


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


# `\Z`, NOT `$`. In Python `$` matches before a TRAILING NEWLINE, so
# `"hop-test\n"` passed every slug check in this file - six of them - and a
# value that is a slug plus an invisible character validated clean. Found via
# `weight.protocol`, where the seam detector then folded it onto the real slug
# with the validator saying nothing, so a fault had no witness anywhere.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\Z")
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


def _computed_by_problems(dataset: str, rec: dict) -> list[str]:
    """Who computed a value the engine did not (#280).

    Required on a `derived_external` row from the generation the fields
    arrived at, and not before: an older line never owed them, which is the
    G25 property the generation table exists for.

    `derived_build` is required beside a NAMED SOFTWARE and forbidden beside
    `by-hand`. A build is what makes a derivation auditable, and a person with
    a pen does not have one - inventing a version for them would be the field
    asserting a fact about a notebook.
    """
    from .provenance import capture_of

    if capture_of(rec) != "derived_external":
        return []
    if line_generation(rec) < key_generation(dataset, "derived_by"):
        return []

    by, build = rec.get("derived_by"), rec.get("derived_build")
    out = []
    if by is None:
        return ["a 'derived_external' value was computed by something other "
                "than this engine, and 'derived_by' has to say what: a slug "
                f"naming the software, or {DERIVED_BY_HAND!r} where a person "
                "did the arithmetic themselves. Without it a consumer cannot "
                "tell one client's figure from another's, or from a bug fixed "
                "two versions ago"]
    if not SLUG_RE.match(str(by)):
        out.append(f"'derived_by' is a lowercase-kebab slug, got {by!r}")
    if by == DERIVED_BY_HAND and build is not None:
        out.append(
            f"{DERIVED_BY_HAND!r} means a person did the arithmetic, and a "
            f"person has no build (got {build!r})")
    elif by != DERIVED_BY_HAND and build is None:
        out.append(
            f"'derived_build' says WHICH build of {by!r} computed this, and "
            "that is the half that makes the derivation auditable - the same "
            "field computed before and after a fix are different facts")
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


def _capability_problems(rec: dict) -> list[str]:
    """What an instrument can measure, and what a claim about that owes (#171).

    A PROXY MUST NAME WHAT IT ACTUALLY MEASURES, which is the rule that makes
    this class of statement useful rather than a label. "This is a proxy" tells
    a consumer to distrust the number; "this is a proxy FOR the continuous
    nightly minimum" tells them what it is, and two sources reporting one field
    name with different constructs are not comparable regardless of their
    precision.

    And a construct is FORBIDDEN on the others, for the reason `derived_build`
    is forbidden beside `by-hand`: a field that is sometimes an answer and
    sometimes decoration is one a reader learns to skip.
    """
    out: list[str] = []
    origin = rec.get("origin")
    if not isinstance(origin, str) or not origin.strip():
        out.append("'origin' names the instrument this is about, got "
                   f"{origin!r}")

    measures = rec.get("measures")
    known = {f for ds in KEYS for f in KEYS[ds]}
    if measures not in known:
        out.append(f"'measures' names a field this record has, got "
                   f"{measures!r}")

    competence = rec.get("competence")
    if competence not in COMPETENCES:
        out.append(f"'competence' is one of {', '.join(sorted(COMPETENCES))}, "
                   f"got {competence!r}")

    construct = rec.get("construct")
    if competence == PROXY and not (isinstance(construct, str)
                                    and construct.strip()):
        out.append("a 'proxy' competence reports a DIFFERENT quantity under "
                   "this name, and 'construct' has to say which one: an "
                   "uncertainty figure cannot catch a wrong measurand, "
                   "because every one of them assumes the right one")
    if competence != PROXY and construct not in (None, ""):
        out.append(f"'construct' says what a PROXY actually measures and has "
                   f"no meaning beside {competence!r}, got {construct!r}")

    basis = rec.get("basis")
    if basis is not None and basis not in CAPABILITY_BASES:
        out.append(f"'basis' is one of {', '.join(sorted(CAPABILITY_BASES))}, "
                   f"got {basis!r}")
    return out


def _comparability_problems(rec: dict) -> list[str]:
    """Comparability EARNED BY OVERLAP, never asserted (#33 item 2, #171 4.1).

    THE SHAPE IS `_capability_problems`'s, reused rather than reinvented:
    `basis` is checked against a closed vocabulary of exactly one value, and
    `bias`/`spread` are required beside one status and forbidden beside
    another - the same required-beside/forbidden-beside pattern `construct`
    already enforces for `proxy`. An offset with no measured size is an
    assertion wearing a measurement's clothes; a bias attached to a refusal
    is a number about nothing. TYPE-CHECKED THROUGH `_TYPES`, not by hand
    here: both are registered there beside every other numeric field
    (#373 review), so `spread: "banana"` fails the same generic check
    `kg: "banana"` already does rather than validating clean because this
    dataset rolled its own.

    'FIELD' NAMES A MEASUREMENT, not any column this record happens to have
    (#373 review - the allowlist this used to be, every key of every
    dataset, accepted `"note"` and `"origin_a"` exactly as readily as `"kg"`).
    `sensitivity` is the engine's own per-field classification (#299),
    reused for the reason `_relabelled_values` already reuses it rather than
    keeping a second list in step with the first: a comparability statement
    is a question about whether two instruments could disagree on a
    QUANTITY, and only a field classified `measurement` is one.
    """
    out: list[str] = []
    field = rec.get("field")
    if not any(field in KEYS[ds] and sensitivity(ds, field) == "measurement"
              for ds in KEYS):
        out.append(f"'field' names a measurement - a quantity two "
                   f"instruments could disagree about, not any column this "
                   f"record has - got {field!r}")

    origin_a, origin_b = rec.get("origin_a"), rec.get("origin_b")
    for name, value in (("origin_a", origin_a), ("origin_b", origin_b)):
        if not isinstance(value, str) or not value.strip():
            out.append(f"'{name}' names one of the two instruments this "
                       f"compares, got {value!r}")
    if (isinstance(origin_a, str) and isinstance(origin_b, str)
            and origin_a == origin_b):
        out.append(f"'origin_a' and 'origin_b' both name {origin_a!r} - a "
                   "comparability statement is about two DIFFERENT "
                   "instruments, and one instrument is trivially comparable "
                   "to itself")

    status = rec.get("status")
    if status not in COMPARABILITY_STATUSES:
        out.append(f"'status' is one of "
                   f"{', '.join(sorted(COMPARABILITY_STATUSES))}, got "
                   f"{status!r}")

    basis = rec.get("basis")
    if basis != OVERLAP_BASIS:
        out.append(f"'basis' is {OVERLAP_BASIS!r} - the only route this "
                   f"engine accepts to a comparability declaration - got "
                   f"{basis!r}")

    overlap_ref = rec.get("overlap_ref")
    if status in (COMPARABLE, OFFSET) and not (
            isinstance(overlap_ref, str) and overlap_ref.strip()):
        out.append(f"'overlap_ref' names the period the overlap was "
                   f"observed in, and is required beside {status!r}: "
                   "comparability earned by overlap has to name the overlap")

    bias, spread = rec.get("bias"), rec.get("spread")
    if status == OFFSET:
        if bias is None:
            out.append("'bias' is the measured cross-instrument offset and "
                       "is required beside 'offset' - an offset with no "
                       "measured size is an assertion, not a measurement")
        if spread is None:
            out.append("'spread' is how tightly the two instruments agreed "
                       "over the overlap and is required beside 'offset', "
                       "per #171: a measured size with no reported spread "
                       "is a number with no idea how firm it is")
    # 'bias' BESIDE 'comparable' IS CONTRADICTORY (#373 review): a MEASURED
    # bias means the two instruments read differently by a known amount,
    # which is what 'offset' is for. 'spread' beside 'comparable' is NOT
    # flagged - it says how tightly the two agreed over the overlap, which
    # is meaningful evidence about a pair the record has already called
    # comparable, not a contradiction the way a bias would be.
    if status == COMPARABLE and bias is not None:
        out.append("'bias' is contradictory beside 'comparable' - a "
                   "measured bias means the two instruments are OFFSET, not "
                   f"on the same footing; write 'offset' instead, got "
                   f"{bias!r}")
    if status == NOT_COMPARABLE:
        if bias is not None:
            out.append("'bias' has no meaning beside 'not_comparable' - a "
                       f"number on a refusal is a number about nothing, got "
                       f"{bias!r}")
        if spread is not None:
            out.append("'spread' has no meaning beside 'not_comparable', got "
                       f"{spread!r}")
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


def _instrument_problems(rec: dict) -> list[str]:
    """An instrument is an identity over an interval, and both are required.

    `to_date` is the one that may be absent, and its absence MEANS something:
    the instrument is still in use. That is why it is not defaulted to today -
    a register that stamps an end date on everything still in service reads,
    a year later, as a shelf of retired equipment.
    """
    out = []
    if not str(rec.get("origin") or "").strip():
        out.append("'origin' names the instrument this describes, and is the "
                   "identity 27 call sites already key on. Without it the row "
                   "registers nothing")
    first, last = rec.get("from_date"), rec.get("to_date")
    dated = isinstance(first, str) and bool(DATE_RE.match(first))
    if not dated:
        out.append(f"'from_date' is an ISO date - when this instrument started "
                   f"reporting under this origin - got {first!r}")
    if last is not None:
        if not isinstance(last, str) or not DATE_RE.match(last):
            out.append(f"'to_date' is an ISO date or absent for an instrument "
                       f"still in use, got {last!r}")
        # Only against a `from_date` that IS one. Comparing an end date to a
        # start date already reported as malformed adds a second complaint
        # about the first one's consequences, which reads as two defects.
        elif dated and last < first:
            out.append(f"'to_date' {last} is before 'from_date' {first}; an "
                       f"instrument that stopped reporting before it started "
                       f"covers no readings at all")
    return out


def overlapping_instrument_problems(rows: list[dict]) -> list[str]:
    """Two instruments claiming one origin on one day (#311).

    CROSS-ROW, which is why it is not in `validate_record`: a row is only
    wrong here in the company of another. Left unchecked, a reading falls into
    two instruments at once and the register answers ambiguously - which is
    worse than not answering, because the whole point is to say which physical
    thing produced a number.

    A retired line does not overlap its replacement. `supersedes` withdraws a
    statement rather than adding a second one, so a corrected interval is
    compared as one interval, not two.
    """
    from .jsonl import line_key, target_of

    out = []
    # RETIREMENT THROUGH THE EXISTING MACHINERY rather than a second copy of
    # it. `target_of` unpacks what a `supersedes` names and `line_key` says
    # what a row answers to, so a correction here is read exactly as it is
    # everywhere else - which is the point, since a register with its own
    # private idea of what counts as retired is one that disagrees with the
    # rest of the record about which lines are live.
    retired = {t[0] for r in rows
               if (t := target_of(r)) is not None}
    live = [r for r in rows
            if line_key("instruments", r) not in retired
            and isinstance(r.get("from_date"), str)]
    by_origin: dict[str, list[dict]] = {}
    for row in live:
        by_origin.setdefault(str(row.get("origin")), []).append(row)
    for origin, group in sorted(by_origin.items()):
        ordered = sorted(group, key=lambda r: r["from_date"])
        for earlier, later in zip(ordered, ordered[1:]):
            end = earlier.get("to_date")
            if end is None or end >= later["from_date"]:
                out.append(
                    f"instruments: {origin!r} is claimed by two intervals at "
                    f"once - {earlier['from_date']} to {end or 'open'} and "
                    f"{later['from_date']} to {later.get('to_date') or 'open'}. "
                    f"A reading in the overlap belongs to both, so the register "
                    f"cannot say which instrument produced it")
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
            # AN OLD LINE IS REPORTED AS AN OLD LINE (#296). The message used
            # to read "use null for unknown, never omit", which is advice
            # addressed to whoever wrote the line - and `append` rebuilds every
            # row from `KEYS` on the way in, so a caller CANNOT omit a key and
            # a row the engine wrote can never trip this. The only lines that
            # reach here are ones an older engine wrote, and telling their
            # author to do something differently is telling them to have
            # written the line at a different time.
            #
            # So it states both numbers and names the two causes. And it does
            # NOT say the line predates the key: this branch only fires when
            # the key's generation is at or below the line's, so the line
            # appears to POSTDATE it. The first draft of this message said the
            # opposite, which would have sent a reader looking for the wrong
            # thing on every row - #295 was 280 of these.
            problems.append(
                f"missing key '{k}': this line carries generation {line_gen} "
                f"and '{k}' is registered at generation "
                f"{key_generation(dataset, k)}, so by the numbering the key "
                f"existed when the line was written. THREE THINGS PRODUCE "
                "THIS and they need different answers. A writer that is not "
                "this engine omitted the key - `append` fills the shape from "
                "KEYS, so no line it wrote can be missing one. Or the key's "
                "generation has MOVED since the line was stamped, which "
                "reinterprets a number already in the record and is an engine "
                "defect rather than anything to fix here (#295). Or the key "
                "was added to KEYS and never registered a generation at all, "
                "in which case it defaults to 1 and every line in the record "
                "is held to it - check that one first if this is firing on "
                "all of them")
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
    if dataset == "instruments":
        problems += _instrument_problems(rec)
    if dataset == "capabilities":
        problems += _capability_problems(rec)
    if dataset == "comparability":
        problems += _comparability_problems(rec)
    # THE FIELD THAT ALREADY HAD THE VOCABULARY AND NO VALIDATION (#212).
    # `for_phase` was checked by nothing, so a typo or a vendor's own spelling
    # sorted last and silently, and the sort key in `api.py` was the only place
    # the legal values were written down.
    if rec.get("for_phase") is not None and rec["for_phase"] not in day_phases():
        problems.append(
            f"'for_phase' is one of {', '.join(sorted(day_phases()))}, got "
            f"{rec['for_phase']!r} - the part-of-day vocabulary is Open "
            "mHealth's, in semantics/day_phase.toml")
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
        problems += _computed_by_problems(dataset, rec)
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
        if _ss and _se and not _bad_time(_ss) and not _bad_time(_se):
            # COMPARED THROUGH `comparable`, and this RAISED before. One naive
            # boundary and one aware one made `<=` throw a TypeError out of
            # `validate_record`, so a single such row took down every append,
            # every build and `validate` itself - the whole record, rather
            # than reporting one line. That is the #38 defect exactly: two
            # timestamps that cannot be compared are an outcome to report,
            # never an exception and never a guessed instant.
            #
            # Unreported rather than reported, deliberately. "These two cannot
            # be compared" is true of the pair and says nothing about whether
            # the night is backwards, which is what this check is for. The
            # mixed-stamp condition is already an advisory the record raises
            # elsewhere, and saying it twice in different words would make one
            # row look like two faults.
            _a, _b, _ok = comparable(parse_time(_se), parse_time(_ss))
            if _ok and _a <= _b:
                problems.append(
                    f"'sleep_end' {_se!r} is not after 'sleep_start' {_ss!r}")
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
    problems += _position_problems(dataset, rec)
    problems += _validate_policy(dataset, rec)
    problems += _sensitive_problems(dataset, rec)
    return _redacted(dataset, rec, problems)


REDACTED = "[precise]"


def _whole_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _position_problems(dataset: str, rec: dict) -> list[str]:
    """Shapes for the two position fields (#239).

    CHECKED HERE AS WELL AS REFUSED AT APPEND, and the pair is not redundant.
    `append` refuses a caller-supplied `seq`, which covers writes through this
    engine and nothing else - and the format invites hand editing and rows
    arrive by sync. Unchecked, `"1"` and `1` are two spellings of one position
    and a negative names a row that cannot exist.
    """
    out = []
    if (position := rec.get("seq")) is not None and dataset in SEQUENCED:
        if not _whole_count(position):
            out.append(
                f"'seq' is this row's position among the rows already sharing "
                f"its key, so it is a whole number counting from zero, got "
                f"{position!r}")
    if (narrow := rec.get("supersedes_seq")) is not None:
        if not _whole_count(narrow):
            out.append(
                f"'supersedes_seq' is the position of the row being corrected, "
                f"so it is a whole number counting from zero, got {narrow!r}")
        if not str(rec.get("supersedes") or "").strip():
            out.append(
                "'supersedes_seq' NARROWS 'supersedes' and cannot stand alone: "
                "a position with no key names a position in nothing")
    return out


def _redacted(dataset: str, rec: dict, problems: list[str]) -> list[str]:
    """Problem strings with any precise value taken back out (#205).

    THE DIAGNOSTIC CHANNEL IS AN EGRESS SURFACE and it is the one nobody
    looks at. This module quotes the offending value in roughly twenty-five
    messages - `got {v!r}` - and those strings travel out through `validate()`
    and `load_report()["warnings"]` to every consumer, a log line and a
    rendered report. A gate on the read path that left the error path quoting
    the value would be a gate with a hole in the shape of a mistake.

    Done ONCE HERE, at the exit, rather than in twenty-five message sites,
    because a message added tomorrow would not know to redact and this does.

    UNSCOPED, AND THE FIRST VERSION WAS NOT. It only rewrote problems that
    named the field, on the reasoning that every message quoting a value also
    names the field it came from. That is false in the form the check needed:
    `bad date {v!r}`, `bad start_time {st!r}` and `bad measured_at {v!r}` name
    no field in quotes at all. So a column-shifted import - the ordinary way a
    flattened export goes wrong - that put an address into `date` while
    `place_precise` also held it produced `bad date '12 Example Street'`
    verbatim, out through `validate()`, `load_report()` warnings, the CLI and
    the MCP validate tool, with the value sitting in `rec` unredacted.

    So it now redacts the value wherever it appears. The cost is that a short
    precise value could blank an unrelated substring and make a message less
    helpful. That trade is not close: a confusing diagnostic is repaired by
    reading the row, and a leaked address cannot be un-leaked.
    """
    pairs = SENSITIVE.get(dataset)
    if not pairs or not problems:
        return problems
    forms = []
    for key in pairs:
        value = rec.get(key)
        if value is None or not str(value).strip():
            continue
        forms += [f for f in (repr(value), str(value)) if f]
    if not forms:
        return problems
    out = []
    for problem in problems:
        for form in forms:
            problem = problem.replace(form, REDACTED)
        out.append(problem)
    return out


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


def protocol_pin_advisories(dataset: str, rows: list[tuple[int, dict]],
                            protocol_rows: list[tuple[int, dict]]) -> list[str]:
    """A weight or measurements row silent about a protocol this dataset has
    otherwise used to name its conditions (#371).

    CAUGHT, not merely surfaced - this is the sharpened ask from the issue's
    own follow-up comment, and the shape below is built to match it exactly.

    SCOPE IS DERIVED, NEVER DECLARED, and that is the whole design. A
    `protocols` row (see `KEYS["protocols"]`) does not say which dataset it
    governs - it is a slug, a date and some prose, nothing more - so "a
    protocol for weight exists" cannot be read off `protocols.jsonl` alone.
    It has to be read off `weight.jsonl` itself: whatever slugs weight rows
    have actually named IS the evidence a protocol applies to weight, and
    nothing else is.

    THE EMPTY CASE IS SILENCE, not a lesser warning, and it is the common
    case: of this repo's own personas, three are 100% pinned and the rest are
    0%, and a record that has never named a protocol for a dataset has given
    no evidence any protocol applies to it. Advising there would be the
    engine inventing a discipline nobody adopted, which the issue's decision
    rules out by name ("a record with no protocols declared has nothing to be
    missing"). So: no slug ever named in this dataset -> return nothing for
    it, full stop, before any row is even looked at for absence.

    A DANGLING SLUG DOES NOT COUNT AS A REAL PROTOCOL. Naming a slug on a
    `weight` row is not the same as that slug being a real, declared
    protocol - it could be a typo, or a slug used before its `protocols` row
    ever lands (legal and open, see the comment on `KEYS["protocols"]`). A
    slug with no matching `protocols` row ANYWHERE in the record is not
    evidence any procedure applies, so it must not anchor the scope and must
    not, on its own, turn the advisory on.

    Written as its own gate for readability, and honestly it is SUBSUMED:
    removing it changes no output any test can see, because a dataset whose
    slugs are all dangling also has no adoption date and stops at the gate
    below. Mutating it away leaves the suite green. It stays because the
    three conditions are three different reasons to say nothing and reading
    them as one would lose two of them - not because anything can catch its
    removal. The same is true of the empty-named-set gate above. What IS
    caught is the combination that matters: one real slug plus one dangling
    one must anchor on the real one's adoption rather than falling through
    to "nothing is declared, scope the whole history".

    THE ANCHOR IS THIS DATASET'S OWN ADOPTION, not a `protocols` declaration
    date pulled from anywhere it happens to sit. It used to be the earliest
    DECLARATION date among the slugs this dataset uses - which over-reaches
    the moment a dataset ever names two slugs: `weight` naming `proto-a`
    (declared 2030) and, much later, also naming `proto-b` (declared 2020 for
    something else entirely) pulled the scope back to 2020 and flagged six
    years of `weight` rows that came before `weight` had named anything at
    all. That is exactly the noise-on-rows-that-were-never-wrong failure the
    scoping rule exists to prevent, just reached from the other direction.
    The fix uses the same principle Step 1 already uses - derive from the
    dataset's OWN rows, never from `protocols.jsonl` directly - so the anchor
    is the earliest date on which a row in THIS dataset actually named a REAL
    (non-dangling) slug. A dataset cannot be dragged backwards by a slug it
    only adopted later, and cannot be anchored by a slug it never really had.

    ADVISORY, NEVER A REFUSAL - the issue is explicit about why. A reading
    taken under unknown conditions is still true, and losing it (by refusing
    the append) would be worse than holding it unpinned. In this repo's own
    corpus 2103 of 2209 weight rows name none, and a validator that cannot
    pass on a real record is one that gets switched off. The issue quotes a
    higher proportion still from a private record; that figure is not
    checkable here, so this states the one that is.
    What must not happen is an unpinned reading being COMPARED as though it
    were pinned - that is `protocol_seam`'s job at build/report time, over
    resolved windows, and is not touched here. This function only says how
    many rows, and which span, are silent about conditions this dataset has
    otherwise cared enough to name.

    ONE LINE PER DATASET, not one per row - `polarity_advisories` and
    `timestamp_advisories` set the precedent: a validator that printed one
    line per unpinned row on a 377-of-381 record would be almost the whole
    file, and that is the validator people stop reading.

    NO LINE-NUMBER POINTER. An earlier version named "(first: line N)", but
    `rows` here is one dataset's UNION across every device file - one writer
    per file (#105) - and a line number is only unique per FILE, not across
    the union. On a record with `weight.jsonl` and `weight.scale2.jsonl`
    both in play, "line 1" could name either file, and nothing here says
    which; a reader who followed it could land on a row that IS pinned while
    the advisory is reporting the ones that are not. Even single-file, the
    first entry in iteration order is not the earliest by date, so the
    pointer could name a later-dated row while the span (below) starts
    earlier. The span's start date is unambiguous across every file in the
    union and is what a reader actually searches for, so the pointer is
    dropped rather than patched to carry a filename too - the file identity
    is not threaded through the tuples `validate()` builds for any of the
    dozen checks that share this shape, and doing it only here for one
    caller would be new machinery this advisory does not need.
    """
    if dataset not in ("weight", "measurements"):
        return []
    # Step 1: slugs THIS DATASET has actually named. Not every slug that
    # exists in `protocols.jsonl` - see the docstring above for why that
    # distinction is the whole point.
    named = {str(r["protocol"]) for _, r in rows if r.get("protocol")}
    if not named:
        return []
    # Step 2: of those named slugs, which are REAL - i.e. have at least one
    # matching `protocols` row anywhere in the record. A slug this dataset
    # names but that is declared nowhere is a DANGLING reference, not
    # evidence a protocol applies (see the docstring's DANGLING SLUG
    # paragraph), and must not reach Step 3 at all.
    declared_slugs = {str(r["slug"]) for _, r in protocol_rows
                      if r.get("slug") and r.get("date")
                      and not _bad_date(r["date"])}
    real = named & declared_slugs
    if not real:
        return []
    # Step 3: THIS DATASET'S OWN adoption date - the earliest date on which
    # one of ITS OWN rows named a real slug. Derived from `rows`, exactly
    # like Step 1, and deliberately NOT from `protocol_rows`: see the
    # docstring's ANCHOR paragraph for why anchoring on a declaration date
    # instead over-reaches into a slug this dataset only adopted later.
    own_adoption = [date.fromisoformat(str(r["date"])) for _, r in rows
                    if str(r.get("protocol")) in real and r.get("date")
                    and not _bad_date(r["date"])]
    if not own_adoption:
        return []
    since = min(own_adoption)
    # Step 4: rows in THIS dataset, dated on or after `since`, that carry no
    # protocol. A malformed date is skipped here rather than guessed at -
    # `_bad_date` already reports it elsewhere as its own problem.
    unpinned = [(n, r) for n, r in rows
               if not r.get("protocol") and r.get("date")
               and not _bad_date(r["date"])
               and date.fromisoformat(str(r["date"])) >= since]
    if not unpinned:
        return []
    span = sorted(date.fromisoformat(str(r["date"])) for _, r in unpinned)
    return [
        f"{dataset}.jsonl: {len(unpinned)} row(s) dated {span[0].isoformat()} "
        f"to {span[-1].isoformat()} carry no 'protocol', though this record "
        f"has named {', '.join(sorted(real))!r} since {since.isoformat()}. "
        "Legal and unrefused - an unpinned reading is still true - but it is "
        "not comparable to one that names its conditions until it does too"]


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
    from .jsonl import line_key, position_of, target_of
    problems: list[str] = []
    by_key: dict[str, list[int]] = {}
    seat: dict[int, int | None] = {}
    for n, r in rows:
        by_key.setdefault(line_key(dataset, r), []).append(n)
        seat[n] = position_of(r)
    superseding = {n for n, r in rows if r.get("supersedes")}
    problems += _unnameable(dataset, rows)
    for n, r in rows:
        if not (ref := r.get("supersedes")):
            continue
        narrow = (target_of(r) or (None, None))[1]
        # Rows that are themselves corrections are excluded from the count. A
        # CHAIN (A superseded by B, B superseded by C) legitimately shares one
        # reference and retires all of it - that is documented behaviour, not
        # ambiguity. What this catches is two rows that were never the same
        # thing answering to one key, which is the case that loses data.
        # A row that is itself a correction is excluded from a BARE reference's
        # matches, because a chain legitimately shares one reference and that
        # is documented behaviour rather than ambiguity. A NARROWED reference
        # names one row, and that row is eligible whatever else it does -
        # excluding it would report "matches no line" about a reference that
        # retires exactly what it names.
        hit = [m for m in by_key.get(str(ref), [])
               if m != n and (narrow is not None or m not in superseding)]
        if narrow is not None:
            hit = [m for m in hit if seat[m] == narrow]
        if len(hit) > 1:
            # AMBIGUOUS AND NAMEABLE, versus ambiguous and not, because the two
            # need different sentences (#239). Where the matched rows carry
            # distinct positions the author can name one, and the advice is the
            # `supersedes_seq` to write. Where they do not - lines older than
            # the field, or two machines that were offline together and stamped
            # the same number - no reference reaches them, and telling somebody
            # holding a five-year-old file to add a vendor identity is advice
            # they cannot take for the rows in front of them.
            seats = [seat[m] for m in hit]
            if None not in seats and len(set(seats)) == len(seats):
                problems.append(
                    f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches "
                    f"{len(hit)} lines ({', '.join(map(str, hit))}) - the most "
                    "recent is the one retired, and it may not be the one "
                    "meant. Name the one you mean with 'supersedes_seq': "
                    + ", ".join(str(x) for x in sorted(seats)))
            else:
                problems.append(
                    f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches "
                    f"{len(hit)} lines ({', '.join(map(str, hit))}) and "
                    "NOTHING CAN NAME THEM APART - the most recent is the one "
                    "retired and no reference reaches the others. These lines "
                    "predate 'seq' or were written by two machines that could "
                    "not see each other. The value can be restated on a new "
                    "line; the earlier ones cannot be corrected in place. Rows "
                    "written from here on carry a position, and a vendor "
                    "identity (activity_id) where the source supplies one, so "
                    "this does not recur")
        elif not hit:
            problems.append(
                f"{dataset}.jsonl line {n}: 'supersedes' {ref!r} matches no "
                "line - nothing is being corrected, and the reference is "
                "probably mistyped")
        elif (moved := _relabelled_values(dataset, dict(rows)[hit[0]], r)):
            # A CORRECTION IS COMPARED AGAINST THE LINE IT RETIRES (#342).
            # Only where the reference is unambiguous: where it matches
            # several lines the advisory above already says the engine picked
            # one and may have picked wrong, and comparing against a row the
            # author did not mean would be a second guess on top of a first.
            problems.append(
                f"{dataset}.jsonl line {n}: this correction keeps "
                f"{', '.join(moved)} unchanged from the line it retires and "
                f"attributes them to a different instrument "
                f"({dict(rows)[hit[0]].get('origin')!r} -> "
                f"{r.get('origin')!r}). That is either an attribution being "
                "fixed or two instruments being laundered into one, and the "
                "record cannot tell them apart - so it is reported rather "
                "than decided. If the values really came from the earlier "
                "instrument, write them as their own line rather than "
                "carrying them forward")
    return problems


def _relabelled_values(dataset: str, retired: dict, correction: dict) -> list[str]:
    """Fields a correction carries forward unchanged under a NEW instrument.

    The laundering shape #325 narrates and #342 names: a hand-merged row that
    supersedes a watch's line, keeping its heart rate and energy figures and
    stamping the console's `origin` on them. Both lines are well-formed, the
    merge works as designed, and the record ends up asserting that a rowing
    console observed a heart rate.

    A value that CHANGED is a correction of the value and says nothing about
    attribution. A value that is identical and has changed instrument is the
    case with no innocent reading available to the engine: either the athlete
    is fixing an attribution, or two instruments have been folded into one.

    NOT AN ORIGIN THE ROW NEVER HAD. Where either line names no instrument
    there is no disagreement to report - silence is not a competing claim,
    which is the rule `instrument_seam` and `is_independent` already keep.

    MEASUREMENTS ONLY, and the cut is the engine's own rather than a list
    written here. #299 classifies every field, and an instrument OBSERVES a
    measurement - it does not observe a date, a slug, a note or a source. The
    first version of this had a hand-written skip list, which is a second
    classification that drifts from the first; filtering on the published
    class drops `type`, `date`, `origin`, `supersedes` and the rest without
    naming any of them.
    """
    before, after = retired.get("origin"), correction.get("origin")
    if before in (None, "") or after in (None, "") or before == after:
        return []
    return sorted(
        field for field, value in correction.items()
        if value is not None and retired.get(field) == value
        and field in KEYS.get(dataset, ())
        and sensitivity(dataset, field) == "measurement")


def _unnameable(dataset: str, rows: list[tuple[int, dict]]) -> list[str]:
    """Rows that share a stored position, which is the one collision left.

    `seq` is counted across every stream at append and takes the higher of the
    count and the highest position already visible, so one machine never hands
    out a number twice and neither does a machine that can SEE the rows. Two
    that cannot see each other at all will, and this says so rather than
    leaving a reference that silently retires whichever sorted last. Reported
    once per key, because it is one fact about a pair.
    """
    from .jsonl import line_key, position_of

    seen: dict[tuple[str, int], list[int]] = {}
    for n, r in rows:
        if (pos := position_of(r)) is not None:
            seen.setdefault((line_key(dataset, r), pos), []).append(n)
    return [
        f"{dataset}.jsonl lines {', '.join(map(str, lines))}: all carry key "
        f"{key!r} at position {pos}, so no correction can name one of them. "
        "Two machines that could not see each other's rows stamped the same "
        "position. Restate the value on a new line rather than correcting "
        "these"
        for (key, pos), lines in sorted(seen.items()) if len(lines) > 1]


def corrections_awaiting_their_target(dataset: str,
                                      rows: list[tuple[int, dict]]) -> list[str]:
    """ADVISORY: a correction whose target is not in this record yet."""
    return _dud_corrections(dataset, rows)[1]


def corrections_that_did_not_apply(dataset: str,
                                   rows: list[tuple[int, dict]]) -> list[str]:
    """PROBLEM: a correction whose target is here and survived anyway."""
    return _dud_corrections(dataset, rows)[0]


def _name(ref: str, narrow: int | None) -> str:
    """A reference as a person would write it in a message."""
    return repr(ref) if narrow is None else f"{ref!r} position {narrow}"


def _dud_corrections(dataset: str, rows: list[tuple[int, dict]]
                     ) -> tuple[list[str], list[str]]:
    """(defeated, awaiting) - two causes with opposite remedies.

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
    from .jsonl import line_key, position_of, retire, target_of
    # IN MERGED ORDER, which is the whole point. `validate` hands these over
    # in FILE order, one device file after another, and in file order the
    # correction sits below its target and applies perfectly. The defect is
    # created by the reordering, so a check that skips it cannot see it.
    #
    # `merge` over a single unnamed stream is the same code path with one
    # actor, so a single-file record is ordered exactly as `load` orders it.
    lines = merge([("", [r for _, r in rows])], dataset)
    applied: set[tuple[str, int | None]] = set()
    retire(dataset, lines, applied=applied)

    out: list[str] = []
    advisory: list[str] = []
    seen: set[tuple[str, int | None]] = set()
    for r in lines:
        # THE WHOLE TARGET, KEY AND POSITION (#239). Matching on the key alone
        # meant a defeated NARROWED correction went unreported whenever any
        # other correction of the same key applied, and a narrowed reference
        # naming a position nothing carries was diagnosed as an ordering
        # defeat - "it sorted before its target, fix the clock" - while
        # `supersedes_problems` said "matches no line, probably mistyped"
        # about the same row. Two contradictory instructions for one line.
        if (target := target_of(r)) is None:
            continue
        ref, narrow = target
        # ASKED OF `retire`, not inferred from what survived (#239). The old
        # check counted anything still alive under the reference as proof the
        # correction did nothing - which was sound while one reference retired
        # every match, and became a false alarm the moment it retired one. A
        # surviving sibling is now the ordinary, intended outcome.
        if target in applied or target in seen:
            continue
        seen.add(target)
        # TWO CAUSES WITH OPPOSITE REMEDIES, split because escalating them
        # together made an ordinary mid-sync record fail `validate` (#210).
        #
        # A reference naming NO line is the offline-first case: another
        # writer's file has not arrived, there is nothing to append, and the
        # record repairs itself when it does. Telling someone to append the
        # correction again is wrong advice for it, and refusing the build is
        # worse.
        #
        # A reference whose target IS here and survived anyway is the defeat:
        # the value the correction was meant to replace is what every reader
        # sees, and no amount of waiting changes it.
        here = [other for other in lines if not other.get("supersedes")
                and line_key(dataset, other) == ref
                and (narrow is None or position_of(other) == narrow)]
        if here:
            out.append(
                f"{dataset}: a correction of {_name(ref, narrow)} did NOT "
                f"apply - the line "
                f"it names is still in the record, so the value it was meant "
                f"to replace is what every reader sees. It sorted before its "
                f"target, which happens when a correction carries no "
                f"recorded_at and its target does, or when another writer "
                f"stamped the target ahead of the machine that wrote the "
                f"correction. Appending it again only helps if this machine's "
                f"clock has since passed that stamp")
        else:
            advisory.append(
                f"{dataset}: a correction of {_name(ref, narrow)} names no "
                f"line in this "
                f"record. That is the ordinary state of a record part way "
                f"through a sync - the writer holding the target has not "
                f"arrived - and it applies itself when that file lands. "
                f"Nothing to do unless it stays after every writer is in")
    return out, advisory


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
