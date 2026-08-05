"""Swimming is expressible in the model that already exists (#230 part 1).

The useful surprise in #230 is that the `sets` model fits lane work as it
stands: a length is one row, the stroke is `exercise`, the length number is
`set_index`, the time is `duration_s`, a 4 x 50 is `block` plus `round`. What
was missing was vocabulary, not structure - `exercises.toml` had no swimming
at all and `modifiers.toml` equipment was entirely gym.

The names are World Aquatics' own, so this is prior art rather than a taxonomy
written from one athlete's examples. The axis assignment is ours and says so.

Parts 2 to 4 of that issue are deliberately absent: parametric requirements
with alternatives, recursive places with attributes, and access states. Each
needs a concept this engine does not have, and #230 itself ranks this part
first as "additive, no new concepts".
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai, init
from vitai.exercises import (entry, exercises, gate_check,
                             requirements, resolve_exercise)
from vitai.modifiers import resolve_modifier
from vitai.schema import SESSION_TYPES

STROKES = ("front-crawl", "backstroke", "breaststroke", "butterfly")


def test_the_four_competitive_strokes_are_catalogued():
    """One `swim` entry would have made a stroke unrecordable, and the strokes
    are the level at which a restriction can tell them apart."""
    known = exercises()

    for stroke in STROKES:
        assert stroke in known, stroke


def test_the_names_a_person_or_a_watch_writes_resolve():
    """`freestyle` and `front crawl` are one stroke under two names, which is
    exactly the free-text collapse this registry exists to end."""
    assert resolve_exercise("freestyle") == "front-crawl"
    assert resolve_exercise("free") == "front-crawl"
    assert resolve_exercise("fly") == "butterfly"
    assert resolve_exercise("back crawl") == "backstroke"


def test_a_stroke_carries_the_axes_a_restriction_reads():
    """The whole design of the registry: a set INHERITS the axes, so an
    episode wanting `pattern` and `region` has something to match against."""
    for stroke in STROKES:
        spec = entry(stroke)
        assert spec.get("region"), stroke
        assert spec.get("pattern"), stroke
        assert spec.get("load") == "bodyweight", stroke


def test_breaststroke_is_the_stroke_an_adductor_gate_can_see():
    """The reason four entries beat one, stated as something that FIRES.

    An earlier version claimed breaststroke omits `upper_back` and that this
    is why a shoulder episode leaves it available. It is not: all four strokes
    carry `shoulder`, so a shoulder restriction blocks all four identically,
    and the claim described a behaviour the model does not produce.

    The distinction that does fire is the whip kick, which is a forceful hip
    adduction. `pattern.adduction` exists for groin and adductor gates, and
    leaving it off cleared the movement most associated with adductor injury
    from the gate written for adductor injury.
    """
    assert gate_check({"pattern": "adduction"},
                      {"exercise": "breaststroke"})["verdict"] == "blocked"
    for other in ("front-crawl", "backstroke", "butterfly"):
        assert gate_check({"pattern": "adduction"},
                          {"exercise": other})["verdict"] == "allowed", other


def test_no_running_does_not_bar_swimming():
    """`gait` is defined as "walking, running, locomotion", and the standard
    lower-limb instruction is "no running, swimming is fine". Labelling a
    stroke `gait` made that instruction block every stroke - the
    over-restriction this registry exists to prevent."""
    for stroke in (*STROKES, "swim-kick"):
        assert gate_check({"pattern": "gait"},
                          {"exercise": stroke})["verdict"] == "allowed", stroke


def test_the_medley_carries_every_region_its_four_strokes_do():
    """A GATE MAY NOT FAIL OPEN, and this entry is used exactly when nobody
    can say which quarter of the swim was which stroke.

    An earlier version claimed "the union of the four" and omitted `hip` and
    `knee`, which are breaststroke's own. A knee restriction then blocked
    breaststroke and ALLOWED a medley of which a quarter is breaststroke.
    """
    union = set()
    for stroke in STROKES:
        union |= set(entry(stroke)["region"])

    assert set(entry("individual-medley")["region"]) >= union

    for gate in ("knee", "hip"):
        assert gate_check({"region": gate},
                          {"exercise": "individual-medley"}
                          )["verdict"] == "blocked", gate


def test_pull_and_kick_are_movements_rather_than_modifiers():
    """They load different regions - arms with the legs supported, or legs
    alone - so folding them into an equipment axis would leave a lower-limb
    restriction unable to see that half the session was legs."""
    pull, kick = entry("swim-pull"), entry("swim-kick")

    assert not ({"thigh", "knee", "calf", "ankle"} & set(pull["region"]))
    assert not ({"shoulder", "upper_arm", "upper_back"} & set(kick["region"]))


def test_the_swim_kit_resolves_on_the_equipment_axis():
    """Kit in the #229 sense: the athlete brings it, so it travels with them
    rather than belonging to a place."""
    assert resolve_modifier("equipment", "buoy") == "pull_buoy"
    assert resolve_modifier("equipment", "flippers") == "swim_fins"
    assert resolve_modifier("equipment", "paddles") == "hand_paddles"
    assert resolve_modifier("equipment", "board") == "kickboard"


def test_a_medley_length_is_one_row_per_stroke(tmp_path):
    """The shape that looked as though it would break the model and does not.

    A lifting set is N reps of ONE movement and the reps are homogeneous by
    definition; a swim set is N lengths and the stroke can change every
    length. Because a length is already a row, a medley is four rows with four
    exercises - the same shape a circuit uses.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    for n, stroke in enumerate(
            ("butterfly", "backstroke", "breaststroke", "front-crawl"), 1):
        v.append("sets", {"date": "2030-05-06", "exercise": stroke,
                          "set_index": n, "duration_s": 48, "rest_s": 15,
                          # `block` is a whole number, not a slug: the
                          # set is the first block of the session and the
                          # round is the first time through it.
                          "block": 1, "round": 1, "source": "athlete"})

    rows = v.sets("2030-05-06")

    assert [r["exercise"] for r in rows] == ["butterfly", "backstroke",
                                             "breaststroke", "front-crawl"]
    assert {r["block"] for r in rows} == {1}
    assert not v.validate()["problems"]


