"""A comparability rule between instruments, EARNED BY OVERLAP (#33 item 2).

#171 settled item 3 of #33 - the instrument seam is a fact about the rows and
needs no comparability rule to detect. This is items 1 and 2 the other way
round: once a seam is detected, does anything license spanning it? The
default is NOT COMPARABLE, which is #33's own acceptance criterion rather
than an engineering choice - deriving a trend across a source change needs an
explicit statement that the two sides are on the same footing, never an
assumption because both are called weight.

#171 section 4.1's own words: "Comparability earned by overlap, never
asserted. A period of simultaneous measurement from two instruments yields a
measured offset instead of a borrowed one." So `basis` is `overlap` and only
`overlap`, closed to one value - the whole point is that this cannot be
asserted from a datasheet, a vendor figure or an athlete's say-so.

`offset` DOES NOT LICENSE A DERIVATION, tested explicitly because it is the
easiest thing here to get backwards: a status that HOLDS A NUMBER reads as
more permissive than one that does not, and it is not. It records that a
cross-instrument difference was measured and how big it was; applying that
number to a reading would be fabricating a measurement (P4), so the
weight-rate seam refusal lifts only for `comparable`.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.policy import all_comparable, comparability
from vitai.schema import (COMPARABILITY_STATUSES, KEYS, OVERLAP_BASIS,
                          validate_record)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def crow(when: str, field: str, origin_a: str, origin_b: str, status: str,
        **kw) -> dict:
    return {**{k: None for k in KEYS["comparability"]}, "date": when,
            "field": field, "origin_a": origin_a, "origin_b": origin_b,
            "status": status, "source": "athlete",
            "recorded_at": f"{when}T08:00:00Z", **kw}


def wrow(when: str, kg: float, origin: str | None,
        source: str = "scale") -> dict:
    return {**{k: None for k in KEYS["weight"]}, "date": when, "kg": kg,
            "source": source, "origin": origin,
            "recorded_at": f"{when}T07:00:00Z"}


def record(tmp_path: Path, weight: list[dict] | None = None,
          comparability_rows: list[dict] | None = None) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[targets]\nphases = [[90.0, 70.0, 0.5]]\n',
        encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in weight or []), encoding="utf-8")
    (root / "data" / "comparability.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in comparability_rows or []),
        encoding="utf-8")
    return Vitai(root, on=date(2030, 5, 14))


def series(origin_a: str, origin_b: str) -> list[dict]:
    """A fortnight of daily readings, the second week on another device -
    `test_instrument_seam.py`'s own fixture, reused rather than reinvented so
    the two suites cannot silently drift on what a seamed window looks like.
    """
    out = []
    for n in range(1, 15):
        origin = origin_a if n <= 7 else origin_b
        out.append(wrow(f"2030-05-{n:02d}", 82.0 - n * 0.2, origin))
    return out


# --- silence resolves to a value, not to a default -----------------------------

def test_silence_resolves_to_not_comparable_stated_false():
    """THE #148 LESSON, one dataset over, and #33's own acceptance criterion:
    the default is NOT COMPARABLE, never an assumption because two readings
    share a field name."""
    got = comparability([], "kg", "scale", "dexa", "2030-06-01")
    assert got["status"] == "not_comparable"
    assert got["stated"] is False
    assert got["bias"] is None and got["spread"] is None
    assert got["basis"] is None and got["overlap_ref"] is None


def test_it_never_returns_none():
    for field in ("kg", "rhr", "steps"):
        got = comparability([], field, "a", "b", "2030-06-01")
        assert got is not None
        assert got["status"] in COMPARABILITY_STATUSES


# --- order-insensitivity ---------------------------------------------------------

def test_the_pair_is_order_insensitive():
    """Whether a scale and a DEXA agree is one fact about the PAIR, not about
    which one a caller names first."""
    rows = [crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="a fortnight in April")]
    forward = comparability(rows, "kg", "scale", "dexa", "2030-06-01")
    backward = comparability(rows, "kg", "dexa", "scale", "2030-06-01")
    assert forward["status"] == backward["status"] == "comparable"


def test_order_insensitivity_holds_for_the_default_too():
    backward = comparability([], "kg", "dexa", "scale", "2030-06-01")
    forward = comparability([], "kg", "scale", "dexa", "2030-06-01")
    assert forward["status"] == backward["status"] == "not_comparable"


def test_a_row_written_with_the_pair_swapped_still_answers():
    """Two rows recorded with the origins swapped are two independent
    identities as far as `supersedes` is concerned - the resolver, not
    storage, reconciles them. The most recently dated one wins, the same
    tie-break `_in_force` already applies within one identity."""
    rows = [crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="January overlap"),
            crow("2030-03-01", "kg", "dexa", "scale", "not_comparable")]
    got = comparability(rows, "kg", "scale", "dexa", "2030-06-01")
    assert got["status"] == "not_comparable", got


# --- dated, through the machinery `capability` already uses --------------------

def test_a_comparability_row_is_read_as_of_a_date():
    rows = [crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="a fortnight in January")]
    assert comparability(rows, "kg", "scale", "dexa",
                        "2030-01-15")["status"] == "comparable"


def test_a_row_dated_after_the_viewpoint_is_invisible():
    """The resolver is EFFECTIVE-DATED: a statement takes effect on its own
    date, and a past viewpoint never sees a later one."""
    rows = [crow("2030-06-01", "kg", "scale", "dexa", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="a fortnight in May")]
    got = comparability(rows, "kg", "scale", "dexa", "2030-01-01")
    assert got["status"] == "not_comparable", got
    assert got["stated"] is False


def test_the_identity_is_the_field_and_the_pair():
    """A pair may be declared comparable for one field and not another - the
    identity has to carry the field, or the second statement would retire
    the first."""
    rows = [crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="weigh-ins"),
            crow("2030-01-01", "body_fat_pct", "scale", "dexa",
                "not_comparable")]
    assert comparability(rows, "kg", "scale", "dexa",
                        "2030-06-01")["status"] == "comparable"
    assert comparability(rows, "body_fat_pct", "scale", "dexa",
                        "2030-06-01")["status"] == "not_comparable"


# --- fail closed: a row must EARN comparable/offset, not merely claim it -------
# (#373 review). `jsonl.load` quarantines a line that fails to PARSE and
# nothing else - a line that parses but fails the SCHEMA comes through it
# untouched, because `build`/`verdicts` read straight off `load`, never off
# `validate_record`. Every dataset before this one only ever LOST a positive
# claim to that gap; this one can WEAKEN a refusal through it, so the
# resolver has to distrust its own input the way any other gate does.

def test_a_row_that_has_not_earned_its_status_resolves_to_not_comparable():
    """`basis: 'stated'` with no `overlap_ref` is exactly the shape a
    hand-written line took in the review that found this: it lifted the
    weight-rate seam and a verdict came back `ahead` on a difference two
    scales produced, not the athlete."""
    unearned = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                    basis="stated", overlap_ref=None)
    got = comparability([unearned], "kg", "scale", "dexa", "2030-06-01")
    assert got["status"] == "not_comparable", got
    assert got["stated"] is False


def test_an_unearned_offset_also_resolves_to_not_comparable():
    unearned = crow("2030-01-01", "kg", "scale", "dexa", "offset",
                    basis="stated", overlap_ref=None, bias=1.0)
    got = comparability([unearned], "kg", "scale", "dexa", "2030-06-01")
    assert got["status"] == "not_comparable", got


def test_an_unearned_row_is_absent_not_a_downgrade_in_place():
    """An unearned row does not become `not_comparable` WHERE IT STANDS - it
    is treated as though it were never written. `(field, origin_a, origin_b)`
    is the stored identity, and `(field, origin_b, origin_a)` is a DIFFERENT
    one that the resolver still asks about (order-insensitivity,
    `test_a_row_written_with_the_pair_swapped_still_answers`), so an earned
    row on one identity has to keep answering even where a later, unearned
    row was written on the other: a downgrade-in-place would let the
    unearned row's later date win the tie-break instead."""
    earned = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                  basis=OVERLAP_BASIS, overlap_ref="January overlap")
    unearned_later_swapped = crow("2030-03-01", "kg", "dexa", "scale",
                                  "comparable", basis="stated",
                                  overlap_ref=None)
    got = comparability([earned, unearned_later_swapped], "kg", "scale",
                        "dexa", "2030-06-01")
    assert got["status"] == "comparable", got


