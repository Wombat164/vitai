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
`overweight`, `obese`, and the rest catalogued beside `CATEGORY_WORDS` below.
A category applied to a person IS the class (c) diagnosis, which is why it is
its own family rather than an addition to `PURPOSE_VERB`. Most of the list
needs no purpose verb and no medical noun beside it - the word itself is the
claim. Three phrases (`CATEGORY_WORDS_GENERIC`) are ordinary technical idioms
outside this domain and only count near a body-composition noun, the same
proximity trade `PURPOSE_VERB` makes with `MEDICAL_NOUN`. A hyphenated or
`snake_case` spelling of any of them is still caught - see the comments above
`_match_form` and `_MARKUP_RE_TIGHT`.

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

import ast
import hashlib
import io
import re
import sys
import tokenize
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
# EVERYTHING, MINUS WHAT IS NAMED (#440). This was an allowlist of places to
# LOOK - README, docs, wiki, skills, src, examples - and every directory added
# to the repo was outside the gate until somebody remembered. `tests/` was the
# one that bit (#388): the repo is public, so a class (c) claim there is as
# published as one in `src/`, and nothing looked at it for the life of the
# project.
#
# Measured before inverting: 67 tracked files with a scannable suffix were
# outside, in `changelog.d/` (45), `.github/` (8), `scripts/` (7),
# `CHANGELOG.md`, `CLAUDE.md`, `CODE_OF_CONDUCT.md`, `RELEASING.md`,
# `connectors/` and the requirements files. All of them published.
#
# So the default is now IN, and staying out is a decision with a reason beside
# it - the shape `test_fixture_coverage.py`'s register uses, and the one an
# allowlist cannot have: a list of places to look says nothing about the place
# nobody thought of.
#
# WHAT IS NAMED HERE IS NOT PROSE, and that is the whole test for belonging.
# Third-party code, build output and generated metadata are not this project
# speaking - and one of them, the derived demo, would make the gate's answer
# depend on whether somebody had run a build, which is worse than not scanning
# it.
NOT_SCANNED: dict[str, str] = {
    ".git":
        "the object store: not source, and full of every string this repo has "
        "ever held including the ones it removed",
    ".venv":
        "third-party code. House style is a rule about what we write, the same "
        "line `vendor/` draws in the lens - and a library's docstrings are not "
        "this project's claims",
    "__pycache__":
        "compiled output of files this gate already reads",
    ".pytest_cache":
        "test-runner state, regenerated on every run",
    ".ruff_cache":
        "linter state, regenerated on every run",
    "src/vitai.egg-info":
        "packaging metadata generated by `pip install -e .`, and absent from a "
        "fresh clone - a gate whose file list depends on whether somebody has "
        "installed the package answers differently on two machines",
    "examples/demo/derived":
        "built by `vitai build` and not committed. Scanning it would make this "
        "gate's answer depend on whether a build had been run; the generator "
        "that writes it is scanned instead, which is where a claim would be "
        "authored",
}

# The gate does not read its own source, and this is a RULE rather than an
# entry above, because it is not a decision anybody may extend. This file IS
# the deny list: `CATEGORY_WORDS`, `DIRECTIVES` and the doctrine explaining
# each. Measured: scanned whole it reports 23 findings, and 20 of them survive
# #388's use/mention split, because the explanations are comments rather than
# literals. Twenty per-sentence exemptions transcribing this file's own deny
# list would not be review, and they would need rewriting every time the list
# moved.
#
# Its TESTS are a different matter and are not spared: `tests/test_boundary_gate.py`
# carries fourteen per-sentence entries in `EXEMPT` below, each naming what it
# quotes. The file that defines the words is exempt; the file that proves they
# work is reviewed sentence by sentence.
_SELF = Path(__file__).resolve()

