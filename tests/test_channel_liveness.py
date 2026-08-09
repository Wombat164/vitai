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


def test_a_record_that_never_used_a_channel_has_not_gone_quiet():
    """Reporting a gap there would invent a history the record does not have."""
    live = channel_liveness([row("2030-03-01", "connector")], "2030-03-31")
    assert live["active"]["last_seen"] is None
    assert live["active"]["quiet_days"] is None
    assert live["active"]["rows"] == 0


def test_a_record_with_no_stated_capture_reports_no_silence():
    """The inversion this must not commit: a schema gap read as a fact about
    the person."""
    live = channel_liveness([row(f"2030-03-{d:02d}", None) for d in range(1, 32)],
                            "2030-03-31")
    assert live["active"]["rows"] == 0 and live["passive"]["rows"] == 0
    assert live["active"]["last_seen"] is None
    assert live["passive"]["last_seen"] is None


def test_derived_rows_count_as_neither():
    live = channel_liveness([row("2030-03-31", "derived"),
                             row("2030-03-01", "manual_entry")], "2030-03-31")
    assert live["passive"]["rows"] == 0
    assert live["active"]["rows"] == 1


def test_no_contrast_field_is_emitted():
    """The first cut had one, and it fired only when the ACTIVE side was the
    quieter - null in the reverse case. That is the engine choosing which shape
    is worth naming and encoding the choice in the schema. Both numbers are
    here; a consumer that wants the difference subtracts, and one that wants it
    the other way round is not told it does not exist."""
    live = channel_liveness([row("2030-03-01", "connector"),
                             row("2030-03-31", "manual_entry")], "2030-03-31")
    assert "contrast_days" not in live, live
    assert live["passive"]["quiet_days"] == 30
    assert live["active"]["quiet_days"] == 0


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
    assert set(live) == {"active", "passive"}
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
    live = channel_liveness({"weight": rows}, "2030-04-10")
    assert live["active"]["last_seen"] == "2030-03-07"
    assert live["passive"]["last_seen"] == "2030-04-10"
    assert live["active"]["quiet_days"] - live["passive"]["quiet_days"] == 34


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


# --- the holes the second review found ---------------------------------------

def test_the_journal_is_the_athlete_writing_and_must_be_seen(tmp_path):
    """THE HOLE THAT MATTERED. Only six datasets carry `capture`. `journal` is
    not one of them, so reading initiative off that field alone made the one
    dataset that is nothing BUT the athlete typing sentences resolve to
    `unknown` and drop out of the count. The engine could report him silent for
    a month on a day he wrote to it - a statement about the athlete made out of
    a statement about the schema, which is the inversion the registry note says
    this must not commit. The row guard was right; the hole was one level up.
    """
    from vitai.schema import KEYS
    assert "capture" not in KEYS["journal"], "if this changes, so does the fix"

    live = channel_liveness(
        {"weight": [{"date": "2030-04-10", "capture": "connector"}],
         "journal": [{"date": "2030-04-09", "text": "still here. not running."}]},
        "2030-04-10")
    assert live["active"]["last_seen"] == "2030-04-09"
    assert live["active"]["rows"] == 1


def test_a_check_is_a_thing_somebody_did():
    live = channel_liveness({"checks": [{"date": "2030-04-09", "slug": "hop"}]},
                            "2030-04-10")
    assert live["active"]["rows"] == 1


def test_no_other_capture_less_dataset_is_guessed_at():
    """Only where the DATASET itself settles it. Guessing per dataset is how a
    vocabulary stops meaning anything, so the rest stay `unknown`."""
    for dataset in ("goals", "medical", "context", "events", "plans",
                    "thresholds", "achievements", "regimes"):
        live = channel_liveness({dataset: [{"date": "2030-04-09"}]}, "2030-04-10")
        assert live["active"]["rows"] == 0, dataset
        assert live["passive"]["rows"] == 0, dataset


def test_a_stated_capture_still_wins_over_the_dataset():
    """The dataset fallback is for rows with nothing stated. A `journal` row
    that somehow states a capture is read by what it says."""
    live = channel_liveness(
        {"journal": [{"date": "2030-04-09", "capture": "connector"}]},
        "2030-04-10")
    assert live["passive"]["rows"] == 1 and live["active"]["rows"] == 0