def test_an_unearned_row_does_not_lift_the_weight_rate_seam(tmp_path):
    """The end-to-end shape of the finding: a hand-written line claiming
    `comparable` without earning it must not reach the weight rate, and
    `vitai validate` still has to report the line as malformed - a different
    question from whether the seam stays refused."""
    unearned = crow("2030-04-01", "kg", "aria-scale", "withings-scale",
                    "comparable", basis="stated", overlap_ref=None)
    v = record(tmp_path, series("aria-scale", "withings-scale"), [unearned])
    rates = [r for r in v.verdicts()
            if r["metric"] == "weight_rate" and r["value"] is not None]
    assert rates and all(r["verdict"] == "no_data" for r in rates), rates
    assert all(r["reason"] == "not_supported" for r in rates), rates

    warnings = v.load_report()["warnings"]
    assert any("basis" in w for w in warnings), warnings


def test_a_not_comparable_row_needs_no_earning():
    """The gate is about WEAKENING a refusal. A `not_comparable` row can only
    add to a refusal that is already the default, so it is honoured
    regardless of `basis` - `vitai validate` reports it as malformed
    separately, which does not change what the seam does."""
    rec = crow("2030-01-01", "kg", "scale", "dexa", "not_comparable",
              basis="stated")
    got = comparability([rec], "kg", "scale", "dexa", "2030-06-01")
    assert got["status"] == "not_comparable", got


