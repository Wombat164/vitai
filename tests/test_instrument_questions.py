"""An instrument that stopped, and a zero that should have been an absence.

#398, from a real outage rather than a hypothetical: a charger left at home, a
watch that fell quiet over several days, and one day on its last charge where
it reported an athlete who had been moving as `steps: 0`.

THE FALSE ZERO IS THE ONE THAT COSTS. A gap announces itself and every reader
already treats absence as absence. A zero is a fabricated measurement that
averages into weekly steps, `kcal_out` and energy availability exactly as
though somebody observed it, and the athlete will never report it because from
their side nothing looks wrong - they know they lost sleep tracking, they have
no reason to suspect a number. It is the case where the engine knows something
the person does not.

WHAT THESE CONTROLS ARE MOSTLY FOR IS THE REFUSALS. Both rules are easy to
write so that they fire; the work is in the days they must stay silent on. A
record that never carried a step count must never be asked why it stopped. A
weekly source is not silent after two days. A field that is legitimately zero
on ordinary days - `alcohol`, `pain` - must not produce a question every time
the athlete has a dry Tuesday. Most of what follows is those cases, because an
asking channel that cries wolf gets switched off, and then the one question
that mattered goes with it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from vitai.api import Vitai
from vitai.questions import KINDS, false_zero_questions, outage_questions
from vitai.schema import KEYS

START = date(2030, 6, 1)


def row(day: date, source: str = "watch", learned: date | None = None,
        **kw) -> dict:
    """One daily claim, stamped with WHEN THE RECORD LEARNED IT.

    `learned` defaults to the day itself, which is what a channel syncing each
    evening looks like. Passing one date for many rows is what a backfill looks
    like, and #405 is the finding that the two are indistinguishable on the
    other clock."""
    return {**{k: None for k in KEYS["daily"]}, "date": day.isoformat(),
            "source": source,
            "recorded_at": f"{(learned or day).isoformat()}T20:00:00+02:00",
            **kw}


def steady(n: int, source: str = "watch", every: int = 1, **kw) -> list[dict]:
    """`n` appearances at a fixed cadence, each learned on the day it happened."""
    return [row(START + timedelta(days=i * every), source,
                steps=9000 + i * 13, kcal_out=2400, **kw) for i in range(n)]


def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def kinds(v: Vitai, on: str) -> list[str]:
    return sorted(q["kind"] for q in v.questions(on)
                  if q["kind"] in ("outage", "false_zero"))


# --- the vocabulary -----------------------------------------------------------

def test_both_kinds_are_declared():
    assert {"outage", "false_zero"} <= KINDS


# --- the false zero -----------------------------------------------------------

def test_a_zero_a_source_has_never_written_before_is_asked_about(tmp_path):
    """THE REPORTED CASE. Fourteen days of a worn watch, then a zero."""
    rows = steady(14) + [row(START + timedelta(days=14), steps=0, kcal_out=1500)]
    v = record(tmp_path, rows)
    q = [x for x in v.questions("2030-06-15") if x["kind"] == "false_zero"]
    assert len(q) == 1, q
    assert q[0]["for_date"] == "2030-06-15"
    assert q[0]["subject"] == "watch"
    assert q[0]["resolves"] == ["steps"]
    assert q[0]["settled_by"] == "athlete"


def test_the_near_floor_value_beside_it_is_not_claimed(tmp_path):
    """The honest limit, pinned so nobody later reads the kind as covering it.

    The reporting issue describes a near-floor `kcal_out` beside the zero
    steps. 1500 is not zero, and calling it too low needs a threshold on a
    distribution - the invented number this module refuses. Only `steps` is
    named, and a reader of `resolves` is entitled to conclude nothing about the
    fields it does not list."""
    rows = steady(14) + [row(START + timedelta(days=14), steps=0, kcal_out=1500)]
    q = [x for x in record(tmp_path, rows).questions("2030-06-15")
         if x["kind"] == "false_zero"]
    assert q[0]["resolves"] == ["steps"], "kcal_out must not be claimed"


def test_a_field_that_is_ordinarily_zero_is_never_asked_about(tmp_path):
    """THE REFUSAL THAT MAKES THE RULE USABLE, and the corpus is what proved
    it necessary.

    The first version of this rule looked at every numeric daily field, on the
    issue's reasoning that a zero out of family could be spotted from the
    field's own distribution. Against the shipped corpus it produced four
    questions, all false positives - three first-ordinary-day `pain` zeros and
    one `sugar_g` - and no true positive anywhere. `ZERO_MEANS_UNOBSERVED` is
    the correction, so a dry Tuesday and a day without sugar stay silent.
    """
    rows = [row(START + timedelta(days=i), steps=9000 + i,
                alcohol=0, pain=0, sugar_g=0) for i in range(14)]
    v = record(tmp_path, rows)
    assert kinds(v, "2030-06-14") == []


def test_the_corpus_asks_nothing_it_should_not(tmp_path):
    """The measurement above, kept rather than described. Every shipped record
    is run, and the only acceptable answer today is silence: none of them
    contains an instrument outage or a fabricated zero, so any question at all
    is a false positive of the kind that gets an asking channel switched off.
    """
    roots = [p for p in sorted(Path("tests/fixtures/personas").iterdir())
             if (p / "vitai.toml").exists()]
    roots.append(Path(__file__).parent.parent / "examples" / "demo")
    assert len(roots) >= 10, roots
    noise = []
    for root in roots:
        for q in Vitai(root).questions():
            if q["kind"] in ("outage", "false_zero"):
                noise.append((root.name, q["kind"], q["for_date"], q.get("resolves")))
    assert noise == [], noise


def test_a_zero_outside_the_declared_set_is_not_a_question(tmp_path):
    """The register doing its job on a field where zero is a real answer."""
    rows = steady(14) + [row(START + timedelta(days=14), steps=9500, pain=0)]
    v = record(tmp_path, rows)
    assert [q for q in v.questions("2030-06-15") if q["kind"] == "false_zero"] == []


def test_only_the_first_zero_is_asked_about(tmp_path):
    """Once the record shows this source writing zeros for this field, the
    engine has no basis left to call the next one wrong - it would be arguing
    with evidence it just accepted."""
    rows = (steady(10)
            + [row(START + timedelta(days=10), steps=0),
               row(START + timedelta(days=11), steps=0),
               row(START + timedelta(days=12), steps=0)])
    q = [x for x in record(tmp_path, rows).questions("2030-06-13")
         if x["kind"] == "false_zero"]
    assert len(q) == 1, q
    assert q[0]["for_date"] == "2030-06-11", "the FIRST zero, not the latest"


def test_superseding_the_zero_stops_the_question(tmp_path):
    """The answer's whole point. `dataset` applies supersedes, so a retired
    false zero is gone from what this reads - and if a later zero exists it
    becomes the first one again and is asked about in its turn."""
    day = (START + timedelta(days=14)).isoformat()
    rows = steady(14) + [row(START + timedelta(days=14), steps=0)]
    before = record(tmp_path, rows)
    assert [q["kind"] for q in before.questions("2030-06-15")
            if q["kind"] == "false_zero"] == ["false_zero"]

    corrected = rows + [row(START + timedelta(days=14), steps=11200,
                            supersedes=f"{day}/watch")]
    after = record(tmp_path / "b", corrected)
    assert [q for q in after.questions("2030-06-15")
            if q["kind"] == "false_zero"] == []


def test_two_sources_are_two_questions(tmp_path):
    """Per SOURCE, because two instruments failing is two facts even on one
    day - and one instrument failing is one fact however many of its fields
    went with it.

    THE SECOND HALF IS UNEXERCISED AND SAYS SO. `resolves` is a list because a
    dying watch writes its zero steps and its zero active minutes in the same
    breath, and grouping them is what stops that being two questions about one
    failure. While `ZERO_MEANS_UNOBSERVED` holds a single field that list can
    never have two entries, so no test here can demonstrate the grouping -
    asserting a one-element list and calling it covered would be the theatre
    this suite is written against. It becomes testable the day the register
    widens, and the day it widens is the day this comment has to go.
    """
    rows = (steady(10) + steady(10, source="phone")
            + [row(START + timedelta(days=10), steps=0),
               row(START + timedelta(days=10), "phone", steps=0)])
    q = sorted((x for x in record(tmp_path, rows).questions("2030-06-11")
                if x["kind"] == "false_zero"), key=lambda x: x["subject"])
    assert [x["subject"] for x in q] == ["phone", "watch"]
    assert len({x["id"] for x in q}) == 2, "one id per source"
    assert all(x["resolves"] == ["steps"] for x in q)


def test_the_register_is_a_floor_and_the_tests_know_its_size(tmp_path):
    """Guards the comment above. If the register widens and nobody revisits
    the grouping test, this fails and points at it."""
    from vitai.questions import ZERO_MEANS_UNOBSERVED

    assert ZERO_MEANS_UNOBSERVED == {"steps"}, (
        "the declared field set changed - `test_two_sources_are_two_questions` "
        "says the multi-field grouping cannot be demonstrated while it holds "
        "one field, and that comment is now either wrong or actionable")


# --- the outage ---------------------------------------------------------------

def test_a_daily_source_that_falls_quiet_is_asked_about_once(tmp_path):
    """ONE QUESTION PER RUN. A five-day outage is one fact about one episode,
    not five facts - which is the discipline this module opens with, and it
    binds hardest here: the longer somebody is away, the more days go missing
    and the more the engine wants to ask."""
    v = record(tmp_path, steady(14))
    q = [x for x in v.questions("2030-06-20") if x["kind"] == "outage"]
    assert len(q) == 1, q
    assert q[0]["for_date"] == "2030-06-15", "the first silent day"
    assert q[0]["through"] == "2030-06-20", "the run is stated, not counted"
    assert q[0]["subject"] == "watch"


def test_a_weekly_source_is_not_silent_after_two_days(tmp_path):
    """CADENCE IS MEASURED, NEVER ASSUMED. This source has always had six-day
    gaps, so two quiet days is it behaving normally."""
    v = record(tmp_path, steady(5, every=7))
    assert kinds(v, "2030-06-30") == [], "two days is within its own habit"
    # And it IS eventually silent - the rule refuses, it does not disable.
    assert "outage" in kinds(v, "2030-07-08")


def test_a_source_the_record_never_carried_is_never_asked_about(tmp_path):
    """SILENCE IS NOT AN INSTRUMENT. Same refusal shape as the protocol
    advisory: a record with none declared has nothing to be missing."""
    v = record(tmp_path, [])
    assert kinds(v, "2030-06-30") == []


def test_a_source_seen_twice_has_an_anecdote_not_a_cadence(tmp_path):
    """Two appearances give ONE prior gap, and 'longer than ever before'
    against a single observation would call a source silent on its second
    quiet day having never shown a habit to break."""
    v = record(tmp_path, steady(2))
    assert kinds(v, "2030-06-30") == []
    assert "outage" in kinds(record(tmp_path / "b", steady(3)), "2030-06-30")


def test_a_source_that_has_resumed_is_not_asked_about(tmp_path):
    """Only where an answer resolves something. The gap is in the past and the
    instrument is back; nothing is open."""
    rows = steady(10) + [row(START + timedelta(days=25), steps=9400)]
    v = record(tmp_path, rows)
    assert [x for x in v.questions("2030-06-26") if x["kind"] == "outage"] == []


def test_the_run_grows_but_stays_one_question(tmp_path):
    """The volume property, checked over a lengthening absence rather than
    asserted. Ten days further away is not ten more questions."""
    v = record(tmp_path, steady(14))
    for on, through in (("2030-06-17", "2030-06-17"),
                        ("2030-06-24", "2030-06-24"),
                        ("2030-07-14", "2030-07-14")):
        q = [x for x in v.questions(on) if x["kind"] == "outage"]
        assert len(q) == 1, (on, q)
        assert q[0]["through"] == through
        assert q[0]["id"] == "outage:daily:watch:2030-06-15", "one id, one run"


def test_the_two_kinds_arrive_distinguishable(tmp_path):
    """THE CONSUMER-FACING POINT. A gap wants an append and a false zero wants
    a supersede, so a client handed one undifferentiated list would append
    beside the lie instead of retiring it. `kind` carries that, with nothing to
    re-derive."""
    rows = steady(14) + [row(START + timedelta(days=14), steps=0)]
    q = [x for x in record(tmp_path, rows).questions("2030-06-25")
         if x["kind"] in ("outage", "false_zero")]
    assert sorted(x["kind"] for x in q) == ["false_zero", "outage"]
    assert len({x["id"] for x in q}) == 2


# --- the derivations read the record, not the viewpoint's convenience ---------

def test_a_day_after_the_viewpoint_is_not_evidence(tmp_path):
    """A reconstruction must not see a zero that had not been written yet."""
    rows = steady(10) + [row(START + timedelta(days=10), steps=0)]
    v = record(tmp_path, rows)
    assert [x for x in v.questions("2030-06-10") if x["kind"] == "false_zero"] == []
    assert [x for x in v.questions("2030-06-11") if x["kind"] == "false_zero"]


def test_neither_derivation_needs_a_record_on_disk():
    """Both are pure functions of rows and a viewpoint, which is what lets
    `questions()` promise no model, no network and no permission layer."""
    rows = [{"date": (START + timedelta(days=i)).isoformat(), "source": "w",
             "recorded_at": f"{(START + timedelta(days=i)).isoformat()}"
                            f"T20:00:00+02:00",
             "steps": 9000 + i} for i in range(5)]
    assert outage_questions(rows, date(2030, 6, 30))[0]["subject"] == "w"
    assert false_zero_questions(rows, date(2030, 6, 30)) == []


# --- the surfaces ------------------------------------------------------------

def test_the_cli_renders_both_kinds(tmp_path):
    """THE GAP THAT SHIPPED A CRASH, kept as a test.

    `cmd_questions` fell through to a branch reading `row['bears_on']`, which
    the two plan-shaped kinds carry and an instrument question has no second
    axis for. It raised `KeyError` on the first record holding one - and the
    whole suite was green, because every existing questions test drove the API
    and nothing drove the RENDERER over these kinds. A shape that varies by
    kind has to be branched on, and a branch nothing exercises is a branch
    nobody has run.
    """
    import subprocess
    import sys

    rows = steady(14) + [row(START + timedelta(days=14), steps=0)]
    v = record(tmp_path, rows)
    proc = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "questions",
         "--root", str(v.root), "--on", "2030-06-25"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "outage watch" in out, out
    assert "2030-06-16 to 2030-06-25" in out, "the run is printed as a run"
    assert "false_zero watch steps" in out, out


def test_every_emitted_kind_is_renderable(tmp_path):
    """Guards the guard, generically. The crash above was one kind missing one
    branch; this fails for any future kind that reaches the renderer without
    one, rather than waiting for somebody to write its own test."""
    import subprocess
    import sys

    rows = steady(14) + [row(START + timedelta(days=14), steps=0)]
    v = record(tmp_path, rows)
    emitted = {q["kind"] for q in v.questions("2030-06-25")}
    assert emitted, "the fixture must emit something for this to check"
    proc = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "questions",
         "--root", str(v.root), "--on", "2030-06-25"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    for kind in sorted(emitted):
        assert kind in proc.stdout, (kind, proc.stdout)


# --- the clock, and the declaration (#405) ------------------------------------

def instrument(origin: str, from_date: str, to_date: str | None = None) -> dict:
    return {**{k: None for k in KEYS["instruments"]}, "date": from_date,
            "origin": origin, "from_date": from_date, "to_date": to_date,
            "source": "athlete"}


def record_with(tmp_path: Path, daily: list[dict],
                instruments: list[dict] | None = None) -> Vitai:
    v = record(tmp_path, daily)
    if instruments:
        (v.root / "data" / "instruments.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in instruments), encoding="utf-8")
    return v


def test_a_one_time_backfill_is_not_a_channel_that_died(tmp_path):
    """THE FALSE POSITIVE THIS RULE'S FIRST LIVE RUN PRODUCED.

    An archive pulled once to recover years of readings from a replaced
    device. Thousands of dates, one transaction day. On the wrong clock it is
    the most established channel in the record and every existing guard passes
    it through: it is not seen once, and it holds far more than an anecdote's
    history. On the right clock it never had a rhythm to break.
    """
    backfill = [row(date(2023, 1, 1) + timedelta(days=i * 7), "old-device",
                    learned=date(2030, 6, 1), steps=8000 + i)
                for i in range(200)]
    v = record_with(tmp_path, backfill)
    assert len({r["date"][:4] for r in v.dataset("daily")}) >= 4, "spans years"
    assert [q for q in v.questions("2030-06-30") if q["kind"] == "outage"] == []


def test_the_same_rows_on_the_wrong_clock_would_have_asked(tmp_path):
    """Guards the guard, so the test above cannot pass by the backfill being
    unremarkable. Measured on `date` these rows have a settled weekly cadence
    and a month of silence, which is exactly what the old rule asked about."""
    backfill = [row(date(2023, 1, 1) + timedelta(days=i * 7), "old-device",
                    learned=date(2030, 6, 1), steps=8000 + i)
                for i in range(200)]
    days = sorted({date.fromisoformat(r["date"]) for r in backfill})
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    assert max(gaps) == 7, gaps
    assert (date(2030, 6, 30) - days[-1]).days > max(gaps), (
        "on valid time this source has been silent longer than it ever was")


def test_a_channel_learned_daily_still_asks(tmp_path):
    """The clock change must not disable the rule. A source learned on the day
    it reports still has a transaction cadence, and still breaks it."""
    v = record_with(tmp_path, steady(14))
    q = [x for x in v.questions("2030-06-25") if x["kind"] == "outage"]
    assert len(q) == 1, q


def test_a_source_that_never_says_when_it_was_written_is_not_asked_about(tmp_path):
    """THE REFUSAL THE CLOCK CHANGE BUYS AND COSTS. A row with no
    `recorded_at` cannot support a transaction-time cadence, and reading one
    off `date` instead is the mistake this whole change removes. Silence is
    the safe direction: an unasked question costs less than a confident one
    about an import that finished years ago."""
    unstamped = [{**{k: None for k in KEYS["daily"]},
                  "date": (START + timedelta(days=i)).isoformat(),
                  "source": "watch", "steps": 9000 + i} for i in range(14)]
    v = record_with(tmp_path, unstamped)
    assert [q for q in v.questions("2030-06-30") if q["kind"] == "outage"] == []


def test_a_declared_end_is_not_an_outage(tmp_path):
    """LAYER ONE. `instruments.to_date` has been in the schema since contract
    45 and nothing consulted it, so a record could already say a device was
    used until a date while the asking channel went on asking why it stopped.
    """
    daily = [row(START + timedelta(days=i), "old-watch", steps=9000 + i,
                 origin="old-watch") for i in range(14)]
    live = record_with(tmp_path, daily)
    assert [q for q in live.questions("2030-06-30") if q["kind"] == "outage"]

    declared = record_with(tmp_path / "b", daily,
                           [instrument("old-watch", "2030-06-01", "2030-06-14")])
    assert [q for q in declared.questions("2030-06-30")
            if q["kind"] == "outage"] == []


def test_a_replacement_reporting_under_the_same_name_stays_live(tmp_path):
    """THE TRAP, AND IT IS IN THIS REPO'S OWN CORPUS. `bea` carries two
    `watch` rows: an old watch closed in February and its replacement opened
    the day after, reporting under the same name, with a note saying that is
    the whole reason the interval matters.

    A rule reading "some row for this origin has a past `to_date`" would call
    that watch retired and silence every question about a channel in daily
    use. Retired means EVERY interval has closed.
    """
    daily = [row(START + timedelta(days=i), "watch", steps=9000 + i,
                 origin="watch") for i in range(14)]
    v = record_with(tmp_path, daily, [
        instrument("watch", "2029-09-03", "2030-02-14"),
        instrument("watch", "2030-02-15", None)])
    assert [q for q in v.questions("2030-06-30") if q["kind"] == "outage"], (
        "a live replacement was silenced by its predecessor's closed interval")


def test_the_corpus_replacement_case_is_real():
    """Reads `bea` rather than restating her, so this fails if the fixture
    that motivates the rule above stops carrying it."""
    bea = Path(__file__).parent / "fixtures" / "personas" / "bea"
    rows = [json.loads(ln) for ln
            in (bea / "data" / "instruments.jsonl").read_text(
                encoding="utf-8").splitlines() if ln.strip()]
    watch = [r for r in rows if r.get("origin") == "watch"]
    assert len(watch) == 2, watch
    assert sum(1 for r in watch if r.get("to_date")) == 1
    assert sum(1 for r in watch if not r.get("to_date")) == 1


def test_an_instrument_closing_after_the_viewpoint_is_still_live(tmp_path):
    """`to_date` in the future is a planned end, not a past one."""
    daily = [row(START + timedelta(days=i), "watch", steps=9000 + i,
                 origin="watch") for i in range(14)]
    v = record_with(tmp_path, daily,
                    [instrument("watch", "2030-06-01", "2031-01-01")])
    assert [q for q in v.questions("2030-06-30") if q["kind"] == "outage"]


def test_the_declaration_matches_the_source_name_too(tmp_path):
    """An instrument is declared per `origin` and a daily row does not always
    carry one - most of this corpus leaves it null. So the source's own name
    is a candidate as well, which is what the operator's wording on the issue
    says: a source OR origin whose instrument is closed."""
    daily = [row(START + timedelta(days=i), "old-import", steps=9000 + i)
             for i in range(14)]
    v = record_with(tmp_path, daily,
                    [instrument("old-import", "2030-06-01", "2030-06-14")])
    assert [q for q in v.questions("2030-06-30") if q["kind"] == "outage"] == []
