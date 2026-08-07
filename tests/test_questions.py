"""The floor of the asking channel: what the record does not know (#224).

Everything else here runs one way - a client asks, the engine answers or
refuses. This is the inversion, and it is the FLOOR of it: a deterministic
derivation over the record, computable with no model configured, no network,
no permission layer and no budget.

THE LOAD-BEARING TEST IS `test_a_record_with_nothing_planned_asks_nothing`.
The engine's urge to ask peaks exactly where asking is least welcome: a long
disengaged stretch produces the most unresolved plans and the most unanswered
anything, and it is precisely the period somebody has deliberately stepped
away from. The property that has to hold is that such a record generates
NOTHING - and it has to hold with the budget layer unbuilt and `nudge_ok`
off, or the safety of the channel depends on its accelerator.

Derive few. Do not generate many and suppress.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from vitai import mcp
from vitai.api import Vitai, init
from vitai.questions import KINDS, SETTLED_BY, ahead, open_questions

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _plan(v: Vitai, slug: str, for_date: str, activity: str = "run", **kw):
    row = {"date": "2030-05-01", "slug": slug, "for_date": for_date,
           "activity": activity, "tier": "committed", "outcome": "unresolved"}
    row.update(kw)
    v.append("plans", row)


def _fingerprint(root: Path) -> str:
    """EVERY FILE, not only the data ones. The first version hashed
    `data/*.jsonl`, so a write to `vitai.toml` or a cache file would have
    passed a test named for the record being byte-identical."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "derived" in path.parts:
            continue
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


# --- derive few -----------------------------------------------------------

def test_a_record_with_nothing_planned_asks_nothing(tmp_path):
    """THE ONE THAT MATTERS. A long quiet stretch: months of history, no
    sessions for weeks, nothing planned. The engine has the most to be curious
    about here and must produce nothing at all.

    Asserted with the budget layer UNBUILT and `nudge_ok` at its default of
    False, because a safety property that depends on the accelerator existing
    is not a safety property.
    """
    v = Vitai(init(tmp_path / "content"))
    for n in range(60):
        day = (date(2030, 3, 1) + timedelta(days=n)).isoformat()
        v.append("weight", {"date": day, "kg": 80.0, "source": "scale"})

    assert v.config.nudge_ok is False
    assert v.questions(date(2030, 5, 1)) == []


def test_a_disengaged_stretch_full_of_unanswered_plans_asks_nothing(tmp_path):
    """The sharper version, and the one an enumerator would fail. Ten plans,
    every one unresolved, every one in the past: the maximum a "what does the
    record not know" query could return, and the period asking is least
    welcome. Nothing here bears on anything that has not happened yet."""
    v = Vitai(init(tmp_path / "content"))
    for n in range(10):
        _plan(v, f"lapsed-{n}", (date(2030, 4, 1) + timedelta(days=n)).isoformat(),
              requires="dry-forecast")

    assert v.plans(date(2030, 6, 1))
    assert v.questions(date(2030, 6, 1)) == []


def test_an_unresolved_plan_in_the_past_is_not_a_question(tmp_path):
    """It is a fact about the record and `plans` already reports it as
    overdue. A question is about what is coming; asking what happened three
    weeks ago changes nothing anybody is about to do, and G82 is that a gap is
    data rather than missing data."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "last-tuesday", "2030-05-02", requires="dry-forecast")

    overdue, = v.plans(date(2030, 6, 1))

    assert overdue["overdue"] is True
    assert v.questions(date(2030, 6, 1)) == []


def test_a_plan_the_athlete_has_already_answered_is_not_asked_again(tmp_path):
    """Even where its day is still ahead. They have said what happened, and
    asking again is asking twice."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast",
          outcome="did_not_activate")

    assert v.questions(date(2030, 6, 1)) == []


# --- what a question is ---------------------------------------------------

