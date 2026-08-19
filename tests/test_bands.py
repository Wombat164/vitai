"""What a shipped interval claims, stated instead of assumed (#402).

#402 says estimates should carry error bands and the bands must be earned, from
a measured overlap, a source that publishes its own uncertainty, or an interval
the athlete stated - "and from nowhere else".

MEASURED FIRST. This engine already ships intervals, and they mean at least
three different things under one naming convention:

    weight.kg_lo/kg_hi              limits an instrument stated
    meals.grams_lo/grams_hi         a range whoever estimated the portion gave
    comparability.difference_lo/hi  the extremes actually observed, which
                                    `db.py` says in as many words are NOT a band
    goals.target_hi                 the far end of an intention, not a value

Nothing in the engine states which is which. There is no `u_given_as`, no
coverage factor, no `ci95` anywhere in `src/`. A consumer meeting `kg_lo` and
`grams_lo` sees one shape and has to guess, and #465 is what guessing costs: a
standard uncertainty read as a 95 per cent half-width understated a finding by a
factor of two, in this repository's own shipped source.

SO WHAT SHIPS IS THE DECLARATION AND NOT A SINGLE NEW BAND. Every `_lo`/`_hi`
field says what it claims and where the width came from, in a closed vocabulary
whose members each name the coverage OUT LOUD - which is #457's `p10`/`p90`
lesson generalised. Fields with no declared width have none, and that absence is
#402's third state rather than a gap to be filled with a default.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from vitai import bands
from vitai.api import Vitai, schema
from vitai.schema import KEYS

DEMO = "examples/demo"

# Every `_lo`/`_hi`-shaped field this engine ships, measured off `schema.KEYS`
# rather than listed, so a new one cannot arrive undeclared.
SHAPED = {"weight.kg", "weight.body_fat", "meals.grams",
          "comparability.difference", "goals.target"}


def _shaped() -> set[str]:
    found = set()
    for dataset, fields in KEYS.items():
        for field in fields:
            for suffix in ("_lo", "_hi"):
                if field.endswith(suffix):
                    found.add(f"{dataset}.{field[:-len(suffix)]}")
    return found


# ------------------------------------------------------------------ the defect

def test_nothing_says_what_a_shipped_interval_claims():
    """The gap, asserted rather than described. Four differently-meaning
    intervals wear one convention and the engine publishes no statement of
    which is which."""
    assert hasattr(bands, "declaration"), (
        "no engine surface says whether `kg_lo` is a coverage interval, a "
        "stated range or an observed one, so a consumer has to guess - and "
        "#465 measured what guessing about an interval costs")


def test_every_interval_shaped_field_is_declared():
    """FAIL CLOSED, in the direction that matters: an undeclared pair is one a
    consumer will read under whatever convention it already believes."""
    assert _shaped() == SHAPED, _shaped()
    declared = set(bands.declaration())
    assert declared == SHAPED, sorted(declared ^ SHAPED)


# ------------------------------------------------------- the vocabulary

def test_a_coverage_word_says_what_it_covers():
    """#457's `p10`/`p90` lesson generalised, and #465's cost. `lo`/`hi` on
    their own name no coverage at all, so the word beside them has to."""
    for name, says in bands.COVERS.items():
        assert says, name
        assert name.replace("-", "").isalnum(), name
    # None of them is a bare "band" or "interval", which would restate the
    # shape and claim nothing.
    assert not {"band", "interval", "range"} & set(bands.COVERS)


def test_every_declared_word_is_used_and_every_used_word_is_declared():
    """Both directions, the doctrine the change kinds and the conditions
    already follow: an unused member of a closed vocabulary is vacuity."""
    used_covers = {e["covers"] for e in bands.declaration().values()
                   if e.get("covers")}
    used_basis = {e["basis"] for e in bands.declaration().values()
                  if e.get("basis")}
    assert used_covers == set(bands.COVERS), (used_covers, set(bands.COVERS))
    assert used_basis == set(bands.BASES), (used_basis, set(bands.BASES))


def test_a_band_names_both_where_the_width_came_from_and_what_it_covers():
    """Two orthogonal facts, and #402 turns on the first while #465 turns on
    the second. A row carrying one and not the other is half a claim."""
    for name, entry in bands.declaration().items():
        if entry["kind"] != "band":
            continue
        assert entry["basis"] in bands.BASES, name
        assert entry["covers"] in bands.COVERS, name


def test_something_that_is_not_a_band_has_to_say_so_and_why():
    """`db.py` says of `comparability.difference_lo`/`_hi`: they assert "no
    distribution and no coverage factor", and "THEY DO NOT EARN A BAND". A
    registry that let it pass as one would contradict the schema that ships
    it."""
    entry = bands.declaration()["comparability.difference"]
    assert entry["kind"] == "not-a-band"
    assert entry["basis"] is None and entry["covers"] is None
    assert entry["says"]
    assert bands.declaration()["goals.target"]["kind"] == "not-a-band"


def test_the_three_intervals_do_not_all_claim_the_same_thing():
    """The premise. If they did, the convention would be fine and this whole
    change would be decoration."""
    claims = {name: e["covers"] for name, e in bands.declaration().items()
              if e["kind"] == "band"}
    assert len(set(claims.values())) > 1, claims


# --------------------------------------------------------- the third state

def test_a_field_with_no_declared_width_has_none():
    """#402's third state - estimated, width unknown - and it needs no
    register. `daily.kcal_out` is the motivating case: a vendor model's output
    with no published uncertainty, no overlap and nothing the athlete said.
    The answer is None, which is not a gap to be filled with a default."""
    assert bands.band_for("daily", "kcal_out") is None
    assert bands.band_for("sessions", "kcal") is None
    assert bands.band_for("daily", "steps") is None


def test_a_default_width_is_not_reachable_through_this_surface():
    """"A default plus or minus 20 per cent is not humility, it is fabricated
    precision about imprecision." There is no code path that returns a width
    for a field nobody measured one for."""
    for dataset, fields in KEYS.items():
        for field in fields:
            entry = bands.band_for(dataset, field)
            assert entry is None or entry["kind"] == "band", (dataset, field)
            if entry:
                assert f"{dataset}.{field}" in bands.declaration()


# --------------------------------------------------- what a record can show

def test_the_fields_that_carry_bands_are_the_ones_that_need_them_least():
    """#402's central complaint, measured on the shipped demo rather than
    asserted: the interval-bearing field is a scale reading, and it is present
    on 2 of 66 of them."""
    v = Vitai(DEMO)
    weighed = [r for r in v.canonical("weight") if r.get("kg") is not None]
    banded = [r for r in weighed if r.get("kg_lo") is not None]
    assert len(weighed) > 50 and len(banded) <= 5, (len(weighed), len(banded))
    # And the field the issue is actually about carries none at all.
    assert bands.band_for("daily", "kcal_out") is None


# ---------------------------------------------------------------- published

def test_a_client_reads_it_from_the_payload():
    """Where `fields`, `units` and `ambiguous_aliases` are, and for #257's
    reason: a separate accessor is a new place for parity to fail."""
    assert schema()["bands"] == bands.declaration()


def test_the_cli_and_the_api_answer_the_same_thing():
    out = subprocess.run([sys.executable, "-m", "vitai.cli", "bands", "--json"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == bands.declaration()


# ----------------------------------------------------------------- controls

def test_an_undeclared_pair_is_refused(monkeypatch):
    """THE CONTROL. The gate above passes today because the registry happens
    to be complete; it has to fail when it is not, or it is a list nobody
    checks."""
    monkeypatch.setitem(KEYS, "weight", list(KEYS["weight"]) + ["fake_lo",
                                                               "fake_hi"])
    assert "weight.fake" in _shaped()
    assert "weight.fake" not in bands.declaration()


def test_the_words_resolve_to_something_rather_than_being_free_text():
    """A vocabulary whose members are prose is prose with a colon in front."""
    assert bands.unresolved("covers", "no-such-coverage")
    assert bands.unresolved("basis", "no-such-basis")
    assert bands.unresolved("covers", next(iter(bands.COVERS))) is None
    with pytest.raises(KeyError):
        bands.unresolved("no-such-axis", "anything")
