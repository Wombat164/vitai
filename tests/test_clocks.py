"""The three clocks: valid time, transaction time, observation time (#37).

Synthetic data only (public repo), fictional athlete, 2030 dates.

The bug these guard: two rows shared an effective date, one superseding the
other, and nothing in the DATA said which won - resolution fell back to file
position, which any sort, reformat or merge silently changes. An ordering a
formatter can change is not an ordering.
"""

import json

import pytest

from vitai.api import Vitai
from vitai.clocks import (is_stamp, now_stamp, order_key, timing_caveat,
                          weigh_in_timing)
from vitai.jsonl import DataError, append, heads, load
from vitai.policy import state
from vitai.schema import (CURRENT_GENERATION, KEYS, key_generation,
                          recorded_at_problems, validate_record)


def goal(slug="steps", date="2030-04-01", target=10000, **kw):
    rec = {"date": date, "slug": slug, "title": f"{slug} goal", "metric": "steps",
           "dataset": None, "session_type": None, "tracker": None,
           "target": target, "policy": "monotonic", "guard_pct": None,
           "period": "weekly", "on_period_end": "reset", "deadline": None,
           "status": "active", "motivator": None, "rationale": None,
           "on_success": None, "on_miss": None, "accountability": None,
           "set_by": "athlete", "reason": None, "note": None}
    rec.update(kw)
    return rec


