"""A gate nobody can read is not a clear run.

`restricts` was matched by set intersection against the activity's classes, on
the RAW tokens. Anything the intersection could not hit vanished - and `may`
fell through to its last branch and answered `allowed`, with the reason "no
gate in force covers this activity", about a record whose own gate said
`blocked`.

TWO WAYS IN, and the second needs no mistake by anybody. A typo is the obvious
one. The other is `restricts: gym` - a RETIRED activity class, which
`ACTIVITY_CLASSES` unions in, so the line VALIDATES CLEAN, and which no session
type declares, so it matched nothing. A severe active episode, correctly
written against the vocabulary of its day, silently stopped gating.

The fix is not a longer list of bad tokens; it is that READABLE MEANS THE
MATCHER CAN MATCH IT rather than that the validator accepts it. Every token now
resolves through the registry first, so `gym` becomes `strength` and bites,
which is only the retirement doctrine already written in `vocab.py` - "the
value stays legal forever and resolves forward to its replacement" - applied by
the reader that was not doing it. Same G89 part-two shape as `hip_pain`.

Found scanning the backlog rather than filed. It is the read half of the harm
`vocab.py` already names in prose:

    an activity class that no rule understands is an unenforced gate, which is
    the exact harm the whole restriction rework exists to remove

THE VALIDATOR ALREADY CAUGHT THE NONSENSE, and that was not enough. `validate`
reports it and returns `ok: False`, but it is a separate call a consumer may
never make, and no safety answer may depend on somebody having made it. The
refusal has to live where the decision is taken.

WHY UNKNOWN RATHER THAN BLOCKED. Treating an unreadable gate as blocking every
activity would be a different invention: the record does not say that either,
and over-restriction is a harm this repo has argued about before (#145). What
is true is that the question cannot be decided, and `may` already has a third
answer for exactly that. `is_gated` returns a bool and cannot carry it, so it
takes the safe side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.safety import (gates_on, is_gated, may, restriction_scope,
                          unreadable_restriction)
from vitai.schema import ACTIVITY_CLASSES, KEYS, validate_record
from vitai.vocab import session_classes as classes_of
from vitai.vocab import session_types

# WHAT THE MATCHER CAN ACTUALLY HIT, which is not the same as what the
# validator accepts, and the gap between them is where `gym` lived. Comparing
# against the legal set is a tautology - `resolve` can only ever return a legal
# slug - so it would pass for any class nobody declares.
DECLARED_CLASSES = {c for t in session_types() for c in classes_of(t)}

# GENUINELY unreadable: nothing in the registry resolves it. `lower-body` was
# the first choice and was wrong - the registry normalises it to `lower_body`,
# so it is a spelling the validator rejects and the matcher understands fine.
NONSENSE = "not-a-body-part"

# LEGAL, VALIDATOR-CLEAN, AND IT USED TO VANISH. `gym` is a RETIRED activity
# class, and `ACTIVITY_CLASSES` unions the retired values in, so validation
# passes - but no session type declares `gym`, so the intersection was empty
# and the gate disappeared. The worse half of this defect, and the half the
# first fix missed: it needs no typo at all.
RETIRED = "gym"

# A spelling the validator rejects and the registry resolves.
MISSPELT = "lower-body"


def episode(**kw) -> dict:
    return {**{k: None for k in KEYS["medical"]}, "date": "2030-05-01",
            "slug": "hip", "kind": "injury", "title": "tweak",
            "status": "active", "severity": "severe",
            "recorded_at": "2030-05-01T08:00:00Z", **kw}


def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "medical.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def gates_for(rows: list[dict]) -> list[dict]:
    return gates_on(rows, "2030-05-01")


# --- the defect ---------------------------------------------------------------

def test_a_gate_the_engine_cannot_read_does_not_answer_allowed(tmp_path):
    """The whole issue in one assertion. Before this, `may('run')` returned
    `allowed` with the reason "no gate in force covers this activity" - on a
    record holding an active, severe, blocking gate."""
    v = record(tmp_path, [episode(restricts=NONSENSE)])
    assert [g["status"] for g in v.gates()] == ["blocked"]
    answer = v.may("run")
    assert answer["verdict"] == "unknown", answer


def test_the_refusal_names_the_token_and_where_to_fix_it(tmp_path):
    """An unknown a reader cannot act on becomes an unknown they work around.
    It names the offending token and sends them to the validator, because this
    is a typo in the record rather than a limit of the engine."""
    v = record(tmp_path, [episode(restricts=NONSENSE)])
    reason = v.may("run")["reason"]
    assert repr(NONSENSE) in reason, reason
    assert "vitai validate" in reason, reason
    assert "not treated as permission" in reason, reason


def test_it_relays_the_gate_s_own_sentence_first(tmp_path):
    """A consumer renders gate text verbatim and may not paraphrase, so the
    clinician's words lead and the engine's explanation follows."""
    v = record(tmp_path, [episode(restricts=NONSENSE)])
    answer = v.may("run")
    assert answer["reason"].startswith("tweak (active)"), answer["reason"]
    assert answer["gates"] == ["hip"]


def test_is_gated_refuses_rather_than_permits():
    """A bool cannot say `unknown`, so it takes the safe side. Answering False
    here is answering "not gated", which every caller reads as permitted."""
    gates = gates_for([episode(restricts=NONSENSE)])
    assert is_gated(gates, "run") is True
    assert is_gated(gates, "swim") is True, "unreadable does not become readable"


def test_the_validator_reports_it_too_and_that_was_never_enough():
    """Both halves matter. `validate` is a separate call a consumer may never
    make; the safety answer must not depend on somebody having made it."""
    problems = validate_record("medical", episode(restricts=NONSENSE))
    assert any(repr(NONSENSE) in p for p in problems), problems


# --- and it does not fire where it should not ---------------------------------

def test_a_readable_gate_is_unaffected():
    gates = gates_for([episode(restricts="impact")])
    assert may(gates, "run")["verdict"] == "blocked"
    assert may(gates, "swim")["verdict"] == "allowed"
    assert is_gated(gates, "run") is True
    assert is_gated(gates, "swim") is False


def test_a_movement_scoped_gate_keeps_its_own_third_answer():
    """`restricts` empty plus a `restriction` spec is the OTHER unknown, and it
    has a different reason and a different remedy. Collapsing the two would
    tell somebody to run the validator over a record that is perfectly valid."""
    gates = gates_for([episode(restricts=None,
                               restriction="pattern=hinge region=hip load=loaded")])
    answer = may(gates, "strength")
    assert answer["verdict"] == "unknown"
    assert "Ask per movement" in answer["reason"], answer["reason"]
    assert "vitai validate" not in answer["reason"], answer["reason"]


def test_an_uncatalogued_activity_keeps_its_own_third_answer():
    """The gate is readable and the ACTIVITY is not. The illegible branch sits
    ahead of this one, so a record that classifies runs is never told that
    nobody has said what a run loads."""
    gates = gates_for([episode(restricts="impact")])
    answer = may(gates, "underwater-basket-weaving")
    assert answer["verdict"] == "unknown"
    assert "nobody has said what" in answer["reason"], answer["reason"]


def test_an_empty_restricts_is_not_unreadable():
    """Absence is not a typo. A gate that says nothing about activity classes
    is answered by the movement branch or by nothing at all."""
    assert unreadable_restriction({"restricts": None}) == set()
    assert unreadable_restriction({"restricts": ""}) == set()
    assert unreadable_restriction({}) == set()


@pytest.mark.parametrize("cls", sorted(ACTIVITY_CLASSES))
def test_every_legal_class_resolves_to_something_a_session_can_carry(cls):
    """The invariant the first cut got backwards.

    Asserting only that a legal class "reads as readable" is what let `gym`
    through: it is legal, it read as readable, and it matched nothing. What
    has to hold is that every legal token RESOLVES to a slug the matcher can
    actually hit - which is what makes validator-clean and gate-effective the
    same set.
    """
    resolved, unreadable = restriction_scope({"restricts": cls})
    assert not unreadable, f"{cls} is legal but nothing resolves it"
    assert resolved, cls
    if cls != "all":
        assert resolved <= DECLARED_CLASSES, (
            f"{cls} resolves to {resolved - DECLARED_CLASSES}, which no session "
            "type declares - so a gate scoped to it matches nothing and "
            "silently stops gating. That is the `gym` defect exactly.")


def test_a_gate_naming_several_classes_reports_only_the_bad_ones():
    """And a gate that names one good class and one bad one BLOCKS on the good
    one rather than going unknown - it has already decided the question."""
    gate = {"restricts": f"impact {NONSENSE}"}
    assert unreadable_restriction(gate) == {NONSENSE}
    gates = gates_for([episode(restricts=f"impact {NONSENSE}")])
    assert may(gates, "run")["verdict"] == "blocked"


def test_a_cleared_gate_stays_cleared_even_if_unreadable():
    """A precondition that passed today is reported and does not block. That
    rule is inherited, not restated, and an unreadable scope must not resurrect
    a gate a check has already cleared."""
    gates = [{"slug": "hip", "status": "cleared", "restricts": NONSENSE,
              "reason": "check passed", "restriction": None}]
    assert is_gated(gates, "run") is False
    assert may(gates, "run")["verdict"] == "allowed"


def test_the_whole_record_answer_agrees_with_the_gate(tmp_path):
    """The symptom that made this worth finding: one record answering its own
    question two ways. `gates()` said blocked and `may()` said allowed."""
    v = record(tmp_path, [episode(restricts=NONSENSE)])
    blocked = [g for g in v.gates() if g["status"] == "blocked"]
    assert blocked
    assert v.may("run")["verdict"] != "allowed"


# --- the case that needed no typo ---------------------------------------------

def test_a_retired_class_still_gates_and_does_not_vanish():
    """The worse half. `gym` was retired in favour of `strength`; the line is
    valid, the gate reads `blocked`, and `may("strength")` used to answer
    `allowed` because no session type declares `gym`."""
    gates = gates_for([episode(restricts=RETIRED)])
    assert validate_record("medical", episode(restricts=RETIRED)) == [], \
        "a retired class is legal forever - that is the whole point of retiring"
    assert may(gates, "strength")["verdict"] == "blocked"
    assert is_gated(gates, "strength") is True


def test_a_retired_class_gates_exactly_what_its_successor_gates():
    """Resolving forward is not a licence to widen. `gym` becomes `strength`
    and stops there - it does not become "everything that happens indoors"."""
    retired_gates = gates_for([episode(restricts=RETIRED)])
    successor = gates_for([episode(restricts="strength")])
    for activity in ("strength", "run", "swim", "cycle", "walk"):
        assert may(retired_gates, activity)["verdict"] \
            == may(successor, activity)["verdict"], activity


def test_a_spelling_the_registry_knows_is_matched_not_refused():
    """`lower-body` is rejected by the validator and understood by the
    registry. Refusing to match it would turn a spelling complaint into a
    disappeared gate, which is the defect rather than the fix - so the gate
    bites and the validator still says to write the canonical slug."""
    gates = gates_for([episode(restricts=MISSPELT)])
    assert may(gates, "run")["verdict"] == "blocked"
    assert validate_record("medical", episode(restricts=MISSPELT)), \
        "the canonical spelling is still what a new line owes"


def test_every_token_is_tried_and_the_unresolved_ones_are_also_flagged():
    """The two sets are not a partition, and the overlap is deliberate.

    Everything goes in the first set, so nothing is dropped without being
    tried - dropping a token untried is exactly how the original defect
    worked. The second set is the SUSPICION: tokens nothing resolves, which
    are either a typo or a gate naming an activity outright. They are tried
    first and only reported if they miss.
    """
    tried, unresolved = restriction_scope(
        {"restricts": f"impact {RETIRED} {MISSPELT} {NONSENSE}"})
    assert tried == {"impact", "strength", "lower_body", NONSENSE}
    assert unresolved == {NONSENSE}
    assert unresolved <= tried, "a suspected token must still be tried"


def test_a_gate_naming_an_uncatalogued_activity_still_bites_that_activity():
    """The guardrail this nearly broke. `restricts: aqua-jogging` gates
    aqua-jogging, and it did so by matching the raw token - which the first
    version of the resolver threw away, turning a working direct-naming gate
    into `unknown`."""
    gates = gates_for([episode(restricts="aqua-jogging")])
    assert may(gates, "aqua-jogging")["verdict"] == "blocked"
    assert is_gated(gates, "aqua-jogging") is True


def test_but_it_does_not_silently_permit_everything_else():
    """The other side of the same token. Nobody classified aqua-jogging, so
    whether it overlaps running is undecidable - and `may` already refuses on
    exactly that ground when the ASKED activity is uncatalogued. This is the
    same rule applied to the gate's side of the comparison."""
    gates = gates_for([episode(restricts="aqua-jogging")])
    assert may(gates, "run")["verdict"] == "unknown"


