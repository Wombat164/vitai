"""Which instrument supplied which field (#325).

A wrist watch and a rowing console recorded one session. The watch had heart
rate and an energy estimate and could not know distance; the console had
distance, stroke rate and watts and knew nothing about a pulse. One session,
two instruments, and the right outcome is one row carrying both.

That already works: appended as two lines they resolve to ONE canonical row,
and `source` reads `matrix-console+polar` to say the row is a merge. What the
row could not say is WHICH INSTRUMENT SUPPLIED WHICH FIELD - its single
`source` is true of half its values and false of the rest, and a consumer
emitting a per-value `source`, which the fact-pack shape already does, was
uniformly wrong for half of them.

`explanations` LOOKS LIKE THE ANSWER AND IS NOT, which is the part worth
holding on to. It records the winner of a CONTEST, and complementary
instruments never contest: heart rate had one witness, distance had one
witness, and a field with one witness "is taken verbatim and explains
nothing" - deliberately, or the explanations become noise nobody reads. So the
case this exists for was exactly the case that stayed silent.

DERIVED, NEVER STORED. The issue offers a `source_of` map on the line as the
minimum fix; nothing needs to go on the line, because the engine is holding
both contributing claims at the moment it merges them and simply threw the
attribution away. Nothing is asked of the athlete, and a row with one writer
gains nothing, because its own `source` is already the whole truth.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vitai.api import Vitai
from vitai.db import LIST_COLS, PROVENANCE_KEYS
from vitai.schema import KEYS

WATCH = {"source": "polar", "origin": "polar-watch", "capture": "ble",
         "avg_hr": 142, "max_hr": 168, "kcal": 310}
CONSOLE = {"source": "matrix-console", "origin": "matrix-rower",
           "capture": "photo", "distance_km": 8.1, "cadence": 26,
           "avg_power": 185}


def session(hour: int, **kw) -> dict:
    return {**{k: None for k in KEYS["sessions"]}, "date": "2030-05-01",
            "type": "row", "duration_s": 1800, "start_time": "18:00",
            "recorded_at": f"2030-05-01T{hour:02d}:00:00Z", **kw}


def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "sessions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def both(tmp_path: Path) -> Vitai:
    return record(tmp_path, [session(19, **WATCH), session(20, **CONSOLE)])


def field_sources(v: Vitai, dataset: str = "sessions") -> dict:
    rows = [r for r in v.resolution()["provenance"] if r["dataset"] == dataset]
    return (rows[0].get("field_sources") or {}) if rows else {}


def weights(tmp_path: Path, rows: list[tuple]) -> Vitai:
    """A weight record: bucketed by date, so two claims certainly merge."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    lines = []
    for source, kg, hour in rows:
        rec = {**{k: None for k in KEYS["weight"]}, "date": "2030-05-01",
               "kg": kg if kg is not None else 70.9, "source": source,
               "recorded_at": f"2030-05-01T{hour:02d}:00:00Z"}
        if source is None:
            rec["body_fat_pct"] = 21.5   # a field only this claim carries
        lines.append(json.dumps(rec))
    (root / "data" / "weight.jsonl").write_text("\n".join(lines) + "\n",
                                                encoding="utf-8")
    return Vitai(root)


# --- the merge already works ---------------------------------------------------

def test_two_instruments_resolve_to_one_row_carrying_both(tmp_path):
    """The issue's first question - is a merged row a case the record intends
    to support - is answered YES by machinery that already exists. Two lines,
    one canonical row, and neither instrument's values are lost."""
    rows = both(tmp_path).canonical("sessions")
    assert len(rows) == 1
    row = rows[0]
    assert row["avg_hr"] == 142 and row["distance_km"] == 8.1
    assert row["source"] == "matrix-console+polar", "the row says it is a merge"


def test_the_rows_own_source_is_true_of_the_row_and_of_no_value_in_it(tmp_path):
    """The defect, stated as the merged row states it."""
    v = both(tmp_path)
    row = v.canonical("sessions")[0]
    assert "polar" in row["source"] and "matrix-console" in row["source"]
    # ...and no single value came from both.
    got = field_sources(v)
    assert got["avg_hr"] != got["distance_km"]


def test_explanations_cannot_answer_it(tmp_path):
    """The reason this needed building at all. `explanations` records contests,
    and complementary instruments never contest - so the two fields the issue
    is about appear in it nowhere."""
    explained = {e["field"] for e in both(tmp_path).resolution()["explanations"]}
    assert "avg_hr" not in explained
    assert "distance_km" not in explained


# --- what it now says ----------------------------------------------------------

