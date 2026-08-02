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
    assert any("same instant" in p
               for p in recorded_at_problems("goals", rows))


def test_a_repeated_stamp_is_reported_even_on_different_dates():
    """The narrow same-date check is what let the real defect hide: a bulk
    import stamped 227 rows on 227 different dates identically, and validate
    called the file valid (#44). A serial appender cannot write two rows at
    one instant, whatever they are dated."""
    same = "2030-04-01T09:00:00+02:00"
    rows = [(1, goal(date="2030-04-01", recorded_at=same)),
            (2, goal(date="2030-05-01", recorded_at=same))]
    assert any("same instant" in p
               for p in recorded_at_problems("goals", rows))


def test_stamps_are_compared_as_instants_not_as_text():
    """Two rows written either side of a flight. As strings `+02:00` sorts
    after `+00:00`; as instants the Brussels one came first."""
    rows = [(1, goal(recorded_at="2030-04-01T11:00:00+02:00")),   # 09:00Z
            (2, goal(recorded_at="2030-04-01T10:00:00+00:00"))]   # 10:00Z
    assert recorded_at_problems("goals", rows) == [], "in order by instant"
    backwards = [(1, goal(recorded_at="2030-04-01T10:00:00+00:00")),
                 (2, goal(recorded_at="2030-04-01T11:00:00+02:00"))]
    assert any("precedes" in p for p in recorded_at_problems("goals", backwards))


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

def test_recorded_at_never_lands_on_the_founding_generation():
    """`recorded_at` touches EVERY dataset at once. A wrong generation does
    not fail loudly - it silently starts REQUIRING the field on lines that
    predate it, which is the exact G25 time bomb the mechanism defuses.

    This asserted `gen == CURRENT_GENERATION[name]` until `sessions` moved
    again for #43, which is when it became clear that was pinning a SNAPSHOT
    rather than an invariant: it said recorded_at must remain the newest field
    on every dataset forever, which no schema can promise. The durable
    property is that it postdates the founding generation and does not claim
    to be newer than its own dataset.

    NARROWED AGAIN for the two datasets #171 added, and the docstring above
    already contains the reason: "no EXISTING line can be required to carry
    it". A dataset at generation 1 has no existing lines, so its first line
    and every line after it carries the field and there is nothing to break.
    The invariant is about datasets with a history rather than about the
    field's number.
    """
    for name in KEYS:
        gen = key_generation(name, "recorded_at")
        if CURRENT_GENERATION[name] > 1:
            assert gen > 1, f"{name}: an existing line would be required to "\
                            "carry a field that postdates it"
        assert gen <= CURRENT_GENERATION[name], name


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


# ---- #38: a record holding both timestamp shapes must still build ---------------

def session(date="2030-05-01", type="run", start_time=None, source="watch",
            distance_km=5.0, duration_s=1800, **kw):
    rec = {"date": date, "type": type, "distance_km": distance_km,
           "duration_s": duration_s, "avg_hr": None, "max_hr": None,
           "cadence": None, "kcal": None, "location": None, "rpe": None,
           "note": None, "_gen": 2, "source": source,
           "start_time": start_time, "elevation_m": None, "setting": None,
           "route": None, "place": None, "with": None, "context": None,
           "planned": None, "weather": None}
    rec.update(kw)
    return rec


def test_comparing_a_naive_and_an_aware_timestamp_does_not_raise():
    """The exact reported failure: `TypeError: can't compare offset-naive and
    offset-aware datetimes`, which took the whole build down."""
    from vitai.resolution import _same_activity
    naive = session(start_time="2030-05-01T09:12:53", source="polar")
    aware = session(start_time="2030-05-01T09:12:53+02:00", source="watch")
    assert _same_activity(naive, aware) in {"match", "possible", "distinct"}


