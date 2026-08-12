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
from vitai.schema import KEYS


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
