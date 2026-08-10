"""A scale change fakes a trend (#33, item 3).

Two weight readings from two scales are not two samples of one series.
Consumer scales carry calibration offsets of a kilo or more, so concatenating
them puts a step at the seam that is arithmetically indistinguishable from real
weight change - and it lands exactly where a long gap makes a jump look
plausible, so the engine would confirm a change that is an instrument swap.

`origin` was written for this and no derivation read it. Measured before
building: nothing in `clocks`, `verdicts` or `report` mentioned it, and the
shipped demo's recent weight window spanned more than one device while
`weight_rate` scored it with nothing anywhere saying so. The same "specified,
validated, never read" shape as `protocol` before #174 and `coverage` before
#186.

SCOPE. This is item 3 of the issue - the seam as data, visible in any output
that spans it. Items 1 and 2 (instrument as a first-class dimension, and a
comparability rule between instruments) are #171's decided scope and are not
touched here; item 3 needs neither, because a seam is a fact about the rows
rather than a claim about the devices.

NOT A SPLIT. #315 split `weight` by protocol and made
`safety._loss_pct_per_week` pick endpoints protocol-blind, which silently
stopped a RED-S hold firing. That change was withdrawn and only the seam flag
shipped. This does the same: it reports and moves nothing.

THE CORPUS DOES NOT EXERCISE IT, measured: no persona has a genuine instrument
swap inside a rate window, and every weight verdict across the corpus is
byte-identical before and after. That is the issue's own argument for building
it now - "before the second source lands, not after" - and it is why the cases
below are constructed.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.clocks import instrument_seam
from vitai.schema import KEYS

PERSONAS = Path(__file__).resolve().parent / "fixtures" / "personas"


def row(when: str, kg: float, origin: str | None, source: str = "scale") -> dict:
    return {**{k: None for k in KEYS["weight"]}, "date": when, "kg": kg,
            "source": source, "origin": origin,
            "recorded_at": f"{when}T07:00:00Z"}


# --- what counts as a seam ------------------------------------------------------

def test_two_scales_across_a_window_are_a_seam():
    """CATALOGUED NAMES ON BOTH SIDES. The first version of this used
    `aria-scale`, which the registry has never seen, so it seamed only because
    the OTHER name happened to be catalogued - the control did not prove the
    rule for the device family the issue is named after."""
    got = instrument_seam([row("2030-05-01", 82.0, "fitbit-scale"),
                           row("2030-05-10", 79.0, "withings-scale")])
    assert got["seam"] is True
    assert got["instruments"] == ["fitbit-scale", "withings-scale"]
    assert (got["stated"], got["silent"]) == (2, 0)


def test_two_uncatalogued_scales_are_still_two_scales():
    """THE HOLE REVIEW FOUND, and it defeated the guardrail for exactly the
    import this issue exists for.

    `resolve_source` maps any name the catalogue has never seen to a single
    `other` key, deliberately. Folding through it made every uncatalogued
    device the SAME device, so two genuinely different scales intersected on
    `{other}` and produced no seam. Takeout and Apple Health carry arbitrary
    `sourceName` strings, which is the whole point of the sequencing note.

    It is in shipped data already: `bathroom-scale` and `gym-scale` both
    resolve to `other`."""
    got = instrument_seam([row("2030-05-01", 82.0, "eufy-scale"),
                           row("2030-05-10", 79.0, "salter-scale")])
    assert got["seam"] is True, got

    ines = instrument_seam([row("2030-05-01", 64.0, "bathroom-scale"),
                            row("2030-05-10", 65.8, "gym-scale")])
    assert ines["seam"] is True, ines


def test_an_unnamed_spelling_of_a_named_device_seams_and_that_is_the_safe_way():
    """`aria` is catalogued and `aria-scale` is not, so they read as two.
    Nothing in the record says they are one scale; the fix is an alias in the
    registry, which is data. The alternative is fuzzy matching on names, which
    is the line `protocol_seam` draws in as many words."""
    got = instrument_seam([row("2030-05-01", 82.0, "aria"),
                           row("2030-05-10", 81.0, "aria-scale")])
    assert got["seam"] is True, got


def test_a_placeholder_is_not_an_instrument():
    """The rule `protocol_seam` states thirty lines up and pins with its own
    test. Letting a dash through manufactured a refusal out of punctuation,
    and the report would have printed "- then withings-scale"."""
    for junk in ("-", " ", "___"):
        got = instrument_seam([row("2030-05-01", 82.0, junk),
                               row("2030-05-10", 79.0, "withings-scale")])
        assert got["seam"] is False, (junk, got)
        assert got["instruments"] == ["withings-scale"], junk


def test_the_reported_order_is_the_record_s_not_the_file_s():
    """"An ordering a formatter can change is not an ordering" - this module's
    own acceptance criterion, which `protocol_seam` pins with reversed rows
    and this did not. The report joins these with "then"."""
    rows = [row("2030-05-10", 79.0, "withings-scale"),
            row("2030-05-01", 82.0, "fitbit-scale")]
    assert instrument_seam(rows)["instruments"] == ["fitbit-scale",
                                                    "withings-scale"]
    assert instrument_seam(list(reversed(rows)))["instruments"] == [
        "fitbit-scale", "withings-scale"]


def test_the_first_spelling_is_the_one_reported():
    """The athlete's own words are what a reader should see, and only the
    COMPARISON folds - `protocol_seam`'s rule again. Which spelling survives
    was unwitnessed."""
    got = instrument_seam([row("2030-05-01", 82.0, "Withings-Scale"),
                           row("2030-05-10", 81.0, "withings-scale")])
    assert got["instruments"] == ["Withings-Scale"], got
    assert got["seam"] is False


def test_one_instrument_throughout_is_not_a_seam():
    got = instrument_seam([row("2030-05-01", 82.0, "aria-scale"),
                           row("2030-05-10", 81.4, "aria-scale")])
    assert got["seam"] is False


def test_a_corroborated_reading_is_not_a_swap():
    """THE CASE THAT CHANGED THE RULE. A canonical row can read `dexa+scale`,
    meaning two devices observed ONE reading. Counting distinct names, the
    shipped demo seamed on `scale, scale, dexa+scale, scale` - where every
    reading includes a scale observation and the series is comparable.

    So a seam is NO COMMON INSTRUMENT, not "more than one name"."""
    got = instrument_seam([row("2030-05-01", 82.0, "scale"),
                           row("2030-05-02", 81.9, "dexa+scale"),
                           row("2030-05-03", 81.8, "scale")])
    assert got["seam"] is False
    assert got["instruments"] == ["scale", "dexa"], "both are still reported"


def test_a_reading_only_one_device_saw_after_readings_only_another_saw():
    """The other side of the same rule: no instrument is behind every reading,
    so there is no series to take a rate from."""
    got = instrument_seam([row("2030-05-01", 82.0, "dexa"),
                           row("2030-05-02", 81.9, "scale")])
    assert got["seam"] is True


def test_silence_is_not_an_instrument():
    """A record that has never used the field must not acquire a seam the day
    it starts. 45% of the corpus's rows that name a source or an origin at
    all name only a channel, so the alternative would seam almost
    everything."""
    got = instrument_seam([row("2030-05-01", 82.0, None),
                           row("2030-05-10", 79.0, None)])
    assert got["seam"] is False
    assert (got["stated"], got["silent"]) == (0, 2)

    mixed = instrument_seam([row("2030-05-01", 82.0, "aria-scale"),
                             row("2030-05-10", 79.0, None)])
    assert mixed["seam"] is False, "one named instrument and a silent row"
    assert (mixed["stated"], mixed["silent"]) == (1, 1)


def test_a_person_is_not_an_instrument():
    """#94 settled this one issue over: `origin: athlete` is the athlete
    writing down what they read, not a device. Counting it seamed the shipped
    demo against its own hand-entered rows - declining a rate because somebody
    typed a number in."""
    got = instrument_seam([row("2030-05-01", 82.0, "scale"),
                           row("2030-05-02", 82.1, "athlete", source="hand")])
    assert got["seam"] is False
    assert "athlete" not in got["instruments"]


def test_one_instrument_spelled_two_ways_is_one():
    """The registry fold, which #174 already paid for on the protocol axis."""
    got = instrument_seam([row("2030-05-01", 82.0, "polar-watch"),
                           row("2030-05-10", 81.0, "Polar-Watch")])
    assert got["seam"] is False, got


