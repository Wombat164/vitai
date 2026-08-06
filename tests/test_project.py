"""If I do this, what then - a proposed act, projected (#193).

"Can I open that bag of crisps?" is not a status question. Everything else here
reports what IS; this reports what WOULD BE, which is the register people
actually use with a partner or a coach.

THE ASYMMETRY IS THE DESIGN. The purpose sentence says this engine logs
nutrition and BUILDS TRAINING PROGRAMMES - two different entitlements in one
breath. So a projected intake gets the record and nothing further: what it
would do to a target the athlete declared, and no verdict on whether to. The
training half is in scope for advice and is not built here, because an app that
answered both in the same voice would have quietly widened its own purpose.

The athlete cannot be expected to feel that difference. The boundary is the
app's to hold, not his to respect.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _record(tmp_path: Path, cap: float = 2600) -> Vitai:
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "intake-cap",
                       "title": "stay under the cap", "metric": "kcal_in",
                       "target": cap, "policy": "monotonic", "period": "daily",
                       "dataset": "daily", "polarity": "ceiling",
                       "lifecycle_status": "active"})
    v.append("daily", {"date": "2030-05-02", "kcal_in": 2100,
                       "source": "athlete"})
    return v


def _fingerprint(root: Path) -> str:
    """Every byte of the record, so a write of any kind shows up."""
    h = hashlib.sha256()
    for path in sorted((root / "data").rglob("*.jsonl")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def test_a_proposed_quantity_is_projected_against_a_declared_target(tmp_path):
    row, = _record(tmp_path).project("daily", {"kcal_in": 400},
                                     "2030-05-02")

    assert row["now"] == 2100.0
    assert row["proposed"] == 400.0
    assert row["projected"] == 2500.0
    assert row["room_left"] == 100.0
    assert row["breach"] is None


def test_a_projection_that_would_breach_says_so(tmp_path):
    row, = _record(tmp_path).project("daily", {"kcal_in": 900},
                                     "2030-05-02")

    assert row["projected"] == 3000.0
    assert row["breach"] == "over"
    assert row["room_left"] == -400.0


def test_a_projection_leaves_the_record_byte_identical(tmp_path):
    """A HYPOTHETICAL IS NOT A CLAIM.

    The append path already refuses caller-supplied provenance; a projection
    needs the stronger property of not being written at all - no append, no
    resolution, no rollup, no emission. Checked over every byte of every data
    file rather than by reading the code, because the guarantee is about what
    happens and not about what was intended.
    """
    v = _record(tmp_path)
    before = _fingerprint(v.root)

    v.project("daily", {"kcal_in": 900}, "2030-05-02")
    v.project("daily", {"kcal_in": 400}, "2030-05-02")

    assert _fingerprint(v.root) == before


def test_every_row_is_marked_as_a_projection(tmp_path):
    """A number that could be mistaken for something the record holds is the
    one thing this must never produce."""
    rows = _record(tmp_path).project("daily", {"kcal_in": 400}, "2030-05-02")

    assert rows and all(r["projection"] is True for r in rows)


def test_training_is_refused_rather_than_answered_in_the_same_voice(tmp_path):
    """The purpose sentence covers programming training and only LOGGING
    nutrition, so the two get different entitlements. Answering both here
    would widen the engine's own purpose quietly."""
    with pytest.raises(ValueError) as raised:
        _record(tmp_path).project("sessions", {"distance_km": 5},
                                  "2030-05-02")

    assert "nutrition-only" in str(raised.value)


def test_a_quantity_the_record_has_never_seen_is_refused(tmp_path):
    """"That bag of crisps" is an item the record does not know. A projection
    is arithmetic on this record's own fields; anything else would need a food
    table, which is a figure about somebody else."""
    with pytest.raises(KeyError):
        _record(tmp_path).project("daily", {"crisps": 1}, "2030-05-02")


def test_a_goal_with_no_daily_period_is_not_projected(tmp_path):
    """A weekly target has no answer to "if I eat this now" - the question is
    about today, and projecting it onto a week would state a figure over a
    window the athlete did not ask about."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("goals", {"date": "2030-05-01", "slug": "weekly-steps",
                       "title": "walk more", "metric": "steps",
                       "target": 70000, "policy": "monotonic",
                       "period": "weekly", "dataset": "daily",
                       "lifecycle_status": "active"})
    v.append("daily", {"date": "2030-05-02", "steps": 9000,
                       "source": "athlete"})

    assert v.project("daily", {"steps": 3000}, "2030-05-02") == []


def test_nothing_is_projected_where_nothing_was_declared(tmp_path):
    """The nutrition half projects against a DECLARED target and has nothing
    to say without one - which is the honest answer rather than inventing a
    reference the athlete never set."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    v.append("daily", {"date": "2030-05-02", "kcal_in": 2100,
                       "source": "athlete"})

    assert v.project("daily", {"kcal_in": 400}, "2030-05-02") == []


def test_the_three_surfaces_agree():
    """P9."""
    from_api = Vitai(DEMO).project("daily", {"kcal_in": 500})
    from_mcp = mcp.call(DEMO, "project",
                        {"dataset": "daily", "values": {"kcal_in": 500}})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "project", "daily", "kcal_in=500",
         "--root", str(DEMO), "--json"], capture_output=True, text=True,
        check=True)
    from_cli = [json.loads(ln) for ln in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli


def test_the_cli_says_the_number_was_not_written():
    """The register #193 asks for: the answer wanted is "yeah, you have room"
    and not a table, and the one thing the engine must not leave ambiguous is
    whether it just recorded something."""
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "project", "daily", "kcal_in=500",
         "--root", str(DEMO)], capture_output=True, text=True, check=True)

    assert "not a record" in out.stdout
    assert "yours" in out.stdout


def test_the_mcp_tool_offers_nutrition_only():
    """An agent reading the tool list learns the boundary from the schema
    rather than from a refusal after the fact."""
    tool, = [t for t in mcp.tool_list() if t["name"] == "project"]

    assert tool["inputSchema"]["properties"]["dataset"]["enum"] == ["daily"]
