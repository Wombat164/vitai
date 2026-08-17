"""The pin gate catches what it is for, and it can fail (#416).

`loadline`'s `main` went red for two days and nobody noticed, and the fix that
stuck there was not bumping a pin - it was making one LOCAL check hold the
contract across all five places that state it, before a push. This file is the
local half of that here: the gate runs inside `pytest -q`, so a workflow that
starts resolving an input at run time fails on the machine that wrote it.

EVERY RULE IS TESTED AGAINST A CASE THAT DOES NOT EXIST IN THIS REPO. A gate
asserted only against the tree it guards is a gate that passes because the tree
is clean, not because the gate works - and it stops working silently the day
somebody edits it. Each test below feeds it the violation it exists to catch,
written out rather than taken from a file, so the failure path has run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pin_gate as gate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def lines(*text: str):
    """Workflow lines in the shape the gate's checks consume."""
    return [(Path("fake.yml"), n, line) for n, line in enumerate(text, 1)]


# --- the repo itself ---------------------------------------------------------

def test_this_repo_passes():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "pin_gate.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_library_answer_and_the_command_answer_are_the_same():
    assert gate.main() == 0


# --- rule 3: actions are SHA-pinned ------------------------------------------

def test_a_moving_tag_is_refused():
    """The one that was actually in the repo:
    `pypa/gh-action-pypi-publish@release/v1`, in the only job holding an OIDC
    token, reached at release time on a green main."""
    found = gate.check_uses(lines("      - uses: pypa/gh-action-pypi-publish@release/v1"))
    assert found and "tag" in found[0]


def test_an_immovable_looking_version_tag_is_refused_too():
    """`@v7.0.1` reads as a fixed point and is not one - a tag is a name its
    owner can repoint, and a compromised action repo repoints it."""
    assert gate.check_uses(lines("      - uses: actions/checkout@v7.0.1"))


def test_a_sha_with_no_version_comment_is_refused():
    """Pinned and unreadable. Nothing says what it is pinned to, so nobody can
    tell whether a dependabot bump is a patch or a major."""
    sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
    assert gate.check_uses(lines(f"      - uses: actions/checkout@{sha}"))
    assert gate.check_uses(lines(f"      - uses: actions/checkout@{sha}  # v7.0.1")) == []


# --- rules 1 and 2: nothing unpinned enters a runner -------------------------

def test_an_unpinned_pip_install_is_refused():
    """Both of the repo's real cases."""
    assert gate.check_pip_installs(lines("      - run: pip install ruff"))
    assert gate.check_pip_installs(lines("      - run: pip install -e . pytest"))


def test_the_editable_install_alone_is_fine():
    """`-e .` is this repo, at this commit. It is the one install that cannot
    resolve to something the commit does not contain."""
    assert gate.check_pip_installs(lines("      - run: pip install -e .")) == []


def test_a_pin_written_inline_is_refused_as_well():
    """Pinned, and in a place dependabot's pip ecosystem cannot read - so it
    is correct today and nothing will ever tell anyone it went stale. That is
    the second half of #416's complaint and it needs its own refusal."""
    found = gate.check_pip_installs(lines("      - run: pip install ruff==0.16.3"))
    assert found and "requirements file" in found[0]


def test_a_new_tool_is_caught_without_anybody_listing_it():
    """The gate is an allowlist of SHAPES, not a denylist of package names.
    `ruff` and `pytest` got here because nothing was watching for them by
    name, so a name-based gate would let the next one through identically."""
    assert gate.check_pip_installs(lines("      - run: pip install some-tool-nobody-has-heard-of"))


def test_an_unpinned_line_inside_a_requirements_file_is_refused(tmp_path, monkeypatch):
    """Installing from a file proves nothing if the file floats."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    (tmp_path / "requirements-x.txt").write_text(
        "# a comment\nruff==0.16.3\npytest\n", encoding="utf-8")
    found = gate.check_pip_installs(lines("      - run: pip install -r requirements-x.txt"))
    assert found and "requirements-x.txt:3" in found[0]


def test_a_requirements_file_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    assert gate.check_pip_installs(lines("      - run: pip install -r nope.txt"))


# --- rules 4 and 5: runtimes and runners -------------------------------------

def test_a_floating_node_version_is_refused():
    assert gate.check_runtime_versions(lines("          node-version: 22"))
    assert gate.check_runtime_versions(lines("          node-version: 22.23.2")) == []


def test_an_unregistered_runner_is_refused():
    """`ubuntu-22.04` - a dated label GitHub retires on its own schedule, in
    the one workflow that had no pull-request trigger, so its retirement would
    have surfaced as a failed deploy on main."""
    found = gate.check_runtime_versions(lines("    runs-on: ubuntu-22.04"))
    assert found and "ubuntu-22.04" in found[0]
    assert gate.check_runtime_versions(lines("    runs-on: ubuntu-latest")) == []


def test_a_matrix_runner_is_read_too():
    """`runs-on: ${{ matrix.os }}` names no label; the labels are in the
    matrix, and reading only the `runs-on:` line would see none of them."""
    assert gate.check_runtime_versions(lines("        os: [ubuntu-latest, ubuntu-20.04]"))
    assert gate.check_runtime_versions(
        lines("        os: [ubuntu-latest, windows-latest]")) == []


def test_every_registered_runner_states_a_reason():
    """A registry entry with an empty reason is a label somebody wanted to
    stop hearing about."""
    thin = sorted(k for k, v in gate.RUNNERS.items() if len(v.strip()) < 40)
    assert not thin, thin


# --- rule 6: the orphan derived artifact ------------------------------------

def test_a_stale_uv_lock_is_refused(tmp_path, monkeypatch):
    """Nothing in this repo reads `uv.lock` and nothing re-derives it, so it
    cannot go red - only quietly wrong, at the next version bump. This is the
    one comparison that can fail."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        'version = "0.6.0"\nrequires-python = ">=3.11"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        'requires-python = ">=3.11"\n\n[[package]]\n'
        'name = "vitai"\nversion = "0.5.0"\n', encoding="utf-8")
    found = gate.check_uv_lock()
    assert found and "0.5.0" in found[0] and "0.6.0" in found[0]