def test_an_empty_window_is_not_a_seam():
    assert instrument_seam([])["seam"] is False


# --- and what it does to a rate ------------------------------------------------

def record(tmp_path: Path, rows: list[dict]) -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[targets]\nphases = [[90.0, 70.0, 0.5]]\n',
        encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root, on=date(2030, 5, 14))


def series(origin_a: str, origin_b: str) -> list[dict]:
    """A fortnight of daily readings, the second week on another device."""
    out = []
    for n in range(1, 15):
        origin = origin_a if n <= 7 else origin_b
        out.append(row(f"2030-05-{n:02d}", 82.0 - n * 0.2, origin))
    return out


def test_a_rate_across_a_scale_change_is_declined(tmp_path):
    """The acceptance criterion: a weight series spanning two scales cannot
    produce a rate, and the record says why."""
    v = record(tmp_path, series("aria-scale", "withings-scale"))
    # The weeks that HAVE a rate to judge. The earliest declines for
    # `no_input` - one week of data is not a fortnight - and that refusal is a
    # different one, so asserting over it would blur what this test pins.
    rates = [r for r in v.verdicts()
             if r["metric"] == "weight_rate" and r["value"] is not None]
    assert rates, "the record has a rate to decline"
    assert all(r["verdict"] == "no_data" for r in rates), rates
    assert all(r["reason"] == "not_supported" for r in rates), rates