# Roots where a Python STRING LITERAL is material rather than something the
# product says (#388).
#
# THE REPO IS PUBLIC, so a class (c) claim in `tests/` is exactly as published
# as one in `src/` - and `tests/` was outside `SURFACE` until now. #387 wrote
# one: a generator comment explaining a persona selection by saying two named
# personas "never leave the obese band at any recorded weight", inside the
# change that forbade doing so, with the compliant wording already in use
# elsewhere in the same diff. Prose drifting where nothing checks it.
#
# ADDING `tests` ALONE PRODUCES 62 FINDINGS, and nearly all are the controls'
# own material: `test_boundary_gate.py` MUST contain "see a doctor" to prove
# the directive family fires, `test_crossings.py`'s deny list must contain the
# category word it scans for, `test_safety.py` must quote the acute tier it
# pins. A gate that fires on the tests proving it works is worse than no gate,
# because the first thing anyone does is exempt the directory - and then it is
# exempt forever.
#
# SO THE SPLIT IS USE VERSUS MENTION, AND IT IS STRUCTURAL. In a test, a
# forbidden phrase inside a string literal is the INPUT the test exists to
# check; the same phrase in a comment or a docstring is the file talking in its
# own voice. That is the difference between quoting a violation and asserting
# one, and Python's own grammar draws it. 62 findings become 12.
#
# DOCSTRINGS ARE VOICE, NOT DATA, even though the parser calls them string
# literals. A docstring is prose addressed to a reader, which is exactly what
# `tests/` was missing a check on.
#
# `src` AND `examples` ARE NOT HERE, deliberately and load-bearingly. A string
# literal there is what the product SAYS - `safety.ACUTE`'s messages are string
# literals, and they are the single most important thing this gate reads.
# Applying the split to them would switch the gate off where it matters most.
TEST_MATERIAL = ("tests",)

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
# `MEDICAL_NOUN`, so `_PURPOSE_RE` is structurally blind to all three.
#
# Split into two tiers, not one flat list, because PR #382's review ran the
# original flat list against real sentences and two of them are ordinary
# technical idioms rather than clinical vocabulary:
#
#   CATEGORY_WORDS: no proximity requirement. The word itself is the claim -
#   there is no engineering homograph for "overweight" the way "detect" and
#   "condition" have one, so nothing needs to stand next to it.
#
#   CATEGORY_WORDS_GENERIC (below, beside `BODY_COMPOSITION_NOUN`): DOES need
#   a nearby body-composition noun, the same proximity trade `_PURPOSE_RE`
#   already makes for `PURPOSE_VERB` + `MEDICAL_NOUN`. "ideal weight" is a
#   barbell-loading idiom, "healthy range" is what a float-precision test
#   calls its tolerance, and "normal range" is a CSV column name - none of
#   them are a claim about a person's reading.
#
# Every entry in both tiers was checked against the whole repo (docs/, wiki/,
# README, skills/, src/, tests/) before being kept - see the rejections
# immediately below the lists, which are exactly as load-bearing as the
# inclusions.
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
# doctrine warns gets a lint deleted.
#
# `healthy weight` stays bare rather than moving to the generic tier below:
# unlike `healthy range` and `normal range`, PR #382's review did not produce
# a false positive for it anywhere in the repo, and "a barbell's healthy
# weight" or "a CSV column named `healthy_weight`" is not an idiom anyone
# actually writes - "ideal weight" and "normal range" are the idioms, not
# this collocation. If a real false positive for it ever turns up, it moves
# to `CATEGORY_WORDS_GENERIC` on that evidence, the same way its two
# siblings just did.
CATEGORY_WORDS_GENERIC = (
    r"healthy range",
    r"normal range",
    r"ideal weight",
)

