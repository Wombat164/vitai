"""A dataset cannot ship without the shipped example knowing it exists.

`generate_demo.py` builds the example and `--check` byte-compares it, so the
demo cannot drift from its generator. Nothing checked whether the generator
knew a dataset existed at all.

Adding `instruments` (#311) I wrote `examples/demo/data/instruments.jsonl` by
hand. The generator had never heard of it, so `--check` reported drift on a
file nothing could regenerate - a message that reads exactly like the ordinary
"regenerate and commit" and is not fixable that way. The full suite, five
gates and ruff were all green - thirty-six test files read the demo, and not
one of them asks whether a dataset reaches it at all - and the `demo` job is
the fast one nobody reads. It was red across two pushes.

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
        "no row in the demo sets `protocol`, so there is nothing for a "
        "protocols row to be the procedure of; what the demo says about how "
        "it weighs is a journal line, which is a claim about practice rather "
        "than a declared procedure",
    "regimes":
        "a regime is a bounded interval in which a figure means something "
        "else, and the demo is deliberately uneventful - inventing one would "
        "add a confound to the record that exists to be readable",
}


def _demo_writes() -> set[str]:
    """Datasets the generator declares it writes.

    FROM A REGISTER THE GENERATOR EXPORTS, not from anything derived. Two
    earlier shapes were both wrong in the way this file exists to prevent.

    Reading the committed directory would call a hand-written file covered,
    which is the case that prompted all of this.

    Substring-matching the generator's SOURCE for `("name",` was the second
    attempt and is worse, because it looks careful. It reports a dataset as
    written when its name appears in a comment - so commenting out a writer,
    the most natural way to remove one, leaves the gate green. It was already
    armed: `("equipment",` sits in that file today inside a tuple of
    set-configuration keys, so the day `equipment` became a dataset the demo
    would ship without it and nothing would say so. And it went red on a
    behaviour-preserving refactor of the writer loop, printing advice that
    would not have fixed anything - which is how a gate gets deleted.

    `generate_demo.WRITES` is a register, and `main` asserts its own writer
    loop matches it, so the two cannot drift.
    """
    from generate_demo import WRITES

    return set(WRITES)


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
    import tempfile

    from generate_demo import _build, _read_all

    # THE WHOLE TREE, and the same suffix set `--check` compares. The first
    # version globbed `data/*.jsonl` only, so a hand-written track under
    # `tracks/` walked past it - and that directory is the one where the
    # personal gate permits coordinates ON THE GROUNDS that they are the
    # generator's own output. A file nobody generated sitting there makes that
    # grounds false, which is a worse failure than the one this started with.
    # BUILT INTO A SCRATCH DIRECTORY, which is what `--check` does. Asking the
    # generator what it produces by running it is the only answer that cannot
    # drift from what it actually produces.
    scratch = Path(tempfile.mkdtemp()) / "demo"
    _build(scratch)
    produced = set(_read_all(scratch))
    on_disk = set(_read_all(DEMO))
    orphans = sorted(on_disk - produced)
    assert not orphans, (
        f"{orphans} are committed under examples/demo and the generator does "
        f"not produce them. Regenerating will not fix this: give them a source "
        f"in `generate_demo.py`, or delete them")


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
    """A register whose entries say "not needed" teaches nothing.

    Word count is the weakest of the three checks here and was the only one in
    the first version, which was close to theatre: "not applicable to a
    single-athlete demo because it is out of scope for us right now" is
    fourteen words and says nothing. The two below are the ones with teeth."""
    assert len(reason.split()) >= 12, (name, reason)


def test_no_two_absences_share_a_reason() -> None:
    """The copy-paste case, which word count cannot see: a new dataset added
    to the register by duplicating the line above it inherits an explanation
    that was true of something else."""
    seen: dict[str, str] = {}
    for name, reason in sorted(DEMO_OMITS.items()):
        assert reason not in seen, (name, seen.get(reason))
        seen[reason] = name


def test_each_absence_talks_about_its_own_dataset() -> None:
    """A reason that never names what it is about has usually drifted from it.

    This is the check that would have caught the `protocols` entry, which
    claimed the demo's weigh-ins name a protocol slug and that the procedure
    lives in the README. Neither was true: no demo row sets `protocol` at all,
    and the prose about weighing is a journal row."""
    for name, reason in sorted(DEMO_OMITS.items()):
        stem = name.rstrip("s")
        assert stem in reason.lower(), (name, reason)