def test_a_condition_nothing_settles_is_a_question(tmp_path):
    """The plan says what it needs and the record holds no answer. "I would
    run if it were dry" with nothing saying whether it is."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")

    question, = v.questions(date(2030, 6, 1))

    assert question["kind"] == "precondition"
    assert question["subject"] == "dry-forecast"
    assert question["about"] == "saturday"
    assert question["for_date"] == "2030-06-10"


def test_it_says_what_would_settle_it(tmp_path):
    """The field that lets a connector or a lookup answer instead of a person,
    which is why a question says what would settle it rather than only what it
    is about."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")

    question, = v.questions(date(2030, 6, 1))

    assert question["settled_by"] == "athlete"
    assert question["settled_by"] in SETTLED_BY
    # NO `lookup`, and its absence is a decision rather than a gap. Whether
    # "dry-forecast" is settleable by a weather service or only by the athlete
    # is a claim about the world this record cannot check, and the outward
    # lookup is a later part of this channel with a permission layer under it.
    assert "lookup" not in SETTLED_BY


def test_a_gate_waiting_on_a_check_is_a_question(tmp_path):
    """The second kind, and the one whose answer most plainly changes what
    somebody is about to do. Three gate states exist because "your leg said no
    today" and "you have not asked it yet" are different facts."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "calf", "kind": "injury",
        "title": "calf", "body_site": "calf", "status": "monitoring",
        "severity": "mild", "restricts": "run",
        "precondition": "hop-test", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10")

    kinds = {q["kind"] for q in v.questions(date(2030, 6, 1))}

    assert "clearance" in kinds


def test_a_gate_that_is_simply_blocked_is_not_a_question(tmp_path):
    """Nothing the athlete can say changes it, so asking would be inviting
    somebody to talk their way past a clinical hold."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "calf", "kind": "injury",
        "title": "calf", "body_site": "calf", "status": "active",
        "severity": "moderate", "restricts": "run", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10")

    assert [q for q in v.questions(date(2030, 6, 1))
            if q["kind"] == "clearance"] == []


def test_a_gate_over_an_activity_nobody_planned_is_not_a_question(tmp_path):
    """A question hangs off a plan. A gate on swimming, with nothing planned
    but a run, is not something an answer would change."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "shoulder", "kind": "injury",
        "title": "shoulder", "body_site": "shoulder", "status": "monitoring",
        "severity": "mild", "restricts": "swim",
        "precondition": "hop-test", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", activity="run")

    assert v.questions(date(2030, 6, 1)) == []


def test_a_gate_spelled_as_a_class_still_covers_a_planned_run(tmp_path):
    """THE FALSE NEGATIVE ON THE SAFETY-RELEVANT KIND, and it was silent.
    `restricts` is validated against activity CLASSES, and `is_gated` expands
    the activity through the registry before comparing - so a gate spelled
    `impact` blocks a planned `run`. Comparing the strings instead missed
    every gate not spelled as the exact activity: `may("run")` said blocked,
    the gate said `check_not_done`, and the derivation whose whole job is to
    surface exactly that check returned nothing.

    Matched by the engine's own rule now rather than by one restated here,
    which is the argument `is_gated`'s own docstring makes.
    """
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "achilles", "kind": "injury",
        "title": "achilles", "body_site": "achilles", "status": "monitoring",
        "severity": "mild", "restricts": "impact",
        "precondition": "hop-test", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", activity="run")

    assert v.may("run", date(2030, 6, 10))["verdict"] != "allowed"
    question, = v.questions(date(2030, 6, 1))
    assert question["kind"] == "clearance"
    assert question["subject"] == "achilles"


def test_a_gate_restricting_everything_covers_any_plan(tmp_path):
    """`all` is a legal value and means what it says. Restating the match
    missed it too."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "post-op", "kind": "restriction",
        "title": "post-op", "body_site": "knee", "status": "monitoring",
        "severity": "mild", "restricts": "all",
        "precondition": "hop-test", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", activity="swim")

    assert [q["kind"] for q in v.questions(date(2030, 6, 1))] == ["clearance"]


