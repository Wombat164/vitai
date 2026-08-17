"""A class per field, published, with no default (#299).

A client that gates egress needs to know which of the engine's fields are
sensitive and how. It cannot ask, so it keeps a copy of this schema, and the
copy is wrong the day a field is added here. Worse than wrong: its fallback
gives an unknown field the MOST PERMISSIVE class, so a new field ships to
every recipient the day it appears and the release log files it as harmless -
so the leak is invisible even to a careful reader.

A PER-FIELD-NAME MAP CANNOT BE RIGHT, which is not a quality problem with the
copy. `reason` is on five datasets: on four it is free prose about why a
policy changed, and on `plans` it is the COM-B axis - `motivation_automatic`,
`capability_physical`, `declined` - a claim about why somebody did not train.
One name, two disclosures, and no map keyed on the name alone can say both.

THE CLASSES ARE A JUDGEMENT AND THIS FILE DOES NOT PRETEND OTHERWISE. What
makes publishing them better than a consumer guessing is not that they are
certainly right: it is that they are wrong in ONE place, reviewable, and
cannot silently default. The pin below is the review surface - adding a field
changes it, and the diff asks what kind of disclosure the new field is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import field_types
from vitai.schema import (KEYS, SENSITIVITY_CLASSES, SENSITIVITY_OVERRIDE,
                          sensitivity)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"

PINNED = {
    # #171: what an instrument is competent at. `measures` and `condition` are
    # REFERENCE - they name a field and a closed scope, and neither says
    # anything about the athlete. `competence`, `construct` and `basis` are
    # PROVENANCE: they are statements about what produced a value, which is
    # the class's own definition.
    "capabilities": {
        "date": "temporal",
        "origin": "provenance",
        "measures": "reference",
        "competence": "provenance",
        "construct": "provenance",
        "condition": "reference",
        "basis": "provenance",
        "set_by": "reference",
        "note": "narrative",
        "supersedes": "reference",
        "recorded_at": "temporal",
        "device": "provenance",
    },
    # #311. The register says WHAT observed a value, which is the provenance
    # class's own definition - `name` and `maker` sit beside `origin` and
    # `model` rather than describing the athlete. The interval is temporal.
    "instruments": {
        "date": "temporal",
        "origin": "provenance",
        "from_date": "temporal",
        "to_date": "temporal",
        "name": "provenance",
        "maker": "provenance",
        "model": "provenance",
        "source": "provenance",
        "note": "narrative",
        "supersedes": "reference",
        "recorded_at": "temporal",
        "device": "provenance",
    },
    # #33 item 2: comparability earned by overlap. `origin_a`/`origin_b` are
    # PROVENANCE beside `origin` - they name what observed a value, the
    # class's own definition. `bias`/`spread` are MEASUREMENT, the measured
    # cross-instrument quantities. `overlap_ref` is REFERENCE, the same class
    # `basis_claims`/`session_ref` carry: a pointer to evidence rather than a
    # statement about the athlete.
    "comparability": {
        "date": "temporal",
        "field": "reference",
        "origin_a": "provenance",
        "origin_b": "provenance",
        "status": "reference",
        "bias": "measurement",
        "spread": "measurement",
        # #402's contract 52. MEASUREMENT for `bias`/`spread`'s own reason
        # rather than by analogy: they are the two ends of the same measured
        # cross-instrument quantity, in the same units, observed over the same
        # overlap. Nothing about the athlete is in them that is not already in
        # the width they bound.
        "difference_lo": "measurement",
        "difference_hi": "measurement",
        "basis": "provenance",
        "overlap_ref": "reference",
        "note": "narrative",
        "source": "provenance",
        "supersedes": "reference",
        "recorded_at": "temporal",
        "device": "provenance",
    },
    "achievements": {
        "date": "temporal", "title": "narrative", "goal": "reference",
        "source": "provenance", "note": "narrative", "occurred_date":
        "temporal", "recorded_at": "temporal", "device": "provenance",
        "seq": "reference"

    },
    "artifacts": {
        "date": "temporal", "sha256": "reference", "media_type":
        "reference", "bytes": "measurement", "captured_at": "temporal",
        "origin": "provenance", "kind": "reference", "note": "narrative",
        "removed": "reference", "reason": "narrative", "recorded_at":
        "temporal", "device": "provenance",
        "seq": "reference"

    },
    "checks": {
        "date": "temporal", "slug": "reference", "result": "reference",
        "value": "measurement", "source": "provenance", "note": "narrative",
        "recorded_at": "temporal", "device": "provenance",
        "seq": "reference"

    },
    "context": {
        "date": "temporal", "mode": "reference", "facilities":
        "whereabouts", "place": "whereabouts", "source": "provenance",
        "note": "narrative", "recorded_at": "temporal", "device":
        "provenance", "place_precise": "whereabouts",
        "seq": "reference"

    },
    "daily": {
        # #402. The field list names columns and says nothing about
        # anybody, so REFERENCE. The reason is BEHAVIOURAL: two of
        # its six codes say why the ATHLETE did not provide a value
        # - declined, or does not know - which is that class's own
        # definition and the call `plans.reason` already gets.
        "absent_fields": "reference",
        "absent_reason": "behavioural",
        "date": "temporal", "steps": "measurement", "distance_km":
        "measurement", "active_min": "measurement", "kcal_out":
        "measurement", "kcal_in": "measurement", "protein_g": "measurement",
        "sleep_h": "measurement", "rhr": "measurement", "hip_pain":
        "clinical", "alcohol": "behavioural", "note": "narrative", "source":
        "provenance", "mood": "behavioural", "feel": "behavioural",
        "coverage": "behavioural", "pain": "clinical", "pain_site":
        "clinical", "pain_side": "clinical", "recorded_at": "temporal",
        "origin": "provenance", "path": "provenance", "origin_evidence":
        "provenance", "capture": "provenance", "read_by": "provenance",
        "modelled": "provenance", "artifact": "reference", "device":
        "provenance", "derived_from": "provenance", "derived_op":
        "provenance", "derived_by": "provenance", "derived_build":
        "provenance", "fat_g": "measurement", "carb_g": "measurement",
        "fibre_g": "measurement", "sugar_g": "measurement", "sodium_mg":
        "measurement", "sleep_start": "temporal", "sleep_end": "temporal",
        "mood_scale": "reference", "pain_scale": "reference",
        "seq": "reference"

    },
    "emissions": {
        "date": "temporal", "kind": "reference", "metric": "reference",
        "week": "temporal", "statement": "narrative", "basis_claims":
        "reference", "policy_asof": "temporal", "contract": "reference",
        "surface": "provenance", "recorded_at": "temporal", "device":
        "provenance"
    },
    "events": {
        "date": "temporal", "slug": "reference", "title": "narrative",
        "kind": "reference", "event_date": "temporal", "priority":
        "reference", "immovable": "reference", "place": "whereabouts",
        "status": "reference", "set_by": "reference", "reason": "narrative",
        "note": "narrative", "recorded_at": "temporal", "device":
        "provenance", "outcome": "reference"
    },
    "goals": {
        "date": "temporal", "slug": "reference", "title": "narrative",
        "metric": "reference", "dataset": "reference", "session_type":
        "reference", "tracker": "provenance", "target": "measurement",
        "policy": "reference", "guard_pct": "measurement", "period":
        "reference", "on_period_end": "reference", "deadline": "temporal",
        "status": "reference", "motivator": "behavioural", "rationale":
        "behavioural", "on_success": "reference", "on_miss": "reference",
        "accountability": "behavioural", "set_by": "reference", "reason":
        "narrative", "note": "narrative", "event": "reference",
        "deadline_kind": "reference", "verification": "reference",
        "change_kind": "reference", "recorded_at": "temporal", "device":
        "provenance", "polarity": "reference", "target_hi": "measurement",
        "lifecycle_status": "reference"
    },
    "inferences": {
        "date": "temporal", "kind": "reference", "statement": "narrative",
        "confidence": "provenance", "model": "provenance", "evidence":
        "provenance", "note": "narrative", "depends_on": "reference",
        "recorded_at": "temporal", "device": "provenance",
        "seq": "reference"

    },
    "journal": {
        "date": "temporal", "kind": "reference", "text": "narrative",
        "about": "narrative", "source": "provenance", "confidence":
        "provenance", "status": "reference", "note": "narrative",
        "recorded_at": "temporal", "device": "provenance",
        "seq": "reference"

    },
    "meals": {
        "date": "temporal", "meal": "reference", "item": "reference",
        "grams": "measurement", "grams_lo": "measurement", "grams_hi":
        "measurement", "kcal_100g": "measurement", "protein_100g":
        "measurement", "fat_100g": "measurement", "carb_100g":
        "measurement", "food_table": "provenance", "note": "narrative",
        "source": "provenance", "recorded_at": "temporal", "origin":
        "provenance", "path": "provenance", "origin_evidence": "provenance",
        "capture": "provenance", "read_by": "provenance", "device":
        "provenance", "derived_from": "provenance", "derived_op":
        "provenance", "derived_by": "provenance", "derived_build":
        "provenance", "fibre_100g": "measurement", "sugar_100g":
        "measurement", "sodium_mg_100g": "measurement"
    },
    "measurements": {
        "date": "temporal", "kind": "reference", "value": "measurement",
        "source": "provenance", "note": "narrative", "recorded_at":
        "temporal", "origin": "provenance", "path": "provenance",
        "origin_evidence": "provenance", "capture": "provenance", "read_by":
        "provenance", "modelled": "provenance", "artifact": "reference",
        "device": "provenance", "protocol": "provenance", "derived_from":
        "provenance", "derived_op": "provenance", "derived_by":
        "provenance", "derived_build": "provenance",
        "seq": "reference"

    },
    "medical": {
        "date": "temporal", "slug": "reference", "kind": "clinical",
        "title": "clinical", "body_site": "clinical", "severity":
        "clinical", "status": "clinical", "resolved_date": "temporal",
        "restricts": "clinical", "provider_type": "clinical", "source":
        "provenance", "note": "clinical", "expects": "clinical",
        "onset_date": "temporal", "precondition": "clinical", "restriction":
        "clinical", "recorded_at": "temporal", "device": "provenance",
        "body_side": "clinical"
    },
    "plans": {
        "date": "temporal", "slug": "reference", "for_date": "temporal",
        "for_phase": "temporal", "activity": "reference", "setting":
        "whereabouts", "tier": "reference", "serves": "reference", "set_by":
        "reference", "requires": "reference", "outcome": "reference",
        "reason": "behavioural", "session_ref": "reference", "note":
        "narrative", "supersedes": "reference", "recorded_at": "temporal",
        "device": "provenance"
    },
    "protocols": {
        "date": "temporal", "slug": "reference", "text": "narrative",
        "supersedes": "reference", "recorded_at": "temporal", "device":
        "provenance",
        # #404. `reference` because it is a list of closed-vocabulary slugs
        # describing a PROCEDURE - "this method fixes the bladder and the fed
        # state" is a property of the method rather than a fact about the
        # athlete on any day.
        #
        # Worth stating because the obvious neighbour is not: a companion field
        # on the READING, saying which conditions actually held that morning,
        # would be `behavioural` and possibly `clinical`, because "I had not
        # voided" is a fact about a body. That asymmetry is part of why the
        # reading-side half was designed and deliberately not built here.
        "controls": "reference",
    },
    "regimes": {
        "date": "temporal", "from_date": "temporal", "to_date": "temporal",
        "dataset": "reference", "field": "reference", "kind": "reference",
        "source": "provenance", "text": "narrative", "anchored_by":
        "reference", "note": "narrative", "recorded_at": "temporal",
        "device": "provenance", "supersedes": "reference",
        "seq": "reference"

    },
    "sessions": {
        # #402. The field list names columns and says nothing about
        # anybody, so REFERENCE. The reason is BEHAVIOURAL: two of
        # its six codes say why the ATHLETE did not provide a value
        # - declined, or does not know - which is that class's own
        # definition and the call `plans.reason` already gets.
        "absent_fields": "reference",
        "absent_reason": "behavioural",
        "date": "temporal", "type": "reference", "distance_km":
        "measurement", "duration_s": "measurement", "avg_hr": "measurement", "avg_power":
        "measurement",
        "max_hr": "measurement", "cadence": "measurement", "kcal":
        "measurement", "location": "whereabouts", "rpe": "measurement",
        "note": "narrative", "source": "provenance", "start_time":
        "temporal", "elevation_m": "measurement", "setting": "whereabouts",
        "route": "whereabouts", "place": "whereabouts", "with":
        "whereabouts", "context": "whereabouts", "planned": "reference",
        "weather": "whereabouts", "recorded_at": "temporal", "track":
        "whereabouts", "activity_id": "provenance", "activity_source":
        "provenance", "origin": "provenance", "path": "provenance",
        "origin_evidence": "provenance", "capture": "provenance", "read_by":
        "provenance", "modelled": "provenance", "type_source": "provenance",
        "artifact": "reference", "device": "provenance", "derived_from":
        "provenance", "derived_op": "provenance", "derived_by":
        "provenance", "derived_build": "provenance", "rpe_scale":
        "reference", "place_precise": "whereabouts",
        "seq": "reference"

    },
    "sets": {
        "date": "temporal", "session_start": "temporal", "exercise":
        "reference", "block": "reference", "round": "reference",
        "set_index": "reference", "reps_completed": "measurement",
        "reps_attempted": "measurement", "load": "measurement", "load_type":
        "reference", "load_unit": "reference", "machine": "provenance",
        "set_type": "reference", "failure": "reference", "rir":
        "measurement", "rpe": "measurement", "rest_s": "measurement",
        "tempo": "measurement", "duration_s": "measurement", "side":
        "reference", "note": "narrative", "source": "provenance",
        "recorded_at": "temporal", "origin": "provenance", "path":
        "provenance", "origin_evidence": "provenance", "capture":
        "provenance", "read_by": "provenance", "equipment": "provenance",
        "angle_class": "reference", "angle_deg": "measurement",
        "resistance_level": "measurement", "seat_pos": "measurement",
        "pad_pos": "measurement", "lever_pos": "measurement", "device":
        "provenance", "derived_from": "provenance", "derived_op":
        "provenance", "derived_by": "provenance", "derived_build":
        "provenance", "rpe_scale": "reference"
    },
    "thresholds": {
        "date": "temporal", "key": "reference", "value": "measurement",
        "change_kind": "reference", "set_by": "reference", "reason":
        "narrative", "note": "narrative", "recorded_at": "temporal",
        "device": "provenance"
    },
    "weight": {
        # #402. The field list names columns and says nothing about
        # anybody, so REFERENCE. The reason is BEHAVIOURAL: two of
        # its six codes say why the ATHLETE did not provide a value
        # - declined, or does not know - which is that class's own
        # definition and the call `plans.reason` already gets.
        "absent_fields": "reference",
        "absent_reason": "behavioural",
        "date": "temporal", "kg": "measurement", "source": "provenance",
        "note": "narrative", "body_fat_pct": "measurement", "kg_lo":
        "measurement", "kg_hi": "measurement", "body_fat_lo": "measurement",
        "body_fat_hi": "measurement", "measured_at": "temporal",
        "recorded_at": "temporal", "origin": "provenance", "path":
        "provenance", "origin_evidence": "provenance", "capture":
        "provenance", "read_by": "provenance", "modelled": "provenance",
        "artifact": "reference", "device": "provenance", "protocol":
        "provenance", "derived_from": "provenance", "derived_op":
        "provenance", "derived_by": "provenance", "derived_build":
        "provenance",
        "seq": "reference"

    },
}


def test_every_field_of_every_dataset_has_a_class():
    """NO DEFAULT, and that is the whole point rather than a strictness. The
    failure this removes is a fallback standing in for a decision nobody made;
    a default here would move that failure one layer in and make it the
    engine's."""
    for dataset, keys in KEYS.items():
        for key in keys:
            assert sensitivity(dataset, key) in SENSITIVITY_CLASSES, (
                f"{dataset}.{key}")


