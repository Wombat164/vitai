"""The exercise registry, and what makes a restriction checkable (#98).

Synthetic data only (public repo), fictional athlete, 2030 dates. The registry
is the world's gym catalogue, never one athlete's programme - that is the
`gym_a`/`gym_b` lesson (G85), and it is why nothing here is named after
anybody's session.
"""

import pytest

from vitai.exercises import (entry, exercises, gate_check, load_of,
                             movement_of, patterns_of, problems, regions_of,
                             registry_problems, resolve_exercise)
from vitai.schema import validate_record
from vitai.vocab import axis_values, parse_restriction


def a_set(exercise="push-up", **kw):
    row = {"date": "2030-05-01", "session_start": "2030-05-01T07:10:00+02:00",
           "exercise": exercise, "block": 1, "round": None, "set_index": 1,
           "reps_completed": 10, "reps_attempted": 10,
           "load": None, "load_type": "bodyweight", "load_unit": None,
           "machine": None, "set_type": "working", "failure": None,
           "rir": None, "rpe": None, "rest_s": 90, "tempo": None,
           "duration_s": None, "side": None, "note": None,
           "source": "stated-in-chat", "recorded_at": None,
           "origin": "athlete", "path": None, "origin_evidence": None,
           "capture": "narrative", "read_by": "athlete"}
    row.update(kw)
    return row


# The gate from the live record, in its post-coordinated form.
NO_LOADED_HIP = parse_restriction("pattern=hinge region=hip load=loaded")


# ---- the registry borrows its axes; it does not invent them ---------------------------

def test_every_entry_uses_the_vocabularies_that_already_exist():
    """A typo'd pattern must not silently create a new one. Borrowing the
    axes is what keeps restrictions and sets joinable, and that is the whole
    defect being fixed - so this is the test that guards the design.
    """
    assert registry_problems() == []


def test_the_seed_covers_the_common_catalogue():
    assert len(exercises()) >= 100


def test_no_entry_pre_coordinates_a_modifier():
    """`incline_dumbbell_bench_press` never becomes an entry - it is
    `bench-press` + equipment + angle (#99). FIT's hundreds of fused enum
    values are the counter-example: a vocabulary that pre-coordinates
    multiplies by the size of every axis it folds in, and can then answer a
    question about none of them.
    """
    for slug in exercises():
        assert "_" not in slug, slug
        assert slug == slug.lower(), slug
    # EVERY token, not just the first: `trap-bar-deadlift`, `landmine-row`,
    # `assisted-dip` and `bodyweight-squat` all passed a first-token check
    # while pre-coordinating equipment, assistance or the load axis itself.
    fused = {"incline", "decline", "dumbbell", "barbell", "cable", "smith",
             "wide", "narrow", "close", "trap", "landmine", "assisted",
             "bodyweight", "machine", "seated", "standing", "band"}
    for slug in exercises():
        for token in slug.split("-"):
            assert token not in fused, f"{slug} pre-coordinates {token!r}"


def test_a_variant_and_its_base_movement_group_together():
    """`bodyweight-squat` beside `squat` recreated the pushup/press-up defect
    INSIDE the registry: a squat query did not group them."""
    for spelling in ("air squat", "bodyweight squat", "smith machine squat"):
        assert resolve_exercise(spelling) == "squat", spelling
    assert resolve_exercise("assisted pull-up") == "pull-up"
    assert resolve_exercise("trap-bar deadlift") == "deadlift"


def test_bench_press_is_one_entry_that_modifiers_post_coordinate_onto():
    """The #59 test, verbatim in intent: the three halves are representable
    without a fused token existing anywhere."""
    assert resolve_exercise("bench press") == "bench-press"
    assert resolve_exercise("incline dumbbell bench press") == "unknown"
    assert "incline-dumbbell-bench-press" not in exercises()


def test_a_region_is_a_list_because_a_movement_loads_several():
    """Forcing one value would make the registry assert a primary mover,
    which is a modelling claim rather than an observation."""
    assert set(regions_of("push-up")) >= {"chest", "shoulder"}
    assert len(regions_of("push-up")) > 1


def test_every_entry_says_where_it_came_from():
    """The licence position, per entry: free-exercise-db is the Unlicense and
    safe to vendor; nothing from wger (CC-BY-SA data) lands here."""
    sources = {entry(slug).get("source") for slug in exercises()}
    assert sources <= {"free-exercise-db", "curated"}, sources
    assert "wger" not in sources