def test_the_same_series_on_one_scale_is_scored(tmp_path):
    """The control on the control: without the swap the identical numbers
    produce a verdict, so the refusal is the instrument change and not the
    shape of the data."""
    v = record(tmp_path, series("aria-scale", "aria-scale"))
    rates = [r for r in v.verdicts() if r["metric"] == "weight_rate"]
    assert any(r["verdict"] != "no_data" for r in rates), rates


def test_the_seam_is_visible_in_the_rollup(tmp_path):
    """"A seam is visible in any output that spans it." No direction word and
    no target beside it, for the reason the protocol seam gives: saying
    "losing, and also NOT COMPARABLE" hands the reader the number's meaning
    and then withdraws it."""
    out = record(tmp_path, series("aria-scale", "withings-scale")).rollup()
    line = [ln for ln in out.splitlines() if ln.startswith("**Rate:**")][0]
    assert "NOT COMPARABLE" in line
    assert "different instruments" in line
    assert "aria-scale" in line and "withings-scale" in line
    for word in ("losing", "gaining", "holding", "target of"):
        assert word not in line, (word, line)


def test_it_does_not_tell_the_athlete_to_be_consistent(tmp_path):
    """The protocol seam says "weigh in the same way and this line comes
    back". An instrument change is not a habit: a scale is replaced once and
    the old readings are permanent, so advice to be consistent would be about
    the wrong thing."""
    out = record(tmp_path, series("aria-scale", "withings-scale")).rollup()
    assert "Weigh in the same way" not in out
    assert "shares one instrument" in out


def test_no_corpus_window_seams():
    """No persona has a genuine swap inside ANY rate window, so this ships
    with every existing weight verdict intact.

    EVERY WINDOW, not the trailing one. The first version checked
    `rows[-14:]` - fourteen READINGS rather than a fortnight, and only the
    last of them - so a swap in an older window would have slipped it, which
    is exactly where `ines` has two multi-scale windows."""
    checked = 0
    for path in sorted(PERSONAS.iterdir()):
        if not (path / "vitai.toml").exists():
            continue
        rows = sorted(Vitai(path).canonical("weight"),
                      key=lambda r: str(r.get("date")))
        for start in range(len(rows)):
            window = rows[start:start + 14]
            if len(window) < 2:
                continue
            checked += 1
            got = instrument_seam(window)
            assert not got["seam"], (path.name, window[0]["date"], got)
    assert checked > 300, checked
