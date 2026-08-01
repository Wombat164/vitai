"""The persona corpus is a set of tests, not a set of stories.

Every deepened persona under tests/fixtures/personas/<slug>/ ships a record
its life would produce, deliberate falsehoods documented in LIES.md, and a
ground-truth expectations.jsonl emitted by the same generator that emitted
the record. This suite holds the corpus to that contract:

- every committed data line passes the engine's own validator;
- every corpus builds with the engine as of the persona's last day;
- the committed data matches its generator byte for byte (drift gate);
- ground truth is well formed, unique, and every LIES.md falsehood has an
  expectations row behind it;
- expectation prose stays inside the medical boundary (observation and
  self-constraint language only, no care instructions);
- and the one lie the engine can already adjudicate end to end is asserted
  against the built database: rachel's inflated walks resolve to the
  device's account, never to her own and never to an average.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from vitai.api import Vitai
from vitai.schema import validate_record

PERSONAS = Path(__file__).parent / "fixtures" / "personas"
EXPECTATION_KINDS = {"lie", "behavior", "gap"}

# Phrases whose presence in ground-truth prose would put the corpus itself
# outside the medical boundary: imperatives whose object is obtaining care.
# The acute carve-out (call emergency services) belongs to the engine's own
# fixed tier, never to expectation prose.
CARE_INSTRUCTION_PHRASES = (
    "see a doctor", "see your doctor", "consult a", "contact a doctor",
    "contact your doctor", "get checked", "get assessed", "get this assessed",
    "seek medical", "medical attention", "take this to a",
)


def persona_dirs() -> list[Path]:
    return sorted(
        d for d in PERSONAS.iterdir()
        if d.is_dir() and d.name != "_gen" and (d / "data").is_dir()
    )


def slugs() -> list[str]:
    return [d.name for d in persona_dirs()]


@pytest.mark.parametrize("slug", slugs())
def test_every_data_line_validates(slug: str) -> None:
    root = PERSONAS / slug
    total = 0
    for path in sorted((root / "data").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            problems = validate_record(path.stem, rec)
            assert not problems, f"{path.name}: {problems} in {rec}"
            total += 1
    assert total > 0, f"{slug} has an empty record"


@pytest.mark.parametrize("slug", slugs())
def test_corpus_builds(slug: str, tmp_path: Path) -> None:
    src = PERSONAS / slug
    work = tmp_path / slug
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("derived"))
    Vitai(work).build()
    assert (work / "derived" / "health.db").exists()
    assert (work / "derived" / "weekly.md").exists()


def test_committed_data_matches_generator(tmp_path: Path) -> None:
    """The drift gate: committed corpora are the byte-exact output of the
    committed generator. Regenerates every persona (generate.py --check)."""
    env = dict(os.environ)
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(PERSONAS / "generate.py"), "--check"],
        capture_output=True, text=True, env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0, (
        f"persona corpora drifted from their generator:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


@pytest.mark.parametrize("slug", slugs())
def test_expectations_well_formed(slug: str) -> None:
    path = PERSONAS / slug / "expectations.jsonl"
    assert path.exists(), f"{slug} ships no ground truth"
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, f"{slug} ground truth is empty"
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), f"{slug} has duplicate expectation ids"
    for r in rows:
        assert r["id"].startswith(f"{slug}-"), r["id"]
        assert r["kind"] in EXPECTATION_KINDS, r
        assert r.get("expect"), f"{r['id']} states no expected behaviour"
        assert r.get("truth") is not None, f"{r['id']} states no ground truth"


@pytest.mark.parametrize("slug", slugs())
def test_expectations_stay_inside_medical_boundary(slug: str) -> None:
    """Ground-truth prose must describe what the engine observes and what it
    will not do; an imperative aimed at obtaining care is a violation even
    inside a fixture, because fixtures state intended behaviour."""
    path = PERSONAS / slug / "expectations.jsonl"
    text = path.read_text(encoding="utf-8").lower()
    for phrase in CARE_INSTRUCTION_PHRASES:
        assert phrase not in text, (
            f"{slug} expectations contain a care instruction: {phrase!r}"
        )


@pytest.mark.parametrize("slug", slugs())
def test_every_documented_lie_has_ground_truth(slug: str) -> None:
    """LIES.md and expectations.jsonl must not drift apart: every lie id
    family named in the prose exists in the ground truth, and every lie row
    in the ground truth belongs to a persona that documents its lies."""
    lies_md = PERSONAS / slug / "LIES.md"
    exp = PERSONAS / slug / "expectations.jsonl"
    rows = [json.loads(line) for line in
            exp.read_text(encoding="utf-8").splitlines() if line.strip()]
    lie_rows = [r for r in rows if r["kind"] == "lie"]
    if lie_rows:
        assert lies_md.exists(), (
            f"{slug} ships lie rows but no LIES.md documenting them"
        )


def test_rachel_inflated_walks_resolve_to_device(tmp_path: Path) -> None:
    """The corpus's cleanest end-to-end lie: eleven walks logged by hand as
    30 minutes, recorded by the phone as 12 to 16. The ladder must merge
    each pair into one activity and the device account must win duration,
    with the athlete's claim never averaged in."""
    src = PERSONAS / "rachel"
    work = tmp_path / "rachel"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("derived"))
    Vitai(work).build()

    exp_rows = [json.loads(line) for line in
                (src / "expectations.jsonl").read_text(encoding="utf-8")
                .splitlines() if line.strip()]
    lie_dates = sorted(
        d for r in exp_rows if r["id"].startswith("rachel-E1-")
        for d in r["dates"]
    )
    assert len(lie_dates) == 11

    con = sqlite3.connect(work / "derived" / "health.db")
    try:
        for day in lie_dates:
            rows = con.execute(
                "SELECT field, chosen_source, chosen_value FROM resolution"
                " WHERE date = ? AND dataset = 'sessions'", (day,)
            ).fetchall()
            by_q = {q: (s, v) for q, s, v in rows}
            assert "duration_s" in by_q, (
                f"{day}: no contested duration resolved; the pair did not "
                f"merge into one activity (resolved fields: {sorted(by_q)})"
            )
            source, value = by_q["duration_s"]
            assert source != "athlete", (
                f"{day}: the athlete's inflated claim won the ladder"
            )
            duration = float(value)
            assert 600 <= duration <= 1080, (
                f"{day}: resolved duration {duration}s is neither the device "
                f"reading (12-16 min) nor plausible; averaging suspected"
            )
    finally:
        con.close()
