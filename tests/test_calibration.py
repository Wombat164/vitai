"""What an overlap between two instruments measured, and what it will not say.

#402 requires that an error band be EARNED - from a measured overlap, a
per-reading uncertainty or a stated range, and from nowhere else.
`comparability` is the dataset that holds a measured overlap and it had no
writer anywhere, so the rule said earn it and there was nothing to earn it
from. `calibration.overlap_calibration` is that pipeline.

MOST OF WHAT FOLLOWS IS THE REFUSALS. Computing a median and a range is
arithmetic; the value of this derivation is entirely in the cases where it
declines - a thin overlap, an ambiguous day, a status it has no business
deciding - because a `comparability` row nobody can trust is worse than an
empty dataset. It is the trustworthiness of the row that the whole feature
rests on.

THE CORPUS CROSS-CHECK AVOIDS THE CIRCULARITY #386 NAMES. `vera`'s
`comparability.jsonl` is AUTHORED by her generator from the runs it builds,
using the plain arithmetic the row is meant to state. The derivation computes
the same figures from the COMMITTED session rows by a different route. The
test below asserts three things agree: the authored row, the derivation, and a
deliberately naive calculation written out longhand here. Had the generator
called `overlap_calibration` to author the row, the comparison would be a
value against itself.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.calibration import MIN_PAIRS, overlap_calibration

VERA = Path(__file__).parent / "fixtures" / "personas" / "vera"


def run(day: str, origin: str, km: float) -> dict:
    return {"date": day, "origin": origin, "distance_km": km}


def pairs(n: int, diff: float = 0.1) -> list[dict]:
    out = []
    for i in range(n):
        day = f"2030-01-{i + 1:02d}"
        out += [run(day, "watch", 10.0), run(day, "phone", 10.0 + diff)]
    return out


# --- what it measures ---------------------------------------------------------

def test_it_reports_bias_and_spread_as_separate_facts():
    """THE FINDING THIS DATASET EXISTS TO CARRY. A median says which way the
    two lean; a spread says how far apart they got. A pair that agrees on
    average and disagrees per reading has a small first number and a large
    second, and any design collapsing them would report it as agreement."""
    rows = (pairs(6, diff=0.0)
            + [run("2030-02-01", "watch", 12.0), run("2030-02-01", "phone", 10.8)])
    out = overlap_calibration(rows, "distance_km", "watch", "phone")
    assert out["row"]["bias"] == 0.0, "they lean nowhere"
    assert out["row"]["spread"] == 1.2, "and they are 1.2 apart at the worst"


def test_the_pair_is_normalised_so_the_sign_is_fixed():
    """Asking whether two instruments agree is one question regardless of
    which is named first, so the answer must not depend on the phrasing."""
    rows = pairs(4, diff=0.25)
    one = overlap_calibration(rows, "distance_km", "watch", "phone")
    other = overlap_calibration(rows, "distance_km", "phone", "watch")
    assert one["row"] == other["row"]
    assert (one["row"]["origin_a"], one["row"]["origin_b"]) == ("phone", "watch")


def test_the_asymmetry_is_reported_beside_the_row_not_inside_it():
    """THE LIMIT THIS MODULE REFUSES TO HIDE. `bias` is a point and `spread` a
    width, so a range running further one way than the other cannot be written
    down. Folding it into a plus-or-minus would be wrong on both sides at once,
    so the two tails are returned separately and the row carries neither."""
    rows = pairs(6, diff=0.0) + [run("2030-03-01", "watch", 11.5),
                                 run("2030-03-01", "phone", 10.0)]
    out = overlap_calibration(rows, "distance_km", "watch", "phone")
    assert out["observed"]["asymmetric"] is True
    assert out["observed"]["low"] == 0.0
    assert out["observed"]["high"] == 1.5
    # Nothing on the row can express that, and nothing pretends to.
    assert set(out["row"]) == {
        "date", "field", "origin_a", "origin_b", "status", "bias", "spread",
        "basis", "overlap_ref", "note", "source"}


def test_a_symmetric_range_says_so():
    """The other side of the check above, so `asymmetric` is a measurement
    rather than a constant that happens to read True on the corpus."""
    rows = (pairs(3, diff=0.0)
            + [run("2030-04-01", "watch", 10.5), run("2030-04-01", "phone", 10.0),
               run("2030-04-02", "watch", 9.5), run("2030-04-02", "phone", 10.0)])
    out = overlap_calibration(rows, "distance_km", "watch", "phone")
    assert out["observed"]["asymmetric"] is False


# --- what it refuses ----------------------------------------------------------

def test_a_thin_overlap_produces_no_row():
    """NO NUMBER IS INVENTED. A row with a spread nobody measured is worse
    than an empty dataset, because the entire value of the dataset is that a
    band resting on it can be trusted."""
    out = overlap_calibration(pairs(MIN_PAIRS - 1), "distance_km",
                              "watch", "phone")
    assert out["row"] is None
    assert "at least 3" in out["refused"]
    assert out["observed"] is None, "nothing measured, nothing reported"


def test_the_smallest_overlap_that_works_does_work():
    """So the refusal above is a boundary rather than a rule that never lets
    anything through."""
    out = overlap_calibration(pairs(MIN_PAIRS), "distance_km", "watch", "phone")
    assert out["row"] is not None
    assert out["refused"] is None


def test_a_day_with_two_readings_from_one_origin_is_dropped_not_guessed():
    """Two runs on a Saturday and two watch rows is four ways to pair them and
    no rule in the record for choosing, so the day says nothing about how the
    instruments compare. Dropped days are REPORTED - an overlap thin because
    half of it was ambiguous is a different fact from one that was thin."""
    rows = pairs(4) + [run("2030-02-02", "watch", 10.0),
                       run("2030-02-02", "watch", 5.0),
                       run("2030-02-02", "phone", 10.1)]
    out = overlap_calibration(rows, "distance_km", "watch", "phone")
    assert out["pairs"] == 4
    assert out["ambiguous_days"] == ["2030-02-02"]


def test_it_never_proposes_comparable():
    """THE BOUNDARY BETWEEN MEASURING AND DECLARING, and the corpus is what
    proved it necessary. `comparable` LIFTS the seam refusal. An earlier
    version chose the status from the arithmetic and called a pair comparable
    when the median came out at zero - which `vera` produces across two
    instruments differing by over a kilometre on a given run. A measured
    difference of zero is an offset of zero, and whether the two are on one
    footing is the athlete's to say."""
    out = overlap_calibration(pairs(5, diff=0.0), "distance_km",
                              "watch", "phone")
    assert out["row"]["status"] == "offset"
    assert out["row"]["bias"] == 0.0
    assert out["row"]["spread"] == 0.0


