"""A goal to reach a level is not a goal to accumulate (#273, #274).

`goal_progress` is accumulation-shaped: `counted` is a sum of contributions
over a period and `progress_pct` is that sum against a target. That is right
for do-more-of-this, and it is not what a body-mass goal is. Nothing
accumulates; the measure is the latest value against a level, and the question
is which side of the line it falls on.

So "Down to 78 kg" reported nothing at all - no count, no percentage, no
breach - beside accumulation goals that worked. `counted` was not broken. It
was correctly declining a question it was not built for, and nothing else
answered it.

The demo half matters as much (#274): `examples/demo` is what a third party
gets, so a distinction it cannot exhibit is one no client author discovers.
Every goal in it was a floor, so contract 24's ceiling was invisible and the
first consumer to meet one met it in production.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai, init
from vitai.contributions import ANCHOR_DATASETS, CONTRIBUTING_DATASETS
from vitai.db import CONTRACT_VERSION, PROGRESS_KEYS
from vitai.schema import GOAL_DATASETS

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _record(tmp_path: Path, kgs: list[tuple[str, float]], **goal) -> Vitai:
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "weight",
                       "title": "a level goal", "metric": "kg",
                       "policy": "monotonic", "period": "none",
                       "lifecycle_status": "active", **goal})
    for day, kg in kgs:
        v.append("weight", {"date": day, "kg": kg, "source": "scale"})
    return v


def test_a_level_goal_is_scored_on_its_latest_observation(tmp_path):
    """The defect: a level goal reported nothing while the flow goals beside
    it worked. It now says where the athlete stands and by how much."""
    v = _record(tmp_path, [("2030-05-02", 80.0), ("2030-05-20", 75.9)],
                target=78, polarity="ceiling")

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["observed"] == 75.9
    assert row["counted"] is None, "a level does not accumulate"
    assert row["room_left"] == 2.1
    assert row["breach"] is None
    assert row["achievement_status"] == "achieved"


def test_the_latest_observation_is_the_latest_and_not_a_mean(tmp_path):
    """A mean over the period answers a different question, and one the engine
    already answers elsewhere: `weight_rate` in `verdicts` is where "are you
    moving at the right speed" belongs."""
    v = _record(tmp_path, [("2030-05-02", 90.0), ("2030-05-03", 80.0),
                           ("2030-05-04", 76.0)],
                target=78, polarity="ceiling")

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["observed"] == 76.0        # not 82.0, the mean


def test_a_level_over_its_ceiling_reports_the_breach(tmp_path):
    v = _record(tmp_path, [("2030-05-02", 81.4)], target=78,
                polarity="ceiling")

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["breach"] == "over"
    assert row["room_left"] == -3.4


def test_a_level_goal_reaching_from_below_is_a_floor(tmp_path):
    """The direction is the goal's to declare, not the engine's to assume.
    Gaining to a target is a floor and scores as one."""
    v = _record(tmp_path, [("2030-05-02", 61.0)], target=65, polarity="floor")

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["observed"] == 61.0
    assert row["progress_pct"] is not None      # the floor's own measure
    assert row["breach"] == "under"


def test_an_observation_after_the_viewpoint_is_not_used(tmp_path):
    """A level goal answers as of a date like everything else here."""
    v = _record(tmp_path, [("2030-05-02", 80.0), ("2030-06-01", 74.0)],
                target=78, polarity="ceiling")

    early, = [r for r in v.goals(__import__("datetime").date(2030, 5, 10))
              if r["slug"] == "weight"]

    assert early["observed"] == 80.0


