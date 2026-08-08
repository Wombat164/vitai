"""A protocol is what pins down the measurand (#174, proposal 4).

`weight.protocol` was written from row one, validated, and read by nothing.
Two things followed from that, and the second is the worse one.

A TREND ACROSS A PROTOCOL CHANGE was reported as a rate. `fasted-post-void`
and `fed-evening-clothed` are not two readings of one quantity; they differ by
breakfast, a day's fluid and a pair of shoes. The engine already declines a
rate whose weigh-in TIMES are spread widely enough to account for it - this is
the same refusal with a discrete cause instead of a continuous one, which is
the calibration-seam argument applied to procedure rather than instrument.

AND A VALIDLY RECORDED READING WAS BEING DISCARDED. Resolution bucketed
`weight` by date alone, so a 06:40 fasted weigh-in and an 18:05 fed one landed
in one contest and the ladder threw the second away - the engine's own
explanation read `discarded: hand=65.8`. `measurements` has had the right rule
all along, one line up in the same function: each KIND is its own quantity, so
a waist reading and a body-fat read on one day do not compete. `protocol` is
that same statement for body mass.

NO SIZE ESTIMATE ANYWHERE IN THIS. It would be easy to hold a table of what a
clothed evening weigh-in adds and subtract it. That is a per-protocol accuracy
claim about equipment and habits this engine has never seen, and it is the
figure the project refuses to invent everywhere else. What the record supports
is that the procedure changed, which is enough to decline the comparison.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.clocks import protocol_seam
from vitai.config import Config
from vitai.report import build_report
from vitai.schema import KEYS

INES = Path(__file__).resolve().parent / "fixtures" / "personas" / "ines"
TODAY = date(2030, 6, 10)


def weigh(day: str, kg: float, protocol=None, source="scale", at="06:40") -> dict:
    return {**{k: None for k in KEYS["weight"]}, "date": day, "kg": kg,
            "source": source, "protocol": protocol, "measured_at": at,
            "recorded_at": f"{day}T07:00:00+01:00"}


def record(tmp_path: Path, rows: list[dict], toml: str = "") -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


# --- the detector -------------------------------------------------------------

def test_one_protocol_is_not_a_seam():
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 69.8, "fasted-post-void")])
    assert scope["seam"] is False
    assert scope["protocols"] == ["fasted-post-void"]
    assert scope["stated"] == 2 and scope["silent"] == 0


def test_two_protocols_are():
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert scope["seam"] is True
    assert scope["protocols"] == ["fasted-post-void", "fed-evening-clothed"]


def test_silence_is_not_a_protocol():
    """A record that has never used the field must not acquire a seam the day
    it starts, and a run of unnamed rows beside one named row is an unanchored
    INTERVAL rather than a change of procedure - which is the rest of #174 and
    is not decided here."""
    scope = protocol_seam([weigh("2030-05-01", 70.0),
                           weigh("2030-05-08", 69.8, "fasted-post-void")])
    assert scope["seam"] is False
    assert scope["stated"] == 1 and scope["silent"] == 1
    assert protocol_seam([weigh("2030-05-01", 70.0)])["seam"] is False
    assert protocol_seam([])["seam"] is False


def test_an_empty_string_is_silence_not_a_protocol():
    assert protocol_seam([weigh("2030-05-01", 70.0, ""),
                          weigh("2030-05-08", 69.8, "fasted-post-void")
                          ])["seam"] is False


def test_the_detector_states_no_size():
    """The refusal says the procedure changed and stops. A figure for what a
    clothed evening weigh-in adds would be a per-protocol accuracy claim about
    hardware and habits the engine has never seen."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert set(scope) == {"protocols", "seam", "stated", "silent"}
    assert not any(isinstance(v, float) for v in scope.values())


# --- the refusal, through the surfaces ----------------------------------------

def _seam_record(tmp_path: Path) -> Vitai:
    """SAME TIME, DIFFERENT PROCEDURE, and the sameness is deliberate.

    A fed evening weigh-in also moves the clock, so a fixture built that way
    trips the #37 timing-drift refusal as well and proves nothing about this
    one - the mutation pass caught exactly that. Here the athlete keeps
    weighing at 06:40 and starts doing it clothed, so the protocol is the only
    thing that changed and the refusal can only have come from it.
    """
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
            for d in range(1, 15)]
    rows += [weigh(f"2030-05-{d:02d}", 71.5 - d * 0.05, "fasted-clothed")
             for d in range(15, 29)]
    return record(tmp_path, rows,
                  "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")