def test_a_field_nobody_classified_raises_rather_than_defaulting():
    """The behaviour that makes the pin below enforceable. A new field is an
    error at the point it is added, not a permissive answer at read time."""
    with pytest.raises(KeyError) as raised:
        sensitivity("daily", "a_field_nobody_has_classified")

    assert "no sensitivity class" in str(raised.value)


def test_no_class_has_moved_and_no_field_is_missing():
    """THE REVIEW SURFACE. The classes are a judgement, so the durable
    property is not that they are right but that changing one is visible and
    adding a field forces a decision. Same shape as #297's generation pin, for
    the same reason: a default standing in for a decision nobody made.
    """
    live = {ds: {k: sensitivity(ds, k) for k in keys}
            for ds, keys in KEYS.items()}

    assert set(live) == set(PINNED), "a dataset arrived or left"
    for ds in sorted(live):
        assert set(live[ds]) == set(PINNED[ds]), (
            f"{ds}: fields {sorted(set(live[ds]) ^ set(PINNED[ds]))} are not "
            "in the pin - what kind of disclosure is the new one?")
        moved = {k: (PINNED[ds][k], v) for k, v in live[ds].items()
                 if PINNED[ds][k] != v}
        assert not moved, f"{ds}: {moved}"


def test_one_name_can_mean_two_disclosures():
    """THE CASE THAT PROVES A PER-NAME MAP WRONG, and it is the one a client's
    copy got wrong: it called every `reason` clinical. On four datasets it is
    prose about a policy change; on `plans` it is a claim about why somebody
    did not train."""
    assert sensitivity("plans", "reason") == "behavioural"
    for dataset in ("goals", "events", "thresholds", "artifacts"):
        assert sensitivity(dataset, "reason") == "narrative", dataset


