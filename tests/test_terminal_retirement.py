"""A retirement either maps forward or it does not, and the difference is data.

The README's migration table said `sessions.location` is read forward as
`place`/`route` "the same as" `hip_pain` is read as `pain`. It is not read as
anything. Nothing was lying: two retirements were assumed to be one kind of
event, and only one of them is.

A RENAME THAT WIDENED versus A SPLIT INTO OTHER TYPES. `hip_pain` -> `pain` is
the first: the old value is exactly a valid new value, and the site is
recovered from the field's own name. `location` -> `place` + `route` is the
second, and the old value is a valid value of NEITHER successor - which is why
the split happened. Free text could not be grouped or compared, and which of
the two a given string belongs in is a judgement only the athlete can make.

So the answer for a split is that nothing maps it. What was wrong was not the
absence but that the absence was undocumented, undetectable and silent.

AND NOT "THE VALUE IS LOST", which the first draft of this said and which is
the same overclaim the change is here to fix. The retired key is a projected
column and a consumer querying the table gets the string. What is empty is
every SUCCESSOR, so nothing built on `place` or `route` sees it: present and
inert, which is a different and smaller claim than dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import (KEY_FORWARD, KEY_RETIREMENT, KEYS,
                          TERMINAL_RETIREMENT, forward_map_for,
                          terminal_retirement)


def _sessions_repo(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "sessions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def _session(day: str, **kw) -> dict:
    return {**{k: None for k in KEYS["sessions"]}, "date": day, "type": "run",
            "duration_s": 1800, "source": "manual",
            "recorded_at": "2030-05-01T08:00:00Z", **kw}


# --- the register -------------------------------------------------------------

def test_every_retired_key_either_maps_forward_or_says_why_it_does_not():
    """The check the README's claim could not be held to.

    G89 part two says the forward map lives in exactly ONE canonicaliser. That
    is a rule about where a map goes and it has nothing to say about a
    retirement that has no map, which is how one acquired a documented map it
    never had. Both halves are now data, and they partition.
    """
    retired = {(d, k) for d, ks in KEY_RETIREMENT.items() for k in ks}
    mapped = {(d, k) for d, ks in KEY_FORWARD.items() for k in ks}
    terminal = {(d, k) for d, ks in TERMINAL_RETIREMENT.items() for k in ks}
    assert not (mapped & terminal), f"both mapped and terminal: {mapped & terminal}"
    assert retired == mapped | terminal, (
        f"unaccounted: {retired - mapped - terminal}, "
        f"not retired at all: {(mapped | terminal) - retired}")


def test_a_terminal_retirement_states_a_reason_and_a_remedy():
    """None from `forward_map_for` is an ANSWER, and an answer needs a because.
    Without one it is indistinguishable from the entry nobody filled in - which
    is the state `sessions.location` was actually in.

    And a remedy per key, not one for all of them. A single message told the
    `planned` case to append a corrected session line; its successor is a
    `plans` row pointing the other way, so the advice was confidently wrong."""
    for dataset, keys in TERMINAL_RETIREMENT.items():
        for key, entry in keys.items():
            assert forward_map_for(dataset, key) is None, f"{dataset}.{key}"
            why, remedy = entry
            assert len(why) > 30 and len(remedy) > 30, f"{dataset}.{key}"
            assert why != remedy, f"{dataset}.{key}"
    remedies = [r for ks in TERMINAL_RETIREMENT.values() for _, r in ks.values()]
    assert len(set(remedies)) == len(remedies), "one remedy is serving two keys"


def test_a_mapped_retirement_names_a_callable_whose_source_reads_the_key():
    """HASATTR IS NOT ENOUGH, and the weak version of this test is how the
    register would certify the bug it exists to prevent.

    `forward_map_for(...) is not None` suppresses the tripwire. If an entry may
    name any resolvable attribute, a future retirement can be registered as
    mapped with nothing reading it: partition green, existence green, tripwire
    silenced, value quietly inert. So the entry names a CALLABLE and this reads
    its source for the retired key. That is why `goals.status` points at
    `policy.lifecycle_of` rather than at the `LIFECYCLE_FORWARD` table it uses
    - a table's existence says nothing about whether anybody consults it."""
    import importlib
    import inspect
    for dataset, keys in KEY_FORWARD.items():
        for key, dotted in keys.items():
            assert terminal_retirement(dataset, key) is None, f"{dataset}.{key}"
            module, _, attr = dotted.rpartition(".")
            mod = importlib.import_module(f"vitai.{module}")
            fn = getattr(mod, attr, None)
            assert callable(fn), f"{dataset}.{key} -> {dotted} is not a callable"
            src = inspect.getsource(fn)
            assert key in src, (
                f"{dotted} is registered as reading `{key}` forward and its "
                f"source never names it")


def test_location_is_the_terminal_one_and_hip_pain_is_not():
    """Named directly, because this pair is the whole point and a partition
    test would pass with both on the wrong side."""
    assert forward_map_for("sessions", "location") is None
    assert terminal_retirement("sessions", "location")
    assert forward_map_for("daily", "hip_pain") == "resolution.canonical_daily"
    assert terminal_retirement("daily", "hip_pain") is None


