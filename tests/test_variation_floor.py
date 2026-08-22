"""The floor the registry declares and the detector never read (#459).

`semantics/variation.toml` says of weight:

    min_spread_abs = 0.2
    window_days = 5
    # "A series that does not move by even this much across five days is
    #  flatter than hydration alone allows."

`resolution._runs_in` reads `window_days` and the note. It has never read
`min_spread_abs`. What it implements is EXACT EQUALITY - a run of identical
values - which is strictly stronger than the rule the registry states, so a
series that creeps by a gram a day walks past a detector whose own comment says
it should not.

That is why #459's four persona weight series were never caught. `vera` runs
59.18, 59.14, 59.14, 59.13: no two-day stretch is exactly constant, every
five-day stretch is four times flatter than the floor, and nothing anywhere
said so.

THE REGISTER AT THE BOTTOM IS THE POINT OF THE CHANGE, and it is pinned in
both directions on purpose. A corpus regenerated in the same commit as the gate
that judges it stays green and falsifies nothing, so the floor here is not one
this change chose: it was authored in a different change, for a different
purpose, against `clocks.DIURNAL_KG_PER_DAY`, and this change only makes the
code read it.
"""

from __future__ import annotations

from pathlib import Path

from vitai.api import Vitai
from vitai.resolution import restatement_runs
from vitai.verdicts import RATE_DECISION_BAND
from vitai.vocab import registry

PERSONAS = Path(__file__).parent / "fixtures" / "personas"
DEMO = "examples/demo"

FLOOR = registry("variation")["variation"]["weight"]["kg"]


def _creep(step: float, days: int = 7, start: float = 80.0):
    """A series that moves every day and never moves far."""
    return [{"date": f"2030-05-{d:02d}", "kg": round(start + d * step, 3)}
            for d in range(1, days + 1)]


# ------------------------------------------------------------------ the defect

def test_a_series_flatter_than_the_declared_floor_is_reported():
    """The defect, asserted rather than described.

    Seven days moving a gram at a time: total travel 0.06 kg against a
    declared floor of 0.2 kg across five days. The registry says this is
    flatter than hydration allows. The detector has never said anything about
    it, because no two readings are equal.
    """
    found = restatement_runs({"weight": _creep(0.01)})
    assert found, (
        "a week that moved 0.06 kg in total was not reported, and "
        f"`variation.toml` declares a floor of {FLOOR['min_spread_abs']} kg "
        f"across {FLOOR['window_days']} days. The registry states a spread "
        f"rule and the code implements exact equality")


def test_the_floor_is_actually_read(monkeypatch):
    """A declared key that changes nothing is a declared key nothing reads.

    Not a source-text check: the registry value is moved and the answer has to
    move with it. A detector that ignored `min_spread_abs` would return the
    same thing for both.
    """
    import vitai.resolution as resolution
    rows = _creep(0.05)          # 0.30 kg of travel across the week
    loose = restatement_runs({"weight": rows})

    real = registry("variation")

    def strict(name):
        if name != "variation":
            return real if name == "variation" else registry(name)
        return {"variation": {"weight": {"kg": {**FLOOR,
                                                "min_spread_abs": 5.0}}}}

    monkeypatch.setattr(resolution, "registry", strict, raising=False)
    monkeypatch.setattr("vitai.vocab.registry", strict)
    widened = restatement_runs({"weight": rows})
    assert len(widened) > len(loose), (
        "raising the declared floor found no more flat stretches, so the "
        "detector is not reading it")


def test_a_run_of_identical_readings_still_fires():
    """The behaviour that already existed, which a spread rule must subsume
    rather than replace: a spread of zero is below any floor."""
    rows = [{"date": f"2030-05-{d:02d}", "kg": 80.0} for d in range(1, 8)]
    found = restatement_runs({"weight": rows})
    assert len(found) == 1
    assert found[0]["kind"] == "constant_value_run"


def test_a_series_that_really_moves_is_still_left_alone():
    """The premise, and the thing a spread rule could most easily break. A
    detector that fired on ordinary weeks would be ignored within one."""
    assert restatement_runs({"weight": _creep(0.1)}) == []
    assert restatement_runs({"weight": _creep(-0.1)}) == []