# --- and it does not ask the athlete to fix it with a check -------------------

def test_an_unreadable_gate_raises_no_clearance_question(tmp_path):
    """`is_gated` counts an unreadable gate as gating, which is right for a
    bool on a safety surface - and it must not turn into a QUESTION.

    A clearance question says the way out is doing the check. The way out here
    is fixing a token in the record, so asking the athlete to earn clearance
    from a gate whose scope nobody can read sends them to do work that settles
    nothing. `may` reports it and `validate` names the token; the asking
    channel stays quiet.
    """
    from vitai.questions import gates_for as clearance_gates

    plan = {"slug": "sat-long", "for_date": "2030-05-04", "activity": "run",
            "outcome": "unresolved"}
    unreadable = episode(restricts=NONSENSE, precondition="hop-test",
                         status="active")
    readable = episode(slug="knee", restricts="impact", precondition="hop-test",
                       status="active")

    def gates_on_day(_day, rows=(unreadable,)):
        return gates_on(list(rows), "2030-05-04")

    assert clearance_gates(plan, gates_on_day) == [], \
        "an unreadable gate must not become a check the athlete can do"
    # The control: the same shape with a READABLE scope does ask.
    assert clearance_gates(plan, lambda d: gates_on([readable], "2030-05-04")) \
        == ["knee"]