# The evidence for the split, verified by running the gate: "A barbell's
# ideal weight for this lift is 60kg per the programming doc.", "returns True
# when the argument is in a healthy range of floating point precision", and
# "The exporter writes a `normal_range` column into the CSV." all fired
# before this tier existed, against three sentences with no athlete, no
# reading and no body in them. None of `CATEGORY_WORDS_GENERIC` is dropped -
# the motivating example ("your BMI entered the healthy range") still fires,
# because `BMI` is within 80 characters of `healthy range` in that sentence.
#
# The measurands actually banded in this domain: a BMI figure, a weight, a
# body-fat reading, a kilogram amount, a mass, a waist measurement. `weight`
# and `mass` are ordinary engineering words too - the same trade-off
# `PURPOSE_VERB` makes with `detect` - but a barbell, a float comparison and
# a CSV column do not have a BMI, a body fat percentage or a waist, so the
# combination of one of them with a generic phrase inside one sentence is
# specific to a person's reading in a way that neither word is alone.
BODY_COMPOSITION_NOUN = r"\b(?:bmi|weight|body fat|kg|mass|waist)\b"

# HYPHENS ARE WORD SPACES for matching. `stop-and-see-a-clinician` is the same
# claim as `stop and see a clinician`, and every phrase above was blind to it -
# the template that `vitai init` copies into every content repo carried the
# hyphenated form and passed. Length-preserving on purpose, so a match offset
# still indexes the original sentence; and matching-only, so the digests the
# exemptions are keyed on do not move.
#
# This is the RIGHT transform for a multi-word phrase like `healthy-range` -
# turning the hyphen into the space the phrase already has elsewhere on the
# list. It is the WRONG transform for `overweight`, `underweight` and
# `prehypertension`: those three are fused compounds with no space-separated
# form anywhere in `CATEGORY_WORDS` or `CATEGORY_WORDS_GENERIC`, so writing
# them as `over-weight`, `under-weight` or `pre-hypertension` - the more
# common clinical spelling for the third one - turns them into `over weight`,
# `under weight`, `pre hypertension`, none of which is on either list either,
# and the hyphenated spelling passed clean. `findings()` below runs the
# category patterns against a SECOND, hyphen-REMOVED probe as well, which
# fuses `over-weight` back into `overweight` instead.
def _match_form(sentence: str) -> str:
    return sentence.replace("-", " ")


_DIRECTIVE_RE = re.compile("|".join(DIRECTIVES), re.I)
_PURPOSE_RE = re.compile(
    rf"(?:{PURPOSE_VERB}[^.!?]{{0,80}}{MEDICAL_NOUN})"
    rf"|(?:{WATCH_VERB}[^.!?]{{0,80}}{CONDITION_NOUN})", re.I)
_CATEGORY_RE = re.compile(r"\b(?:" + "|".join(CATEGORY_WORDS) + r")\b", re.I)
_CATEGORY_GENERIC_RE = re.compile(
    rf"(?:{BODY_COMPOSITION_NOUN}[^.!?]{{0,80}}"
    rf"\b(?:{'|'.join(CATEGORY_WORDS_GENERIC)})\b)"
    rf"|(?:\b(?:{'|'.join(CATEGORY_WORDS_GENERIC)})\b[^.!?]{{0,80}}"
    rf"{BODY_COMPOSITION_NOUN})", re.I)


def _category_search(candidate: str) -> re.Match | None:
    """Bare clinical words OR a generic phrase beside a body-composition
    noun - the two `CATEGORY_WORDS` tiers are one family for `findings()`,
    which reports both as "category claim" and does not care which tier
    fired."""
    return _CATEGORY_RE.search(candidate) or _CATEGORY_GENERIC_RE.search(candidate)


# Sentences, across hard line wraps. The docs here are wrapped at ~80 columns,
# so splitting on a newline hid every directive long enough to straddle one -
# which is most of them. Paragraph breaks still end a sentence, since a blank
# line is a real boundary and joining across one invents adjacency.
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]|$)")

# Markdown formatting must not break a phrase: `see a **doctor**` is the same
# claim as `see a doctor`, and a lint that can be evaded by emphasis is one
# that will be, by accident, on the first pass of someone tidying a document.
_MARKUP_RE = re.compile(r"[*_`]+|\[|\]\([^)]*\)")

