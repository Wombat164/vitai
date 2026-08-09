"""Field types are public, and the things that duplicate a fact agree (#257).

`KEYS` was public and the types were not, so a consumer building a queryable
projection could check its column NAMES against the engine and had to guess or
copy everything else. One copied, and the copy went several increments stale:
nine fields were in the record and reached no query, with nothing reporting a
problem because from the engine's side nothing was wrong.

Half a derivation is not a derivation. These tests hold the published half
honest, and pin the three places where one fact is written down twice.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from vitai.api import field_types, schema
from vitai.db import LIST_COLS, _TEXT_COLS, column_affinity
from vitai.schema import KEYS

ROOT = Path(__file__).resolve().parents[1]


# ---- the accessor answers what a projection needs ---------------------------

def test_every_dataset_and_field_is_covered():
    """A field missing here is one a consumer cannot type, and it would be
    missing silently - which is the defect, not a gap in it."""
    types = field_types()
    assert set(types) == set(KEYS)
    for dataset, fields in types.items():
        assert set(fields) == set(KEYS[dataset]), dataset


def test_each_entry_answers_every_question_a_consumer_was_guessing_at():
    """The list grows by one each time a client is caught keeping its own copy.

    `coarse_companion` joined at #205: a field with one has no column in the
    read model and is absent from every default projection, so an accessor a
    consumer builds its projection from has to say which fields those are.
    `sensitivity` joined at #299, after a client's hand-written egress map gave
    an unknown field the most permissive class. `units` and `aliases` join at
    #310, after a hand-written unit map and a hand-written English one - the
    second of which failed silently, routing a question about steps to a pack
    of goals. `display_name` joins at #331: a client had `aliases` and `units`
    and still had nothing to PRINT, so it softened the field name's
    underscores and showed "kcal in".
    """
    for dataset, fields in field_types().items():
        for name, spec in fields.items():
            assert set(spec) == {"types", "affinity", "container",
                                 "coarse_companion", "sensitivity",
                                 "units", "aliases",
                                 "display_name"}, f"{dataset}.{name}"
            assert spec["affinity"] in {"TEXT", "REAL"}
            assert isinstance(spec["container"], bool)
            assert spec["coarse_companion"] is None or (
                spec["coarse_companion"] in KEYS[dataset]), f"{dataset}.{name}"


def test_an_unconstrained_field_says_so_rather_than_guessing():
    """`None` means the engine constrains nothing. A consumer must be able to
    tell that from a field constrained to strings, because inventing a
    constraint is how a valid row gets rejected."""
    assert field_types("daily")["daily"]["note"]["types"] is None
    assert field_types("daily")["daily"]["steps"]["types"] == ["integer"]


def test_a_numeric_field_reads_as_number_not_as_two_python_classes():
    """`(int, float)` is an implementation detail of a Python validator. The
    consumers that need this most are not in Python (#257)."""
    assert field_types("weight")["weight"]["kg"]["types"] == ["number"]


def test_it_can_be_asked_for_one_dataset():
    one = field_types("sessions")
    assert set(one) == {"sessions"}


def test_an_unknown_dataset_raises_rather_than_returning_empty():
    """An empty dict reads as 'this dataset has no fields', which is a
    different and much more damaging answer than 'no such dataset'."""
    try:
        field_types("not_a_dataset")
    except KeyError as e:
        assert "not_a_dataset" in str(e)
    else:
        raise AssertionError("expected KeyError")


# ---- container declaration is checked in both directions --------------------

def test_every_list_column_is_text():
    """A JSON array under REAL affinity is mangled, so the two declarations
    cannot drift apart without corrupting the column."""
    assert LIST_COLS <= _TEXT_COLS


def test_every_field_observed_holding_a_list_is_declared_a_container():
    """The register direction that catches a NEW list field. Without it,
    `container` would be a hand-kept set - the very thing #257 is about."""
    seen: set[str] = set()
    for path in (ROOT / "examples").rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.update(k for k, v in rec.items() if isinstance(v, list))
    undeclared = seen - set(LIST_COLS)
    assert not undeclared, (
        f"fields hold a list in the fixtures but are not in LIST_COLS: "
        f"{sorted(undeclared)}. A consumer will read them as a scalar and "
        f"drop the field rather than fail."
    )


def test_the_container_flag_agrees_with_the_declaration():
    types = field_types()
    flagged = {f for ds in types.values() for f, spec in ds.items() if spec["container"]}
    assert flagged == {c for c in LIST_COLS if any(c in KEYS[d] for d in KEYS)}


def test_affinity_matches_the_projection_the_engine_actually_builds():
    for dataset, fields in field_types().items():
        for name, spec in fields.items():
            assert spec["affinity"] == column_affinity(name), f"{dataset}.{name}"


# ---- the accessor reaches every surface (P9) --------------------------------

def test_the_shape_accessor_carries_the_fields():
    assert schema()["fields"] == field_types()


def test_the_whole_shape_is_json_transportable():
    """A connector in another language is the consumer this exists for."""
    assert json.loads(json.dumps(schema())) == schema()


def test_the_cli_json_surface_carries_it():
    r = subprocess.run([sys.executable, "-m", "vitai.cli", "schema", "--json"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["fields"] == field_types()


def test_the_human_surface_says_the_data_exists():
    """A capability reachable only through --json is one a reader never learns
    about."""
    r = subprocess.run([sys.executable, "-m", "vitai.cli", "schema"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "fields" in r.stdout


# ---- one number, written down twice, now checked ----------------------------

def test_the_package_version_matches_pyproject():
    """`__version__` is `schema()['engine']`, `vitai --version`, and the MCP
    server's reported version. Its ONLY job is to be accurate about which
    engine is running, and it was wrong: the 0.5.0 release bumped
    `pyproject.toml` and left the constant at 0.4.0, so every one of those
    three reported the previous release.
    """
    from vitai import __version__
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, re.M)
    assert m, "pyproject has no version"
    assert __version__ == m.group(1), (
        f"__version__ is {__version__} and pyproject says {m.group(1)}"
    )
