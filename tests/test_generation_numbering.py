"""A generation is appended, never inserted (#295).

A dataset's generation is HOW MANY BUMP BLOCKS APPEAR ABOVE A POINT in
`schema.py`, and `_gen` is stamped into a line at append time and never
rewritten - correctly, because it is a fact about what the schema was when the
line was written. Put a new block above an existing one and every generation
below it shifts up by one, so a number already sitting in a record starts
denoting a LATER schema state than the one it was stamped under. G25's
exemption, `line_generation(rec) < key_generation(...)`, then reads a line as
owing a key that did not exist when it was written.

That happened. #287 added its block above two that already existed and moved
fourteen keys, and on a real record 140 lines that were compliant on the day
they were written started failing `validate` - 280 problems, none of them
about the contents.

WHY A TEST AND NOT A CONVENTION. The failure was SILENT AND RETROACTIVE:
nothing broke when the change merged, the record was correct, the engine was
correct, and the two disagreed only once a reader compared them. A convention
against inserting is worth having and would not have caught it, because
nothing was checking. And it repairs nothing already written: `_gen` cannot be
rewritten, and appending corrections would restate hundreds of rows to absorb
a numbering choice that was not the record's mistake.

So the whole table is pinned here as literal data. Adding a key adds a line.
Renumbering one CHANGES a line, in a diff that names it, at the point of
insertion - which is weeks before it would otherwise surface as a report about
somebody's record.

UPDATING THIS IS THE DELIBERATE ACT. A new key at the end of the table is the
ordinary case and needs no thought. A key whose number MOVED is the case this
exists for: it means lines already written have been reinterpreted, and the
question to answer before touching the numbers is whose records they are in.
"""

from __future__ import annotations

from vitai.schema import (CURRENT_GENERATION, KEY_GENERATION,
                          KEY_RETIREMENT, KEYS, validate_record)

PINNED = {
    "achievements": {
        "device": 4,
        "occurred_date": 2,
        "recorded_at": 3,
    },
    "artifacts": {
        "device": 3,
        "recorded_at": 2,
    },
    "checks": {
        "device": 3,
        "recorded_at": 2,
    },
    "context": {
        "device": 3,
        "place_precise": 4,
        "recorded_at": 2,
    },
    "daily": {
        "artifact": 7,
        "capture": 5,
        "carb_g": 10,
        "coverage": 2,
        "derived_build": 13,
        "derived_by": 13,
        "derived_from": 9,
        "derived_op": 9,
        "device": 8,
        "fat_g": 10,
        "feel": 2,
        "fibre_g": 10,
        "modelled": 6,
        "mood": 2,
        "mood_scale": 12,
        "origin": 4,
        "origin_evidence": 4,
        "pain": 2,
        "pain_scale": 12,
        "pain_side": 2,
        "pain_site": 2,
        "path": 4,
        "read_by": 5,
        "recorded_at": 3,
        "sleep_end": 11,
        "sleep_start": 11,
        "sodium_mg": 10,
        "source": 2,
        "sugar_g": 10,
    },
    "events": {
        "device": 3,
        "outcome": 4,
        "recorded_at": 2,
    },
    "goals": {
        "change_kind": 2,
        "deadline_kind": 2,
        "device": 4,
        "event": 2,
        "lifecycle_status": 6,
        "polarity": 5,
        "recorded_at": 3,
        "target_hi": 5,
        "verification": 2,
    },
    "inferences": {
        "depends_on": 2,
        "device": 4,
        "recorded_at": 3,
    },
    "journal": {
        "device": 3,
        "recorded_at": 2,
    },
    "meals": {
        "derived_build": 6,
        "derived_by": 6,
        "derived_from": 4,
        "derived_op": 4,
        "device": 3,
        "fibre_100g": 5,
        "recorded_at": 2,
        "sodium_mg_100g": 5,
        "sugar_100g": 5,
    },
    "measurements": {
        "artifact": 6,
        "capture": 4,
        "derived_build": 10,
        "derived_by": 10,
        "derived_from": 9,
        "derived_op": 9,
        "device": 7,
        "modelled": 5,
        "origin": 3,
        "origin_evidence": 3,
        "path": 3,
        "protocol": 8,
        "read_by": 4,
        "recorded_at": 2,
    },
    "medical": {
        "body_side": 6,
        "device": 5,
        "expects": 2,
        "onset_date": 2,
        "precondition": 2,
        "recorded_at": 4,
        "restriction": 3,
    },
    "sessions": {
        "activity_id": 4,
        "activity_source": 4,
        "artifact": 8,
        "capture": 6,
        "context": 2,
        "derived_build": 13,
        "derived_by": 13,
        "derived_from": 10,
        "derived_op": 10,
        "device": 9,
        "elevation_m": 2,
        "modelled": 7,
        "origin": 6,
        "origin_evidence": 6,
        "path": 6,
        "place": 2,
        "place_precise": 14,
        "planned": 2,
        "read_by": 6,
        "recorded_at": 3,
        "route": 2,
        "rpe_scale": 11,
        "setting": 2,
        "source": 2,
        "start_time": 2,
        "track": 4,
        "type_source": 7,
        "weather": 2,
        "with": 2,
    },
    "sets": {
        "angle_class": 3,
        "angle_deg": 3,
        "derived_build": 7,
        "derived_by": 7,
        "derived_from": 5,
        "derived_op": 5,
        "device": 4,
        "equipment": 3,
        "lever_pos": 3,
        "pad_pos": 3,
        "recorded_at": 2,
        "resistance_level": 3,
        "rpe_scale": 6,
        "seat_pos": 3,
    },
    "thresholds": {
        "device": 3,
        "recorded_at": 2,
    },
    "weight": {
        "artifact": 7,
        "body_fat_hi": 2,
        "body_fat_lo": 2,
        "body_fat_pct": 2,
        "capture": 5,
        "derived_build": 11,
        "derived_by": 11,
        "derived_from": 10,
        "derived_op": 10,
        "device": 8,
        "kg_hi": 2,
        "kg_lo": 2,
        "measured_at": 3,
        "modelled": 6,
        "origin": 4,
        "origin_evidence": 4,
        "path": 4,
        "protocol": 9,
        "read_by": 5,
        "recorded_at": 3,
    },
}