def test_a_pull_set_records_its_buoy(tmp_path):
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("sets", {"date": "2030-05-06", "exercise": "swim-pull",
                      "set_index": 1, "duration_s": 55,
                      "equipment": "pull_buoy", "source": "athlete"})

    row, = v.sets("2030-05-06")

    assert row["equipment"] == "pull_buoy"
    assert not v.validate()["problems"]


def test_a_swim_session_is_no_longer_reported_as_an_uncatalogued_movement():
    """`swim` is a session TYPE, not a movement, and reporting it as
    unannotated said the catalogue had a gap when what it has is a boundary.
    The strokes are the movements, and they are now catalogued."""
    assert "swim" in SESSION_TYPES

    out = requirements(["front-crawl", "swim-kick", "swim"])

    # A boundary, not a gap: `swim` is a session type and will never have a
    # row here. The strokes ARE catalogued - they report unannotated only
    # because what a swim requires is #230 part 2, which is a different
    # sentence from "nobody has catalogued this movement".
    assert out["not_exercises"] == ["swim"]
    assert "swim" not in out["unannotated"]


def test_a_swim_requires_water_and_says_so_coarsely(tmp_path):
    """The COARSE half, and the registry's completeness guard forces a choice.

    `[]` would mean "needs nothing - a floor press", which answers "you can
    swim in your garage". Omitting the key leaves the movement unannotated,
    which the registry's own guard refuses because a gap there disables
    provisioning for any session containing it. So the requirement is stated
    as far as a slug can state it.

    What stays unsayable is "at least 12 m of straight line, OR an active
    countercurrent" - no room for a parameter, and a list reads as AND where
    the countercurrent is an alternative. That is #230 part 2.
    """
    for stroke in (*STROKES, "swim-pull", "swim-kick"):
        assert entry(stroke)["fixture"] == ["swimmable-water"], stroke

    out = requirements(list(STROKES))

    assert out["fixtures"] == ["swimmable-water"]
    assert out["unannotated"] == []


