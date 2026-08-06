"""May I do this today, and the third answer (#275).

A synthetic athlete coming back from an achilles flare asked, in this order:
"am I allowed to run", "is walking gated", "can I bike instead", "is walking
ok tho". All four got the same paragraph, because `restricts: impact` was the
only thing the gate said.

The issue proposed resolving `impact` into activities against the exercise
registry. That work was not needed: `semantics/session_types.toml` already
declares the classes each session type falls under - a run is `impact`, a walk
is not - and `is_gated` has read it correctly all along. What was missing was
a SURFACE to ask through, which is the fourth instance of the same defect
(#257, #258, #267), and a THIRD ANSWER.

The third answer is the load-bearing part. `gated()` returns a bool, so an
activity nobody has classified comes back False: not gated, which reads as
permitted. That is how a gated athlete gets a green light for something nobody
assessed, and it is the failure #229 already named - reading unannotated as
free is what strands someone at a park with a programme written for a rack.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vitai import mcp
from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
ON = "2030-06-28"


def _gated(tmp_path: Path, restricts: str = "impact") -> Vitai:
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "achilles",
                         "kind": "symptom", "title": "soreness",
                         "body_site": "achilles", "body_side": "right",
                         "severity": "mild", "status": "monitoring",
                         "restricts": restricts, "source": "athlete"})
    return v


def test_the_four_questions_no_longer_get_one_answer(tmp_path):
    """The whole issue, as the athlete asked it."""
    v = _gated(tmp_path)

    verdicts = {a: v.may(a, "2030-05-02")["verdict"]
                for a in ("run", "walk", "cycle", "swim")}

    assert verdicts["run"] == "blocked"
    assert verdicts["walk"] == "allowed"
    assert verdicts["cycle"] == "allowed"
    assert len(set(verdicts.values())) > 1, (
        "if every activity answers the same the command adds nothing")


def test_an_activity_nobody_has_classified_is_not_allowed(tmp_path):
    """THE FAILURE THIS EXISTS TO STOP.

    `gated()` says False for it, which reads as permitted. Nobody has said
    what aqua-jogging loads, so this record cannot say whether the gate
    covers it - and a consumer must refuse rather than assume.
    """
    v = _gated(tmp_path)

    assert v.gated("aqua-jogging", "2030-05-02") is False   # the old answer
    assert v.may("aqua-jogging", "2030-05-02")["verdict"] == "unknown"


def test_the_unknown_answer_says_what_would_fix_it(tmp_path):
    """A refusal a consumer cannot act on is a refusal it will work around.

    And the remedy has to be one the athlete can perform: an earlier version
    said "add it to semantics/session_types.toml", which ships inside the
    installed package and is not a file a content repo can edit.
    """
    reason = _gated(tmp_path).may("aqua-jogging", "2030-05-02")["reason"]

    assert "nobody has said" in reason
    assert "toml" not in reason


def test_a_boundary_is_not_a_gap(tmp_path):
    """#248's rule, inherited. An activity the registry KNOWS but which no
    gate covers is allowed, and it must not be confused with one nobody has
    classified - those want opposite responses."""
    v = _gated(tmp_path)

    known = v.may("swim", "2030-05-02")
    unknown = v.may("nonsense", "2030-05-02")

    assert known["verdict"] == "allowed" and known["classes"]
    assert unknown["verdict"] == "unknown" and not unknown["classes"]


def test_a_blocked_answer_relays_the_gate_rather_than_paraphrasing_it(tmp_path):
    """A consumer renders gate text verbatim and has no licence to reword it,
    so the verdict carries the gate's own sentence and its slug."""
    v = _gated(tmp_path)

    out = v.may("run", "2030-05-02")

    assert out["gates"] == ["achilles"]
    assert "soreness" in out["reason"]
    assert out["matched"] == ["impact"]