# --- validation: what a claim owes -----------------------------------------------

def test_basis_must_be_overlap_and_nothing_else():
    """The whole point: this cannot be asserted from a datasheet, a vendor
    figure or an athlete's say-so."""
    for bad in ("stated", "observed", "datasheet", None):
        rec = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
                   basis=bad, overlap_ref="a fortnight")
        problems = validate_record("comparability", rec)
        assert any("basis" in p for p in problems), (bad, problems)

    good = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
               basis=OVERLAP_BASIS, overlap_ref="a fortnight")
    assert validate_record("comparability", good) == []


def test_an_offset_with_no_bias_is_an_assertion_not_a_measurement():
    bad = crow("2030-01-01", "kg", "scale", "dexa", "offset",
              basis=OVERLAP_BASIS, overlap_ref="a fortnight", spread=0.1)
    problems = validate_record("comparability", bad)
    assert any("bias" in p for p in problems), problems

    good = crow("2030-01-01", "kg", "scale", "dexa", "offset",
               basis=OVERLAP_BASIS, overlap_ref="a fortnight", bias=0.6,
               spread=0.1)
    assert validate_record("comparability", good) == []


def test_an_offset_with_no_spread_is_also_an_assertion():
    """#171's decision named BOTH `bias` and `spread` required beside
    `offset` - a measured size with no reported spread is a number with no
    idea how firm it is, and #373's review found only `bias` was actually
    enforced."""
    bad = crow("2030-01-01", "kg", "scale", "dexa", "offset",
              basis=OVERLAP_BASIS, overlap_ref="a fortnight", bias=0.6)
    problems = validate_record("comparability", bad)
    assert any("spread" in p for p in problems), problems


def test_a_non_numeric_spread_is_rejected():
    """#373 review: `spread` was never type-checked, so `spread: "banana"`
    validated clean beside a required-ness check that only asked whether the
    key was present."""
    bad = crow("2030-01-01", "kg", "scale", "dexa", "offset",
              basis=OVERLAP_BASIS, overlap_ref="a fortnight", bias=0.6,
              spread="banana")
    problems = validate_record("comparability", bad)
    assert any("spread" in p for p in problems), problems


def test_bias_is_contradictory_beside_comparable():
    """A MEASURED bias means the two instruments read differently by a known
    amount - that is what `offset` is for. `comparable` beside a `bias` is a
    row disagreeing with itself."""
    bad = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
              basis=OVERLAP_BASIS, overlap_ref="a fortnight", bias=0.4)
    problems = validate_record("comparability", bad)
    assert any("bias" in p for p in problems), problems