def test_free_text_about_an_injury_is_not_the_same_as_free_text():
    """The other override, and the same argument. A note on a `medical` row is
    a note about a health episode, and releasing it is a different disclosure
    from releasing a note about a route."""
    assert sensitivity("medical", "note") == "clinical"
    assert sensitivity("sessions", "note") == "narrative"


def test_the_overrides_stay_few():
    """An override is a place a name stopped carrying its meaning. A long list
    of them would say the names are wrong rather than that a dataset is
    unusual, so the count is pinned to make growth a decision."""
    assert sum(len(v) for v in SENSITIVITY_OVERRIDE.values()) <= 8


def test_the_class_is_not_the_datatype():
    """Published BESIDE the type rather than derived from it, because they are
    orthogonal and a consumer needs both. `pain` is a clinical NUMBER;
    `activity` is a reference that happens to be text. A client inferring the
    class from the type would gate the wrong half of the record."""
    daily = field_types("daily")["daily"]

    assert daily["pain"]["sensitivity"] == "clinical"
    assert daily["pain"]["affinity"] == "REAL"
    assert daily["note"]["sensitivity"] == "narrative"


# --- it is published, which is the point --------------------------------------

def test_it_reaches_the_accessor_consumers_already_read():
    """`field_types()` exists because consumers were guessing at the types.
    This is the same guess one layer up, so it lands in the same place rather
    than behind a new door nobody knows to open."""
    fields = field_types("plans")["plans"]

    assert fields["reason"]["sensitivity"] == "behavioural"
    assert set(fields["reason"]) >= {"types", "affinity", "container",
                                     "coarse_companion", "sensitivity"}


