"""Lead with what is blocking, then what fired, then the tables (#76).

Measured on a live record, 83 per cent of this document was one table and
everything actionable sat in its last thirteen lines - below the fold by a
factor of twenty, in a document a reader has been trained by bulk to skim.
#40 already reasons about the same failure: an alert that fires every day is
worse than none, because it teaches the reader to skip it. Here it is volume
rather than repetition, and the effect is identical.

TWO THINGS THE ISSUE DID NOT KNOW, both found by running it.

The comment beside the Gates section said gates "outrank tripwires and sit
above them in the reader's eye", and the code emitted them afterwards - on the
shipped demo, `## Gates` at line 56 and `## Tripwires` at 52.

And the issue's ask to suppress all-zero week rows would have deleted evidence
of training. The table counted running and strength, and every other session
still created its week through a defaultdict, so a 20 km ride, a swim and a
walk each rendered `| 0.0 | 0 | 0 | - | - |` - identical to a week nobody
trained. Most of those rows are not weeks somebody stopped logging; they are
weeks this table could not describe.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _headings(text: str) -> list[str]:
    return [ln.strip("# ").strip() for ln in text.splitlines()
            if ln.startswith("## ")]


def _weeks(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("| 20")]


def _record(tmp_path: Path) -> Vitai:
    return Vitai(init(tmp_path / "content"))


# --- what a reader meets first --------------------------------------------

def test_a_gate_is_above_the_tables():
    """The one thing in this document that is already decided, and it was
    below a table long enough to train a skim past it."""
    headings = _headings(Vitai(DEMO).rollup(date(2030, 6, 30)))

    assert headings.index("Gates") < headings.index("Weight")
    assert headings.index("Gates") < headings.index("Training by week")


def test_a_gate_is_above_the_tripwires_as_its_own_comment_says():
    """A tripwire is something to discuss; a gate is something already
    decided. The comment beside them said gates sit above, and the code put
    them below."""
    headings = _headings(Vitai(DEMO).rollup(date(2030, 6, 30)))

    assert headings.index("Gates") < headings.index("Tripwires")


def test_the_tripwires_are_above_the_tables():
    headings = _headings(Vitai(DEMO).rollup(date(2030, 6, 30)))

    assert headings.index("Tripwires") < headings.index("Weight")


def test_nothing_firing_is_said_rather_than_left_blank(tmp_path):
    """An empty section is information too, and a reader cannot tell one from
    a section that failed to render."""
    text = _record(tmp_path).rollup(date(2030, 6, 1))

    assert "- Nothing firing." in text
    assert "- Nothing gated." in text


def test_a_safety_escalation_outranks_even_a_gate():
    """Ordering by how little argument the reader gets: an escalation names an
    action, a gate names a block, a tripwire names a discussion."""
    from vitai.report import build_report
    from vitai.config import Config

    text = build_report(
        Config(), [], [], [], today=date(2030, 6, 1),
        gates=[{"restricts": "run", "reason": "an episode"}],
        escalations=[{"level": "urgent", "date": "2030-06-01",
                      "detail": "a detail", "action": "an action"}])

    assert _headings(text).index("Safety") < _headings(text).index("Gates")


# --- a week of cycling is not a week of nothing ---------------------------

def test_a_week_of_any_other_activity_is_not_a_week_of_nothing(tmp_path):
    """THE ASK THAT WOULD HAVE DELETED THE EVIDENCE. Suppressing all-zero rows
    looks like removing noise, and on the record this was measured against
    most of them are weeks somebody trained in a way the table could not
    describe."""
    v = _record(tmp_path)
    for kind, day in (("cycle", "2030-05-06"), ("swim", "2030-05-13"),
                      ("walk", "2030-05-20")):
        v.append("sessions", {"date": day, "type": kind, "distance_km": 20.0,
                              "duration_s": 3600, "source": "watch"})

    rows = _weeks(v.rollup(date(2030, 6, 1)))

    assert len(rows) == 3
    for row in rows:
        assert "| 0.0 | 0 | 0 | 0 |" not in row, row
        assert row.rstrip().endswith("| - | - |")


def test_a_run_week_and_a_ride_week_are_told_apart(tmp_path):
    """The distinction the column exists for."""
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-06", "type": "cycle",
                          "distance_km": 30.0, "duration_s": 3600,
                          "source": "watch"})
    v.append("sessions", {"date": "2030-05-13", "type": "run",
                          "distance_km": 10.0, "source": "watch"})

    ride, run = _weeks(v.rollup(date(2030, 6, 1)))

    assert "| 0.0 | 0 | 0 | 1 |" in ride
    assert "| 10.0 | 1 | 0 | 0 |" in run


def test_the_table_still_says_when_there_were_no_sessions(tmp_path):
    text = _record(tmp_path).rollup(date(2030, 6, 1))

    assert "_No sessions._" in text


# --- bounded, and honest about what it hid --------------------------------

def test_the_table_shows_a_recent_window(tmp_path):
    """A weekly document is read weekly. The full series reached 267 rows
    going back seven years on the record this was measured on."""
    v = _record(tmp_path)
    for n in range(40):
        v.append("sessions", {
            "date": (date(2029, 6, 4) + timedelta(weeks=n)).isoformat(),
            "type": "run", "distance_km": 5.0, "source": "watch"})

    rows = _weeks(v.rollup(date(2030, 6, 1)))

    assert len(rows) == 12


def test_it_says_how_many_weeks_it_did_not_show(tmp_path):
    """A bounded table that does not say it is bounded reads as the whole
    record, which is the same mistake in the other direction."""
    v = _record(tmp_path)
    for n in range(40):
        v.append("sessions", {
            "date": (date(2029, 6, 4) + timedelta(weeks=n)).isoformat(),
            "type": "run", "distance_km": 5.0, "source": "watch"})

    assert "_28 earlier week(s) not shown._" in v.rollup(date(2030, 6, 1))


def test_a_shorter_record_says_nothing_about_hidden_weeks(tmp_path):
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-06", "type": "run",
                          "distance_km": 5.0, "source": "watch"})

    assert "not shown" not in v.rollup(date(2030, 6, 1))


def test_the_window_is_configurable_and_zero_means_all(tmp_path):
    """The default is a number somebody picked, so it is a declared setting
    rather than a constant buried in a renderer."""
    from vitai.config import Config

    assert Config().rollup_weeks == 12

    v = _record(tmp_path)
    for n in range(20):
        v.append("sessions", {
            "date": (date(2030, 1, 7) + timedelta(weeks=n)).isoformat(),
            "type": "run", "distance_km": 5.0, "source": "watch"})
    toml = v.root / "vitai.toml"
    toml.write_text(toml.read_text() + "\n[preferences]\nrollup_weeks = 0\n",
                    encoding="utf-8")

    assert len(_weeks(Vitai(v.root).rollup(date(2030, 6, 1)))) == 20


# --- a comparison nobody made ---------------------------------------------

def test_the_easy_cap_says_it_is_todays_cap(tmp_path):
    """`vitai.toml` has no history, so the engine cannot date the cap. `OVER
    +2` on a run from seven years earlier asserts a comparison that was never
    made; the rollup says once which cap it used rather than implying a
    contemporaneous one on every row."""
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-06", "type": "run",
                          "distance_km": 5.0, "avg_hr": 160,
                          "source": "watch"})
    # INTO the existing section rather than appending a second one: the
    # template already declares `[tripwires]`, and a duplicate table is a TOML
    # error rather than an override.
    toml = v.root / "vitai.toml"
    toml.write_text(toml.read_text().replace(
        "[tripwires]", "[tripwires]\neasy_hr_cap = 150", 1), encoding="utf-8")

    text = Vitai(v.root).rollup(date(2030, 6, 1))

    assert "OVER +10" in text
    assert "cap configured today (150), which the record cannot date" in text


def test_no_note_where_no_cap_is_configured(tmp_path):
    """A note about a comparison nobody made is itself noise."""
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-06", "type": "run",
                          "distance_km": 5.0, "avg_hr": 160,
                          "source": "watch"})

    assert "cannot date" not in v.rollup(date(2030, 6, 1))


def test_the_shipped_rollup_still_carries_its_markers():
    """The demo job asserts these, and a restructure that dropped one would
    pass every test above."""
    text = Vitai(DEMO).rollup(date(2030, 6, 30))

    assert "**Rate:**" in text
    assert "## Tripwires" in text
    assert text.startswith("# Weekly rollup")
    assert "derived, do not edit" in text
