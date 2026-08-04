"""Reads over sets, and the numbers that must refuse (#100).

Synthetic data only (public repo), fictional athlete, 2030 dates. Half of this
file is refusals, because half of the increment is: the arithmetic is
ordinary, and what earns it its keep is declining to produce a figure that
would be a confident wrong answer.
"""

import json

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.progression import (bodyweight_on, is_maximal_evidence,
                               ordinal_change, progression, resolved_load,
                               scale_name, scale_of, tonnage, volume,
                               working_weight)
from vitai.schema import CURRENT_GENERATION


def a_set(**kw):
    row = {"date": "2030-05-01", "session_start": "2030-05-01T07:10:00+02:00",
           "exercise": "leg press", "block": 1, "round": None, "set_index": 1,
           "reps_completed": 12, "reps_attempted": 12,
           "load": None, "load_type": None, "load_unit": None,
           "machine": None, "set_type": "working", "failure": None,
           "rir": None, "rpe": None, "rest_s": 90, "tempo": None,
           "duration_s": None, "side": None, "note": None,
           "source": "stated-in-chat", "recorded_at": None,
           "origin": "athlete", "path": None, "origin_evidence": None,
           "capture": "narrative", "read_by": "athlete",
           "equipment": None, "angle_class": None, "angle_deg": None,
           "resistance_level": None, "seat_pos": None, "pad_pos": None,
           "lever_pos": None, "device": None,
           "_gen": CURRENT_GENERATION["sets"]}
    row.update(kw)
    return row


def stack(load, **kw):
    return a_set(load=load, load_type="machine_stack",
                 machine="leg-press-a", **kw)


# The stack progression the issue names: the third row is the failed attempt.
STACK_BLOCK = [
    stack(59, set_index=1),
    stack(66, set_index=2),
    stack(73, set_index=3, reps_completed=0, reps_attempted=1,
          failure="muscular"),
    stack(66, set_index=4),
]