def test_a_reading_after_the_viewpoint_is_not_evidence():
    rows = pairs(4) + [run("2030-06-01", "watch", 99.0),
                       run("2030-06-01", "phone", 1.0)]
    out = overlap_calibration(rows, "distance_km", "watch", "phone",
                              on=date(2030, 5, 1))
    assert out["pairs"] == 4
    assert out["row"]["spread"] == 0.0


def test_the_basis_is_always_overlap():
    """`basis` is a closed vocabulary of one value, because the whole point is
    that this cannot be asserted from a datasheet or a vendor figure."""
    out = overlap_calibration(pairs(4), "distance_km", "watch", "phone")
    assert out["row"]["basis"] == "overlap"


# --- the corpus, by three routes ---------------------------------------------

def _committed_diffs() -> list[float]:
    """The differences, calculated longhand off the committed rows.

    DELIBERATELY NAIVE. This is the third opinion, and it is worth having only
    while it shares no code with either of the other two - so it reads the
    files, pairs by date, subtracts, and does nothing clever."""
    by_day: dict[str, dict[str, float]] = {}
    path = VERA / "data" / "sessions.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_day.setdefault(row["date"], {})[row["origin"]] = row["distance_km"]
    return sorted(round(v["watch"] - v["phone"], 6) for v in by_day.values()
                  if "watch" in v and "phone" in v)


def test_the_corpus_carries_a_measured_overlap():
    """The gap this closes: no record anywhere wrote a `comparability` row, so
    #402's route 1 had zero machine-readable evidence to rest on."""
    rows = Vitai(VERA).dataset("comparability")
    assert len(rows) == 1, rows
    assert rows[0]["basis"] == "overlap"
    assert rows[0]["field"] == "distance_km"


