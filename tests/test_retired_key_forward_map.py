"""One canonicaliser, not nine hand-copies of half of it (#126, G89 part two).

`hip_pain` is retired at generation 2 in favour of `pain` + `pain_site`, and
`resolution.canonical_daily` is the one place that reads an old line forward.
Eight readers re-implemented that map anyway, and the re-implementations were
not equivalent to it: they carried the SCORE and dropped the SITE.

That is the failure mode a duplicated map has. A second copy is not merely
redundant - it is a copy someone wrote from memory, and what it forgets is
whatever the original did in its second half. Here it produced a record that
answered its own question two ways in one report: the gate said `unspecified
site` and the prose two lines below said `hip`.

WHY THE SAFETY PATH MAY CALL A FUNCTION FROM `resolution`, given the standing
decision that safety reads the RAW record: canonicalising is not adjudicating.
`canonical_daily` is a pure function of the single row it is handed. It
consults no other row, no source ladder and no precedence, so the property
that decision protects - an escalation cannot disappear because a ladder
picked another source's null - is untouched by it. The last test here pins
that, because the argument is only as good as the function staying pure.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from vitai.api import Vitai
from vitai.report import unreadable_dates
from vitai.resolution import canonical_daily
from vitai.safety import escalations, gates_on
from vitai.schema import KEY_RETIREMENT, KEYS

TODAY = date(2030, 5, 2)


def legacy_record(tmp_path: Path, score: int) -> Vitai:
    """A repo whose only pain line is written the generation-1 way."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text(
        '[athlete]\nname = "T"\n[tripwires]\npain_gate = 2\n', encoding="utf-8")
    row = {**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
           "hip_pain": score, "source": "manual",
           "recorded_at": "2030-05-01T08:00:00Z"}
    (root / "data" / "daily.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")
    return Vitai(root)


def test_a_legacy_line_gates_at_the_site_it_named(tmp_path):
    """The live defect. `gates_on` reads raw rows - deliberately - and its own
    copy of the forward map took the score and left the site behind, so the
    gate on a legacy record could not say which part of the athlete hurt."""
    gates = legacy_record(tmp_path, 4).gates()
    assert [g["slug"] for g in gates] == ["pain:hip"]
    assert "at hip" in gates[0]["reason"]
    assert "unspecified" not in gates[0]["reason"]


def test_the_gate_and_the_prose_do_not_disagree_about_one_row(tmp_path):
    """The symptom that makes this more than untidiness: both sentences are in
    the same report, about the same row, and they say different things. The
    prose reads canonical rows and knew the site all along."""
    out = legacy_record(tmp_path, 4).rollup()
    said = [ln for ln in out.splitlines() if "pain" in ln.lower()]
    assert said, out
    assert not any("unspecified site" in ln for ln in said), said


def test_a_legacy_line_reaches_the_verdict_through_the_api(tmp_path):
    """THE READER THAT CANONICALISES NOWHERE OF ITS OWN, pinned at the surface.

    `gates_on` and `escalations` call `canonical_daily` themselves, so the
    tests above hold whatever the caller hands them. `compute_verdicts` does
    not: it reads `d["pain"]` and nothing else, on the stated grounds that the
    rows arriving have already been mapped. That grounds is a property of
    every CALL SITE rather than of the function, and nothing checked it - the
    suite's other legacy-verdict test resolves the rows by hand first, so it
    would stay green if `Vitai.verdicts()` began passing raw ones.

    What that would look like is the reason this is worth a test: a legacy
    line has no `pain`, so it would not raise or warn. It would drop out of
    the pain gate silently, and a record whose only pain lines predate the
    generalisation would report no pain at all while validating cleanly.
    """
    rows = [r for r in legacy_record(tmp_path, 4).verdicts()
            if r["metric"] == "pain_gate"]
    assert rows, "the legacy line never reached the pain gate"
    assert rows[0]["value"] == 4
    assert rows[0]["verdict"] == "behind"


def test_a_legacy_line_escalates_at_the_site_it_named():
    """The same hand-copy sat on the absolute-threshold path, where the row
    that reaches it is the one nobody adjudicated on purpose."""
    legacy = {"date": "2030-05-01", "hip_pain": 9}
    out = escalations([], [legacy], [], [])
    assert [e["trigger"] for e in out] == ["severe_pain"]
    assert out[0]["detail"] == "pain 9 at hip"


