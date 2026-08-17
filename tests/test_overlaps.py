"""The paired-measurement window as its own dataset (#413).

`comparability` DECLARES that two origins may be read across and cites the
evidence for it. Until contract 53 that citation was `overlap_ref`, free prose,
and on the corpus's one measured row it read "101 run(s) both instruments
recorded, 2030-01-06 to 2030-06-30" - the census in English. A reference that is
a sentence is not a reference: nothing can follow it, nothing can count it, and
a client deciding whether to trust the figure has to parse the sentence or give
up.

TWO RULES CARRY THIS FILE, and the tests are organised under them.

A WINDOW IS EARNED, NEVER ASSERTED, which is the rule `comparability` itself
rests on, one level down. A census exists because two origins were compared over
dates both covered. What one line can prove of that is bounded and the bound is
tested rather than glossed: `validate_record` sees one row, so it refuses the
census that could not have come from any record - fewer paired days than the
engine will measure at all, more days than the window holds - and the census is
checked against the readings it claims to count in
`test_the_corpus_census_is_what_the_engine_counts`, which is the only place that
can be done.

AND EXACTLY ONE SHAPE OF EVIDENCE, never two. The statistics are NOT here: the
median and the two ends of the measured difference went onto the `comparability`
row at contract 52 and stay there. What this dataset holds is what that row
cannot - the size of the comparison - and where it holds it, the sentence is
refused rather than tolerated, because two carriers of one fact drift and the
prose copy is the one nothing can check.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

from vitai.api import Vitai
from vitai.calibration import overlap_calibration
from vitai.policy import comparability, overlap
from vitai.schema import (KEYS, MIN_PAIRS, census_is_earned,
                          overlap_evidence_problems,
                          overlap_timing_advisories, validate_record)

ROOT = Path(__file__).resolve().parents[1]
VERA = ROOT / "tests" / "fixtures" / "personas" / "vera"
DEMO = ROOT / "examples" / "demo"


def row(**kw) -> dict:
    """A complete `overlaps` line, so a test changes exactly one thing."""
    base = {"date": "2030-06-30", "dataset": "sessions",
            "field": "distance_km", "origin_a": "phone", "origin_b": "watch",
            "paired_days": 101, "dropped_days": 0,
            "from_date": "2030-01-06", "to_date": "2030-06-30",
            "source": "athlete", "note": None, "supersedes": None,
            "recorded_at": "2030-06-30T22:00:00+01:00", "device": None}
    base.update(kw)
    return base


def crow(**kw) -> dict:
    """A complete `comparability` line, same reason."""
    base = {"date": "2030-06-30", "field": "distance_km",
            "origin_a": "phone", "origin_b": "watch", "status": "offset",
            "bias": 0.0, "spread": 1.26, "difference_lo": -0.03,
            "difference_hi": 1.23, "basis": "overlap", "overlap_ref": None,
            "note": None, "source": "athlete", "supersedes": None,
            "recorded_at": "2030-06-30T21:00:00+01:00", "device": None}
    base.update(kw)
    return base


def rows(root: Path, dataset: str) -> list[dict]:
    path = root / "data" / f"{dataset}.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


# --- the dataset exists and is shaped the way the record reads it ------------

def test_the_dataset_is_registered_with_the_columns_it_needs():
    assert KEYS["overlaps"] == [
        "date", "dataset", "field", "origin_a", "origin_b", "paired_days",
        "dropped_days", "from_date", "to_date", "source", "note",
        "supersedes", "recorded_at", "device"]


def test_the_statistics_are_deliberately_not_here():
    """THE REFUSAL, PINNED. The proposal that named this dataset listed the
    median, the low and the high among its columns. Contract 52 put all three
    on the `comparability` row one contract earlier, held to each other by
    `_difference_range_problems` - so carrying them here as well would be one
    width stated in two datasets, kept honest by a cross-dataset rule.

    Pinned as a test rather than left to a comment because the pressure to add
    them is real and recurring: every reader of a census will want the numbers
    beside it, and the answer is that they are one join away on the row that
    DECLARES, which is where a statistic about a difference belongs.
    """
    for name in ("bias", "spread", "difference_lo", "difference_hi",
                 "median", "low", "high"):
        assert name not in KEYS["overlaps"], name
    for name in ("bias", "spread", "difference_lo", "difference_hi"):
        assert name in KEYS["comparability"], name


def test_the_read_model_has_a_column_for_every_field():
    """A column a consumer cannot select is a column that does not exist."""
    import sqlite3

    con = sqlite3.connect(Vitai(VERA).build())
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(overlaps)")]
        assert [c for c in KEYS["overlaps"] if c in cols] == KEYS["overlaps"]
        counted = con.execute(
            "SELECT paired_days, dropped_days, from_date, to_date "
            "FROM overlaps").fetchall()
        assert counted == [(101, 0, "2030-01-06", "2030-06-30")]
    finally:
        con.close()


# --- a window is EARNED ------------------------------------------------------

def test_a_complete_census_validates():
    assert validate_record("overlaps", row()) == []
    assert census_is_earned(row())


def test_a_window_below_the_engines_floor_is_refused():
    """THE CORE EARN RULE. `MIN_PAIRS` is the count below which the engine
    refuses to measure a window at all, so a line claiming fewer is claiming a
    measurement that would not have been made.

    Asserted against the constant rather than against `3`, so moving the
    threshold moves this test with it rather than leaving a literal behind.
    """
    thin = row(paired_days=MIN_PAIRS - 1, from_date="2030-06-28")
    problems = validate_record("overlaps", thin)
    assert any("paired_days" in p and "at least" in p for p in problems), problems
    assert not census_is_earned(thin)

    # And the mutation control: one MORE day and the same line is a window.
    ok = row(paired_days=MIN_PAIRS, from_date="2030-06-28")
    assert validate_record("overlaps", ok) == []
    assert census_is_earned(ok)


def test_a_window_cannot_hold_more_days_than_it_has():
    """THE ARITHMETIC THAT SEPARATES A COUNT FROM A NUMBER SOMEBODY LIKED.

    Every day of the overlap either paired or was dropped, never both, and
    there is at most one of each per date - so the two counts together cannot
    exceed the span. This is the strongest thing one line can say about
    whether the census was counted, and it is worth having precisely because
    the re-derivation that would say more is not available here.
    """
    span = row(from_date="2030-06-01", to_date="2030-06-30")  # 30 days
    problems = validate_record("overlaps", span)
    assert any("cannot hold more days than it has" in p for p in problems), problems
    assert not census_is_earned(span)

    # Exactly full is legal: 30 days, 25 paired and 5 dropped.
    exact = row(from_date="2030-06-01", to_date="2030-06-30",
                paired_days=25, dropped_days=5)
    assert validate_record("overlaps", exact) == []
    # One more dropped day and the same window cannot hold them.
    over = dict(exact, dropped_days=6)
    assert any("cannot hold more days" in p
               for p in validate_record("overlaps", over))


def test_both_counts_are_required_and_are_whole_days():
    for missing in ("paired_days", "dropped_days"):
        problems = validate_record("overlaps", row(**{missing: None}))
        assert any(missing in p and "required" in p for p in problems), problems
    assert any("dropped_days" in p
               for p in validate_record("overlaps", row(dropped_days=-1)))
    # HALF A DAY NEITHER PAIRED NOR DROPPED: registered in `_TYPES` as an
    # integer, so a float is refused by the generic check rather than by a
    # hand-rolled one here.
    assert any("paired_days" in p
               for p in validate_record("overlaps", row(paired_days=101.5)))
    assert any("paired_days" in p
               for p in validate_record("overlaps", row(paired_days="many")))


def test_the_window_is_an_interval_and_runs_forwards():
    backwards = row(from_date="2030-06-30", to_date="2030-01-06")
    assert any("before" in p for p in validate_record("overlaps", backwards))
    assert not census_is_earned(backwards)
    for bad in (None, "the spring", "2030-13-01"):
        assert any("from_date" in p
                   for p in validate_record("overlaps", row(from_date=bad)))


def test_the_census_says_which_readings_it_counted():
    """`dataset` IS THE COLUMN THIS DATASET EXISTS TO HAVE, and the reason is
    measurable rather than stylistic: `distance_km` is a column of `daily` AND
    of `sessions`, so a census without it cannot be followed back to the
    readings - which is the sentence's own defect one level down.
    """
    assert {ds for ds in KEYS if "distance_km" in KEYS[ds]} >= {"daily",
                                                                "sessions"}
    assert any("dataset" in p
               for p in validate_record("overlaps", row(dataset="runs")))
    assert any("field" in p
               for p in validate_record("overlaps", row(field="distance_km",
                                                        dataset="weight")))
    # A column that is not a QUANTITY two instruments could disagree about.
    assert any("field" in p
               for p in validate_record("overlaps", row(field="note")))


def test_two_different_instruments_or_there_is_nothing_to_pair():
    same = row(origin_a="watch", origin_b="watch")
    assert any("DIFFERENT" in p for p in validate_record("overlaps", same))
    assert not census_is_earned(same)
    assert any("origin_b" in p
               for p in validate_record("overlaps", row(origin_b=None)))


def test_a_date_that_matches_the_shape_and_does_not_exist_is_reported():
    """A VALIDATOR THAT RAISES ON THE LINE IT EXISTS TO DESCRIBE IS WORSE THAN
    ONE THAT GETS THE LINE WRONG.

    `DATE_RE` checks the SHAPE of a date. `2030-02-30` matches it and does not
    exist; `"2030-06-30\n"` matches it too, because the pattern ends in `$` and
    a JSON string may carry a trailing newline. Either one parses, so
    `jsonl.load` will not quarantine it, and it reaches the validator and the
    seam gate intact. The first version of this dataset called
    `date.fromisoformat` on both and took down `vitai validate`, `vitai build`,
    the verdicts and the rollup with a ValueError - every surface of the
    record, from one line nobody could be told about.
    """
    for bad in ("2030-02-30", "2029-02-29", "2030-06-30\n", "2030-13-01"):
        for field in ("from_date", "to_date", "date"):
            rec = row(**{field: bad})
            problems = validate_record("overlaps", rec)
            assert problems, (field, bad)
            assert census_is_earned(rec) is False, (field, bad)
    # And the whole cross-dataset path stays a report rather than a crash.
    assert overlap_evidence_problems([crow()], [row(from_date="2030-02-30")])


def test_a_census_cannot_predate_the_window_it_counted():
    """`date` is when the record made the statement and `to_date` is the last
    day it claims to have counted, so a row dated first is evidence about days
    that had not happened yet. The engine's writer always stamps them equal;
    nothing checked that a hand-written line did, and `policy` resolves
    censuses as-of a viewpoint - so a backdated one would earn a declaration
    for weeks its own window had not reached."""
    early = row(date="2030-03-01")
    problems = validate_record("overlaps", early)
    assert any("before the days it counted" in p for p in problems), problems
    assert not census_is_earned(early)
    # Dated ON the last paired day is what the engine writes, and is legal.
    assert validate_record("overlaps", row(date="2030-06-30")) == []
    # Later is legal too: counting a window up is an act with its own date.
    assert validate_record("overlaps", row(date="2030-08-01")) == []


def test_the_gate_refuses_every_input_the_validator_refuses():
    """THE INVARIANT, ASSERTED RATHER THAN ASSUMED: only a census that
    validates can earn.

    The first version of `census_is_earned` restated the validator's rules
    instead of asking it, and drifted inside one review - it left out the
    checks on `dataset` and `field`, so a census naming a dataset that does
    not exist was reported by `vitai validate` and honoured by the seam gate
    at the same time. Every mutation below was green against the suite before
    this test existed.
    """
    refused = [
        row(dataset="banana"),                      # no such dataset
        row(dataset="weight"),                      # field not on it
        row(field="note"),                          # not a measurement
        row(origin_a=""), row(origin_a=None),       # identity not a string
        row(origin_a="watch"),                      # both the same
        row(paired_days=101.0),                     # not a whole day
        row(paired_days=True),                      # bool is not a count
        row(paired_days="101"),                     # a numeral is not a number
        row(dropped_days=None),                     # required
        row(dropped_days=-1),                       # negative days
        row(paired_days=2, from_date="2030-06-29"),  # below MIN_PAIRS
        row(from_date="2030-07-01"),                # window runs backwards
        row(from_date="banana"),                    # not a date at all
        row(from_date="2030-06-01"),                # more days than it spans
        row(date="2030-01-01"),                     # predates its own window
    ]
    for rec in refused:
        assert validate_record("overlaps", rec), rec
        assert census_is_earned(rec) is False, rec
    # And the one that passes both.
    assert validate_record("overlaps", row()) == []
    assert census_is_earned(row()) is True


def test_a_census_the_validator_rejects_lifts_nothing():
    """The invariant above, at the surface that matters. A dataset name the
    record does not have is not a hand-wave: it is the difference between a
    census about her runs and a census about nothing."""
    declared = crow(status="comparable", bias=None, spread=None,
                    difference_lo=None, difference_hi=None)
    for bad in (row(dataset="banana"), row(paired_days=101.0),
                row(from_date="2030-02-30"), row(date="2030-01-01")):
        assert comparability([declared], "distance_km", "phone", "watch",
                             "2030-07-01", [bad])["status"] == "not_comparable"


def test_a_record_carrying_an_impossible_date_still_validates_rather_than_dying():
    """END TO END, because the crash this pins was not visible from any unit:
    the line parses, so it reaches `validate` through the ordinary load path."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "record"
        shutil.copytree(VERA, root)
        (root / "data" / "overlaps.jsonl").write_text(
            json.dumps(row(from_date="2030-02-30", _gen=1)) + "\n",
            encoding="utf-8")
        report = Vitai(root).validate()
        assert report["problems"], "the bad line has to be reported"
        assert any("from_date" in p for p in report["problems"])