PINNED_FOUNDING = {
    "achievements": ["date", "goal", "note", "source", "title"],
    "artifacts": [
        "bytes", "captured_at", "date", "kind", "media_type", "note",
        "origin", "reason", "removed", "sha256"
    ],
    "checks": ["date", "note", "result", "slug", "source", "value"],
    "context": ["date", "facilities", "mode", "note", "place", "source"],
    "daily": [
        "active_min", "alcohol", "date", "distance_km", "hip_pain",
        "kcal_in", "kcal_out", "note", "protein_g", "rhr", "sleep_h",
        "steps"
    ],
    "emissions": [
        "basis_claims", "contract", "date", "device", "kind", "metric",
        "policy_asof", "recorded_at", "statement", "surface", "week"
    ],
    "events": [
        "date", "event_date", "immovable", "kind", "note", "place",
        "priority", "reason", "set_by", "slug", "status", "title"
    ],
    "goals": [
        "accountability", "dataset", "date", "deadline", "guard_pct",
        "metric", "motivator", "note", "on_miss", "on_period_end",
        "on_success", "period", "policy", "rationale", "reason",
        "session_type", "set_by", "slug", "status", "target", "title",
        "tracker"
    ],
    "inferences": [
        "confidence", "date", "evidence", "kind", "model", "note",
        "statement"
    ],
    "journal": [
        "about", "confidence", "date", "kind", "note", "source", "status",
        "text"
    ],
    "meals": [
        "capture", "carb_100g", "date", "fat_100g", "food_table", "grams",
        "grams_hi", "grams_lo", "item", "kcal_100g", "meal", "note",
        "origin", "origin_evidence", "path", "protein_100g", "read_by",
        "source"
    ],
    "measurements": ["date", "kind", "note", "source", "value"],
    "medical": [
        "body_site", "date", "kind", "note", "provider_type",
        "resolved_date", "restricts", "severity", "slug", "source",
        "status", "title"
    ],
    "plans": [
        "activity", "date", "device", "for_date", "for_phase", "note",
        "outcome", "reason", "recorded_at", "requires", "serves",
        "session_ref", "set_by", "setting", "slug", "supersedes", "tier"
    ],
    "protocols": ["date", "device", "recorded_at", "slug", "supersedes", "text"],
    "regimes": [
        "anchored_by", "dataset", "date", "device", "field", "from_date",
        "kind", "note", "recorded_at", "source", "supersedes", "text",
        "to_date"
    ],
    "sessions": [
        "avg_hr", "cadence", "date", "distance_km", "duration_s", "kcal",
        "location", "max_hr", "note", "rpe", "type"
    ],
    "sets": [
        "block", "capture", "date", "duration_s", "exercise", "failure",
        "load", "load_type", "load_unit", "machine", "note", "origin",
        "origin_evidence", "path", "read_by", "reps_attempted",
        "reps_completed", "rest_s", "rir", "round", "rpe", "session_start",
        "set_index", "set_type", "side", "source", "tempo"
    ],
    "thresholds": ["change_kind", "date", "key", "note", "reason", "set_by", "value"],
    "weight": ["date", "kg", "note", "source"],
}