def test_an_unreadable_gate_does_not_hide_a_movement_scoped_one():
    """Both undecidable gates are named, not just whichever got there first.

    The verdict is `unknown` either way, so this changes no decision - but the
    answer claims to carry "the gates that decided it", and dropping the
    movement-scoped one loses its remedy. The two unknowns want opposite
    actions: fix a token, versus ask per movement.
    """
    gates = gates_for([episode(restricts=NONSENSE),
                       episode(slug="knee", restricts=None,
                               restriction="pattern=hinge region=knee load=loaded")])
    answer = may(gates, "strength")
    assert answer["verdict"] == "unknown"
    assert sorted(answer["gates"]) == ["hip", "knee"], answer["gates"]
    assert "vitai validate" in answer["reason"]
    assert "Ask per movement" in answer["reason"]


# --- the rules the mutation pass found uncontrolled ---------------------------

def test_a_legal_class_no_session_type_declares_would_be_caught():
    """The control on the control. `test_every_legal_class_resolves...` is only
    worth having if it can fail, and its first version could not: it compared
    against the legal set, which `resolve` can only ever return a member of.

    Simulated here rather than asserted about today's registry, because today's
    registry is clean and the point is that it might not stay so.
    """
    invented = "aerial"
    assert invented not in DECLARED_CLASSES
    resolved, unreadable = {invented}, set()
    assert not unreadable, "the weak assertion would pass"
    assert not resolved <= DECLARED_CLASSES, \
        "the strengthened one catches it"