def test_a_flow_goal_is_untouched_and_carries_no_observation(tmp_path):
    """Which column holds the number is how a consumer tells the two shapes
    apart, so a flow goal must not start carrying one."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "steps",
                       "title": "walk more", "metric": "steps", "target": 70000,
                       "policy": "monotonic", "period": "weekly",
                       "dataset": "daily", "lifecycle_status": "active"})
    v.append("daily", {"date": "2030-05-02", "steps": 9000, "source": "phone"})

    row, = [r for r in v.goals(__import__("datetime").date(2030, 5, 3))
            if r["slug"] == "steps"]

    assert row["counted"] == 9000
    assert row["observed"] is None


def test_the_two_sets_do_not_overlap_and_do_not_cover_everything():
    """`measurements` is in neither, deliberately, and the gap is stated.

    An earlier version asserted the two sets PARTITION `GOAL_DATASETS` and
    put `measurements` in the anchor half to make that true. It is
    entity-attribute-value - the quantity is in `value`, keyed by `kind` - so
    a goal naming metric `value` scored against the latest reading of any
    kind, and a body-fat percentage answered a waist-circumference ceiling.
    Reporting the wrong instrument is not an improvement on reporting
    nothing, which is the trade this whole change refuses.
    """
    assert not (ANCHOR_DATASETS & CONTRIBUTING_DATASETS)
    assert ANCHOR_DATASETS | CONTRIBUTING_DATASETS < GOAL_DATASETS
    assert GOAL_DATASETS - ANCHOR_DATASETS - CONTRIBUTING_DATASETS == {
        "measurements"}


def test_an_undeclared_level_goal_is_not_scored_at_all(tmp_path):
    """SILENCE, not an inversion.

    Scoring an undeclared level against the `floor` default does not fix the
    defect, it upgrades it: on the persona corpus a goal 6.1 kg OVER its loss
    target reported `achieved` at 109 per cent. A consumer can see a null; it
    cannot see that a verdict points the wrong way.
    """
    v = _record(tmp_path, [("2030-05-02", 84.1)], target=78)

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["observed"] is None
    assert row["achievement_status"] is None
    assert row["progress_pct"] is None
    assert any("LEVEL" in a for a in v.validate()["advisories"])


def test_a_modelled_value_is_not_an_observation(tmp_path):
    """The contract has said since 12 that a consumer reading a column must
    check `modelled`. A level goal scored against a vendor's estimate reports
    an inference as a measurement."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "weight",
                       "title": "a level goal", "metric": "kg", "target": 78,
                       "policy": "monotonic", "period": "none",
                       "lifecycle_status": "active", "polarity": "ceiling"})
    v.append("weight", {"date": "2030-05-02", "kg": 80.0, "source": "scale"})
    v.append("weight", {"date": "2030-05-09", "kg": 74.0, "source": "app",
                        "modelled": "kg"})

    row, = [r for r in v.goals() if r["slug"] == "weight"]

    assert row["observed"] == 80.0, "the estimate was scored as a measurement"


def test_a_discarded_claim_does_not_become_the_scored_level(tmp_path):
    """`Vitai.goals()` computes over raw claims and the read model's table
    over resolved rows. A level goal reads ONE row and reports it, so on the
    raw path a memory-logged figure would beat the scale it contradicts."""
    root = init(tmp_path / "content")
    (root / "vitai.toml").write_text(
        '[resolution.precedence]\nkg = ["scale", "app"]\n', encoding="utf-8")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "weight",
                       "title": "a level goal", "metric": "kg", "target": 78,
                       "policy": "monotonic", "period": "none",
                       "lifecycle_status": "active", "polarity": "ceiling"})
    v.append("weight", {"date": "2030-05-02", "kg": 80.4, "source": "scale"})
    v.append("weight", {"date": "2030-05-02", "kg": 77.0, "source": "app"})

    from_api, = [r for r in v.goals() if r["slug"] == "weight"]
    from_table, = [r for r in v.derived("goal_progress")
                   if r["slug"] == "weight"]

    assert from_api["observed"] == from_table["observed"] == 80.4


def test_the_advisory_stops_once_the_goal_is_closed_or_declared(tmp_path):
    """A goal's lifecycle is its LATEST line's, and so is its polarity.

    Filtering per line meant a completed goal and a goal cured by restating it
    both kept drawing the advisory forever - and in an append-only record the
    athlete has no remedy for that.
    """
    v = _record(tmp_path, [("2030-05-02", 80.0)], target=78)
    assert any("LEVEL" in a for a in v.validate()["advisories"])

    v.append("goals", {"date": "2030-06-01", "slug": "weight",
                       "title": "a level goal", "metric": "kg", "target": 78,
                       "policy": "monotonic", "period": "none",
                       "lifecycle_status": "active", "polarity": "ceiling"})

    assert not [a for a in v.validate()["advisories"] if "LEVEL" in a]


def test_the_cli_renders_a_level_goal(tmp_path):
    """P9: the fix has to reach the surface the issue is about. `vitai goals`
    branched on `counted is None` and printed "not scored here" about the very
    goal the level shape was added to score."""
    from vitai.cli import _fmt_goal

    v = _record(tmp_path, [("2030-05-02", 81.4)], target=78,
                polarity="ceiling")
    row, = [r for r in v.goals() if r["slug"] == "weight"]

    line = _fmt_goal(row).splitlines()[0]
    assert "not scored here" not in line
    assert "81.4" in line and "OVER by 3.4" in line