# ---- resolution -----------------------------------------------------------------------

def test_three_spellings_of_one_movement_are_one_exercise():
    """`push-up`, `pushup` and `press-up` were three exercises and no query
    grouped them."""
    assert resolve_exercise("pushup") == "push-up"
    assert resolve_exercise("press-up") == "push-up"
    assert resolve_exercise("Push Ups") == "push-up"
    assert resolve_exercise("push-up") == "push-up"


def test_an_unknown_exercise_resolves_rather_than_erroring():
    assert resolve_exercise("something nobody catalogued") == "unknown"
    assert resolve_exercise(None) == "unknown"


def test_an_unknown_exercise_is_a_finding_that_names_the_string():
    found = problems({"exercise": "matrix rower thing"})
    assert len(found) == 1
    assert "matrix rower thing" in found[0]
    assert "exercises.toml" in found[0]


def test_the_row_is_still_recorded(tmp_path):
    """Rejecting it would lose the training. The set is the fact; the
    vocabulary is a lookup that has not caught up."""
    row = a_set(exercise="a movement nobody catalogued")
    found = validate_record("sets", row)
    assert len(found) == 1 and "unknown exercise" in found[0]


def test_a_fit_token_resolves_as_an_alias():
    """The `strava`/`healthkit` mechanism from session_types.toml, so a FIT
    import (#101) maps inward without a translation table of its own."""
    assert resolve_exercise("PUSH_UP") == "push-up"
    assert resolve_exercise("BENCH_PRESS") == "bench-press"


# ---- the gate the clinician actually described -------------------------------------------

def test_a_loaded_hip_hinge_is_blocked():
    """THE case. `pattern=hinge region=hip load=loaded` had nothing to match
    against, so the coarse `restricts: strength` gate was used instead - and
    it blocked push-ups.
    """
    verdict = gate_check(NO_LOADED_HIP, a_set("hip thrust", load_type="external",
                                              load=60))
    assert verdict["verdict"] == "blocked"
    assert verdict["exercise"] == "hip-thrust"


def test_a_squat_is_left_alone():
    """"No loaded hip work, squats fine" - the distinction the coarse
    vocabulary could not express."""
    assert gate_check(NO_LOADED_HIP,
                      a_set("squat", load_type="external",
                            load=60))["verdict"] == "allowed"


def test_a_push_up_is_left_alone():
    """The collateral damage that started this: an over-broad gate blocked
    push-ups precisely because the precise gate had nothing to check."""
    assert gate_check(NO_LOADED_HIP, a_set("push-up"))["verdict"] == "allowed"


def test_an_unloaded_hip_hinge_is_left_alone():
    """The restriction names `load=loaded`, and a glute bridge is not."""
    assert gate_check(NO_LOADED_HIP,
                      a_set("glute bridge"))["verdict"] == "allowed"


def test_a_restriction_naming_any_one_loaded_site_catches_the_exercise():
    """A deadlift loads hip, hamstring and lower back. Requiring the
    restriction to match EVERY site would clear a hip restriction against it
    because it also loads the back."""
    assert gate_check(NO_LOADED_HIP,
                      a_set("deadlift", load_type="external",
                            load=100))["verdict"] == "blocked"


# ---- the set overrides the registry --------------------------------------------------------

def test_a_weighted_push_up_is_still_a_push_up():
    """The set says it was loaded; the registry only says what usually
    happens. Getting this backwards would let a default overrule an
    observation."""
    weighted = a_set("push-up", load_type="bodyweight_plus", load=20)
    assert resolve_exercise(weighted["exercise"]) == "push-up"
    assert movement_of(weighted)["load"] == "loaded"
    assert movement_of(a_set("push-up"))["load"] == "bodyweight"


def test_the_registry_default_is_used_only_when_the_set_is_silent():
    assert movement_of({"exercise": "squat"})["load"] == "loaded"
    assert movement_of({"exercise": "push-up"})["load"] == "bodyweight"


