"""The coarse tier of a measurement's time, as a vocabulary (#212).

A measurement event needs a temporal identifier, and the no-invention rule
makes it two tiers: a coarse one any source can state, and a precise one where
a device supplies it. The precise tier is built and well populated -
`weight.measured_at` on 2066 rows, `sessions.start_time` on 2767. The coarse
tier had nowhere to live, so "morning weigh-in" went into a note as prose.

ADOPTED, NOT INVENTED (G85). Open mHealth's `part-of-day` is a four-value enum,
one of the few schemas in that library still on 1.0 and not deprecated. Four is
fewer than an invented vocabulary would have - no "midday", no "early morning" -
and that is information: the coarse tier exists so any source can state it, and
a vocabulary a source cannot map onto confidently defeats the purpose.

WHAT THIS IS NOT. It does not store a phase on a measurement row, and it does
not derive one from a timestamp. Both wait on the anchor - which clock times a
given athlete's phases correspond to - and the anchor's input is measured to be
absent from every record this repo ships. That finding is on the issue with a
recommendation; what is here is the vocabulary and the one consumer that
already had it, hardcoded.
"""

from __future__ import annotations

from vitai.schema import KEYS, day_phases, validate_record
from vitai.vocab import registry


def plan(**kw) -> dict:
    return {**{k: None for k in KEYS["plans"]}, "date": "2030-05-01",
            "slug": "easy-run", "tier": "committed",
            "for_date": "2030-05-02", **kw}


# --- the vocabulary -------------------------------------------------------------

def test_it_is_open_mhealths_four_values():
    assert list(day_phases()) == ["morning", "afternoon", "evening", "night"]


def test_each_value_carries_the_standards_own_string():
    """`term` verbatim, the way `statistics.toml` carries IEEE 1752.1's - a
    mapping stated in a field can be checked, one implied by a slug cannot."""
    for slug, entry in day_phases().items():
        assert entry["term"] == slug, (slug, entry)
        assert entry["label"], slug


def test_it_asserts_no_snomed_code_it_has_not_checked():
    """Open mHealth binds each value to a SNOMED concept. This file does not
    reproduce concept IDs, because a code written from memory is a code nobody
    checked - and #263's point is that claiming conformance without a check is
    conformance by assertion."""
    raw = (registry("day_phase"))
    assert "snomed" not in str(raw).lower(), raw


def test_it_implies_no_clock_range():
    """"Whose morning" is the anchor question and the decision is explicit
    that it is derived from the athlete's own data. A night worker's morning
    is not 06:00 because a table said so, so no table here says so."""
    for entry in day_phases().values():
        assert not any(k in entry for k in ("from", "to", "start", "end",
                                            "hour", "hours")), entry


# --- the consumer that already had it, inline -----------------------------------

def test_the_plan_sort_reads_the_registry():
    """It was three values hardcoded in `api.py` as a sort key: no registry
    entry, no validation, and `night` unaddable without finding that line."""
    import inspect

    from vitai import api

    src = inspect.getsource(api.Vitai.plans)
    assert "day_phases()" in src
    assert '"morning": 0' not in src


def test_a_night_plan_now_sorts_where_it_belongs(tmp_path):
    """The defect the inline dict caused: a plan for a night shift fell to the
    same bucket as a plan with no phase at all, because the dict had three
    keys and `.get(..., 9)` caught everything else."""
    import json

    from vitai.api import Vitai

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    # SLUGS CHOSEN SO THE TIEBREAK DISAGREES with the defect. Under the old
    # inline dict `night` fell to the same bucket as no phase at all - both
    # `.get(..., 9)` - and the slug broke the tie. With `a-` before `z-`, the
    # buggy order puts the unphased plan first and the correct order does not,
    # so this cannot pass by luck the way the first version did.
    rows = [plan(slug="a-unphased", for_date="2030-05-02"),
            plan(slug="z-at-night", for_date="2030-05-02", for_phase="night"),
            plan(slug="b-at-dawn", for_date="2030-05-02", for_phase="morning")]
    (root / "data" / "plans.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    got = [r["slug"] for r in Vitai(root).plans()]
    assert got.index("b-at-dawn") < got.index("z-at-night") < got.index(
        "a-unphased"), got


# --- and the field is validated now ---------------------------------------------

def test_an_unknown_phase_is_refused():
    problems = validate_record("plans", plan(for_phase="midday"))
    assert any("for_phase" in p for p in problems), problems
    assert any("day_phase.toml" in p for p in problems), "it says where to look"


def test_every_registry_value_validates():
    for slug in day_phases():
        assert validate_record("plans", plan(for_phase=slug)) == [], slug


def test_no_phase_is_still_legal():
    """A plan without one is the common case and always was."""
    assert validate_record("plans", plan()) == []
