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


# ---- #379: a category is a diagnosis in one word --------------------------------------

@pytest.mark.parametrize("line", [
    "Your BMI entered the healthy range.",
    "You are in the overweight band.",
    "This reading is in the obese category.",
    "That result sits in the underweight range.",
    "Your latest reading suggests you are morbidly obese.",
    "Your BMI is now in the healthy weight range.",
    # "ideal weight" moved to `CATEGORY_WORDS_GENERIC` (see the proximity
    # tests below), so this needs the BMI it would have in a real report -
    # bare "ideal weight" with nothing beside it no longer fires, and
    # should not: see test_a_generic_phrase_needs_a_body_composition_noun.
    "This value falls in the ideal weight zone for your BMI.",
    "Your systolic reading is hypertensive.",
    "This value is in the prehypertension range.",
])
def test_a_category_word_is_caught(line):
    """#370 decided the engine may state the ratio and the numeric boundary
    but may never name the band - "you have entered the healthy band" is
    class (c), a category applied to a person as the engine's own conclusion.
    None of these contain a purpose verb or a `MEDICAL_NOUN`, so they were
    invisible to the gate before #379."""
    found = scan(line)
    assert found and found[0].startswith("category claim"), line


@pytest.mark.parametrize("line", [
    # PR #382's review: `_match_form` turns a hyphen into a space, which is
    # right for a multi-word phrase already on the list ("healthy-range")
    # but wrong for these three fused compounds - there is no space-
    # separated form of any of them anywhere in `CATEGORY_WORDS`, so the
    # hyphenated spelling used to pass clean. Both spellings of all three
    # words are checked here, not just the hyphenated one, so a regression
    # that broke the plain spelling instead would still be caught.
    "the athlete is in an over-weight band",
    "the athlete is in an overweight band",
    "that result sits in an under-weight range",
    "that result sits in an underweight range",
    # "pre-hypertension" is the more common clinical spelling than the fused
    # form this gate already caught - both must fire.
    "this reads as pre-hypertension",
    "this reads as prehypertension",
])
def test_a_hyphenated_compound_is_the_same_category_word(line):
    found = scan(line)
    assert found and found[0].startswith("category claim"), line


@pytest.mark.parametrize("line", [
    # PR #382's review, run and confirmed firing before this fix: none of
    # these three names a person's reading, and none has a body-composition
    # noun within the sentence.
    "A barbell's ideal weight for this lift is 60kg per the programming doc.",
    "returns True when the argument is in a healthy range of floating "
    "point precision",
    "The exporter writes a normal range column into the CSV.",
])
def test_a_generic_phrase_with_no_body_composition_noun_is_left_alone(line):
    """`ideal weight`, `healthy range` and `normal range` are ordinary
    technical idioms outside this domain, unlike the five unambiguous
    clinical words that stay bare. Scoped to a nearby body-composition
    noun the way `_PURPOSE_RE` scopes `PURPOSE_VERB` to `MEDICAL_NOUN`."""
    assert scan(line) == [], line


@pytest.mark.parametrize("line", [
    # The motivating example must survive the scoping fix: "BMI" is within
    # 80 characters of "healthy range" here, on the noun-then-phrase side.
    "Your BMI entered the healthy range.",
    # Phrase-then-noun must also fire - a real sentence could name the
    # measurand after the band as easily as before it.
    "The healthy range for your BMI is wide.",
    "Your weight is now in the normal range for your height.",
    "The ideal weight for your body fat percentage is unchanged.",
])
def test_a_generic_phrase_needs_a_body_composition_noun(line):
    found = scan(line)
    assert found and found[0].startswith("category claim"), line


@pytest.mark.parametrize("line", [
    # PR #382's review: `_MARKUP_RE` strips `_` as a markdown emphasis
    # marker, which turns a code identifier into three separate words -
    # exactly the shape the new bare CATEGORY family made exploitable, and
    # exactly the shape #370's BMI band field will plausibly introduce.
    "`is_overweight_flag`",
    "The schema adds a `is_overweight_flag` column.",
    "`healthy_range_min`",
    "The config exposes `healthy_range_min` and `healthy_range_max`.",
    "`ideal_weight_kg`",
    "The report renders `ideal_weight_kg` next to the athlete's own value.",
])
def test_an_identifier_is_not_prose(line):
    """An identifier is not prose: `\\b` must not land inside
    `is_overweight_flag` just because it would land inside "is overweight
    flag". Preserving `_` as a word character for CATEGORY matching only
    (see `_MARKUP_RE_TIGHT`) is what stops it."""
    assert scan(line) == [], line


def test_underscore_emphasis_still_reaches_directives_and_purpose():
    """The identifier fix is scoped to CATEGORY only (see `_MARKUP_RE_TIGHT`
    and `_tight_sentences()`): DIRECTIVES and PURPOSE_RE still read the
    prose form, where `_` folds away like every other emphasis marker, so
    `_see a doctor_` and `_detects_ a medical condition` still evade
    nothing."""
    assert scan("If it persists, _see a doctor_ about it.")
    assert scan("vitai _detects_ the medical condition early.")


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