def test_a_declaration_whose_only_census_postdates_it_is_flagged():
    """`overlap_evidence_problems` asks whether a census EXISTS; `policy` asks
    whether one was in force on the date being judged. Those were one question
    while the evidence was a sentence, because a sentence travels on the row.
    They can differ now, and the difference is silent without this."""
    declared = crow(date="2030-06-30", status="comparable", bias=None,
                    spread=None, difference_lo=None, difference_hi=None)
    late = row(date="2030-07-15")
    # Green on the problem side, which is correct: the row is legal.
    assert overlap_evidence_problems([declared], [late]) == []
    # And the seam really is refused before the census.
    assert comparability([declared], "distance_km", "phone", "watch",
                         "2030-07-01", [late])["status"] == "not_comparable"
    # So the advisory says so, naming the date it starts being honoured.
    said = overlap_timing_advisories([declared], [late])
    assert any("2030-07-15" in a and "unevidenced before it" in a
               for a in said), said
    # A census dated with the declaration says nothing.
    assert overlap_timing_advisories([declared], [row(date="2030-06-30")]) == []
    # Nor does one on a row that carries its own sentence.
    assert overlap_timing_advisories(
        [crow(overlap_ref="a hundred paired runs")], [late]) == []


# --- exactly one shape of evidence -------------------------------------------