def test_the_authored_row_the_derivation_and_longhand_all_agree():
    """THREE ROUTES TO ONE NUMBER. The row `vera` wrote, the derivation over
    her committed sessions, and the arithmetic spelled out above."""
    diffs = _committed_diffs()
    assert len(diffs) > 50, "the overlap must be substantial to mean anything"
    mid = len(diffs) // 2
    longhand_bias = (diffs[mid] if len(diffs) % 2
                     else round((diffs[mid - 1] + diffs[mid]) / 2, 6))
    longhand_spread = round(diffs[-1] - diffs[0], 6)

    derived = Vitai(VERA).overlap_calibration(
        "sessions", "distance_km", "watch", "phone")["row"]
    authored = Vitai(VERA).dataset("comparability")[0]

    assert derived["bias"] == authored["bias"] == longhand_bias
    assert derived["spread"] == authored["spread"] == longhand_spread
    assert derived["status"] == authored["status"] == "offset"


def test_her_overlap_is_the_shape_the_feature_needs():
    """A near-zero median with a wide one-sided range. A record where the two
    instruments differed by a constant would be summarised by one number and
    would teach nothing about why two are owed."""
    out = Vitai(VERA).overlap_calibration(
        "sessions", "distance_km", "watch", "phone")
    seen = out["observed"]
    assert abs(seen["median"]) < 0.1, seen
    assert seen["range"] > 1.0, seen
    assert seen["asymmetric"] is True, seen
    assert abs(seen["high"]) > abs(seen["low"]) * 5, (
        "the long tail is the finding: the phone reads short under canopy and "
        "never reads long by anything like as much")


def test_nothing_in_her_record_is_corrected():
    """Measuring that two instruments disagree is not a licence to adjust
    either. Both claims stand exactly as each instrument reported them, and
    the canonical series picks one by the precedence ladder rather than
    blending them or applying the measured offset."""
    v = Vitai(VERA)
    raw = [r for r in v.dataset("sessions") if r["date"] == "2030-01-06"]
    assert len(raw) == 2, raw
    claimed = {r["origin"]: r["distance_km"] for r in raw}
    canonical = [r for r in v.canonical()["sessions"]
                 if r["date"] == "2030-01-06"]
    assert len(canonical) == 1
    assert canonical[0]["distance_km"] in claimed.values(), (
        "the canonical distance is one of the two claims, not an adjusted or "
        "averaged third number")


@pytest.mark.parametrize("field,dataset", [("distance_km", "sessions")])
def test_the_dataset_is_named_and_not_guessed(field: str, dataset: str):
    """A field name does not identify a dataset. `distance_km` is on `daily`
    AND on `sessions`, and searching for the first dataset carrying the name
    measured the wrong one and reported a refusal over an overlap that was
    there all along."""
    from vitai.schema import KEYS

    assert field in KEYS["daily"] and field in KEYS["sessions"]
    with pytest.raises(KeyError):
        Vitai(VERA).overlap_calibration("weight", field, "watch", "phone")


# --- the surface -------------------------------------------------------------

def test_the_cli_renders_the_measurement_and_names_the_asymmetry():
    """#398 shipped a `KeyError` in a CLI renderer while the whole suite was
    green, because every test drove the API and nothing drove the command.

    The asymmetry line is the part that matters here: the row cannot carry it,
    so the surface a person reads has to say it out loud or the limit is
    invisible to everyone except a reader of this module."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "calibrate", "--root", str(VERA),
         "--dataset", "sessions", "--field", "distance_km",
         "--origin-a", "watch", "--origin-b", "phone"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "phone vs watch" in out, out
    assert "NOT a plus-or-minus" in out, out
    assert "ASYMMETRIC" in out, out


def test_the_cli_refuses_without_a_dataset():
    """A field name does not identify a dataset, and the command says so
    rather than guessing."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "calibrate", "--root", str(VERA),
         "--field", "distance_km", "--origin-a", "watch", "--origin-b", "phone"],
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert "does not identify a dataset" in proc.stderr, proc.stderr
