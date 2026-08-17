"""The changelog-fragment gate, runnable before a push (#416).

It was the one gate of five that ran ONLY in `ci.yml`. Four had a test file
each; this had none, so `pytest -q` was green whether the fragments were well
formed or not, and a badly named fragment failed after the push - in the job
#389's docstring already calls "the fast one nobody reads".

That is the same shape as everything else in this change: a check whose result
is not attributable to a local run. `scripts/pin_gate.py` now refuses a gate
script that no test exercises, so this file is what that rule asks for and the
next gate cannot arrive without one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import changelog_gate as gate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_this_repos_fragments_are_clean():
    """The gate passes here, so a failure is a new fragment's fault."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "changelog_gate.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_it_agrees_with_itself_when_called_as_a_library():
    """`main()` shells nothing and `check()` is what it reports. A gate whose
    subprocess answer and library answer could differ is two gates."""
    assert gate.check() == []
    assert gate.main() == 0


def test_the_check_can_actually_fail(tmp_path, monkeypatch):
    """The control on the control.

    A gate that returns `[]` no matter what passes both tests above and
    measures nothing - which is the defect this whole change is about. So it
    is pointed at a directory holding a fragment named the way the convention
    forbids, and it must complain.
    """
    bad = tmp_path / "changelog.d"
    bad.mkdir()
    (bad / "README.md").write_text("# Changelog fragments\n", encoding="utf-8")
    (bad / "418.md").write_text("- no category in the name\n", encoding="utf-8")
    monkeypatch.setattr(gate, "FRAGMENTS", bad)
    problems = gate.check()
    assert problems, "a fragment with no category was accepted"
    assert any("418.md" in p for p in problems), problems


def test_a_well_formed_fragment_is_accepted(tmp_path, monkeypatch):
    """The other direction, so the failure above is not the gate refusing
    everything it is shown."""
    good = tmp_path / "changelog.d"
    good.mkdir()
    (good / "README.md").write_text("# Changelog fragments\n", encoding="utf-8")
    (good / "418.fixed.md").write_text(
        "- **Something was wrong and now is not** (#418).\n", encoding="utf-8")
    monkeypatch.setattr(gate, "FRAGMENTS", good)
    assert gate.check() == []
