"""The medical-boundary lint (#117).

A boundary that lives only in a document regresses the first time somebody
writes a helpful string. This is the mechanical complement to
`docs/medical-boundary.md` and to #110's module-wide check.

The tests here are mostly about the lint NOT crying wolf. A lint that fires on
prose explaining the rule, or on ordinary engineering words, gets deleted -
and a deleted lint catches nothing at all, so a false positive costs more here
than a missed string.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import boundary_gate as gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def scan(text: str) -> list[str]:
    return gate.findings(Path("x.md"), text, gate.allowed())


# ---- it catches what it is for -------------------------------------------------------

@pytest.mark.parametrize("line", [
    "If this keeps happening, see a doctor.",
    "Contact a clinician before your next session.",
    "You should get assessed before training again.",
    "Take this record to a physician.",
    "Book an appointment about this.",
    "This needs a clinician.",
    "The engine routes to a clinician and stops.",
])
def test_a_care_directive_is_caught(line):
    found = scan(line)
    assert found and found[0].startswith("care directive"), line


@pytest.mark.parametrize("line", [
    "vitai detects the medical condition early.",
    "vitai identifies medical conditions early.",
    "The engine screens for a deficiency.",
    "It monitors for arrhythmia.",
])
def test_a_purpose_claim_is_caught(line):
    found = scan(line)
    assert found and found[0].startswith("purpose claim"), line


def test_the_finding_names_the_sentence_so_it_can_be_found():
    found = scan("Some prose. If it persists, see a doctor about it. More.")
    assert "see a doctor" in found[0]


# ---- it does not cry wolf ---------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "vitai does not diagnose, treat or advise on any condition.",
    "It never tells you to see a doctor.",
    "Nothing here routes to a clinician.",
    "This is not a claim that the engine detects a disease.",
    "No plan is issued, and the record does not need a clinician to say so.",
])
def test_a_disclaimer_is_not_a_claim(line):
    """The boundary documents are full of these, so matching them would make
    the lint loudest exactly where the doctrine is stated - which is how a
    lint gets deleted."""
    assert scan(line) == [], line


@pytest.mark.parametrize("line", [
    "The parser detects a duplicate row.",
    "`verify` detects a corrupted artifact.",
    "The gate monitors for schema drift.",
    "This screens for malformed dates before the build runs.",
])
def test_ordinary_engineering_words_are_left_alone(line):
    """`detect`, `screen` and `monitor` are everyday words here. They count
    only next to a medical noun, or the lint fires on half the codebase."""
    assert scan(line) == [], line


def test_the_acute_tier_is_exempt_by_value_not_by_file():
    """Sparing `safety.py` would spare whatever is written into it next, so
    the carve-out reads `safety.ACUTE` directly.

    The earlier version of this test asserted only that the acute strings
    pass, which they did WITHOUT the exemption - no pattern happened to match
    them - so deleting the whole carve-out left it green. It now checks the
    exemption is doing work: a sentence that WOULD be caught is spared
    because it is in the acute tier, and stops being spared when it is not.
    """
    import hashlib

    from vitai.safety import ACUTE
    spared = gate.allowed()
    caught = "Contact a doctor today about this."
    assert gate.findings(Path("x.md"), caught, spared), "premise"

    # The same sentence, exempt purely because it is an acute-tier sentence.
    exempt_hashes = {hashlib.sha256(gate._norm(s).encode()).hexdigest()
                     for text in ACUTE.values() for s in gate.sentences(text)}
    assert gate.findings(Path("x.md"), caught,
                         spared | {hashlib.sha256(
                             gate._norm(caught).encode()).hexdigest()}) == []
    assert exempt_hashes <= spared, (
        "the acute tier's sentences are not in the allowlist - the carve-out "
        "hashes a different unit from the one `findings` compares")
    for text in ACUTE.values():
        assert gate.findings(Path("x.md"), text, spared) == [], text


def test_every_exemption_records_why_and_where():
    """An exemption whose justification is not written down is
    indistinguishable from an oversight - and one keyed only by hash could be
    pasted into another file and inherit the pass."""
    assert gate.EXEMPT
    for (where, digest), reason in gate.EXEMPT.items():
        assert len(digest) == 64, digest
        assert len(reason) > 20, (where, reason)
        assert (gate.ROOT / where).exists(), where


def test_an_exemption_is_scoped_to_the_file_it_was_granted_for():
    """Copying an exempt sentence somewhere else must not carry the pass with
    it. The exemption is a statement about one place, not about a form of
    words."""
    where, digest = next(iter(gate.EXEMPT))
    text = (gate.ROOT / where).read_text(encoding="utf-8")
    culprit = next(
        s for s in gate.sentences(text)
        if __import__("hashlib").sha256(
            gate._norm(s).encode()).hexdigest() == digest)
    spared = gate.allowed()
    assert gate.findings(Path(where), culprit, spared) == []
    assert gate.findings(Path("README.md"), culprit, spared), (
        "an exempt sentence kept its pass in a different file")


def test_editing_an_exempt_sentence_re_triggers_the_gate():
    """Hashed rather than listed by file, so the exemption cannot silently
    cover whatever replaces it."""
    where, digest = next(iter(gate.EXEMPT))
    text = (gate.ROOT / where).read_text(encoding="utf-8")
    culprit = next(
        s for s in gate.sentences(text)
        if __import__("hashlib").sha256(
            gate._norm(s).encode()).hexdigest() == digest)
    edited = culprit.replace("doctor", "doctor today")
    assert gate.findings(Path(where), edited, gate.allowed()), edited


# ---- the surface ----------------------------------------------------------------------------

def test_the_gate_covers_the_surface_that_matters():
    covered = {p.relative_to(ROOT).parts[0] for p in gate.files()}
    assert {"README.md", "docs", "skills", "src", "wiki"} <= covered


def test_the_templates_are_scanned():
    """`vitai init` stamps them into every athlete's private record, so a
    directive there propagates rather than sitting in one repo."""
    scanned = {p.relative_to(ROOT).as_posix() for p in gate.files()}
    assert any(p.startswith("src/vitai/templates/") for p in scanned)


def test_the_repository_is_clean():
    """The gate that runs in CI, run here too - so a failure names the file
    during development rather than after a push."""
    got = subprocess.run([sys.executable, str(ROOT / "scripts"
                                              / "boundary_gate.py")],
                         capture_output=True, text=True)
    assert got.returncode == 0, got.stdout


def test_the_gate_actually_fails_on_a_violation(tmp_path, monkeypatch):
    """Nothing tested the failure path, so dropping `bad += 1` from `main()`
    would have left the suite green while CI silently stopped gating."""
    bad = tmp_path / "README.md"
    bad.write_text("If it persists, see a doctor about it.\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "SURFACE", ("README.md",))
    assert gate.main() == 1


def test_the_gate_passes_on_a_clean_tree(tmp_path, monkeypatch):
    ok = tmp_path / "README.md"
    ok.write_text("The engine states what it observed and stops.\n",
                  encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "SURFACE", ("README.md",))
    assert gate.main() == 0


def test_a_directive_across_a_hard_wrap_is_caught():
    """The docs here are wrapped at ~80 columns, so splitting sentences on a
    newline hid every directive long enough to straddle one - which is most
    of them."""
    wrapped = ("If the pain keeps coming back, see a\n"
               "doctor before you train again.\n")
    assert scan(wrapped)


def test_a_directive_at_end_of_file_with_no_terminator_is_caught():
    assert scan("If this keeps happening, see a doctor")


def test_markdown_formatting_does_not_evade_the_gate():
    """A lint that can be evaded by emphasis will be, by accident, on the
    first pass of someone tidying a document."""
    for line in ("see a **doctor** about it.",
                 "see a [doctor](https://example.com) about it.",
                 "see a  doctor about it."):
        assert scan(line), line


def test_a_conditional_negative_is_still_a_directive():
    """The commonest real phrasing there is. A negation token anywhere in the
    sentence used to suppress the whole thing, so "if symptoms do not improve,
    see a doctor" - the exact sentence this gate exists for - passed."""
    for line in ("If symptoms do not improve within a week, see a doctor.",
                 "If you cannot bear weight on it, see a doctor immediately.",
                 "Unless it settles, contact your doctor."):
        assert scan(line), line