def test_assistance_is_a_regression_not_a_loading():
    """The effective load is bodyweight MINUS the assistance, so an assisted
    pull-up is strictly easier than an unassisted one. Mapping it to `loaded`
    blocked the rehab regression while leaving the full movement allowed,
    which is precisely backwards.
    """
    assert load_of(a_set("dip", load_type="assisted", load=20)) == "bodyweight"
    hard = parse_restriction("pattern=pull region=upper_back load=loaded")
    assert gate_check(hard, a_set("pull-up", load_type="assisted", load=30)
                      )["verdict"] == "allowed"


def test_a_bodyweight_hip_hinge_becomes_blocked_once_it_is_loaded():
    bare = a_set("glute bridge")
    loaded = a_set("glute bridge", load_type="external", load=40)
    assert gate_check(NO_LOADED_HIP, bare)["verdict"] == "allowed"
    assert gate_check(NO_LOADED_HIP, loaded)["verdict"] == "blocked"


# ---- the abstention that must never become a pass -------------------------------------------

def test_an_unknown_exercise_is_not_evaluated_rather_than_allowed():
    """The subtlety that must not be missed. An unknown exercise has NO axes,
    so a restriction check can neither pass nor fail - and a silent pass means
    the athlete trains on an injury nobody flagged, with nothing in the output
    saying so.
    """
    verdict = gate_check(NO_LOADED_HIP, a_set("some machine nobody named"))
    assert verdict["verdict"] == "not_evaluated"
    assert verdict["verdict"] != "allowed"
    assert "not evaluated" in verdict["detail"]


def test_the_abstention_names_the_string_and_the_fix():
    detail = gate_check(NO_LOADED_HIP, a_set("mystery machine"))["detail"]
    assert "mystery machine" in detail
    assert "exercises.toml" in detail


def test_an_axis_free_restriction_abstains_rather_than_clearing():
    """It is not a gate over everything and it is not a clean pass either -
    most often it is a spec that failed to parse, since `parse_restriction`
    DROPS pairs it cannot resolve. Answering `allowed` turns a typo into a
    silent clearance.
    """
    assert gate_check({}, a_set("hip thrust", load_type="external")
                      )["verdict"] == "not_evaluated"
    # A spec whose every pair fails to resolve parses to nothing at all.
    # (A PARTLY unresolvable spec keeps what parsed and is therefore BROADER
    # than intended - over-blocking rather than fail-open, and
    # `restriction_problems` reports it.)
    typo = parse_restriction("pattern=hindge regoin=hip")
    assert typo == {}
    assert gate_check(typo, a_set("deadlift", load_type="external")
                      )["verdict"] == "not_evaluated"


def test_a_restriction_on_an_axis_no_exercise_carries_abstains():
    """The other way a gate failed open. `activity=strength` names a
    session-level axis no exercise carries, and `restriction_matches` reads an
    absent axis as "does not match" - right for narrowing, wrong as a verdict.
    Every strength set came back allowed from a restriction plainly covering
    it.
    """
    verdict = gate_check(parse_restriction("activity=strength"),
                         a_set("bench press", load_type="external", load=80))
    assert verdict["verdict"] == "not_evaluated"
    assert "activity" in verdict["detail"]


@pytest.mark.parametrize("axis", ["pattern", "load", "plane"])
def test_the_axes_are_the_restriction_vocabularies(axis):
    used = set()
    for slug in exercises():
        value = entry(slug).get(axis)
        if value is None:
            continue
        used.update(value if isinstance(value, list) else [value])
    assert used <= set(axis_values(axis)), (axis, used - set(axis_values(axis)))


def test_a_retired_entry_resolves_forward(tmp_path, monkeypatch):
    """The mechanism, EXERCISED rather than merely present. The previous
    version of this test asserted that a `[retired]` table existed and never
    retired or resolved anything, so it promised behaviour it did not check.
    """
    import vitai.vocab as vocab
    fake = {"version": 1, "exercises": {
                "push-up": {"label": "Push-up", "pattern": "push",
                            "region": ["chest"], "load": "bodyweight",
                            "plane": "sagittal", "source": "curated"}},
            "retired": {"press-up-machine": {"maps_to": "push-up"}}}
    monkeypatch.setattr(vocab, "registry", lambda name: fake)
    monkeypatch.setattr(vocab, "_INDEX", {}, raising=False)
    vocab._index.cache_clear()
    try:
        assert vocab.resolve("exercises", "exercises", "press-up-machine") == (
            "push-up")
    finally:
        vocab._index.cache_clear()


