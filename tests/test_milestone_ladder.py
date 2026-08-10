"""Every milestone a goal has, not only the ones it crossed (#330).

MEASURED BEFORE BUILDING, and the issue's premise did not hold the way it was
written. A `milestones` table already exists - `["date", "goal", "period",
"fraction", "value", "target", "label"]` - in the read model and on
`Vitai.milestones()`, holding 33 rows for `marcus`. It answers three of the
four things the issue asks for: a label, the value, and when it was passed.
"Whether it is passed" is answered by existence, since a row is minted only on
crossing, and ordering falls out of `fraction`.

What the issue was reading is a different field. `goal_progress.milestones` is
a COUNT, and nothing pointed from it to the table.

TWO THINGS WERE GENUINELY WRONG, and they are what this closes.

The count is scoped to the CURRENT BUCKET and its name never said so. On
`marcus`, `weekly-volume` has 33 crossed milestones and it read 0, because
every one was crossed in an earlier week. A consumer showing "0 milestones"
beside a goal with 33 is not thin, it is wrong.

And the ladder was private. `MILESTONE_FRACTIONS` lives in `contributions.py`
and reached no surface, so a client could not say how many rungs a goal has,
which are still ahead, or which is next - and would have had to slice the
target into quarters itself, which is the inventing-engine-semantics failure
the issue rightly refuses.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai
from vitai.contributions import MILESTONE_FRACTIONS, mints_milestones
from vitai.schema import KEYS

PERSONAS = Path(__file__).resolve().parent / "fixtures" / "personas"


def ladder(name: str, **kw) -> list[dict]:
    return Vitai(PERSONAS / name).milestone_ladder(**kw)


# --- the rungs -----------------------------------------------------------------

def test_a_goal_reports_every_rung_not_only_the_crossed_ones():
    got = ladder("marcus")
    assert [r["fraction"] for r in got] == list(MILESTONE_FRACTIONS)
    assert all(r["goal"] == "weekly-volume" for r in got)
    assert [r["value"] for r in got] == [22.5, 45.0, 67.5, 90.0]


def test_it_says_which_one_is_next():
    """The ask the crossed-rows table cannot meet: a client showing progress
    needs the rung ahead, not only the ones behind."""
    got = ladder("marcus")
    nxt = [r for r in got if r["next"]]
    assert len(nxt) == 1, got
    assert nxt[0]["fraction"] == 0.25
    assert not nxt[0]["passed"]


def test_a_finished_bucket_has_no_next():
    """`nora` crossed all four this week. "Next" is not a rung when there is
    none left, and reporting the last one again would say the goal is still
    ahead of her."""
    got = ladder("nora")
    assert got and all(r["passed"] for r in got), got
    assert not any(r["next"] for r in got)
    assert [r["passed_on"] for r in got] == ["2030-06-25", "2030-06-26",
                                             "2030-06-29", "2030-06-29"]


def test_a_passed_rung_carries_when_and_a_label():
    got = [r for r in ladder("nora") if r["fraction"] == 0.5][0]
    assert got["passed"] is True
    assert got["passed_on"] == "2030-06-26"
    assert got["label"], got


def test_an_unpassed_rung_says_nothing_it_does_not_know():
    for r in ladder("marcus"):
        assert r["passed"] is False
        assert r["passed_on"] is None
        assert r["label"] is None
        assert r["passed_target"] is None


# --- the bucket, which is the whole design decision ----------------------------

def test_the_ladder_is_this_bucket_rather_than_all_of_history():
    """MEASURED, and it changed the design. A weekly floor goal crosses 25%
    most weeks - `marcus` has 33 crossings against four fractions - so a
    lifetime ladder would collapse 33 real events into four rungs and call the
    goal three quarters done forever.

    Milestones key on (slug, bucket, fraction) because the achievement is "a
    quarter of the way through THIS week", and the ladder has to mean the same
    thing the minting does."""
    v = Vitai(PERSONAS / "marcus")
    crossed = v.milestones()
    assert len(crossed) == 33, len(crossed)
    assert len({m["period"] for m in crossed}) > 4, "many buckets"

    got = v.milestone_ladder()
    assert len(got) == 4, "one bucket's worth"
    assert len({r["period"] for r in got}) == 1
    assert not any(r["passed"] for r in got), (
        "this bucket is fresh, whatever history holds")


def test_every_rung_names_its_bucket():
    """So a consumer never has to infer which period it is looking at."""
    for name in ("marcus", "nora", "yasmin"):
        for r in ladder(name):
            assert r["period"], r


def test_the_target_in_force_and_the_target_it_was_crossed_against_both_show():
    """They come apart, and reporting one would render a date against a number
    that never applied on it. This athlete's target moved 95 to 90, so a rung
    sitting at 22.5 today was crossed at 23.75."""
    seen = {m["target"] for m in Vitai(PERSONAS / "marcus").milestones()}
    assert seen == {90, 95}, seen
    for r in ladder("nora"):
        assert r["target"] == 80
        assert r["passed_target"] == 80


# --- which goals have a ladder at all ------------------------------------------

def test_a_goal_the_engine_will_not_mint_for_gets_no_ladder():
    """An empty list says "this goal has no milestone surface". A ladder of
    quarters would say something the engine has deliberately declined to say -
    an approach needs a baseline the goal row does not carry, a cap has no
    achievement to fraction, a completed goal is measured rather than scored
    again, and a daily bucket would mint 1460 rows a year."""
    assert ladder("ines") == []          # completed, and a ceiling
    assert ladder("rachel") == []        # target is null
    assert ladder("derek") == []         # no goals at all


def test_the_ladder_and_the_minting_agree_about_which_goals_have_one():
    """ONE PREDICATE, two readers. Two copies would drift, and the visible
    symptom would be a surface promising four rungs to a goal that can never
    reach one."""
    for path in sorted(PERSONAS.iterdir()):
        if not (path / "vitai.toml").exists():
            continue
        v = Vitai(path)
        with_ladder = {r["goal"] for r in v.milestone_ladder()}
        eligible = {str(g["slug"]) for g in v.goals() if mints_milestones(g)}
        assert with_ladder == eligible, path.name
        # And nothing mints for a goal the predicate refuses.
        minted = {m["goal"] for m in v.milestones()}
        assert not (minted - eligible - _completed_since(v)), path.name


def _completed_since(v: Vitai) -> set[str]:
    """A goal can mint and LATER complete, so its historical rows outlive its
    eligibility. That is correct - the crossing happened - and it is why the
    check above subtracts them rather than asserting equality."""
    return {str(g["slug"]) for g in v.goals()
            if str(g.get("lifecycle_status")) == "completed"}


def test_one_goal_can_be_asked_for():
    got = ladder("yasmin")
    slug = got[0]["goal"]
    only = ladder("yasmin", slug=slug)
    assert only and all(r["goal"] == slug for r in only)
    assert len(only) < len(got), "yasmin has more than one goal with a ladder"


# --- the count that was wrong ---------------------------------------------------

def test_the_lifetime_count_is_published_beside_the_bucket_one():
    """`goal_progress.milestones` reads 0 for a goal with 33 crossings,
    because it counts THIS bucket. Kept, because a consumer reading it today
    is reading a per-bucket figure and widening it would change every one of
    those readings - so the lifetime number arrives beside it under a name
    that says what it is."""
    got = {r["slug"]: r for r in Vitai(PERSONAS / "marcus").goals()}
    assert got["weekly-volume"]["milestones"] == 0
    assert got["weekly-volume"]["milestones_total"] == 33


def test_the_totals_agree_with_the_table():
    for path in sorted(PERSONAS.iterdir()):
        if not (path / "vitai.toml").exists():
            continue
        v = Vitai(path)
        crossed = v.milestones()
        for row in v.goals():
            want = sum(1 for m in crossed if m["goal"] == row["slug"])
            assert row["milestones_total"] == want, (path.name, row["slug"])


def test_the_column_is_appended_rather_than_inserted():
    from vitai.db import PROGRESS_KEYS

    assert PROGRESS_KEYS[-1] == "milestones_total"
    assert PROGRESS_KEYS.index("milestones") < PROGRESS_KEYS.index("observed")


def test_it_reaches_the_read_model(tmp_path):
    # A COPY. Building in the persona directory writes `derived/` into shared
    # fixture state at test time, which every other test in the suite avoids.
    import shutil

    root = tmp_path / "marcus"
    shutil.copytree(PERSONAS / "marcus", root)
    con = sqlite3.connect(Vitai(root).build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(goal_progress)")]
        assert "milestones_total" in cols
        got = con.execute("SELECT milestones, milestones_total FROM goal_progress "
                          "WHERE slug = 'weekly-volume'").fetchone()
        assert got == (0, 33), got
    finally:
        con.close()


def test_the_fractions_are_published_rather_than_guessed():
    """The reason this is an accessor and not a note in the README: a client
    slicing a target into quarters is copying a rule this engine owns, and the
    copy is wrong the day the tuple changes."""
    target = [r for r in ladder("nora")][0]["target"]
    assert [r["value"] for r in ladder("nora")] == [
        round(target * f, 3) for f in MILESTONE_FRACTIONS]


# --- P9: the same capability on every surface ----------------------------------

def test_it_reaches_the_cli():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["milestones", "--root", str(PERSONAS / "nora")])
    out = buf.getvalue()
    assert "weekly-training-volume" in out
    assert "[x] 25% of 80 = 20" in out, out
    assert "passed 2030-06-25" in out


def test_the_cli_marks_the_next_rung():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["milestones", "--root", str(PERSONAS / "marcus")])
    out = buf.getvalue()
    assert "[>] 25%" in out, out
    assert "[ ] 50%" in out, out


def test_it_reaches_the_agent_surface():
    from vitai.mcp import call, tool_list

    assert any(t["name"] == "milestone_ladder" for t in tool_list())
    got = call(PERSONAS / "nora", "milestone_ladder", {})
    assert got and all(r["passed"] for r in got)
    only = call(PERSONAS / "nora", "milestone_ladder",
                {"slug": "weekly-training-volume"})
    assert only == got


def test_the_goals_line_no_longer_hides_a_goal_with_crossings():
    """`marcus` has 33 crossed milestones and this line printed NOTHING about
    them, because the bucket count is 0 and 0 is falsy. The count that decides
    whether to speak is now the total."""
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["goals", "--root", str(PERSONAS / "marcus")])
    out = buf.getvalue()
    assert "0 milestone(s) this period, 33 in all" in out, out


# --- passed is about the VALUE, not the fraction -------------------------------

def mid_bucket_change(tmp_path: Path, first: float, second: float) -> Vitai:
    """A goal whose target moves partway through the bucket it is scored in.

    Crossings are minted event by event against the target in force AT THAT
    EVENT, so a mid-bucket change leaves a bucket whose crossings do not line
    up with the rungs the current target defines. That is the shape that tells
    "was this fraction ever crossed" apart from "has progress reached this
    value", and nothing in the shipped corpus does it - measured: zero rungs
    across ten personas disagree under the two rules.
    """
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")

    def goal(date_: str, target: float) -> dict:
        return {**{k: None for k in KEYS["goals"]}, "date": date_, "slug": "vol",
                "title": "volume", "metric": "distance_km", "dataset": "sessions",
                "session_type": "run", "target": target, "policy": "open",
                "period": "weekly", "on_period_end": "reset", "status": "active",
                "set_by": "athlete", "recorded_at": f"{date_}T08:00:00Z"}

    (root / "data" / "goals.jsonl").write_text(
        json.dumps(goal("2030-06-01", first)) + "\n"
        + json.dumps(goal("2030-06-27", second)) + "\n", encoding="utf-8")
    (root / "data" / "sessions.jsonl").write_text("".join(
        json.dumps({**{k: None for k in KEYS["sessions"]},
                    "date": f"2030-06-{d:02d}", "type": "run",
                    "distance_km": 7.0, "duration_s": 2400,
                    "source": "watch"}) + "\n" for d in (24, 25, 26, 27, 28)),
        encoding="utf-8")
    return Vitai(root, on="2030-06-28")


def test_a_rung_is_passed_when_progress_reached_it_not_when_a_fraction_minted(tmp_path):
    """THE DEFECT REVIEW FOUND, and it is the one this method's bucket scoping
    exists to prevent, arriving through the other door.

    Target 100 lowered to 40 partway through the week, 35 km logged. ONE
    crossing minted - 75% of 40 - because the earlier events were measured
    against marks of 25/50/75/100 and the later ones found `before` already
    past the new lower marks. So "was this fraction crossed" says the athlete
    has passed one rung and their NEXT is 10 km, which they went past on day
    two. "Has progress reached this value" says three of four, next is 40."""
    v = mid_bucket_change(tmp_path, 100, 40)
    assert [m["fraction"] for m in v.milestones()] == [0.75], v.milestones()

    got = v.milestone_ladder()
    assert [r["value"] for r in got] == [10.0, 20.0, 30.0, 40.0]
    assert [r["passed"] for r in got] == [True, True, True, False]
    assert [r["next"] for r in got] == [False, False, False, True]
    assert all(r["reached"] == 35.0 for r in got)


def test_a_rung_can_be_passed_with_no_date(tmp_path):
    """The honest consequence of the rule above: where the target moved past a
    rung, there is no crossing to date it. Saying "passed" without a date is
    true; a date against a number nobody reached would not be."""
    got = mid_bucket_change(tmp_path, 100, 40).milestone_ladder()
    dateless = [r for r in got if r["passed"] and r["passed_on"] is None]
    assert len(dateless) == 2, got
    assert all(r["label"] is None and r["passed_target"] is None
               for r in dateless)


def test_the_rule_holds_across_the_whole_corpus():
    """The invariant, over real records: `passed` is exactly "reached the
    value". Stated as a property so a future change to either side has to keep
    them in step."""
    checked = 0
    for path in sorted(PERSONAS.iterdir()):
        if not (path / "vitai.toml").exists():
            continue
        for r in Vitai(path).milestone_ladder():
            checked += 1
            assert r["passed"] == (r["reached"] >= r["value"]), (path.name, r)
    assert checked >= 40, checked


# --- the surfaces the first cut left unwitnessed --------------------------------

def test_the_cli_emits_rungs_as_jsonl():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["milestones", "--root", str(PERSONAS / "nora"), "--json"])
    rows = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln]
    assert rows == Vitai(PERSONAS / "nora").milestone_ladder()


def test_the_cli_says_so_when_no_goal_has_a_ladder():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["milestones", "--root", str(PERSONAS / "rachel")])
    out = buf.getvalue()
    assert "no goal has a milestone ladder" in out, out
    assert "caps, approaches" in out, "and it says which shapes those are"
