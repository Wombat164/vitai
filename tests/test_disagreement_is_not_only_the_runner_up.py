"""A third claim differing wildly went unnoticed (#94, ask 4).

`independent_witnesses` counts three for three sources agreeing and three for
three sources where one contradicts the others. Same number, opposite
meanings - which is ask 4's point: "nothing contradicted this" is a different
claim from "three things confirmed it", and today they render the same.

The engine already knows the difference and was only half telling anyone.
`_merge_fields` records `discarded` over EVERY losing claim - widened for #73,
with the comment saying so - and records `disagreed` two lines below it from
the runner-up alone. The comment beside `unattributed_loser`, in the same
dict, names this exact defect while fixing a neighbour:

    `disagreed` compares the winner with the runner-up only, so a third
    unattributed claim differing wildly went unnoticed

It was fixed there and not here.

IT REACHED A READER. `_contradictions` gates the `source_disagreement`
tripwire on the flag, and the CLI marks a contested line with `!` only when it
is set. So a scale saying 70.0, an app saying 70.0 and a watch saying 84.5
produced no mark and no tripwire - because the two the ladder happened to
compare agreed.

WHAT IS NOT HERE: the 10 per cent tolerance. `_disagrees` calls two values
equal when they differ by less than a tenth, and the repo's own comment
observes that "10% of a day's burn is ~300 kcal, which is enough to flip a
surplus into a deficit while counting as agreement". That is a threshold with
its own argument and its own blast radius; this change makes the existing rule
reach every claim rather than changing what the rule says.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.provenance import independent_witnesses
from vitai.schema import KEYS


def weigh(source: str, kg: float, hour: int) -> dict:
    return {**{k: None for k in KEYS["weight"]}, "date": "2030-05-01",
            "kg": kg, "source": source, "capture": "ble",
            "recorded_at": f"2030-05-01T{hour:02d}:00:00Z"}


def record(tmp_path: Path, rows: list[dict], toml: str = "") -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def kg_row(v: Vitai) -> dict:
    return next(e for e in v.resolution()["explanations"] if e["field"] == "kg")


# --- the asymmetry ask 4 names -------------------------------------------------

def test_a_count_of_witnesses_says_nothing_about_whether_they_agreed():
    """The premise, reproduced. This is why `disagreed` has to be right: the
    corroboration count cannot carry the distinction and does not try to."""
    def rows(*kgs):
        return [weigh(s, kg, 7) for s, kg in zip(("scale", "app", "watch"), kgs)]

    assert independent_witnesses(rows(70.0, 70.0, 70.0)) == 3
    assert independent_witnesses(rows(70.0, 70.0, 84.5)) == 3


# --- the defect ----------------------------------------------------------------

def test_a_third_claim_differing_wildly_is_noticed(tmp_path):
    """The runner-up agrees and the third does not. Before this, `disagreed`
    was False, no tripwire fired, and the CLI printed no mark."""
    v = record(tmp_path, [weigh("scale", 70.0, 1), weigh("app", 70.0, 2),
                          weigh("watch", 84.5, 3)])
    assert kg_row(v)["disagreed"] is True
    fired = [t for t in v.conservation() if t["kind"] == "source_disagreement"]
    assert fired, v.conservation()


def test_the_tripwire_names_what_was_discarded_and_not_the_pair_that_agreed(
        tmp_path):
    """Naming the runner-up produced `source_disagreement: app says 70.0,
    scale says 70.0` - two identical numbers under a disagreement heading,
    which reads as a broken tripwire rather than a real one."""
    v = record(tmp_path, [weigh("scale", 70.0, 1), weigh("app", 70.0, 2),
                          weigh("watch", 84.5, 3)])
    detail = next(t["detail"] for t in v.conservation()
                  if t["kind"] == "source_disagreement")
    assert "84.5" in detail, detail
    assert "watch" in detail, detail


def test_the_ladder_still_explains_itself_through_the_runner_up(tmp_path):
    """`over_source` and `over_value` describe the contest the ladder actually
    decided, and `reason` is written about that pair. Only the flag widened -
    repointing those would leave `reason` explaining a comparison it did not
    make."""
    v = record(tmp_path, [weigh("scale", 70.0, 1), weigh("app", 70.0, 2),
                          weigh("watch", 84.5, 3)])
    row = kg_row(v)
    assert row["over_value"] == 70.0, "the runner-up, not the outlier"
    assert "84.5" in row["discarded"] and "70.0" in row["discarded"]


def test_agreement_all_round_still_says_nothing(tmp_path):
    """The common case must stay silent or the tripwire list becomes noise
    nobody reads."""
    v = record(tmp_path, [weigh("scale", 70.0, 1), weigh("app", 70.0, 2),
                          weigh("watch", 70.0, 3)])
    assert kg_row(v)["disagreed"] is False
    assert not [t for t in v.conservation()
                if t["kind"] == "source_disagreement"]


def test_a_two_source_contest_is_unchanged(tmp_path):
    """With one discard the widening is a no-op, which is most of the corpus.
    A change that moved the two-source answer would be changing the rule
    rather than its reach."""
    disagree = record(tmp_path / "a", [weigh("scale", 70.0, 1),
                                       weigh("app", 84.5, 2)])
    agree = record(tmp_path / "b", [weigh("scale", 70.0, 1),
                                    weigh("app", 70.0, 2)])
    assert kg_row(disagree)["disagreed"] is True
    assert kg_row(agree)["disagreed"] is False


def test_the_tolerance_itself_is_untouched(tmp_path):
    """Deliberately out of scope. `_disagrees` calls two values equal below a
    tenth, and the repo's own comment says 10 per cent of a day's burn is
    enough to flip a surplus into a deficit while counting as agreement. That
    is a threshold with its own argument; this change makes the existing rule
    reach every claim rather than changing what it says."""
    from vitai.resolution import DISAGREEMENT_TOLERANCE, _disagrees

    assert DISAGREEMENT_TOLERANCE == 0.10
    assert _disagrees(70.0, 84.5) is True
    assert _disagrees(70.0, 74.5) is False, "6 per cent still reads as agreement"

    # And through the whole path, so the scope of this change is legible.
    v = record(tmp_path, [weigh("scale", 70.0, 1), weigh("app", 70.0, 2),
                          weigh("watch", 74.5, 3)])
    assert kg_row(v)["disagreed"] is False


def test_the_widening_matches_the_one_discarded_already_had(tmp_path):
    """Both answer a question about ALL the losing claims, and they sat two
    lines apart with one widened and one not."""
    import inspect

    from vitai import resolution

    src = inspect.getsource(resolution._merge_fields)
    assert 'for _, rec in witnesses[1:]' in src
    assert '_disagrees(winner[field], loser[field])' not in src, \
        "the runner-up-only comparison is gone"