# ---- what the review of this feature found ------------------------------------------

def test_a_recorded_load_counts_even_when_load_type_is_missing():
    """40 kg on the record is evidence of loading whatever the row forgot to
    say. Reading only `load_type` let the registry default overrule the set's
    own number - the wrong direction for a record built on observations."""
    assert load_of({"exercise": "glute bridge", "load": 40,
                    "load_type": None}) == "loaded"
    assert gate_check(NO_LOADED_HIP, {"exercise": "glute bridge", "load": 40,
                                      "load_type": None}
                      )["verdict"] == "blocked"


def test_a_compound_lift_carries_every_pattern_it_involves():
    """A thruster is a squat AND an overhead press. One pattern per entry
    meant a restriction on loaded overhead pressing caught neither it nor a
    clean and jerk - a real clinical gate quietly failing to fire.
    """
    assert set(patterns_of("thruster")) == {"squat", "push"}
    overhead = parse_restriction("pattern=push region=shoulder load=loaded")
    for lift in ("thruster", "clean and jerk", "snatch"):
        assert gate_check(overhead, a_set(lift, load_type="external", load=60)
                          )["verdict"] == "blocked", lift
    assert gate_check(overhead, a_set("squat", load_type="external", load=60)
                      )["verdict"] == "allowed"


def test_an_exercise_done_both_ways_states_no_default_load():
    """A dip, a pull-up and a back extension are done loaded and unloaded.
    Defaulting either way guesses; absent means the SET has to say, and a
    restriction keyed on load abstains until it does."""
    for slug in ("dip", "pull-up", "back-extension"):
        assert entry(slug).get("load") is None, slug
    lower_back = parse_restriction("region=lower_back load=loaded")
    assert gate_check(lower_back, a_set("back extension", load_type=None)
                      )["verdict"] == "not_evaluated"
    assert gate_check(lower_back, a_set("back extension", load_type="external",
                                        load=40))["verdict"] == "blocked"


def test_a_raise_is_not_a_press():
    """A front raise is shoulder flexion, not a press, and labelling it
    `push` over-blocks it under a pressing restriction - the collateral
    damage this registry exists to remove."""
    assert patterns_of("front raise") == ["flexion"]


def test_abduction_movements_abstain_until_the_pattern_axis_has_them():
    """#58 owns adding adduction and abduction to `restrictions.toml`. Until
    it lands every available pattern is wrong for these - `push` over-blocks a
    lateral raise under a pressing restriction and `rotate` blocks an abductor
    machine under a rotational one - so they are left OUT and abstain, which
    is the answer this module's own doctrine requires.
    """
    for movement in ("lateral raise", "hip abduction", "seated hip adduction"):
        assert resolve_exercise(movement) == "unknown", movement
        assert gate_check(NO_LOADED_HIP, a_set(movement)
                          )["verdict"] == "not_evaluated"


def test_a_sit_up_is_not_a_crunch():
    """A sit-up loads the hip flexors and a crunch does not, so folding one
    into the other cleared sit-ups under a hip-flexion restriction."""
    assert "hip" not in regions_of("crunch")
    assert resolve_exercise("sit-up") != "crunch"


def test_an_entry_that_was_written_here_says_so():
    """`source` records the LICENCE position per entry, and a wrong one is
    worse than none: it implies a provenance nobody can verify. Entries with
    no free-exercise-db counterpart are `curated`.
    """
    assert entry("hollow-hold")["source"] == "curated"
    assert entry("bench-press")["source"] == "free-exercise-db"
    seeded = sum(1 for x in exercises()
                 if entry(x)["source"] == "free-exercise-db")
    assert 0 < seeded < len(exercises()), "every entry claims one provenance"


def test_no_two_entries_claim_the_same_spelling():
    """`vocab._index` uses `setdefault`, so a collision would be resolved
    silently by file order and nobody would find out."""
    from vitai.vocab import _normalise
    seen = {}
    for slug in exercises():
        data = entry(slug)
        spellings = [slug, data.get("label"), data.get("fit"),
                     *(data.get("aliases") or [])]
        for spelling in filter(None, spellings):
            key = _normalise(spelling)
            assert key not in seen or seen[key] == slug, (
                f"{spelling!r} is claimed by both {seen.get(key)} and {slug}")
            seen[key] = slug