def test_the_three_surfaces_agree():
    """P9. A client gating egress reads this over MCP or the CLI, not by
    importing the module."""
    from vitai.api import schema as engine_schema
    from_api = engine_schema()["fields"]["plans"]["reason"]["sensitivity"]
    from_mcp = mcp.call(DEMO, "schema", {})["fields"]["plans"]["reason"]
    # `schema` takes no root: it is a property of the installed ENGINE
    # rather than of any one record, which is why a client can ask for it
    # before it has a record at all.
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "schema", "--json"],
        capture_output=True, text=True, check=True)
    from_cli = json.loads(out.stdout)["fields"]["plans"]["reason"]

    assert from_api == "behavioural"
    assert from_mcp["sensitivity"] == from_cli["sensitivity"] == from_api


def test_a_client_can_derive_its_whole_map_from_one_call():
    """The thing a consumer was hand-maintaining. If this cannot be built from
    the published shape in one pass, the copy stays."""
    published = field_types()

    derived = {(ds, f): spec["sensitivity"]
               for ds, fields in published.items() for f, spec in fields.items()}

    assert len(derived) == sum(len(v) for v in KEYS.values())
    assert set(derived.values()) <= SENSITIVITY_CLASSES


def test_the_precise_tier_is_classified_where_it_lives():
    """#205 introduced this idea for one field pair, and the general form has
    to agree with it: the precise tier is where the athlete is."""
    assert sensitivity("sessions", "place_precise") == "whereabouts"
    assert sensitivity("sessions", "place") == "whereabouts"
    assert field_types("sessions")["sessions"]["place_precise"][
        "coarse_companion"] == "place"
