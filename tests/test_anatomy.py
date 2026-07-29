"""The body-site registry: a closed vocabulary with post-coordinated sides.

Synthetic data only (public repo: no real measurements).
"""

import pytest

from vitai.anatomy import (
    SIDES, describe, is_paired, is_site, known_sites, label_of, osiics_of,
    region_of, regions, resolve, sites,
)
from vitai.resolution import canonical_daily
from vitai.schema import validate_record


def daily(date="2030-05-01", **kw):
    rec = {"date": date, "steps": None, "distance_km": None, "active_min": None,
           "kcal_out": None, "kcal_in": None, "protein_g": None, "sleep_h": None,
           "rhr": None, "alcohol": None, "note": None, "source": None,
           "mood": None, "feel": None, "coverage": None, "pain": None,
           "pain_site": None, "pain_side": None, "_gen": 2}
    rec.update(kw)
    return rec


# ---- the registry itself -----------------------------------------------------

def test_registry_loads_and_is_not_empty():
    assert len(known_sites()) >= 20
    assert set(regions()) >= {"head_neck", "trunk", "upper_limb", "lower_limb"}


def test_every_site_has_a_known_region_and_label():
    for slug, meta in sites().items():
        assert meta.get("region") in regions(), f"{slug} has an unknown region"
        assert meta.get("label"), f"{slug} has no label"
        assert isinstance(meta.get("paired"), bool), f"{slug} must declare paired"


def test_no_site_name_encodes_a_side():
    """Laterality is post-coordinated - the FHIR/openEHR call. A `left_knee`
    entry would double the vocabulary and re-open the ambiguity."""
    for slug in known_sites():
        assert not slug.startswith(("left_", "right_"))
        assert "left" not in slug and "right" not in slug


def test_aliases_are_unambiguous():
    """One spelling must not map to two sites, or resolution is a coin toss."""
    seen: dict[str, str] = {}
    for slug, meta in sites().items():
        for alias in meta.get("aliases", []):
            key = alias.lower()
            assert key not in seen, f"{alias!r} claimed by {seen.get(key)} and {slug}"
            seen[key] = slug


def test_osiics_codes_are_single_letters_where_present():
    for slug, meta in sites().items():
        if (code := meta.get("osiics")) is not None:
            assert isinstance(code, str) and len(code) == 1 and code.isupper(), slug


# ---- resolution --------------------------------------------------------------

@pytest.mark.parametrize("written,expected", [
    ("knee", "knee"),
    ("Knee", "knee"),
    ("KNEE", "knee"),
    ("lower back", "lower_back"),
    ("lower-back", "lower_back"),
    ("Lower back", "lower_back"),
    ("lumbar", "lower_back"),
    ("low back", "lower_back"),
    ("IT band", "knee"),
    ("itb", "knee"),
    ("quads", "thigh"),
    ("plantar fasciitis", "heel"),
    ("achilles tendon", "achilles"),
    ("glutes", "hip"),
])
def test_resolve_maps_what_an_athlete_would_actually_type(written, expected):
    assert resolve(written) == expected


def test_unknown_sites_do_not_resolve():
    assert resolve("soul") is None
    assert resolve("") is None
    assert resolve(None) is None
    assert is_site("patella") is True
    assert is_site("aura") is False


def test_region_rollup_answers_anything_in_the_lower_limb():
    lower = [s for s in known_sites() if region_of(s) == "lower_limb"]
    assert {"knee", "achilles", "hamstring", "calf"} <= set(lower)
    assert region_of("neck") == "head_neck"
    assert region_of("nonsense") is None


def test_paired_versus_midline():
    assert is_paired("knee") is True
    assert is_paired("shoulder") is True
    assert is_paired("lower_back") is False
    assert is_paired("chest") is False


def test_labels_and_codes():
    assert label_of("lower_back") == "Lower back"
    assert osiics_of("neck") == "N"
    # Blank means "not verified from a primary source", not "no such code".
    assert osiics_of("hamstring") is None


def test_describe_renders_for_an_athlete():
    assert describe("knee", "left") == "Left knee"
    assert describe("achilles", "bilateral") == "Both achilles"
    assert describe("lower_back") == "Lower back"
    assert describe("nonsense", "left") is None


# ---- validation --------------------------------------------------------------

def test_a_known_site_with_a_side_validates():
    assert validate_record("daily", daily(pain=4, pain_site="knee",
                                          pain_side="left")) == []


def test_an_alias_validates_too():
    assert validate_record("daily", daily(pain=3, pain_site="itb",
                                          pain_side="right")) == []


def test_an_unknown_site_is_rejected_with_the_vocabulary():
    problems = validate_record("daily", daily(pain=4, pain_site="soul",
                                              pain_side="left"))
    assert any("unknown 'pain_site'" in p for p in problems)
    assert any("knee" in p for p in problems), "the error should list the options"


def test_a_paired_site_needs_a_side():
    problems = validate_record("daily", daily(pain=4, pain_site="knee"))
    assert any("both sides" in p for p in problems)


def test_a_midline_site_refuses_a_side():
    problems = validate_record("daily", daily(pain=4, pain_site="lower_back",
                                              pain_side="left"))
    assert any("midline" in p for p in problems)


def test_a_midline_site_without_a_side_is_fine():
    assert validate_record("daily", daily(pain=4, pain_site="lower_back")) == []


def test_side_must_come_from_the_closed_set():
    problems = validate_record("daily", daily(pain=4, pain_site="knee",
                                              pain_side="port"))
    assert any("pain_side" in p for p in problems)
    assert SIDES == {"left", "right", "bilateral"}


def test_a_side_without_a_site_says_nothing():
    problems = validate_record("daily", daily(pain_side="left"))
    assert any("says nothing" in p for p in problems)


def test_no_pain_needs_neither_site_nor_side():
    assert validate_record("daily", daily(pain=0)) == []
    assert validate_record("daily", daily()) == []


# ---- the legacy path ---------------------------------------------------------

def test_legacy_hip_pain_still_maps_and_invents_no_side():
    legacy = {"date": "2030-05-01", "steps": None, "distance_km": None,
              "active_min": None, "kcal_out": None, "kcal_in": None,
              "protein_g": None, "sleep_h": None, "rhr": None, "hip_pain": 3,
              "alcohol": None, "note": None}
    mapped = canonical_daily(legacy)
    assert mapped["pain"] == 3
    assert mapped["pain_site"] == "hip"
    assert mapped.get("pain_side") is None, (
        "the old field never recorded which hip; guessing would invent a fact")


def test_canonical_daily_normalises_an_alias_to_its_slug():
    mapped = canonical_daily(daily(pain=2, pain_site="IT band", pain_side="left"))
    assert mapped["pain_site"] == "knee"


def test_canonical_daily_leaves_an_already_canonical_row_alone():
    row = daily(pain=2, pain_site="knee", pain_side="left")
    assert canonical_daily(row) is row