def test_each_field_names_the_instrument_that_supplied_it(tmp_path):
    got = field_sources(both(tmp_path))
    assert got["avg_hr"] == "polar"
    assert got["max_hr"] == "polar"
    assert got["kcal"] == "polar"
    assert got["distance_km"] == "matrix-console"
    assert got["cadence"] == "matrix-console"
    assert got["avg_power"] == "matrix-console"


def test_a_contested_field_names_the_winner(tmp_path):
    """Where they DO contest, the map agrees with the ladder rather than
    holding a second opinion."""
    v = both(tmp_path)
    got = field_sources(v)
    for e in v.resolution()["explanations"]:
        assert got[e["field"]] == e["chosen_source"], e["field"]


def test_it_names_no_field_the_row_does_not_hold(tmp_path):
    v = both(tmp_path)
    row = v.canonical("sessions")[0]
    for field in field_sources(v):
        assert row.get(field) is not None, field


# --- and costs a single-writer row nothing ------------------------------------

def test_a_row_with_one_writer_gets_no_map(tmp_path):
    """Ceremony on the 99 per cent of rows written by one writer is the thing
    the issue explicitly does not ask for. Its own `source` is already the
    whole truth."""
    v = record(tmp_path, [session(19, **WATCH)])
    assert v.resolution()["provenance"] == [] or not field_sources(v)


def test_nothing_is_asked_of_the_athlete():
    """DERIVED, NEVER STORED. The issue offers a `source_of` map on the line as
    the minimum fix; nothing goes on the line, because the engine holds both
    contributing claims at the moment it merges them and was throwing the
    attribution away."""
    assert "field_sources" not in KEYS["sessions"]
    assert not any("source_of" in fields for fields in KEYS.values())


# --- and it reaches a consumer -------------------------------------------------

