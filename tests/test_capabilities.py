"""What an instrument can and cannot measure, dated (#171).

An instrument change is a confound that looks exactly like a physiological one:
a resting heart rate stepping from 54 to 49 is either a training adaptation or
a new optical sensor. `origin` said which instrument observed a value and
nothing said what that instrument is competent at.

CATEGORICAL, NEVER A NUMBER, after the issue surveyed what vendors publish:
only power meters publish anything, those cover the random term alone, field
observation contradicts them by up to twenty percent, and one vendor's marketed
tolerance is half its own service tolerance. A borrowed figure would be a
confident wrong number about confidence.

KEYED ON `origin`, the identity 27 call sites already use for an instrument.
#311's device register later gives that string an entity with an interval;
this enriches the same identity rather than minting a second one.

SCOPE. This ships the dataset, its dating and its public surface. Comparability
between instruments EARNED BY OVERLAP, and coverage, are the issue's other two
halves and are not here - both are derived from the record rather than stated
in it, and neither can be computed before there is somewhere to put the answer.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import COMPETENCES, KEYS, validate_record

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def row(when: str, origin: str, measures: str, competence: str, **kw) -> dict:
    return {**{k: None for k in KEYS["capabilities"]}, "date": when,
            "origin": origin, "measures": measures, "competence": competence,
            "set_by": "athlete", "recorded_at": f"{when}T08:00:00Z", **kw}


def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "capabilities.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root, on=date(2030, 6, 30))


# --- silence resolves to a value, not to a default -----------------------------

def test_an_instrument_nobody_has_written_about_answers_unknown(tmp_path):
    """THE #148 LESSON, one dataset over, and the reason there is no default.

    There, baselines lived in `vitai.toml` - a mutable file OUTSIDE the
    append-only record - and dated rows overlaid it, so any week with no dated
    row was judged by whatever that file said TODAY. A reconstruction of March
    returned March's data under September's policy.

    A capability default in `semantics/` would be identical: every window with
    no capability row judged by whatever this build ships. So silence resolves
    to `unknown`, a value in the vocabulary."""
    got = record(tmp_path, []).capability("polar-watch", "rhr")
    assert got["competence"] == "unknown"
    assert got["stated"] is False
    assert got["construct"] is None and got["basis"] is None


def test_unknown_and_absent_are_different_facts(tmp_path):
    """"Nobody has said" and "it does not measure this" are different, and a
    consumer can act on both. Collapsing them is what a default would do."""
    v = record(tmp_path, [row("2030-01-01", "aria-scale", "body_fat_pct",
                              "absent")])
    assert v.capability("aria-scale", "body_fat_pct")["competence"] == "absent"
    assert v.capability("aria-scale", "kg")["competence"] == "unknown"
    assert "absent" in COMPETENCES and "unknown" in COMPETENCES


def test_it_never_returns_none(tmp_path):
    """A null is a thing a consumer has to interpret, and the interpretations
    differ. Every question gets a competence."""
    v = record(tmp_path, [])
    for measures in ("rhr", "kg", "steps", "sleep_h"):
        assert v.capability("anything", measures)["competence"] == "unknown"


# --- dated, through the machinery policy already uses ---------------------------

def test_a_capability_is_read_as_of_a_date(tmp_path):
    """A statement takes effect on its own date and a past day never sees a
    later one - the property `policy.state` already has, reused rather than
    reimplemented."""
    v = record(tmp_path, [
        row("2030-01-01", "polar-watch", "rhr", "measures", basis="stated"),
        row("2030-06-01", "polar-watch", "rhr", "proxy", basis="observed",
            construct="a daytime spot statistic, not the nightly minimum")])

    assert v.capability("polar-watch", "rhr", on="2030-03-01")["competence"] \
        == "measures"
    later = v.capability("polar-watch", "rhr", on="2030-06-15")
    assert later["competence"] == "proxy"
    assert "nightly minimum" in later["construct"]


def test_a_statement_dated_after_the_question_is_invisible(tmp_path):
    v = record(tmp_path, [row("2030-06-01", "polar-watch", "rhr", "proxy",
                              construct="a spot statistic")])
    assert v.capability("polar-watch", "rhr", on="2030-01-01")["competence"] \
        == "unknown"


def test_the_identity_is_instrument_and_measurand_and_condition(tmp_path):
    """Keying on the instrument alone would make each new statement retire the
    last. A watch can be competent at steps and a proxy for sleep, and
    competent at heart rate seated while only a proxy for it at threshold."""
    v = record(tmp_path, [
        row("2030-01-01", "polar-watch", "steps", "measures"),
        row("2030-01-01", "polar-watch", "rhr", "measures"),
        row("2030-01-01", "polar-watch", "rhr", "proxy", condition="threshold",
            construct="a smoothed estimate under load")])

    assert v.capability("polar-watch", "steps")["competence"] == "measures"
    assert v.capability("polar-watch", "rhr")["competence"] == "measures"
    scoped = v.capability("polar-watch", "rhr", condition="threshold")
    assert scoped["competence"] == "proxy"
    assert "under load" in scoped["construct"]


def test_the_dating_machinery_is_shared_not_copied():
    """`policy._in_force` is what dates goals and thresholds, and it handles a
    TUPLE identity now - it read `r.get(ident)` with whatever `IDENTITY_KEY`
    declared, which returns None for a tuple, so every row of a tuple-keyed
    dataset was silently skipped. It had only ever been called with
    scalar-keyed ones, so the gap cost nothing and was invisible."""
    from vitai.policy import _in_force

    rows = [row("2030-01-01", "a", "kg", "measures"),
            row("2030-02-01", "b", "kg", "measures")]
    got = _in_force(rows, "capabilities", "2030-06-01")
    assert len(got) == 2, got


# --- what a claim owes ----------------------------------------------------------

def test_a_proxy_must_name_what_it_actually_measures():
    """The rule that makes this useful rather than a label. "This is a proxy"
    says distrust the number; "this is a proxy FOR the continuous nightly
    minimum" says what it is - and no uncertainty figure would ever catch a
    wrong measurand, because every one of them assumes the right one."""
    bad = row("2030-01-01", "polar-watch", "rhr", "proxy")
    problems = validate_record("capabilities", bad)
    assert any("construct" in p for p in problems), problems

    good = row("2030-01-01", "polar-watch", "rhr", "proxy",
               construct="a daytime spot statistic")
    assert validate_record("capabilities", good) == []


def test_a_construct_has_no_meaning_beside_the_others():
    """Forbidden for the reason `derived_build` is forbidden beside `by-hand`:
    a field that is sometimes an answer and sometimes decoration is one a
    reader learns to skip."""
    rec = row("2030-01-01", "polar-watch", "steps", "measures",
              construct="something")
    assert any("construct" in p for p in validate_record("capabilities", rec))


def test_the_competence_vocabulary_is_closed():
    rec = row("2030-01-01", "polar-watch", "steps", "probably")
    assert any("competence" in p for p in validate_record("capabilities", rec))
    assert COMPETENCES == {"measures", "proxy", "absent", "unknown"}


def test_it_can_only_be_about_a_field_the_record_has():
    rec = row("2030-01-01", "polar-watch", "vibes", "measures")
    assert any("measures" in p for p in validate_record("capabilities", rec))


def test_no_row_carries_a_number():
    """The issue's central finding, enforced by the column set rather than by
    a rule somebody has to remember: there is nowhere to put an uncertainty, a
    tolerance or an offset."""
    for field in ("uncertainty", "tolerance", "offset", "sd", "error", "bias"):
        assert field not in KEYS["capabilities"], field


# --- the surfaces ---------------------------------------------------------------

def test_the_demo_states_three_and_the_fourth_is_the_absence():
    """One of each competence the record can state. `unknown` is deliberately
    NOT written: writing it would be writing the default the engine refuses to
    keep in a file."""
    v = Vitai(DEMO)
    assert v.capability("scale", "rhr")["competence"] == "proxy"
    assert v.capability("scale", "kg")["competence"] == "measures"
    assert v.capability("scale", "body_fat_pct",
                        condition="hydrated")["competence"] == "absent"
    assert v.capability("scale", "steps")["competence"] == "unknown"

    stated = {r["competence"] for r in v.capabilities()}
    assert "unknown" not in stated, stated


def test_it_reaches_the_read_model():
    import sqlite3

    con = sqlite3.connect(Vitai(DEMO).build())
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(capabilities)")]
        assert "competence" in cols and "construct" in cols
        got = con.execute("SELECT competence FROM capabilities "
                          "WHERE measures = 'rhr'").fetchone()
        assert got == ("proxy",), got
    finally:
        con.close()


def test_it_reaches_the_cli():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["capabilities", "--root", str(DEMO)])
    out = buf.getvalue()
    assert "scale: rhr - proxy" in out, out
    assert "actually measures: a daytime spot statistic" in out, out


def test_it_reaches_the_agent_surface():
    from vitai.mcp import call, tool_list

    assert any(t["name"] == "capabilities" for t in tool_list())
    got = call(DEMO, "capabilities", {})
    assert [r["measures"] for r in got]
    assert all("competence" in r for r in got)


def test_the_cli_says_so_when_nothing_is_stated(tmp_path):
    from vitai.cli import main

    v = record(tmp_path, [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["capabilities", "--root", str(v.root)])
    out = buf.getvalue()
    assert "no instrument has a stated capability" in out
    assert "gap in the record" in out, "and it says whose gap it is"