def test_a_declaration_with_a_census_may_not_also_carry_the_sentence():
    """THE DEFECT #413 CLOSES, arriving from the other side.

    `vera`'s row carried "101 run(s) both instruments recorded, 2030-01-06 to
    2030-06-30" beside a record that now counts exactly that. Two carriers of
    one fact drift, and the prose one is the copy nothing can check.
    """
    both = crow(overlap_ref="101 run(s) both instruments recorded")
    problems = overlap_evidence_problems([both], [row()])
    assert any("second spelling" in p for p in problems), problems
    # Drop the sentence and the same pair is clean.
    assert overlap_evidence_problems([crow()], [row()]) == []


def test_a_declaration_with_neither_names_its_overlap_nowhere():
    """THE OLD REQUIREMENT, WHICH MOVED RATHER THAN WEAKENED."""
    problems = overlap_evidence_problems([crow()], [])
    assert any("names its overlap nowhere" in p for p in problems), problems
    # Either shape satisfies it.
    assert overlap_evidence_problems(
        [crow(overlap_ref="a fortnight of same-day readings")], []) == []
    assert overlap_evidence_problems([crow()], [row()]) == []


def test_an_unearned_census_does_not_count_as_evidence():
    """GATES MUST FAIL CLOSED, and this is the one that could be walked past.

    Since contract 53 an `overlaps` line is a way to satisfy the requirement
    that a declaration name its overlap. If any four fields in a second file
    counted, the check would be easier to bypass than the sentence it
    replaced. A census that has not earned itself is not evidence.
    """
    thin = row(paired_days=1, dropped_days=0, from_date="2030-06-30")
    assert not census_is_earned(thin)
    problems = overlap_evidence_problems([crow()], [thin])
    assert any("names its overlap nowhere" in p for p in problems), problems


