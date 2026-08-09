"""A protocol is what pins down the measurand (#174, proposal 4).

`weight.protocol` was written from row one, validated, and read by nothing.
Two things followed from that, and the second is the worse one.

A TREND ACROSS A PROTOCOL CHANGE was reported as a rate. `fasted-post-void`
and `fed-evening-clothed` are not two readings of one quantity; they differ by
breakfast, a day's fluid and a pair of shoes. The engine already declines a
rate whose weigh-in TIMES are spread widely enough to account for it - this is
the same refusal with a discrete cause instead of a continuous one, which is
the calibration-seam argument applied to procedure rather than instrument.

AND A VALIDLY RECORDED READING WAS BEING DISCARDED. Resolution bucketed
`weight` by date alone, so a 06:40 fasted weigh-in and an 18:05 fed one landed
in one contest and the ladder threw the second away - the engine's own
explanation read `discarded: hand=65.8`. `measurements` has had the right rule
all along, one line up in the same function: each KIND is its own quantity, so
a waist reading and a body-fat read on one day do not compete. `protocol` is
that same statement for body mass.

NO SIZE ESTIMATE ANYWHERE IN THIS. It would be easy to hold a table of what a
clothed evening weigh-in adds and subtract it. That is a per-protocol accuracy
claim about equipment and habits this engine has never seen, and it is the
figure the project refuses to invent everywhere else. What the record supports
is that the procedure changed, which is enough to decline the comparison.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.clocks import protocol_seam
from vitai.config import Config
from vitai.report import build_report
from vitai.schema import KEYS

INES = Path(__file__).resolve().parent / "fixtures" / "personas" / "ines"
TODAY = date(2030, 6, 10)


def weigh(day: str, kg: float, protocol=None, source="scale", at="06:40") -> dict:
    return {**{k: None for k in KEYS["weight"]}, "date": day, "kg": kg,
            "source": source, "protocol": protocol, "measured_at": at,
            "recorded_at": f"{day}T07:00:00+01:00"}


def record(tmp_path: Path, rows: list[dict], toml: str = "") -> Vitai:
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n' + toml,
                                     encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


# --- the detector -------------------------------------------------------------

def test_one_protocol_is_not_a_seam():
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 69.8, "fasted-post-void")])
    assert scope["seam"] is False
    assert scope["protocols"] == ["fasted-post-void"]
    assert scope["stated"] == 2 and scope["silent"] == 0


def test_two_protocols_are():
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert scope["seam"] is True
    assert scope["protocols"] == ["fasted-post-void", "fed-evening-clothed"]


def test_silence_is_not_a_protocol():
    """A record that has never used the field must not acquire a seam the day
    it starts, and a run of unnamed rows beside one named row is an unanchored
    INTERVAL rather than a change of procedure - which is the rest of #174 and
    is not decided here."""
    scope = protocol_seam([weigh("2030-05-01", 70.0),
                           weigh("2030-05-08", 69.8, "fasted-post-void")])
    assert scope["seam"] is False
    assert scope["stated"] == 1 and scope["silent"] == 1
    assert protocol_seam([weigh("2030-05-01", 70.0)])["seam"] is False
    assert protocol_seam([])["seam"] is False


def test_an_empty_string_is_silence_not_a_protocol():
    assert protocol_seam([weigh("2030-05-01", 70.0, ""),
                          weigh("2030-05-08", 69.8, "fasted-post-void")
                          ])["seam"] is False


def test_the_detector_states_no_size():
    """The refusal says the procedure changed and stops. A figure for what a
    clothed evening weigh-in adds would be a per-protocol accuracy claim about
    hardware and habits the engine has never seen."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert set(scope) == {"protocols", "seam", "stated", "silent"}
    assert not any(isinstance(v, float) for v in scope.values())


# --- the refusal, through the surfaces ----------------------------------------