def test_spread_is_permitted_beside_comparable():
    """NOT a contradiction the way `bias` is: `spread` says how tightly the
    two instruments agreed over the overlap, which is meaningful evidence
    about a pair the record has already called comparable."""
    good = crow("2030-01-01", "kg", "scale", "dexa", "comparable",
               basis=OVERLAP_BASIS, overlap_ref="a fortnight", spread=0.05)
    assert validate_record("comparability", good) == []


def test_a_bias_on_a_refusal_is_meaningless():
    bad = crow("2030-01-01", "kg", "scale", "dexa", "not_comparable", bias=0.4)
    problems = validate_record("comparability", bad)
    assert any("bias" in p for p in problems), problems

    bad_spread = crow("2030-01-01", "kg", "scale", "dexa", "not_comparable",
                      spread=0.1)
    assert any("spread" in p for p in validate_record("comparability",
                                                       bad_spread))

    # `basis` is required on every row regardless of status - it names the
    # ONLY route this dataset accepts, and a refusal reached by checking an
    # overlap and finding no agreement states that route the same as a
    # `comparable` row does. `overlap_ref` is the one that stays optional
    # here: asserting a negative earns nothing and needs no evidence.
    good = crow("2030-01-01", "kg", "scale", "dexa", "not_comparable",
               basis=OVERLAP_BASIS)
    assert validate_record("comparability", good) == []


def test_comparable_and_offset_require_an_overlap_ref():
    for status in ("comparable", "offset"):
        rec = crow("2030-01-01", "kg", "scale", "dexa", status,
                   basis=OVERLAP_BASIS, bias=0.5 if status == "offset" else None)
        problems = validate_record("comparability", rec)
        assert any("overlap_ref" in p for p in problems), (status, problems)

    # not_comparable earns nothing and needs no OVERLAP_REF to assert -
    # `basis` still has to be `overlap`, the only route this dataset accepts.
    refusal = crow("2030-01-01", "kg", "scale", "dexa", "not_comparable",
                   basis=OVERLAP_BASIS)
    assert validate_record("comparability", refusal) == []


def test_the_status_vocabulary_is_closed():
    rec = crow("2030-01-01", "kg", "scale", "dexa", "probably")
    assert any("status" in p for p in validate_record("comparability", rec))
    assert COMPARABILITY_STATUSES == {"comparable", "offset", "not_comparable"}


def test_the_two_instruments_must_be_named_and_different():
    missing = crow("2030-01-01", "kg", "scale", None, "not_comparable")
    assert any("origin_b" in p for p in validate_record("comparability", missing))

    same = crow("2030-01-01", "kg", "scale", "scale", "not_comparable")
    assert any("origin_a" in p or "origin_b" in p
              for p in validate_record("comparability", same))


def test_it_can_only_be_about_a_field_the_record_has():
    rec = crow("2030-01-01", "vibes", "scale", "dexa", "not_comparable")
    assert any("field" in p for p in validate_record("comparability", rec))


def test_field_must_be_a_measurement_not_any_column(tmp_path):
    """#373 review: the old check (`field in {every key of every dataset}`)
    accepted `"note"` and `"origin_a"` exactly as readily as `"kg"`, because
    it was built from the same key set it was meant to police. `sensitivity`
    is the engine's own per-field classification (#299) - reused rather than
    a second field list kept in step with it - and only a field classified
    `measurement` is a quantity two instruments could disagree about."""
    for bad_field in ("note", "origin_a", "source", "status"):
        rec = crow("2030-01-01", bad_field, "scale", "dexa", "not_comparable")
        problems = validate_record("comparability", rec)
        assert any("field" in p for p in problems), (bad_field, problems)

    for good_field in ("kg", "body_fat_pct", "steps", "rhr"):
        rec = crow("2030-01-01", good_field, "scale", "dexa", "not_comparable",
                   basis=OVERLAP_BASIS)
        problems = validate_record("comparability", rec)
        assert not any("field" in p for p in problems), (good_field, problems)


# --- and what it does to the weight-rate seam refusal (#33 item 3) -------------