def test_the_clearance_is_judged_on_the_day_the_thing_is_planned(tmp_path):
    """Gates were read on the VIEWPOINT day and attached to plans for later
    ones, which was wrong in both directions. A check passing today cleared
    the gate and silenced the question about next Saturday - so the question
    vanished on the day the athlete engaged with the check and came back the
    next morning."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "achilles", "kind": "injury",
        "title": "achilles", "body_site": "achilles", "status": "monitoring",
        "severity": "mild", "restricts": "impact",
        "precondition": "hop-test", "source": "athlete"})
    v.append("checks", {"date": "2030-06-01", "slug": "hop-test",
                        "result": "pass", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", activity="run")

    # Cleared today, and today is not the day the run happens.
    assert [g["status"] for g in v.gates(date(2030, 6, 1))] == ["cleared"]

    assert [q["kind"] for q in v.questions(date(2030, 6, 1))] == ["clearance"]


def test_an_episode_that_ends_before_the_plan_asks_nothing(tmp_path):
    """The other direction of the same defect: the record already holds the
    answer, and asking would be asking about a gate that will not exist."""
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "achilles", "kind": "injury",
        "title": "achilles", "body_site": "achilles", "status": "resolved",
        "severity": "mild", "restricts": "impact", "precondition": "hop-test",
        "resolved_date": "2030-06-03", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", activity="run")

    assert v.questions(date(2030, 6, 1)) == []


def test_a_plan_for_today_is_still_ahead(tmp_path):
    """The most imminent case, and the day a clearance check is actually
    actionable. Untested, `<` and `<=` were indistinguishable and the whole
    suite passed with today's plan silenced."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "today", "2030-06-01", requires="dry-forecast")

    assert len(v.questions(date(2030, 6, 1))) == 1


def test_a_plan_resolved_by_a_later_row_is_not_asked_about(tmp_path):
    """THE LIFECYCLE THE RECORD ACTUALLY USES. A plan is resolved by a SECOND
    ROW carrying the same slug - not by editing the first, because an honestly
    unresolved plan was not WRONG and a correction says a line was. Filtering
    row by row kept the original, still unresolved, and went on asking a
    question the athlete had already answered.

    The first version of this test wrote the outcome on a single row, which is
    a shape the demo uses and the live lifecycle does not - so it passed while
    the case it was named for was broken.
    """
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast",
          date="2030-06-11", outcome="completed", session_ref="2030-06-10")

    assert len(v.plans(date(2030, 6, 1))) >= 1
    assert v.questions(date(2030, 6, 1)) == []


def test_a_re_dated_plan_is_one_question_and_not_two(tmp_path):
    """The same root, and it broke the id's whole purpose. Two rows of one
    plan, both unresolved, produced two questions sharing one id - so a
    decline hung on that id would ambiguously cover both."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    _plan(v, "saturday", "2030-06-17", requires="dry-forecast",
          date="2030-06-05")

    questions = v.questions(date(2030, 6, 1))

    assert len(questions) == 1
    assert questions[0]["for_date"] == "2030-06-17"


# --- what it is not -------------------------------------------------------

def test_nothing_it_returns_is_a_sentence(tmp_path):
    """A question the engine phrased would be the engine deciding how it
    sounds, and "no question may imply a duty" lives entirely in phrasing. So
    every field is a slug, a date or a closed vocabulary, and the wording
    belongs to whatever asks - which is also the side that can gate what
    leaves."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")

    question, = v.questions(date(2030, 6, 1))

    assert set(question) == {"id", "kind", "about", "for_date", "subject",
                             "settled_by", "bears_on"}
    for key in ("id", "kind", "for_date", "settled_by"):
        assert len(str(question[key]).split()) == 1, (key, question[key])
    assert not {"message", "detail", "text", "prompt", "severity"} & set(question)