def test_the_illegible_branch_sits_ahead_of_the_uncatalogued_one():
    """Ordering, which had no control anywhere in the suite.

    Both answers are `unknown`, so nothing in the suite noticed - but demoted,
    the gate DISAPPEARS from the answer and the reader is told nobody has said
    what their activity loads, when the thing to fix is a token in the record.
    """
    gates = gates_for([episode(restricts=NONSENSE)])
    answer = may(gates, "underwater-basket-weaving")
    assert answer["verdict"] == "unknown"
    assert answer["gates"] == ["hip"], "the unreadable gate must still be named"
    assert "vitai validate" in answer["reason"]
    assert "nobody has said what" not in answer["reason"]


def test_a_matching_gate_keeps_its_clearance_question_despite_a_junk_token():
    """The regression the second review caught, and the reason `gates_for` asks
    "undecidable for THIS activity" rather than "unreadable at all".

    The gate blocks running on `impact`; the hop test is exactly the way out.
    A second, unrelated junk token must not silence that."""
    from vitai.questions import gates_for as clearance_gates

    plan = {"slug": "sat-long", "for_date": "2030-05-04", "activity": "run",
            "outcome": "unresolved"}
    mixed = episode(slug="knee", restricts=f"impact {NONSENSE}",
                    precondition="hop-test", status="active")
    assert clearance_gates(
        plan, lambda d: gates_on([mixed], "2030-05-04")) == ["knee"]


def test_a_direct_naming_gate_keeps_its_clearance_question_too():
    """`restricts: aqua-jogging` bites aqua-jogging, so the check is the remedy
    there as well - the token being unresolvable says nothing about whether the
    gate covers the activity it names."""
    from vitai.questions import gates_for as clearance_gates

    plan = {"slug": "pool", "for_date": "2030-05-04",
            "activity": "aqua-jogging", "outcome": "unresolved"}
    direct = episode(restricts="aqua-jogging", precondition="hop-test",
                     status="active")
    assert clearance_gates(
        plan, lambda d: gates_on([direct], "2030-05-04")) == ["hip"]


def test_two_unreadable_gates_each_keep_their_own_sentence():
    """No comma splice and no misattribution. The first version pooled the
    tokens under one singular clause, so each gate was described as restricting
    the other's token - a sentence neither gate said, on a surface that relays
    gate text verbatim."""
    gates = gates_for([episode(restricts="zzz-one"),
                       episode(slug="knee", restricts="zzz-two")])
    reason = may(gates, "run")["reason"]
    first, _, second = reason.partition("; ")
    assert second, reason
    assert "'zzz-one'" in first and "'zzz-two'" not in first, first
    assert "'zzz-two'" in second and "'zzz-one'" not in second, second


def test_the_tokeniser_is_the_one_the_validator_uses():
    """Two readers of one field is the G89 shape. `restricts: "run,impact"` is
    validator-clean, and a bare split made it one unresolvable token."""
    for written in ("run,impact", "run, impact", "run impact"):
        assert validate_record("medical", episode(restricts=written)) == [], written
        resolved, unreadable = restriction_scope({"restricts": written})
        assert resolved == {"run", "impact"}, (written, resolved)
        assert not unreadable, (written, unreadable)
    resolved, _ = restriction_scope({"restricts": ["run", "impact"]})
    assert resolved == {"run", "impact"}
