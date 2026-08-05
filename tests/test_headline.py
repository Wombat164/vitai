"""What a client may put at the top of a screen without inventing it (#209).

A conformance client deleted four stat tiles because each was a derivation the
engine does not emit. The issue's table says the 7-day weight average is one of
them - "nothing. No rolling mean anywhere".

That is half right, and the half it gets wrong is the interesting one.
`status()` has always emitted `mean_kg_7d`, and it is the mean of the last
SEVEN WEIGH-INS rather than of seven days. On a record with one weigh-in a week
those seven points span six weeks. So the engine was not missing the tile: it
was making the same mistake the issue catches the client making, in the field's
own name, and the CLI printed it as "7d avg".
"""

from __future__ import annotations

from pathlib import Path

from vitai.api import Vitai, init

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def _weekly(tmp_path: Path) -> Vitai:
    """One weigh-in a week, which is an ordinary way to keep this record."""
    root = init(tmp_path / "content")
    v = Vitai(root)
    for n, day in enumerate(("2030-03-04", "2030-03-11", "2030-03-18",
                             "2030-03-25", "2030-04-01", "2030-04-08",
                             "2030-04-15", "2030-04-22", "2030-04-29")):
        v.append("weight", {"date": day, "kg": 82.0 - n * 0.3,
                            "source": "scale"})
    return v


def test_the_mean_says_what_it_is_actually_over(tmp_path):
    """THE DEFECT, measured rather than asserted.

    Seven weigh-ins a week apart is a forty-two day mean. Rendering it as
    "7d avg" describes a window the record never used, and every consumer
    reading the field name alone would render it that way.
    """
    st = _weekly(tmp_path).status("2030-04-29")

    assert st["mean_kg_points"] == 7
    assert st["mean_kg_span_days"] == 42


def test_a_daily_weigher_gets_the_span_the_name_promises():
    """Where the two agree, they agree - so the field is not always wrong,
    which is precisely why it went unnoticed."""
    st = Vitai(DEMO).status("2030-06-30")

    assert st["mean_kg_points"] == 7
    assert st["mean_kg_span_days"] <= 7


def test_the_value_itself_did_not_change(tmp_path):
    """A consumer already reading `mean_kg_7d` keeps the number it had.

    The span arrives BESIDE it. Silently recomputing the mean over a real
    seven-day window would move a figure on somebody's screen with no
    contract change to point at, which is a worse fix than the mislabel.
    """
    st = _weekly(tmp_path).status("2030-04-29")

    # The last seven of the nine weigh-ins, which is what it has always been.
    expected = sum(82.0 - n * 0.3 for n in range(2, 9)) / 7

    assert round(st["mean_kg_7d"], 6) == round(expected, 6)


def test_the_cli_labels_the_span_it_used(tmp_path):
    """The CLI printed "7d avg" from the field name. It is where the mislabel
    actually reached a person."""
    import subprocess
    import sys

    root = _weekly(tmp_path).root
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "status", "--root", str(root)],
        capture_output=True, text=True, check=True)

    assert "42d avg" in out.stdout
    assert "7d avg" not in out.stdout
    assert "7 weigh-ins" in out.stdout


def test_the_rate_the_client_reimplemented_was_already_emitted():
    """The issue's own useful row: the engine emits a rate judged against the
    phase target and the dashboard displayed neither - it computed its own
    over a different window. A discoverability failure, not a missing
    feature."""
    v = Vitai(DEMO)
    judged = [r for r in v.verdicts()
              if r["metric"] == "weight_rate" and r["value"] is not None]

    assert judged
    assert all(r["target"] is not None for r in judged)
    # And the same figure is one call away for a client that wants one number
    # rather than a week series.
    assert v.status("2030-06-30")["rate_kg_per_week"] is not None


def test_no_cross_metric_adherence_figure_is_emitted():
    """AND THERE SHOULD NOT BE ONE.

    The deleted tile collapsed every metric and every week into one
    percentage with refusals dropped from the denominator, so a record ninety
    per cent unjudgeable could show one hundred per cent adherence.

    `verdicts` carries a `reason` column and refuses to write a declined row
    without one, precisely so a consumer cannot flatten "the record holds
    nothing to judge" into "not counted". A single percentage flattens it by
    construction, and an engine-side version would inherit the same defect.
    This test exists so that adding one is a deliberate act rather than an
    afternoon's convenience.
    """
    v = Vitai(DEMO)
    surfaces = [v.status("2030-06-30"), v.situation()]

    for surface in surfaces:
        assert not [k for k in surface
                    if "adherence" in k or "compliance" in k], surface.keys()


def test_a_refusal_is_still_visible_beside_the_judged_rows():
    """What a client needs INSTEAD of one percentage: the count it would have
    flattened, still separable."""
    rows = Vitai(DEMO).verdicts()
    refused = [r for r in rows if r["verdict"] == "no_data"]

    assert refused, "the demo must carry refusals or this proves nothing"
    assert all(r["reason"] for r in refused), (
        "a refusal without a reason is what makes flattening possible")