def test_a_record_mixing_both_shapes_builds(tmp_path):
    """End to end, because the reported symptom was a traceback out of
    `vitai build`, not a wrong answer."""
    from datetime import date as _date
    root = repo(tmp_path)
    write(root, "sessions", [
        session(start_time="2030-05-01T09:12:53", source="polar"),
        session(start_time="2030-05-01T09:12:53+02:00", source="watch"),
        session(date="2030-05-03", start_time="2030-05-03T18:00:00", source="polar"),
    ])
    Vitai(root).build(today=_date(2030, 5, 4))
    sessions = Vitai(root).canonical("sessions")
    assert sessions, "the build produced canonical sessions rather than raising"


def test_two_platforms_one_walk_still_resolve_to_one_activity(tmp_path):
    """The mixture must not cost the athlete the merge. The timestamp test is
    unavailable, so shape plus disjoint sources decides it - the #16 rule."""
    root = repo(tmp_path)
    write(root, "sessions", [
        session(type="walk", distance_km=6.4, duration_s=4920,
                start_time="2030-05-01T14:05:00+02:00", source="watch"),
        session(type="walk", distance_km=6.38, duration_s=4906,
                start_time="2030-05-01T14:05:11", source="app"),
    ])
    canonical = Vitai(root).canonical("sessions")
    assert len(canonical) == 1
    assert canonical[0]["source"] == "app+watch"


def test_the_undecidable_comparison_is_reported_as_what_it_was(tmp_path):
    """Not as a shape-only merge. Both rows HAVE a start_time - telling the
    athlete to record one they already have would send them nowhere."""
    root = repo(tmp_path)
    write(root, "sessions", [
        session(type="walk", distance_km=6.4, duration_s=4920,
                start_time="2030-05-01T14:05:00+02:00", source="watch"),
        session(type="walk", distance_km=6.38, duration_s=4906,
                start_time="2030-05-01T14:05:11", source="app"),
    ])
    kinds = {n["kind"] for n in Vitai(root).conservation()}
    assert "incomparable_timestamps" in kinds
    assert "shape_only_merge" not in kinds


def test_an_offset_is_never_guessed_for_a_naive_timestamp():
    """The tempting repair, and why it is refused. A platform emitting UTC
    beside a connector writing naive local is the COMMONEST mixed pairing;
    lending the UTC row's +00:00 to a naive +02:00 row places it two hours
    from where it happened, and the result still looks like a clean instant.
    """
    from vitai.clocks import comparable, parse_time
    naive = parse_time("2030-05-01T09:12:53")
    utc = parse_time("2030-05-01T07:12:53+00:00")
    _, _, ok = comparable(naive, utc)
    assert ok is False, "declined, not guessed"


def test_two_aware_timestamps_compare_as_instants_across_offsets():
    """Where the frames ARE known, the comparison is by instant and not by
    wall clock: these two read 09:12 and 07:12 but are the same moment."""
    from vitai.resolution import _same_activity
    brussels = session(start_time="2030-05-01T09:12:53+02:00", source="watch",
                       distance_km=5.0, duration_s=1800)
    utc = session(start_time="2030-05-01T07:12:53+00:00", source="strava",
                  distance_km=9.9, duration_s=1805)      # shapes disagree
    assert _same_activity(brussels, utc) == "match", "only the instant can say so"


def test_two_naive_timestamps_share_a_frame_and_stay_comparable():
    """The existing record is uniformly naive and must keep working: two naive
    values share a frame by construction, so wall-clock order IS instant order
    between them, and a DST fold cannot order them wrongly relative to each
    other."""
    from vitai.resolution import _same_activity
    early = session(start_time="2030-05-01T09:00:00", source="polar",
                    distance_km=5.0, duration_s=1800)
    later = session(start_time="2030-05-01T14:00:00", source="app",
                    distance_km=9.9, duration_s=1805)
    assert _same_activity(early, later) == "distinct"


def test_mixed_shapes_are_reported_as_an_advisory_not_an_error():
    """Naive rows are already on disk and are not wrong. Making them an ERROR
    would leave the record unbuildable from the first converted row until the
    last - blocking the very migration it would be demanding."""
    from vitai.schema import timestamp_advisories
    rows = [(1, session(start_time="2030-05-01T09:00:00")),
            (2, session(start_time="2030-05-02T09:00:00+02:00"))]
    advisories = timestamp_advisories("sessions", rows)
    assert len(advisories) == 1 and "naive" in advisories[0]
    assert all(validate_record("sessions", r) == [] for _, r in rows), "both legal"


