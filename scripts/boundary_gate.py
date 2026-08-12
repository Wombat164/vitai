#!/usr/bin/env python3
"""A deterministic medical-boundary lint over the public surface (#117).

`docs/medical-boundary.md` sets out where the line sits, and #110 moved
`safety.py` to the right side of it. This is the mechanical complement,
because a boundary that lives only in a document regresses the first time
somebody writes a helpful string.

The audit that produced the doctrine found roughly twenty violating strings
across seven files. Every one of them would have been caught by the deny list
below at the moment it was written, which is the whole argument for the lint:
the cost of holding the line drops from a review each time to nothing.

## What it looks for

Care DIRECTIVES: phrasing that tells the reader to go and obtain care, or that
claims vitai detects, screens for or monitors a condition. Both are the same
mistake in different grammar - one asserts an instruction the tool cannot help
anyone carry out, and the other asserts a medical purpose. Under FDA general
wellness and MDCG 2019-11 the trigger is the CLAIM, not the technology.

CATEGORY words (#379): a small deny list of clinical banding vocabulary -
`overweight`, `obese`, `healthy range`, and the rest catalogued beside
`CATEGORY_WORDS` below. A category applied to a person IS the class (c)
diagnosis; it needs no purpose verb and no medical noun beside it, which is
why it is its own family rather than an addition to `PURPOSE_VERB`.

## What it deliberately does not do, and this is the load-bearing paragraph

No natural-language understanding, and no attempt to catch condition-naming
mechanically - that is open-ended and stays a review judgement. **Start narrow
and grow.** A lint that cries wolf gets deleted, and a deleted lint catches
nothing at all, so a false positive here costs more than a missed string.

This applies with extra force to `CATEGORY_WORDS`: it is a DENY LIST, not a
definition of class (c). It catches the category words somebody sat down and
thought of - the ones a lookup table would introduce in an afternoon - and
nothing else. `docs/medical-boundary.md` class (c) forbids naming or implying
"a disease, syndrome or diagnosis" in general; this file mechanically enforces
only the slice of that rule which is a word on the list below plus the two
older families above it. A novel category this list did not anticipate - a
regional term, a newly-popular banding scheme, a translated word, a compound
nobody has written yet - passes clean. The SHAPE that would actually close the
gap (a bare adjective applied to the athlete beside a number the engine
published) cannot be expressed as a pattern without also firing on ordinary
prose that applies the same adjectives to a route, a vendor ecosystem, or an
athlete's sleep duration - see the false positives `CATEGORY_WORDS` was
trimmed against, below. So the rest of class (c) is enforced the way it always
was: by a reviewer reading `docs/medical-boundary.md` and this list is a floor
under that, not a replacement for it.

## The allowlist is hashed, not listed

Sparing a FILE would mean the exemption silently covers whatever is written
into it next. Sparing a hashed STRING means an edit re-triggers review, which
is the property the acute tier needs: the same discipline #110's fixture test
applies, so the two guards agree rather than drifting apart.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The public surface. `docs/` is included even though the engine never reads
# it: a claim in a design document is still a claim, and it is the surface a
# regulator or a contributor reads first. `pyproject.toml` is here because its
# `description` renders on PyPI, which is the single most-read sentence the
# project has.
#
# `CHANGELOG.md` is deliberately absent - it is history, and rewriting what a
# release said in order to satisfy a lint written afterwards is falsifying a
# record rather than fixing a claim.
# `assets/` holds the brand document, which is marketing copy and therefore
# the most purpose-asserting prose the project will ever write - the sentence
# a reader meets before any of the engineering. It was outside the surface
# while README.md was inside it, which is the wrong way round.
SURFACE = ("README.md", "SECURITY.md", "ARCHITECTURE.md", "CONTRIBUTING.md",
           "pyproject.toml", "assets", "docs", "wiki", "skills", "src",
           "examples")

SUFFIXES = {".md", ".py", ".toml", ".txt", ".rst", ".yml", ".yaml", ".json"}

# Phrases that tell the reader to go and obtain care.
DIRECTIVES = (
    r"see (?:a|your) (?:doctor|clinician|physician|gp|specialist)",
    r"contact (?:a|your) (?:doctor|clinician|physician|dietitian|specialist|"
    r"prescriber|gp)",
    r"consult (?:a|your) (?:doctor|clinician|physician|professional|"
    r"healthcare\s+professional)",
    r"(?:speak|talk) to (?:a|your) (?:doctor|clinician|physician|gp)",
    r"seek (?:medical|professional) (?:attention|advice|help|care)",
    r"take this (?:record|to) ",
    r"book an appointment",
    r"needs? a clinician",
    r"until a clinician has",
    r"refer(?:ral)? to (?:a|your) (?:doctor|clinician|specialist)",
    r"routes? to a clinician",
    # A destination without a noun. "They route to a human and stop" gives the
    # output an addressee just as plainly as naming the profession does, and
    # it read as safe precisely because it named nobody. The lookahead spares
    # the human-in-the-loop idiom, which is the stock phrase of every process
    # document ("unreviewed PRs route to a human reviewer") and has nothing to
    # do with care.
    r"routes? to a human(?!\s+(?:reviewer|operator|maintainer|in.the.loop))",
    # The `get ...` family needs a care word nearby, or it fires on
    # "timestamps get checked during the build" and the lint gets deleted.
    r"get (?:assessed|checked|looked at|seen)\b[^.!?]{0,60}"
    r"(?:doctor|clinician|physician|medical|professional)",
    r"(?:doctor|clinician|physician|medical|professional)[^.!?]{0,60}"
    r"get (?:assessed|checked|looked at|seen)\b",
    r"get (?:assessed|checked) before",
)

# Phrases claiming a medical PURPOSE. The verbs are ordinary engineering words
# here, so they only count next to a medical noun.
# `flag`, `spot` and `catch` are deliberately NOT here. This codebase says
# "red flag", "at-risk flag" and "the engine catches" constantly, and adding
# them produced findings on a streak-forgiveness table and a hold tier. Start
# narrow: `identifies` was the real gap, and the rest can be added the day a
# string actually needs them.
PURPOSE_VERB = (r"(?:detects?|detecting|identif(?:y|ies)|screens? for|"
                r"screening for|monitors? for|diagnos(?:es|is|ing)|"
                r"predicts?)")

# `watch ... for` is a SEPARATE rule with a narrower object, because it is an
# ordinary engineering verb and the nouns above are ordinary vocabulary here.
# It was grown for the actual form the violation took - ARCHITECTURE.md's "a
# duty to watch deterministically for what its own coaching can cause (RED-S /
# low energy availability)", a self-assigned duty to notice a named syndrome,
# which is the classic sentence by which a wellness tool argues itself into
# being a device and which none of the clinical verbs appeared in.
#
# Folded into PURPOSE_VERB it fired on "watch for regressions in the injury
# parser" and "the CI job watches the fixtures for drift in the injuries
# table". A lint that cries wolf gets deleted, and a deleted lint catches
# nothing at all. So: an adverb may sit between the verb and `for` (that is
# the form the violation used) but a noun phrase may not, and the object must
# be a named CONDITION rather than any medical word - "watch for injuries" is
# something a test docstring says and "watch for a syndrome" is not.
WATCH_VERB = r"watch(?:es|ing)? (?:\w+ly )?for"
CONDITION_NOUN = (r"\b(?:medical conditions?|disease|illness|disorder|"
                  r"syndrome|pathology|arrhythmia|"
                  r"red[- ]s|low energy availability)\b")

# `\b` on BOTH sides, and `precondition`/`conditioning` excluded explicitly.
# `precondition` is a live schema field and `conditioning` is core training
# vocabulary: without this, one ordinary sentence pairing either with a purpose
# verb fails CI, which is precisely how a lint earns its deletion.
# Bare `condition` is NOT here. It matched `precondition` (a live schema
# field), `conditioning` (core training vocabulary) and `race condition`
# (ordinary engineering), and a lint that fires on those is one that gets
# deleted. `medical condition` is explicit and unambiguous, which is the only
# form worth matching.
# `red[- ]s` and `low energy availability` are named because the sentence this
# gate was grown to catch named THEM and none of the generic nouns: "a duty to
# watch deterministically for what its own coaching can cause (RED-S / low
# energy availability)". The generic list would have let the most specific
# claim in the repo through, which is the wrong way round. `red[- ]s` rather
# than `red-s` because hyphens are word spaces by the time a pattern sees a
# sentence - the second branch is belt and braces for any caller that matches
# an unfolded string.
MEDICAL_NOUN = (r"\b(?:medical conditions?|disease|illness|disorder|"
                r"syndrome|pathology|arrhythmia|deficienc(?:y|ies)|"
                r"injur(?:y|ies)|red[- ]s|low energy availability)\b")

# #379 (#370's decided rule made this load-bearing: "the engine may compute
# the ratio and state the boundary as a boundary; it may never name the
# band"). A bare category word IS the class (c) diagnosis - "your BMI entered
# the healthy range", "you are in the overweight band", "this reading is in
# the obese category" - none of them contain a purpose verb or a
# `MEDICAL_NOUN`, so `_PURPOSE_RE` is structurally blind to all three. No
# proximity requirement, unlike `PURPOSE_VERB` + `MEDICAL_NOUN`: the word
# itself is the claim, there is no engineering homograph for "overweight" the
# way "detect" and "condition" have one, so nothing needs to stand next to it.
#
# Every entry here was checked against the whole repo (docs/, wiki/, README,
# skills/, src/, tests/) before being kept - see the rejections immediately
# below the list, which are exactly as load-bearing as the inclusions.
#
# `obese` is deliberately here without `morbidly` in front of it: bare
# `obese` already matches inside `morbidly obese`, so a separate entry would
# be a second pattern for the same match.
#
# Blood pressure and body fat are the same shape as BMI - a number banded
# into a named category - so their vocabulary belongs beside it rather than
# waiting for a #370-shaped issue of their own. Nothing in this codebase
# tracks blood pressure yet, but the vocabulary is ordinary and a contributor
# reaching for it will reach for exactly these words.
CATEGORY_WORDS = (
    r"overweight",
    r"underweight",
    r"obese",
    r"healthy weight",
    r"healthy range",
    r"normal range",
    r"ideal weight",
    r"hypertensive",
    r"prehypertension",
)

# `obesity` is NOT in `CATEGORY_WORDS`, and this is a rejection on the same
# footing as the inclusions above, not an oversight. It fires on legitimate
# prose in two places on the public surface today: `docs/plan-v3.md`'s and
# `skills/vitai-validate/SKILL.md`'s persona-construction methodology, both
# listing "severe obesity" as an axis a validation persona should span - a
# design document describing a TEST AXIS, not the engine concluding a
# diagnosis about a reading. Tightening the pattern to require a labelling
# word nearby (`category`, `range`, `band`) would dodge those two sentences,
# but it would also be exactly the proximity machinery this family exists to
# avoid needing, for one word, on the strength of two hits - the same
# trade-off that kept `flag`, `spot` and `catch` out of `PURPOSE_VERB` above.
# `obese` stays on the list and catches the adjective form; the noun form
# waits for a real violation to justify the added machinery.
#
# Bare `healthy` and `normal` are NOT here, and could not be: this codebase's
# own prose calls a well-maintained OSS project "healthy", a route "normal",
# and mid-30s resting heart rate "normal for a trained endurance athlete"
# constantly (`docs/prior-art-schemas.md`, `docs/model.md`, `src/vitai/safety.py`).
# Either word alone would fire dozens of times across the surface on its first
# run, which is precisely the "cries wolf" failure mode this file's own
# doctrine warns gets a lint deleted. Only the two-word collocations above -
# `healthy weight`, `healthy range`, `normal range` - are specific enough to
# survive that check, and both were confirmed absent from the repo's existing
# prose before being added.

# HYPHENS ARE WORD SPACES for matching. `stop-and-see-a-clinician` is the same
# claim as `stop and see a clinician`, and every phrase above was blind to it -
# the template that `vitai init` copies into every content repo carried the
# hyphenated form and passed. Length-preserving on purpose, so a match offset
# still indexes the original sentence; and matching-only, so the digests the
# exemptions are keyed on do not move.
def _match_form(sentence: str) -> str:
    return sentence.replace("-", " ")


_DIRECTIVE_RE = re.compile("|".join(DIRECTIVES), re.I)
_PURPOSE_RE = re.compile(
    rf"(?:{PURPOSE_VERB}[^.!?]{{0,80}}{MEDICAL_NOUN})"
    rf"|(?:{WATCH_VERB}[^.!?]{{0,80}}{CONDITION_NOUN})", re.I)
_CATEGORY_RE = re.compile(r"\b(?:" + "|".join(CATEGORY_WORDS) + r")\b", re.I)

# Sentences, across hard line wraps. The docs here are wrapped at ~80 columns,
# so splitting on a newline hid every directive long enough to straddle one -
# which is most of them. Paragraph breaks still end a sentence, since a blank
# line is a real boundary and joining across one invents adjacency.
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]|$)")

# Markdown formatting must not break a phrase: `see a **doctor**` is the same
# claim as `see a doctor`, and a lint that can be evaded by emphasis is one
# that will be, by accident, on the first pass of someone tidying a document.
_MARKUP_RE = re.compile(r"[*_`]+|\[|\]\([^)]*\)")

# NEGATION IS CLAUSE-SCOPED, the same discipline `safety.py` applies to prose
# symptoms - and for the same reason. A token anywhere in the sentence
# suppressed "If symptoms do not improve within a week, see a doctor", which
# is the single commonest real phrasing of the thing this gate exists to
# catch. Only a negation in the SAME clause, and before the phrase, disclaims
# it.
_NEGATIONS = ("not", "never", "nothing", "nobody", "without", "cannot",
              "refuses", "refuse", "declines", "decline", "no")
_CLAUSE_BREAK_RE = re.compile(r"[,;:]|\b(?:if|when|unless|but|however|"
                              r"otherwise|should)\b", re.I)


def _disclaimed(sentence: str, at: int) -> bool:
    """Is the phrase at `at` inside a clause that negates it?"""
    lead = sentence[:at]
    breaks = [m.end() for m in _CLAUSE_BREAK_RE.finditer(lead)]
    clause = lead[breaks[-1]:] if breaks else lead
    words = re.findall(r"[a-z']+", clause.lower())
    return any(w in _NEGATIONS for w in words)


# Sentences deliberately exempt, keyed by (file, hash of the sentence).
#
# Hashed so an EDIT re-triggers review rather than the exemption silently
# covering whatever replaces it. Keyed BY FILE as well, so an exempt sentence
# cannot be pasted somewhere else and inherit the pass - the exemption is a
# statement about one place, not about a form of words.
#
# The reason is recorded beside each, because an exemption whose justification
# is not written down is indistinguishable from an oversight.
EXEMPT: dict[tuple[str, str], str] = {
    # --- PERMANENT: the doctrine cannot be written without quoting the rule.
    # Exactly the shape that tripped safety.py's own comments and #80's
    # transmit check - prose explaining a constraint trips the constraint.
    ("docs/medical-boundary.md",
     "91585901e9213dd3c808f7943c46963439b835bcdf6b390d89363eaacd010226"):
        "the doctrine naming the defect it exists to prevent",
    ("docs/medical-boundary.md",
     "bfeb82262b7ca9108b2a24c3c3851e21b8cc9b6f01643ca1014b16ba6c5d8967"):
        "the doctrine quoting the removed phrasings as examples",
    ("docs/medical-boundary.md",
     "88bda657dc35a6b7cc9775996858fb587fc480989917cb08f9a60824ff665620"):
        "the doctrine defining the capability-claim class",
    ("docs/medical-boundary.md",
     "3c253765cab65ea46a81d341ad2e16d107052375c4081fd469a084d40c11b497"):
        "the doctrine quoting the watch-for-a-syndrome claim it forbids",
    ("docs/medical-boundary.md",
     "38e2021bcc1c802e562a6ae14a7cee6f0811503a8f4a745d2415beb1bf043b05"):
        "the doctrine's worked rewrite pair, quoting the non-compliant form",

    # The pre-#110 routing debt that used to sit here is GONE, cleared by
    # #116 rather than re-pointed: five sentences across four documents were
    # exempted because they described a clinician-review exit that #110 had
    # already removed, which made them false as well as over the line. They
    # are reworded now, so there is nothing left to spare.
}


def allowed() -> set[str]:
    """Hashes of the strings that are deliberately exempt.

    Built from the CODE rather than transcribed, so the acute tier cannot
    drift out of the exemption: `safety.ACUTE` is the carve-out #110 defines,
    and this reads the same object rather than a copy of it.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from vitai.safety import ACUTE, DISCLAIMER

    out: set[str] = set()
    for text in set(ACUTE.values()) | {DISCLAIMER}:
        # Per SENTENCE, because that is the unit `findings` compares. Hashing
        # the whole multi-sentence value produced a digest that could never
        # match anything, so the acute carve-out was dead code and the "the
        # two guards cannot drift" property did not exist.
        for sentence in sentences(text):
            out.add(hashlib.sha256(_norm(sentence).encode()).hexdigest())
    return out


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def files() -> list[Path]:
    out: list[Path] = []
    for entry in SURFACE:
        path = ROOT / entry
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out += [p for p in sorted(path.rglob("*"))
                    if p.is_file() and p.suffix in SUFFIXES]
    return out