def test_the_partial_forms_declare_the_kit_they_need():
    """Kit belongs to the athlete and travels with them, which is the axis
    that decides whether a session is provisionable somewhere."""
    assert requirements(["swim-pull"])["kit"] == ["pull-buoy"]
    assert requirements(["swim-kick"])["kit"] == ["kickboard"]


def test_every_added_entry_names_where_its_axes_came_from():
    """The axis assignment is ours, not a database's. `source = "curated"`
    is what keeps a borrowed-looking entry from claiming prior art it does
    not have."""
    for slug in (*STROKES, "individual-medley", "swim-pull", "swim-kick"):
        assert entry(slug).get("source") == "curated", slug


def test_the_registry_stays_loadable_and_the_toml_stays_valid():
    """A vocabulary file is data, and a data file that stops parsing takes the
    engine with it."""
    path = (Path(__file__).resolve().parents[1] / "src" / "vitai"
            / "semantics" / "exercises.toml")
    import tomllib

    parsed = tomllib.loads(path.read_text(encoding="utf-8"))

    assert len(parsed["exercises"]) == len(exercises())
    assert json.dumps(parsed["exercises"]["front-crawl"], sort_keys=True)


def test_the_reading_order_is_the_order_swum_not_the_alphabet(tmp_path):
    """The read path had to be fixed for the medley to survive it.

    `sets()` sorted by `exercise` BEFORE `block`, `round` and `set_index`,
    which groups a lifting session by movement and reads perfectly well -
    while contradicting the method's own first line, "in the order they were
    performed". A medley came back backstroke, breaststroke, butterfly, front
    crawl: alphabetical, and not an order anybody swam.

    The counters are what say when a set happened. A name never did.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    for n, stroke in enumerate(
            ("butterfly", "backstroke", "breaststroke", "front-crawl"), 1):
        v.append("sets", {"date": "2030-05-06", "exercise": stroke,
                          "set_index": n, "duration_s": 48,
                          "block": 1, "round": 1, "source": "athlete"})

    order = [r["exercise"] for r in v.sets("2030-05-06")]

    assert order == ["butterfly", "backstroke", "breaststroke", "front-crawl"]
    assert order != sorted(order), (
        "if the strokes happen to be alphabetical the fixture proves nothing"
    )


def test_a_blockless_session_is_scoped_by_movement(tmp_path):
    """`set_index` is "the set's position in its BLOCK", so without a block
    the exercise is the only scope those indices have.

    My first cut compared them across movements regardless, and three
    deadlifts and three benches numbered 1-3 each interleaved into a superset
    nobody performed - bench first, though the deadlifts came first. A
    block-less session is NORMAL, so that is not an edge case.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    for move in ("deadlift", "bench-press"):
        for i in (1, 2, 3):
            v.append("sets", {"date": "2030-05-06", "exercise": move,
                              "set_index": i, "reps_completed": 5,
                              "source": "athlete"})

    order = [r["exercise"] for r in v.sets("2030-05-06")]

    assert order == ["bench-press"] * 3 + ["deadlift"] * 3, (
        "block-scoped indices were compared across blocks")


def test_a_session_that_states_its_blocks_reads_in_block_order(tmp_path):
    """With a block, the counters order everything and the name decides
    nothing - which is what lets a medley survive the read path."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for block, move in ((1, "deadlift"), (2, "bench-press"), (3, "deadlift")):
        v.append("sets", {"date": "2030-05-06", "exercise": move, "block": block,
                          "set_index": 1, "reps_completed": 5,
                          "source": "athlete"})

    order = [r["exercise"] for r in v.sets("2030-05-06")]

    assert order == ["deadlift", "bench-press", "deadlift"]