def test_it_counts_when_the_row_ARRIVED_not_when_it_happened():
    """The athlete types nothing for a month, then sits down and enters a
    month of backfill. Reading `date` reported him silent for a month on the
    day he wrote - the opposite of the fact this exists to show."""
    live = channel_liveness(
        [{"date": "2030-03-10", "capture": "manual_entry",
          "recorded_at": "2030-04-10T19:00:00+02:00"}],
        "2030-04-10")
    assert live["active"]["last_seen"] == "2030-04-10"
    assert live["active"]["quiet_days"] == 0


def test_a_row_with_no_usable_date_is_not_counted():
    """It used to reach `max()` as an empty string and win, putting a non-date
    into a field typed `date | None`."""
    live = channel_liveness([{"capture": "manual_entry"},
                             {"date": "2030-04-01", "capture": "manual_entry"}],
                            "2030-04-10")
    assert live["active"]["last_seen"] == "2030-04-01"
    assert live["active"]["rows"] == 1


def test_a_date_that_does_not_parse_cannot_win_the_maximum():
    """Compared as strings, an unparseable date beat every real one - it sorted
    above them, erased the true `last_seen` and nulled `quiet_days`, putting a
    non-date into a field typed `date | None`. Bad dates do reach here:
    `validate` reports `2030-04-31` and the row stays live."""
    # `2030-02-30` sorts BELOW the viewpoint, so it passes the horizon filter,
    # and ABOVE the real reading, so it wins `max()`. Compared as strings it
    # became `last_seen`; parsed for `quiet_days` a moment later, it raises.
    live = channel_liveness([{"date": "2030-02-30", "capture": "manual_entry"},
                             {"date": "2030-01-05", "capture": "manual_entry"}],
                            "2030-04-10")
    assert live["active"]["last_seen"] == "2030-01-05"
    assert live["active"]["quiet_days"] == 95
    assert live["active"]["rows"] == 1


def test_a_trailing_space_is_tolerated_rather_than_dropped():
    """The other side of the same guard: a date that is merely untidy is still
    a date, and dropping it would lose a real arrival."""
    live = channel_liveness([{"date": "2030-04-06 ", "capture": "manual_entry"}],
                            "2030-04-10")
    assert live["active"]["last_seen"] == "2030-04-06"


def test_a_viewpoint_that_does_not_parse_does_not_crash_or_lie():
    live = channel_liveness([{"date": "2030-04-05", "capture": "manual_entry"}],
                            "not-a-date")
    assert live["active"]["quiet_days"] is None


def test_a_partner_typing_on_the_athletes_behalf_is_still_a_person():
    """THE CLAIM IS NARROWED, NOT THE CODE. `read_by: human-other` is the case
    the corpus has - a partner entering rows - and those rows are a person
    acting, so the tool is being talked to. The first docstring said "the
    athlete's own action", which was stronger than what is checked. A consumer
    that needs the narrower question reads `read_by`, which exists for it."""
    rec = {"date": "2030-06-10", "capture": "narrative", "read_by": "human-other"}
    assert initiative_of(rec) == "active"


def test_the_brief_degrades_rather_than_failing(tmp_path):
    """`situation`'s stated invariant: every derived section is guarded and a
    failure is named in `unavailable` rather than taking down a brief whose
    whole job is to still answer. `channels` was computed outside the guard."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    (root / "data" / "weight.jsonl").write_text(
        json.dumps({"date": "2030-05-01", "kg": 70.0, "source": "scale"}) + "\n",
        encoding="utf-8")
    v = Vitai(root)
    import vitai.provenance as prov

    def boom(*_a, **_k):
        raise ValueError("a channel it could not read")

    saved = prov.channel_liveness
    prov.channel_liveness = boom
    try:
        brief = v.situation(on="2030-05-01")
    finally:
        prov.channel_liveness = saved
    assert brief["unresolved"]["channels"] == {}
    assert any("channels" in str(u) for u in brief["unresolved"]["unavailable"]), \
        brief["unresolved"]["unavailable"]
