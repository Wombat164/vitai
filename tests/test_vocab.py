"""Vocabularies as registries (G85, issue #18).

Synthetic data only (public repo).

The two tests that justify the whole change are
`test_no_loaded_hip_work_still_permits_squats` and
`test_no_loaded_lumbar_flexion_is_expressible`: both are real clinical gates
that sat in a record with `restricts: null` and a RESTRICTION NOT ENFORCEABLE
marker, because no value in the old flat vocabulary could express them. An
athlete with an active injury gate got "no active safety escalations".
"""

import pytest

from vitai import vocab
from vitai.safety import gates_on, is_gated, is_movement_gated, session_classes
from vitai.schema import validate_record


def medical(date="2030-05-01", slug="hip", title="Hip", **kw):
    rec = {"date": date, "slug": slug, "kind": "injury", "title": title,
           "body_site": None, "severity": "moderate", "status": "active",
           "resolved_date": None, "restricts": None, "provider_type": None,
           "source": "athlete", "note": None, "expects": None,
           "onset_date": None, "precondition": None, "restriction": None,
           "_gen": 3}
    rec.update(kw)
    return rec


# ---- the two clinical gates --------------------------------------------------

HIP_THRUST = {"pattern": "hinge", "region": "hip", "load": "loaded"}
SQUAT = {"pattern": "squat", "region": "hip", "load": "loaded"}
BODYWEIGHT_BRIDGE = {"pattern": "hinge", "region": "hip", "load": "bodyweight"}
CRUNCH = {"pattern": "flexion", "region": "lower_back", "load": "loaded"}


def test_no_loaded_hip_work_still_permits_squats():
    """The sharp one. `lower_body` would have banned the squats the clinician
    explicitly permitted, which is why the gate was left unenforced."""
    episode = medical(restriction="pattern=hinge region=hip load=loaded",
                      title="No loaded hip work")
    gates = gates_on([episode], "2030-05-10")
    assert len(gates) == 1, "a structured-only restriction must produce a gate"
    assert is_movement_gated(gates, HIP_THRUST) is True
    assert is_movement_gated(gates, SQUAT) is False, (
        "the permitted movement must stay permitted")


def test_bodyweight_is_left_alone_by_a_loaded_restriction():
    gates = gates_on([medical(restriction="pattern=hinge region=hip load=loaded")],
                     "2030-05-10")
    assert is_movement_gated(gates, BODYWEIGHT_BRIDGE) is False


def test_no_loaded_lumbar_flexion_is_expressible():
    episode = medical(restriction="pattern=flexion region=lumbar load=loaded",
                      title="No loaded lumbar flexion")
    assert validate_record("medical", episode) == []
    gates = gates_on([episode], "2030-05-10")
    assert is_movement_gated(gates, CRUNCH) is True
    assert is_movement_gated(gates, SQUAT) is False


def test_an_absent_axis_means_any():
    """`pattern=flexion` alone catches flexion anywhere."""
    gates = gates_on([medical(restriction="pattern=flexion")], "2030-05-10")
    assert is_movement_gated(gates, CRUNCH) is True
    assert is_movement_gated(gates, {"pattern": "flexion", "region": "neck"}) is True
    assert is_movement_gated(gates, SQUAT) is False


def test_an_undescribed_movement_is_not_shown_to_be_restricted():
    """A restriction narrows. A movement nobody described cannot be proven to
    fall inside one, so it does not match - the engine does not guess."""
    gates = gates_on([medical(restriction="pattern=hinge region=hip load=loaded")],
                     "2030-05-10")
    assert is_movement_gated(gates, {"pattern": "hinge"}) is False


def test_a_region_restriction_catches_the_sites_beneath_it():
    gates = gates_on([medical(restriction="region=lower_limb")], "2030-05-10")
    assert is_movement_gated(gates, {"region": "knee"}) is True
    assert is_movement_gated(gates, {"region": "shoulder"}) is False


