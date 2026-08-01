"""An itemised meal estimate, with a range that never collapses (#96).

Synthetic data only (public repo), fictional athlete, 2030 dates. The meal
below is invented; the SHAPE of it - a protein whose portion nobody can see,
small items that are easy to count, and a cooking fat that is easy to forget -
is what a photographed plate actually looks like.
"""

import json

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.meals import (buffered, day_disagreements, dominant_uncertainty,
                         item_energy, meal_total, quantity_range, unsettled)
from vitai.schema import KEYS, validate_record


def item(name, grams=None, lo=None, hi=None, kcal_100g=None, **kw):
    row = {"date": "2030-05-01", "meal": "lunch", "item": name,
           "grams": grams, "grams_lo": lo, "grams_hi": hi,
           "kcal_100g": kcal_100g, "protein_100g": None, "fat_100g": None,
           "carb_100g": None, "food_table": "usda" if kcal_100g else None,
           "note": None, "source": "photo-estimate", "recorded_at": None,
           "origin": None, "path": None, "origin_evidence": None,
           "capture": None, "read_by": None}
    row.update(kw)
    return row


# A plate: the protein carries the uncertainty, the small items do not.
PLATE = [item("chicken thigh", 165, 140, 200, kcal_100g=240),
         item("green olives", 32, 28, 36, kcal_100g=145),
         item("tomato", 70, 60, 80, kcal_100g=18),
         item("cooking oil", 11, 8, 14, kcal_100g=884)]


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, rows):
    (root / "data" / "meals.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- the item is the unit ---------------------------------------------------------

def test_energy_is_derived_from_the_quantity_never_stored():
    """An item whose gram estimate is corrected must not keep an energy
    figure computed from the old one."""
    lo, est, hi = item_energy(item("chicken thigh", 165, 140, 200,
                                   kcal_100g=240))
    assert (round(lo), round(est), round(hi)) == (336, 396, 480)


def test_an_unbounded_estimate_is_a_zero_width_range_not_certainty():
    assert quantity_range(item("tomato", 70)) == (70.0, 70.0, 70.0)
    assert unsettled([item("tomato", 70)])[0]["missing"] == "range"


def test_an_item_with_no_quantity_is_a_question():
    assert unsettled([item("sweetcorn")])[0]["missing"] == "quantity"


def test_the_dish_is_never_the_unit():
    """A dish-level number cannot be corrected, cannot be questioned, and
    cannot say which part it is unsure about."""
    assert any("ingredient" in p for p in
               validate_record("meals", item("", 400, kcal_100g=150)))


# ---- the total always carries its range --------------------------------------------

def test_the_total_is_a_range_and_the_range_is_the_confidence_statement():
    total = meal_total(PLATE)
    assert total["lo"] < total["estimate"] < total["hi"]
    assert total["width"] == pytest.approx(total["hi"] - total["lo"])
    assert total["complete"] is True


def test_there_is_no_confidence_field_to_put_a_number_in():
    """No corpus of photo-estimated meals scored against weighed truth
    exists, so a 0.6 here would be a decimal point pretending to be
    calibration (P4). Asserted against the schema, not against intent.
    """
    assert "confidence" not in KEYS["meals"]
    problems = validate_record("meals", {**item("tomato", 70, kcal_100g=18),
                                         "confidence": 0.6})
    assert any("unknown key 'confidence'" in p for p in problems)


def test_an_unpriced_item_is_counted_rather_than_dropped():
    """A total that silently omits the olive oil is wrong in the direction
    that matters most."""
    total = meal_total([*PLATE, item("dressing", 20)])
    assert total["unpriced"] == 1
    assert total["complete"] is False


def test_the_narrative_names_which_item_dominates_the_error():
    """"600, and 70 of the 90 is how much chicken" tells the athlete which
    single question collapses the range. A bare total cannot."""
    dominant = dominant_uncertainty(PLATE)
    assert dominant["item"] == "chicken thigh"
    assert dominant["share"] > 0.5


def test_a_meal_nobody_is_uncertain_about_has_no_dominant_item():
    settled = [item("tomato", 70, 70, 70, kcal_100g=18)]
    assert dominant_uncertainty(settled) is None


# ---- the buffer is policy, not a judgement ------------------------------------------

def test_the_buffer_is_applied_and_stays_decomposable():
    """A number the athlete cannot decompose back into what was estimated
    and what was policy is a number they cannot check."""
    total = meal_total(PLATE)
    with_buffer = buffered(total, 15)
    assert with_buffer["estimate"] == pytest.approx(total["estimate"] * 1.15)
    assert with_buffer["unbuffered"]["estimate"] == pytest.approx(
        total["estimate"])
    assert with_buffer["buffer_pct"] == 15


def test_no_buffer_is_the_default_and_says_so():
    assert buffered(meal_total(PLATE), None)["buffer_pct"] is None


def test_the_buffer_comes_from_config_so_it_cannot_vary_by_meal(tmp_path):
    """A buffer added by judgement on some meals and not others corrupts
    every comparison in the series."""
    root = repo(tmp_path)
    write(root, PLATE + [{**r, "date": "2030-05-02", "meal": "dinner"}
                         for r in PLATE])
    with (root / "vitai.toml").open("a", encoding="utf-8") as fh:
        fh.write("\n[preferences]\nintake_buffer_pct = 15\n")
    applied = {m["kcal"]["buffer_pct"] for m in Vitai(root).meals()}
    assert applied == {15}, "every meal or none"


# ---- a meal is not a day --------------------------------------------------------------

def test_a_meal_estimate_never_displaces_a_stated_whole_day():
    """THE one that bites. `stated-in-chat` outranks a logger export in the
    precedence ladder, so writing a meal estimate into `kcal_in` would
    displace the athlete's own itemised day when it arrived - a model's guess
    beating the athlete's own record.
    """
    day = {"date": "2030-05-01", "kcal_in": 2210, "source": "mfp-export"}
    found = day_disagreements(PLATE, [day])
    assert len(found) == 1
    assert found[0]["stated"] == 2210
    assert "neither figure supersedes the other" in found[0]["detail"]


def test_the_meal_sum_being_lower_is_the_expected_case_not_a_disagreement():
    """Meals the athlete did not photograph are missing from one figure and
    present in the other, so this is reported rather than adjudicated."""
    day = {"date": "2030-05-01", "kcal_in": 2210, "source": "mfp-export"}
    found = day_disagreements(PLATE, [day])
    assert found[0]["meals_hi"] < 2210
    assert "not a correction" in found[0]["detail"]


def test_meals_never_displace_a_stated_whole_day_through_resolution(tmp_path):
    """The hazard stated as it actually happens, THROUGH the resolver.

    The previous version of this test wrote only meals, so `canonical("daily")`
    was empty and `all(...)` was trivially true - it could only have caught an
    engine that invented daily rows from nothing, not one that displaced an
    existing figure. This writes the whole-day row the meal estimate would
    have to beat.
    """
    root = repo(tmp_path)
    write(root, PLATE)
    (root / "data" / "daily.jsonl").write_text(json.dumps({
        "date": "2030-05-01", "kcal_in": 2210, "source": "mfp-export",
        "steps": None, "distance_km": None, "active_min": None,
        "kcal_out": None, "protein_g": None, "sleep_h": None, "rhr": None,
        "hip_pain": None, "alcohol": None, "note": None}) + "\n",
        encoding="utf-8")
    day = [r for r in Vitai(root).canonical("daily")
           if r["date"] == "2030-05-01"]
    assert len(day) == 1
    assert day[0]["kcal_in"] == 2210, "a meal estimate displaced the athlete"
    assert day[0]["source"] == "mfp-export"


def test_the_comparison_quotes_the_figure_precedence_chose(tmp_path):
    """With two sources on one day, the raw rows carry both. Quoting whichever
    landed last in the file would cite the figure precedence decided AGAINST,
    which is worse than not comparing at all.
    """
    root = repo(tmp_path)
    write(root, PLATE)
    base = {"steps": None, "distance_km": None, "active_min": None,
            "kcal_out": None, "protein_g": None, "sleep_h": None,
            "rhr": None, "hip_pain": None, "alcohol": None, "note": None}
    (root / "data" / "daily.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kcal_in": 2210, "source": "app", **base},
        {"date": "2030-05-01", "kcal_in": 1950, "source": "watch", **base},
    ]) + "\n", encoding="utf-8")
    with (root / "vitai.toml").open("a", encoding="utf-8") as fh:
        fh.write("\n[resolution.precedence]\nkcal_in = [\"app\"]\n")
    found = Vitai(root).meal_day_disagreements()
    assert found[0]["stated"] == 2210, "quoted the losing claim"