def test_a_uniformly_naive_record_has_nothing_to_advise():
    """It is internally consistent. The mixture is what costs something."""
    from vitai.schema import timestamp_advisories
    rows = [(1, session(start_time="2030-05-01T09:00:00")),
            (2, session(start_time="2030-05-02T09:00:00"))]
    assert timestamp_advisories("sessions", rows) == []


# ---- #44: a clock that ties orders nothing --------------------------------------

def test_a_thousand_appends_yield_a_thousand_distinct_stamps(tmp_path):
    """The reported defect: 227 bulk-imported rows got 4 distinct values. On
    this machine it was worse - all 227 shared ONE stamp, because a second is
    an eternity in a write loop and the comparison admitted equal."""
    from datetime import date as _date, timedelta as _td
    root = repo(tmp_path)
    for i in range(1000):
        append(root / "data", "weight",
               {"date": (_date(2030, 1, 1) + _td(days=i)).isoformat(),
                "kg": 80.0 - i * 0.001, "source": "scale"})
    stamps = [r["recorded_at"] for r in load(root / "data", "weight")]
    assert len(stamps) == 1000
    assert len(set(stamps)) == 1000, "every row must be orderable against every other"


def test_stamps_are_strictly_increasing_never_merely_non_decreasing(tmp_path):
    from datetime import date as _date, timedelta as _td
    from vitai.clocks import stamp_instant
    root = repo(tmp_path)
    for i in range(200):
        append(root / "data", "weight",
               {"date": (_date(2030, 1, 1) + _td(days=i)).isoformat(),
                "kg": 80.0, "source": "scale"})
    instants = [stamp_instant(r["recorded_at"])
                for r in load(root / "data", "weight")]
    assert all(b > a for a, b in zip(instants, instants[1:]))


def test_the_serialised_stamp_carries_microseconds(tmp_path):
    """A second-resolution format cannot satisfy the test above even in
    principle, so the resolution is asserted directly rather than left to be
    inferred from a loop that happens to be slow enough."""
    root = repo(tmp_path)
    row = append(root / "data", "weight",
                 {"date": "2030-05-01", "kg": 79.4, "source": "scale"})
    assert "." in row["recorded_at"].split("+")[0].split("-")[-1]
    seconds_field = row["recorded_at"].split("T")[1].split("+")[0]
    assert len(seconds_field.split(".")[1]) == 6


def test_wall_clock_is_used_whenever_it_has_moved_on(tmp_path):
    """The logical clock only steps in to break a tie. Where real time has
    advanced, the stamp is the truth and not an accumulating fiction."""
    from datetime import datetime as _dt
    root = repo(tmp_path)
    first = append(root / "data", "weight",
                   {"date": "2030-05-01", "kg": 79.4, "source": "scale"},
                   now=_dt(2030, 5, 1, 9, 0, 0))
    second = append(root / "data", "weight",
                    {"date": "2030-05-02", "kg": 79.2, "source": "scale"},
                    now=_dt(2030, 5, 1, 10, 0, 0))
    assert first["recorded_at"].startswith("2030-05-01T09:00:00")
    assert second["recorded_at"].startswith("2030-05-01T10:00:00")


def test_a_tie_is_broken_by_one_tick_not_by_a_second(tmp_path):
    """Two rows written at the same wall-clock instant still order, and the
    stamp stays within a microsecond of the truth rather than inventing a
    later second."""
    from datetime import datetime as _dt
    from vitai.clocks import stamp_instant
    root = repo(tmp_path)
    at = _dt(2030, 5, 1, 9, 0, 0)
    a = append(root / "data", "weight",
               {"date": "2030-05-01", "kg": 79.4, "source": "scale"}, now=at)
    b = append(root / "data", "weight",
               {"date": "2030-05-02", "kg": 79.2, "source": "scale"}, now=at)
    ia, ib = stamp_instant(a["recorded_at"]), stamp_instant(b["recorded_at"])
    assert ib > ia
    assert (ib - ia).total_seconds() < 0.001