def test_the_subject_is_the_records_words_and_not_a_slug(tmp_path):
    """A NARROWER CLAIM THAN THE FIRST WORDING, which said no field here is
    prose and was false. `plans.requires` is not slug-checked anywhere -
    nothing stops an athlete writing a sentence there - so `subject` carries
    it verbatim, and a consumer has to treat it as content rather than as an
    identifier. Pinned so that #205's boundary work inherits a true statement
    about it rather than a comfortable one.
    """
    v = Vitai(init(tmp_path / "content"))
    sentence = "whether the physio is happy about hills again"
    _plan(v, "saturday", "2030-06-10", requires=sentence)

    assert v.validate()["problems"] == []
    question, = v.questions(date(2030, 6, 1))
    assert question["subject"] == sentence


def test_the_vocabularies_are_closed():
    """An open vocabulary is where a word like `urgent` arrives."""
    for question in Vitai(DEMO).questions():
        assert question["kind"] in KINDS
        assert question["settled_by"] in SETTLED_BY


def test_asking_leaves_the_record_byte_identical(tmp_path):
    """RESOLUTION STAYS SIDE-EFFECT FREE, and so does this. A read that queued
    a question would fire once per consumer per build - and this is read by
    every client, every time. Checked over every byte of every data file
    rather than by reading the code."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    before = _fingerprint(v.root)

    v.questions(date(2030, 6, 1))
    v.questions(date(2030, 6, 2))
    v.build()

    assert _fingerprint(v.root) == before


def test_it_is_not_a_tripwire_and_not_in_the_read_model(tmp_path):
    """DERIVED, NEVER PERSISTED. An open question is computation and a
    rebuild recomputes it; storing one would duplicate the derived tier into
    the ground-truth tier and grow without bound on every build, which is the
    argument `assert_delivery` already wrote down. What persists is an ACT -
    and the act here is a decline, which belongs with whatever asks."""
    import sqlite3

    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    v.build()

    con = sqlite3.connect(v.root / "derived" / "health.db")
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    assert v.questions(date(2030, 6, 1))
    assert not [t for t in tables if "question" in t]
    assert not [t for t in v.resolution()["tripwires"] if "question" in t["kind"]]


def test_the_nudge_flag_changes_nothing_here(tmp_path):
    """`nudge_ok` is the consent to be INTERRUPTED, and this interrupts
    nobody. Turning it on must change nothing at the floor, or the derivation
    has quietly become the thing that speaks.

    Asserted on the behaviour rather than on the source text, which was the
    first version and was wrong twice over: it read a docstring that legitimately
    NAMES the flag while explaining that it is not read, and it would have
    passed for a module that reached the setting under any other spelling.
    """
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    quiet = v.questions(date(2030, 6, 1))

    toml = v.root / "vitai.toml"
    toml.write_text(toml.read_text() + "\n[preferences]\nnudge_ok = true\n",
                    encoding="utf-8")
    loud = Vitai(v.root)

    assert loud.config.nudge_ok is True
    assert loud.questions(date(2030, 6, 1)) == quiet


# --- ordering and identity ------------------------------------------------

def test_a_dormant_record_read_at_its_own_horizon_still_answers(tmp_path):
    """A DECISION RATHER THAN A DEFECT, recorded because it looks like one.

    The viewpoint falls back to the record's own horizon, so a record whose
    last act was planning something keeps reporting that question however long
    ago it stopped. That is the engine's viewpoint doctrine working: the
    question really is open, and nothing ever answered it.

    The dormancy property this channel needs is about a record with NOTHING
    PLANNED, which is the disengaged shape - somebody who stopped logging
    rather than somebody who stopped after making a plan. Asked with a real
    viewpoint, the stale plan is behind and nothing is returned.
    """
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "comeback", "2030-05-03", requires="dry-forecast")

    assert v.questions()                       # at the record's own horizon
    assert v.questions(date(2032, 1, 1)) == []  # asked from a real today


def test_the_soonest_comes_first(tmp_path):
    """The one ordering the engine can derive without deciding what matters to
    a person. How often somebody may be interrupted is a fact about their
    attention rather than about the record, and it is not decided here."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "later", "2030-06-20", requires="dry-forecast")
    _plan(v, "sooner", "2030-06-10", requires="dry-forecast")

    assert [q["about"] for q in v.questions(date(2030, 6, 1))] == [
        "sooner", "later"]


