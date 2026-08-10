"""The per-value source a consumer actually receives (#325).

Contract 40 derived `field_sources` and contract 42 derived `field_origins` -
which feed and which instrument supplied each field of a merged row. Nothing
read them.

So the fact pack a consumer receives still carried the row's single `source`,
which on a merged row is the joined label. Measured before this change: a
session merged from a watch and a rowing console reported
`matrix-console+polar` for BOTH the heart rate and the distance - a string
true of neither field.

That is the issue's own complaint one layer downstream of where it was filed:
"on a merged row the emitted per-value `source` is therefore uniformly wrong
for half the fields", with the map that fixes it sitting unread in the same
build. The title's half shipped; this is the body's.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.query import collect
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


def record(tmp_path: Path, rows: list[dict], dataset: str = "sessions") -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / f"{dataset}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def values(v: Vitai, metric: str) -> list[dict]:
    return v.check("2030-05-01", metric, 0)["values"]


# --- the defect -----------------------------------------------------------------

def test_a_merged_row_reports_the_source_that_supplied_each_field(tmp_path):
    v = record(tmp_path, [session(19, **WATCH), session(20, **CONSOLE)])

    hr = values(v, "avg_hr")
    assert [r["source"] for r in hr] == ["polar"]
    assert [r["origin"] for r in hr] == ["polar-watch"]

    km = values(v, "distance_km")
    assert [r["source"] for r in km] == ["matrix-console"]
    assert [r["origin"] for r in km] == ["matrix-rower"]


def test_it_no_longer_reports_the_joined_label(tmp_path):
    """The exact string the issue names. It is true of the ROW and of none of
    its fields, which is what makes it worse than silence."""
    v = record(tmp_path, [session(19, **WATCH), session(20, **CONSOLE)])
    assert v.canonical("sessions")[0]["source"] == "matrix-console+polar"
    for metric in ("avg_hr", "distance_km", "cadence", "kcal"):
        for row in values(v, metric):
            assert "+" not in str(row["source"]), (metric, row)


# --- and it changes nothing for the 99% ----------------------------------------

def test_a_single_writer_row_still_reports_its_own_source(tmp_path):
    """The issue is explicit that this must not become ceremony on every row:
    a row with one writer has nothing to disambiguate, and its own `source` is
    already the whole truth."""
    v = record(tmp_path, [session(19, **WATCH)])
    got = values(v, "avg_hr")
    assert [r["source"] for r in got] == ["polar"]
    assert [r["origin"] for r in got] == ["polar-watch"]


def test_a_row_naming_no_instrument_reports_none(tmp_path):
    """`field_origins` never invents one, so neither does this."""
    v = record(tmp_path, [session(19, source="polar", avg_hr=142)])
    assert [r["origin"] for r in values(v, "avg_hr")] == [None]


def test_daily_rows_get_it_too(tmp_path):
    """Not a sessions-only fix: `collect` emits from both datasets and both
    were carrying the row label."""
    rows = [{**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "steps": 9000, "source": "watch", "origin": "polar-watch",
             "recorded_at": "2030-05-01T19:00:00Z"},
            {**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "kcal_in": 2100, "source": "app", "origin": "mfp",
             "recorded_at": "2030-05-01T20:00:00Z"}]
    v = record(tmp_path, rows, dataset="daily")
    assert v.canonical("daily")[0]["source"] == "app+watch"
    assert [r["source"] for r in values(v, "steps")] == ["watch"]
    assert [r["source"] for r in values(v, "kcal_in")] == ["app"]


# --- where it declines to answer ------------------------------------------------

def test_two_sessions_on_one_date_keep_their_row_label(tmp_path):
    """A provenance row is keyed by (dataset, date) and nothing more, so a
    date holding two sessions has two maps and no way to say which is which -
    a gap #326's contract note already records.

    Where more than one map could apply this declines and the row keeps its
    own `source`, which is the answer that guesses least. Picking one would be
    per-field attribution from the wrong row, which is worse than the joined
    label it replaced.

    ONE OF THEM IS MERGED, which is what makes this test bite. Two
    single-writer sessions carry no map at all, so the guard is never reached
    and a fixture built that way passes whether it exists or not - measured:
    removing the guard left the whole file green. Here the morning session is
    a merge and carries a map, so without the guard its attribution would be
    applied to the evening session's heart rate too.

    REAL TIMESTAMPS, because `start_time: "07:00"` does not parse: the
    clustering falls back to shape - same type, same duration, different
    sources - and merges everything. That trap is recorded on #330 and it bit
    again here."""
    # Morning: a merge of two instruments, so it HAS a field map.
    m_watch = session(19, source="polar", origin="polar-watch", avg_hr=142,
                      start_time="2030-05-01T07:00:00Z")
    m_console = session(20, source="matrix-console", origin="matrix-rower",
                        distance_km=8.1, start_time="2030-05-01T07:02:00Z")
    # Evening: a single writer, and a DIFFERENT instrument.
    evening = session(21, source="garmin", origin="garmin-watch", avg_hr=150,
                      start_time="2030-05-01T19:00:00Z")
    v = record(tmp_path, [m_watch, m_console, evening])
    assert len(v.canonical("sessions")) == 2, "two distinct sessions"

    got = values(v, "avg_hr")
    assert len(got) == 2, got
    assert {r["source"] for r in got} == {"matrix-console+polar", "garmin"}, (
        "each row keeps its own label; neither borrows the other's map")


def test_collect_without_provenance_behaves_exactly_as_before(tmp_path):
    """The parameter is additive. A caller that passes nothing gets the row's
    own source, which is what every caller got before this change."""
    v = record(tmp_path, [session(19, **WATCH), session(20, **CONSOLE)])
    plain = collect(v.canonical(), "2030-05-01", "avg_hr")
    assert [r["source"] for r in plain] == ["matrix-console+polar"]
    assert [r["origin"] for r in plain] == ["matrix-rower+polar-watch"], (
        "the row's own origin is joined too, and just as true of neither field")


def test_the_ambiguity_guard_declines_whichever_row_holds_the_map():
    """THE GUARD ITSELF, tested directly, because the integration test above
    passes by luck of ordering.

    Provenance rows for a date arrive in group order and the map-less one came
    first, so `rows[0]` returned nothing and removing the guard changed no
    answer. Put the map first and the same code would attribute a merged
    session's fields to every other session on that date.

    It is also what makes the per-metric lookup in `collect` safe: that
    resolves the map ONCE and applies it to every row of the day, which is
    only correct because this refuses to answer when the day holds more than
    one."""
    from vitai.query import _per_field

    mapped = {"dataset": "sessions", "date": "2030-05-01",
              "field_sources": {"avg_hr": "polar"},
              "field_origins": {"avg_hr": "polar-watch"}}
    bare = {"dataset": "sessions", "date": "2030-05-01",
            "field_sources": None, "field_origins": None}

    assert _per_field([mapped], "sessions", "2030-05-01", "avg_hr") == (
        "polar", "polar-watch", True), "one row: the map is usable"
    for order in ([mapped, bare], [bare, mapped]):
        assert _per_field(order, "sessions", "2030-05-01", "avg_hr") == (
            None, None, False), "two rows: no way to say which, so neither"


def test_a_date_the_provenance_does_not_cover_declines():
    from vitai.query import _per_field

    rows = [{"dataset": "sessions", "date": "2030-05-01",
             "field_sources": {"avg_hr": "polar"}, "field_origins": {}}]
    for args in (("sessions", "2030-05-02"), ("daily", "2030-05-01")):
        assert _per_field(rows, *args, "avg_hr") == (None, None, False), args
    assert _per_field(None, "sessions", "2030-05-01", "avg_hr") == (
        None, None, False)


def test_a_declining_map_does_not_borrow_the_rows_instrument(tmp_path):
    """THE DEFECT THE `or` FALLBACK SHIPPED, and it is this issue's own
    opening sentence turned against it.

    A map can apply to the row and still decline a FIELD: `field_origins`
    omits any field whose winning claim named no device, deliberately, so
    silence does not become an attribution. The fallback read that silence as
    the row's one named instrument - so on a watch-plus-console merge where
    only the watch names a device, the DISTANCE was attributed to the wrist
    watch that could not know it.

    Null is the honest answer. The source side is unaffected because a map
    only exists where sources differ, so its row fallback is the joined label:
    a visible decline rather than a false bare name."""
    v = record(tmp_path, [session(19, source="polar", origin="polar-watch",
                                  avg_hr=142),
                          session(20, source="matrix-console", distance_km=8.1)])
    assert v.canonical("sessions")[0]["origin"] == "polar-watch", (
        "one named instrument, so the row's own origin is a bare name")

    hr = values(v, "avg_hr")[0]
    assert (hr["source"], hr["origin"]) == ("polar", "polar-watch")

    km = values(v, "distance_km")[0]
    assert km["source"] == "matrix-console"
    assert km["origin"] is None, "the console named none, so neither do we"


def test_daily_rows_carry_the_instrument_too(tmp_path):
    """The sessions branch had a control and the daily branch did not, so
    dropping the daily origin read left all 2389 tests green - the same
    half-witnessed shape this file has already caught twice."""
    rows = [{**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "steps": 9000, "source": "watch", "origin": "polar-watch",
             "recorded_at": "2030-05-01T19:00:00Z"},
            {**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "kcal_in": 2100, "source": "app", "origin": "mfp-phone",
             "recorded_at": "2030-05-01T20:00:00Z"}]
    v = record(tmp_path, rows, dataset="daily")
    assert [r["origin"] for r in values(v, "steps")] == ["polar-watch"]
    assert [r["origin"] for r in values(v, "kcal_in")] == ["mfp-phone"]


def test_a_map_that_covers_nothing_is_not_a_map():
    """`_per_field` reports a map applies only when one carries entries. An
    empty pair would make every field 'declined' and blank every instrument on
    the row, which is the mirror of the defect above."""
    from vitai.query import _per_field

    empty = [{"dataset": "daily", "date": "2030-05-01",
              "field_sources": None, "field_origins": None}]
    assert _per_field(empty, "daily", "2030-05-01", "steps") == (None, None, False)