def test_a_validate_run_after_a_bulk_append_is_clean(tmp_path, capsys):
    """End to end, because the symptom was `validate` reporting 24 problems
    about rows the engine's own helper had written."""
    from datetime import date as _date, timedelta as _td
    from vitai.cli import main
    root = repo(tmp_path)
    Vitai(root).append_many("weight", [
        {"date": (_date(2030, 1, 1) + _td(days=i)).isoformat(),
         "kg": 80.0 - i * 0.01, "source": "scale"} for i in range(227)])
    main(["validate", "--root", str(root)])
    out = capsys.readouterr().out
    assert "all data lines valid" in out
    assert "same instant" not in out


# ---- #44: the batch primitive bulk import needs ---------------------------------

def test_append_many_stamps_every_row_distinctly(tmp_path):
    from datetime import date as _date, timedelta as _td
    root = repo(tmp_path)
    rows = Vitai(root).append_many("weight", [
        {"date": (_date(2030, 1, 1) + _td(days=i)).isoformat(),
         "kg": 80.0, "source": "scale"} for i in range(2000)])
    assert len({r["recorded_at"] for r in rows}) == 2000


def test_a_batch_with_one_bad_row_writes_nothing(tmp_path):
    """An append-only file cannot be un-appended, so a partial batch would
    leave the caller to work out how far it got."""
    root = repo(tmp_path)
    with pytest.raises(DataError, match="nothing was written"):
        Vitai(root).append_many("weight", [
            {"date": "2030-05-01", "kg": 79.4, "source": "scale"},
            {"date": "the second of May", "kg": 79.2, "source": "scale"},
        ])
    assert load(root / "data", "weight") == []


def test_a_batch_continues_the_clock_from_what_is_already_on_disk(tmp_path):
    """The file is the clock's memory, so two separate imports cannot collide
    even if they start within the same second."""
    from vitai.clocks import stamp_instant
    root = repo(tmp_path)
    first = Vitai(root).append_many(
        "weight", [{"date": "2030-05-01", "kg": 79.4, "source": "scale"}])
    second = Vitai(root).append_many(
        "weight", [{"date": "2030-05-02", "kg": 79.2, "source": "scale"}])
    assert stamp_instant(second[0]["recorded_at"]) > stamp_instant(
        first[0]["recorded_at"])


def test_the_cli_accepts_jsonl_so_a_bulk_import_is_one_invocation(tmp_path, capsys):
    import sys
    from io import StringIO
    from vitai.cli import main
    root = repo(tmp_path)
    capsys.readouterr()                      # discard `init`'s own output
    payload = "\n".join(json.dumps(
        {"date": f"2030-05-{i + 1:02d}", "kg": 80.0 - i * 0.1, "source": "scale"})
        for i in range(5))
    sys.stdin = StringIO(payload)
    try:
        main(["append", "weight", "--root", str(root)])
    finally:
        sys.stdin = sys.__stdin__
    echoed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(echoed) == 5
    assert len({r["recorded_at"] for r in echoed}) == 5


# ---- an unstamped line among stamped ones (#149) ---------------------------------

def test_a_wholly_unstamped_file_is_a_legacy_corpus():
    """`known_by` lets an unstamped row survive every cutoff, which is right:
    a legacy line lacks a transaction time by PREDATING the clock, and
    without the affordance `as_of` would empty a legacy corpus instead of
    reconstructing one."""
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": "2030-01-01"}), (2, {"date": "2030-02-01"})]
    assert unstamped_after_the_clock_started("weight.jsonl", rows) == []


def test_an_unstamped_row_predating_the_clock_is_fine():
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": "2030-01-01"}),
            (2, {"date": "2030-05-01",
                 "recorded_at": "2030-05-01T09:00:00+02:00"})]
    assert unstamped_after_the_clock_started("weight.jsonl", rows) == []