def _seam_record(tmp_path: Path) -> Vitai:
    """SAME TIME, DIFFERENT PROCEDURE, and the sameness is deliberate.

    A fed evening weigh-in also moves the clock, so a fixture built that way
    trips the #37 timing-drift refusal as well and proves nothing about this
    one - the mutation pass caught exactly that. Here the athlete keeps
    weighing at 06:40 and starts doing it clothed, so the protocol is the only
    thing that changed and the refusal can only have come from it.
    """
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
            for d in range(1, 15)]
    rows += [weigh(f"2030-05-{d:02d}", 71.5 - d * 0.05, "fasted-clothed")
             for d in range(15, 29)]
    return record(tmp_path, rows,
                  "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")


def test_a_rate_across_the_seam_is_declined_in_the_verdicts(tmp_path):
    """`not_supported`, the same reason the timing-drift refusal uses: the
    measurement cannot support the judgement. Not `no_policy` - there is a
    target - and not a verdict, because a consumer renders AHEAD or BEHIND as
    fact."""
    v = _seam_record(tmp_path)
    crossing = [r for r in v.verdicts()
                if r.get("metric") == "weight_rate" and r["week"] == "2030-05-13"]
    assert crossing, [r["week"] for r in v.verdicts()
                      if r.get("metric") == "weight_rate"]
    assert crossing[0]["verdict"] == "no_data"
    assert crossing[0]["reason"] == "not_supported"


def test_the_rollup_says_the_protocol_changed_rather_than_the_times_varied():
    """Two different sentences for two different problems. "Weigh-in times
    vary" is a habit to tighten; a protocol change is a boundary the rate does
    not cross, and telling somebody to weigh more consistently would be advice
    about the wrong thing."""
    # The seam has to fall inside the rate's OWN window - it judges the seven
    # days it computes over and nothing else, which is #68's rule and stays
    # true here.
    rows = [weigh(f"2030-06-{d:02d}", 70.0 - d * 0.02, "fasted-post-void")
            for d in range(1, 6)]
    rows += [weigh(f"2030-06-{d:02d}", 71.4 - d * 0.02, "fasted-clothed")
             for d in range(6, 10)]
    out = build_report(Config(phases=((70.0, 68.0, 0.15),)), rows, [], [],
                       today=TODAY)
    assert "NOT COMPARABLE" in out, out
    assert "protocol changed over this window" in out, out
    assert "fasted-post-void then fasted-clothed" in out, out
    assert "weigh-in times vary too much" not in out, out