def test_a_cleared_precondition_lifts_a_structured_gate_too():
    episode = medical(restriction="pattern=hinge region=hip load=loaded",
                      restricts="strength", precondition="hop-test")
    gates = gates_on([episode], "2030-05-10",
                     checks=[{"date": "2030-05-10", "slug": "hop-test",
                              "result": "pass", "value": None,
                              "source": "athlete", "note": None}])
    assert is_movement_gated(gates, HIP_THRUST) is False


# ---- restriction parsing -----------------------------------------------------

def test_a_restriction_resolves_aliases_through_the_body_site_registry():
    """"do not invent a second anatomy" - region reuses body_sites.toml."""
    assert vocab.parse_restriction("region=lumbar")["region"] == "lower_back"
    assert vocab.parse_restriction("region=lumbar spine")["region"] == "lower_back"


def test_pattern_aliases_take_the_athletes_words():
    assert vocab.parse_restriction("pattern=deadlift")["pattern"] == "hinge"
    assert vocab.parse_restriction("pattern=crunch")["pattern"] == "flexion"
    assert vocab.parse_restriction("pattern=bench press")["pattern"] == "push"


def test_a_typo_is_a_loud_error_not_a_narrower_gate():
    problems = vocab.restriction_problems("pattern=hnige region=hip")
    assert problems and "unknown pattern" in problems[0]
    assert any("hinge" in p for p in problems), "the error lists the options"


def test_an_unknown_axis_is_rejected():
    assert any("axis" in p for p in vocab.restriction_problems("colour=blue"))


def test_a_restriction_needs_at_least_one_axis():
    assert vocab.restriction_problems("   ") == []          # absent is fine
    assert vocab.restriction_problems("nonsense") != []      # gibberish is not


def test_the_validator_rejects_a_bad_restriction():
    assert any("unknown pattern" in p for p in validate_record(
        "medical", medical(restriction="pattern=levitate")))


# ---- session types -----------------------------------------------------------

def test_the_vocabulary_is_not_one_athletes_programme():
    """`gym_a` is one person's Strength A day. Nobody else has one."""
    types = vocab.session_types()
    assert "gym_a" not in types and "gym_b" not in types
    for sport in ("cycle", "swim", "row", "climb", "sport", "paddle",
                  "wintersport", "mobility", "strength"):
        assert sport in types, sport


def test_retired_programme_labels_still_resolve():
    """An old line carrying `gym_a` is history, not an error."""
    assert vocab.resolve_session_type("gym_a") == "strength"
    assert vocab.resolve_session_type("gym_b") == "strength"
    assert vocab.is_retired("session_types", "gym_a") is True
    assert validate_record("sessions", {
        "date": "2030-05-01", "type": "gym_a", "distance_km": None,
        "duration_s": None, "avg_hr": None, "max_hr": None, "cadence": None,
        "kcal": None, "location": None, "rpe": None, "note": None}) == []


def test_an_athletes_own_words_resolve():
    """`yoga` and `tennis` used to fold into the coarse `mobility` and
    `sport`. They are now values in their own right, because the activity
    axis carries Strava's 50 sport types (#53) - so the expectations change
    deliberately rather than the vocabulary being bent to fit them.

    The coarse values still exist and still resolve; what changed is that a
    named activity is no longer flattened into its category.
    """
    for written, expect in [("cycling", "cycle"), ("bike", "cycle"),
                            ("Swimming", "swim"), ("erg", "row"),
                            ("yoga", "yoga"), ("bouldering", "climb"),
                            ("tennis", "tennis"), ("weights", "strength"),
                            ("some winter sport", None)]:
        assert vocab.resolve_session_type(written) == expect, written
    # The coarse values are still legal for an athlete who only knows that much.
    assert vocab.resolve_session_type("wintersport") == "wintersport"


def test_session_classes_come_from_the_registry():
    assert "impact" in session_classes("run")
    assert "cardio" in session_classes("cycle")
    assert session_classes("gym_a") == session_classes("strength"), (
        "a retired label gates exactly as its replacement does")


def test_a_gate_on_an_activity_class_still_works():
    """The coarse path is unchanged - it is a projection, not a casualty."""
    gates = gates_on([medical(restricts="run impact")], "2030-05-10")
    assert is_gated(gates, "run") is True
    assert is_gated(gates, "cycle") is False
    assert is_gated(gates, "swim") is False


