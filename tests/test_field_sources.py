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


def field_sources(v: Vitai) -> dict:
    return v.resolution()["provenance"][0].get("field_sources") or {}


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


def test_it_is_declared_a_container_so_a_consumer_knows_to_parse_it():
    assert "field_sources" in LIST_COLS
    assert PROVENANCE_KEYS[-1] == "field_sources", "appended, never inserted"


def test_the_serialised_map_is_key_sorted(tmp_path):
    """Two builds of one record must compare equal as text: what a merged row
    says about which instrument supplied which field does not depend on the
    order the fields happen to be walked in."""
    from vitai.db import _cell

    assert _cell({"b": "2", "a": "1"}) == '{"a":"1","b":"2"}'
    first = both(tmp_path / "one").build().read_bytes()
    second = both(tmp_path / "two").build().read_bytes()
    assert first == second