def test_a_day_with_no_stated_intake_produces_no_comparison():
    assert day_disagreements(PLATE, []) == []


# ---- provenance --------------------------------------------------------------------

def test_a_composition_figure_names_the_table_it_came_from():
    """Two items in one meal can legitimately come from different tables,
    and a figure whose source is unrecorded cannot be rechecked when that
    table is revised."""
    orphan = {**item("tomato", 70, kcal_100g=18), "food_table": None}
    assert any("food_table" in p for p in validate_record("meals", orphan))


def test_an_estimate_can_say_it_was_read_off_a_photograph():
    """#78's axis, one domain over: a photo-derived kcal and a barcode
    scan must stay distinguishable forever."""
    row = item("chicken thigh", 165, 140, 200, kcal_100g=240,
               origin="athlete", capture="photo", read_by="model")
    assert validate_record("meals", row) == []


def test_a_photo_read_by_nobody_is_rejected_here_too():
    row = item("chicken thigh", 165, kcal_100g=240, capture="photo")
    assert any("read_by" in p for p in validate_record("meals", row))


def test_a_quantity_range_out_of_order_is_a_validation_error():
    assert any("range out of order" in p for p in validate_record(
        "meals", item("tomato", 70, lo=80, hi=60, kcal_100g=18)))


def test_a_bound_needs_something_to_bound():
    assert any("need" in p for p in validate_record(
        "meals", item("tomato", lo=60, hi=80, kcal_100g=18)))