def test_a_matching_uv_lock_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        'version = "0.5.0"\nrequires-python = ">=3.11"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        'requires-python = ">=3.11"\n\n[[package]]\n'
        'name = "vitai"\nversion = "0.5.0"\n', encoding="utf-8")
    assert gate.check_uv_lock() == []


# --- rules 7 and 8: the local check is the point ----------------------------

def test_a_contributing_that_documents_an_unpinned_install_is_refused(tmp_path, monkeypatch):
    """The shape CONTRIBUTING.md actually had. A pin that CI holds and a
    developer does not is a lint nobody can reproduce before pushing."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    (tmp_path / "CONTRIBUTING.md").write_text(
        "```bash\npip install -e . pytest ruff\n```\n", encoding="utf-8")
    found = gate.check_contributing()
    assert found
    assert any("pytest, ruff" in p for p in found), found


def test_a_gate_no_document_names_is_refused(tmp_path, monkeypatch):
    """A gate wired into CI and into no pre-push document can only fail after
    a push - #389's whole argument, one layer up."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "WORKFLOWS", tmp_path / "wf")
    (tmp_path / "wf").mkdir()
    (tmp_path / "wf" / "ci.yml").write_text(
        "      - run: python scripts/example_gate.py\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "example_gate.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example_gate.py").write_text(
        "import example_gate\n", encoding="utf-8")
    found = gate.check_gates_are_runnable_locally()
    assert found and "no pre-push document names it" in found[0]


def test_a_gate_no_test_exercises_is_refused(tmp_path, monkeypatch):
    """`changelog_gate.py` was exactly this: wired into CI, tested by nothing,
    so `pytest -q` was green whether it passed or not."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "WORKFLOWS", tmp_path / "wf")
    (tmp_path / "wf").mkdir()
    (tmp_path / "wf" / "ci.yml").write_text(
        "      - run: python scripts/example_gate.py\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "example_gate.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "RELEASING.md").write_text(
        "python scripts/example_gate.py\n", encoding="utf-8")
    found = gate.check_gates_are_runnable_locally()
    assert found and "run by CI and by no test" in found[0]


def test_a_gate_ci_never_runs_is_refused(tmp_path, monkeypatch):
    """The other direction, and the one #418 is about: a check that exists and
    is dispatched by nothing."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "WORKFLOWS", tmp_path / "wf")
    (tmp_path / "wf").mkdir()
    (tmp_path / "wf" / "ci.yml").write_text("jobs:\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "example_gate.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    found = gate.check_gates_are_runnable_locally()
    assert any("never runs it" in p for p in found), found


def test_a_narrower_documented_lint_is_refused(tmp_path, monkeypatch):
    """Three documents said `ruff check src tests` while CI ran `ruff check .`
    - so a clean local lint said something true about two directories and was
    read as a fact about the repo, which is the misreading widening the CI
    scope was meant to end."""
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "WORKFLOWS", tmp_path / "wf")
    (tmp_path / "wf").mkdir()
    (tmp_path / "wf" / "ci.yml").write_text(
        "      - run: ruff check .\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "RELEASING.md").write_text(
        "```bash\nruff check src tests\n```\n", encoding="utf-8")
    found = gate.check_gates_are_runnable_locally()
    assert found and "ruff check src tests" in found[0]


# --- what it deliberately does not do ---------------------------------------

def test_it_never_asserts_a_pin_is_CURRENT():
    """`contract_literal_gate.py` declines the same thing and says why: a
    check that a version is the latest passes today and fails tomorrow with no
    commit, which is the exact defect this gate exists to remove. Read as
    source, because the absence of a behaviour cannot be called."""
    text = (ROOT / "scripts" / "pin_gate.py").read_text(encoding="utf-8")
    assert "does not check that a pin is CURRENT" in text.replace("**", "")
    for forbidden in ("urllib.request", "urlopen", "requests.", "socket."):
        assert forbidden not in text, (
            f"the pin gate reaches for {forbidden} - a gate that asks the "
            "network what the latest version is has an answer that changes "
            "with no commit, which is what it exists to refuse")