def test_an_unstamped_row_inside_the_stamped_era_is_flagged():
    """A forgotten workout appended by hand with no stamp is visible at EVERY
    historical cutoff, so a reconstruction stops being stable - which is the
    one property `as_of` exists to provide."""
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": "2030-05-01",
                 "recorded_at": "2030-05-01T09:00:00+02:00"}),
            (2, {"date": "2030-05-02",
                 "recorded_at": "2030-05-02T09:00:00+02:00"}),
            (3, {"date": "2030-06-01"})]
    found = unstamped_after_the_clock_started("weight.jsonl", rows)
    assert found and "was already running" in found[0]
    # It names the DATE of the offending row, not its line - see
    # test_the_advisory_names_the_dates_rather_than_a_line_number.
    assert "2030-06-01" in found[0]


def test_the_rule_reads_the_clock_rather_than_file_position():
    """File position was the obvious signal and is the wrong one: #37
    established that an ordering a formatter can change is not an ordering,
    and a regenerated file is written sorted. An unstamped row sitting AFTER
    a stamped one but dated before it is a legacy row that got sorted there.
    """
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": "2030-05-01",
                 "recorded_at": "2030-05-01T09:00:00+02:00"}),
            (2, {"date": "2030-04-01"})]
    assert unstamped_after_the_clock_started("weight.jsonl", rows) == []


def test_it_is_an_advisory_and_never_fails_a_build(tmp_path, capsys):
    """Making it an error would make a legacy record unbuildable until every
    row was rewritten - which is the migration the rule would be demanding."""
    import json

    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "weight.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None,
         "recorded_at": "2030-05-01T09:00:00+02:00"},
        {"date": "2030-05-02", "kg": 79.8, "source": "scale", "note": None,
         "recorded_at": "2030-05-02T09:00:00+02:00"},
        {"date": "2030-06-01", "kg": 79.0, "source": "scale", "note": None},
    ]) + "\n", encoding="utf-8")
    capsys.readouterr()
    main(["validate", "--root", str(root)])
    out = capsys.readouterr().out
    assert "was already running" in out
    # One prefix, not two. The message carried its own "advisory: " while the
    # caller adds "ADVISORY: ", so it printed "ADVISORY: advisory:".
    assert "ADVISORY: advisory:" not in out
    # And it names no file or line: `validate` hands this the merged stream
    # across every device file, so a line number belongs to whichever file it
    # came from and naming one points at the wrong row.
    assert "weight.jsonl line" not in [
        ln for ln in out.splitlines() if "was already running" in ln][0]


def test_a_stamped_row_with_no_date_does_not_flag_every_legacy_row():
    """`min` over the dates included the empty string for a dateless stamped
    row, so the floor became "" - every legacy row sorted after it, and the
    message named a blank date."""
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": None, "recorded_at": "2030-05-01T09:00:00+02:00"}),
            (2, {"date": "2030-06-01",
                 "recorded_at": "2030-06-01T09:00:00+02:00"}),
            (3, {"date": "2020-01-01"})]
    assert unstamped_after_the_clock_started("weight.jsonl", rows) == []


def test_the_advisory_names_the_dates_rather_than_a_line_number():
    """Across device files the line numbers belong to different files, so one
    of them points at the wrong row."""
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(1, {"date": "2030-05-01",
                 "recorded_at": "2030-05-01T09:00:00+02:00"}),
            (2, {"date": "2030-05-02",
                 "recorded_at": "2030-05-02T09:00:00+02:00"}),
            (1, {"date": "2030-06-01"})]
    found = unstamped_after_the_clock_started("weight.jsonl", rows)
    assert "2030-06-01" in found[0]
    assert "line 1" not in found[0]
    assert not found[0].startswith("advisory")