# ---- the surface -----------------------------------------------------------------------

def test_the_cli_never_prints_a_bare_total(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, PLATE)
    capsys.readouterr()
    main(["meals", "--root", str(root)])
    out = capsys.readouterr().out
    assert "kcal" in out
    total = meal_total(PLATE)
    assert f"{total['lo']:.0f}-{total['hi']:.0f} kcal" in out
    assert "chicken thigh" in out and "usda" in out
    # Every kcal figure printed must be a range, whatever it is formatted
    # like: pinning one midpoint spelling would pass a regression that
    # printed "total: 552.2 kcal" or "552kcal" instead.
    import re
    for line in out.splitlines():
        # The narrative line talks about the WIDTH of the range ("144 of 212
        # kcal"), which is a single number by construction and is the
        # opposite of a bare total - it exists to say how uncertain the
        # total is.
        if "most of the range is" in line:
            continue
        for figure in re.findall(r"([\d.,-]+)\s*kcal", line):
            assert "-" in figure, (
                f"a bare kcal figure reached the output: {figure!r} in {line!r}")


def test_the_cli_asks_rather_than_assuming(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [*PLATE, item("sweetcorn")])
    capsys.readouterr()
    main(["meals", "--root", str(root)])
    out = capsys.readouterr().out
    assert "ask: sweetcorn" in out
    assert "not priced" in out


def test_every_dataset_can_actually_be_created_as_a_table():
    """`table` was the obvious name for where a composition figure came from,
    and it is a SQL reserved word - the read model refused to build.

    Asserted by CREATING the tables rather than by checking names against a
    keyword list I would have to keep correct: `key` on `thresholds` is in
    SQLite's keyword list and is perfectly legal as a column, so a list-based
    version of this test is both a false positive there and no guarantee
    anywhere else. The question is only ever "does SQLite accept it".
    """
    import sqlite3

    from vitai.db import _cols
    con = sqlite3.connect(":memory:")
    try:
        for dataset, keys in KEYS.items():
            con.execute(f"CREATE TABLE {dataset}({_cols(keys)})")
    finally:
        con.close()


def test_the_manifest_reaches_the_read_model(tmp_path):
    import sqlite3
    root = repo(tmp_path)
    write(root, PLATE)
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        rows = con.execute(
            "SELECT item, grams, food_table FROM meals ORDER BY item").fetchall()
    finally:
        con.close()
    assert ("chicken thigh", 165.0, "usda") in rows


# ---- what the review of this feature found ------------------------------------------