def test_a_rate_across_the_seam_is_declined_in_the_verdicts(tmp_path):
    """`not_supported`, the same reason the timing-drift refusal uses: the
    measurement cannot support the judgement. Not `no_policy` - there is a
    target - and not a verdict, because a consumer renders AHEAD or BEHIND as
    fact."""
    v = _seam_record(tmp_path)
    crossing = [r for r in v.verdicts()
                if r.get("metric") == "weight_rate" and r["week"] == "2030-05-13"]
    assert crossing, [r["week"] for r in v.verdicts()
                      if r.get("metric") == "weight_rate"]
    assert crossing[0]["verdict"] == "no_data"
    assert crossing[0]["reason"] == "not_supported"


def test_the_rollup_says_the_protocol_changed_rather_than_the_times_varied():
    """Two different sentences for two different problems. "Weigh-in times
    vary" is a habit to tighten; a protocol change is a boundary the rate does
    not cross, and telling somebody to weigh more consistently would be advice
    about the wrong thing."""
    # The seam has to fall inside the rate's OWN window - it judges the seven
    # days it computes over and nothing else, which is #68's rule and stays
    # true here.
    rows = [weigh(f"2030-06-{d:02d}", 70.0 - d * 0.02, "fasted-post-void")
            for d in range(1, 6)]
    rows += [weigh(f"2030-06-{d:02d}", 71.4 - d * 0.02, "fasted-clothed")
             for d in range(6, 10)]
    out = build_report(Config(phases=((70.0, 68.0, 0.15),)), rows, [], [],
                       today=TODAY)
    assert "NOT COMPARABLE" in out, out
    assert "protocol changed" in out, out
    assert "fasted-clothed then fasted-post-void" in out, out
    assert "weigh-in times vary too much" not in out, out


def test_a_rate_under_one_protocol_is_untouched(tmp_path):
    """The control. Everything above must cost nothing to a record that
    weighs itself the same way every time."""
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
            for d in range(1, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates
    assert not any(r["reason"] == "not_supported" for r in rates), rates


def test_a_record_that_never_names_a_protocol_is_untouched(tmp_path):
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05) for d in range(1, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates
    assert not any(r["reason"] == "not_supported" for r in rates), rates


# --- and the reading is not discarded -----------------------------------------

def test_two_protocols_on_one_day_are_two_quantities_not_a_contest(tmp_path):
    """The defect underneath the seam. Bucketing `weight` by date alone put a
    06:40 fasted weigh-in and an 18:05 fed one into one contest, and the ladder
    discarded the second: `discarded: hand=65.8`. A validly recorded reading
    disappearing because another reading shares its date is the one thing an
    append-only record must not do."""
    v = record(tmp_path, [weigh("2030-05-30", 64.14, "fasted-post-void"),
                          weigh("2030-05-30", 65.8, "fed-evening-clothed",
                                source="hand", at="18:05")])
    kept = sorted((r["kg"], r["protocol"]) for r in v.canonical("weight"))
    assert kept == [(64.14, "fasted-post-void"), (65.8, "fed-evening-clothed")]
    assert not [e for e in v.resolution()["explanations"]
                if e.get("field") == "kg"], "nothing was adjudicated away"


def test_two_readings_under_ONE_protocol_still_compete(tmp_path):
    """The rule is not "never merge two weigh-ins". Two claims about the SAME
    measurand on one day are exactly what the ladder is for, and splitting
    those would turn every duplicate import into two rows."""
    v = record(tmp_path, [weigh("2030-05-30", 64.14, "fasted-post-void"),
                          weigh("2030-05-30", 64.2, "fasted-post-void",
                                source="hand")])
    assert len(v.canonical("weight")) == 1


def test_rows_naming_no_protocol_group_together(tmp_path):
    """`None` is one bucket, not one bucket each - so a record that has never
    used the field adjudicates exactly as it did before."""
    v = record(tmp_path, [weigh("2030-05-30", 64.14),
                          weigh("2030-05-30", 64.2, source="hand")])
    assert len(v.canonical("weight")) == 1


def test_ines_e2_is_answered():
    """The persona expectation this was filed against, checked against the
    shipped corpus rather than a fixture written to pass.

    ines-E2: "the reading is not an error and must not be dropped, and it is
    also not comparable with the rest."
    """
    v = Vitai(INES)
    day = [r for r in v.canonical("weight") if r["date"] == "2030-05-30"]
    assert sorted(r["kg"] for r in day) == [64.14, 65.8], "not dropped"
    assert {r["protocol"] for r in day} == {"fasted-post-void",
                                            "fed-evening-clothed"}
    crossing = [r for r in v.verdicts() if r.get("metric") == "weight_rate"
                and r["week"] == "2030-05-27"]
    assert crossing[0]["reason"] == "not_supported", "not comparable"