def test_a_refusal_owes_no_evidence():
    """Asserting a negative earns nothing, so `not_comparable` needs neither
    shape - the rule `_comparability_problems` already applied to the
    sentence, carried over unchanged."""
    refusal = crow(status="not_comparable", bias=None, spread=None,
                   difference_lo=None, difference_hi=None)
    assert overlap_evidence_problems([refusal], []) == []


def test_a_retired_declaration_is_not_held_to_the_rule():
    """`supersedes` withdraws a statement rather than adding a second one, so
    a corrected line is read as retired here exactly as it is everywhere
    else."""
    stale = crow(date="2030-06-29", overlap_ref="101 run(s), Jan to June")
    fixed = crow(supersedes="distance_km/phone/watch@2030-06-29")
    assert overlap_evidence_problems([stale, fixed], [row()]) == []


# --- the census EARNS the declaration ----------------------------------------

def test_a_census_lets_a_declaration_stand_without_a_sentence():
    """`policy._earns_its_status` is the gate that decides whether a row is
    honoured at all, and it used to require the sentence. A row whose overlap
    is COUNTED is better evidenced than one whose overlap is described, and
    would have been thrown away as unearned."""
    declared = crow(status="comparable", bias=None, spread=None,
                    difference_lo=None, difference_hi=None)
    # Without the censuses, silence - which is the fail-closed direction.
    assert comparability([declared], "distance_km", "phone", "watch",
                         "2030-07-01")["status"] == "not_comparable"
    # With them, the record's own answer.
    assert comparability([declared], "distance_km", "phone", "watch",
                         "2030-07-01", [row()])["status"] == "comparable"