PINNED_RETIREMENT = {
    "daily": {"hip_pain": 2},
    "goals": {"status": 6},
    "sessions": {"location": 2, "planned": 12},
}

PINNED_CURRENT = {
    "achievements": 4,
    "artifacts": 3,
    "checks": 3,
    "context": 4,
    "daily": 13,
    "emissions": 1,
    "events": 4,
    "goals": 6,
    "inferences": 4,
    "journal": 3,
    "meals": 6,
    "measurements": 10,
    "medical": 6,
    "plans": 1,
    "protocols": 1,
    "regimes": 1,
    "sessions": 14,
    "sets": 7,
    "thresholds": 3,
    "weight": 11,
}



def _plausible(dataset: str) -> dict:
    """The few values a row of this dataset needs to get past the CONTENT
    checks, so what is left is the generation question this file is about."""
    common = {"date": "2030-05-01"}
    return common | {
        "weight": {"kg": 80.0, "source": "scale"},
        "daily": {"steps": 9000, "source": "athlete"},
        "sessions": {"type": "run", "distance_km": 5.0, "source": "watch"},
        "measurements": {"kind": "waist_cm", "value": 90.0, "source": "tape"},
        "meals": {"meal": "lunch", "item": "soup", "source": "athlete"},
        "sets": {"exercise": "push-up", "set_index": 1, "reps_completed": 5,
                 "session_start": "2030-05-01T08:00:00+02:00"},
        "goals": {"slug": "a-goal", "title": "a goal", "metric": "steps",
                  "target": 10000, "policy": "monotonic", "period": "daily",
                  "dataset": "daily"},
        "thresholds": {"key": "rhr_high", "value": 70.0},
        "medical": {"slug": "an-episode", "kind": "injury", "site": "knee",
                    "status": "open"},
        "events": {"slug": "an-event", "title": "an event",
                   "event_date": "2030-06-01", "kind": "race"},
        "protocols": {"slug": "a-protocol", "text": "do the thing"},
        "plans": {"slug": "a-plan", "for_date": "2030-05-02",
                  "activity": "run", "tier": "committed",
                  "outcome": "unresolved"},
        "achievements": {"kind": "distance", "detail": "first 10k"},
        "checks": {"slug": "a-check", "result": "pass"},
        "context": {"mode": "normal", "source": "athlete"},
        "journal": {"kind": "claim", "text": "a note"},
        "inferences": {"kind": "pattern", "statement": "a guess",
                       "confidence": 0.4, "model": "a-model"},
        "artifacts": {"sha256": "a" * 64, "media_type": "image/png",
                      "bytes": 1, "kind": "photo"},
        "regimes": {"kind": "estimated", "dataset": "weight", "field": "kg",
                    "from_date": "2030-05-01", "to_date": "2030-05-02",
                    "text": "a regime", "source": "athlete"},
        "emissions": {"kind": "verdict", "metric": "weight_rate",
                      "statement": "a statement", "surface": "cli",
                      "policy_asof": "2030-05-01", "contract": "1"},
    }.get(dataset, {})


