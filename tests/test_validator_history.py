"""Already corrected is not still wrong (#245).

`validate` reported content problems on every line in the log, including lines
a later line had already corrected. In an append-only record those lines
cannot be edited, so the problems were permanently unfixable - and a validator
whose output can never reach zero is one people stop reading, including for
the problems that are actionable.

NOT SILENCED. The line really is malformed and the log really does contain it,
and a record that hid its own history of mistakes would be a worse record. The
ask was only that the two stop looking identical.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai, init
from vitai.schema import CURRENT_GENERATION, KEYS

_made = [0]


def a_goal(**kw):
    g = {k: None for k in KEYS["goals"]}
    g.update({"date": "2030-06-01", "slug": "errands",
              "title": "Errands become movement", "metric": None,
              "policy": "monotonic", "period": "weekly", "tracker": None,
              "lifecycle_status": "active", "verification": "attested",
              "_gen": CURRENT_GENERATION["goals"]})
    g.update(kw)
    return g


def report(tmp_path: Path, rows, dataset="goals"):
    _made[0] += 1
    root = init(tmp_path / f"c{_made[0]}")
    (root / "data" / f"{dataset}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return Vitai(root).validate()


def test_a_line_that_still_determines_the_record_is_a_problem(tmp_path):
    """The actionable case, and it must stay loud."""
    got = report(tmp_path, [a_goal()])
    assert len(got["problems"]) == 1 and not got["ok"]


def test_a_line_a_later_line_corrected_is_reported_quietly(tmp_path):
    """Effective dating: a later row with the same slug simply wins, which is
    the documented pattern for a policy dataset and the only one available
    there - several rows of one goal share a line key, so a `supersedes`
    reference retires the most recent rather than the one below it, and no
    sequence of appends reaches the earliest."""
    got = report(tmp_path, [a_goal(), a_goal(date="2030-06-02", period="none")])
    assert got["problems"] == [] and got["ok"]
    kept = [a for a in got["advisories"] if "already corrected" in a]
    assert len(kept) == 1


def test_the_advisory_says_which_line_corrected_it(tmp_path):
    """"Already corrected" is only useful if the reader can see by what."""
    got = report(tmp_path, [a_goal(), a_goal(date="2030-06-02", period="none")])
    assert any("line 1 (already corrected by line 2)" in a
               for a in got["advisories"])


def test_a_well_tended_record_can_reach_zero(tmp_path):
    """The useful property. A number that can reach zero is one worth looking
    at; one that cannot is a list people learn to skim."""
    got = report(tmp_path, [a_goal(), a_goal(date="2030-06-02", period="none")])
    assert got["problems"] == []


def test_two_different_goals_both_wrong_are_both_problems(tmp_path):
    """The correction must be per identity, not per dataset: a second goal
    with its own slug corrects nothing."""
    got = report(tmp_path, [a_goal(slug="a"),
                            a_goal(slug="b", date="2030-06-02")])
    assert len(got["problems"]) == 2


def test_a_superseded_line_is_quiet_too(tmp_path):
    """The other way a line stops determining the record."""
    bad = {k: None for k in KEYS["weight"]}
    bad.update({"date": "2030-06-01", "kg": 80.0, "source": "scale",
                "body_fat_pct": 250.0,      # a 0-100 percentage, refused
                "_gen": CURRENT_GENERATION["weight"]})
    fix = dict(bad, body_fat_pct=25.0, supersedes="2030-06-01/scale",
               recorded_at="2030-06-02T07:00:00+00:00")
    got = report(tmp_path, [bad, fix], dataset="weight")
    assert got["problems"] == []
    assert any("already corrected by line 2" in a for a in got["advisories"])
