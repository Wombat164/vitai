"""An unpinned reading is CAUGHT, not only made visible (#371).

The issue's own follow-up comment settles the shape tightly and this test
file follows it line for line:

- ONLY where a protocol for that dataset EXISTS in the record - and because a
  `protocols` row does not say which dataset it governs (see
  `KEYS["protocols"]`), "exists for this dataset" has to be read off the
  dataset itself: the slugs its own rows have actually named. A record that
  has never named a protocol in `weight` has nothing to be missing there,
  even if `protocols.jsonl` carries a row for something else entirely.
- ADVISORY, never a refusal - `validate()["problems"]` must stay untouched
  and `ok` must stay true. A reading taken under unknown conditions is still
  true; refusing it would lose it, which is worse than holding it unpinned.
- Scoped to rows written ON OR AFTER the protocol was declared. A reading
  from before the declaration could not have named a procedure that did not
  exist yet, and flagging it would be noise on exactly the rows that were
  never wrong.

THE CORPUS GAP THIS FILE WORKS AROUND: no persona fixture shipped in this
repo has a mixed pinned/unpinned weight series to exercise the sharp case
against - three personas are 100% pinned and the rest are 0%. Modifying a
persona fixture to manufacture one would regenerate the corpus, which is a
separate change, so every record below is built from scratch in a temp dir.
"""

from __future__ import annotations

import json
from pathlib import Path

from vitai.api import Vitai
from vitai.schema import KEYS, protocol_pin_advisories


def weigh(day: str, kg: float, protocol=None, source="scale") -> dict:
    """One `weight` row, every key from `KEYS` present so no generation or
    unknown-key problem can fire - mirrors `test_protocol_seam.py`."""
    return {**{k: None for k in KEYS["weight"]}, "date": day, "kg": kg,
            "source": source, "protocol": protocol,
            "recorded_at": f"{day}T07:00:00+01:00"}


def measure(day: str, kind: str, value: float, protocol=None,
           source="tape") -> dict:
    """One `measurements` row, same fill-from-KEYS discipline."""
    return {**{k: None for k in KEYS["measurements"]}, "date": day,
            "kind": kind, "value": value, "protocol": protocol,
            "source": source, "recorded_at": f"{day}T07:00:00+01:00"}


def protocol(day: str, slug: str, text="the procedure") -> dict:
    """One `protocols` row - declares a slug, names nothing about which
    dataset it governs, per `KEYS["protocols"]`."""
    return {**{k: None for k in KEYS["protocols"]}, "date": day, "slug": slug,
            "text": text, "recorded_at": f"{day}T07:00:00+01:00"}


