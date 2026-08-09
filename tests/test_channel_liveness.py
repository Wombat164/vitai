"""The hardware kept talking (#146).

The engine could see WHAT arrived and not whether anybody was there when it
did. A record where the watches keep syncing and every line the athlete wrote
himself stopped a month ago is a different record from one where nothing is
happening, and `last_seen` cannot tell them apart because both channels write
into the same datasets.

The fact was already there and one registry field away. `capture` says how a
value arrived; `initiative` says whether a person had to do anything for it to
arrive at all - the ACTIVE versus PASSIVE split that digital phenotyping and
mHealth have drawn for years, where the whole point is that the two fail
differently and the active side stops first when somebody disengages.

AN OBSERVATION, NEVER A READING OF IT. Two dates and the gap between them.
Not engagement, not adherence, not motivation, and no threshold that decides
when the gap becomes one of those. `stefan` exists in this corpus to prove
that guessing is wrong even when the guess is right: his father died on
2030-03-09, the sentence appears nowhere in the record, and stefan-E0 says
any output naming a cause is wrong by construction. stefan-E4 adds the other
half - silence is neither compliance nor refusal, because nothing was adhered
to and nothing was declined.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from vitai.api import Vitai
from vitai.provenance import channel_liveness, initiative_of

STEFAN = Path(__file__).resolve().parent / "fixtures" / "personas" / "stefan"


def row(day: str, capture: str | None) -> dict:
    return {"date": day, "capture": capture}


# --- the axis -----------------------------------------------------------------

def test_a_person_had_to_be_there():
    for capture in ("manual_entry", "narrative", "photo"):
        assert initiative_of({"capture": capture}) == "active", capture


def test_nobody_had_to_be():
    for capture in ("ble", "connector", "file_export"):
        assert initiative_of({"capture": capture}) == "passive", capture


def test_a_bulk_export_is_passive_because_the_act_produced_the_transfer():
    """The one judgement call. Running an export IS an act, but it produced the
    transfer rather than the values - they were captured passively at the time
    and relayed later. Reading it as active would let one archive upload
    register as somebody starting to talk to the tool again."""
    assert initiative_of({"capture": "file_export"}) == "passive"


def test_arithmetic_is_neither_a_person_nor_a_sensor():
    for capture in ("derived", "derived_external"):
        assert initiative_of({"capture": capture}) == "derived", capture


def test_an_unstated_capture_is_its_own_answer():
    """And must not collapse into either side. A record that has never written
    `capture` would otherwise read as every channel silent, which turns a gap
    in the schema into a statement about the athlete."""
    assert initiative_of({}) == "unknown"
    assert initiative_of({"capture": None}) == "unknown"
    assert initiative_of({"capture": "something-nobody-registered"}) == "unknown"


def test_every_registered_capture_mode_declares_one():
    """A mode added without it would silently join `unknown` and be invisible
    to this whole surface."""
    from vitai.vocab import registry
    modes = registry("capture")["capture"]
    missing = [k for k, v in modes.items() if not v.get("initiative")]
    assert not missing, missing
    assert {v["initiative"] for v in modes.values()} <= {
        "active", "passive", "derived", "unknown"}


# --- the liveness ---------------------------------------------------------

def test_the_hardware_keeps_talking_while_the_athlete_stops():
    live = channel_liveness(
        [row(f"2030-03-{d:02d}", "connector") for d in range(1, 32)]
        + [row(f"2030-03-{d:02d}", "manual_entry") for d in range(1, 8)],
        "2030-03-31")
    assert live["active"]["last_seen"] == "2030-03-07"
    assert live["active"]["quiet_days"] == 24
    assert live["passive"]["last_seen"] == "2030-03-31"
    assert live["passive"]["quiet_days"] == 0
    assert live["contrast_days"] == 24


def test_a_record_that_never_used_a_channel_has_not_gone_quiet():
    """Reporting a gap there would invent a history the record does not have."""
    live = channel_liveness([row("2030-03-01", "connector")], "2030-03-31")
    assert live["active"]["last_seen"] is None
    assert live["active"]["quiet_days"] is None
    assert live["contrast_days"] is None


def test_a_record_with_no_stated_capture_reports_no_silence():
    """The inversion this must not commit: a schema gap read as a fact about
    the person."""
    live = channel_liveness([row(f"2030-03-{d:02d}", None) for d in range(1, 32)],
                            "2030-03-31")
    assert live["active"]["rows"] == 0 and live["passive"]["rows"] == 0
    assert live["active"]["last_seen"] is None
    assert live["passive"]["last_seen"] is None
    assert live["contrast_days"] is None


def test_derived_rows_count_as_neither():
    live = channel_liveness([row("2030-03-31", "derived"),
                             row("2030-03-01", "manual_entry")], "2030-03-31")
    assert live["passive"]["rows"] == 0
    assert live["active"]["rows"] == 1
    assert live["contrast_days"] is None, "derived must not fake a live channel"


def test_the_contrast_only_points_one_way():
    """Active quieter than passive is the shape worth seeing. The reverse - a
    device that stopped while the athlete kept writing - is a different fact
    with a different cause, and reporting it in the same field would let a
    consumer read one as the other."""
    live = channel_liveness([row("2030-03-01", "connector"),
                             row("2030-03-31", "manual_entry")], "2030-03-31")
    assert live["passive"]["quiet_days"] == 30
    assert live["active"]["quiet_days"] == 0
    assert live["contrast_days"] is None


def test_nothing_after_the_viewpoint_is_counted():
    live = channel_liveness([row("2030-03-01", "manual_entry"),
                             row("2030-06-01", "manual_entry")], "2030-03-31")
    assert live["active"]["last_seen"] == "2030-03-01"
    assert live["active"]["rows"] == 1


def test_it_reports_dates_and_a_gap_and_nothing_else():
    """No verdict, no threshold, no word for what the gap means. The moment
    this grows one it is guessing at a cause the record cannot support."""
    live = channel_liveness([row("2030-03-01", "manual_entry"),
                             row("2030-03-31", "connector")], "2030-03-31")
    assert set(live) == {"active", "passive", "contrast_days"}
    assert set(live["active"]) == {"last_seen", "quiet_days", "rows"}
    assert all(not isinstance(v, str) or v[:2].isdigit()
               for side in ("active", "passive")
               for v in [live[side]["last_seen"]] if v is not None)


# --- against the corpus that filed it -----------------------------------------

def test_stefan_e1_the_contrast_is_visible():
    """"passive rows continue while every athlete-initiated channel stops at
    once on 2030-03-08", read at the expectation's own viewpoint."""
    rows = []
    for path in sorted((STEFAN / "data").glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    live = channel_liveness(rows, "2030-04-10")
    assert live["active"]["last_seen"] == "2030-03-07"
    assert live["passive"]["last_seen"] == "2030-04-10"
    assert live["contrast_days"] == 34


def test_stefan_reaches_the_brief():
    """It is no use if a consumer cannot see it. Read over the RAW rows, not
    the canonical ones: resolution discards the losing claim in a contest, so a
    manual line that lost to a device line would take the athlete's own voice
    out of the count and the silence would be the ladder's, not his."""
    v = Vitai(STEFAN,
              as_of=datetime.fromisoformat("2030-04-10T20:00:00+02:00"))
    channels = v.situation(on="2030-04-10")["unresolved"]["channels"]
    assert channels["active"]["last_seen"] == "2030-03-07"
    assert channels["active"]["quiet_days"] >= 30
    assert channels["passive"]["quiet_days"] <= 1
    assert channels["contrast_days"] >= 30


def test_the_brief_names_no_cause_for_it():
    """stefan-E0: his father died on 2030-03-09, the sentence exists only in
    the expectations file, and any engine output naming a cause is wrong by
    construction - including a correct guess. This surface adds two dates and
    must not add a story."""
    v = Vitai(STEFAN,
              as_of=datetime.fromisoformat("2030-04-10T20:00:00+02:00"))
    channels = v.situation(on="2030-04-10")["unresolved"]["channels"]
    rendered = json.dumps(channels).lower()
    for word in ("engag", "motivat", "adher", "compli", "refus", "concern",
                 "grief", "stress", "disengag", "lapse", "abandon"):
        assert word not in rendered, f"{word} in {rendered}"


def test_the_count_is_over_raw_rows_because_canonical_ones_lose_claims(tmp_path):
    """THE RAW ROWS, NOT THE CANONICAL ONES, and this is the control for it.

    Two claims about one day, one typed by hand and one read off a scale.
    Resolution produces ONE canonical row, so at most one of the two captures
    survives into it - and worse, the merge is field by field, so the surviving
    `capture` need not even belong to the claim whose `kg` won. Counting
    channels off canonical rows would therefore report a day the athlete wrote
    on as a day he did not, and the silence would be the ladder's rather than
    his. That is exactly the misreading this surface exists to prevent.
    """
    from vitai.provenance import channel_liveness as liveness
    from vitai.schema import KEYS

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n'
        "[resolution.precedence]\nkg = ['scale', 'hand']\n", encoding="utf-8")
    rows = [{**{k: None for k in KEYS["weight"]}, "date": "2030-05-01",
             "kg": 70.0, "source": "scale", "capture": "ble",
             "recorded_at": "2030-05-01T07:00:00Z"},
            {**{k: None for k in KEYS["weight"]}, "date": "2030-05-01",
             "kg": 70.4, "source": "hand", "capture": "manual_entry",
             "recorded_at": "2030-05-01T07:00:01Z"}]
    (root / "data" / "weight.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    v = Vitai(root)
    assert len(v.canonical("weight")) == 1, "two claims, one canonical row"

    # Over canonical rows one of the two channels disappears entirely.
    over_canonical = liveness(v.canonical("weight"), "2030-05-01")
    assert 0 in (over_canonical["active"]["rows"],
                 over_canonical["passive"]["rows"]), over_canonical

    # Over the raw rows both are counted, which is what the brief reports.
    channels = v.situation(on="2030-05-01")["unresolved"]["channels"]
    assert channels["active"]["rows"] == 1
    assert channels["passive"]["rows"] == 1
    assert channels["active"]["last_seen"] == "2030-05-01", \
        "he typed something that day, whatever the ladder did with it"
