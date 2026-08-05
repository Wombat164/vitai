"""Reading a derived table is a supported call, by its contract name (#267).

`best_efforts` is materialised, correct, and was reachable three ways, all
wrong: a private attribute, a direct query against a table name the contract
exists to insulate consumers from, or re-parsing the tracks - at which point
the number is the caller's claim rather than this engine's, which is what
#247 was closed to prevent. The client did none of them and shipped without
it, which was the right call and left the gap.

That is #257 arriving a second time in three weeks, and #258 a third, so the
fix is the shape those established rather than a fourth convention.

One thing checked before it was claimed: `best_efforts` is the ONLY derived
table with no public path. `goal_progress`, `plan_churn` and `justifications`
are all reachable - under `goals()`, `churn()` and `resolution()`. That is the
same defect in a quieter form, because the contract table names the TABLE and
nothing tells a consumer which method hides it.

AND THE CHECK THAT MATTERED WAS THE ONE I NEARLY SKIPPED. I first wrote that
the named accessors return the same rows, having compared them on the demo
record and seen them match. They do not: `goals()` computes over `datasets()`,
the RAW claims, and the table computes over the resolved canonical rows. The
demo simply has no duplicate capture touching a counted goal. `reaches the
same rows` was a claim about one fixture wearing the clothes of a claim about
the engine, so it is pinned below on a record built to break it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import Vitai
from vitai.db import DERIVED_TABLES

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def test_every_derived_table_is_reachable_by_its_contract_name():
    """The register, and it has to check the KEYS rather than the return.

    The first version asserted `isinstance(..., list)`, which cannot fail:
    `derived()` refuses an unknown name and returns `.get(name) or []` for a
    known one, so a table `_derivations` stopped emitting would return `[]`
    forever and pass. Renaming one key inside `_derivations` left all 1509
    tests green while both the accessor and the built table went empty - the
    specified-and-never-written defect, in the guard meant to catch it.

    `build_db` indexes the same dict with the same `or []`, so this one
    comparison covers the accessor and the read model together.
    """
    v = Vitai(DEMO)
    computed = v._derivations(v.resolution(), today=v.on)

    assert set(computed) == set(DERIVED_TABLES), (
        "a derivation key that no table name matches is written nowhere, and "
        "a table name no derivation produces is empty forever")
    # And the demo, which ships tracks, goals and contested rows, must
    # actually populate them rather than merely declaring them.
    empty = sorted(t for t in DERIVED_TABLES if not v.derived(t))
    assert empty == ["escalations"], (
        f"unexpectedly empty on the demo record: {empty}")


def test_best_efforts_is_reachable_without_a_private_attribute():
    """The specific gap #267 was filed for."""
    rows = Vitai(DEMO).derived("best_efforts")

    assert rows, "the demo record ships tracks, so this must not be empty"
    assert set(DERIVED_TABLES["best_efforts"]) <= set(rows[0])


def test_basis_survives_the_trip():
    """WITHOUT IT A TIME IS A NUMBER WHOSE CLASS HAS BEEN THROWN AWAY.

    `device` means measured against the watch's own cumulative distance, an
    observation. `derived` means against the engine's haversine sum, which is
    not. On a real 11 km track the two differ by twenty seconds over ten
    kilometres, so a client rendering one as the other is quoting a figure it
    cannot stand behind.
    """
    rows = Vitai(DEMO).derived("best_efforts")

    assert all(r.get("basis") for r in rows)
    # SUBSET, not intersection. `&` passes when every effort collapses to one
    # basis, which is the regression this test is named for.
    assert {"device", "derived"} <= {r["basis"] for r in rows}


def test_an_unknown_table_is_refused_with_the_list():
    with pytest.raises(KeyError) as raised:
        Vitai(DEMO).derived("best_effort")          # the singular, a typo

    assert "best_efforts" in str(raised.value)


def test_a_dataset_name_is_not_a_derived_table():
    """The two accessors are keyed by different vocabularies, and a caller
    reaching for the wrong one should be told rather than handed nothing."""
    with pytest.raises(KeyError):
        Vitai(DEMO).derived("sessions")
    with pytest.raises(KeyError):
        Vitai(DEMO).dataset("best_efforts")