def test_no_key_has_been_renumbered():
    """The whole of it, in one comparison, so a shift cannot hide among the
    keys that did not move."""
    live = {ds: dict(sorted(ks.items()))
            for ds, ks in sorted(KEY_GENERATION.items()) if ks}

    moved = {f"{ds}.{k}": (PINNED[ds][k], g)
             for ds, ks in live.items() for k, g in ks.items()
             if k in PINNED.get(ds, {}) and PINNED[ds][k] != g}

    assert set(live) == set(PINNED), "a dataset gained or lost its registry"
    for ds in live:
        assert set(live[ds]) == set(PINNED[ds]), (
            f"{ds}: registered keys are {sorted(set(live[ds]) ^ set(PINNED[ds]))} "
            "away from the pin. A key absent from the pin is silently skipped "
            "by the comparison below, so it could be renumbered freely")
    assert not moved, (
        f"{len(moved)} key(s) changed generation: {moved}. A number already "
        "stamped into records now denotes a different schema state, so lines "
        "that were compliant when written will fail validate. If a bump block "
        "was added above an existing one, move it below them instead")


def test_nothing_has_lost_its_generation():
    """A key dropping out of the table is the same defect wearing an absence:
    it falls back to generation 1, so every line is held to it."""
    live = {ds: set(ks) for ds, ks in KEY_GENERATION.items()}

    lost = {f"{ds}.{k}" for ds, ks in PINNED.items() for k in ks
            if k not in live.get(ds, set())}

    assert not lost, f"{sorted(lost)} lost their registered generation"


def test_the_current_generation_of_each_dataset_is_pinned_too():
    """`CURRENT_GENERATION` is what `append` stamps, so a shift there changes
    what every row written from now on claims about itself."""
    moved = {ds: (was, CURRENT_GENERATION[ds]) for ds, was in PINNED_CURRENT.items()
             if CURRENT_GENERATION.get(ds) != was}

    assert not moved, f"the stamped generation moved for {moved}"


def test_every_registered_key_is_a_key_of_its_dataset():
    """A registration for a key that is not in `KEYS` exempts nothing and
    reads as covered."""
    for ds, keys in KEY_GENERATION.items():
        stray = sorted(set(keys) - set(KEYS.get(ds, ())))
        assert not stray, f"{ds} registers generations for {stray}"


def test_a_generation_is_never_ahead_of_its_dataset():
    """A key registered above the dataset's current generation can never be
    required, so it is a key nothing will ever ask for."""
    for ds, keys in KEY_GENERATION.items():
        for key, gen in keys.items():
            assert gen <= CURRENT_GENERATION[ds], f"{ds}.{key} is {gen}"


# --- the reported failure, as a regression test -------------------------------

def test_a_line_written_before_a_key_existed_still_validates():
    """THE ROWS THE ISSUE COUNTED. A `daily` line stamped at generation 11 or
    12 was written before `derived_by` existed and was complete on the day it
    was written. After the insertion those numbers denoted a later schema
    state, so 135 of them started owing a key that had not been invented.
    """
    for gen in (11, 12):
        row = {k: None for k in KEYS["daily"]
               if k not in ("derived_by", "derived_build")}
        row.update({"date": "2030-05-01", "steps": 9000,
                    "source": "athlete", "_gen": gen})

        assert validate_record("daily", row) == [], gen


def test_the_sessions_rows_too():
    """Five of them, at generation 11 under the old numbering."""
    for gen in (10, 11):
        row = {k: None for k in KEYS["sessions"]
               if k not in ("derived_by", "derived_build")}
        row.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                    "source": "watch", "_gen": gen})

        assert validate_record("sessions", row) == [], gen


def test_every_reachable_stamp_still_validates():
    """THE SAFETY ARGUMENT, CHECKED RATHER THAN ASSERTED, and the first version
    of this was a tautology: it compared `{g < n}` against `{g < n+1}` over a
    range, which is set arithmetic that never touches the engine and cannot
    fail under any code change at all.

    The property that matters is not "raising a number exempts more" - most of
    these numbers went DOWN relative to the engine that was deployed. It is
    that no reachable `_gen` value holds a line to a key it could not have had.
    So this builds, for every generation each dataset has ever been at, the row
    an engine at that state would have written - complete from the keys
    registered at or below it - and validates it.
    """
    for dataset, current in sorted(CURRENT_GENERATION.items()):
        registered = KEY_GENERATION.get(dataset, {})
        for gen in range(1, current + 1):
            row = {k: None for k in KEYS[dataset]
                   if registered.get(k, 1) <= gen}
            # Only the values that EXIST at this generation: a content field
            # registered above it did not exist yet, and supplying it would be
            # testing a row no engine could have written.
            row.update({k: v for k, v in _plausible(dataset).items()
                        if k in row})
            row["_gen"] = gen

            problems = [p for p in validate_record(dataset, row)
                        if "missing key" in p or "unknown key" in p]

            assert not problems, f"{dataset} at generation {gen}: {problems}"


