"""The rollup states the direction and not the figure (#185, contract 32).

`verdicts` says `answers: direction` on `weight_rate`, because this project's
pre-registered run measured a median `u_rate / half-band` of 1.74 and found
more than half of scored weeks admit no verdict word at all. The rollup - the
engine's most-read artifact - went on printing "losing 0.45 kg/week" to two
decimal places anyway.

A contract the engine's own output does not honour is a contract nobody has to,
and this one was shipping in both states at once: a column telling a consumer
not to render the magnitude, beside prose rendering it.

WHAT STAYS. The direction, in words, because G69 put it there - a bare signed
quantity whose plain reading inverts its meaning showed "+1.10 kg/week" to an
athlete who had LOST 1.5 kg. The target, because a declared policy figure is
not a measurement. The verdict, and every caveat.
"""

from __future__ import annotations

import re
from pathlib import Path

from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _rate_line(text: str) -> str:
    line = [ln for ln in text.splitlines() if ln.startswith("**Rate:**")]
    assert line, "the rollup must carry a rate line or this proves nothing"
    return line[0]


def _measured_half(line: str) -> str:
    """Everything before the declared target.

    The naive check - no digit after "losing" anywhere on the line - matches
    the TARGET, which is a policy figure the athlete chose and which nothing
    here makes unquotable. Only the measured half is under the contract.
    """
    return line.split(", against a target of")[0].split(" (no phase")[0]


def test_the_rate_line_carries_no_measured_magnitude():
    """The one part the measurement cannot support."""
    measured = _measured_half(_rate_line(Vitai(DEMO).rollup()))

    assert not re.search(r"\d", measured), measured


def test_the_direction_survives_in_words():
    """G69's reason for putting it in words in the first place: the sign is a
    detail rather than the message, and reading it backwards is dangerous for
    a scale-anxious under-eater."""
    line = _rate_line(Vitai(DEMO).rollup())

    assert re.search(r"\*\*Rate:\*\* (losing|gaining|holding)", line), line


def test_the_declared_target_survives():
    """A policy figure is not a measurement. The athlete chose 0.35; nothing
    about the uncertainty of an observed rate makes their own target
    unquotable."""
    line = _rate_line(Vitai(DEMO).rollup())

    assert re.search(r"target of losing \d+\.\d\d kg/week", line), line


def test_the_verdict_and_its_caveat_survive():
    """#37's caveat is the payload, and dropping the magnitude must not take
    the sentence that explains it."""
    text = Vitai(DEMO).rollup()

    assert "NOT READABLE" in _rate_line(text)
    assert "Judge on this line, never a single morning." in text


def test_the_api_still_returns_the_number():
    """PROSE HONOURS THE CONTRACT; DATA CARRIES IT.

    `status()` is a dict a consumer reads, and contract 32's `answers` is what
    tells that consumer what the figure is good for. Removing it from the data
    would leave a client unable to compute anything at all, which is a
    different and worse failure than rendering it unqualified.
    """
    st = Vitai(DEMO).status("2030-06-30")

    assert st["rate_kg_per_week"] is not None
    assert st["direction"] in ("losing", "gaining", "holding")


def test_a_record_with_no_phase_target_still_reads(tmp_path):
    """The other branch of the same line."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for n, day in enumerate(("2030-05-01", "2030-05-02", "2030-05-03",
                             "2030-05-04", "2030-05-05", "2030-05-06",
                             "2030-05-07", "2030-05-08", "2030-05-09",
                             "2030-05-10")):
        v.append("weight", {"date": day, "kg": 82.0 - n * 0.1,
                            "source": "scale"})

    line = _rate_line(v.rollup())

    assert not re.search(r"\d", _measured_half(line)), line
    assert "no phase targets configured" in line
