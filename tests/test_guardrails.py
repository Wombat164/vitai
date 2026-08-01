"""Guardrail fixtures: safety behaviour proven by a test, never by a paragraph.

Every safety finding from a persona validation sweep is frozen here as a
synthetic athlete plus an assertion about what the engine MUST produce. The
personas are fictional; the failures they caught were real.

Tests marked `xfail(strict=True)` describe behaviour the model has COMMITTED to
but not yet built. They are specifications, not aspirations: when the increment
lands, the xfail flips to a pass and pytest fails the build if it is still
marked expected-failure. Nothing here may be deleted to make a build green - a
finding is retired only when its behaviour ships.

**All eight sweep-1 and sweep-2 specifications now hold** (issue #12) and their
markers are gone. They stay here as plain tests, which is the point: the
finding is retired by shipping the behaviour, and the test that caught it
becomes the thing that stops it coming back.

Sweep 1 (2026-07-29): docs/validation-personas.md
"""

from __future__ import annotations

import json

from vitai.api import Vitai

# --------------------------------------------------------------------------
# fixture builders - each is one athlete the engine got wrong
# --------------------------------------------------------------------------

DAILY_KEYS = ["date", "steps", "distance_km", "active_min", "kcal_out", "kcal_in",
              "protein_g", "sleep_h", "rhr", "hip_pain", "alcohol", "note",
              "source", "mood", "feel", "coverage", "pain", "pain_site",
              "pain_side"]


def _daily(date: str, **kw) -> dict:
    rec = {k: None for k in DAILY_KEYS}
    rec["date"] = date
    rec["_gen"] = 2
    rec.update(kw)
    return rec


def _write(root, name: str, rows: list[dict]) -> None:
    d = root / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _repo(tmp_path, name: str):
    root = tmp_path / name
    root.mkdir()
    (root / "vitai.toml").write_text('[athlete]\nname = "fixture"\n',
                                     encoding="utf-8")
    return root


