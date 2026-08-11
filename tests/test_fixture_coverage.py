"""A dataset cannot ship without the shipped example knowing it exists.

`generate_demo.py` builds the example and `--check` byte-compares it, so the
demo cannot drift from its generator. Nothing checked whether the generator
knew a dataset existed at all.

Adding `instruments` (#311) I wrote `examples/demo/data/instruments.jsonl` by
hand. The generator had never heard of it, so `--check` reported drift on a
file nothing could regenerate - a message that reads exactly like the ordinary
"regenerate and commit" and is not fixable that way. The full suite, five
gates and ruff were all green, because none of them looks at the demo, and the
`demo` job is the fast one nobody reads. It was red across two pushes.

So this is an ALLOWLIST that fails closed: every dataset is either written by
the demo generator or written down here as deliberately absent, with the
reason. Not every dataset belongs in one athlete's example. The absence has to
be a decision somebody made rather than one nobody saw.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from vitai.schema import KEYS

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
sys.path.insert(0, str(ROOT / "examples"))


# Datasets the demo deliberately does not write, and why. An entry here is a
# decision; an entry that gains a writer has to leave, or the register rots
# into a list of excuses the way any backlog does.
DEMO_OMITS = {
    "artifacts":
        "the demo ships no bytes, and an artifact row with a content address "
        "behind which nothing is stored would make the example's own "
        "`verify_artifacts` report a fault on a clean checkout",
    "protocols":
        "the demo's weigh-ins name a protocol slug and the procedure behind it "
        "is prose in the README rather than a row; a one-athlete example has "
        "one procedure and nothing to contrast it with",
    "regimes":
        "a regime is a bounded interval in which a figure means something "
        "else, and the demo is deliberately uneventful - inventing one would "
        "add a confound to the record that exists to be readable",
}


def _demo_writes() -> set[str]:
    """Datasets the GENERATOR produces, read from the generator itself.

    Not from the committed directory: a file somebody wrote by hand is exactly
    what this is here to catch, and reading the directory would call it
    covered.
    """
    import generate_demo

    source = Path(generate_demo.__file__).read_text(encoding="utf-8")
    # The writer loop names each dataset as a `("name", rows)` pair.
    return {name for name in KEYS if f'("{name}",' in source}


def test_every_dataset_is_written_by_the_demo_or_declared_absent() -> None:
    missing = sorted(set(KEYS) - _demo_writes() - set(DEMO_OMITS))
    assert not missing, (
        f"{missing} exist in the schema and the demo generator does not write "
        f"them. Either write them in `generate_demo.py` or add them to "
        f"DEMO_OMITS with the reason - a dataset the shipped example has never "
        f"heard of is one no consumer of that example can discover")


def test_the_register_does_not_keep_what_has_been_fixed() -> None:
    """The half that stops this becoming a place to put things. A dataset that
    gains a writer has to leave the register."""
    stale = sorted(set(DEMO_OMITS) & _demo_writes())
    assert not stale, (
        f"{stale} are declared absent from the demo and the generator writes "
        f"them. Remove them from DEMO_OMITS")


def test_no_declared_absence_names_a_dataset_that_does_not_exist() -> None:
    """Back-pressure the other way: a renamed or retired dataset must not sit
    here forever explaining why something nobody has heard of is missing."""
    unknown = sorted(set(DEMO_OMITS) - set(KEYS))
    assert not unknown, unknown


def test_every_committed_demo_file_is_one_the_generator_produces() -> None:
    """THE FAILURE THAT PROMPTED THIS, stated directly rather than as drift.

    `--check` compares bytes, so a hand-written file it cannot regenerate
    reports as drift and the advice it prints - regenerate and commit - does
    not fix it. This says the actual thing: the generator does not produce
    this file."""
    on_disk = {p.stem for p in (DEMO / "data").glob("*.jsonl")}
    orphans = sorted(on_disk - _demo_writes())
    assert not orphans, (
        f"{orphans} are committed under examples/demo/data and the generator "
        f"does not produce them. Regenerating will not fix this: add them to "
        f"`generate_demo.py` so they have a source")


def test_the_declared_absences_are_really_absent() -> None:
    """A reason for an absence that is not an absence is worse than no reason:
    it tells the next reader not to look."""
    for name in DEMO_OMITS:
        path = DEMO / "data" / f"{name}.jsonl"
        rows = ([json.loads(line) for line
                 in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if path.exists() else [])
        assert not rows, (name, len(rows))


@pytest.mark.parametrize("name,reason", sorted(DEMO_OMITS.items()))
def test_each_absence_gives_a_reason_worth_reading(name: str, reason: str) -> None:
    """A register whose entries say "not needed" teaches nothing. Length is a
    crude proxy and it is the only mechanical one there is; the real check is
    that somebody had to write a sentence."""
    assert len(reason.split()) >= 12, (name, reason)