def test_the_span_is_still_measured_in_days(monkeypatch):
    """Three readings in one morning are one observation restated twice, and
    a row-count rule would have called that a flat week. A spread rule makes
    that easier to get wrong, not harder."""
    rows = [{"date": "2030-05-01", "kg": 80.0 + i * 0.01} for i in range(6)]
    assert restatement_runs({"weight": rows}) == []


def test_an_unlisted_field_is_still_never_checked():
    """The registry stays open in the deny-list direction: an omission
    accuses nobody."""
    flat = [{"date": f"2030-05-{d:02d}", "sleep_h": 8.0} for d in range(1, 15)]
    assert restatement_runs({"daily": flat}) == []


# ----------------------------------------------------------------- the corpus

# WHAT THE ENGINE'S OWN RULE FINDS, pinned in both directions and split by
# which clause found it, because the two clauses are different evidence.
#
# `BELOW_THE_FLOOR` is the detection this change adds: a stretch that moved,
# and moved less across a whole declared window than hydration alone accounts
# for. Value is (runs, longest stretch in days).
#
# `EXACTLY_CONSTANT` is the older clause, tightened here. It used to fire on
# TWO identical readings five days apart, which over this corpus produced 49
# runs across five personas of which 46 rested on two or three readings -
# `tom` alone had 23 pairs, on a weight series carrying real noise and rounded
# to 0.1 kg, where two of 326 readings landing on one tick a week apart is
# arithmetic rather than evidence. At three readings it is 19 runs across
# three personas, and `bea`, `marcus` and `rachel` leave entirely.
#
# THE FLOOR IS NOT THIS CHANGE'S TO CHOOSE. `semantics/variation.toml` has
# declared 0.2 kg across 5 days since the detector was built, against
# `clocks.DIURNAL_KG_PER_DAY`'s 1.0 kg waking swing, for a purpose that had
# nothing to do with fixtures. This change only makes the code read it. A
# corpus judged by a rule written in the same commit stays green and
# falsifies nothing; this one is judged by a rule that was already there.
#
# PRESENCE IS NOT THE FINDING; RUN LENGTH IS - and `kenji` is what measured
# that (#462). He was built to carry published day-to-day variation and he
# joins this register anyway, with one run of six days.
#
# That is chance and it was checked rather than assumed. Rebuilding his series
# from the same process under 200 different seeds, 143 of them - 72 per cent -
# hold at least one stretch of five days or more under the declared floor; the
# median longest run is five days and the longest seen is nine. A realistic
# daily series of this length is MORE likely than not to trip a 0.2 kg floor
# over 5 days somewhere, so a record's absence from this register says less
# than its position in it.
#
# Which is what the two ends of the table already showed and nobody had put a
# number on: `vera` at 71 days and `hana` at 26 are series that cannot
# fluctuate, while `nora`'s two six-day stretches inside 1,096 daily readings
# are a real flat fortnight. `kenji` at six belongs with `nora`, and the fact
# that a fixture built specifically to fix flatness lands in a flatness
# register is the clearest evidence available that the register measures
# something narrower than its name suggests.
BELOW_THE_FLOOR = {"hana": (5, 26), "ines": (3, 18), "kenji": (1, 6),
                   "nora": (2, 6), "sofia": (1, 13), "stefan": (5, 22),
                   "tom": (2, 26), "vera": (2, 71)}
EXACTLY_CONSTANT = {"sofia": (1, 6), "stefan": (1, 8), "tom": (17, 23)}


def _runs(root) -> tuple[list, list]:
    found = restatement_runs({"weight": Vitai(root).canonical("weight")})
    return ([r for r in found if "moved only" in r["detail"]],
            [r for r in found if "held exactly" in r["detail"]])


def _longest(runs) -> int:
    return max((int(r["detail"].split("which is ")[1].split(" days")[0])
                for r in runs), default=0)