def test_one_plan_can_hold_more_than_one_question(tmp_path):
    """A run that needs dry weather AND a clearance is two questions, not one
    - they are settled by different things and either can be answered without
    the other.

    This is also the only shape in which the final ordering does any work: two
    questions on ONE day, where the order they are generated in and the order
    they are named in differ. Without it a reader gets whichever the loop
    happened to emit first, which is a different answer on a plan carrying
    both kinds.
    """
    v = Vitai(init(tmp_path / "content"))
    v.append("medical", {
        "date": "2030-05-01", "slug": "calf", "kind": "injury",
        "title": "calf", "body_site": "calf", "status": "monitoring",
        "severity": "mild", "restricts": "run",
        "precondition": "hop-test", "source": "athlete"})
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")

    questions = v.questions(date(2030, 6, 1))

    assert [q["kind"] for q in questions] == ["clearance", "precondition"]
    assert len({q["id"] for q in questions}) == 2
    assert [q["id"] for q in questions] == sorted(q["id"] for q in questions)


def test_the_same_question_has_the_same_identity(tmp_path):
    """So that whatever asks can tell it has asked before - which is what a
    decline will need something stable to hang on."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")

    first = v.questions(date(2030, 6, 1))
    second = Vitai(v.root).questions(date(2030, 6, 2))

    assert [q["id"] for q in first] == [q["id"] for q in second]
    assert first[0]["id"] == "plans:saturday:requires"


def test_two_plans_needing_the_same_thing_are_two_questions(tmp_path):
    """They are answered separately: it may be dry on Saturday and not on
    Sunday, and collapsing them would answer one by asking about the other."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "saturday", "2030-06-10", requires="dry-forecast")
    _plan(v, "sunday", "2030-06-11", requires="dry-forecast")

    assert len({q["id"] for q in v.questions(date(2030, 6, 1))}) == 2


def test_ahead_is_the_filter_and_nothing_else_is(tmp_path):
    """Stated directly against the helper, because the safety property rests
    entirely on it: everything a question can be derived from comes out of
    here, so a record whose `ahead` is empty cannot produce one."""
    v = Vitai(init(tmp_path / "content"))
    _plan(v, "past", "2030-05-02", requires="dry-forecast")

    plans = v.plans(date(2030, 6, 1))

    assert plans
    assert ahead(plans, date(2030, 6, 1)) == []
    assert open_questions(plans, v.gates(date(2030, 6, 1)), date(2030, 6, 1)) == []


# --- the doors ------------------------------------------------------------

def test_the_three_surfaces_agree():
    """P9."""
    from_api = Vitai(DEMO).questions("2030-06-30")
    from_mcp = mcp.call(DEMO, "questions", {"on": "2030-06-30"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "questions", "--on", "2030-06-30",
         "--root", str(DEMO), "--json"], capture_output=True, text=True,
        check=True)
    from_cli = [json.loads(ln) for ln in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli
    assert from_api


def test_the_shipped_record_holds_one_of_each_kind():
    """#204's corollary, and the second one arrived by fixing the matcher
    rather than by being written. The demo has an achilles episode restricting
    `impact` and waiting on a hop-test, and a planned `run` - which the
    engine's own `may()` calls blocked and which string-matching `restricts`
    against the activity could not see at all."""
    questions = Vitai(DEMO).questions("2030-06-30")

    assert [q["kind"] for q in questions] == ["clearance", "precondition"]
    assert {q["subject"] for q in questions} == {"achilles", "dry-forecast"}


def test_the_cli_says_so_when_there_is_nothing(tmp_path):
    """The ordinary answer, and one that prints nothing is indistinguishable
    from a command that failed quietly."""
    root = init(tmp_path / "content")
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "questions", "--root", str(root)],
        capture_output=True, text=True, check=True)

    assert "nothing open" in out.stdout