def test_a_comparable_declaration_lifts_the_refusal(tmp_path):
    """The acceptance criterion the other way: an EXPLICIT statement, earned
    by overlap, is the only thing that gets a spanning rate back."""
    rows = [crow("2030-04-01", "kg", "aria-scale", "withings-scale",
                "comparable", basis=OVERLAP_BASIS,
                overlap_ref="a fortnight of same-day dual readings")]
    v = record(tmp_path, series("aria-scale", "withings-scale"), rows)
    rates = [r for r in v.verdicts()
            if r["metric"] == "weight_rate" and r["value"] is not None]
    assert rates, "the record has a rate to judge"
    assert all(r["verdict"] != "no_data" for r in rates), rates


def test_a_not_comparable_declaration_does_not_lift_it(tmp_path):
    rows = [crow("2030-04-01", "kg", "aria-scale", "withings-scale",
                "not_comparable")]
    v = record(tmp_path, series("aria-scale", "withings-scale"), rows)
    rates = [r for r in v.verdicts()
            if r["metric"] == "weight_rate" and r["value"] is not None]
    assert rates and all(r["verdict"] == "no_data" for r in rates), rates
    assert all(r["reason"] == "not_supported" for r in rates), rates


def test_silence_does_not_lift_it_either(tmp_path):
    v = record(tmp_path, series("aria-scale", "withings-scale"), [])
    rates = [r for r in v.verdicts()
            if r["metric"] == "weight_rate" and r["value"] is not None]
    assert rates and all(r["verdict"] == "no_data" for r in rates), rates


def test_an_offset_declaration_does_not_lift_it():
    """THE ONE MOST LIKELY TO BE GOTTEN BACKWARDS. `offset` holds a number
    and reads as more permissive than a bare refusal; it is not. Applying a
    measured cross-instrument difference to a reading would be fabricating a
    measurement (P4), so the rate still refuses beside it - never averaged
    out, never applied."""
    rows = [crow("2030-04-01", "kg", "aria-scale", "withings-scale", "offset",
                basis=OVERLAP_BASIS, bias=0.6, spread=0.1,
                overlap_ref="a fortnight of same-day dual readings")]
    assert all_comparable(rows, "kg", ["aria-scale", "withings-scale"],
                          "2030-06-01") is False


def test_all_comparable_requires_every_pair(tmp_path):
    """Three instruments in a window: `comparable` between two of them is not
    enough, because the seam a rate spans may be the third pair."""
    rows = [crow("2030-01-01", "kg", "a", "b", "comparable",
                basis=OVERLAP_BASIS, overlap_ref="overlap ab")]
    assert all_comparable(rows, "kg", ["a", "b", "c"], "2030-06-01") is False

    rows += [crow("2030-01-01", "kg", "a", "c", "comparable",
                  basis=OVERLAP_BASIS, overlap_ref="overlap ac"),
            crow("2030-01-01", "kg", "b", "c", "comparable",
                  basis=OVERLAP_BASIS, overlap_ref="overlap bc")]
    assert all_comparable(rows, "kg", ["a", "b", "c"], "2030-06-01") is True


def test_the_rollup_reflects_a_lifted_refusal(tmp_path):
    """`report.build_report` shares the gate with `verdicts.compute_verdicts`
    (#33 item 3's own rollup line), so the two surfaces cannot drift."""
    rows = [crow("2030-04-01", "kg", "aria-scale", "withings-scale",
                "comparable", basis=OVERLAP_BASIS,
                overlap_ref="a fortnight of same-day dual readings")]
    out = record(tmp_path, series("aria-scale", "withings-scale"),
                rows).rollup()
    line = [ln for ln in out.splitlines() if ln.startswith("**Rate:**")][0]
    assert "NOT COMPARABLE" not in line, line


def test_the_rollup_still_refuses_beside_an_offset(tmp_path):
    rows = [crow("2030-04-01", "kg", "aria-scale", "withings-scale", "offset",
                basis=OVERLAP_BASIS, bias=0.6,
                overlap_ref="a fortnight of same-day dual readings")]
    out = record(tmp_path, series("aria-scale", "withings-scale"),
                rows).rollup()
    line = [ln for ln in out.splitlines() if ln.startswith("**Rate:**")][0]
    assert "NOT COMPARABLE" in line, line
    assert "different instruments" in line