# --- and the record says so ---------------------------------------------------

def test_a_dropped_legacy_value_is_reported_rather_than_going_quietly(tmp_path):
    """The harm was never the absence of a map - it was that three sessions
    could carry a location, none of it reach any report, and nothing anywhere
    mention it."""
    v = _sessions_repo(tmp_path, [_session(f"2030-05-{n:02d}", location="canal path")
                                  for n in (1, 2, 3)])
    fired = [t for t in v.conservation() if t["kind"] == "unread_retired_value"]
    assert len(fired) == 1, v.conservation()
    assert fired[0]["severity"] == "review"
    assert "3 sessions line(s) carry `location`" in fired[0]["detail"]
    assert "the engine will not choose for you" in fired[0]["detail"]
    # NOT "the value is lost". The column still holds it; what is empty is
    # every successor. Overclaiming here would be this change committing the
    # thing it is fixing.
    assert "the column still holds what they said" in fired[0]["detail"]


def test_it_fires_once_for_a_field_not_once_for_every_row(tmp_path):
    """A record predating a retirement carries the old key on its whole
    history. One tripwire per row would bury every other tripwire under a fact
    that is true once."""
    v = _sessions_repo(tmp_path, [_session(f"2030-05-{n:02d}", location="park")
                                  for n in range(1, 20)])
    fired = [t for t in v.conservation() if t["kind"] == "unread_retired_value"]
    assert len(fired) == 1
    assert "19 sessions line(s)" in fired[0]["detail"]


def test_a_mapped_retirement_is_silent_because_nothing_was_dropped(tmp_path):
    """The other half of the rule, and the reason this is not just "warn on any
    retired key". A legacy `hip_pain` line reaches every reader intact, so
    there is nothing to tell anybody."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
         "hip_pain": 3, "source": "manual"}) + "\n", encoding="utf-8")
    v = Vitai(root)
    assert [t for t in v.conservation() if t["kind"] == "unread_retired_value"] == []
    assert v.canonical("daily")[0]["pain"] == 3


def test_a_record_that_never_used_the_retired_key_hears_nothing(tmp_path):
    """A null is not a value. Firing on the KEY rather than on a value would
    make every modern record carry a warning about a field it has never
    written, which is how a real signal gets trained out of a reader."""
    v = _sessions_repo(tmp_path, [_session("2030-05-01", place="park",
                                           route="towpath-loop")])
    assert [t for t in v.conservation() if t["kind"] == "unread_retired_value"] == []


def test_the_engine_does_not_guess_which_successor_the_value_belonged_to(tmp_path):
    """The refusal at the centre of this. `canal path` could be a place or a
    route and only the athlete knows; a map would have to pick, and picking is
    a claim about somewhere they went."""
    v = _sessions_repo(tmp_path, [_session("2030-05-01", location="canal path")])
    row = v.canonical("sessions")[0]
    assert row["location"] == "canal path"
    assert row["place"] is None and row["route"] is None


# The two sentences that carried the wrong claim, verbatim from the docs as
# they shipped. Kept as literals rather than paraphrased: a paraphrase would
# drift and stop matching, and this check exists precisely because prose drifts
# away from code with nothing noticing.
THE_CLAIM_THAT_WAS_WRONG = (
    "the same applies to `sessions.location` -> `place`/`route`",           # README
    "`sessions.location` became `place` + `route`.",                        # wiki
)

# What each doc must say instead. Both are checked, because the claim lived in
# both and fixing one would leave an integrator reading the other straight back
# into the original bug. This repo already has README-versus-wiki drift tests;
# they compare row coverage and version columns, so a claim like this sails
# through them.
SHIPPED_DOCS = {
    "README.md": ("never was read forward", "no successor inherited it"),
    "wiki/content/reference/data-model.md": ("nothing maps it forward, deliberately",
                                             "that is a SPLIT into"),
}


def test_no_shipped_doc_promises_a_mapping_that_does_not_exist():
    """The defect this issue actually is: prose is where the wrong claim lived,
    so the check reads the prose."""
    root = Path(__file__).resolve().parents[1]
    for name, must_say in SHIPPED_DOCS.items():
        text = (root / name).read_text(encoding="utf-8")
        for gone in THE_CLAIM_THAT_WAS_WRONG:
            assert gone not in text, f"{name} still says: {gone}"
        for phrase in must_say:
            assert phrase in text, f"{name} no longer says: {phrase}"


def test_both_docs_are_checked_and_neither_check_is_vacuous():
    """A guard on the guard above. Each entry must name a file that exists and
    a phrase that lands exactly once in it - a check anchored on something
    generic, or on a file that has been renamed, passes whatever the docs say.

    Not required to be unique ACROSS the two: the same sentence in both is the
    outcome this is trying to produce, since the claim being wrong in one place
    and right in the other is how it survived.
    """
    root = Path(__file__).resolve().parents[1]
    for name, must_say in SHIPPED_DOCS.items():
        assert (root / name).is_file(), name
        text = (root / name).read_text(encoding="utf-8")
        for phrase in must_say:
            assert text.count(phrase) == 1, (
                f"{name}: {phrase!r} appears {text.count(phrase)} times")