def test_a_census_dated_after_the_question_earns_nothing():
    """Evidence that arrives after the statement it supports is retroactive
    reasoning, which is what effective-dating exists to prevent."""
    declared = crow(status="comparable", bias=None, spread=None,
                    difference_lo=None, difference_hi=None)
    assert comparability([declared], "distance_km", "phone", "watch",
                         "2030-06-29", [row()])["status"] == "not_comparable"


def test_an_unearned_census_lifts_nothing():
    declared = crow(status="comparable", bias=None, spread=None,
                    difference_lo=None, difference_hi=None)
    thin = row(paired_days=2, from_date="2030-06-29")
    assert comparability([declared], "distance_km", "phone", "watch",
                         "2030-07-01", [thin])["status"] == "not_comparable"


# --- the resolver ------------------------------------------------------------

def test_nothing_is_an_answer_and_is_not_a_window_of_no_days():
    assert overlap([], "sessions", "distance_km", "phone", "watch",
                   "2030-07-01") is None


def test_the_pair_is_answered_in_either_order():
    for a, b in (("phone", "watch"), ("watch", "phone")):
        found = overlap([row()], "sessions", "distance_km", a, b, "2030-07-01")
        assert found is not None and found["paired_days"] == 101


def test_a_re_measurement_supersedes_the_census_it_replaces():
    first = row()
    again = row(date="2030-09-30", paired_days=150, to_date="2030-09-30",
                supersedes="sessions/distance_km/phone/watch@2030-06-30",
                recorded_at="2030-09-30T22:00:00+01:00")
    found = overlap([first, again], "sessions", "distance_km", "phone",
                    "watch", "2030-10-01")
    assert found["paired_days"] == 150
    # And as of a date before the re-measurement, the first still stands.
    assert overlap([first, again], "sessions", "distance_km", "phone",
                   "watch", "2030-07-01")["paired_days"] == 101