@pytest.mark.parametrize("line", [
    # docs/prior-art-schemas.md, describing OSS project health, not a person.
    "Open Food Facts is alive and healthy.",
    "OSRM, Valhalla and GraphHopper are all healthy.",
    "This plus a healthy vendor ecosystem.",
    # src/vitai/safety.py's own RHR comment - "healthy" and "normal" describe
    # a population and an athlete's physiology respectively, not a category
    # word from the deny list.
    "Resting heart rate outside this band is outside the range of a healthy "
    "person at rest.",
    "Mid-30s is normal for a trained endurance athlete and must not fire.",
    # docs/medical-boundary.md's own worked (a) example: the SAME two words
    # as `healthy range`, but in the opposite order, which is exactly the
    # collocation the deny list must not fire on out of order.
    "Your recorded resting heart rate is outside the range seen in healthy "
    "people at rest.",
    # docs/model.md and skills/vitai-coach/SKILL.md: "normal" as an ordinary
    # adjective for a day, a route, or a mode - not a clinical band.
    "Two goals may share a metric, or be pursued differently, and that is "
    "normal.",
    "Vacation and a deadline week are not normal weeks.",
    # docs/plan-v3.md and skills/vitai-validate/SKILL.md: "obesity" naming a
    # persona-construction test axis, not the engine's own conclusion about a
    # reading. This is why `obesity` (unlike `obese`) is not on the deny
    # list - see the rejection comment beside `CATEGORY_WORDS`.
    "Deliberately span the axes the author does not occupy: shift work, "
    "life-stage physiology, severe obesity, elite performance.",
    "Body composition spectrum: elite and lean through to severe obesity.",
])
def test_ordinary_healthy_and_normal_are_left_alone(line):
    """"healthy" and "normal" are ordinary English, and this codebase's own
    prose uses them constantly for OSS projects, routes, weeks and
    physiology. Only the specific two-word collocations on the deny list
    (`healthy range`, `healthy weight`, `normal range`) are narrow enough to
    survive a scan of the whole repo; bare `healthy` or `normal` is not, and
    `obesity` bare is not either, because of the two "severe obesity"
    sentences quoted above."""
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


def test_the_brand_document_is_scanned():
    """Marketing copy is the most purpose-asserting prose a project writes,
    and it was outside the surface while README.md was inside it."""
    scanned = {p.relative_to(ROOT).as_posix() for p in gate.files()}
    assert "assets/BRAND.md" in scanned


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


# ---- #112 / #113 / #114: what the surface rewrite removed, locked in --------
#
# Every string below was live on the public surface and passed this gate. A
# rewrite that is not also a rule is a rewrite somebody undoes.

def test_a_hyphenated_directive_is_the_same_directive():
    """`vitai init` stamped "stop-and-see-a-clinician" into every content
    repo and the gate never saw it: each phrase was written with spaces, so
    hyphenating one evaded all of them. Punctuation is not a boundary."""
    assert scan("Red-flag symptoms that mean stop-and-see-a-clinician.")


def test_hyphen_folding_does_not_move_the_exemption_digests():
    """Matching folds hyphens; HASHING must not, or an exemption recorded
    against a hyphenated sentence stops matching it and CI fails on a
    sentence somebody deliberately spared.

    Through `findings` on purpose. Recomputing the digest with `_norm` here
    and comparing it to `_norm` there proves only that a function equals
    itself: fold the hyphens on the hashing path too and that comparison
    stays green while every hyphenated exemption lapses.
    """
    import hashlib
    text = "Red-flag symptoms that mean stop-and-see-a-clinician."
    assert scan(text), "premise: this is a directive the gate catches"
    digest = hashlib.sha256(gate._norm(text).encode()).hexdigest()
    assert not gate.findings(Path("x.md"), text, {digest})


def test_no_exemption_outlives_the_sentence_it_spares():
    """A hash with nothing behind it is an exemption nobody can review: the
    reason beside it describes a sentence that is no longer in the file."""
    import hashlib
    for (path, digest) in gate.EXEMPT:
        live = {hashlib.sha256(gate._norm(s).encode()).hexdigest()
                for s in gate.sentences(
                    (gate.ROOT / path).read_text(encoding="utf-8"))}
        assert digest in live, f"{path}: no live sentence hashes to {digest}"


def test_an_addressee_with_no_profession_is_still_an_addressee():
    """The wiki's consumer contract told every integrator that the tables
    "route to a human and stop". It read as safe because it named nobody."""
    assert scan("Neither table is advisory - they route to a human "
                    "and stop.")


def test_a_duty_to_watch_for_a_named_syndrome_is_a_purpose_claim():
    """ARCHITECTURE.md's principle 7 claimed "a duty to watch
    deterministically for what its own coaching can cause (RED-S / low
    energy availability)" - a self-assigned duty to notice a medical
    syndrome, which is the classic sentence by which a wellness tool argues
    itself into being a device. None of the clinical-sounding verbs were in
    it, and neither was any of the generic medical nouns."""
    assert scan("A tool that coaches calorie deficits owes a duty to "
                    "watch deterministically for what its own coaching can "
                    "cause (RED-S / low energy availability).")


def test_ordinary_watching_is_not_a_purpose_claim():
    """`watch ... for` is an engineering verb and `injury` is core vocabulary
    here, so pairing them by proximity fired on sentences a test docstring
    writes. An adverb may sit between the verb and `for`; a noun phrase may
    not, and the object must be a named condition."""
    assert not scan("Reviewers should watch for regressions in the injury "
                    "parser.")
    assert not scan("The CI job watches the fixtures for drift in the "
                    "injuries table.")


def test_a_human_in_the_loop_is_not_a_care_destination():
    """"Unreviewed PRs route to a human reviewer" is the stock phrase of
    every process document and has nothing to do with care."""
    assert not scan("Escalations in CI route to a human reviewer before "
                    "merge.")
    assert scan("They route to a human and stop."), "premise"


def test_the_engine_may_still_say_it_does_not_watch_for_anything():
    """The disclaiming form must survive the new verb, or the doctrine
    cannot state its own rule."""
    assert not scan("The module never claims to watch for a syndrome.")