# --- the two surfaces share a VIEWPOINT, not only a definition (#373 review) ---
#
# `compute_verdicts` resolved comparability as of `wk`, the Monday of the
# week it is judging; `report.build_report` resolved it as of `today`, the
# moment the report happens to be built. `series()`'s fixture runs through
# 2030-05-14, a Tuesday, whose week starts Monday 2030-05-13 - so a row dated
# 2030-05-14 (the record() default `on`) used to be IN FORCE by `today` but
# not yet by that week's own Monday: the rollup said the rate was comparable
# while the verdicts table for the identical week still refused it. Both now
# ask the same question of the record.

def test_verdicts_and_report_agree_on_a_row_dated_inside_the_week(tmp_path):
    rows = [crow("2030-05-14", "kg", "aria-scale", "withings-scale",
                "comparable", basis=OVERLAP_BASIS,
                overlap_ref="mid-week overlap")]
    v = record(tmp_path, series("aria-scale", "withings-scale"), rows)
    week = "2030-05-13"  # the Monday `pts[-1]` (2030-05-14) falls in

    verdict_rows = [r for r in v.verdicts()
                    if r["metric"] == "weight_rate" and r["week"] == week]
    assert verdict_rows, verdict_rows
    assert verdict_rows[0]["verdict"] == "no_data", verdict_rows[0]
    assert verdict_rows[0]["reason"] == "not_supported", verdict_rows[0]

    line = [ln for ln in v.rollup().splitlines()
           if ln.startswith("**Rate:**")][0]
    assert "NOT COMPARABLE" in line, line


def test_verdicts_and_report_agree_on_a_row_dated_before_the_week(tmp_path):
    """The control case: dated at the week's own Monday or earlier, the row
    is in force by BOTH viewpoints, and both surfaces lift the refusal."""
    rows = [crow("2030-05-13", "kg", "aria-scale", "withings-scale",
                "comparable", basis=OVERLAP_BASIS,
                overlap_ref="overlap declared at the week's start")]
    v = record(tmp_path, series("aria-scale", "withings-scale"), rows)
    week = "2030-05-13"

    verdict_rows = [r for r in v.verdicts()
                    if r["metric"] == "weight_rate" and r["week"] == week]
    assert verdict_rows, verdict_rows
    assert verdict_rows[0]["verdict"] != "no_data", verdict_rows[0]

    line = [ln for ln in v.rollup().splitlines()
           if ln.startswith("**Rate:**")][0]
    assert "NOT COMPARABLE" not in line, line


# --- the surfaces -----------------------------------------------------------------

def test_it_reaches_the_api():
    v = Vitai(DEMO)
    got = v.comparability("kg", "scale", "dexa")
    assert got["status"] == "comparable", got
    swapped = v.comparability("kg", "dexa", "scale")
    assert swapped["status"] == "comparable"
    assert v.comparability("kg", "scale", "watch")["status"] == "not_comparable"


def test_it_reaches_the_read_model():
    import sqlite3

    con = sqlite3.connect(Vitai(DEMO).build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(comparability)")]
        assert "status" in cols and "origin_a" in cols and "origin_b" in cols
        got = con.execute(
            "SELECT status FROM comparability WHERE field = 'kg'").fetchone()
        assert got == ("comparable",), got
    finally:
        con.close()


def test_it_reaches_the_cli():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["comparability", "--root", str(DEMO), "--field", "kg",
             "--origin-a", "scale", "--origin-b", "dexa"])
    out = buf.getvalue()
    assert "comparable" in out, out


def test_the_cli_needs_a_full_question():
    from vitai.cli import main

    try:
        main(["comparability", "--root", str(DEMO), "--field", "kg"])
        raised = False
    except SystemExit:
        raised = True
    assert raised, "a partial question should refuse rather than guess"


def test_it_reaches_the_agent_surface():
    from vitai.mcp import call, tool_list

    assert any(t["name"] == "comparability" for t in tool_list())
    got = call(DEMO, "comparability",
              {"field": "kg", "origin_a": "scale", "origin_b": "dexa"})
    assert got["status"] == "comparable", got