def repo(tmp_path):
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def write(root, name, rows):
    (root / "data" / f"{name}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---- ordering: the bug this exists for ----------------------------------------

def test_same_date_rows_resolve_from_data_not_file_position():
    """THE acceptance criterion. Two rows, one date, and the answer must come
    from the record rather than from which line happens to be second."""
    early = goal(target=10000, recorded_at="2030-04-01T09:15:00+02:00")
    late = goal(target=12000, recorded_at="2030-04-01T18:40:00+02:00")
    for order in ([early, late], [late, early]):
        assert state(order, [], "2030-04-01").goal("steps")["target"] == 12000


def test_rewriting_the_file_cannot_change_what_the_record_asserts():
    """A sort, a reformat or a git merge reorders lines. Before this, that
    silently changed which goal was in force."""
    rows = [goal(target=10000, recorded_at="2030-04-01T09:15:00+02:00"),
            goal(target=12000, recorded_at="2030-04-01T18:40:00+02:00")]
    forward = heads(rows, "goals")["steps"]["target"]
    reversed_file = heads(list(reversed(rows)), "goals")["steps"]["target"]
    sorted_by_target = heads(sorted(rows, key=lambda r: r["target"]),
                             "goals")["steps"]["target"]
    assert forward == reversed_file == sorted_by_target == 12000


def test_absent_sorts_before_present_so_a_stamped_row_wins():
    """A stamped row was demonstrably written later than an unstamped one."""
    legacy = goal(target=10000)
    stamped = goal(target=12000, recorded_at="2030-04-01T09:15:00+02:00")
    assert order_key(legacy) < order_key(stamped)
    assert state([stamped, legacy], [], "2030-04-01").goal("steps")["target"] == 12000


def test_an_unstamped_file_keeps_exactly_its_old_behaviour():
    """The migration must be a READ NO-OP: with the key constant across every
    legacy row, a stable sort preserves file order, so last-line-wins holds."""
    rows = [goal(target=10000), goal(target=12000), goal(target=11000)]
    assert heads(rows, "goals")["steps"]["target"] == 11000
    assert state(rows, [], "2030-04-01").goal("steps")["target"] == 11000


def test_valid_time_may_still_be_backdated():
    """`date` is not monotonic and must not be - a line written today about a
    decision made last week is legitimately backdated. Only the transaction
    clock is monotonic."""
    later_written_earlier_dated = [
        goal(date="2030-04-10", target=12000,
             recorded_at="2030-04-10T09:00:00+02:00"),
        goal(date="2030-04-02", target=9000,
             recorded_at="2030-04-11T09:00:00+02:00"),
    ]
    assert validate_record("goals", later_written_earlier_dated[1]) == []
    # The backdated line governs its own date...
    on_2 = state(later_written_earlier_dated, [], "2030-04-02").goal("steps")
    assert on_2["target"] == 9000
    # ...and the later-dated one still governs later days.
    on_10 = state(later_written_earlier_dated, [], "2030-04-10").goal("steps")
    assert on_10["target"] == 12000


# ---- the shape of a transaction time -------------------------------------------

def test_a_transaction_time_must_carry_an_explicit_offset():
    """A bare local timestamp is unorderable against one written elsewhere,
    and this record travels."""
    assert is_stamp("2026-07-31T14:32:05+02:00")
    assert not is_stamp("2026-07-31T14:32:05")
    assert not is_stamp("2026-07-31")
    assert not is_stamp(None)
    problems = validate_record("goals", goal(recorded_at="2030-04-01T09:15:00"))
    assert any("offset" in p for p in problems)


def test_now_stamp_carries_an_offset():
    assert is_stamp(now_stamp())


def test_a_future_stamp_is_not_rejected_per_line():
    """Deliberate: every fixture in this repo is dated 2030 so a synthetic
    record can never be mistaken for a real one. A wall-clock check would
    reject the test corpus and catch nothing monotonicity does not."""
    assert validate_record("goals", goal(recorded_at="2030-04-01T09:15:00+02:00")) == []


# ---- file-level integrity ------------------------------------------------------

def test_an_out_of_order_stamp_is_reported():
    """The check that actually catches a hand-authored value: a human writing
    a plausible timestamp rarely lands it in the right place in the sequence."""
    rows = [(1, goal(recorded_at="2030-04-02T09:00:00+02:00")),
            (2, goal(recorded_at="2030-04-01T09:00:00+02:00"))]
    problems = recorded_at_problems("goals", rows)
    assert any("monotonic" in p for p in problems)


def test_unstamped_rows_never_trip_the_ordering_check():
    rows = [(1, goal(target=1)), (2, goal(target=2)), (3, goal(target=3))]
    assert recorded_at_problems("goals", rows) == []


def test_two_rows_claiming_the_same_instant_are_an_error():
    """Ordering must come from data; two identical stamps means it cannot."""
    same = "2030-04-01T09:00:00+02:00"
    rows = [(1, goal(target=1, recorded_at=same)),
            (2, goal(target=2, recorded_at=same))]
    assert any("same date and recorded_at" in p
               for p in recorded_at_problems("goals", rows))


# ---- the append boundary --------------------------------------------------------

def test_append_stamps_the_clocks_the_machine_owns(tmp_path):
    root = repo(tmp_path)
    row = append(root / "data", "weight",
                 {"date": "2030-05-01", "kg": 79.4, "source": "scale"})
    assert is_stamp(row["recorded_at"])
    assert row["_gen"] == CURRENT_GENERATION["weight"]
    assert row["note"] is None, "missing keys are filled, never omitted"
    assert load(root / "data", "weight") == [row]


def test_append_refuses_an_author_supplied_transaction_time(tmp_path):
    """The whole point: a clock you can write is not a clock, it is another
    opinion. This is the boundary where that is enforceable."""
    root = repo(tmp_path)
    with pytest.raises(ValueError, match="machine-set"):
        append(root / "data", "weight",
               {"date": "2030-05-01", "kg": 79.4, "source": "scale",
                "recorded_at": "2030-05-01T08:00:00+02:00"})


def test_append_refuses_an_invalid_line(tmp_path):
    """An append-only file cannot be un-appended, so a bad line is refused at
    the door rather than corrected later by a superseding line."""
    root = repo(tmp_path)
    with pytest.raises(DataError, match="bad date"):
        append(root / "data", "weight",
               {"date": "the first of May", "kg": 79.4, "source": "scale"})
    assert load(root / "data", "weight") == []


def test_append_refuses_an_unknown_key(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(ValueError, match="stps"):
        append(root / "data", "daily", {"date": "2030-05-01", "stps": 9000})


def test_append_refuses_a_clock_that_moved_backwards(tmp_path):
    from datetime import datetime
    root = repo(tmp_path)
    append(root / "data", "weight",
           {"date": "2030-05-01", "kg": 79.4, "source": "scale"},
           now=datetime(2030, 5, 1, 9, 0))
    with pytest.raises(DataError, match="must not go backwards"):
        append(root / "data", "weight",
               {"date": "2030-05-02", "kg": 79.2, "source": "scale"},
               now=datetime(2030, 4, 30, 9, 0))


def test_append_reaches_both_the_api_and_the_cli(tmp_path, capsys):
    root = repo(tmp_path)
    written = Vitai(root).append("weight", {"date": "2030-05-01", "kg": 79.4,
                                            "source": "scale"})
    assert is_stamp(written["recorded_at"])

    from vitai.cli import main
    import sys
    from io import StringIO
    sys.stdin = StringIO(json.dumps({"date": "2030-05-02", "kg": 79.2,
                                     "source": "scale"}))
    try:
        main(["append", "weight", "--root", str(root)])
    finally:
        sys.stdin = sys.__stdin__
    echoed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert is_stamp(echoed["recorded_at"])
    assert len(load(root / "data", "weight")) == 2


# ---- observation time on weight -------------------------------------------------

def test_measured_at_is_hhmm_not_a_full_timestamp():
    """Deliberately unlike sessions.start_time. A session has a duration and
    can cross a timezone; a weigh-in is a point on a day the row already
    names, and HH:MM is what an athlete can answer from memory."""
    base = {"date": "2030-05-01", "kg": 79.4, "source": "scale", "note": None}
    assert validate_record("weight", {**base, "measured_at": "07:10"}) == []
    assert validate_record("weight", {**base, "measured_at": None}) == []
    assert any("measured_at" in p for p in
               validate_record("weight", {**base, "measured_at": "2030-05-01T07:10:00+02:00"}))
    assert any("measured_at" in p for p in
               validate_record("weight", {**base, "measured_at": "7am"}))


def test_weigh_in_timing_reports_spread_and_its_consequence():
    rows = [{"measured_at": "07:00"}, {"measured_at": "19:00"}]
    t = weigh_in_timing(rows)
    assert t == {"known": 2, "unknown": 0, "spread_h": 12.0, "drift_kg": 1.0}


def test_a_rate_with_no_recorded_times_says_it_cannot_be_checked():
    caveat = timing_caveat(weigh_in_timing([{}, {}]), 0.67)
    assert caveat and "not recorded" in caveat


def test_a_partly_timed_rate_says_which_part_is_unchecked():
    caveat = timing_caveat(weigh_in_timing([{"measured_at": "07:00"}, {}]), 0.67)
    assert caveat and "1 of these weigh-ins" in caveat


def test_a_consistent_morning_routine_gets_no_caveat():
    """Silence is the common outcome. A caveat on every line trains the
    reader to skip it."""
    rows = [{"measured_at": "07:00"}, {"measured_at": "07:20"}]
    assert timing_caveat(weigh_in_timing(rows), 0.67) is None


def test_a_wide_spread_that_rivals_the_rate_is_flagged_with_advice():
    rows = [{"measured_at": "07:00"}, {"measured_at": "19:00"}]
    caveat = timing_caveat(weigh_in_timing(rows), 0.30)
    assert caveat and "12.0 h" in caveat and "consistent time" in caveat


def test_a_tight_spread_beating_a_tiny_rate_states_it_without_blaming(tmp_path):
    """The routine is already tight; what makes the rate unreadable is that it
    is tiny. Telling them to be more consistent would blame the wrong thing."""
    rows = [{"measured_at": "07:00"}, {"measured_at": "07:30"}]
    caveat = timing_caveat(weigh_in_timing(rows), 0.02)
    assert caveat and "not yet separable" in caveat
    assert "consistent time" not in caveat


# ---- the verdict must not outrun the data ---------------------------------------

def test_an_unreadable_rate_does_not_get_an_actionable_verdict(tmp_path):
    """`SLOW - check logging` tells an athlete to cut harder. If the slowness
    is an artifact of weighing at 19:00 half the week, that is the engine
    driving a real deficit off a clock (P3: confidence never launders up)."""
    from datetime import date as _date
    root = repo(tmp_path)
    rows = []
    for i, (day, kg, at) in enumerate([
            ("2030-05-01", 80.0, "07:00"), ("2030-05-03", 80.6, "19:00"),
            ("2030-05-05", 79.9, "07:10"), ("2030-05-07", 80.5, "19:20"),
            ("2030-05-08", 79.9, "07:05")]):
        rows.append({"date": day, "kg": kg, "source": "scale", "note": None,
                     "measured_at": at, "body_fat_pct": None, "kg_lo": None,
                     "kg_hi": None, "body_fat_lo": None, "body_fat_hi": None,
                     "_gen": CURRENT_GENERATION["weight"],
                     "recorded_at": f"{day}T21:0{i}:00+02:00"})
    write(root, "weight", rows)
    text = Vitai(root).rollup(today=_date(2030, 5, 8))
    assert "NOT READABLE" in text or "not yet separable" in text
    assert "SLOW - check logging" not in text


# ---- G25: the per-dataset regression the largest schema move needs --------------

def test_recorded_at_landed_one_generation_past_every_dataset():
    """`recorded_at` touches EVERY dataset at once. A wrong generation does
    not fail loudly - it silently starts REQUIRING the field on lines that
    predate it, which is the exact G25 time bomb the mechanism defuses."""
    for name in KEYS:
        gen = key_generation(name, "recorded_at")
        assert gen == CURRENT_GENERATION[name], name
        assert gen > 1, f"{name}: no existing line can be required to carry it"


def test_every_dataset_carries_the_field():
    for name, keys in KEYS.items():
        assert "recorded_at" in keys, name


def test_the_committed_demo_corpus_still_validates():
    """History stability against a REAL corpus rather than a constructed one:
    the demo holds gen-1, gen-2 and gen-3 lines across thirteen datasets, and
    every one of them predates this change."""
    from pathlib import Path
    from vitai.jsonl import read_lines
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo" / "data"
    if not demo.exists():                                # pragma: no cover
        pytest.skip("demo corpus not generated")
    seen = 0
    for name in KEYS:
        rows, errors = read_lines(demo / f"{name}.jsonl")
        assert errors == [], f"{name}: {errors}"
        assert recorded_at_problems(name, rows) == [], name
        for n, rec in rows:
            assert validate_record(name, rec) == [], f"{name}.jsonl line {n}"
            seen += 1
    assert seen > 100, "the corpus should be substantial enough to mean something"