def test_an_impact_gate_now_reaches_sports_it_used_to_miss():
    gates = gates_on([medical(restricts="impact")], "2030-05-10")
    assert is_gated(gates, "sport") is True, "team sport is impact loading"
    assert is_gated(gates, "swim") is False


# ---- registry hygiene --------------------------------------------------------

@pytest.mark.parametrize("name,section", [
    ("session_types", "types"), ("restrictions", "pattern"),
    ("restrictions", "load"), ("restrictions", "plane"),
    ("restrictions", "activity")])
def test_every_registry_entry_has_a_label(name, section):
    for slug in vocab.values(name, section):
        assert vocab.meta(name, section, slug).get("label"), f"{name}.{slug}"


def test_no_alias_is_claimed_twice_in_one_section():
    """One spelling mapping to two values would make resolution a coin toss."""
    for name, section in (("session_types", "types"), ("restrictions", "pattern")):
        seen: dict[str, str] = {}
        for slug in vocab.values(name, section):
            for alias in vocab.meta(name, section, slug).get("aliases", []):
                key = alias.lower()
                assert key not in seen, f"{alias!r}: {seen.get(key)} vs {slug}"
                seen[key] = slug


def test_session_type_classes_are_all_real_activity_classes():
    """The two registries must stay in step, or a gate silently misses."""
    known = set(vocab.activity_classes())
    for slug in vocab.session_types():
        for cls in vocab.session_classes(slug):
            assert cls in known, f"{slug} declares unknown class {cls!r}"


def test_every_retired_value_maps_somewhere_real():
    for name, section in (("session_types", "types"), ("restrictions", "activity")):
        for old, meta in vocab.retired(name).items():
            assert meta.get("maps_to") in vocab.values(name, section), old
            assert meta.get("reason"), f"{old} retired without a reason"


# ---- couplings the vocabulary change could have broken silently -------------

def test_the_rollup_counts_strength_sessions_by_class_not_by_prefix(tmp_path):
    """`startswith("gym")` silently zeroed the weekly strength column the
    moment the vocabulary was renamed, and no test covered it."""
    from vitai.config import Config
    from vitai.report import build_report
    sessions = [{"date": "2030-05-01", "type": t, "distance_km": None,
                 "duration_s": 3600, "avg_hr": None, "max_hr": None,
                 "cadence": None, "kcal": None, "location": None, "rpe": 5,
                 "note": None}
                for t in ("strength", "gym_a")]
    text = build_report(Config(), [], [], sessions, today=None)
    assert "## Training by week" in text
    # both the current and the retired label land in the strength column
    row = [ln for ln in text.splitlines() if "2030-04-29" in ln]
    assert row and " 2 " in row[0], row


def test_a_weight_goal_can_be_scoped_to_the_weight_dataset():
    """G86: the most common goal in the domain had nowhere to point."""
    goal = {"date": "2030-05-01", "slug": "cut", "title": "Get to 74 kg",
            "metric": "kg", "dataset": "weight", "session_type": None,
            "tracker": None, "target": 74.0, "policy": "monotonic",
            "guard_pct": None, "period": "none", "on_period_end": None,
            "deadline": None, "status": "active", "motivator": None,
            "rationale": None, "on_success": None, "on_miss": None,
            "accountability": None, "set_by": "athlete", "reason": None,
            "note": None}
    assert validate_record("goals", goal) == []
    assert any("dataset" in p for p in validate_record(
        "goals", {**goal, "dataset": "astrology"}))