def test_a_couple_of_stamped_rows_do_not_start_a_clock_for_a_legacy_file():
    """The demo's sessions came from an export that does not stamp, plus one
    stamped provenance pair. Treating any stamp as the start of the clock
    flagged eight ordinary legacy rows in the flagship corpus - the advisory
    firing on the normal case, which is how an advisory teaches people to
    ignore it."""
    from vitai.schema import unstamped_after_the_clock_started
    rows = [(n, {"date": f"2030-04-{n:02d}"}) for n in range(1, 21)]
    rows[9] = (10, {"date": "2030-04-10",
                    "recorded_at": "2030-04-10T09:00:00+02:00"})
    assert unstamped_after_the_clock_started("weight.jsonl", rows) == []


def test_a_legacy_device_file_is_not_outvoted_by_a_stamped_sibling(tmp_path,
                                                                   capsys):
    """The rule is per FILE, and a file is what has a clock. Run on the
    merged multi-device stream, `weight.jsonl` being wholly unstamped - the
    case the first guard exists to exempt - lost the majority vote to a
    stamped `weight.watch.jsonl`, and every one of its legacy rows was
    flagged as a hand edit.
    """
    import json

    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    data = root / "data"
    (data / "weight.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2030-03-{n:02d}", "kg": 80.0, "source": "scale",
         "note": None}) for n in range(1, 6)) + "\n", encoding="utf-8")
    (data / "weight.watch.jsonl").write_text("\n".join(json.dumps(
        {"date": f"2030-01-{n:02d}", "kg": 80.0, "source": "scale",
         "note": None, "recorded_at": f"2030-01-{n:02d}T09:00:00+02:00"})
        for n in range(1, 12)) + "\n", encoding="utf-8")
    capsys.readouterr()
    main(["validate", "--root", str(root)])
    assert "was already running" not in capsys.readouterr().out


def test_findings_come_back_in_date_order(tmp_path):
    """Emitting the ambiguous findings and then the normal ones gave a list
    sorted within each group and out of order overall."""
    from vitai.meals import day_disagreements
    meals = [{"date": "2030-01-05", "meal": "lunch", "item": "x",
              "grams": 100, "kcal_100g": 100, "food_table": "usda"},
             {"date": "2030-09-09", "meal": "lunch", "item": "x",
              "grams": 100, "kcal_100g": 100, "food_table": "usda"}]
    daily = [{"date": "2030-09-09", "kcal_in": 1, "source": "a"},
             {"date": "2030-09-09", "kcal_in": 2, "source": "b"},
             {"date": "2030-01-05", "kcal_in": 2200, "source": "mfp-export"}]
    got = day_disagreements(meals, daily)
    assert [f["date"] for f in got] == ["2030-01-05", "2030-09-09"]


def test_the_wall_clock_is_read_at_the_boundary_and_nowhere_below_it():
    """Eleven methods read `date.today()` for themselves. A build straddling
    midnight therefore answered two different questions, no caller could pin
    the viewpoint without passing it to every method, and there was nothing
    for an artifact to record afterwards.

    Mechanical on purpose: this is a property of where the clock is read, and
    a reviewer cannot see it by reading any one method.
    """
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "vitai" / "api.py").read_text(encoding="utf-8")
    body = src[src.index("    @property"):]  # everything after __init__
    reads = [ln.strip() for ln in body.splitlines()
             if re.search(r"date\.today\(\)|datetime\.now\(", ln)
             and not ln.lstrip().startswith("#")]
    assert reads == [], reads


