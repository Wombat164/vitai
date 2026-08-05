"""Reading a dataset is a supported call, on every surface (#258).

The engine's correction rule is correct and was reachable only by knowing it
existed. A consumer that did not find it wrote the nine obvious lines instead,
and they were wrong twice over: one reference dropped every row sharing its
key, and - the part that is not a variant of the known bug - each correction
matched its own reference and was dropped along with its target, so the record
got shorter every time somebody fixed a typo.

So these tests do two things. They pin the two behaviours a reimplementation
gets wrong, against the supported path, so the path is worth pointing at. And
they assert that all three surfaces answer identically, because P9 says the
CLI and the API are one surface and an agent reading through MCP must not get
a third answer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vitai import mcp
from vitai.api import Vitai, init
from vitai.schema import CURRENT_GENERATION, KEYS


def w(**kw) -> dict:
    rec = {k: None for k in KEYS["weight"]}
    rec.update({"date": "2030-05-04", "kg": 80.0, "source": "scale",
                "_gen": CURRENT_GENERATION["weight"]})
    rec.update(kw)
    return rec


def record(tmp_path: Path, name: str, rows: list[dict], slug: str) -> Path:
    root = init(tmp_path / slug)
    (root / "data" / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return root


def test_a_correction_replaces_one_row_and_survives_itself(tmp_path):
    """The exact shape that shortened the consumer's dataset by two.

    A correction carries the same `<date>/<source>` as the row it names, so a
    naive matcher drops the target AND the correction. What must come back is
    one row, and it must be the corrected value - not zero rows, and not the
    stale one.
    """
    rows = [w(kg=80.0), w(kg=81.4, supersedes="2030-05-04/scale")]
    root = record(tmp_path, "weight", rows, "one")

    live = Vitai(root).dataset("weight")

    assert len(live) == 1, "the correction retired itself along with its target"
    assert live[0]["kg"] == 81.4


def test_one_reference_does_not_retire_every_row_sharing_its_key(tmp_path):
    """#239's rule, which a copy living in a consumer did not get.

    Three weigh-ins on one day from one scale, and a correction naming that
    date and source. One row goes; two stay. The consumer's version left
    nothing behind.
    """
    rows = [w(kg=80.0, measured_at="07:00"),
            w(kg=80.4, measured_at="12:00"),
            w(kg=80.9, measured_at="19:00"),
            w(kg=81.4, measured_at="19:00", supersedes="2030-05-04/scale")]
    root = record(tmp_path, "weight", rows, "two")

    live = Vitai(root).dataset("weight")

    assert len(live) == 3
    assert 81.4 in [r["kg"] for r in live]


def test_a_chain_of_corrections_leaves_the_last_one(tmp_path):
    """Corrections correcting corrections. The third edge a copy has to know."""
    rows = [w(kg=80.0),
            w(kg=81.4, supersedes="2030-05-04/scale"),
            w(kg=82.2, supersedes="2030-05-04/scale")]
    root = record(tmp_path, "weight", rows, "three")

    live = Vitai(root).dataset("weight")

    assert [r["kg"] for r in live] == [82.2]


def test_an_event_dataset_never_retires(tmp_path):
    """The fourth edge. A later row cannot make an earlier one not have been
    said, so `emissions` ignores a reference rather than honouring it.

    THE REFERENCE HAS TO BE THE KEY THAT WOULD OTHERWISE MATCH, and the first
    version of this test got that wrong: it named `2030-05-04/None`, which
    matches nothing at all, so it passed with the event-dataset guard removed
    and pinned nothing. `emissions` has no `source` field, so `line_key`'s
    `<date>/<source>` fallback renders `2030-05-04/` with the source empty -
    and it is precisely because every emission on a day shares that key that
    this dataset must refuse the reference rather than honour it.
    """
    said = {k: None for k in KEYS["emissions"]}
    said.update({"date": "2030-05-04", "kind": "verdict",
                 "statement": "a figure", "surface": "cli",
                 "_gen": CURRENT_GENERATION["emissions"]})
    other = dict(said, statement="a later figure",
                 supersedes="2030-05-04/")
    root = record(tmp_path, "emissions", [said, other], "four")

    assert len(Vitai(root).dataset("emissions")) == 2


def test_the_three_surfaces_return_the_same_rows(tmp_path):
    """P9: one surface. An agent through MCP, a script through the CLI and a
    library caller must not get three answers to one question."""
    rows = [w(kg=80.0), w(kg=81.4, supersedes="2030-05-04/scale")]
    root = record(tmp_path, "weight", rows, "five")

    from_api = Vitai(root).dataset("weight")
    from_mcp = mcp.call(root, "dataset", {"name": "weight"})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weight",
         "--root", str(root), "--json"],
        capture_output=True, text=True, check=True)
    from_cli = [json.loads(line) for line in out.stdout.splitlines()]

    assert from_api == from_mcp == from_cli


def test_the_read_path_is_documented_on_every_surface(tmp_path):
    """The register that would have prevented this.

    `dataset()` was correct, public and undocumented, absent from the CLI and
    absent from the MCP tool list. Each absence on its own looks like a small
    omission; together they are why re-deriving the rule looked like the
    obvious path. The check is deliberately narrow - it asserts presence, not
    wording - because a test over prose is one nobody can satisfy honestly.
    """
    for name in ("dataset", "datasets", "rollup", "verdicts"):
        doc = getattr(Vitai, name).__doc__
        assert doc and doc.strip(), f"Vitai.{name} has no docstring"

    assert "dataset" in mcp.TOOLS
    described = {t["name"]: t["description"] for t in mcp.tool_list()}
    assert described["dataset"].strip(), (
        "the MCP description derives from the method docstring, so an empty "
        "one means the method lost its own")

    out = subprocess.run([sys.executable, "-m", "vitai.cli", "--help"],
                         capture_output=True, text=True, check=True)
    assert "dataset" in out.stdout


def test_the_summary_counts_declared_fields_not_observed_ones(tmp_path):
    """The denominator comes from the engine, never from the data.

    Reporting "12 of 12 fields" because this record happens to use twelve
    would state one record's habits as the schema. `field_types` is what #257
    published for exactly this, and the count of declared fields must not move
    when a record stops writing one.
    """
    root = record(tmp_path, "weight", [w(kg=80.0)], "six")
    full = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weight",
         "--root", str(root)], capture_output=True, text=True, check=True)

    declared = len(KEYS["weight"])
    assert f"of {declared} declared fields" in full.stdout
    # One row carrying three values, against a schema with many more.
    assert f"({3} of {declared} declared fields)" in full.stdout


def test_a_quarantined_line_is_never_silent(tmp_path):
    """A partial answer must not read as a complete one.

    Malformed lines are dropped so a read can proceed (G26), which means the
    row count alone cannot tell a consumer that anything went missing.
    """
    root = record(tmp_path, "weight", [w(kg=80.0)], "seven")
    path = root / "data" / "weight.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n",
                    encoding="utf-8")

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weight",
         "--root", str(root)], capture_output=True, text=True, check=True)

    assert "quarantined" in out.stdout
    assert "1 live row(s)" in out.stdout

    # And on the machine path too, where the consumer this issue is about
    # actually reads. Stderr, so the JSONL on stdout stays parseable.
    machine = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weight",
         "--root", str(root), "--json"],
        capture_output=True, text=True, check=True)

    assert "quarantined" in machine.stderr
    assert [json.loads(ln) for ln in machine.stdout.splitlines()]


def test_an_empty_dataset_says_so_rather_than_printing_nothing(tmp_path):
    root = record(tmp_path, "weight", [w(kg=80.0)], "eight")
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "emissions",
         "--root", str(root)], capture_output=True, text=True, check=True)

    assert "no live rows" in out.stdout


def test_an_unknown_dataset_is_refused_with_the_list(tmp_path):
    root = record(tmp_path, "weight", [w(kg=80.0)], "nine")
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "dataset", "weights",
         "--root", str(root)], capture_output=True, text=True)

    assert out.returncode != 0
    assert "weight" in out.stderr
