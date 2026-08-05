"""Every aggregate says what KIND of number it is (#261 layer 1, #208).

`verdicts.value` carried a maximum, a week-over-week change and six averages
in one column, and nothing said which was which. The sharpest case is `steps`:
a weekly row reading 9752 is the DAILY AVERAGE, and a consumer reading it as
the week's total sees a week in which the athlete walked five thousand steps a
day fewer than they did. Every figure in that sentence is the record's; the
noun was the lie.

IEEE 1752.1 has this vocabulary already - `descriptive-statistic` - so the
terms are adopted rather than invented, and the one thing it does not cover, a
comparison between two windows, sits under a `vitai` namespace instead of
being bent into `average` to claim a standard term.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from vitai.api import Vitai, init
from vitai.db import CONTRACT_VERSION, VERDICT_KEYS
from vitai.schema import CURRENT_GENERATION, KEYS, statistics
from vitai.verdicts import _row

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
PUBLISHED = Path(__file__).resolve().parent / "fixtures" \
    / "ieee_1752_descriptive_statistic.json"


def _published() -> dict:
    """The standard's own enum, as published, vendored beside this test.

    Vendored rather than fetched: the build is network-free, and a test that
    reached the network would fail in a tunnel and pass against whatever the
    standard says next week. The fixture records its source URL and the date
    it was taken, so re-checking it is one curl.
    """
    return json.loads(PUBLISHED.read_text(encoding="utf-8"))


def test_every_judged_row_declares_its_statistic():
    """The register. A metric that ships unlabelled is one a consumer guesses
    at, and guessing is what this whole change is about."""
    rows = Vitai(DEMO).verdicts()
    assert rows

    unlabelled = sorted({r["metric"] for r in rows
                         if r["value"] is not None and not r["statistic"]})
    assert unlabelled == [], f"these report a number and no kind: {unlabelled}"


def test_the_statistic_is_the_one_the_code_actually_computes():
    """Not "a plausible label" - the one the arithmetic produces.

    `pain_gate` takes the WORST day, because a gate is about the worst day.
    Labelling it `average` would have been the easy mistake and would have
    let a consumer render a week containing one bad day as a calm one.
    """
    # EVERY valued row per metric, not a dict. A dict comprehension is
    # last-write-wins, so it checked only whichever branch the demo's final
    # row happened to come from - and relabelling the JUDGED `weight_rate`
    # branch passed all 1510 tests, because the demo's last such rows are
    # `not_supported` refusals from a different call site.
    labels: dict[str, set] = {}
    for r in Vitai(DEMO).verdicts():
        if r["value"] is not None:
            labels.setdefault(r["metric"], set()).add(r["statistic"])

    assert labels["pain_gate"] == {"maximum"}
    assert labels["steps"] == {"average"}
    assert labels["sleep"] == {"average"}
    assert labels["rhr"] == {"average"}
    assert labels["easy_hr"] == {"average"}
    assert labels["intake_floor"] == {"average"}
    assert labels["protein_floor"] == {"average"}
    # The two that must NOT claim a standard term, across every branch that
    # emits them.
    assert labels["weight_rate"] == {"period-over-period-change"}


def test_a_between_window_comparison_does_not_claim_a_standard_term():
    """`weight_rate` is this week's mean minus last week's.

    That is not a descriptive statistic of a set and 1752.1 has no term for
    it, so it carries a `vitai`-namespaced one. Calling it `average` would
    have been the flattering choice - every row claiming a standard term -
    and it would have been false.
    """
    known = statistics()
    ours = {k for k, v in known.items() if v["namespace"] == "vitai"}

    assert ours == {"period-over-period-change", "composite-of-summaries"}
    # And the negative claim is CHECKED, not asserted: neither appears in the
    # published enum, which ships as a fixture beside this test.
    published = set(_published()["enum"])
    for slug in ours:
        assert known[slug].get("term") is None, slug
        assert slug not in published and known[slug]["label"] not in published


def test_a_new_metric_cannot_ship_unlabelled():
    """Held where the rows are BUILT, not at each caller, for the same reason
    `reason` is: a new call site must not be able to omit it."""
    with pytest.raises(ValueError) as raised:
        _row("2030-05-06", "invented", 42.0, 10.0, "behind")

    assert "KIND" in str(raised.value)


def test_a_statistic_must_be_one_the_registry_knows():
    """A label nothing defines is worse than none: it reads as though the
    question was settled."""
    with pytest.raises(ValueError):
        _row("2030-05-06", "invented", 42.0, 10.0, "behind",
             statistic="weekly-ish")


def test_a_refusal_carries_no_statistic():
    """There is no number for it to describe, and a label beside a null value
    describes nothing."""
    with pytest.raises(ValueError):
        _row("2030-05-06", "steps", None, None, "no_data",
             reason="no_input", statistic="average")


def test_a_suppressed_row_keeps_the_label_of_the_number_it_keeps(tmp_path):
    """Suppression is a label and never a deletion: the value survives, so
    what kind of number it is has to survive with it.

    ON A RECORD THAT ACTUALLY SUPPRESSES SOMETHING. The first version of this
    test read the demo, which suppresses nothing, so dropping the label in the
    rewrite passed every test in the file - the fixture-never-reaches-the-path
    failure, in the test written to catch a dropped label.
    """
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    toml = root / "vitai.toml"
    toml.write_text(toml.read_text(encoding="utf-8")
                    + '\n[preferences]\n'
                      'suppressed_metrics = ["steps", "weight_rate"]\n',
                    encoding="utf-8")

    rows = [r for r in Vitai(root).verdicts()
            if r["metric"] in ("steps", "weight_rate")]

    assert rows, "the fixture must produce these rows or it proves nothing"
    assert all(r["reason"] == "suppressed" for r in rows)
    judged = [r for r in rows if r["value"] is not None]
    assert judged, "suppression is a label, not a deletion - the value stays"
    # BOTH, and they differ. Suppressing only `steps` could not tell a
    # pass-through from a hardcoded `average`, because average is what
    # `steps` is - so that version passed with the label hardcoded.
    labels = {r["metric"]: r["statistic"] for r in judged}
    assert labels["steps"] == "average"
    assert labels["weight_rate"] == "period-over-period-change"


def test_the_column_reaches_the_read_model(tmp_path):
    """A field written nowhere is the specified-and-never-written defect, and
    this one is only useful to a consumer that can SELECT it."""
    # The demo, copied, because a fresh `init` has no thresholds in its
    # `vitai.toml` and an absent threshold DISABLES its verdict - so the
    # fixture would have produced no judged rows and passed on an empty set.
    root = tmp_path / "content"
    shutil.copytree(DEMO, root)
    Vitai(root).build()

    con = sqlite3.connect(root / "derived" / "health.db")
    rows = con.execute(
        "SELECT metric, value, statistic FROM verdicts "
        "WHERE value IS NOT NULL").fetchall()
    contract, = con.execute(
        "SELECT value FROM meta WHERE key='contract'").fetchone()
    con.close()

    assert rows, "the fixture must produce judged rows or this proves nothing"
    assert all(r[2] for r in rows), f"unlabelled in the read model: {rows}"
    assert "statistic" in VERDICT_KEYS
    assert contract == CONTRACT_VERSION


def test_the_vocabulary_is_prior_art_with_a_citation():
    """Every entry is external prior art or an explicit statement that none
    exists. A registry that lets us invent a statistic is one where a number's
    kind becomes whatever was convenient to say about it."""
    for slug, spec in statistics().items():
        assert spec.get("citation"), slug
        assert spec.get("namespace") in ("ieee-1752.1", "vitai"), slug
        assert spec.get("label"), slug


def test_every_borrowed_term_is_in_the_published_enum():
    """CONFORMANCE THAT IS CHECKED RATHER THAN CLAIMED (#263).

    A `namespace = "ieee-1752.1"` entry asserts that a published standard
    contains that term. Asserting a non-empty citation string proves nothing
    about the standard, which is conformance by assertion - the defect #263
    names. The published enum ships as a fixture, fetched from the schema's
    own w3id URL, and every borrowed term must be in it VERBATIM.

    This caught a real one: `standard deviation` is spelled with a space in
    the standard and our slug uses a hyphen, so a consumer deriving the term
    from the slug would have exported a value the standard does not define.
    The `term` field carries the standard's spelling for exactly that reason.
    """
    published = set(_published()["enum"])
    borrowed = {k: v for k, v in statistics().items()
                if v["namespace"] == "ieee-1752.1"}

    assert borrowed, "the whole point is that most of these are not ours"
    for slug, spec in borrowed.items():
        assert spec.get("term"), f"{slug} claims the standard and names no term"
        assert spec["term"] in published, (
            f"{slug} claims IEEE 1752.1 term {spec['term']!r}, which is not in "
            f"the published enum: {sorted(published)}")


def test_the_vocabulary_is_a_subset_and_says_so():
    """We adopt the terms this engine computes, not the whole enum. Claiming
    the enum IS our vocabulary was the first version's wording and it was
    false in both directions - seventeen terms published, eight borrowed."""
    published = set(_published()["enum"])
    borrowed = {v["term"] for v in statistics().values() if v.get("term")}

    assert borrowed < published, "a strict subset, or the comment is wrong"
    assert len(published) > len(borrowed)


def test_the_engine_does_not_know_a_statistic_the_registry_lacks():
    """The code reads the vocabulary rather than restating it, so the two
    cannot drift - the failure `vocabularies.md` records ten instances of."""
    from vitai import verdicts

    assert verdicts.STATISTICS == frozenset(statistics())
    for name in (verdicts.AVERAGE, verdicts.MAXIMUM, verdicts.COUNT,
                 verdicts.PERIOD_CHANGE):
        assert name in verdicts.STATISTICS


def test_a_symptom_count_is_a_count_and_not_an_average(tmp_path):
    """Two chest-pain episodes in a week is 2, not 1 per day. The row set a
    dashboard already renders is where the mislabel would be least visible."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for day in (6, 8):
        v.append("daily", {"date": f"2030-05-{day:02d}", "steps": 9000,
                           "note": "chest pain climbing the stairs, eased "
                                   "after a few minutes rest",
                           "source": "athlete"})

    rows = [r for r in v.verdicts(__import__("datetime").date(2030, 5, 10))
            if str(r["metric"]).startswith("symptom_")]

    assert rows, "the fixture must trigger a symptom row"
    assert all(r["statistic"] == "count" for r in rows)


def test_a_json_consumer_sees_the_label(tmp_path):
    """The CLI contract a dashboard consumes, not only the Python one."""
    rows = json.loads(json.dumps(Vitai(DEMO).verdicts()))

    judged = [r for r in rows if r["value"] is not None]
    assert judged and all("statistic" in r for r in judged)
    # And a refused row still carries the KEY, so a consumer can select it
    # without discovering that some rows lack the column.
    assert all("statistic" in r for r in rows)


def test_the_contraindicated_rewrite_keeps_each_row_own_label():
    """The SECOND row-rebuilding site, which had no coverage at all.

    When rapid loss is the declared expectation of a treatment, `weight_rate`
    is relabelled `contraindicated` and keeps its value. Hardcoding `average`
    into that rewrite passed all 1510 tests, because nothing asserted a
    statistic on any contraindicated row - the same fixture-never-reaches-the-
    path failure as the suppression one, at the site next door.
    """
    from vitai.config import Config
    from vitai.verdicts import compute_verdicts

    weight = [{"date": f"2030-06-{d:02d}", "kg": 126.0 - d * 0.3,
               "source": "clinic", "note": None, "body_fat_pct": None,
               "kg_lo": None, "kg_hi": None, "body_fat_lo": None,
               "body_fat_hi": None, "_gen": 2} for d in range(1, 15)]
    med = [{k: None for k in KEYS["medical"]} | {
        "date": "2030-05-01", "slug": "glp1", "kind": "medication",
        "title": "a treatment", "severity": "none", "status": "active",
        "expects": "rapid_loss", "_gen": CURRENT_GENERATION["medical"]}]

    rows = compute_verdicts(Config(phases=((130.0, 100.0, 0.7),)),
                            weight, [], [], medical=med)
    rewritten = [r for r in rows
                 if r["metric"] == "weight_rate" and r["value"] is not None]

    assert rewritten, "the fixture must produce a contraindicated valued row"
    assert all(r["reason"] == "contraindicated" for r in rewritten)
    assert all(r["statistic"] == "period-over-period-change"
               for r in rewritten), "the rewrite substituted its own label"


def test_the_safety_floors_declare_their_statistic_and_their_window():
    """The floors had ZERO label coverage, and they are the safety-bearing
    rows. They are also the ones whose population is not the week they are
    keyed by: a fourteen-day mean on a row that names one week.
    """
    from vitai.config import Config
    from vitai.verdicts import compute_verdicts

    days = [{k: None for k in KEYS["daily"]} | {
        "date": f"2030-06-{d:02d}", "kcal_in": 900.0, "protein_g": 28.0,
        "source": "athlete", "_gen": CURRENT_GENERATION["daily"]}
        for d in range(1, 15)]
    weight = [{k: None for k in KEYS["weight"]} | {
        "date": "2030-06-14", "kg": 70.0, "source": "scale",
        "_gen": CURRENT_GENERATION["weight"]}]

    rows = {r["metric"]: r for r in compute_verdicts(
        Config(), weight, days, [], medical=[]) if r["value"] is not None}

    assert "intake_floor" in rows and "protein_floor" in rows
    for metric in ("intake_floor", "protein_floor"):
        assert rows[metric]["statistic"] == "average", metric
        assert rows[metric]["window_days"] == 14, (
            f"{metric} is a mean over fourteen days on a row keyed by one "
            f"week; saying 7 would point a consumer at the wrong population")


def test_energy_availability_does_not_claim_to_be_an_average():
    """It is (mean intake - exercise per day) / fat-free mass.

    On a record with fewer than fourteen logged intakes the two terms do not
    even share a denominator - the mean is over the days that carry one, the
    second divides by the window length regardless - so it is the mean of no
    per-day series that exists. `average` was the first label and it was
    wrong; nothing asserted it, so relabelling it `count` also passed.
    """
    from vitai.config import Config
    from vitai.verdicts import compute_verdicts

    days = [{k: None for k in KEYS["daily"]} | {
        "date": f"2030-06-{d:02d}", "kcal_in": 1400.0, "protein_g": 90.0,
        "source": "athlete", "_gen": CURRENT_GENERATION["daily"]}
        for d in range(1, 15)]
    weight = [{k: None for k in KEYS["weight"]} | {
        "date": "2030-06-14", "kg": 70.0, "body_fat_pct": 20.0,
        "source": "scale", "_gen": CURRENT_GENERATION["weight"]}]
    sessions = [{k: None for k in KEYS["sessions"]} | {
        "date": "2030-06-10", "type": "run", "duration_s": 3600,
        "kcal": 600.0, "source": "watch",
        "_gen": CURRENT_GENERATION["sessions"]}]

    rows = {r["metric"]: r for r in compute_verdicts(
        Config(), weight, days, sessions, medical=[]) if r["value"] is not None}

    assert "energy_availability" in rows, "the fixture must produce an EA row"
    assert rows["energy_availability"]["statistic"] == "composite-of-summaries"
    assert rows["energy_availability"]["window_days"] == 14
