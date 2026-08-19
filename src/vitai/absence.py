"""The absence vocabulary, and what tells its words apart (#456).

`absent_reason` is the ONE vocabulary in this engine a client has to WRITE, and
`schema()` did not publish it. A misspelled verdict word makes a client render
badly; a misspelled absence word makes `append_many` raise on the athlete's
device, as a failed write for a question they answered helpfully.

AND THE PAYLOAD ALREADY CARRIED AN ABSENCE VOCABULARY - a different one.
`builds.absence_meanings` says what the absence of a FIELD FROM A BUILD means:
`not_measured`, `not_installed`, `unknown`. A client hunting the payload for
words to write finds it first, and none of its members is a legal
`absent_reason`. `unknown` is precisely the word contract 51 dropped, for the
reason it dropped it: a null already says that. So the trap was not that the
vocabulary was missing - it was that the wrong one was in reach.

WORDS ALONE WOULD NOT BE ENOUGH. #467 settled this one field over: publishing
an interval without publishing what it covers left a client rendering blind, and
a vocabulary a client must write is worth nothing unless it can tell which
member means which. The distinctions here are subtle and consequential - an
athlete who declines, an athlete who does not know, and a null are three
different facts - and they lived only in the comment above `ABSENT_REASONS`.

THREE FACTS PER WORD, each taken from that comment rather than invented, and
each separating the vocabulary differently:

    asked            was the athlete asked? A null and a refusal are not the
                     same silence.
    settled          does asking again add anything? "A permanent answer;
                     asking again is rude" and "answered, and asking again is
                     pointless" are this engine's own words for two of these.
    counts_as_a_gap  is this a hole at all? `not-applicable` is "not a gap at
                     all", and a coverage figure that counted it would report a
                     hole where the quantity does not exist.

WHAT THIS DOES NOT ADD, and it is the question #456 leaves open: a word for
"the athlete was asked, they know, and this record has no slug for the answer."
That is not an absence of an ANSWER - it is an absence of a WORD, and recording
it in `absent_reason` would put a fact about this engine's vocabulary into a
field about the athlete's data, where every later reader would take it for the
second. The answer belongs in the record as prose and the missing slug belongs
in an issue against the vocabulary that lacks it. No seventh word.
"""

from __future__ import annotations

from .schema import ABSENT_REASONS

# WHICH VOCABULARY THIS IS, said out loud because there are two and they are
# both about absence (#400's rule: a label is a claim).
SAYS = ("why a value this record was expected to hold is not there - written "
        "on the row, by whoever recorded it")
OTHER = ("`builds.absence_meanings` is the other one: what the absence of a "
         "field FROM A BUILD means. Its words are not legal here and a write "
         "carrying one is refused")

REASONS = {
    "not-performed": {
        "says": "the measurement was never made",
        "asked": False,
        "settled": False,
        "counts_as_a_gap": True,
    },
    "unable-to-obtain": {
        "says": "it was attempted and no value came back",
        "asked": False,
        "settled": False,
        "counts_as_a_gap": True,
    },
    "error": {
        "says": "a value came back and was rejected as wrong",
        "asked": False,
        "settled": False,
        "counts_as_a_gap": True,
    },
    "asked-declined": {
        "says": "the athlete was asked and would rather not say",
        "asked": True,
        # "A permanent answer; asking again is rude."
        "settled": True,
        "counts_as_a_gap": True,
    },
    "asked-unknown": {
        "says": "the athlete was asked and does not know",
        "asked": True,
        # "Answered, and asking again is pointless." This is the word the
        # client's gap-tapping flow needs to tell apart from silence, and the
        # reason it survived the pruning from FHIR's list.
        "settled": True,
        "counts_as_a_gap": True,
    },
    "not-applicable": {
        "says": "the quantity does not apply here",
        "asked": False,
        "settled": True,
        # "Not a gap at all."
        "counts_as_a_gap": False,
    },
}

# WHAT WAS DROPPED FROM FHIR's `dataAbsentReason` AND WHY, published so a
# client reading that codelist beside this one is not left wondering whether an
# omission was a decision. The reasons are the ones in `schema.py`.
DROPPED = {
    "unknown": "a null `absent_reason` already says exactly this, and a code "
               "meaning the same as the absence of a code is an in-band "
               "restatement of it",
    "not-asked": "the same: silence already says nobody asked",
    "unsupported": "contract 44 carries it - an instrument that does not "
                   "observe a quantity is `competence: absent`, and a second "
                   "spelling would drift from the first",
    "masked": "neither this nor `not-permitted` arises in a record whose owner "
              "is its only subject, and a redaction vocabulary invites a "
              "redaction mechanism nobody has designed",
    "not-permitted": "as `masked`",
    "not-a-number": "it encodes a value a numeric column cannot hold, and this "
                    "engine validates types rather than smuggling sentinels "
                    "through them",
}


def reason(word: str) -> dict | None:
    """What `word` means and what tells it apart, or None if it is not one.

    NONE FOR ANYTHING OUTSIDE THE VOCABULARY, including the words the other
    absence vocabulary publishes: a client that reached for `unknown` gets
    nothing here rather than a plausible answer that would be refused at the
    write.
    """
    if word not in ABSENT_REASONS:
        return None
    return dict(REASONS[word])


def declaration() -> dict:
    """The whole vocabulary, its distinctions, and what was left out."""
    return {
        "says": SAYS,
        "not_to_be_confused_with": OTHER,
        "reasons": {word: dict(REASONS[word]) for word in sorted(ABSENT_REASONS)},
        "dropped": dict(sorted(DROPPED.items())),
    }
