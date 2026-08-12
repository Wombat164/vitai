"""A dataset cannot ship without the README's data-model table knowing it
exists.

#366 found it by using the record rather than by reading it: an agent asked
to log a session the athlete meant to do LATER that day followed the
documented path and was routed to `sessions` - the exact write contract 33
exists to prevent, where a skipped row "sums to zero and counts as one,
corrupting every count silently". `schema.py`'s own docstring caught it. No
front door did, because the two tables under "The data model" in README.md
had stopped being the full list: `plans` shipped under #221 with a schema, a
validator, CLI reach and a migration note, and never reached either table.
Five more (`capabilities`, `instruments`, `protocols`, `regimes`, and
`emissions` before its allowlist entry below) were in the same state. Nothing
was red, because nothing looked.

This is #359 and its own demo-coverage instance (`test_fixture_coverage.py`,
written for exactly this shape one dataset earlier) applied to the surface a
WRITER reads rather than the surface an example ships. Same structure,
deliberately: an ALLOWLIST that fails closed, with the same two back-pressure
halves, so a dataset that gains a table row leaves the register and a
register entry naming a retired dataset cannot sit here forever.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vitai.schema import KEYS

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

# Table-row pattern: the two data-model tables both write one row per dataset
# as `| `data/<name>.jsonl` | ... |`, anchored at the start of the line so a
# passing MENTION elsewhere in the file (the Quickstart's `data/*.jsonl`
# glob, or a migration-table row's prose reference to a dataset by name)
# cannot be mistaken for the table actually documenting it.
_ROW = re.compile(r"^\| `data/([a-z_]+)\.jsonl` \|", re.M)

# Datasets the README's data-model tables deliberately do not list, and why.
# An entry here is a decision; an entry that gains a row has to leave, or the
# register rots into a list of excuses the way any backlog does.
README_OMITS = {
    "emissions":
        "emissions has one door and it is not a writer's: EVENT_DATASETS in "
        "jsonl.py refuses it to the generic append path, and `api.append` "
        "raises if a caller tries, because only `assert_delivery` may stamp "
        "the contract and surface an emission was made under. A table meant "
        "to route a writer to the right dataset would be routing them "
        "somewhere the engine itself refuses to let them write",
}


def _readme_datasets() -> set[str]:
    """Datasets named by a row in either data-model table, read from the file
    itself. This is the thing under test, not the source of the expectation -
    `schema.KEYS` supplies that, from the module the tables are meant to
    summarise."""
    text = README.read_text(encoding="utf-8")
    return set(_ROW.findall(text))


def test_every_dataset_is_in_the_readme_table_or_declared_absent() -> None:
    missing = sorted(set(KEYS) - _readme_datasets() - set(README_OMITS))
    assert not missing, (
        f"{missing} exist in the schema and no row in README.md's data-model "
        f"tables names them. Either add a table row (in the 'what happened' "
        f"table or the 'what you were aiming at' table, by what the dataset "
        f"means, not alphabetically) or add it to README_OMITS with the "
        f"reason - a dataset the front door has never heard of is one a "
        f"writer routes around, not through")


def test_the_register_does_not_keep_what_has_been_fixed() -> None:
    """The half that stops this becoming a place to put things. A dataset
    that gains a README table row has to leave the register."""
    stale = sorted(set(README_OMITS) & _readme_datasets())
    assert not stale, (
        f"{stale} are declared absent from the README tables and a table row "
        f"names them anyway. Remove them from README_OMITS")


def test_no_declared_absence_names_a_dataset_that_does_not_exist() -> None:
    """Back-pressure the other way: a renamed or retired dataset must not sit
    here forever explaining why something nobody has heard of is missing."""
    unknown = sorted(set(README_OMITS) - set(KEYS))
    assert not unknown, unknown


@pytest.mark.parametrize("name,reason", sorted(README_OMITS.items()))
def test_each_absence_gives_a_reason_worth_reading(name: str, reason: str) -> None:
    """Word count alone is weak, but a reason under it is reliably theatre:
    "not needed for the README right now" is ten words and says nothing."""
    assert len(reason.split()) >= 12, (name, reason)


def test_each_absence_talks_about_its_own_dataset() -> None:
    """A reason that never names what it is about has usually drifted from
    it - the check `test_fixture_coverage.py` added after its own `protocols`
    entry stopped describing `protocols` at all."""
    for name, reason in sorted(README_OMITS.items()):
        stem = name.rstrip("s")
        assert stem in reason.lower(), (name, reason)