def _dated_repo(tmp_path):
    """A repo whose answers actually move with the viewpoint.

    `examples/demo` has no medical episodes, gates or escalations, so most of
    these methods return an empty list on every date - and comparing empty to
    empty certifies nothing. Each method below is checked for DISCRIMINATION
    first, so a fixture that stops exercising one fails loudly instead of
    quietly passing.
    """
    import json

    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    (root / "data" / "medical.jsonl").write_text(json.dumps(
        {"date": "2030-06-01", "slug": "chest", "kind": "symptom",
         "title": "chest tightness", "body_site": "chest",
         "severity": "red_flag", "status": "open", "resolved_date": None,
         "restricts": "all", "provider_type": None, "source": "athlete",
         "note": None, "expects": None, "onset_date": "2030-06-01",
         "precondition": "hop-test", "restriction": None}) + "\n"
        # Closed by a LATER LINE rather than by editing the first: the
        # episode is open on 2 June and closed on 15 July, which is what
        # makes the viewpoint observable at all.
        + json.dumps(
        {"date": "2030-06-30", "slug": "chest", "kind": "symptom",
         "title": "chest tightness", "body_site": "chest",
         "severity": "red_flag", "status": "resolved",
         "resolved_date": "2030-06-30", "restricts": "all",
         "provider_type": None, "source": "athlete", "note": None,
         "expects": None, "onset_date": "2030-06-01",
         "precondition": "hop-test", "restriction": None}) + "\n",
        encoding="utf-8")
    (root / "data" / "events.jsonl").write_text(json.dumps(
        {"date": "2030-05-01", "slug": "spring-10k",
         "title": "a 10k somewhere", "kind": "race",
         "event_date": "2030-07-01", "priority": "a", "immovable": True,
         "place": None, "status": "planned", "set_by": "athlete",
         "reason": None, "note": None}) + "\n", encoding="utf-8")
    return root


def test_the_viewpoint_threads_to_every_method_that_takes_one(tmp_path):
    """`self.on` has to be the default each method falls back to, or pinning
    it at construction is decoration - the caller would still have to pass it
    everywhere, which is the thing it exists to stop.
    """
    from datetime import date

    from vitai.api import Vitai
    root = _dated_repo(tmp_path)
    # `inside` sits inside `urgent_now`'s one-day window around the episode's
    # own date, or `urgent` and the banner come back empty on both viewpoints
    # and certify nothing.
    inside, outside = date(2030, 6, 2), date(2030, 7, 15)
    loose = Vitai(root)
    # `checks` and `safety` are deliberately absent. There, `on=None` means
    # EVERY date rather than today - `escalations` applies no cutoff at all
    # without one - so defaulting them to the viewpoint would silently turn
    # "everything the record justifies" into "today's". Not every optional
    # `on` is a clock, and the ones that are not must keep their meaning.
    for name in ("episodes", "gates", "pending_checks", "urgent",
                 "safety_banner", "events"):
        method = getattr(loose, name)
        assert method(inside) != method(outside), (
            f"{name} does not move with the viewpoint on this fixture, so "
            f"comparing it proves nothing")
        assert getattr(Vitai(root, on=inside), name)() == method(inside), name


def test_the_viewpoint_is_not_re_read_per_access(tmp_path):
    """Read per method, a build crossing midnight answered half its questions
    on one day and half on the next. A property that re-read the clock would
    reintroduce exactly that while looking identical from outside.
    """
    import datetime as real

    from vitai.api import Vitai
    import vitai.api as api
    engine = Vitai(_dated_repo(tmp_path))
    first = engine.on

    class Moved(real.date):
        @classmethod
        def today(cls):
            return real.date(1999, 1, 1)

    api.date = Moved
    try:
        assert engine.on == first
    finally:
        api.date = real.date


def test_a_viewpoint_of_the_wrong_type_is_refused_at_the_boundary(tmp_path):
    """`as_of` validates one line below and `on` did not, so a `str` - the
    natural call, since every per-call `on` here takes `date | str` - left
    half the engine working and half raising AttributeError from somewhere
    that never mentioned the constructor. A `datetime` was worse: it
    subclasses `date`, so it passed every isinstance check in the codebase
    and died comparing a datetime to a date.
    """
    from datetime import date, datetime

    import pytest

    from vitai.api import Vitai
    root = _dated_repo(tmp_path)
    assert Vitai(root, on="2030-06-15").on == date(2030, 6, 15)
    with pytest.raises(TypeError, match="as_of"):
        Vitai(root, on=datetime(2030, 6, 15, 14, 30))
    with pytest.raises(TypeError):
        Vitai(root, on=20300615)


def test_a_pinned_window_does_not_fall_through_to_the_wall_clock(tmp_path):
    """`query.window` anchors to the last logged session, which is right. Its
    empty-record branch reached for the wall clock, so a pinned instance on a
    repo with no sessions returned today's real week.
    """
    from datetime import date

    from vitai.api import Vitai
    got = Vitai(_dated_repo(tmp_path), on=date(2030, 6, 15)).window(days=7)
    assert got["to"] == "2030-06-15" and got["from"] == "2030-06-09"


