"""A persona's narrative and its numbers must be drawn from the same place.

Every defect this file pins was real and shipped green. The generators built
their prose, their regimes and their plans from one source and their data from
another, so each record was internally valid and jointly false: bea trained
and weighed herself during her own recorded sleep, her regime declared four
nights over a stretch the roster made two days off, maja's plan recorded a
session as skipped on an evening with six sets behind it, and her itemised day
disagreed with its own total by 29 g of protein.

None of it broke a test. A fixture corpus is a set of test oracles, so a false
statement in one is a broken oracle even while the suite is green - and the
only thing that catches it is a check that reads BOTH halves and compares
them, which is what this file is.

Written as properties over whichever personas have the data rather than as
assertions about three specific ones, so a new persona is covered on the day
it lands rather than the day somebody remembers.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PERSONAS = Path(__file__).parent / "fixtures" / "personas"
sys.path.insert(0, str(PERSONAS))


def slugs() -> list[str]:
    return sorted(p.name for p in PERSONAS.iterdir()
                  if (p / "vitai.toml").exists())


def rows(slug: str, dataset: str) -> list[dict]:
    path = PERSONAS / slug / "data" / f"{dataset}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line
            in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _woke(slug: str) -> dict[str, datetime]:
    return {r["date"]: datetime.fromisoformat(r["sleep_end"])
            for r in rows(slug, "daily") if r.get("sleep_end")}


# --- the night bounds the day -------------------------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_nothing_is_logged_before_the_athlete_woke(slug: str) -> None:
    """A session inside the athlete's own recorded sleep is a contradiction a
    consumer can only read as signal. bea shipped eleven of them, from two
    generators that never consulted each other."""
    woke = _woke(slug)
    early = [r["date"] for r in rows(slug, "sessions")
             if r.get("start_time") and r["date"] in woke
             and datetime.fromisoformat(r["start_time"]) < woke[r["date"]]]
    assert not early, (slug, early[:5])


@pytest.mark.parametrize("slug", slugs())
def test_no_weigh_in_happens_before_waking(slug: str) -> None:
    """Worse than a session, because the protocol says so out loud: bea's
    weigh-ins are taken under `fasted-post-waking`, and five of them were
    stamped before the sleep row on the same day had ended."""
    woke = _woke(slug)
    for r in rows(slug, "weight"):
        at, day = r.get("measured_at"), r["date"]
        if not at or day not in woke:
            continue
        up = woke[day]
        hour, minute = (int(x) for x in str(at).split(":"))
        assert up.replace(hour=hour, minute=minute) >= up, (slug, day, at)


# --- a sleep interval agrees with its own duration ----------------------------

@pytest.mark.parametrize("slug", slugs())
def test_every_sleep_interval_matches_its_duration(slug: str) -> None:
    for r in rows(slug, "daily"):
        if not (r.get("sleep_start") and r.get("sleep_end")):
            continue
        began = datetime.fromisoformat(r["sleep_start"])
        ended = datetime.fromisoformat(r["sleep_end"])
        assert began.tzinfo and ended.tzinfo, (slug, r["date"])
        assert (ended - began).total_seconds() / 3600 == pytest.approx(
            r["sleep_h"], abs=1e-9), (slug, r["date"])


# --- a declared interval describes something that is there --------------------

@pytest.mark.parametrize("slug", slugs())
def test_a_regime_covers_days_the_record_actually_has(slug: str) -> None:
    """A regime empties or qualifies real days. One covering no rows at all
    describes an event the record does not contain, which is how bea came to
    ship a four-night regime over a stretch containing a morning session."""
    for r in rows(slug, "regimes"):
        covered = [x for x in rows(slug, r["dataset"])
                   if r["from_date"] <= x["date"] <= r["to_date"]
                   and x.get(r["field"]) is not None]
        assert covered, (slug, r["from_date"], r["to_date"], r["field"])


# --- a plan's outcome is what happened -----------------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_a_plan_outcome_agrees_with_the_sessions(slug: str) -> None:
    """`completed` needs a session on the day and `skipped` needs none. maja's
    one skipped plan had a full session behind it, in the fixture built to
    teach the difference between a miss and a circumstance."""
    trained = {r["date"] for r in rows(slug, "sessions")}
    for r in rows(slug, "plans"):
        day, outcome = r.get("for_date"), r.get("outcome")
        if not day or outcome not in ("completed", "skipped"):
            continue
        assert (day in trained) == (outcome == "completed"), (slug, day, outcome)


# --- a total agrees with its parts ---------------------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_an_itemised_day_agrees_with_its_daily_row(slug: str) -> None:
    """Where a day is logged twice - once as a total and once as items - the
    two must agree. Drawn independently they disagreed by 29 g of protein,
    which a consumer cross-checking parts against a total would report as a
    finding about the athlete."""
    meals = rows(slug, "meals")
    if not meals:
        pytest.skip(f"{slug} itemises no meals")
    daily = {r["date"]: r for r in rows(slug, "daily")}
    for day in sorted({m["date"] for m in meals}):
        row = daily.get(day)
        if row is None or row.get("protein_g") is None:
            continue
        for field, per100 in (("protein_g", "protein_100g"),
                              ("carb_g", "carb_100g"), ("fat_g", "fat_100g")):
            total = sum(m[per100] * m["grams"] / 100 for m in meals
                        if m["date"] == day and m.get(per100) is not None)
            assert row[field] == pytest.approx(total, abs=1.0), (
                slug, day, field, row[field], total)


# --- energy agrees with the macros it is made of -------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_energy_agrees_with_the_macros_where_all_four_are_present(slug: str) -> None:
    for r in rows(slug, "daily"):
        have = [r.get(k) for k in ("kcal_in", "protein_g", "carb_g", "fat_g")]
        if any(v is None for v in have):
            continue
        kcal, protein, carb, fat = have
        assert kcal == pytest.approx(protein * 4 + carb * 4 + fat * 9, abs=1.0), \
            (slug, r["date"])


# --- a stack number is not a mass ---------------------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_a_machine_stack_load_is_a_whole_pin_position(slug: str) -> None:
    """The schema already refuses `load_unit: kg` on a stack. It cannot refuse
    a half-value, so maja shipped 37.5 and 42.5 as pin positions under a
    comment asserting they were pin positions."""
    for r in rows(slug, "sets"):
        if r.get("load_type") != "machine_stack" or r.get("load") is None:
            continue
        assert r.get("load_unit") is None, (slug, r["date"])
        assert float(r["load"]).is_integer(), (slug, r["date"], r["load"])


# --- per-side work is not silently lopsided -----------------------------------

@pytest.mark.parametrize("slug", slugs())
def test_unilateral_work_is_balanced_or_the_imbalance_is_declared(slug: str) -> None:
    """A two-to-one asymmetry running for months is a fact about the athlete
    and belongs in the prose. maja's arrived from a parity that never flipped,
    in the fixture that warns against double-counting per-side work."""
    sets = [r for r in rows(slug, "sets") if r.get("side") in ("left", "right")]
    if not sets:
        pytest.skip(f"{slug} logs no unilateral work")
    left = sum(1 for r in sets if r["side"] == "left")
    right = len(sets) - left

    # NO ESCAPE HATCH. The first version let an imbalance through if the
    # persona's WORLD.md contained the word "asymmetry" - and maja's does,
    # inside the sentence explaining that she has none. A control that a
    # document can switch off by mentioning it is not a control. A persona
    # that genuinely wants a lopsided record changes this test on purpose.
    assert abs(left - right) <= max(2, 0.1 * len(sets)), (slug, left, right)


# --- the index knows who exists ------------------------------------------------

def test_the_corpus_readme_lists_every_persona() -> None:
    """Doctrine calls this file the index of who exists, and it said ten while
    thirteen were on disk."""
    text = (PERSONAS / "README.md").read_text(encoding="utf-8")
    for slug in slugs():
        assert f"`{slug}`" in text, slug


@pytest.mark.parametrize("slug", slugs())
def test_a_documented_instrument_interval_covers_its_own_rows(slug: str) -> None:
    """A register entry naming a date range nothing was recorded in describes
    kit the record cannot show was ever used."""
    for r in rows(slug, "instruments"):
        origin, first = r["origin"], r["from_date"]
        last = r.get("to_date") or "9999-12-31"
        seen = any(x.get("origin") == origin and first <= x["date"] <= last
                   for ds in ("daily", "sessions", "weight", "measurements")
                   for x in rows(slug, ds))
        assert seen, (slug, origin, first, last)


# --- bea's regimes are read off her roster, not written beside it -------------

def test_beas_ward_regime_covers_only_night_shifts() -> None:
    """The generic check above only asks that a regime covers rows that exist,
    which the hardcoded dates passed: they were real days with real steps. The
    claim they make is stronger - "four nights on the unit" - and the roster
    made two of them days off and one a day shift.

    So this reads the roster and the regime and compares them. It is
    persona-specific because the roster is."""
    from datetime import date as _date

    from _gen.bea import DEFAULT_END, NIGHT, _roster

    roster = _roster(DEFAULT_END)
    ward = [r for r in rows("bea", "regimes") if r["field"] == "steps"]
    assert ward, "bea declares no ward-steps regime"
    for r in ward:
        day, last = _date.fromisoformat(r["from_date"]), _date.fromisoformat(r["to_date"])
        covered = []
        while day <= last:
            covered.append(roster.get(day))
            day += timedelta(days=1)
        assert set(covered) == {NIGHT}, (r["from_date"], r["to_date"], covered)
        assert f"{len(covered)} nights" in r["text"], r["text"]


def test_beas_scoring_regime_covers_the_days_it_reduced() -> None:
    """The nap-scoring regime says the watch reports short over an interval.
    The first version declared a week in which the scored days read HIGHER
    than her ordinary mean, because the generator never modelled the dip it
    narrated."""
    from datetime import date as _date

    from _gen.bea import DEFAULT_END, NIGHT, _roster

    roster = _roster(DEFAULT_END)
    sleep = [r for r in rows("bea", "regimes") if r["field"] == "sleep_h"]
    assert sleep, "bea declares no scoring regime"
    r = sleep[0]

    after_night = [(x["date"], x["sleep_h"]) for x in rows("bea", "daily")
                   if x.get("sleep_start") and roster.get(
                       _date.fromisoformat(x["date"]) - timedelta(days=1)) == NIGHT]
    inside = [v for d, v in after_night if r["from_date"] <= d <= r["to_date"]]
    outside = [v for d, v in after_night if not (r["from_date"] <= d <= r["to_date"])]
    assert len(inside) >= 3, inside
    assert sum(inside) / len(inside) < sum(outside) / len(outside) - 0.5, (
        sum(inside) / len(inside), sum(outside) / len(outside))