def test_a_rate_under_one_protocol_is_untouched(tmp_path):
    """The control. Everything above must cost nothing to a record that
    weighs itself the same way every time."""
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
            for d in range(1, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates
    assert not any(r["reason"] == "not_supported" for r in rates), rates


def test_a_record_that_never_names_a_protocol_is_untouched(tmp_path):
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05) for d in range(1, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates
    assert not any(r["reason"] == "not_supported" for r in rates), rates


# --- what is NOT fixed here, pinned so it cannot be forgotten ----------------

def test_two_protocols_on_one_day_are_still_adjudicated_against_each_other():
    """THE DEFECT UNDER THE SEAM, PINNED RATHER THAN FIXED, with the reason.

    Resolution buckets `weight` by date alone, so ines' 06:40 fasted weigh-in
    and her 18:05 fed one land in one contest and the ladder discards the
    second - the engine's own explanation reads `discarded: hand=65.8`. A
    reading that is not wrong and has no better replacement, gone because
    another reading shares its date.

    Splitting the bucket by `protocol` - the rule `measurements` already
    applies by `kind`, one line up in the same function - was built and then
    withdrawn, because it makes `weight` yield more canonical rows per date
    than the rest of the engine is ready for. Two consequences are
    safety-grade: `safety._loss_pct_per_week` picks its endpoints
    protocol-blind, so a twice-daily record's RED-S loss rate collapses under
    the threshold and the clinical hold silently stops firing; and
    `composition.endpoints` would assert a resolvable fat change across a
    twelve-hour seam and print it in the rollup.

    This asserts TODAY's behaviour so that changing it has to be deliberate.
    It is not an endorsement of it.
    """
    v = Vitai(INES)
    day = [r for r in v.canonical("weight") if r["date"] == "2030-05-30"]
    assert len(day) == 1, "still one row - see the docstring"
    assert day[0]["protocol"] == "fasted-post-void"
    discarded = [e for e in v.resolution()["explanations"]
                 if e.get("date") == "2030-05-30" and e.get("field") == "kg"]
    assert discarded and "65.8" in str(discarded[0]["discarded"]), discarded


def test_ines_e2_is_not_answered_by_this_change():
    """And the seam never fires for her, which is the honest consequence.

    Her two protocols sit on ONE day, so the discard above removes the second
    before any window can span it. ines-E2 needs the resolution split, and
    that is why the split is worth doing rather than why it is safe to do
    today. Recorded here so the expectation is not read as satisfied.
    """
    v = Vitai(INES)
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates, "she has rates"
    assert not any(r.get("reason") == "not_supported" for r in rates), \
        "no seam is visible to her record while the fed reading is discarded"


# --- the rules the review found uncontrolled ---------------------------------

def test_the_protocols_are_named_in_the_order_they_were_used():
    """The report joins these with "then". A sorted set made that assert a
    chronology the record contradicts."""
    rows = [weigh("2030-05-01", 70.0, "zz-morning"),
            weigh("2030-05-08", 71.0, "aa-evening")]
    assert protocol_seam(rows)["protocols"] == ["zz-morning", "aa-evening"]
    assert protocol_seam(list(reversed(rows)))["protocols"] == \
        ["zz-morning", "aa-evening"], "file order must not decide it"


def test_a_seam_the_rate_stands_on_is_seen(tmp_path):
    """`v0` is a trailing 7-day mean at `anchor0`, so it reaches up to six days
    BEFORE it. Scoping the window to `anchor0..last` let a protocol change the
    rate is standing on go unseen - it printed "FAST - raise intake", a deficit
    instruction manufactured entirely by the change, while the verdicts refused
    the same week. Two surfaces disagreeing about one record."""
    rows = [weigh(f"2030-05-{d:02d}", 71.4, "fasted-clothed") for d in range(1, 5)]
    rows += [weigh(f"2030-05-{d:02d}", 70.0, "fasted-post-void")
             for d in range(5, 13)]
    out = build_report(Config(phases=((70.0, 68.0, 0.15),)), rows, [], [],
                       today=date(2030, 5, 12))
    assert "NOT COMPARABLE" in out, out
    assert "raise intake" not in out, out


def test_the_two_surfaces_agree_about_one_record(tmp_path):
    """The invariant behind the last one: wherever the rollup declines, the
    verdicts decline, and the other way round."""
    rows = [weigh(f"2030-05-{d:02d}", 71.4, "fasted-clothed") for d in range(1, 5)]
    rows += [weigh(f"2030-05-{d:02d}", 70.0, "fasted-post-void")
             for d in range(5, 13)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rollup_declines = "NOT COMPARABLE" in v.rollup(today=date(2030, 5, 12))
    latest = [r for r in v.verdicts(today=date(2030, 5, 12))
              if r.get("metric") == "weight_rate"]
    verdict_declines = any(r.get("reason") == "not_supported" for r in latest)
    assert rollup_declines == verdict_declines, (rollup_declines, latest)


def test_the_seam_is_reported_even_with_no_target_configured():
    """A record with no phase still deserves to know its trend crossed a seam.
    #37's timing caveat already prints unconditionally; this is the same class
    of statement, and it used to vanish when `target` was None."""
    rows = [weigh(f"2030-06-{d:02d}", 70.0, "fasted-post-void") for d in range(1, 6)]
    rows += [weigh(f"2030-06-{d:02d}", 71.4, "fasted-clothed") for d in range(6, 10)]
    out = build_report(Config(), rows, [], [], today=TODAY)
    assert "NOT COMPARABLE" in out, out


def test_no_direction_word_is_printed_beside_the_refusal():
    """"gaining, and also NOT COMPARABLE" hands the reader the number's
    meaning and then withdraws it. If the rate cannot be compared, the
    direction is not a finding either."""
    rows = [weigh(f"2030-06-{d:02d}", 70.0, "fasted-post-void") for d in range(1, 6)]
    rows += [weigh(f"2030-06-{d:02d}", 71.4, "fasted-clothed") for d in range(6, 10)]
    out = build_report(Config(phases=((70.0, 68.0, 0.15),)), rows, [], [],
                       today=TODAY)
    line = next(ln for ln in out.splitlines() if "**Rate:**" in ln)
    assert "gaining" not in line and "losing" not in line, line
    assert "against a target of" not in line, line


def test_the_seam_is_reported_instead_of_the_timing_caveat_not_beside_it():
    """Precedence, which had no control because the seam fixture deliberately
    removed the drift confound. Here BOTH fire, and the seam must win: telling
    somebody to weigh more consistently is advice about the wrong thing when
    the procedure itself changed."""
    rows = [weigh(f"2030-06-{d:02d}", 70.0, "fasted-post-void", at="06:40")
            for d in range(1, 6)]
    rows += [weigh(f"2030-06-{d:02d}", 70.1, "fasted-clothed", at="19:30")
             for d in range(6, 10)]
    out = build_report(Config(phases=((70.0, 68.0, 0.15),)), rows, [], [],
                       today=TODAY)
    line = next(ln for ln in out.splitlines() if "**Rate:**" in ln)
    assert "NOT COMPARABLE" in line, line
    assert "NOT READABLE" not in line, line


def test_a_seam_outside_the_window_does_not_suppress_a_later_clean_rate(tmp_path):
    """The sixth uncontrolled rule: scoping. Passing the whole history instead
    of the window would let one protocol change suppress every rate forever,
    and the entire suite stayed green under that mutation."""
    rows = [weigh(f"2030-04-{d:02d}", 72.0, "fasted-clothed") for d in range(1, 15)]
    rows += [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
             for d in range(1, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    late = [r for r in v.verdicts() if r.get("metric") == "weight_rate"
            and r["week"] >= "2030-05-13"]
    assert late, "there are later weeks"
    assert not any(r.get("reason") == "not_supported" for r in late), late


# --- one spelling is not two protocols ----------------------------------------

def test_a_spelling_variant_does_not_manufacture_a_seam():
    """A FALSE REFUSAL IS NOT A SAFE ONE. Comparing raw strings meant
    `Fasted-Post-Void` and `fasted-post-void` were two protocols, so a rate was
    declined as NOT COMPARABLE for an athlete who weighed the same way both
    times. The validator does report the spelling - `protocol` must be a slug -
    but it is a separate call, and a refusal that fires on a typo is one
    readers learn to skip past.
    """
    for variant in ("Fasted-Post-Void", "fasted_post_void", "fasted post void",
                    "FASTED-POST-VOID"):
        scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                               weigh("2030-05-08", 69.8, variant)])
        assert scope["seam"] is False, variant
        assert scope["protocols"] == ["fasted-post-void"], variant


def test_two_real_protocols_still_are():
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert scope["seam"] is True
    assert len(scope["protocols"]) == 2


@pytest.mark.parametrize("a,b", [("post-void", "postvoid"),
                                 ("dxa-1", "dxa1"),
                                 ("dexa", "dexa-2")])
def test_a_separator_folds_to_a_word_boundary_and_never_to_nothing(a, b):
    """A NEAR PAIR, because the far pair proved nothing.

    The first control for over-merging paired `fasted-post-void` with
    `fed-evening-clothed` - strings differing in every token, which no fold
    short of collapsing dissimilar words can merge. A fold one notch more
    aggressive (separators to nothing rather than to a space) passed the
    entire suite and made `dxa-1` and `dxa1` one protocol. The rule under test
    is exactly one character class wide, so the control has to be too."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, a),
                           weigh("2030-05-08", 71.4, b)])
    assert scope["seam"] is True, (a, b)
    assert scope["protocols"] == [a, b]


def test_the_whole_registry_fold_is_used_and_not_half_of_it():
    """`vocab.resolve` normalises AND decamels, so `FastedPostVoid` is one
    value with `fasted-post-void` to every lookup in the engine. Borrowing only
    `_normalise` left exactly the vendor token shape `_decamel` exists for
    still seaming, while the comment claimed the registry's equivalence."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-08", 69.8, "FastedPostVoid")])
    assert scope["seam"] is False
    assert scope["protocols"] == ["fasted-post-void"]


def test_a_placeholder_is_not_a_procedure():
    """`" "`, `"-"` and `"___"` all normalise to nothing. The raw-value filter
    let them through as three named protocols which then merged into one, so
    the report named a protocol called `" "`."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, " "),
                           weigh("2030-05-04", 70.0, "-"),
                           weigh("2030-05-08", 71.4, "___")])
    assert scope["protocols"] == []
    assert scope["seam"] is False
    assert scope["stated"] == 0


def test_the_order_is_the_records_and_not_the_files():
    """THIS MODULE'S OWN ACCEPTANCE CRITERION: "an ordering a formatter can
    change is not an ordering". Sorting by file position was cosmetic while
    both spellings were listed; now that the first becomes the single
    athlete-facing name, reordering two lines changed the report - and the name
    chosen was not the one `recorded_at` says came first."""
    early = weigh("2030-05-01", 70.0, "fasted-post-void")
    early["recorded_at"] = "2030-05-01T06:00:00Z"
    late = weigh("2030-05-01", 70.0, "Fasted-Post-Void")
    late["recorded_at"] = "2030-05-01T07:00:00Z"
    other = weigh("2030-05-08", 71.4, "fed-evening-clothed")

    forwards = protocol_seam([early, late, other])["protocols"]
    backwards = protocol_seam([late, early, other])["protocols"]
    assert forwards == backwards == ["fasted-post-void", "fed-evening-clothed"]


def test_a_slug_with_a_trailing_newline_is_still_a_fault():
    """`$` matches before a trailing newline in Python, so `"hop-test\n"`
    passed every slug check in `schema.py` - six of them. Found here: the fold
    merged it onto the real slug and the validator said nothing, so an
    invisible character had no witness anywhere."""
    from vitai.schema import validate_record

    row = weigh("2030-05-01", 70.0, "fasted-post-void\n")
    assert validate_record("weight", row), "the fault must be reported"


def test_the_athletes_own_spelling_is_what_gets_reported():
    """Only the COMPARISON folds. The rollup relays what the record says, and
    normalising the reported name would show the athlete a word they did not
    write."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, "Fasted Post Void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert "Fasted Post Void" in scope["protocols"]


def test_the_first_spelling_wins_when_they_disagree():
    """Deterministic, and it is the one the athlete used first - so a later
    typo does not rename their protocol in the report."""
    scope = protocol_seam([weigh("2030-05-01", 70.0, "fasted-post-void"),
                           weigh("2030-05-04", 70.0, "Fasted-Post-Void"),
                           weigh("2030-05-08", 71.4, "fed-evening-clothed")])
    assert scope["protocols"] == ["fasted-post-void", "fed-evening-clothed"]


def test_a_rate_is_not_declined_for_a_typo(tmp_path):
    """End to end, which is where the harm was: the verdict, not the helper."""
    rows = [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "fasted-post-void")
            for d in range(1, 15)]
    rows += [weigh(f"2030-05-{d:02d}", 70.0 - d * 0.05, "Fasted-Post-Void")
             for d in range(15, 29)]
    v = record(tmp_path, rows, "[targets]\nphases = [[70.0, 68.0, 0.15]]\n")
    rates = [r for r in v.verdicts() if r.get("metric") == "weight_rate"]
    assert rates
    assert not any(r.get("reason") == "not_supported" for r in rates), rates