# The descending series that read as maximal and was not.
PUSH_UPS = [a_set(exercise="push-up", load_type="bodyweight", set_index=i,
                  reps_completed=r, reps_attempted=r)
            for i, r in enumerate((13, 12, 10), start=1)]


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, rows, name="sets"):
    (root / "data" / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- the refusal the increment exists for -------------------------------------------

def test_a_set_with_no_stated_endpoint_is_never_a_maximum():
    """THE case. Set 1 sat against a stated max and looked like one; set 2
    held 92% of it, where genuine failure leaves 55-70%. Reading a
    null-failure set as maximal is what manufactured a max several reps below
    the truth.
    """
    for row in PUSH_UPS:
        assert is_maximal_evidence(row) is False
    assert is_maximal_evidence(a_set(failure="volitional")) is False
    assert is_maximal_evidence(a_set(failure="muscular")) is True
    assert is_maximal_evidence(a_set(failure="technical")) is True


def test_a_null_failure_set_still_counts_as_volume():
    """It happened. Counting the work is not the same as reading it as a
    limit, and refusing both would lose the training to protect an inference
    nobody asked for."""
    got = volume(PUSH_UPS)
    assert got["reps"] == 35
    assert got["sets"] == 3


def test_the_progression_marks_which_points_are_evidence_of_a_maximum():
    got = progression(PUSH_UPS, "push-up")
    assert [p["maximal_evidence"] for p in got["points"]] == [False] * 3


# ---- scales, and what may not be added ------------------------------------------------

def test_a_stack_number_and_a_mass_are_different_units():
    """Both are spelled in kilograms and are not the same kind of thing,
    which is exactly why summing them looks reasonable."""
    assert scale_of(stack(66)) == ("stack", "leg-press-a")
    assert scale_of(a_set(load=60, load_type="external")) == ("mass", None)
    assert scale_name(("stack", "leg-press-a")) == "stack(leg-press-a)"


def test_two_machines_stacks_are_two_scales_and_never_one_subtotal():
    """66 on one machine is not 66 on another (#60), so the machine is part
    of the unit rather than a label on it - asserted through `tonnage`,
    because testing the tuple alone would pass under a bucket-key collision.
    """
    a = scale_of(stack(66))
    b = scale_of(a_set(load=66, load_type="machine_stack", machine="row-b"))
    assert a != b
    got = tonnage([stack(66), a_set(load=66, load_type="machine_stack",
                                    machine="row-b")])
    assert {x["scale"] for x in got["by_scale"]} == {
        "stack(leg-press-a)", "stack(row-b)"}
    assert any(f["kind"] == "no_grand_total" for f in got["findings"])


def test_tonnage_has_no_grand_total_key_at_all():
    """Not a total set to None, which a consumer renders as zero: the key is
    ABSENT, so asking for one raises rather than returning a plausible
    figure."""
    got = tonnage([*STACK_BLOCK,
                   a_set(exercise="bench press", load=60,
                         load_type="external", reps_completed=8)])
    assert "total" not in got
    with pytest.raises(KeyError):
        got["total"]


def test_tonnage_reports_per_scale_subtotals_and_says_they_do_not_add():
    got = tonnage([*STACK_BLOCK,
                   a_set(exercise="bench press", load=60,
                         load_type="external", reps_completed=8)])
    scales = {b["scale"] for b in got["by_scale"]}
    assert scales == {"stack(leg-press-a)", "mass"}
    assert any(f["kind"] == "no_grand_total" for f in got["findings"])


def test_a_machine_ordinal_cannot_be_multiplied_into_a_tonnage():
    """It has no zero and no established spacing. Level 15 for 20 minutes is
    not 300 of a unit."""
    got = tonnage([a_set(exercise="crosstrainer", resistance_level=15,
                         machine="cross-b", reps_completed=0,
                         reps_attempted=0, duration_s=1800)])
    assert got["by_scale"] == []
    assert any(f["kind"] == "not_summable" for f in got["findings"])


def test_rows_that_cannot_be_resolved_are_named_rather_than_dropped():
    """A derivation that quietly skips what it cannot handle produces a total
    that is wrong in the direction of looking fine."""
    got = tonnage([a_set(exercise="push-up", load_type="bodyweight")], [])
    assert got["by_scale"] == []
    finding = next(f for f in got["findings"] if f["kind"] == "unresolved_load")
    assert finding["rows"][0]["exercise"] == "push-up"


# ---- bodyweight resolves, or declines ---------------------------------------------------

def test_bodyweight_resolves_against_the_trend_not_one_morning():
    """P6: body mass swings about a kilogram within a day, so a single
    reading is a worse estimate of what a push-up costs than the fortnight
    around it."""
    weights = [{"date": "2030-04-28", "kg": 80.0},
               {"date": "2030-05-01", "kg": 82.0},
               {"date": "2030-05-04", "kg": 81.0}]
    assert bodyweight_on(weights, "2030-05-01") == pytest.approx(81.0)


def test_bodyweight_declines_when_there_is_no_weight_near_the_date():
    """A made-up bodyweight propagates into every tonnage that touches it and
    is invisible once it has."""
    assert bodyweight_on([{"date": "2029-01-01", "kg": 80.0}],
                         "2030-05-01") is None
    load, why = resolved_load(a_set(load_type="bodyweight"), [])
    assert load is None and "no weight data" in why


def test_a_resolved_bodyweight_tonnage_never_sits_beside_barbell_kilos():
    """P3. Summed together, an 80 kg athlete's push-ups dominate the figure
    with a number nobody weighed - and the total then moves when they cut,
    for reasons that have nothing to do with training."""
    got = tonnage([a_set(exercise="bench press", load=60,
                         load_type="external", reps_completed=8),
                   a_set(exercise="push-up", load_type="bodyweight",
                         reps_completed=13)],
                  [{"date": "2030-05-01", "kg": 80.0}])
    scales = {b["scale"]: b for b in got["by_scale"]}
    assert set(scales) == {"mass", "mass(modelled)"}
    assert scales["mass"]["basis"] == ["measured"]
    assert scales["mass(modelled)"]["basis"] == ["modelled"]


def test_assistance_subtracts_from_bodyweight():
    load, basis = resolved_load(
        a_set(load_type="assisted", load=20), [{"date": "2030-05-01", "kg": 80.0}])
    assert load == pytest.approx(60.0) and basis == "modelled"


# ---- progression is machine-scoped by default --------------------------------------------

def test_a_progression_across_two_machines_refuses():
    """Sets of one exercise across two machines are two series, and splicing
    them into one produces a trend that describes neither (#60)."""
    rows = [*STACK_BLOCK,
            a_set(exercise="leg press", load=70, load_type="machine_stack",
                  machine="leg-press-b", date="2030-05-08")]
    got = progression(rows, "leg press")
    assert got["points"] == []
    assert got["findings"][0]["kind"] == "cross_scale_progression"


def test_scoping_to_one_machine_gives_the_series():
    rows = [*STACK_BLOCK,
            a_set(exercise="leg press", load=70, load_type="machine_stack",
                  machine="leg-press-b", date="2030-05-08")]
    got = progression(rows, "leg press", machine="leg-press-a")
    assert [p["load"] for p in got["points"]] == [59, 66, 73, 66]
    assert got["findings"] == []


def test_the_failed_attempt_is_visible_in_the_trajectory():
    """The most informative set of the block, and the reason the dataset
    exists."""
    got = progression(STACK_BLOCK, "leg press", machine="leg-press-a")
    failed = [p for p in got["points"] if p["reps_completed"] == 0]
    assert len(failed) == 1
    assert failed[0]["load"] == 73
    assert failed[0]["reps_attempted"] == 1
    assert failed[0]["maximal_evidence"] is True


def test_reps_at_a_fixed_load_across_two_dates_is_a_query():
    """"66 went from 8 reps to 12 between Tuesday and Thursday" was
    established by reading two prose notes side by side."""
    rows = [stack(66, date="2030-05-01", reps_completed=8, reps_attempted=8),
            stack(66, date="2030-05-03", reps_completed=12, reps_attempted=12)]
    got = progression(rows, "leg press", machine="leg-press-a")
    at_66 = [p for p in got["points"] if p["load"] == 66]
    assert [p["reps_completed"] for p in at_66] == [8, 12]


# ---- an ordinal is an order, not a ratio ---------------------------------------------------

def test_an_ordinal_change_is_steps_and_never_a_percentage():
    """"Level 15 is 15/13 of level 13" is not a valid inference even where
    the arithmetic looks proportional: the scale is not established to be
    linear, or to have a zero."""
    before = a_set(resistance_level=13, machine="cross-b")
    after = a_set(resistance_level=15, machine="cross-b")
    got = ordinal_change(before, after)
    assert got["steps"] == 2
    assert "not a ratio" in got["detail"]
    assert "%" not in got["detail"]


def test_an_ordinal_change_across_machines_refuses():
    got = ordinal_change(a_set(resistance_level=13, machine="cross-a"),
                         a_set(resistance_level=15, machine="cross-b"))
    assert got["steps"] is None
    assert "not a quantity" in got["detail"]


# ---- the working weight --------------------------------------------------------------------

def test_the_working_weight_ignores_warmups_and_drops():
    """A warm-up is not the working weight, and a drop-set segment is a load
    chosen because the working one had just been reached."""
    rows = [stack(30, set_index=1, set_type="warmup"),
            stack(66, set_index=2, set_type="working"),
            stack(40, set_index=3, set_type="drop")]
    got = working_weight(rows, "leg press")
    assert got["load"] == 66


def test_the_working_weight_carries_its_failure_state():
    """"80 for 8" means something different depending on whether 8 was all
    there was."""
    got = working_weight([stack(66, failure="muscular")], "leg press")
    assert got["maximal_evidence"] is True
    assert working_weight([stack(66)], "leg press")["maximal_evidence"] is False


def test_an_exercise_with_no_working_sets_says_so():
    got = working_weight([stack(30, set_type="warmup")], "leg press")
    assert got["load"] is None
    assert "not the working weight" in got["detail"]


# ---- the surface -----------------------------------------------------------------------------

def test_the_cli_never_prints_a_grand_tonnage(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [*STACK_BLOCK,
                 a_set(exercise="bench press", load=60, load_type="external",
                       reps_completed=8)])
    capsys.readouterr()
    main(["sets", "tonnage", "--root", str(root)])
    out = capsys.readouterr().out
    assert "stack(leg-press-a)" in out and "mass" in out
    assert "NO_GRAND_TOTAL" in out
    # No line states a total FIGURE. Scoped past the refusal's own label,
    # which legitimately contains the word.
    for line in out.splitlines():
        if line.startswith("NO_GRAND_TOTAL"):
            continue
        assert not line.lower().startswith("total"), line


def test_the_cli_marks_a_non_maximal_point(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, PUSH_UPS)
    capsys.readouterr()
    main(["sets", "progression", "push-up", "--root", str(root)])
    out = capsys.readouterr().out
    assert out.count("(not a maximum)") == 3


def test_a_thin_series_does_not_get_a_trend_voice(tmp_path, capsys):
    """P3/G27: a progression over one session is not a trend, and saying so
    costs one line."""
    root = repo(tmp_path)
    write(root, PUSH_UPS)
    capsys.readouterr()
    main(["sets", "progression", "push-up", "--root", str(root)])
    assert "too thin to read as a trend" in capsys.readouterr().out


def test_the_cli_refuses_a_cross_machine_progression(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [*STACK_BLOCK,
                 a_set(exercise="leg press", load=70,
                       load_type="machine_stack", machine="leg-press-b",
                       date="2030-05-08")])
    capsys.readouterr()
    main(["sets", "progression", "leg press", "--root", str(root)])
    out = capsys.readouterr().out
    assert "CROSS_SCALE_PROGRESSION" in out
    assert "Scope the query to one machine" in out


def test_a_read_verb_needs_something_to_be_about(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(SystemExit, match="needs an exercise"):
        main(["sets", "progression", "--root", str(root)])


def test_the_list_verb_still_works(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, STACK_BLOCK)
    capsys.readouterr()
    main(["sets", "--root", str(root)])
    assert "FAILED" in capsys.readouterr().out


def test_the_api_and_cli_agree(tmp_path):
    """P9: the CLI is a harness over the API, never a second code path."""
    root = repo(tmp_path)
    write(root, STACK_BLOCK)
    v = Vitai(root)
    assert v.set_volume()["reps"] == sum(r["reps_completed"] for r in STACK_BLOCK)
    assert v.working_weight("leg press")["load"] == 66
    assert v.set_progression("leg press", "leg-press-a")["points"]
    assert "total" not in v.set_tonnage()


def test_a_load_that_was_not_lifted_is_not_a_working_weight():
    """The failed attempt is the heaviest row in a stack block, so taking the
    max load made the working weight the one thing the athlete could NOT
    do."""
    got = working_weight(STACK_BLOCK, "leg press")
    assert got["load"] == 66
    only_failed = [stack(73, reps_completed=0, reps_attempted=1,
                         failure="muscular")]
    assert working_weight(only_failed, "leg press")["load"] is None
    assert "not a working weight" in working_weight(
        only_failed, "leg press")["detail"]


# ---- what the review of this feature found ------------------------------------------

def test_recording_where_the_seat_went_does_not_disable_the_machine():
    """`seat_pos`, `pad_pos` and `lever_pos` are machine-scoped CONFIGURATION,
    not the load. Treating them as the scale reclassified a perfectly summable
    pin as an un-multipliable ordinal - so one seat-position row made the
    whole machine's progression refuse, even when scoped.
    """
    configured = stack(66, seat_pos=4, pad_pos=2)
    assert scale_of(configured) == ("stack", "leg-press-a")
    assert tonnage([configured])["by_scale"][0]["tonnage"] == pytest.approx(792)
    got = progression([*STACK_BLOCK, configured], "leg press",
                      machine="leg-press-a")
    assert got["findings"] == []


def test_two_load_bearing_numbers_on_one_row_are_named_not_picked_between():
    """A resistance level AND a stack load is two scales on one row. Silently
    preferring one drops the other with no ambiguity reported."""
    both = stack(66, resistance_level=15)
    assert scale_of(both)[0] == "ambiguous"
    got = tonnage([both])
    assert got["by_scale"] == []
    assert any("two different scales" in f["detail"] for f in got["findings"])


def test_a_stack_load_with_no_machine_has_no_scale():
    """THE refusal, and it was walking straight through: two pin numbers with
    no machine named merged into one `stack` bucket and were summed - exactly
    the cross-machine sum this module exists to prevent."""
    got = tonnage([a_set(load=66, load_type="machine_stack", machine=None),
                   a_set(load=70, load_type="machine_stack", machine=None)])
    assert got["by_scale"] == []
    assert any("only a number on one machine" in f["detail"]
               for f in got["findings"])


def test_a_bare_number_with_no_load_type_is_not_assumed_to_be_kilograms():
    """It could be a pin. "Nobody said" is applied to `failure`; it applies
    here too, and promoting it would put an unlabelled stack number beside
    barbell kilos."""
    got = tonnage([a_set(load=66, load_type=None)])
    assert got["by_scale"] == []
    assert any("kilograms or a pin position" in f["detail"]
               for f in got["findings"])


def test_unstated_assistance_is_not_zero_assistance():
    """Treating it as zero tonnages an assisted pull-up as an unassisted one,
    which is the direction that overstates the work."""
    load, why = resolved_load(a_set(load_type="assisted", load=None),
                              [{"date": "2030-05-01", "kg": 80.0}])
    assert load is None and "unstated is not zero" in why


def test_assistance_larger_than_the_athlete_is_named_not_clamped():
    """Clamping to zero manufactures a figure from a row that cannot be
    right."""
    load, why = resolved_load(a_set(load_type="assisted", load=100),
                              [{"date": "2030-05-01", "kg": 80.0}])
    assert load is None and "cannot be right" in why


def test_a_negative_load_is_refused():
    load, why = resolved_load(a_set(load_type="external", load=-20), [])
    assert load is None and "negative" in why


def test_the_working_weight_never_ranks_across_scales():
    """`max` over the raw number ranked a pin of 66 above 60 kg - the
    comparison this whole module refuses."""
    got = working_weight([a_set(load=60, load_type="external"),
                          a_set(load=66, load_type="machine_stack",
                                machine="row-b")], "leg press")
    assert got["load"] is None
    assert "more than one scale" in got["detail"]


def test_a_bodyweight_working_weight_declines_with_a_reason(tmp_path, capsys):
    """It returned `load: None` and NO `detail`, and the CLI printed
    `got["detail"]` - so the verb crashed with a KeyError on the commonest
    case there is."""
    got = working_weight(PUSH_UPS, "push-up")
    assert got["load"] is None
    assert "detail" in got and "bodyweight movement" in got["detail"]

    root = repo(tmp_path)
    write(root, PUSH_UPS)
    capsys.readouterr()
    main(["sets", "working-weight", "push-up", "--root", str(root)])
    assert "bodyweight movement" in capsys.readouterr().out


def test_unstated_reps_are_not_reported_as_a_failed_attempt():
    """The refusal was right and its stated reason was false: nothing was
    attempted-and-failed, the reps are simply unstated."""
    got = working_weight([stack(66, reps_completed=None, reps_attempted=None)],
                         "leg press")
    assert got["load"] is None
    assert "unstated is not zero" in got["detail"]


def test_a_volitional_stop_at_zero_reserve_is_legal_and_not_maximal():
    """The commonest way a set ends, and the pairing the old gloss made read
    as a contradiction (#244).

    Someone judges he cannot do another WITHOUT starting one and finding out.
    That is `volitional` - he ended the set - with `rir: 0`, because he
    believed none were left. It is not `muscular`, which asserts a rep was
    attempted and lost, and encoding it that way would put a tested limit in
    the record where nothing was tested.

    It is not evidence of a maximum, and the reason matters: not that reps
    were left, but that the question was never put.
    """
    from vitai.progression import is_maximal_evidence
    from vitai.schema import validate_record

    from vitai.schema import CURRENT_GENERATION, KEYS

    def a_set(**kw):
        row = {k: None for k in KEYS["sets"]}
        row.update({"date": "2030-05-01", "exercise": "bench-press",
                    "set_index": 1, "reps_completed": 8, "reps_attempted": 8,
                    "load": 60, "load_type": "external", "load_unit": "kg",
                    "source": "stated-in-chat", "capture": "narrative",
                    "read_by": "athlete",
                    "_gen": CURRENT_GENERATION["sets"]})
        row.update(kw)
        return row

    row = a_set(failure="volitional", rir=0, set_type="working")
    assert validate_record("sets", row) == []
    assert not is_maximal_evidence(row)
    # And the tested endings still are.
    assert is_maximal_evidence(a_set(failure="muscular", rir=0, set_type="working"))
