"""The rollup's weight table is a SERIES, one line per day (#396).

Reported from real use: a rollup whose weight table repeated a date three
times, every repeat carrying the same value from a different source. That
would make the table a list of CLAIMS wearing the shape of a series.

IT DOES NOT REPRODUCE, and this file is what that investigation left behind.
`Vitai.rollup` and `Vitai.build` both hand `build_report` the CANONICAL
weight, and for `weight` the resolver groups strictly by date - one merged row
per day, with no branch that can emit two (contrast `sessions`, which clusters,
and `measurements`, which splits by kind because a waist reading and a body-fat
read are not competing claims). Six shapes were tried and all collapsed: same
value from two sources, different `measured_at`, different `device`,
disagreeing values, per-device files under #105's union merge, and a
`supersedes` chain.

SO WHY WRITE TESTS FOR A BUG THAT IS NOT THERE. Because nothing pinned the
property. The table reads canonical by a call-site argument in `api.py`, three
words that no test would notice changing, and the report itself cannot tell:
it renders whatever list it is handed. That is the same shape as #126's verdict
path, where `compute_verdicts` read a mapped field on the stated grounds that
callers pass mapped rows, and no test held any caller to it.

THE CASE THAT MATTERS IS THE ONE WHERE THE VALUES AGREE. Two claims for one
day carrying the SAME kilogram render two identical lines - arithmetically
unimpeachable, and wrong about how many times the athlete stood on a scale. A
test that only checked disagreeing values would pass while the invisible case
regressed, so the agreeing case is first here and is the one the report was
reported on.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import KEYS

DAY = "2030-06-03"
NEXT = "2030-06-04"


def _record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps({**{k: None for k in KEYS["weight"]}, **r}) + "\n"
                for r in rows), encoding="utf-8")
    return Vitai(root)


def _table(v: Vitai) -> list[str]:
    """The weight table's data rows, as rendered."""
    lines = v.rollup().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("| Date |"))
    out = []
    for ln in lines[start + 2:]:
        if not ln.startswith("|"):
            break
        out.append(ln)
    return out


def _dates(rows: list[str]) -> list[str]:
    return [r.split("|")[1].strip() for r in rows]


def test_two_claims_for_one_day_with_the_same_value_render_one_line(tmp_path):
    """THE REPORTED CASE, and the one a reader cannot spot.

    Both claims say 82.7. Rendering both is not an arithmetic error - it is
    the page asserting two weigh-ins where the record describes one, which is
    a claim about the athlete's behaviour the record never made.
    """
    v = _record(tmp_path, [
        {"date": DAY, "kg": 82.7, "source": "stated-in-chat"},
        {"date": DAY, "kg": 82.7, "source": "an-export"},
        {"date": NEXT, "kg": 82.5, "source": "an-export"},
    ])
    # THE ANCHOR FIRST. If the record did not actually hold two claims for the
    # day, everything below would pass by having nothing to collapse.
    assert len(v.dataset("weight")) == 3
    assert len(v.canonical()["weight"]) == 2

    assert _dates(_table(v)) == [DAY, NEXT]


def test_a_day_appears_once_even_when_the_two_claims_disagree(tmp_path):
    """The visible half, and it checks WHICH value survives rather than only
    the row count: a table that printed one line but the unresolved figure
    would still be telling the reader something the record does not stand
    behind."""
    v = _record(tmp_path, [
        {"date": DAY, "kg": 82.7, "source": "a", "origin": "scale"},
        {"date": DAY, "kg": 83.9, "source": "b", "origin": "dexa"},
        {"date": NEXT, "kg": 82.5, "source": "a"},
    ])
    resolved = {r["date"]: r["kg"] for r in v.canonical()["weight"]}
    rows = _table(v)
    assert _dates(rows) == [DAY, NEXT]
    assert f"{resolved[DAY]:.1f}" in rows[0], (rows[0], resolved[DAY])


def test_the_coverage_count_agrees_with_the_table(tmp_path):
    """A fix that corrected the table and left this line counting claims would
    have moved the inconsistency rather than removed it: the page would print
    a weight count that its own table contradicts, two screens apart, and the
    reader has no way to tell which is the record."""
    v = _record(tmp_path, [
        {"date": DAY, "kg": 82.7, "source": "a"},
        {"date": DAY, "kg": 82.7, "source": "b"},
        {"date": DAY, "kg": 82.7, "source": "c"},
        {"date": NEXT, "kg": 82.5, "source": "a"},
    ])
    assert len(v.dataset("weight")) == 4
    out = v.rollup()
    counted = [ln for ln in out.splitlines() if ln.startswith("- weight:")]
    assert counted, out
    assert counted[0].startswith("- weight: 2 "), counted[0]
    assert len(_table(v)) == 2


def test_the_rolling_average_is_not_weighted_by_how_many_sources_logged(tmp_path):
    """`_rolling` means over the VALUES in its window, so a day carrying three
    claims would count three times. With claims that agree that is invisible;
    with claims that disagree it drags the average toward whichever day was
    logged most, which is a property of the record's plumbing rather than of
    the athlete."""
    many = _record(tmp_path, [
        {"date": DAY, "kg": 80.0, "source": "a"},
        {"date": DAY, "kg": 86.0, "source": "b"},
        {"date": DAY, "kg": 86.0, "source": "c"},
        {"date": NEXT, "kg": 80.0, "source": "a"},
    ])
    one = _record(tmp_path / "b", [
        {"date": DAY, "kg": r["kg"], "source": "resolved"}
        for r in many.canonical()["weight"] if r["date"] == DAY
    ] + [{"date": NEXT, "kg": 80.0, "source": "a"}])
    assert _table(many)[-1] == _table(one)[-1], (
        "the 7d average differs depending on how many sources logged the same "
        "day, so it is averaging claims rather than days")


def test_the_series_survives_per_device_files(tmp_path):
    """#105's union merge puts one logical dataset in several files. The table
    must still be a series - a second machine appending is not a second
    weigh-in."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    for name, rows in (
            ("weight.phone.jsonl", [{"date": DAY, "kg": 82.7, "source": "a",
                                     "device": "phone"}]),
            ("weight.laptop.jsonl", [{"date": DAY, "kg": 82.7, "source": "b",
                                      "device": "laptop"},
                                     {"date": NEXT, "kg": 82.5, "source": "b",
                                      "device": "laptop"}])):
        (root / "data" / name).write_text(
            "".join(json.dumps({**{k: None for k in KEYS["weight"]}, **r}) + "\n"
                    for r in rows), encoding="utf-8")
    v = Vitai(root)
    assert len(v.dataset("weight")) == 3
    assert _dates(_table(v)) == [DAY, NEXT]
