"""Everything the `demo` CI job asserts, runnable before pushing (#389).

The persona corpus is held to its generator by `test_personas_corpus`, INSIDE
pytest, so a developer finds drift by running the suite. The demo's equivalent
lived only in `.github/workflows/ci.yml`, and so did fourteen assertions about
what the shipped example must actually say. A green local suite could ship demo
drift, and did: #370's contract bump moved the `contract` stamp on the demo's
`emissions` rows, the local run reported 2908 passed, and the `demo` job went
red on a push.

A CHECK THAT EXISTS ONLY IN CI IS A CHECK NOBODY CAN RUN, and it fails at the
worst moment - after the work is pushed, in the job the `test_fixture_coverage`
docstring already describes as "the fast one nobody reads". This repo's whole
persona apparatus is built on the opposite premise.

WRITTEN AS ASSERTIONS RATHER THAN GREPS, which is the second half of the point.
`grep -q "impact blocked"` says a string is present; it cannot say what was
supposed to be there instead, so a failing job prints an exit code and the
reader goes to the YAML to find out what it wanted. Each test below carries
what it is protecting.

BUILT INTO A SCRATCH COPY. The workflow builds in place because a runner is
disposable; a test must not write `derived/` into the working tree, and the
copy also proves the demo builds from its committed data alone rather than
from something a previous build left behind.

THE CLI, NOT THE API, wherever the job used the CLI. #398 shipped a `KeyError`
in a CLI renderer while the whole suite was green, because every test drove the
API and nothing drove the command. Fidelity to what CI ran is the point here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
# The synthetic athlete's last day. The workflow pins it for the reason the
# comment there gives: the date-sensitive sections render what the demo exists
# to show only when read from the end of its own block.
ON = date(2030, 6, 30)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    work = tmp_path_factory.mktemp("demo") / "demo"
    shutil.copytree(DEMO, work, ignore=shutil.ignore_patterns("derived"))
    Vitai(work).build(today=ON)
    return work


def cli(root: Path, *args: str) -> str:
    proc = subprocess.run([sys.executable, "-m", "vitai.cli", *args,
                           "--root", str(root)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def rollup(built: Path) -> str:
    return (built / "derived" / "weekly.md").read_text(encoding="utf-8")


# --- the two that have no local equivalent at all -----------------------------

def test_the_committed_demo_matches_its_generator():
    """THE ONE THAT BIT. Byte-compared, the same contract the personas are
    held to - and the only check that catches a contract bump moving a stamp
    on a committed demo row."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "generate_demo.py"), "--check"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_demo_validates():
    """The shipped example must pass the engine's own validator. Advisories
    are allowed and are not failures - `validate` exits non-zero only on a
    line it refuses - so this asserts the exit code rather than the absence of
    advice, which the demo legitimately carries."""
    out = cli(DEMO, "validate")
    assert "all data lines valid" in out, out


# --- the rollup renders real content ------------------------------------------

def test_the_rollup_carries_a_rate_and_a_tripwire_section(built):
    """"Demo or it didn't happen". An example that builds an empty document
    would pass every structural check and teach nobody anything."""
    out = rollup(built)
    assert "**Rate:**" in out
    assert "Tripwires" in out


def test_the_happy_path_still_scores(built):
    """The demo's headline rate moved off the happy path when #37's timing
    artifact landed, so this is asserted where it still lives: a week with a
    consistent weigh-in routine scores normally in the machine contract."""
    assert '"verdict": "on_target"' in cli(built, "verdicts")


def test_a_rate_the_weigh_in_times_cannot_support_is_not_scored(built):
    """#37, and the most valuable thing the demo demonstrates. The routine
    falls apart after the travel week, so the current rate spans about twelve
    hours of weigh-in times - enough diurnal drift to account for the whole
    number. The rollup must decline to judge it AND say why, and the machine
    contract must not emit a verdict a consumer would render as fact."""
    out = rollup(built)
    assert "NOT READABLE" in out
    assert "not yet separable from weigh-in timing" in out
    verdicts = cli(built, "verdicts")
    assert '"metric": "weight_rate"' in verdicts
    assert '"verdict": "no_data"' in verdicts


# --- the safety layer ---------------------------------------------------------

def test_the_rollup_shows_a_live_gate(built):
    out = rollup(built)
    assert "## Gates" in out
    assert "impact blocked" in out


def test_all_three_precondition_states_render(built):
    """THE ONE THAT MATTERS IS THE MIDDLE ONE: a check nobody did is not a
    pass. The three states are different facts and the demo exists partly to
    show that they read differently."""
    assert "blocks impact" in cli(built, "safety", "--on", "2030-06-28")
    assert "hop-test" in cli(built, "safety", "--on", "2030-06-28")
    assert "fail" in cli(built, "safety", "--on", "2030-06-28")
    assert "LIFTED today" in cli(built, "safety", "--on", "2030-06-29")
    assert "check not done" in cli(built, "safety", "--on", "2030-06-30")


def test_a_resolved_episode_does_not_gate(built):
    """The calf episode is closed, and a closed episode that still gated would
    be the safety layer refusing to let go."""
    out = cli(built, "safety", "--on", "2030-06-30")
    assert "calf" not in out, out