def test_no_key_arrives_without_a_generation():
    """A key in `KEYS` with no entry in `KEY_GENERATION` defaults to generation
    1, so EVERY line in every record is held to it - the loudest version of
    this defect, and the third cause the validate message names.

    A founding key legitimately has no entry, and the code cannot tell one from
    a key somebody forgot to register: both are simply absent. So the founding
    set is pinned. Adding a key without a generation changes this list, and the
    diff asks the only question that matters - was this key there from the
    beginning, or does it need a number?

    Pinned here rather than left to the corpus, because #287 is the proof that
    corpus tests miss generation defects: its fixtures were regenerated in the
    same change, so they agreed with the broken numbering and stayed green.
    """
    live = {ds: sorted(set(keys) - set(KEY_GENERATION.get(ds, {})))
            for ds, keys in sorted(KEYS.items())}

    changed = {ds: (PINNED_FOUNDING.get(ds), ks)
               for ds, ks in live.items() if PINNED_FOUNDING.get(ds) != ks}

    assert not changed, (
        f"the founding key set moved for {sorted(changed)}. A key with no "
        "registered generation defaults to 1, so every line in every record "
        "is held to it - if this key is new, give it a generation")


def test_no_retirement_has_been_renumbered():
    """THE FIFTEENTH NUMBER, and the one nothing was watching. A retirement
    shifts by exactly the same mechanism - `sessions.planned` moved 12 to 13
    with the rest - and it is the easiest to forget because nothing about it
    looks like a key. Restoring it silently would have left the next
    insertion's retirement damage unnamed."""
    live = {ds: dict(sorted(ks.items()))
            for ds, ks in sorted(KEY_RETIREMENT.items()) if ks}

    moved = {f"{ds}.{k}": (PINNED_RETIREMENT[ds][k], g)
             for ds, ks in live.items() for k, g in ks.items()
             if k in PINNED_RETIREMENT.get(ds, {})
             and PINNED_RETIREMENT[ds][k] != g}

    assert not moved, f"{len(moved)} retirement(s) changed generation: {moved}"
    assert live == PINNED_RETIREMENT, "a retirement was added or lost"


# --- the message an old line gets (#296) --------------------------------------

def test_the_message_does_not_address_a_writer():
    """`append` rebuilds every row from `KEYS`, so a caller cannot omit a key
    and no line the engine wrote can trip this. "use null for unknown, never
    omit" was advice about something the writer could not have done
    differently, on every one of the 280 rows."""
    row = {k: None for k in KEYS["daily"] if k != "pain_site"}
    row.update({"date": "2030-05-01", "steps": 9000, "source": "athlete",
                "_gen": 13})

    problem, = validate_record("daily", row)

    assert "never omit" not in problem
    assert "generation 13" in problem and "generation 2" in problem


def test_the_message_does_not_claim_the_line_predates_the_key():
    """A DIRECTION THIS GOT WRONG ONCE. The branch fires only where the key's
    generation is at or BELOW the line's, so the line appears to postdate the
    key - and the first draft said the line predates it, which would have sent
    a reader looking for the wrong thing on every row."""
    row = {k: None for k in KEYS["daily"] if k != "pain_site"}
    row.update({"date": "2030-05-01", "steps": 9000, "source": "athlete",
                "_gen": 13})

    problem, = validate_record("daily", row)

    assert "predates" not in problem
    assert "existed when the line was written" in problem


def test_the_message_names_both_causes():
    """A writer that is not this engine, or a generation that moved. They need
    different answers, and a message naming one sends half its readers to the
    wrong place."""
    row = {k: None for k in KEYS["daily"] if k != "pain_site"}
    row.update({"date": "2030-05-01", "steps": 9000, "source": "athlete",
                "_gen": 13})

    problem, = validate_record("daily", row)

    assert "not this engine" in problem
    assert "MOVED" in problem
    # AND THE THIRD, which the first draft left out: a key added to `KEYS`
    # with no registration defaults to generation 1 and fires this on every
    # line in the record. A message naming two causes sends a reader with the
    # third one looking in two wrong places.
    assert "never registered a generation" in problem
    assert "THREE THINGS" in problem