def test_a_canonical_row_carries_both_spellings_so_counting_both_double_counts():
    """Why the reader's copy was not harmless even where it agreed.

    `canonical_daily` LEAVES the retired key in place - an appended line is
    never rewritten - so a mapped row answers to both names. The rollup's
    unreadable-date tally summed over a field list naming each, and reported
    one bad legacy row as two."""
    mapped = canonical_daily({"date": "not-a-date", "hip_pain": 4})
    assert mapped["pain"] == 4 and mapped["hip_pain"] == 4
    per_field = {f: unreadable_dates([mapped], TODAY, f)
                 for f in ("pain", "hip_pain")}
    assert per_field == {"pain": 1, "hip_pain": 1}, per_field


def test_one_unreadable_legacy_row_is_reported_as_one_row(tmp_path):
    """And the tally itself, through the surface that prints it."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    rows = [{**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "steps": 9000, "source": "manual"},
            {**{k: None for k in KEYS["daily"]}, "date": "2030-05-01",
             "hip_pain": 4, "source": "app"}]
    (root / "data" / "daily.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    # A row the report cannot date, carrying the retired key.
    bad = canonical_daily({"date": "2030-13-40", "hip_pain": 4})
    from vitai.report import build_report
    from vitai.config import Config
    out = build_report(Config(), [], [bad], [], today=TODAY)
    counted = re.search(r"(\d+) row\(s\) carry a date", out)
    assert counted is not None, out
    assert counted.group(1) == "1", out


# --- the structural half ------------------------------------------------------

# WHERE A RETIRED KEY MAY BE READ OFF A ROW, and why each one is allowed.
# Anything else is a forward map written a second time, which is how this key
# became load-bearing in five modules instead of one. Pinned rather than
# counted loosely: the bug was never a big number of sites, it was a site
# that disagreed with the canonicaliser about what the map does.
MAY_READ_THE_RETIRED_KEY = {
    "resolution.py": 2,   # the one canonicaliser: the test, and the value
    "schema.py": 1,       # validation, which must keep ACCEPTING an old line
}

_READS_IT = re.compile(r'(?:\.get\(|\[)\s*(["\'])hip_pain\1')


def test_the_retired_key_is_read_off_a_row_in_exactly_two_modules():
    """G89's acceptance criterion, as a check rather than a promise.

    The issue's own note says to grep the retired name across the tree before
    calling a retirement done. This is that grep, kept.

    A LOOKUP BY NAME IS NOT A READ AND IS NOT COUNTED. `_goal_for(active,
    "pain") or _goal_for(active, "hip_pain")` in `verdicts` is G89 part
    THREE - successor first, old name as fallback - and it is asking about a
    GOAL's declared metric, not mapping a daily row forward. Part three has
    to appear at every such site; part two must appear exactly once.
    """
    import vitai
    src = Path(vitai.__file__).parent
    found = {}
    for path in sorted(src.rglob("*.py")):
        if hits := len(_READS_IT.findall(path.read_text(encoding="utf-8"))):
            found[path.name] = hits
    assert found == MAY_READ_THE_RETIRED_KEY, (
        f"{found} - a reader that names the retired key is re-implementing "
        "`canonical_daily`. Call it instead: it maps the score AND the site, "
        "and a copy that forgets the second half is the #126 defect.")


def test_every_retired_key_has_a_generation():
    """The register this rests on. If a key is retired without one, the
    canonicaliser has no way to know an old line is old."""
    for dataset, keys in KEY_RETIREMENT.items():
        for key, gen in keys.items():
            assert key in KEYS[dataset], f"{dataset}.{key} retired but absent"
            assert isinstance(gen, int) and gen >= 2, f"{dataset}.{key}={gen}"


def test_the_canonicaliser_is_a_pure_function_of_the_row_it_is_given():
    """The whole licence for calling it from the safety path.

    Canonicalising must not be able to consult anything except the row: the
    moment it does, a gate becomes reachable by another row's content, and
    "safety reads the raw record" stops being true while still looking it.
    """
    row = {"date": "2030-05-01", "hip_pain": 4}
    alone = canonical_daily(dict(row))
    # Same row, in the company of others that would win any precedence ladder.
    crowd = [{"date": "2030-05-01", "pain": 0, "pain_site": "knee",
              "source": "clinic"},
             dict(row),
             {"date": "2030-05-01", "pain": 9, "pain_site": "back"}]
    assert canonical_daily(crowd[1]) == alone
    assert alone["pain"] == 4 and alone["pain_site"] == "hip"
    # And it does not invent the half the old field never recorded.
    assert alone.get("pain_side") is None


def test_a_line_written_the_new_way_is_left_exactly_alone():
    """A record that never had the retired key must not be able to tell that
    any of this exists - including on the safety path, which now runs every
    row through the canonicaliser."""
    modern = {"date": "2030-05-01", "pain": 4, "pain_site": "knee"}
    assert canonical_daily(modern) == modern
    gates = gates_on([], "2030-05-01", pain_gate=2, daily=[modern], checks=[])
    assert [g["slug"] for g in gates] == ["pain:knee"]


# --- the same rule, one field over: a site read without the registry ----------
#
# Found reviewing the change above rather than filed, and it is the same defect
# in a worse place. `pain_site` is validated against a registry that accepts
# ALIASES, so two spellings of one site are both clean, and any code comparing
# the raw string to a canonical slug answers differently depending on which the
# athlete typed. #126's thesis is that a map belongs in one place; a site read
# without the registry is that thesis broken on the field the retirement was
# generalised INTO.

def test_a_red_flag_site_written_as_an_alias_still_escalates():
    """The one that matters. `RED_FLAG_SITES` is keyed on slugs, and the raw
    comparison meant `ribs` - an accepted alias of `chest` - produced no
    cardiac escalation while `chest` produced an EMERGENCY. Same pain, same
    day, same record; the difference was a word choice."""
    for spelling in ("chest", "ribs", "sternum"):
        row = {"date": "2030-05-01", "pain": 3, "pain_site": spelling}
        out = escalations([], [row], [], [])
        assert [e["trigger"] for e in out] == ["cardiac"], spelling
        assert out[0]["level"] == "emergency", spelling


def test_a_red_flag_body_site_on_a_medical_line_escalates_by_alias_too():
    """The other loop, reading `medical.body_site` by the same broken rule."""
    episode = {"date": "2030-05-01", "kind": "injury", "title": "tightness",
               "body_site": "sternum", "status": "open"}
    out = escalations([episode], [], [], [])
    assert [e["trigger"] for e in out] == ["cardiac"]


def test_a_site_the_registry_does_not_know_is_not_a_red_flag():
    """`resolve` returns None for a site the registry does not know, and
    normalising must not turn an unknown site into a matching one. Nothing
    here claims the raw spelling reaches a message - it cannot, because no
    escalation is emitted; it is kept so an unknown site is never silently
    renamed to None if this ever grows a branch that does emit."""
    row = {"date": "2030-05-01", "pain": 3, "pain_site": "elbow-of-doom"}
    assert escalations([], [row], [], []) == []


def test_a_gate_names_the_site_by_its_slug_not_by_its_spelling():
    """A DELIBERATE behaviour change, recorded because it is one.

    Canonicalising on the safety path applies the registry there for the first
    time, so an existing record writing `IT band` sees its gate slug move from
    `pain:IT band` to `pain:knee`. No gate appears or disappears - firing turns
    on the score, which this never touches - but the identity a consumer keys
    on changes, and the rollup prose already normalised, so the two now agree
    where before they did not."""
    row = {"date": "2030-05-01", "pain": 5, "pain_site": "IT band"}
    gates = gates_on([], "2030-05-01", pain_gate=2, daily=[row], checks=[])
    assert [g["slug"] for g in gates] == ["pain:knee"]
    assert "at knee" in gates[0]["reason"]


def test_a_painful_row_with_no_site_is_not_given_the_retired_field_s_joint():
    """The last fossil of the retirement, on the prose side. A score with no
    site is invalid and reported, but it still loads - and the report defaulted
    it to `hip`, naming a body part the record never did, while the gate two
    lines away said `unspecified site`."""
    from vitai.config import Config
    from vitai.report import build_report
    row = {"date": "2030-05-01", "pain": 5, "pain_site": None}
    out = build_report(Config(pain_gate=2), [], [row], [], today=TODAY)
    assert "at unspecified site" in out
    assert "at hip" not in out