def test_no_session_type_ever_loses_a_restriction_class():
    """The near-miss that earned this test.

    Regenerating `session_types.toml` for #53 silently dropped `impact` from
    the coarse `sport`, `run`+`impact` from `test`, and `lower_body` from
    `swim` and `wintersport`. Every one of those is safety-bearing: an impact
    gate would have stopped blocking team sport, and nothing in the suite
    said so except one test that happened to cover `sport`.

    A registry is data, and data can be regenerated. This asserts the
    property that must survive any regeneration: a type's classes may GROW,
    never shrink, because shrinking them silently unblocks something a
    clinician blocked.
    """
    baseline = {
        "run": {"run", "impact", "cardio", "lower_body"},
        "walk": {"walk", "cardio", "lower_body"},
        "cycle": {"cycle", "cardio", "lower_body"},
        "swim": {"swim", "cardio", "upper_body", "lower_body"},
        "row": {"row", "cardio", "upper_body", "lower_body"},
        "strength": {"strength", "upper_body", "lower_body"},
        "climb": {"climb", "upper_body", "strength"},
        "sport": {"sport", "impact", "cardio"},
        "wintersport": {"wintersport", "cardio", "lower_body"},
        "paddle": {"paddle", "cardio", "upper_body"},
        "mobility": {"mobility"},
        "test": {"cardio", "run", "impact"},
    }
    for slug, must_have in baseline.items():
        got = session_classes(slug)
        assert must_have <= got, f"{slug} lost {sorted(must_have - got)}"


def test_every_class_a_type_claims_is_a_real_restriction_class():
    """A class no rule understands is an unenforced gate - the precise harm
    the restriction rework removed.

    Checked against the REGISTRY's classes, not `safety.session_classes`,
    which deliberately falls back to the activity's own name so that a gate
    naming an unrecognised activity directly still bites. That fallback is
    not a class claim and must not be read as one.
    """
    legal = set(vocab.axis_values("activity"))
    for slug in vocab.session_types():
        unknown = set(vocab.session_classes(slug)) - legal
        assert not unknown, f"{slug} claims unknown class(es) {sorted(unknown)}"


# ---- #53: the 50 sport types, and setting as its own axis ----------------------

def test_the_activity_axis_carries_stravas_sport_types():
    """Sourced, not hand-assembled: Strava's `SportType` is exactly 50 values,
    a maintained consumer-grade taxonomy. 47 are adopted as values here."""
    types = vocab.registry("session_types")["types"]
    named = {m["strava"] for m in types.values() if m.get("strava")}
    assert len(named) == 47
    for expected in ("Run", "Ride", "Elliptical", "StandUpPaddling",
                     "HighIntensityIntervalTraining", "Pickleball"):
        assert expected in named, expected


def test_the_three_pre_coordinated_strava_types_are_not_values():
    """`VirtualRun` bundles an activity with a modality, which is the defect
    the whole registry exists to avoid. They resolve, and they resolve to the
    ACTIVITY - the modality belongs in `setting`."""
    types = vocab.registry("session_types")["types"]
    named = {m.get("strava") for m in types.values()}
    for pre in ("VirtualRun", "VirtualRide", "VirtualRow"):
        assert pre not in named, f"{pre} must not be an activity value"
    assert vocab.resolve_session_type("VirtualRun") == "run"
    assert vocab.resolve_session_type("VirtualRide") == "cycle"
    assert vocab.resolve_session_type("VirtualRow") == "row"


def test_the_catchall_is_an_activity_plus_a_setting():
    """What the athlete asked for, decomposed. `outdoor_other` is not an
    activity; Polar's OTHER_OUTDOOR resolves to the activity half and the
    setting is recorded separately."""
    assert vocab.resolve_session_type("OTHER_OUTDOOR") == "other"
    assert vocab.resolve_setting("outdoor") == "outdoor"


def test_no_value_pre_coordinates_activity_with_setting():
    """The invariant, asserted rather than trusted: no activity value may
    carry a setting word, and no setting may carry an activity."""
    settings = set(vocab.settings()) | {"treadmill", "home"}
    for slug in vocab.session_types():
        parts = set(slug.split("_"))
        assert not (parts & settings), f"{slug} bakes a setting into an activity"
    for slug in vocab.settings():
        assert slug not in vocab.session_types(), slug