# CATEGORY matching needs `_` treated differently from every other family.
# `_MARKUP_RE` strips it as a markdown emphasis marker - right for `_see a
# doctor_`, which this codebase's docs do write - but an identifier is not
# prose: stripping the underscores out of `is_overweight_flag` turns one
# token into three, and `\b` then lands inside the middle of a variable name.
# Preserving `_` as a word character is exactly what stops that, because
# `\b` will not match inside `is_overweight_flag` while the underscores are
# still there holding it together as one token.
#
# Scoped to CATEGORY only, not shared with `_MARKUP_RE`: DIRECTIVES and
# PURPOSE_VERB still need underscores folded away, because the same
# emphasis form (`_word_`) is how this codebase's docs occasionally write
# "doctor" or "detect" for emphasis, and losing that would let `_see a
# doctor_` evade the directive family the way `**doctor**` almost did.
# `sentences()` below is unchanged and still feeds hashing, DIRECTIVES and
# PURPOSE_RE; `_tight_sentences()` is the identifier-preserving twin used
# only for CATEGORY.
_MARKUP_RE_TIGHT = re.compile(r"[*`]+|\[|\]\([^)]*\)")

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

    # --- #388: the boundary controls, quoting the forms they exist to catch.
    # Same shape as the doctrine entries above and the same justification:
    # prose explaining a constraint trips the constraint. These are what
    # survives the use/mention split in `voice()` - 62 findings from adding
    # `tests` to SURFACE become these, and every one is a sentence ABOUT a
    # forbidden phrasing, in a file whose job is proving the gate catches it.
    # None applies a category to a person or tells a reader to obtain care,
    # which is the pair no syntactic split can separate on its own.

    ("tests/test_boundary_gate.py",
     "5871624d94dcd5d6b1eb66ed6d35c440187095326f9dc133cf33fea0fb24138c"):
        "the control pinning that a generic collocation needs a body- "
        "composition noun within reach, quoting the pair",
    ("tests/test_boundary_gate.py",
     "3e4869443181d8f04fceb6a331d6a55b0206a2ecd29d86974d7077af7c0cf50d"):
        "the control explaining why the hyphenated clinical spelling must "
        "fold to the fused one on the deny list",
    ("tests/test_boundary_gate.py",
     "1bf260380a192dedc9b2e4500eceb29a269100e7e2aa87908abd498d28e2ecb3"):
        "the control quoting the collocation-plus-noun example that the "
        "proximity scoping had to keep firing on",
    ("tests/test_boundary_gate.py",
     "259ce8d7de22b1e8ca9448d9e2b97c8c92ba6b4d8fd9c54c213cdbc4a93db5d9"):
        "the control explaining why the -ity noun is not on the deny list "
        "while the adjective is",
    ("tests/test_boundary_gate.py",
     "cea7308468e96fdb48cb5fb9716eccdd5fffba301be204bb67e2694736f87f89"):
        "the control explaining why three collocations need a nearby noun "
        "and five clinical words stay bare",
    ("tests/test_boundary_gate.py",
     "69da8b693212c1b6d9a2ef4be2013f9a85454616404f9ad29fd071fd402ec61b"):
        "the control recording that the identifier-preserving pass is "
        "CATEGORY-only, quoting the families that still read the prose form",
    ("tests/test_boundary_gate.py",
     "39f3e5815788737834c57fb55453ca6365994af2f9be23f796a385beba5e780e"):
        "the control explaining which collocations are narrow enough to "
        "scan the whole repo with, quoting each",
    ("tests/test_boundary_gate.py",
     "0244eeff0f07ff87c3a6577bbdfb18f10cc8ed21ae8ef53028ea1b1589f663b4"):
        "the control quoting the exact directive that a whole-sentence "
        "negation check used to suppress",
    ("tests/test_boundary_gate.py",
     "53cdeeb7d1d25b59fc17dad3477ba30928fadcc5586e060e101c3a25cee7814e"):
        "the control quoting the hyphenated directive that evaded a spaces- "
        "only deny list across every content repo",
    ("tests/test_boundary_gate.py",
     "f8932021cd0b415a93d2d1399381dbf364627163ae59819f1ba85bf596fa0764"):
        "the control quoting the addressee-with-no-profession phrasing that "
        "read as safe because it named nobody",
    ("tests/test_boundary_gate.py",
     "84da57a9008ac5b5376419cc83edef5cf1606ae1e364a1835204a7e044267b4c"):
        "the control quoting the self-assigned duty-to-watch sentence that "
        "argues a wellness tool into being a device",
    ("tests/test_safety.py",
     "fcc7b2130f8208c6faa791d900f80d3570a87767913d278e389177a765001b27"):
        "the control quoting the removed routing claim that #110 took off "
        "every escalation surface",
    ("tests/test_safety.py",
     "00234ae963db7789e578281d3e66765587fe0024fed49f15c1567806febd4efc"):
        "the control quoting the ordinary directive it contrasts the acute "
        "tier against",
    ("tests/test_safety.py",
     "d1038a54005583471466b19e225ce6f8ed199e89b97d1f3573f17522960e5589"):
        "the control recording that a MESSAGES-only sweep let the removed "
        "routing claim print through a green build, quoting it",

    # --- #440: the record of what changed about the boundary.
    # Inverting SURFACE brought `CHANGELOG.md` and `changelog.d/` into scope,
    # and a project cannot say what it changed about a deny list without
    # quoting the list. Same shape as the doctrine entries at the top.
    #
    # THE COST WORTH KNOWING: a fragment's exemption MIGRATES when
    # `changelog_gate.py --assemble` folds it into `CHANGELOG.md`. The
    # sentence survives and the file it lives in does not, so the entry has to
    # be re-keyed at release - and
    # `test_no_exemption_outlives_the_sentence_it_spares` is what will say so,
    # loudly, rather than the release going quiet.

    ("CHANGELOG.md",
     "47464bd535058f8889b286bd61211f501d6ea0ddfa6a49046e8f9e71c6862be9"):
        "the released history quoting the severity definition that #110 "
        "removed",
    ("CHANGELOG.md",
     "1a93ef283072d9382bb8a6f3f28cecf7fa3c18d9522602c67da2cac1545c76a9"):
        "the released history describing what this gate matches, quoting "
        "two of each family",
    ("CHANGELOG.md",
     "58fb3e1bdbc13e7bcd701fd738f119d0c993c5eeb58cf068f45e37767e628043"):
        "the released history quoting the escalation phrasing that moved "
        "inside the firewall",
    ("CHANGELOG.md",
     "435718a139547e987a4915b4e44c625d1efc4390fbc1495de973075dabf8bcc0"):
        "the released history quoting the routing behaviour that #110 took "
        "out",
    ("CHANGELOG.md",
     "f9c9db91275d5c87230eb050bd7da0557104f87bef42973ccbe93401ac041a64"):
        "the released history quoting the banner claim that is no longer "
        "made anywhere",
    ("changelog.d/379.fixed.md",
     "86d3cb966fca8ae692e1dc6519855be41058aa200db0310ea0296f97007c6526"):
        "the release note describing the scope the category family was "
        "added to, quoting the sentence that slipped it",
    ("changelog.d/379.fixed.md",
     "f05b085fd7acdd3bf7de7b6320a79af55c9538b5144938c332e85a6dea16e801"):
        "the release note introducing the deny list, which cannot say what "
        "was added without listing the words",
    ("changelog.d/379.fixed.md",
     "8064fe92365863a5d49f8b48e567dcc828f08e1db8368dd781573e9d06e08591"):
        "the release note stating the hyphenation rule, quoting the three "
        "words it folds",
    ("changelog.d/379.fixed.md",
     "462247e62c7218acf5f08b75d0f912a2917e4171527fb6f3cbb224b322f44c26"):
        "the release note explaining the hyphen transform, quoting the "
        "compound it must not break",
    ("changelog.d/379.fixed.md",
     "b28115fca309de807933323f8a16a12cc4b60525620acf495a119d735973ab3c"):
        "the release note stating the proximity rule, quoting the three "
        "collocations it applies to",
    ("changelog.d/379.fixed.md",
     "64ce9aa09bfa92976abd50976c564648fcf74aa44f113d590be87295107d2ea2"):
        "the release note explaining why those three needed a proximity "
        "rule, quoting an out-of-domain use",
    ("changelog.d/379.fixed.md",
     "8bae35fe2b5cbf823b89479895cd86840ddeef981606154361b40883fbe32035"):
        "the release note quoting the sentence the whole category family "
        "was built to catch",
    ("changelog.d/379.fixed.md",
     "b9dffc8a817b2ec4bf28db3892be35fb749e548cac39e7c97a0f6e6025c5f425"):
        "the release note explaining the emphasis-marker defect, quoting "
        "the identifier it split into words",
    ("changelog.d/379.fixed.md",
     "078c34aefd30e8357b54b7cb09b8ad40a43a6887c4011a31a81d8dcb6de9acf7"):
        "the release note describing the identifier-preserving pass and "
        "what it is scoped to",
    ("changelog.d/388.fixed.md",
     "7fbf8f1549f715f5ac2e1f842b364cb5c91e48dab71e30bac0f4d3f99676dae4"):
        "the release note for #388 quoting the directive its own controls "
        "must hold to prove the family fires",
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


