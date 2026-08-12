"""`Vitai.plan()` (#368): a plan is DECIDED, never ACQUIRED.

`claim()` and `said()` split narrative capture on whether a number can be
taken from what was said. A plan is a third act: it has structure (`slug`,
`for_date`, `activity`, `tier`, `serves`), so `said()` cannot hold it, and
nothing was observed, so `claim()`'s acquisition stamp (`capture`, `read_by`,
`source`) would be a lie on it. `plans` carries its own provenance
vocabulary - `set_by`, `tier`, `reason` - and `plan()` is the one door that
writes through it.

These tests cover: a valid plan row and its stamped provenance; the refusal
`claim(dataset="plans", ...)` now raises, naming the verb to use instead; that
refusal reachable through the CLI and the MCP tool; that `plan()` offers no
`dataset` argument to misuse in the first place; and the round trip through
whatever already reads `plans`.
"""

from __future__ import annotations

import json

import pytest

from vitai.api import Vitai
from vitai.cli import main
from vitai.mcp import call, tool_list
from vitai.schema import validate_record


def _repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def _valid_plan():
    """A plan row with every field `_validate_plan` requires unconditionally:
    a slug (identity), a `for_date` (ISO), and a `tier` (closed vocabulary,
    not optional). `serves` is left out because it is only required when
    `tier == "programme"`, which this is not."""
    return {"slug": "evening-run", "for_date": "2026-08-10",
            "activity": "run", "tier": "committed"}


# ---- a valid row, and what it does NOT carry --------------------------------

def test_plan_writes_a_valid_plans_row_with_no_acquisition_vocabulary(tmp_path):
    engine = Vitai(_repo(tmp_path))
    row = engine.plan(_valid_plan())
    assert validate_record("plans", row) == []
    for stamped in ("capture", "read_by", "source"):
        # Not merely absent from the CALL - absent from the ROW, because a
        # row carrying `capture: None` would still be the wrong shape: the
        # field belongs to `claim()`'s vocabulary and `plans` never declared
        # it (it is not in KEYS["plans"]), so it cannot even be null on this
        # row without `validate_record` refusing it as an unknown key.
        assert stamped not in row


def test_plan_round_trips_through_the_dataset_it_writes(tmp_path):
    """The read half: whatever already reads `plans` (`dataset("plans")`,
    used by `questions.py` and the projection surfaces) sees the row `plan()`
    wrote, untouched."""
    engine = Vitai(_repo(tmp_path))
    written = engine.plan(_valid_plan())
    [read_back] = engine.dataset("plans")
    assert read_back["slug"] == written["slug"] == "evening-run"
    assert read_back["for_date"] == "2026-08-10"
    assert read_back["tier"] == "committed"
    assert read_back["set_by"] == "athlete"


# ---- the intention provenance: `set_by` -------------------------------------

def test_set_by_defaults_to_athlete(tmp_path):
    """Matching `claim()`'s default for `read_by`: the commonest case is the
    athlete stating their own plan, so that is what a caller gets without
    naming one."""
    engine = Vitai(_repo(tmp_path))
    row = engine.plan(_valid_plan())
    assert row["set_by"] == "athlete"


def test_set_by_carries_a_coach_set_plan(tmp_path):
    """`plans` treats a coach-set plan and a self-set plan as equally able to
    bind (the vocabulary is `goals`/`events`/`thresholds`' own AUTHORS set),
    so the caller can say who decided rather than have it defaulted away."""
    engine = Vitai(_repo(tmp_path))
    row = engine.plan(_valid_plan(), set_by="coach")
    assert row["set_by"] == "coach"


def test_set_by_is_checked_against_the_authors_vocabulary(tmp_path):
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="set_by is one of"):
        engine.plan(_valid_plan(), set_by="the athlete's imaginary friend")


# ---- the fields the engine stamps, refused inside `values` ------------------

def test_set_by_cannot_be_smuggled_through_values(tmp_path):
    """The same rule `claim()` applies to `read_by`: a caller who could set
    its own `set_by` inside the dict could file a coach's decision as the
    athlete's own, or the reverse - so it is a keyword argument, not a key."""
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match=r"the `set_by` parameter"):
        engine.plan({**_valid_plan(), "set_by": "coach"})


def test_supersedes_needs_the_deliberate_corrects_parameter(tmp_path):
    """`supersedes` retires the line it names on every future load - the
    record's only destructive primitive - so it is reached through `corrects`
    exactly as on `claim()`, never through a key that rode into `values`."""
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="corrects"):
        engine.plan({**_valid_plan(), "supersedes": "evening-run@2026-08-01"})
    row = engine.plan(_valid_plan(), corrects="evening-run@2026-08-01")
    assert row["supersedes"] == "evening-run@2026-08-01"