def test_correcting_one_item_does_not_retire_the_whole_plate(tmp_path):
    """The #43 defect in a new dataset, and in the one whose premise is that
    the ITEM is the unit of estimate - so it has to be the unit of correction
    too. Every item of one plate shares a date and a source, so a
    `supersedes` aimed at the chicken retired the olives and the tomato.
    """
    root = repo(tmp_path)
    v = Vitai(root)
    for row in PLATE:
        v.append("meals", {k: val for k, val in row.items()
                           if k != "recorded_at"})
    v.append("meals", {**{k: val for k, val in PLATE[0].items()
                          if k != "recorded_at"},
                       "grams": 200, "grams_lo": 190, "grams_hi": 210,
                       "supersedes": "lunch/chicken thigh@2030-05-01"})
    live = v.dataset("meals")
    assert sorted(r["item"] for r in live) == [
        "chicken thigh", "cooking oil", "green olives", "tomato"]
    assert next(r for r in live if r["item"] == "chicken thigh")["grams"] == 200


def test_a_negative_quantity_is_rejected_rather_than_subtracting_energy():
    """It passes the ordering check (-50 <= -50 <= -50) and drags the plate
    total down by an arbitrary amount."""
    bad = item("cooking oil", -50, kcal_100g=884)
    assert any("cannot be" in p for p in validate_record("meals", bad))
    assert meal_total([bad])["estimate"] < 0, "the arithmetic really does this"


def test_a_quoted_number_is_rejected_rather_than_read_as_absent():
    """The ordinary hand-edit typo. Without a type check it validates clean,
    then reads as null - so the biggest item on the plate silently leaves the
    total instead of failing.
    """
    typo = {**item("chicken thigh", kcal_100g=240), "grams": "165"}
    assert any("grams" in p for p in validate_record("meals", typo))
    assert meal_total([typo])["unpriced"] == 1, "and this is what it would do"


def test_a_range_bounded_on_one_side_only_is_rejected():
    """`quantity_range` substitutes the point for the missing side, so
    140-165-(none) prints as a bounded "140-165 g" while the uncertainty
    upward - the direction that under-counts intake - is erased.
    """
    half = item("chicken thigh", 165, lo=140, kcal_100g=240)
    assert any("both" in p for p in validate_record("meals", half))
    assert unsettled([half])[0]["why"] == "bounded on one side only"


def test_a_buffer_that_cannot_be_applied_is_an_error_not_a_number():
    """A negative buffer inverts the range and a NaN makes every figure NaN,
    both silently."""
    for bad in (-150, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="intake_buffer_pct"):
            buffered(meal_total(PLATE), bad)


def test_an_explicit_zero_buffer_is_recorded_as_a_decision():
    """`if not pct` read an explicit "no buffer" as "nobody said", which are
    different facts everywhere else in this record."""
    zero = buffered(meal_total(PLATE), 0)
    assert zero["buffer_pct"] == 0
    assert zero["estimate"] == pytest.approx(meal_total(PLATE)["estimate"])


def test_a_zero_calorie_item_is_priced_not_unpriced():
    """0 kcal/100 g is a real figure - water, a diet drink - and is not the
    same as an item nobody has looked up."""
    water = item("sparkling water", 330, 330, 330, kcal_100g=0,
                 food_table="usda")
    assert validate_record("meals", water) == []
    assert meal_total([water])["unpriced"] == 0


def test_an_unbounded_item_does_not_print_like_a_settled_one(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, [item("rice", 150, kcal_100g=130)])
    capsys.readouterr()
    main(["meals", "--root", str(root)])
    out = capsys.readouterr().out
    assert "unbounded" in out
    assert "ask: rice" in out


def test_the_date_filter_scopes_the_day_comparison_too(tmp_path, capsys):
    root = repo(tmp_path)
    write(root, PLATE + [{**r, "date": "2030-05-02"} for r in PLATE])
    base = {"steps": None, "distance_km": None, "active_min": None,
            "kcal_out": None, "protein_g": None, "sleep_h": None,
            "rhr": None, "hip_pain": None, "alcohol": None, "note": None}
    (root / "data" / "daily.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kcal_in": 2210, "source": "app", **base},
        {"date": "2030-05-02", "kcal_in": 2100, "source": "app", **base},
    ]) + "\n", encoding="utf-8")
    capsys.readouterr()
    main(["meals", "--root", str(root), "--on", "2030-05-02"])
    out = capsys.readouterr().out
    assert "2030-05-01" not in out