def test_the_three_surfaces_return_the_same_rows():
    """P9. An agent, a script and a library caller get one answer."""
    from_api = Vitai(DEMO).derived("best_efforts")
    from_mcp = mcp.call(DEMO, "derived", {"name": "best_efforts"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "derived", "best_efforts",
         "--root", str(DEMO), "--json"],
        capture_output=True, text=True, check=True)
    from_cli = [json.loads(line) for line in out.stdout.splitlines()]

    # Dict equality ignores key order, which is the only thing the CLI's
    # `sort_keys` changes. ROW order must still match, so this compares the
    # lists rather than sets of them.
    assert from_api == from_mcp == from_cli


def test_the_mcp_tool_offers_every_table_the_engine_has():
    """The enum comes from the engine, so a table added to the read model is
    offered the same day rather than whenever somebody widens a literal."""
    tool = [t for t in mcp.tool_list() if t["name"] == "derived"][0]

    assert set(tool["inputSchema"]["properties"]["name"]["enum"]) == set(
        DERIVED_TABLES)
    assert tool["description"].strip()


def test_the_mcp_tool_refuses_an_undeclared_argument():
    """The declared schema is the whole surface, enforced rather than
    advertised - the property that keeps `claim` from reaching `corrects`."""
    with pytest.raises(KeyError):
        mcp.call(DEMO, "derived", {"name": "best_efforts", "on": "2030-06-01"})


def test_an_empty_derived_table_says_so_rather_than_printing_nothing():
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "derived", "escalations",
         "--root", str(DEMO)], capture_output=True, text=True, check=True)

    assert "no rows" in out.stdout


def test_the_cli_refuses_a_table_the_engine_does_not_have():
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "derived", "invented",
         "--root", str(DEMO)], capture_output=True, text=True)

    assert out.returncode != 0
    assert "best_efforts" in out.stderr


def test_a_write_does_not_leave_a_stale_derived_view(tmp_path):
    """The cache is per instance and a write is what makes an instance stale.

    `_forget` clears it for the same reason it clears the loaded datasets: an
    instance is a view at one cutoff, and a table computed before an append
    describes a record that no longer exists.
    """
    from vitai.api import init

    root = init(tmp_path / "content")
    v = Vitai(root)
    assert v.derived("session_weeks") == []

    # Only what a caller may assert: `device`, `recorded_at` and `_gen` are
    # machine-stamped and the append path refuses a supplied one.
    v.append("sessions", {"date": "2030-05-06", "type": "run",
                          "distance_km": 10.0, "duration_s": 3600,
                          "source": "watch"})

    assert v.derived("session_weeks"), (
        "the derived view was computed before the append and never dropped")


def test_the_named_accessor_and_the_table_are_not_the_same_rows(tmp_path):
    """The divergence, on a record that exposes it.

    One session reaching the record twice - a watch file and the same run
    re-logged from a phone - is one session after resolution and two before
    it. `goals()` reads before, the `goal_progress` table reads after, so
    they report different progress against one goal, and a consumer moving
    from one to the other silently changes what the athlete is told.

    THIS TEST DOES NOT SAY WHICH IS RIGHT. The build's own doctrine is that
    judging on raw claims double counts, which points at `goals()` being the
    defect, but changing what a live accessor reports is not #267's to do.
    What is #267's is that the two are documented as different rather than
    discovered to be.
    """
    from vitai.api import init

    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "weekly-km",
                       "title": "twenty kilometres a week",
                       "metric": "distance_km", "target": 20.0,
                       "policy": "monotonic", "period": "weekly",
                       "lifecycle_status": "active", "dataset": "sessions"})
    for source in ("watch", "phone"):
        v.append("sessions", {"date": "2030-05-06", "type": "run",
                              "distance_km": 10.0, "duration_s": 3600,
                              "source": source})

    named = {r["slug"]: r["counted"] for r in v.goals(date(2030, 5, 8))}
    table = {r["slug"]: r["counted"] for r in v.derived("goal_progress")}

    assert named["weekly-km"] != table["weekly-km"], (
        "if these agree the divergence is gone, and the docstrings saying "
        "they differ are now the thing that is wrong")
    assert named["weekly-km"] == 20.0        # both claims counted
    assert table["weekly-km"] == 10.0        # one session, resolved