@pytest.mark.parametrize("field", ["recorded_at", "device", "_gen"])
def test_machine_set_fields_are_refused_from_values(tmp_path, field):
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="not a field the caller states"):
        engine.plan({**_valid_plan(), field: "anything"})


def test_the_allowlist_covers_a_field_nobody_has_added_yet(tmp_path):
    """A denylist fails silently every time the schema grows; this refuses
    anything that is not a declared field of `plans`."""
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError, match="no field"):
        engine.plan({**_valid_plan(), "trustworthiness": 11})


# ---- claim(dataset="plans", ...) now names the verb to use instead ---------

def test_claim_on_plans_names_the_verb_to_use(tmp_path):
    """The refusal used to be `append_many`'s generic "unknown key(s) for
    plans: capture, read_by, source" - three internal field names and no way
    forward. `claim()`'s own "not a quantity" error hands back the parameter
    to use; this one hands back the verb."""
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError) as caught:
        engine.claim("plans", {"slug": "evening-run",
                               "for_date": "2026-08-10", "tier": "committed"})
    message = str(caught.value)
    assert "plan()" in message
    # Not just ANY error - not the generic one it used to fall through to,
    # which named the internal fields and nothing to do about them.
    assert "capture, read_by, source" not in message


def test_claim_on_plans_refuses_before_any_row_is_written(tmp_path):
    """A refusal that still wrote something would be worse than the one it
    replaces. Nothing should land in `plans.jsonl`."""
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(ValueError):
        engine.claim("plans", {"slug": "evening-run",
                               "for_date": "2026-08-10", "tier": "committed"})
    assert engine.dataset("plans") == []


# ---- the same refusal, reachable through the CLI ----------------------------

def test_the_cli_relays_the_plans_refusal_naming_the_verb(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["claim", "--root", str(root), "--dataset", "plans",
              "slug=evening-run"])
    assert "plan()" in str(caught.value)


def test_the_plan_verb_is_reachable_through_the_cli(tmp_path, capsys):
    """P9: the CLI verb lands in the same change as the API method."""
    root = _repo(tmp_path)
    capsys.readouterr()
    main(["plan", "--root", str(root), "--set-by", "coach",
          "slug=evening-run", "for_date=2026-08-10", "activity=run",
          "tier=committed"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["slug"] == "evening-run"
    assert printed["set_by"] == "coach"
    assert "capture" not in printed
    assert len(Vitai(root).dataset("plans")) == 1


# ---- the same refusal, reachable through the MCP tool -----------------------

def test_the_mcp_claim_tool_relays_the_plans_refusal_naming_the_verb(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(ValueError) as caught:
        call(root, "claim", {"dataset": "plans",
                             "values": {"slug": "evening-run",
                                        "for_date": "2026-08-10",
                                        "tier": "committed"}})
    assert "plan()" in str(caught.value)


def test_the_plan_tool_is_reachable_through_mcp(tmp_path):
    root = _repo(tmp_path)
    row = call(root, "plan", {
        "values": {"slug": "evening-run", "for_date": "2026-08-10",
                   "activity": "run", "tier": "committed"},
        "set_by": "athlete",
    })
    assert row["slug"] == "evening-run"
    assert row["set_by"] == "athlete"
    assert len(Vitai(root).dataset("plans")) == 1


def test_the_plan_tool_does_not_offer_the_destructive_corrects_argument(tmp_path):
    """Matching `claim`'s own tool: the retire path is deliberately withheld
    from the MCP surface, not merely undocumented, so an agent driving this
    tool cannot reach it by ignoring the declared schema."""
    root = _repo(tmp_path)
    advertised = {t["name"]: set(t["inputSchema"]["properties"])
                  for t in tool_list()}
    assert "corrects" not in advertised["plan"]
    with pytest.raises(KeyError) as caught:
        call(root, "plan", {"values": _valid_plan(),
                            "corrects": "evening-run@2026-08-01"})
    assert "corrects" in str(caught.value)


# ---- plan() offers no dataset argument to misuse in the first place --------

def test_plan_has_no_dataset_parameter(tmp_path):
    """The design decision the issue calls for: refusing a dataset that is
    not `plans` by not offering the choice, rather than by checking one.
    Asserted on the signature, because there is no argument slot to pass a
    wrong value into."""
    import inspect

    params = inspect.signature(Vitai.plan).parameters
    assert "dataset" not in params
    # And passing one by keyword does not silently get ignored either - a
    # caller reaching for the `claim()` shape out of habit gets a TypeError
    # from Python itself, naming the argument it does not recognise.
    engine = Vitai(_repo(tmp_path))
    with pytest.raises(TypeError):
        engine.plan(_valid_plan(), dataset="weight")