def voice(path: Path, text: str) -> str:
    """The text a file says in its OWN VOICE, which is what this gate reads.

    Everything outside `TEST_MATERIAL` is its own voice entire, unchanged. A
    Python file inside it contributes its comments and docstrings, and none of
    its other string literals - see `TEST_MATERIAL` for why that line and not
    a directory exemption.

    A FILE THAT WILL NOT PARSE IS READ WHOLE, which is the fail-safe direction:
    a syntax error must not be a way to hide a sentence from the gate.
    """
    if path.suffix != ".py" or not any(
            path.as_posix().startswith(f"{root}/") for root in TEST_MATERIAL):
        return text
    spoken: list[str] = []
    block: list[str] = []
    previous = -2
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            # CONSECUTIVE COMMENT LINES ARE ONE PARAGRAPH, and getting this
            # wrong is not cosmetic: `_segment` splits on blank lines, so
            # emitting each line separately cut a wrapped sentence into fragments
            # and the claim that spanned two lines matched nothing. A reader
            # sees a comment block as a paragraph, and so must this.
            if token.start[0] != previous + 1 and block:
                spoken.append(" ".join(block))
                block = []
            block.append(token.string.lstrip("#").strip())
            previous = token.start[0]
        if block:
            spoken.append(" ".join(block))
        tree = ast.parse(text)
    except (SyntaxError, tokenize.TokenError, ValueError):
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if (doc := ast.get_docstring(node, clean=True)):
                spoken.append(doc)
    # A BLANK LINE BETWEEN THEM, because `_segment` treats one as a paragraph
    # break and joining two unrelated comments would invent adjacency between
    # them - the same reason that function splits on blank lines.
    return "\n\n".join(spoken)