def test_no_module_reads_the_wall_clock_during_a_build(tmp_path):
    """The behavioural half of the check above, and it caught what the source
    check could not: `rollup` passed its own UN-defaulted `today` straight
    into `build_report`, which fell back to `date.today()` itself. Every
    table honoured the pinned viewpoint and the report around them was dated
    by the wall clock - a rollup that disagreed with its own contents.

    Nothing in `api.py` was wrong to read, so a source scan of that one file
    could not see it. This watches every module instead.
    """
    import datetime as real
    import importlib
    import pkgutil
    import shutil
    from pathlib import Path

    import vitai
    from vitai.api import Vitai

    reads: list[str] = []

    class Meta(type):
        # `isinstance(a_real_date, Watched)` must stay true, or the engine's
        # own `isinstance(on, date)` branches take the wrong path and the
        # probe measures its own instrumentation.
        def __instancecheck__(cls, obj):
            return isinstance(obj, real.date)

    class Watched(real.date, metaclass=Meta):
        @classmethod
        def today(cls):
            import traceback
            frame = traceback.extract_stack()[-2]
            reads.append(f"{Path(frame.filename).name}:{frame.lineno}")
            return real.date(2030, 7, 1)

    patched: list = []
    try:
        # INSIDE the try. Patching before it meant a failure part-way through
        # the loop left the already-patched modules answering 2030-07-01 for
        # the rest of the session.
        for mod in pkgutil.iter_modules(vitai.__path__):
            module = importlib.import_module(f"vitai.{mod.name}")
            if getattr(module, "date", None) is real.date:
                module.date = Watched
                patched.append(module)
        assert patched, "nothing was instrumented, so this proves nothing"
        root = tmp_path / "demo"
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "examples" / "demo", root)
        engine = Vitai(root, on=real.date(2030, 6, 20))
        engine.build()
        engine.rollup()
        engine.safety()
        engine.goals()
        engine.churn()
        engine.events()
        assert reads == [], reads
    finally:
        for module in patched:
            module.date = real.date


def test_the_viewpoint_reaches_the_context_lookup(tmp_path):
    """`context` was one of the eleven changed call sites and neither test
    above reaches it - the fixture has no context rows, so it answers None on
    every date."""
    import json
    from datetime import date

    from vitai.api import Vitai
    root = _dated_repo(tmp_path)
    # TWO rows. Context carries forward from the most recent row at or
    # before the date, so a single row answers the same thing on every later
    # viewpoint and the comparison would prove nothing.
    (root / "data" / "context.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"date": "2030-06-02", "mode": "travel", "facilities": None,
         "place": None, "source": "athlete", "note": "away"},
        {"date": "2030-07-01", "mode": "home", "facilities": None,
         "place": None, "source": "athlete", "note": "back"},
    ]) + "\n", encoding="utf-8")
    assert Vitai(root, on=date(2030, 6, 2)).context()["mode"] == "travel"
    assert Vitai(root, on=date(2030, 7, 15)).context()["mode"] == "home"


def test_verdicts_take_a_viewpoint_they_do_not_read():
    """A parameter nothing consumes is worse than no parameter: `verdicts`,
    `churn` and the `today=` threaded through `build` all reach
    `compute_verdicts`, which never references it.

    So the viewpoint does NOT govern verdicts, and this records that rather
    than letting the signature imply otherwise. Delete this test when
    `compute_verdicts` starts reading its clock - it will fail then, which is
    the point.
    """
    import ast
    import inspect

    from vitai import verdicts
    tree = ast.parse(inspect.getsource(verdicts.compute_verdicts))
    fn = tree.body[0]
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "today" in {a.arg for a in fn.args.args}
    assert "today" not in used, (
        "compute_verdicts now reads its viewpoint - good; delete this test "
        "and add verdicts back to the threading test above")
