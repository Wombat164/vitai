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
sys.path.insert(0, str(PERSONAS))
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
        # THE DATASET IS THE STEM BEFORE THE FIRST DOT, not the whole stem.
        # `daily.old-band.jsonl` is one of #105's per-device streams and holds
        # `daily` rows; taking `path.stem` whole asked the schema about a
        # dataset called `daily.old-band` and raised `KeyError`. Nothing had
        # noticed because no persona used a second stream until `hana`, whose
        # one-time archive import is a second writer by nature - which is the
        # shape #405 is about, and it could not have been fixtured without
        # hitting this.
        dataset = path.name.split(".", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            problems = validate_record(dataset, rec)
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


@pytest.mark.parametrize("slug", slugs())
def test_persona_toml_is_the_asserted_identity(slug: str) -> None:
    """docs/persona-doctrine.md: three things drift and they are not one
    version. persona.toml is the machine-readable statement of all three,
    and tests assert on it rather than trusting prose."""
    import importlib
    import tomllib

    meta = tomllib.loads(
        (PERSONAS / slug / "persona.toml").read_text(encoding="utf-8"))
    mod = importlib.import_module(f"_gen.{slug}")

    assert meta["persona"]["slug"] == slug
    assert meta["persona"]["version"] == mod.PERSONA_VERSION >= 1
    assert meta["persona"]["seed"] == mod.SEED

    dates = sorted(
        json.loads(line)["date"]
        for path in (PERSONAS / slug / "data").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    assert meta["persona"]["span"] == [dates[0], dates[-1]]

    from _gen import common
    assert meta["schema"]["contract"] == common.AUTHORED_AGAINST_CONTRACT
    assert meta["schema"]["generations"] == common.AUTHORED_AGAINST_GENERATIONS


@pytest.mark.parametrize("slug", slugs())
def test_findings_attribute_a_persona_version(slug: str) -> None:
    """A finding that does not name the persona version that exposed it
    cannot be checked later for whether the evidence still exists."""
    text = (PERSONAS / slug / "FINDINGS.md").read_text(encoding="utf-8")
    import tomllib

    meta = tomllib.loads(
        (PERSONAS / slug / "persona.toml").read_text(encoding="utf-8"))
    tag = f"{slug}@{meta['persona']['version']}"
    assert tag in text, (
        f"{slug}/FINDINGS.md never cites {tag}; findings must record the "
        f"persona version that exposed them"
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


# --- stefan: the confabulation persona ----------------------------------------
#
# One month of severely degraded data whose cause never enters the record.
# The ground truth is knowable to these tests (expectations stefan-E0) and
# never to the engine; the critical assertion is negative. See
# tests/fixtures/personas/stefan/FINDINGS.md.

# Words that would each constitute a stated cause if they appeared in
# stefan's engine-visible record. The true cause's vocabulary is included:
# the record must not know it, in any words.
STEFAN_RECORD_LEAK_WORDS = (
    "died", "death", "grief", "bereave", "funeral", "mourn", "condolence",
    "widow", "orphan",
)


def _stefan_banned_attributions() -> tuple[str, ...]:
    import importlib

    return importlib.import_module("_gen.stefan").BANNED_ATTRIBUTIONS


def test_stefan_record_never_states_the_cause() -> None:
    """The asymmetry is the fixture: the cause exists in expectations.jsonl
    and FINDINGS/LIES (test-side), and nowhere the engine or a reader of
    the record's own documents can see."""
    root = PERSONAS / "stefan"
    engine_visible = sorted((root / "data").glob("*.jsonl")) + [
        root / "vitai.toml", root / "PROFILE.md", root / "WORLD.md",
        root / "METRICS.md",
    ]
    for path in engine_visible:
        text = path.read_text(encoding="utf-8").lower()
        for word in STEFAN_RECORD_LEAK_WORDS:
            assert word not in text, (
                f"{path.name} leaks the cause into the record: {word!r}"
            )


def test_stefan_outputs_attribute_no_cause(tmp_path: Path) -> None:
    """Build with full knowledge and scan every engine output, prose and
    database alike, for any attributed cause. The engine refusing to fill
    the silence is the entire fixture; one banned word anywhere fails."""
    src = PERSONAS / "stefan"
    work = tmp_path / "stefan"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("derived"))
    Vitai(work).build()
    banned = _stefan_banned_attributions()

    weekly = (work / "derived" / "weekly.md").read_text(
        encoding="utf-8").lower()
    for word in banned:
        assert word not in weekly, f"weekly.md attributes a cause: {word!r}"

    con = sqlite3.connect(work / "derived" / "health.db")
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({table})")]
            for row in con.execute(f"SELECT * FROM {table}"):
                for col, val in zip(cols, row):
                    if not isinstance(val, str):
                        continue
                    low = val.lower()
                    for word in banned:
                        assert word not in low, (
                            f"{table}.{col} attributes a cause: {word!r} "
                            f"in {val!r}"
                        )
    finally:
        con.close()


def test_stefan_tripwires_describe_the_degradation(tmp_path: Path) -> None:
    """Behaviour 1: evaluated inside the silent month, the engine states
    the resting-rate excess and the sleep-floor breach as observations
    about the record, which is exactly the register the medical boundary
    allows and the only description this fixture requires."""
    from datetime import date as _date

    src = PERSONAS / "stefan"
    work = tmp_path / "stefan"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("derived"))
    Vitai(work).build(today=_date(2030, 4, 10))
    weekly = (work / "derived" / "weekly.md").read_text(encoding="utf-8")
    assert "over baseline" in weekly, "resting-rate tripwire did not fire"
    assert "floor" in weekly, "sleep-floor tripwire did not fire"


def _vitai_supports_as_of() -> bool:
    import inspect

    return "as_of" in inspect.signature(Vitai.__init__).parameters


@pytest.mark.skipif(not _vitai_supports_as_of(),
                    reason="knowledge cutoff (as_of, #131) not merged yet")
def test_stefan_epochs_divide_what_was_knowable(tmp_path: Path) -> None:
    """Epoch-keyed assertions per #130: during the silence, the disclosure
    does not exist and no output may attribute; after it, the record's own
    words exist and the outputs still must not explain March."""
    from datetime import datetime as _dt

    src = PERSONAS / "stefan"
    banned = _stefan_banned_attributions()
    t1 = _dt.fromisoformat("2030-04-10T20:00:00+02:00")
    t2 = _dt.fromisoformat("2030-06-29T20:00:00+02:00")

    for label, cutoff, disclosure_expected in (
            ("during", t1, False), ("after", t2, True)):
        work = tmp_path / f"stefan-{label}"
        shutil.copytree(src, work, ignore=shutil.ignore_patterns("derived"))
        Vitai(work, as_of=cutoff).build()
        con = sqlite3.connect(work / "derived" / "health.db")
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM journal WHERE text LIKE ?",
                ("%Flensburg%",)).fetchone()[0]
        finally:
            con.close()
        assert (n > 0) == disclosure_expected, (
            f"as_of {label}: disclosure visibility wrong (rows={n})"
        )
        weekly = (work / "derived" / "weekly.md").read_text(
            encoding="utf-8").lower()
        for word in banned:
            assert word not in weekly, (
                f"as_of {label}: weekly.md attributes a cause: {word!r}"
            )