def _skipped(rel: str) -> bool:
    """Is this path inside something `NOT_SCANNED` names?"""
    return any(rel == entry or rel.startswith(f"{entry}/")
               for entry in NOT_SCANNED)


def files() -> list[Path]:
    """Every file in the tree with a scannable suffix, minus what is named.

    WALKED RATHER THAN ASKED OF GIT, deliberately. A gate that shells out to
    `git ls-files` does not run in a source tarball, and one whose file list
    depends on a subprocess has a resolution step in front of it - the argument
    `pin_gate` already makes about YAML parsers. What git tracks is held
    against this list by a TEST, where git is available and where a mismatch is
    a finding rather than a crash.
    """
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if path.resolve() == _SELF:
            continue
        if not _skipped(path.relative_to(ROOT).as_posix()):
            out.append(path)
    return out


def _segment(text: str, markup_re: re.Pattern[str]) -> list[str]:
    """Paragraph by paragraph, markup stripped by `markup_re` and hard wraps
    joined, then split into sentences.

    A blank line is a real boundary, and joining across one would invent
    adjacency between two unrelated statements. Shared by `sentences()` and
    `_tight_sentences()` so the two differ only in which characters count as
    markup - never in how a paragraph becomes a list of sentences, which is
    what keeps the two outputs aligned index-for-index.
    """
    out = []
    for para in re.split(r"\n\s*\n", text):
        joined = " ".join(markup_re.sub(" ", para).split())
        out += [s.strip() for s in _SENTENCE_RE.findall(joined) if s.strip()]
    return out


