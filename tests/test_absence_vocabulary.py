"""The absence vocabulary, published with what distinguishes its words (#456).

`absent_reason` is the one vocabulary in this engine a client has to WRITE, and
`schema()` did not publish it. A misspelled verdict word makes a client render
badly; a misspelled absence word makes `append_many` raise on the athlete's
device, as a failed write for a question they answered helpfully.

AND THE PAYLOAD ALREADY CARRIED AN ABSENCE VOCABULARY - THE WRONG ONE.
`builds.absence_meanings` is `not_measured`, `not_installed`, `unknown`: what
the absence of a FIELD FROM A BUILD means. A client hunting the payload for the
words to write finds it, and none of its three members is a legal
`absent_reason` - `unknown` is precisely the word contract 51 DROPPED, because
a null already says it. The trap was reachable before this change and the write
would have been refused.

WORDS ALONE WOULD NOT BE ENOUGH, which is #467's lesson one field over: a
vocabulary a client must write is worth nothing unless the client can tell which
member means which. The distinctions here are subtle and consequential - a
declining athlete, an athlete who does not know, and a null are three different
facts - and they lived only in source comments.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from vitai import absence
from vitai.api import Vitai, init, schema
from vitai.schema import ABSENT_REASONS

DEMO = "examples/demo"


# ------------------------------------------------------------------ the defect

def test_the_vocabulary_a_client_must_write_is_published():
    """The gap, asserted rather than described."""
    assert "absent_reasons" in schema(), (
        "`absent_reason` is the one vocabulary a client has to WRITE and the "
        "payload does not carry it, so the only way to reach a word is to "
        "spell it and hope")


def test_it_is_the_whole_vocabulary_and_nothing_else():
    """Against `schema.ABSENT_REASONS` itself, so the published list cannot
    drift from the one that validates a write."""
    assert set(schema()["absent_reasons"]) == set(ABSENT_REASONS)


def test_it_is_ordered_so_a_client_that_diffs_the_payload_sees_no_churn():
    """`ABSENT_REASONS` is a set and a set's iteration order is not stable
    across builds. A payload that reordered between them would look like a
    change to every consumer that compares."""
    words = list(schema()["absent_reasons"])
    assert words == sorted(words)


# ------------------------------------------- the trap that was already there

def test_the_other_absence_vocabulary_is_not_a_source_of_words_to_write():
    """The premise, measured. A client that found `builds.absence_meanings`
    and wrote one of its members would have the write refused."""
    other = schema()["builds"]["absence_meanings"]
    assert other, "premise: the payload really does carry a second one"
    assert not set(other) & set(ABSENT_REASONS), other


def test_writing_a_word_from_the_other_vocabulary_is_refused(tmp_path):
    """Not a hypothetical: the failure this issue is about, reached by the
    route the issue did not anticipate."""
    v = Vitai(init(tmp_path / "r"))
    with pytest.raises(Exception) as e:
        v.append("weight", {"date": "2030-05-01", "kg": None,
                            "absent_fields": "kg", "absent_reason": "unknown"})
    assert "absent_reason" in str(e.value)


def test_each_vocabulary_says_which_one_it_is():
    """#400's rule - a label is a claim - applied to two lists that are both
    about absence and are about different things."""
    assert absence.SAYS
    assert "build" in absence.OTHER.lower()


# ------------------------------------------------- what distinguishes them

def test_every_word_carries_what_distinguishes_it():
    """#467, one field over. Publishing six words without publishing what
    tells them apart would leave the client doing exactly what it does now."""
    published = schema()["absent_reasons"]
    for word in ABSENT_REASONS:
        entry = absence.reason(word)
        assert entry["says"], word
        assert isinstance(entry["asked"], bool), word
        assert isinstance(entry["counts_as_a_gap"], bool), word
        assert isinstance(entry["settled"], bool), word
        assert word in published


def test_the_three_facts_are_not_the_same_fact():
    """Each has to separate the words differently, or two of them are one
    fact with two names and a consumer branching on either gets the same
    answer."""
    facts = {}
    for key in ("asked", "counts_as_a_gap", "settled"):
        facts[key] = frozenset(w for w in ABSENT_REASONS
                               if absence.reason(w)[key])
    assert len(set(facts.values())) == 3, facts
    for key, group in facts.items():
        assert 0 < len(group) < len(ABSENT_REASONS), (key, group)


def test_the_one_that_is_not_a_gap_says_so():
    """`not-applicable` is "not a gap at all" in this engine's own words, and
    a coverage figure that counted it as one would be reporting a hole where
    the quantity does not exist."""
    assert absence.reason("not-applicable")["counts_as_a_gap"] is False
    for word in ABSENT_REASONS - {"not-applicable"}:
        assert absence.reason(word)["counts_as_a_gap"] is True, word


def test_the_two_that_answer_the_gap_tapping_flow_are_distinguishable():
    """The flow named in `schema.py` as the reason `asked-unknown` survived
    the pruning: somebody was asked and the answer was that nobody knows,
    which the client needs to tell apart from silence AND from a refusal."""
    declined, unknown = absence.reason("asked-declined"), absence.reason("asked-unknown")
    assert declined["asked"] and unknown["asked"]
    assert declined["settled"] and unknown["settled"]
    assert declined["says"] != unknown["says"]
    assert absence.reason("not-performed")["asked"] is False


def test_a_word_outside_the_vocabulary_is_refused():
    assert absence.reason("unknown") is None
    assert absence.reason("not-asked") is None


def test_the_dropped_words_are_named_with_the_reason_they_were_dropped():
    """So a client reading FHIR's `dataAbsentReason` beside this one is not
    left to wonder whether an omission was a decision."""
    assert set(absence.DROPPED) >= {"unknown", "not-asked", "unsupported"}
    for word, why in absence.DROPPED.items():
        assert why and word not in ABSENT_REASONS


# --------------------------------------------------------------------- P9

def test_the_cli_and_the_api_answer_the_same_thing():
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "absence",
                          "--json"], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == absence.declaration()


def test_the_declaration_and_the_payload_are_one_thing():
    assert schema()["absent_reasons"] == sorted(absence.declaration()["reasons"])
