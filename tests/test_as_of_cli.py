"""A knowledge cutoff is reachable from every surface, not just Python (#269).

`Vitai(root, as_of=...)` has always existed and `dataset()` has always honoured
it. `vitai dataset` exposed `--root` and `--json` and nothing else, so
reconstructing what the record KNEW at a past moment was an API-only
capability - which is the shape of defect #158 exists to remove, in the surface
that closed #258. Fine for Python; nothing at all for the connector author in
another language who is the reason `schema --json` exists.

`--as-of` AND NOT `--on`, which is the whole design question and the one place
this is easy to get wrong. Three of the four sibling read commands spell their
viewpoint `--on`, so copying them would be the familiar spelling of the wrong
axis:

    on     - valid time: as of what DAY is this being judged
    as_of  - transaction time: what did the record KNOW at that moment

`dataset()` returns raw claims and judges nothing, so `on` has no work to do
there and the cutoff is the only meaningful knob.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import Vitai

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
CUTOFF = "2030-05-01"


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weight",
         "--root", str(DEMO), *args], capture_output=True, text=True)


def test_a_cutoff_hides_what_was_appended_after_it():
    """The capability that existed and could not be asked for."""
    now = _cli("--json")
    then = _cli("--json", "--as-of", CUTOFF)

    assert now.returncode == 0 and then.returncode == 0
    assert len(then.stdout.splitlines()) < len(now.stdout.splitlines())


def test_the_cli_and_the_api_reconstruct_the_same_record():
    """P9, on the axis this adds rather than only on the rows."""
    from datetime import datetime

    from_api = Vitai(DEMO, as_of=datetime.fromisoformat(
        f"{CUTOFF}T00:00:00+00:00")).dataset("weight")
    out = _cli("--json", "--as-of", CUTOFF)
    from_cli = [json.loads(ln) for ln in out.stdout.splitlines()]

    assert from_cli == from_api


def test_the_mcp_tool_reaches_the_same_axis():
    """A capability one surface can reach the other must."""
    now = mcp.call(DEMO, "dataset", {"name": "weight"})
    then = mcp.call(DEMO, "dataset",
                    {"name": "weight", "as_of": f"{CUTOFF}T00:00:00+00:00"})

    assert len(then) < len(now)


def test_a_bare_date_means_utc_midnight():
    """"What did the record know on the 3rd" is the question a person asks,
    and refusing it over a missing timezone would be pedantry at the wrong
    moment."""
    bare = _cli("--json", "--as-of", CUTOFF)
    spelled = _cli("--json", "--as-of", f"{CUTOFF}T00:00:00+00:00")

    assert bare.returncode == 0
    assert bare.stdout == spelled.stdout


def test_a_naive_instant_is_refused_rather_than_guessed():
    """A naive cutoff compares against aware stamps by guessing a zone, and
    the guess is the local one - so the same command answers differently on
    two machines. The constructor already refuses it; the CLI says so before
    the traceback."""
    out = _cli("--as-of", f"{CUTOFF}T10:00:00")

    assert out.returncode != 0
    assert "no timezone" in out.stderr
    assert "two machines" in out.stderr


def test_nonsense_is_refused_with_the_shape_it_wanted():
    out = _cli("--as-of", "last tuesday")

    assert out.returncode != 0
    assert "ISO instant" in out.stderr


def test_the_flag_says_what_it_does_not_yet_do():
    """#148: `as_of` reconstructs past data under TODAY's policy, so an as-of
    read is already half a lie. Making it reachable by more people is the
    argument for the help text saying so rather than for waiting."""
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "--help"],
        capture_output=True, text=True, check=True)

    assert "--as-of" in out.stdout
    assert "#148" in out.stdout


def test_the_command_did_not_grow_an_on_flag():
    """The familiar spelling of the wrong axis. A `--on` here would read as a
    viewpoint on a command that judges nothing, which is how the two get
    conflated in the first place."""
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "--help"],
        capture_output=True, text=True, check=True)

    assert "--on " not in out.stdout and "--on\n" not in out.stdout


def test_the_mcp_tool_refuses_a_naive_cutoff():
    """Same refusal, same reason, through the agent's door."""
    with pytest.raises(ValueError):
        mcp.call(DEMO, "dataset",
                 {"name": "weight", "as_of": f"{CUTOFF}T10:00:00"})