def test_the_names_that_fell_into_other_now_resolve():
    """436 of 1,502 imported activities landed in `other` (29%). These are
    the examples the issue named, and they resolve by CURATED ALIAS - nothing
    fuzzy-matches, so a name nobody mapped still reports as unmapped."""
    for written, expect in [("Outdoor Bike", "cycle"),
                            ("Elliptical Trainer", "elliptical"),
                            ("Sport", "sport"),
                            ("MountainBikeRide", "mountain_bike_ride"),
                            ("crosstrainer", "elliptical")]:
        assert vocab.resolve_session_type(written) == expect, written


def test_an_unmapped_name_stays_unmapped():
    """The discipline that must survive: the importer reports rather than
    guesses. A matcher that turns 'Running (jogging), 9 mph' into `run` will
    also turn something else into `run` silently, and nobody will find out."""
    assert vocab.resolve_session_type("Running (jogging), 9 mph") is None
    assert vocab.resolve_session_type("Elliptical, High Resistance") is None
    assert vocab.resolve_session_type("Water Sport") is None


def test_a_healthkit_type_maps_outward():
    """An Apple Health import maps onto this axis rather than needing its own
    vocabulary. Mapped outward, never vendored."""
    assert vocab.resolve_session_type("HKWorkoutActivityTypeYoga") == "yoga"
    assert vocab.resolve_session_type("HKWorkoutActivityTypeElliptical") == "elliptical"


def test_a_retired_setting_still_resolves():
    assert vocab.resolve_setting("treadmill") == "indoor"
    assert vocab.resolve_setting("home") == "indoor"
    assert "treadmill" not in vocab.settings(), "legal, no longer offered"


# ---- the frontal-plane pair (#58) ---------------------------------------------------

def test_a_hip_adduction_machine_is_describable():
    """Found live, on a machine the athlete was about to load. Twelve
    patterns and none of them named adduction, so about as direct a loaded
    hip movement as a gym contains could not be described by the restriction
    system that exists to protect a hip.
    """
    from vitai.vocab import parse_restriction
    spec = parse_restriction("pattern=adduction region=hip load=loaded")
    assert spec == {"pattern": "adduction", "region": "hip", "load": "loaded"}


def test_a_hip_restriction_can_name_adduction_without_banning_the_plane():
    """The acceptance criterion, and the reason `plane=frontal` is not a
    substitute: it would also catch abduction, lateral lunges and side planks
    - a far wider ban than any clinician said, and over-restriction is its
    own harm.
    """
    from vitai.vocab import parse_restriction, restriction_matches
    spec = parse_restriction("pattern=adduction region=hip load=loaded")
    adduction = {"pattern": "adduction", "region": "hip", "load": "loaded"}
    assert restriction_matches(spec, adduction) is True
    for spared in ({"pattern": "abduction", "region": "hip", "load": "loaded"},
                   {"pattern": "lunge", "region": "hip", "load": "loaded"},
                   {"pattern": "isometric", "region": "hip",
                    "load": "bodyweight"}):
        assert restriction_matches(spec, spared) is False, spared


def test_the_plane_axis_is_not_used_as_a_proxy():
    """A plane is WHERE a movement happens; a pattern is what it does. The
    two stay separate axes, and neither stands in for the other."""
    from vitai.vocab import axis_values
    assert set(axis_values("plane")) == {"frontal", "sagittal", "transverse"}
    assert "frontal" not in axis_values("pattern")
    assert "adduction" not in axis_values("plane")


def test_the_pair_completes_a_vocabulary_already_half_adopted():
    """Grounded rather than invented: this registry already carries
    `flexion`, `extension` and `rotate` from standard planes-of-motion
    terminology, so adding its remaining pair finishes that adoption instead
    of starting a second taxonomy (G85)."""
    from vitai.vocab import axis_values
    planes_of_motion = {"flexion", "extension", "rotate", "adduction",
                        "abduction"}
    assert planes_of_motion <= set(axis_values("pattern"))


def test_the_machine_spellings_resolve():
    """A restriction is written by hand and by a screenshot-reading skill,
    so the words on the machine resolve."""
    from vitai.vocab import resolve_axis
    assert resolve_axis("pattern", "adductor machine") == "adduction"
    assert resolve_axis("pattern", "hip abduction") == "abduction"
    assert resolve_axis("pattern", "inner thigh") == "adduction"