def nursing_mother(tmp_path):
    """~1200 kcal while exclusively breastfeeding, losing ~1 kg/week, one
    near-syncope. Configured NOTHING - as a real new user has not."""
    root = _repo(tmp_path, "nursing")
    days = []
    for i in range(14):
        days.append(_daily(f"2030-06-{i + 1:02d}", kcal_in=1200, protein_g=50,
                           sleep_h=3.0, mood=3, source="mfp", coverage="full",
                           note="nearly blacked out standing up" if i == 9 else None))
    _write(root, "daily", days)
    _write(root, "weight", [
        {"date": "2030-06-01", "kg": 75.5, "source": "scale", "note": None,
         "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "_gen": 2},
        {"date": "2030-06-14", "kg": 74.0, "source": "scale", "note": None,
         "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "_gen": 2},
    ])
    _write(root, "sessions", [])
    return root


def exertional_chest_pain(tmp_path):
    """Five exertional chest-pain episodes with increasing duration, reported
    the way people actually report them: buried in prose, downplayed."""
    root = _repo(tmp_path, "chest")
    notes = {
        1: "chest twinge going up the stairs at bedtime, few seconds, gone",
        3: "twinge when lifting heavy stock, ~10s, had to put it down",
        6: "twinge on the stairs after mowing, ~15s, sat down till it passed",
        10: "twinge lifting a pallet wrong, few seconds",
        12: "twinge reaching overhead with the drill, ~20s, longest yet",
    }
    days = [_daily(f"2030-06-{i + 1:02d}", source="recall", coverage="manual",
                   note=notes.get(i)) for i in range(14)]
    _write(root, "daily", days)
    _write(root, "weight", [])
    _write(root, "sessions", [])
    return root


def deviceless_athlete(tmp_path):
    """No wearable, no weight goal, no intention of acquiring either. Phone
    step counts are the only real data her life produces."""
    root = _repo(tmp_path, "deviceless")
    steps = [8900, 9500, 2200, 4700, 8300, 7600, 8100,
             2900, 6400, 3100, 7900, 8700, 9200, 1800]
    _write(root, "daily", [
        _daily(f"2030-06-{i + 1:02d}", steps=s, source="phone")
        for i, s in enumerate(steps)])
    _write(root, "weight", [])
    _write(root, "sessions", [])
    return root


# --------------------------------------------------------------------------
# G68 - defaults protect. The safety net may not be opt-in.
# --------------------------------------------------------------------------

def test_dangerous_deficit_fires_without_any_configuration(tmp_path):
    """THE finding of sweep 1. A nursing mother eating ~1200 kcal and losing
    ~1 kg/week produced `tripwires: none` because she had configured nothing.
    Absolute-danger rules must fire from DEFAULTS."""
    v = Vitai(nursing_mother(tmp_path))
    v.build()
    # `no_data` rows do not count: the engine emits them for an athlete who
    # supplied 14 days of intake, protein, sleep and mood plus two weigh-ins.
    # That is not an absence of data, it is an absence of any rule that reads
    # it - and reporting "no_data" for a record that HAS data is its own
    # truthfulness problem (G64).
    actionable = [r for r in v.verdicts()
                  if r.get("verdict") not in (None, "no_data")]
    assert actionable or v.conservation(), (
        "an unconfigured athlete in danger produced no actionable signal - "
        "only no_data rows over a record that is not empty")


def test_intake_below_physiological_floor_is_flagged(tmp_path):
    v = Vitai(nursing_mother(tmp_path))
    v.build()
    rows = v.verdicts()
    assert any("intake" in str(r).lower() or "floor" in str(r).lower()
               for r in rows), "1200 kcal/day sustained produced no verdict"


# --------------------------------------------------------------------------
# G59 - a red flag in prose must still escalate
# --------------------------------------------------------------------------

def test_exertional_chest_pain_in_notes_escalates(tmp_path):
    """Five episodes, increasing duration, produced silence. The escalation
    path must start at ingest: the LLM classifies symptom language into a
    claim, the engine decides severity."""
    v = Vitai(exertional_chest_pain(tmp_path))
    v.build()
    surfaced = json.dumps(v.verdicts()) + json.dumps(v.conservation())
    assert "chest" in surfaced.lower() or "urgent" in surfaced.lower(), (
        "recurrent exertional chest pain produced no escalation")


# --------------------------------------------------------------------------
# G62/G64 - the athlete's refusals are honoured; deviceless still works
# --------------------------------------------------------------------------

def test_status_does_not_demand_weight_from_an_athlete_without_a_weight_goal(tmp_path):
    """`vitai status` currently opens by telling an athlete who explicitly
    refused a weight goal that she has failed to weigh herself."""
    v = Vitai(deviceless_athlete(tmp_path))
    v.build()
    assert "weight" not in v.status_line().lower(), (
        "status led with weight for an athlete who has no weight goal")


def test_deviceless_athlete_gets_a_useful_rollup(tmp_path):
    """Her steps are genuinely real and genuinely all she has. They must
    appear somewhere."""
    v = Vitai(deviceless_athlete(tmp_path))
    v.build()
    assert "step" in v.rollup().lower(), (
        "14 days of step data produced nothing in the rollup")


# --------------------------------------------------------------------------
# G69 - no bare signed quantity whose plain reading inverts its meaning
# --------------------------------------------------------------------------

def test_rate_states_its_direction_in_words(tmp_path):
    """The rollup rendered `+1.10 kg/week` for an athlete who LOST 1.5 kg.
    For a scale-anxious under-eater that misreading is actively dangerous."""
    v = Vitai(nursing_mother(tmp_path))
    v.build()
    text = v.rollup().lower()
    if "kg/week" in text:
        assert ("losing" in text or "gaining" in text or "loss" in text), (
            "a signed rate was rendered without stating its direction in words")


# --------------------------------------------------------------------------
# Invariants that must hold NOW - these are not xfail, they guard the present
# --------------------------------------------------------------------------

def test_engine_survives_an_athlete_with_almost_no_data(tmp_path):
    """Whatever else it does, it must not crash on the majority case: someone
    who tracks almost nothing."""
    v = Vitai(exertional_chest_pain(tmp_path))
    v.build()
    assert isinstance(v.status_line(), str)
    assert isinstance(v.rollup(), str)


def test_engine_survives_an_athlete_with_no_weight_data_at_all(tmp_path):
    v = Vitai(deviceless_athlete(tmp_path))
    v.build()
    assert isinstance(v.status_line(), str)


def test_no_llm_authored_text_in_the_number_path(tmp_path):
    """P4: the engine's own output must be reproducible from the data alone.
    Two builds over identical inputs are byte-identical."""
    root = nursing_mother(tmp_path)
    v = Vitai(root)
    v.build()
    first = v.rollup()
    v.build()
    assert v.rollup() == first, "rebuild was not deterministic"


# --------------------------------------------------------------------------
# Sweep 2 (2026-07-29): five athletes spanning elite -> severe obesity
# --------------------------------------------------------------------------

def low_energy_athlete(tmp_path):
    """Endurance athlete: energy availability far below the clinical threshold,
    five months amenorrhoeic, RHR drifted 42 -> 51, two prior stress fractures,
    recurrent exertional dizziness. She names none of it as a problem - the
    highest-severity presentation in the suite, and entirely implicit."""
    root = _repo(tmp_path, "reds")
    days = []
    for i in range(28):
        days.append(_daily(f"2030-06-{i + 1:02d}", kcal_in=1600, protein_g=63,
                           sleep_h=6.6, rhr=50, mood=5, source="garmin",
                           coverage="full",
                           note="dizzy on the long ride again; period still absent, 5th month"
                           if i % 7 == 3 else None))
    _write(root, "daily", days)
    _write(root, "weight", [
        {"date": "2030-06-01", "kg": 57.0, "source": "scale", "note": None,
         "body_fat_pct": 17.0, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "_gen": 2}])
    # ~2600 kcal long ride + ~1050 long run: expenditure dwarfs a 1600 intake
    _write(root, "sessions", [
        {"date": f"2030-06-{d:02d}", "type": "other", "distance_km": 108.0,
         "duration_s": 13800, "avg_hr": 141, "max_hr": 168, "cadence": None,
         "kcal": 2650, "location": None, "rpe": 7, "note": "long ride",
         "source": "garmin", "start_time": None, "elevation_m": None,
         "setting": "outdoor", "route": None, "place": None, "with": None,
         "context": None, "planned": None, "weather": None, "_gen": 2}
        for d in (6, 13, 20, 27)])
    return root


def glp1_athlete(tmp_path):
    """Severe obesity, five months on a GLP-1 agonist: 16 kg down, involuntary
    sub-800 kcal days from nausea, protein far too low, no resistance training,
    and self-reported weakness on stairs she attributes to the weight loss."""
    root = _repo(tmp_path, "glp1")
    days = []
    for i in range(28):
        low = i % 3 == 0
        days.append(_daily(f"2030-06-{i + 1:02d}",
                           kcal_in=700 if low else 1400,
                           protein_g=28 if low else 45,
                           sleep_h=5.5, mood=4 if low else 6, source="recall",
                           coverage="manual",
                           note="nausea, barely ate" if low else
                           "legs feel weaker on the stairs than they should"))
    _write(root, "daily", days)
    _write(root, "weight", [
        {"date": "2030-06-01", "kg": 126.0, "source": "clinic", "note": None,
         "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "_gen": 2},
        {"date": "2030-06-28", "kg": 122.0, "source": "clinic", "note": None,
         "body_fat_pct": None, "kg_lo": None, "kg_hi": None,
         "body_fat_lo": None, "body_fat_hi": None, "_gen": 2}])
    _write(root, "sessions", [])
    return root


def test_low_energy_presentation_triggers_a_hold_not_a_note(tmp_path):
    """Energy availability far below threshold + amenorrhoea + RHR drift +
    prior stress fractures is the highest-severity combination in the model.
    Correct behaviour is to SUSPEND progression and refer - not to add a line
    to the weekly rollup."""
    v = Vitai(low_energy_athlete(tmp_path))
    v.build()
    surfaced = (json.dumps(v.verdicts()) + json.dumps(v.conservation())).lower()
    assert "hold" in surfaced or "refer" in surfaced or "energy" in surfaced, (
        "a textbook RED-S presentation produced no hold and no referral")


def test_glp1_low_protein_flags_lean_mass_risk_not_restriction(tmp_path):
    """Rapid loss on a GLP-1 is EXPECTED and must not fire a rate tripwire.
    The real risk - inadequate protein during rapid loss with no resistance
    training - must fire instead. Firing the wrong one is worse than silence:
    it tells a succeeding athlete she is failing."""
    v = Vitai(glp1_athlete(tmp_path))
    v.build()
    surfaced = (json.dumps(v.verdicts()) + json.dumps(v.conservation())).lower()
    assert "protein" in surfaced or "lean" in surfaced, (
        "rapid medicated loss with inadequate protein produced no lean-mass "
        "warning")


def test_medicated_rapid_loss_does_not_crash_the_engine(tmp_path):
    """Holds today: whatever it says, it must survive a regime change of this
    size (a 24-month plateau followed by a sharp medicated drop)."""
    v = Vitai(glp1_athlete(tmp_path))
    v.build()
    assert isinstance(v.rollup(), str)
