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

## What it deliberately does not do

No natural-language understanding, and no attempt to catch condition-naming
mechanically - that is open-ended and stays a review judgement. **Start narrow
and grow.** A lint that cries wolf gets deleted, and a deleted lint catches
nothing at all, so a false positive here costs more than a missed string.

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

    # --- DEBT, not decisions. Every one describes routing that #110 REMOVED,
    # so these sentences are now false as well as over the line. They belong
    # to #116 and to the session that owns `docs/`, not to this gate. Listed
    # individually so the lint can gate CI today and the debt stays visible -
    # excluding the directory would hide it, and hide whatever is written
    # there next.
    ("docs/cross-metric-inference.md",
     "3e7c94c637d54fb9dd1b0570d2b47427a1649d31bec96123e34fa78d34a643fd"):
        "stale: pre-#110 routing; #116 owns the rewrite",
    ("docs/model.md",
     "02191f8391725b3cf85b64088009be39528ce3811dde836e2236e65192535a72"):
        "stale: pre-#110 routing; #116 owns the rewrite",
    ("docs/model.md",
     "b8190e1ddd8503ed50c5e78acfbc0e84c29572e82df82e78cc239e4c5b7de515"):
        "stale: pre-#110 routing; #116 owns the rewrite",
    ("docs/plan-v3.md",
     "93d1e27fbfff46e31a1bfe6295fd797ebce90fed5dcf759bc9969b3ad7f424e7"):
        "stale: pre-#110 routing; #116 owns the rewrite",
    ("docs/the-loop.md",
     "27b32823f12553739406ea3026d590e37346261652dca6fb87f374e4d580d1bf"):
        "stale: pre-#110 routing, surfaced by hyphen normalisation; "
        "#116 owns the rewrite",
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
    """Every care directive or purpose claim in this file."""
    out = []
    here = path.as_posix()
    for sentence in sentences(text):
        digest = hashlib.sha256(_norm(sentence).encode()).hexdigest()
        if digest in spared or (here, digest) in EXEMPT:
            continue
        probe = _match_form(sentence)
        for label, pattern in (("care directive", _DIRECTIVE_RE),
                               ("purpose claim", _PURPOSE_RE)):
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
              "do. It does not tell the reader to obtain care, and it does "
              "not claim to detect, screen for or monitor a condition.\n"
              "See docs/medical-boundary.md. If a string is genuinely part "
              "of the acute tier, it belongs in safety.ACUTE, which this "
              "gate reads directly.")
        return 1
    print("boundary gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