# --- fixtures and kit: what a movement requires (#227) ------------------------

def test_every_fixture_and_kit_value_names_a_registry_slug():
    """The registry cannot reference equipment that does not exist."""
    from vitai.exercises import validate_fixtures
    assert validate_fixtures() == []


def test_absent_and_empty_are_different_answers():
    """`[]` means the movement needs nothing; `None` means nobody annotated it.

    Conflating them is what strands an athlete at a park with a programme
    written for a rack, so the distinction is asserted rather than assumed.
    """
    from vitai.exercises import fixtures_of
    assert fixtures_of("floor-press") == []          # needs nothing, deliberately
    assert fixtures_of("bench-press") == ["bench"]   # needs a bench
    assert fixtures_of("no-such-movement") is None   # unknown, not free


def test_requirements_are_derived_from_the_exercise_list():
    from vitai.exercises import requirements
    got = requirements(["push-up", "bench-press", "pull-up"])
    assert got["fixtures"] == ["bench", "pull-up-bar"]
    assert got["unannotated"] == []


def test_a_bodyweight_session_requires_nothing():
    from vitai.exercises import requirements
    got = requirements(["push-up", "plank", "lunge", "burpee"])
    assert got == {"fixtures": [], "kit": [], "unannotated": [],
                   "not_exercises": []}


def test_an_unannotated_movement_is_reported_rather_than_treated_as_free():
    """The refusal case: a consumer must not answer 'you can do this here'
    on a requirements list that silently omitted what it did not know."""
    from vitai.exercises import requirements
    got = requirements(["push-up", "no-such-movement"])
    # NAMED, not collapsed (#227). This asserted `["unknown"]`, which is what
    # `resolve_exercise` answers for everything it does not recognise - so two
    # uncatalogued movements reported one entry and a consumer could not say
    # which, or that there were two.
    assert got["unannotated"] == ["no-such-movement"]
    assert got["not_exercises"] == []


def test_the_registry_is_fully_annotated():
    """Every catalogued movement says what it needs.

    Not a style rule: an unannotated exercise makes `requirements` refuse, so
    a gap here disables provisioning for any session containing it.
    """
    from vitai.exercises import exercises, fixtures_of, kit_of
    missing = [e for e in exercises()
               if fixtures_of(e) is None and kit_of(e) is None]
    assert missing == []


# ---- a session type is not a movement (#227) -------------------------------

def test_a_run_is_not_an_uncatalogued_exercise():
    """A run, a swim and a ride have no row in this registry and never will,
    because a run is not an exercise. Reporting them as unannotated said the
    catalogue had a gap, when what it has is a boundary - and the two want
    opposite responses. A gap is closed by cataloguing the movement; a
    boundary is not closed at all, it is asked of something else."""
    from vitai.exercises import requirements
    got = requirements(["run", "swim", "cycle"])
    assert got["not_exercises"] == ["cycle", "run", "swim"]
    assert got["unannotated"] == []


def test_a_mixed_plan_keeps_the_three_apart():
    """The case that surfaced it: a plan holding a catalogued movement, an
    uncatalogued one and an activity reported one opaque `unknown`."""
    from vitai.exercises import requirements
    got = requirements(["bench-press", "run", "no-such-movement"])
    assert got["fixtures"] == ["bench"]
    assert got["not_exercises"] == ["run"]
    assert got["unannotated"] == ["no-such-movement"]


def test_a_consumer_still_has_to_refuse_on_either():
    """Both lists are reasons to refuse a "you can do this here" answer. They
    differ in what would fix them, not in whether the engine may guess."""
    from vitai.exercises import requirements
    for plan in (["run"], ["no-such-movement"]):
        got = requirements(plan)
        assert got["unannotated"] or got["not_exercises"]
        assert got["fixtures"] == [] and got["kit"] == []


def test_what_a_run_requires_is_still_unanswered():
    """Deliberately. Saying it needs a vocabulary of PLACES - a road, a pool,
    open water - and `fixtures.toml` is a gym catalogue: bench, rack,
    cable-stack. Inventing those slugs here is the write-a-vocabulary-from-one
    -athlete's-examples hazard #236 exists to gate."""
    from vitai.exercises import fixture_values, requirements
    assert not {"road", "pool", "open-water", "track"} & set(fixture_values())
    assert requirements(["run"])["fixtures"] == []