def build(tmp_path: Path, **files: list[dict]) -> Vitai:
    """A content repo with only the dataset files named in `files` written -
    every other dataset's file is simply absent, which `stream_paths` treats
    as zero rows rather than an error."""
    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    for name, rows in files.items():
        (root / "data" / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return Vitai(root)


def _advisory_for(advisories: list[str], filename: str) -> str | None:
    matches = [a for a in advisories if a.startswith(filename)]
    assert len(matches) <= 1, f"expected at most one advisory for {filename}, " \
        f"got {matches}"
    return matches[0] if matches else None


# --- the sharp case: mixed, after declaration, advises -----------------------

def test_mixed_series_after_declaration_advises(tmp_path):
    rows = [
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-06-02", 70.1, None),
        weigh("2030-06-03", 70.2, None),
        weigh("2030-06-04", 70.0, "fasted-post-void"),
        weigh("2030-06-05", 69.9, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    assert result["ok"] is True
    assert not any("protocol" in p for p in result["problems"])
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert "3 row(s)" in advisory
    assert "2030-06-02" in advisory and "2030-06-05" in advisory
    assert "fasted-post-void" in advisory
    assert advisory not in result["problems"]


# --- never named in this dataset: silent, even with a protocols row --------

def test_never_named_in_dataset_is_silent_even_with_a_protocols_row(tmp_path):
    # protocols.jsonl declares a slug, but not one single weight row ever
    # names it (or any other slug). The declaration exists "for something
    # else" - the record just never says what, because a protocols row
    # cannot say what - and weight must stay silent regardless.
    rows = [weigh("2030-06-02", 70.1, None),
           weigh("2030-06-03", 70.2, None),
           weigh("2030-06-04", 70.0, None)]
    protocols = [protocol("2030-06-01", "some-other-procedure")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    assert result["ok"] is True
    assert _advisory_for(result["advisories"], "weight.jsonl") is None


# --- rows before the declaration are not advised ----------------------------

def test_rows_before_declaration_are_not_advised(tmp_path):
    rows = [
        # Before the protocol existed: cannot have named it, must not count.
        weigh("2030-05-01", 71.0, None),
        weigh("2030-05-02", 71.1, None),
        # The declaration.
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        # After: unpinned rows here DO count.
        weigh("2030-06-02", 70.1, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert "1 row(s)" in advisory
    assert "2030-06-02" in advisory
    # The pre-declaration dates must not appear as flagged rows.
    assert "2030-05-01" not in advisory
    assert "2030-05-02" not in advisory


# --- fully pinned series: silent --------------------------------------------

def test_fully_pinned_series_is_silent(tmp_path):
    rows = [
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-06-02", 70.1, "fasted-post-void"),
        weigh("2030-06-03", 70.2, "fasted-post-void"),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    assert result["ok"] is True
    assert _advisory_for(result["advisories"], "weight.jsonl") is None


# --- advisory, never a problem ----------------------------------------------

def test_advisory_never_a_problem_and_ok_stays_true(tmp_path):
    rows = [
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-06-02", 70.1, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert advisory in result["advisories"]
    assert advisory not in result["problems"]
    assert not any("no 'protocol'" in p for p in result["problems"])
    assert result["ok"] is True


# --- each dataset is scoped independently -----------------------------------

# --- no line-number pointer: the date span is the unambiguous locator ------

def test_advisory_carries_no_line_pointer(tmp_path):
    """An earlier version of this advisory named "(first: line N)". `rows` is
    the union across every device file for the dataset (#105), and a line
    number is only unique per FILE - so the pointer could name a file other
    than the one it meant, or (even single-file) a later-dated row than the
    span it was attached to. It is gone; the dated span already reported is
    the unambiguous locator a reader searches by."""
    rows = [
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-06-02", 70.1, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert "line" not in advisory
    assert "first:" not in advisory


# --- gate: no slug named at all -> silence, before protocols is even read --

def test_no_slug_named_anywhere_in_dataset_is_silent(tmp_path):
    """Not one row in the dataset ever names a protocol slug. This is the
    common case (nine of this repo's own personas) and must stay silent
    without even looking at what `protocols.jsonl` declares - a dataset that
    has never named anything has offered no evidence any protocol applies."""
    rows = [weigh("2030-06-01", 70.0, None),
           weigh("2030-06-02", 70.1, None)]
    protocols = [protocol("2020-01-01", "some-unrelated-procedure")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    assert result["ok"] is True
    assert _advisory_for(result["advisories"], "weight.jsonl") is None


# --- gate: a dangling slug alone must not anchor the whole history ---------

def test_dangling_slug_alone_does_not_anchor_the_whole_history(tmp_path):
    """The DANGEROUS gate from review. A slug this dataset names but that
    `protocols.jsonl` never declares anywhere is a typo, or a slug used
    ahead of its own declaration - not evidence any procedure applies. Five
    rows spanning 2020-01-01 to 2024-01-01 name no protocol; the only slug
    this dataset has ever named is dangling. Without this gate, the scope
    would fall through to the dataset's entire history and flag all five -
    exactly "the engine inventing a discipline nobody adopted" the issue's
    decision rules out. This is the shape demonstrated in review: 5 rows,
    2020-01-01 to 2024-01-01, one dangling slug, must stay silent."""
    rows = [
        weigh("2020-01-01", 71.0, "ghost-protocol"),
        weigh("2021-01-01", 70.8, None),
        weigh("2022-01-01", 70.5, None),
        weigh("2023-01-01", 70.2, None),
        weigh("2024-01-01", 70.0, None),
    ]
    protocols = [protocol("2030-01-01", "some-other-procedure")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    assert result["ok"] is True
    assert _advisory_for(result["advisories"], "weight.jsonl") is None


# --- gate: no protocols row at all, not even for an unrelated slug ---------

def test_dangling_slug_with_empty_protocols_file_does_not_anchor(tmp_path):
    """Same gate as above, from the other direction: `protocols.jsonl` does
    not exist at all, so `protocol_rows` is empty. A named slug still cannot
    be REAL without at least one matching declaration anywhere."""
    rows = [
        weigh("2020-01-01", 71.0, "ghost-protocol"),
        weigh("2021-01-01", 70.8, None),
    ]
    v = build(tmp_path, weight=rows)
    result = v.validate()
    assert result["ok"] is True
    assert _advisory_for(result["advisories"], "weight.jsonl") is None


# --- gate: a real slug named only on bad-date rows anchors on nothing ------

def test_real_slug_named_only_on_a_bad_date_row_does_not_crash_or_anchor():
    """Direct call, not through `v.validate()`: this isolates the ONE gate
    that actually has to stop `since = min(...)` from running over an empty
    list. `real` can be non-empty (the slug genuinely has a `protocols` row)
    while no row of THIS dataset names it on a parseable date - here the only
    row naming it has a malformed `date`. `_bad_date` already reports that
    row as its own problem elsewhere (see the docstring on Step 4); this
    function must not additionally blow up computing the anchor."""
    rows = [
        (1, {**{k: None for k in KEYS["weight"]}, "date": "not-a-date",
             "kg": 70.0, "source": "scale", "protocol": "fasted-post-void",
             "recorded_at": "2030-06-01T07:00:00+01:00"}),
        (2, {**{k: None for k in KEYS["weight"]}, "date": "2030-06-02",
             "kg": 70.1, "source": "scale", "protocol": None,
             "recorded_at": "2030-06-02T07:00:00+01:00"}),
    ]
    protocol_rows = [
        (1, {**{k: None for k in KEYS["protocols"]}, "date": "2030-06-01",
             "slug": "fasted-post-void", "text": "the procedure",
             "recorded_at": "2030-06-01T07:00:00+01:00"}),
    ]
    assert protocol_pin_advisories("weight", rows, protocol_rows) == []


# --- anchor: this dataset's own adoption, not an unrelated slug's --------

def test_anchor_is_not_dragged_back_by_an_unrelated_later_adopted_slug(tmp_path):
    """The over-reach demonstrated in review. `weight` names `proto-a` (its
    own practice, first used and declared 2030-06-01) and, much later, also
    names `proto-b` - which happens to have been declared 2020-01-01, for
    something else entirely. The OLD anchor (earliest DECLARATION date
    across every slug ever named) was 2020-01-01, and it flagged the
    2021-03-01 row - six years before `weight` had named anything at all.
    The anchor must be `weight`'s OWN first use of a real slug (2030-06-01),
    so only the 2031-01-01 row - after that, unpinned - is advised."""
    rows = [
        weigh("2021-03-01", 71.5, None),
        weigh("2030-06-01", 70.0, "proto-a"),
        weigh("2031-01-01", 69.9, None),
        weigh("2032-01-01", 69.8, "proto-b"),
    ]
    protocols = [protocol("2030-06-01", "proto-a"),
                protocol("2020-01-01", "proto-b")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert "1 row(s)" in advisory
    assert "2031-01-01" in advisory
    assert "2021-03-01" not in advisory
    assert "since 2030-06-01" in advisory


# --- composition: one real slug + one ghost slug anchors on the real one ---

def test_real_and_ghost_slug_together_anchor_on_the_real_ones_own_adoption(
        tmp_path):
    """Both gates at once, composed: a dataset naming one REAL slug (declared,
    and actually used here since 2030-06-01) and one GHOST slug (named here,
    never declared anywhere) must anchor on the real slug's own adoption -
    not fall through to silence because a slug is dangling, and not get
    pulled back to year one because a slug is dangling either."""
    rows = [
        weigh("2029-06-01", 71.0, None),
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-07-01", 69.8, "ghost-protocol"),
        weigh("2030-06-02", 70.1, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void")]
    v = build(tmp_path, weight=rows, protocols=protocols)
    result = v.validate()
    advisory = _advisory_for(result["advisories"], "weight.jsonl")
    assert advisory is not None
    assert "1 row(s)" in advisory
    assert "2030-06-02" in advisory
    assert "since 2030-06-01" in advisory
    assert "2029-06-01" not in advisory
    assert "0001-01-01" not in advisory
    assert "ghost-protocol" not in advisory


def test_datasets_are_scoped_independently(tmp_path):
    """`weight` fully pinned (silent) while `measurements` is mixed under its
    own, differently-named protocol (advises) - proves the derivation runs
    per dataset rather than once over the record, and that one dataset's
    protocol usage cannot leak a scope into the other."""
    weight_rows = [
        weigh("2030-06-01", 70.0, "fasted-post-void"),
        weigh("2030-06-02", 70.1, "fasted-post-void"),
    ]
    measurement_rows = [
        measure("2030-07-01", "waist_cm", 82.0, "morning-tape"),
        measure("2030-07-02", "waist_cm", 82.5, None),
    ]
    protocols = [protocol("2030-06-01", "fasted-post-void"),
                protocol("2030-07-01", "morning-tape")]
    v = build(tmp_path, weight=weight_rows, measurements=measurement_rows,
             protocols=protocols)
    result = v.validate()
    assert _advisory_for(result["advisories"], "weight.jsonl") is None
    m_advisory = _advisory_for(result["advisories"], "measurements.jsonl")
    assert m_advisory is not None
    assert "1 row(s)" in m_advisory
    assert "2030-07-02" in m_advisory