def sentences(text: str) -> list[str]:
    """Sentences, with markdown stripped and hard wraps joined.

    This is the prose form: hashing, `EXEMPT` lookups, DIRECTIVES and
    PURPOSE_RE all read this one. `_tight_sentences()` below is the
    identifier-preserving twin used only for CATEGORY.
    """
    return _segment(text, _MARKUP_RE)


def _tight_sentences(text: str) -> list[str]:
    """Same sentences as `sentences()`, with `_` left as a word character.

    Neither `markup_re` touches `.`, `!` or `?`, so the two segmentations
    agree on where every sentence starts and ends - only the spelling inside
    a sentence can differ. `findings()` below zips this against
    `sentences()` on that assumption and falls back to the prose form
    (correct, just without identifier protection for that one sentence) if
    it is ever wrong, rather than trusting a misaligned pairing.
    """
    return _segment(text, _MARKUP_RE_TIGHT)


def findings(path: Path, text: str, spared: set[str]) -> list[str]:
    """Every care directive, purpose claim, or category claim in this file."""
    out = []
    here = path.as_posix()
    prose = sentences(text)
    tight = _tight_sentences(text)
    if len(tight) != len(prose):
        tight = prose  # fail safe: see `_tight_sentences()`'s docstring.
    for sentence, tight_sentence in zip(prose, tight):
        digest = hashlib.sha256(_norm(sentence).encode()).hexdigest()
        if digest in spared or (here, digest) in EXEMPT:
            continue
        probe = _match_form(sentence)
        for label, search, candidates in (
                ("care directive", _DIRECTIVE_RE.search, (probe,)),
                ("purpose claim", _PURPOSE_RE.search, (probe,)),
                # CATEGORY is built from `tight_sentence`, NOT `probe`: by
                # the time `sentence` (and therefore `probe`) exists, its
                # underscores are already gone - `sentences()` stripped them
                # at the paragraph stage, which is exactly the hole in
                # finding 3. Starting from `tight_sentence` and then folding
                # hyphens the same two ways `_match_form` and the hyphen-
                # removed form do for `probe` gets both fixes at once:
                # `healthy-range` reads as the phrase (space-folded), and
                # `over-weight` / `pre-hypertension` read as the fused
                # compound (hyphen-removed), while `is_overweight_flag`
                # stays one token throughout because nothing here ever
                # touches `_` - see `_MARKUP_RE_TIGHT` above.
                ("category claim", _category_search,
                 (tight_sentence, _match_form(tight_sentence),
                  tight_sentence.replace("-", "")))):
            hit = None
            for candidate in candidates:
                hit = search(candidate)
                if hit and not _disclaimed(candidate, hit.start()):
                    break
                hit = None
            if hit:
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
        here = path.relative_to(ROOT)
        for problem in findings(here, voice(here, text), spared):
            print(f"BOUNDARY GATE: {here}: {problem}")
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