def test_a_cleared_gate_does_not_block(tmp_path):
    """A gate whose precondition passed is reported and does not block, which
    is `is_gated`'s rule - inherited rather than restated."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "achilles",
                         "kind": "symptom", "title": "soreness",
                         "body_site": "achilles", "body_side": "right",
                         "severity": "mild", "status": "monitoring",
                         "restricts": "impact", "precondition": "hop-test",
                         "source": "athlete"})
    v.append("checks", {"date": "2030-05-02", "slug": "hop-test",
                        "result": "pass", "source": "athlete"})

    assert v.may("run", "2030-05-02")["verdict"] == "allowed"


def test_a_gate_on_everything_blocks_an_activity_it_never_names(tmp_path):
    """`restricts: all` is the one that must not need a class match."""
    v = _gated(tmp_path, restricts="all")

    assert v.may("walk", "2030-05-02")["verdict"] == "blocked"


def test_the_three_surfaces_agree(tmp_path):
    """P9. A client, a script and an agent get one answer."""
    from_api = Vitai(DEMO).may("run", ON)
    from_mcp = mcp.call(DEMO, "may", {"activity": "run", "on": ON})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "may", "run", "--root", str(DEMO),
         "--on", ON, "--json"], capture_output=True, text=True)
    from_cli = json.loads(out.stdout)

    assert from_api == from_mcp == from_cli


def test_the_cli_exits_non_zero_on_anything_but_allowed():
    """A shell reading exit 0 as permission would turn "nobody has said" into
    a green light, which is the failure this command exists to stop."""
    codes = {}
    for activity in ("run", "walk", "aqua-jogging"):
        out = subprocess.run(
            [sys.executable, "-m", "vitai.cli", "may", activity,
             "--root", str(DEMO), "--on", ON], capture_output=True, text=True)
        codes[activity] = out.returncode

    assert codes["walk"] == 0
    assert codes["run"] == 2
    # 3, not 2: argparse exits 2 on a usage error, so a script checking only
    # the code could not tell a refusal from a typo'd flag.
    assert codes["aqua-jogging"] == 3, "unknown must not read as permission"


def test_the_mcp_tool_honours_the_viewpoint():
    """A gate lifted today and a gate in force last week are different
    answers, so an agent that pins a date must get the pinned one."""
    early = mcp.call(DEMO, "may", {"activity": "run", "on": "2030-06-28"})
    later = mcp.call(DEMO, "may", {"activity": "run", "on": "2030-06-29"})

    assert early["verdict"] != later["verdict"], (
        "the demo's hop-test clears the gate on the 29th, so these must differ")


def test_the_engine_already_held_the_mapping():
    """The issue proposed building a resolution that already existed.

    `session_types.toml` declares that a run falls under `impact` and a walk
    does not, so the answer was computable and unaskable - the same shape as
    #257, #258 and #267, where a correct capability had no supported door.
    """
    from vitai.vocab import session_classes

    assert "impact" in session_classes("run")
    assert "impact" not in session_classes("walk")
    assert "impact" not in session_classes("cycle")


def test_a_stop_everything_gate_is_not_reported_as_unanswerable(tmp_path):
    """`unknown` must not short-circuit before the gates are read.

    Every pain gate and every clinical hold restricts `all`. Reading the
    registry alone made an unclassified activity answer "this record cannot
    say whether a gate covers it" while every gate in the record said no -
    the engine denying it could tell, with the answer sitting in front of it.
    """
    v = _gated(tmp_path, restricts="all")

    out = v.may("aqua-jogging", "2030-05-02")

    assert out["verdict"] == "blocked"
    assert out["matched"] == ["all"]


def test_a_gate_naming_an_activity_outright_still_bites(tmp_path):
    """`session_classes` treats an unrecognised activity as its own class so
    a gate naming it directly bites. Reading the registry instead split the
    two surfaces: `gated` blocked it and `may` called it unanswerable.

    Written RAW rather than appended: `append` refuses a `restricts` token
    that is not a known class, and the read path deliberately honours one
    anyway - which is why `session_classes` has the fallback at all. A record
    is plain text and the engine reads what is in it.
    """
    from vitai.schema import CURRENT_GENERATION, KEYS

    root = init(tmp_path / "content")
    rec = {k: None for k in KEYS["medical"]}
    rec.update({"date": "2030-05-01", "slug": "achilles", "kind": "symptom",
                "title": "soreness", "severity": "mild",
                "status": "monitoring", "restricts": "aqua-jogging",
                "source": "athlete", "_gen": CURRENT_GENERATION["medical"]})
    (root / "data" / "medical.jsonl").write_text(
        json.dumps(rec) + "\n", encoding="utf-8")
    v = Vitai(root)

    assert v.gated("aqua-jogging", "2030-05-02") is True
    assert v.may("aqua-jogging", "2030-05-02")["verdict"] == "blocked"


def test_an_activity_class_is_a_legal_question(tmp_path):
    """Both surfaces document taking "a session type or activity class", and
    only one of them did."""
    v = _gated(tmp_path)

    for token in ("impact", "cardio"):
        assert v.gated(token, "2030-05-02") == (
            v.may(token, "2030-05-02")["verdict"] == "blocked"), token
    assert v.may("impact", "2030-05-02")["verdict"] == "blocked"


def test_a_movement_restriction_is_not_an_answer_about_an_activity(tmp_path):
    """THE CONFIDENT FALSE GREEN LIGHT.

    A post-coordinated gate - "no loaded hip hinging" - restricts particular
    movements and carries no activity class at all. Reading only `restricts`
    made a clinical hold invisible, so `may("strength")` answered ALLOWED
    with the sentence "no gate in force covers this activity" while one was.
    """
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("medical", {"date": "2030-05-01", "slug": "hip", "kind": "injury",
                         "title": "a hip episode", "body_site": "hip",
                         "body_side": "left", "severity": "mild",
                         "status": "active", "source": "athlete",
                         "restriction": "pattern=hinge region=hip load=loaded"})

    out = v.may("strength", "2030-05-02")

    assert out["verdict"] == "unknown"
    assert "no gate in force" not in out["reason"]
    assert "per movement" in out["reason"]
    assert out["gates"] == ["hip"]


def test_every_verdict_has_the_same_shape():
    """`matched` was present on one branch and absent on the others, so a
    consumer keying on it got a surprise from a different answer."""
    v = Vitai(DEMO)
    shapes = {frozenset(v.may(a, ON)) for a in ("run", "walk", "nonsense")}

    assert len(shapes) == 1, shapes