def sentences(text: str) -> list[str]:
    """Sentences, with markdown stripped and hard wraps joined.

    Paragraph by paragraph: a blank line is a real boundary, and joining
    across one would invent adjacency between two unrelated statements.
    """
    out = []
    for para in re.split(r"\n\s*\n", text):
        joined = " ".join(_MARKUP_RE.sub(" ", para).split())
        out += [s.strip() for s in _SENTENCE_RE.findall(joined) if s.strip()]
    return out


def findings(path: Path, text: str, spared: set[str]) -> list[str]:
    """Every care directive, purpose claim, or category claim in this file."""
    out = []
    here = path.as_posix()
    for sentence in sentences(text):
        digest = hashlib.sha256(_norm(sentence).encode()).hexdigest()
        if digest in spared or (here, digest) in EXEMPT:
            continue
        probe = _match_form(sentence)
        for label, pattern in (("care directive", _DIRECTIVE_RE),
                               ("purpose claim", _PURPOSE_RE),
                               ("category claim", _CATEGORY_RE)):
            hit = pattern.search(probe)
            if hit and not _disclaimed(probe, hit.start()):
                out.append(f"{label}: {' '.join(sentence.split())[:80]}")
                break
    return out


def main() -> int:
    spared = allowed()
    bad = 0
    for path in files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for problem in findings(path.relative_to(ROOT), text, spared):
            print(f"BOUNDARY GATE: {path.relative_to(ROOT)}: {problem}")
            bad += 1
    if bad:
        print(f"FAILED: {bad} finding(s).\n"
              "vitai states what it observed and what it will therefore not "
              "do. It does not tell the reader to obtain care, it does not "
              "claim to detect, screen for or monitor a condition, and it "
              "does not name the category a reading falls into.\n"
              "See docs/medical-boundary.md. If a string is genuinely part "
              "of the acute tier, it belongs in safety.ACUTE, which this "
              "gate reads directly.")
        return 1
    print("boundary gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