def test_a_level_goal_with_no_polarity_is_advised_on(tmp_path):
    """The default is safe for a flow and unsafe for a level.

    More steps is progress whoever wrote the goal; more kilograms is not, and
    the class is not obscure - losing weight is the motivating case of the
    whole record. Advisory rather than a problem, because old lines keep
    validating and the engine does not get to decide which way a goal points.
    """
    v = _record(tmp_path, [("2030-05-02", 80.0)], target=78)

    advisories = " ".join(v.validate()["advisories"])

    assert "LEVEL" in advisories and "weight" in advisories
    assert not v.validate()["problems"]


def test_the_advisory_is_about_the_shape_not_the_words(tmp_path):
    """Not the title heuristic, which needs the word `cap` and would need
    `down to` and `under` and every phrasing after that. A level metric with
    no declared direction is a fact about the row."""
    v = _record(tmp_path, [("2030-05-02", 80.0)], target=78,
                title="a title mentioning nothing in particular")

    assert any("LEVEL" in a for a in v.validate()["advisories"])


def test_a_declared_level_goal_draws_no_advisory(tmp_path):
    v = _record(tmp_path, [("2030-05-02", 80.0)], target=78,
                polarity="ceiling")

    assert not [a for a in v.validate()["advisories"] if "LEVEL" in a]


def test_the_column_reaches_the_read_model(tmp_path):
    root = tmp_path / "content"
    __import__("shutil").copytree(DEMO, root)
    Vitai(root).build()

    con = sqlite3.connect(root / "derived" / "health.db")
    rows = con.execute("SELECT slug, counted, observed FROM goal_progress "
                       "WHERE observed IS NOT NULL").fetchall()
    contract, = con.execute(
        "SELECT value FROM meta WHERE key='contract'").fetchone()
    con.close()

    assert rows, "the demo ships a level goal, so this must not be empty"
    assert all(r[1] is None for r in rows), "a level does not accumulate"
    assert "observed" in PROGRESS_KEYS
    assert contract == CONTRACT_VERSION


# --- the fixture half (#274) ------------------------------------------------

def test_the_demo_exhibits_more_than_one_polarity():
    """#204's corollary: a fixture holding one value of a vocabulary proves
    nothing about the distinction the field exists to draw.

    Every demo goal was a floor, so contract 24's ceiling was invisible and a
    consumer reading the demo would render every goal with `progress_pct` -
    reproducing the defect polarity was added to remove, which is what the
    reference client did.
    """
    rows = Vitai(DEMO).derived("goal_progress")

    assert {"floor", "ceiling"} <= {r["polarity"] for r in rows}


def test_the_demo_exercises_the_over_side_of_a_ceiling():
    """A demo whose every ceiling is respected teaches a consumer as little as
    one with no ceiling at all. The motivating case of contract 24 is the
    breach: 1100 kcal a day against a 1200 cap once reported 641.7%."""
    rows = Vitai(DEMO).derived("goal_progress")
    breached = [r for r in rows if r["breach"] == "over"]

    assert breached, "no shipped goal exercises breach: over"
    assert all(r["room_left"] is not None and r["room_left"] < 0
               for r in breached)


def test_the_demo_has_a_week_with_no_sessions():
    """Contract 28 emits a row for every week in range including the ones
    holding nothing, and the demo trained every week, so the row a consumer
    has to render was undemonstrable."""
    rows = Vitai(DEMO).derived("session_weeks")
    empty = [r for r in rows if r["sessions"] == 0]

    assert empty, "no empty week in the shipped fixture"
    assert all(r["distance_km"] is None for r in empty), (
        "an empty week logs no distance, and zero would assert one")


def test_the_quiet_week_is_a_gap_rather_than_an_edge():
    """A run of zero weeks at either end could be explained away as the record
    starting or stopping. A gap with sessions on both sides is the shape a
    consumer actually has to render."""
    rows = sorted(Vitai(DEMO).derived("session_weeks"), key=lambda r: r["week"])
    weeks = [r["week"] for r in rows]
    empty = {r["week"] for r in rows if r["sessions"] == 0}

    assert empty
    for week in empty:
        assert week != weeks[0] and week != weeks[-1]


def test_the_demo_still_carries_an_undeclared_level_goal():
    """The advisory needs something to point at.

    A record where every line was already correct demonstrates neither the
    hazard nor the advice, and the demo's whole job is to be what a consumer
    reads. The EARLIER weight line keeps its polarity unset on purpose; the
    later one declares it.
    """
    lines = [json.loads(ln) for ln
             in (DEMO / "data" / "goals.jsonl").read_text(
                 encoding="utf-8").splitlines() if ln.strip()]
    weight = [g for g in lines if g.get("slug") == "weight"]

    assert any(g.get("polarity") is None for g in weight)
    assert any(g.get("polarity") == "ceiling" for g in weight)