def _census() -> tuple[dict, dict]:
    below, exact = {}, {}
    for root in sorted(PERSONAS.iterdir()):
        if not root.is_dir() or root.name == "_gen":
            continue
        soft, hard = _runs(root)
        if soft:
            below[root.name] = (len(soft), _longest(soft))
        if hard:
            exact[root.name] = (len(hard), _longest(hard))
    return below, exact


def test_which_records_hold_a_stretch_flatter_than_the_declared_floor():
    """#459, measured by the engine's own rule rather than by a new one.

    `vera` holds a 71-day stretch that travelled 0.18 kg and a 64-day one
    that travelled 0.19: those are ramps, not weighed series. `hana` and
    `stefan` hold five each, `ines` three.

    AND THE PREMISE OF #459 DOES NOT FULLY SURVIVE. It named four personas.
    The engine's own floor names seven, and the three extra are not the same
    phenomenon - `nora` holds two six-day stretches inside 1,096 daily
    readings, which is what a real flat fortnight looks like, and `tom` holds
    long flat patches beside forty exactly-constant runs, which is a coarse
    logger rather than a smooth one. Length is what separates them and it is
    pinned here rather than editorialised into a verdict.
    """
    below, _ = _census()
    assert below == BELOW_THE_FLOOR, below


def test_a_pair_of_identical_readings_is_no_longer_called_a_run():
    """The other half of the same defect, in the other direction.

    The floor clause was too strong - exact equality where the registry said
    spread. The evidence clause was too weak: two readings five days apart.
    Over this corpus that produced 49 runs across five personas, 46 of them
    resting on two or three readings, because two of `tom`'s 326 noisy
    readings landing on the same 0.1 kg tick a week apart is arithmetic. A
    detector reporting that at scale teaches a reader to skip its output,
    which is how a check stops being one without ever being switched off.
    """
    _, exact = _census()
    assert exact == EXACTLY_CONSTANT, exact
    assert "bea" not in exact and "marcus" not in exact and "rachel" not in exact


def test_the_shipped_demo_holds_neither():
    """The control on both registers. A rule that flagged every record would
    satisfy them and mean nothing, and the demo is the one record whose weight
    series was generated WITH day-to-day noise - `rng.gauss(0, 0.25)` on top
    of the trend, which is what a scale and a body produce together."""
    soft, hard = _runs(DEMO)
    assert (soft, hard) == ([], [])


def test_the_two_routes_to_this_finding_do_not_name_the_same_set():
    """And they should not, which is the interesting part.

    #457 named four personas by a different statistic - the p10..p90 spread of
    their seven-day changes against the band `weight_rate` is judged in. All
    four are here, so the routes agree where they overlap. But this rule finds
    three more, and #457's finds none that this one misses: a series can be
    flat in stretches while jumping between them, which is `tom`, and a series
    with no noise at all is flat everywhere, which is `vera`.

    A subset relation rather than an equality is the honest statement of how
    two measurements of neighbouring phenomena relate.

    #457'S SET IS RECOMPUTED HERE rather than imported from its test module.
    Importing it would make the two agree because one copied the other, and
    the claim is that two measurements agree - so this runs the other
    measurement again. (The import also only resolved locally: `tests` is not
    a package, and CI said so.)
    """
    smooth = set()
    for root in sorted(PERSONAS.iterdir()):
        if not root.is_dir() or root.name == "_gen":
            continue
        week = [r for r in Vitai(root).weight_outlook(days=7)["horizons"]
                if r["days"] == 7]
        if week and (week[0]["change_p90"] - week[0]["change_p10"]
                     ) <= 2 * RATE_DECISION_BAND:
            smooth.add(root.name)
    assert smooth, "the other measurement found nothing, so this asserts nothing"
    assert smooth < set(BELOW_THE_FLOOR), (sorted(smooth),
                                           sorted(BELOW_THE_FLOOR))


def test_the_measurement_can_fail():
    """The control on the controls: a series built to be flat is found, and
    the same series built to move is not, through the same call."""
    assert restatement_runs({"weight": _creep(0.005, days=14)}) != []
    assert restatement_runs({"weight": _creep(0.30, days=14)}) == []