def test_the_same_field_on_another_dataset_is_another_window():
    assert overlap([row()], "daily", "distance_km", "phone", "watch",
                   "2030-07-01") is None


# --- the corpus, where the census is checked against the readings ------------

def test_the_corpus_census_is_what_the_engine_counts():
    """THE CONTROL THAT MAKES "EARNED" MEAN SOMETHING, and the only place it
    can live.

    `vera`'s census is AUTHORED - written by the persona builder from her own
    runs - and the engine counts the same window from her session claims by a
    different path. Two paths to one set of numbers is a check; one path twice
    would be a mirror.

    THIS IS THE RE-DERIVATION `validate_record` DELIBERATELY DOES NOT DO. A
    row check that re-counted would make an already-written line's validity
    depend on lines appended after it - a later observation inside the window
    changes the count - and an append-only record whose history stops
    validating when history is added to is not append-only. Here the record is
    fixed and regenerated together, so the comparison is exact and means what
    it says.
    """
    measured = overlap_calibration(rows(VERA, "sessions"), "distance_km",
                                   "phone", "watch", dataset="sessions")
    recorded = overlap(rows(VERA, "overlaps"), "sessions", "distance_km",
                       "phone", "watch", "2030-12-31")
    assert recorded is not None
    assert recorded["paired_days"] == measured["pairs"] == 101
    assert recorded["dropped_days"] == len(measured["ambiguous_days"]) == 0
    assert recorded["from_date"] == measured["overlap"]["from_date"]
    assert recorded["to_date"] == measured["overlap"]["to_date"]
    # And the window really is bounded by days that paired.
    assert (recorded["paired_days"] + recorded["dropped_days"]) <= 1 + (
        __import__("datetime").date.fromisoformat(recorded["to_date"])
        - __import__("datetime").date.fromisoformat(recorded["from_date"])).days


def test_the_sentence_is_gone_from_the_row_the_issue_was_about():
    """`vera`'s `overlap_ref` was the sentence #413 is named for."""
    declared = rows(VERA, "comparability")
    assert len(declared) == 1
    assert declared[0]["overlap_ref"] is None
    # And what the census cannot hold is still said, on the field for it.
    assert "forest loop" in declared[0]["note"]


def test_the_demos_declaration_keeps_its_sentence_and_that_is_the_point():
    """THE OTHER BRANCH, DEMONSTRATED BY A RECORD RATHER THAN BY A FIXTURE.

    The demo declares its scale and its DEXA comparable on two same-day
    readings. Two is below `MIN_PAIRS`, so no census can be earned for it and
    none is written - and the sentence stays, because there is nothing to
    replace it with. After this change a reader can TELL, from data, which
    declarations rest on a counted window and which rest on a sentence. Before
    it, both looked identical.
    """
    declared = rows(DEMO, "comparability")
    assert len(declared) == 1
    assert declared[0]["overlap_ref"], "the demo's row keeps its sentence"
    assert rows(DEMO, "overlaps") == []
    measured = overlap_calibration(rows(DEMO, "weight"), "kg", "scale",
                                   "dexa", dataset="weight")
    assert measured["pairs"] < MIN_PAIRS
    assert measured["overlap"] is None
    assert Vitai(DEMO).validate()["ok"]


def test_both_shipped_records_validate_clean():
    for root in (VERA, DEMO):
        report = Vitai(root).validate()
        assert report["problems"] == [], (root.name, report["problems"][:5])


# --- P9: one capability, three surfaces --------------------------------------