def test_it_is_a_column_and_survives_the_round_trip(tmp_path):
    v = both(tmp_path)
    con = sqlite3.connect(v.build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(provenance)")]
        assert "field_sources" in cols
        raw = con.execute("SELECT field_sources FROM provenance").fetchone()[0]
        assert json.loads(raw)["avg_hr"] == "polar"
    finally:
        con.close()


def test_it_is_a_map_and_is_not_declared_a_list():
    """`LIST_COLS` promises a JSON ARRAY - `field_types` documents it as "true
    where the value is a list" - and a consumer iterating a parsed map gets
    keys instead of items. So it has its own declaration.

    And the honest scope of that declaration: `field_types()` walks `KEYS`, so
    a DERIVED table's columns reach no public accessor at all. A consumer's
    only route to this is importing `vitai.db`, which is the hand-copy pattern
    #257 exists to abolish - worth saying rather than implying the flag is
    published."""
    from vitai.api import field_types
    from vitai.db import MAP_COLS

    assert "field_sources" in MAP_COLS
    assert "field_sources" not in LIST_COLS
    assert not any("field_sources" in fields for fields in field_types().values())


def test_the_column_is_appended_rather_than_inserted():
    """Positional reads are not the contract - `PROVENANCE_KEYS[-1]` would
    break the moment contract 41 appends the next column, and asserting it
    would teach a consumer the wrong habit. What matters is that no earlier
    column moved."""
    before = ["date", "dataset", "origin", "independent_sources",
              "trust", "chain"]
    assert PROVENANCE_KEYS[:len(before)] == before
    assert "field_sources" in PROVENANCE_KEYS[len(before):]


def test_a_provenance_row_carries_no_way_to_tell_two_merges_apart():
    """A KNOWN LIMIT, pinned structurally rather than discovered later.

    A provenance row is keyed by dataset, date and origin, with no ordinal, no
    `activity_id` and no `start_time`. So a morning and an evening outing that
    each merge a watch and a console produce two rows a consumer cannot attach
    to their sessions. The ambiguity predates this column and is harmless for
    `trust` and `chain`, which are cluster-symmetric across a merge;
    per-field attribution is the first thing on that row for which it is not.

    Asserted over the KEYS rather than through a fixture, because the fixture
    would be testing the session clusterer and this is a statement about the
    table's grain. Closing it needs an identity on the provenance row.
    """
    assert set(PROVENANCE_KEYS) & {"activity_id", "start_time", "ordinal",
                                   "row_ref", "seq"} == set(), (
        "if a discriminator has arrived, this limit is closed and the note in "
        "db.py's contract 40 entry should go with it")


def test_the_serialised_map_is_key_sorted(tmp_path):
    """Two builds of one record must compare equal as text: what a merged row
    says about which source supplied which field does not depend on the order
    the fields happen to be walked in."""
    from vitai.db import _map_cell

    assert _map_cell({"b": "2", "a": "1"}) == '{"a":"1","b":"2"}'
    first = both(tmp_path / "one").build().read_bytes()
    second = both(tmp_path / "two").build().read_bytes()
    assert first == second


# --- what the review found the first cut got wrong ---------------------------

def test_it_never_names_a_field_the_finished_row_took_elsewhere(tmp_path):
    """THE MAP IS SEALED BEFORE THE ROW IS. `_keep_identity_together` runs
    after the field loop and takes the identity triple from one claim in FILE
    ORDER rather than from the ladder winner - so the map could attribute an
    `activity_id` to the source that lost it, and could name a `track` on a row
    whose `track` ended up null. The first version's comment claimed it "cannot
    drift from what the row actually took", and it could."""
    console = session(20, activity_id="m-77", activity_source="matrix",
                      **CONSOLE)
    watch = session(19, activity_id="p-11", activity_source="polar",
                    track="tracks/row.fit", **WATCH)
    v = record(tmp_path, [console, watch])
    row = v.canonical("sessions")[0]
    got = field_sources(v)

    for field, source in got.items():
        assert row.get(field) is not None, f"{field} named on a row without it"
    if "activity_id" in got:
        owner = next(r for r in (console, watch)
                     if r["activity_id"] == row["activity_id"])
        assert got["activity_id"] == owner["source"]


def test_two_claims_from_one_source_are_one_writer(tmp_path):
    """`len(claims) > 1` counted ROWS. An informal re-export correcting an
    earlier line - which `_recency` calls the commonest case - is two claims
    and one writer, and the canonical `source` says so by staying a bare name
    with no `+`. A map there is ceremony on exactly the rows #325 asks us not
    to burden, and a consumer using its presence as the merge signal would
    have been misled."""
    # WEIGHT, not sessions: weight buckets by date so two claims certainly
    # merge, where the session clusterer may keep two near-identical outings
    # apart and prove nothing about the guard.
    v = weights(tmp_path, [("scale", 70.0, 1), ("scale", 70.2, 2)])
    row = v.canonical("weight")[0]
    assert row["source"] == "scale", "one writer, so no `+`"
    assert not field_sources(v, "weight")


def test_the_map_appears_exactly_when_the_source_says_merge(tmp_path):
    """The two signals must agree, in both directions - that is what makes
    either of them usable."""
    cases = ((weights(tmp_path / "m", [("scale", 70.0, 1), ("hand", 70.4, 2)]),
              True),
             (weights(tmp_path / "s", [("scale", 70.0, 1)]), False),
             (weights(tmp_path / "d", [("scale", 70.0, 1), ("scale", 70.2, 2)]),
              False))
    for v, expected in cases:
        row = v.canonical("weight")[0]
        assert ("+" in row["source"]) is expected, row["source"]
        assert bool(field_sources(v, "weight")) is expected


def test_an_unattributed_winner_is_named_unknown_not_none(tmp_path):
    """An unattributed claim that wins a field must not publish `"None"`.

    TWO THINGS ENFORCE THIS AND ONLY ONE IS NEEDED, which is worth saying
    rather than dressing a redundant line as a control. `or UNKNOWN_SOURCE`
    at the point of recording is the obvious guard; the prune below re-derives
    the owner from the finished row and lands on the same answer, so removing
    the fallback leaves this passing. The fallback stays because it makes the
    recorded value right at the moment it is recorded rather than right after
    a later repair, and a value that is only correct downstream is a value
    somebody will read upstream."""
    from vitai.resolution import UNKNOWN_SOURCE

    v = weights(tmp_path, [("scale", 70.0, 1), (None, None, 2)])
    got = field_sources(v, "weight")
    assert got, "the rows must actually merge for this to test anything"
    assert "None" not in got.values(), got
    assert set(got.values()) <= {"scale", UNKNOWN_SOURCE}, got
    assert UNKNOWN_SOURCE in got.values(), "the anonymous claim won something"


def test_a_malformed_map_on_a_raw_line_still_fails_loudly(tmp_path):
    """The dict branch started life in `_cell`, which sees every raw line's
    every field - so a `note: {...}` an athlete should never have written went
    from a loud build failure to a silently stored JSON string. Widening what
    the engine accepts is not a side effect a serialiser gets to have."""
    import pytest

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "sessions.jsonl").write_text(json.dumps(
        {**{k: None for k in KEYS["sessions"]}, "date": "2030-05-01",
         "type": "run", "duration_s": 1800, "source": "manual",
         "note": {"unexpected": "dict"}}) + "\n", encoding="utf-8")
    with pytest.raises(Exception):
        Vitai(root).build()


def test_the_map_column_is_the_only_one_serialised_as_a_map():
    from vitai.db import MAP_COLS

    assert MAP_COLS == {"field_sources"}