def test_the_three_surfaces_return_the_same_row():
    from vitai.mcp import serve

    api = Vitai(VERA).overlap("sessions", "distance_km", "phone", "watch")

    stdin = io.StringIO("\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "overlap",
                               "arguments": {"dataset": "sessions",
                                             "field": "distance_km",
                                             "origin_a": "phone",
                                             "origin_b": "watch"}}}),
    ]) + "\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        serve(VERA, stdin=stdin)
    replies = [json.loads(ln) for ln in out.getvalue().splitlines() if ln]
    mcp = json.loads(replies[-1]["result"]["content"][0]["text"])

    cli = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "overlap", "--root", str(VERA),
         "--dataset", "sessions", "--field", "distance_km",
         "--origin-a", "phone", "--origin-b", "watch", "--json"],
        capture_output=True, text=True, check=True)

    assert api == mcp == json.loads(cli.stdout)


def test_the_cli_prints_the_counts_rather_than_a_sentence():
    cli = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "overlap", "--root", str(VERA),
         "--dataset", "sessions", "--field", "distance_km",
         "--origin-a", "phone", "--origin-b", "watch"],
        capture_output=True, text=True, check=True)
    assert "101 paired day(s)" in cli.stdout
    assert "0 day(s) dropped" in cli.stdout
    assert "2030-01-06 to 2030-06-30" in cli.stdout
    # AND SAYS WHAT IT IS NOT. A count is the size of a comparison, never its
    # result and never a licence to read the two instruments as one series.
    assert "not its result" in cli.stdout


def test_the_cli_says_nothing_rather_than_zero():
    cli = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "overlap", "--root", str(DEMO),
         "--dataset", "weight", "--field", "kg",
         "--origin-a", "scale", "--origin-b", "dexa"],
        capture_output=True, text=True, check=True)
    assert "no counted window" in cli.stdout
    assert "0 paired" not in cli.stdout


def test_calibrate_now_reports_the_window_it_would_write():
    cli = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "calibrate", "--root", str(VERA),
         "--dataset", "sessions", "--field", "distance_km",
         "--origin-a", "phone", "--origin-b", "watch"],
        capture_output=True, text=True, check=True)
    assert "window:  101 paired day(s), 0 dropped" in cli.stdout
    assert "sessions.distance_km" in cli.stdout


def test_the_writer_proposes_no_census_where_it_cannot_name_the_dataset():
    """`overlap_calibration` is handed rows and never learns which dataset
    they came from, and `field` does not settle it. Where the caller does not
    say, no census is proposed - a guessed `dataset` would be unfollowable in
    exactly the way the sentence it replaces was."""
    head = overlap_calibration(rows(VERA, "sessions"), "distance_km",
                               "phone", "watch")
    assert head["pairs"] == 101
    assert head["row"] is not None
    assert head["overlap"] is None


def test_the_writer_no_longer_produces_the_sentence():
    """The writer used to build `overlap_ref` by describing the counts in
    English, so appending what it produced would now trip the both-carriers
    rule from the engine's own output.

    BOTH HALVES ARE STAMPED THROUGH THE APPEND DOOR before they are judged,
    because what this function returns is a PROPOSAL and not a record line:
    `supersedes`, `recorded_at` and `device` are machine-set and `append` fills
    them from `KEYS`. `census_is_earned` asks the validator, and the validator
    holds a line to every key its generation registers - so judging the
    proposal directly would be judging a shape the record never holds.
    """
    head = overlap_calibration(rows(VERA, "sessions"), "distance_km",
                               "phone", "watch", dataset="sessions")
    assert head["row"]["overlap_ref"] is None

    def stamped(dataset: str, proposed: dict) -> dict:
        line = {k: proposed.get(k) for k in KEYS[dataset]}
        line["recorded_at"] = "2030-06-30T22:00:00+01:00"
        return line

    census = stamped("overlaps", head["overlap"])
    declared = stamped("comparability", head["row"])
    assert validate_record("overlaps", census) == []
    assert census_is_earned(census)
    assert overlap_evidence_problems([declared], [census]) == []
    assert overlap_timing_advisories([declared], [census]) == []
