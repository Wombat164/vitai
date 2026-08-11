"""An absence is not ambiguous once a build says what it could emit (#335).

The core install is dependency-free and route work ships as an optional extra
(#23), so a row enriched by the extra carries fields a core install cannot
produce. A consumer meeting an absent field then has two readings and no way
to choose, which is the ambiguity this engine refuses everywhere else.

Two questions, and the tests are organised around the fact that only the first
is answerable: what the install in front of you can produce, and what the
build that wrote some older row could produce. Nothing on an ordinary row says
which build wrote it, so the second answers `unknown`, on purpose and loudly.
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from vitai import builds as B
from vitai.api import schema


# No extra exists yet, so `not_installed` is unreachable from the shipped
# data. That is not a reason to leave the branch untested: it is the branch
# the whole issue is about, and #23 will be written against it. The registry
# is supplied as data here rather than asserted from the file.
WITH_AN_EXTRA = {
    "extras": {"route": {"fields": ["surface", "named_way"]}},
    "builds": {
        "1.0.0": {"ships": ["route"]},
        "0.9.0": {"ships": []},
    },
}


@pytest.fixture
def with_an_extra(monkeypatch):
    monkeypatch.setattr(B, "_data", lambda: WITH_AN_EXTRA)


# --- the registry ships honest ----------------------------------------------

def test_the_reading_install_is_covered_by_the_registry():
    """BACK-PRESSURE ON THE VERSION BUMP, and the reason this test exists at
    all. A registry that does not list the build shipping it cannot answer the
    one question it is guaranteed to be asked - what can the install in front
    of me do - and would return `unknown` about itself. Releasing without
    adding an entry is the way that happens, so it fails here instead."""
    assert B.this_build() in B.builds()


def test_no_extra_is_declared_before_it_exists():
    """The route extra is not built. Declaring it here would make the registry
    assert a capability the engine does not have, which is the failure the
    file exists to prevent. When #23 lands this test changes with it."""
    assert B.extras() == {}
    assert B.builds()[B.this_build()] == []


def test_what_it_publishes_is_a_copy(with_an_extra):
    """Against a NON-EMPTY registry, which is the only way this can fail. The
    first version used the shipped data, where every `ships` list is empty -
    and `[] or []` yields the second literal, a fresh list every call, so
    handing back the cached one was undetectable. `registry` is lru_cached, so
    the aliasing would have been real and permanent for the process."""
    B.extras()["route"].append("invented_field")
    B.builds()["1.0.0"].append("invented_extra")
    B.extras()["invented_extra_entirely"] = ["x"]

    assert B.extras() == {"route": ["surface", "named_way"]}
    assert B.builds()["1.0.0"] == ["route"]
    assert B.owner("invented_field") is None


# --- the answerable question ------------------------------------------------

def test_this_build_can_emit_a_core_field():
    assert B.can_emit("rhr") == "yes"
    assert B.can_emit("rhr", B.this_build()) == "yes"


def test_a_build_the_registry_does_not_cover_answers_unknown():
    """Not "no". A build nobody recorded is a build nobody knows about, and
    saying "no" would assert an incapacity from silence."""
    assert B.can_emit("rhr", "0.1.0") == B.UNKNOWN
    assert B.absence("rhr", "0.1.0") == B.UNKNOWN


def test_a_covered_build_makes_not_measured_sayable():
    assert B.absence("rhr", B.this_build()) == B.NOT_MEASURED


# --- the unanswerable one ---------------------------------------------------

def test_an_unknown_writer_does_not_silently_become_the_reader():
    """`can_emit` defaults to the install doing the reading, which is the
    useful single-install case. `absence` must NOT: answering about the build
    in front of you, for a row an older build wrote, is exactly the wrong
    inference the issue exists to prevent."""
    assert B.absence("rhr", None) == B.UNKNOWN
    with pytest.raises(TypeError):
        B.absence("rhr")


def test_nothing_on_a_row_says_which_build_wrote_it():
    """Including a row that carries `derived_build`. That field names the
    build that DERIVED a value on a `derived_external` row, which is a
    different fact from what the writer was capable of - and reading it as
    this would be a confident wrong answer on the one row in the corpus that
    has one."""
    assert B.writing_build({}) is None
    assert B.writing_build({"derived_build": "0.4.0",
                            "derived_by": "somebody else"}) is None


# --- the extra path, which the shipped registry cannot witness --------------

# No extra exists yet, so `not_installed` is unreachable from the shipped
# data. That is not a reason to leave the branch untested: it is the branch
# the whole issue is about, and #23 will be written against it. The registry
# is supplied as data here rather than asserted from the file.
def test_a_build_that_ships_the_extra_could_have_measured_it(with_an_extra):
    assert B.can_emit("surface", "1.0.0") == "yes"
    assert B.absence("surface", "1.0.0") == B.NOT_MEASURED


def test_a_build_without_the_extra_could_not(with_an_extra):
    """The case the issue was raised for: the absence means the install could
    not produce the value, not that the value was not there to produce."""
    assert B.can_emit("surface", "0.9.0") == "no"
    assert B.absence("surface", "0.9.0") == B.NOT_INSTALLED


def test_a_core_field_is_unaffected_by_an_extra_existing(with_an_extra):
    for build in ("1.0.0", "0.9.0"):
        assert B.can_emit("rhr", build) == "yes"
        assert B.absence("rhr", build) == B.NOT_MEASURED


def test_the_three_readings_are_distinct(with_an_extra):
    """`not_measured`, `not_installed` and `unknown` must not collapse onto
    each other - collapsing them is the defect, not a tidy-up."""
    got = {B.absence("surface", "1.0.0"),
           B.absence("surface", "0.9.0"),
           B.absence("surface", "0.0.1")}
    assert got == {B.NOT_MEASURED, B.NOT_INSTALLED, B.UNKNOWN}
    assert set(B.ABSENCE_MEANINGS) == got


def test_owner_routes_a_field_to_the_extra_that_owns_it(with_an_extra):
    assert B.owner("surface") == "route"
    assert B.owner("named_way") == "route"
    assert B.owner("rhr") is None


# --- P9: the same answer on every surface -----------------------------------

def test_the_registry_reaches_the_published_schema(with_an_extra):
    """Against a non-empty registry too. Comparing the published block to
    `extras()` while both are empty is an identity that holds however the
    block is built - replacing it with a literal `{}` passed."""
    got = schema()["builds"]
    assert got["this"] == B.this_build()
    assert got["extras"] == {"route": ["surface", "named_way"]}
    assert got["released"] == {"1.0.0": ["route"], "0.9.0": []}
    assert got["absence_meanings"] == list(B.ABSENCE_MEANINGS)


def test_the_published_block_matches_what_the_engine_ships():
    got = schema()["builds"]
    assert got["extras"] == B.extras()
    assert got["released"] == B.builds()


def test_the_question_reaches_the_cli():
    from vitai.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["can-emit", "rhr", "--build", B.this_build(), "--json"])
    assert json.loads(buf.getvalue()) == {
        "field": "rhr", "build": B.this_build(),
        "can_emit": "yes", "absence_means": B.NOT_MEASURED}


def test_the_cli_says_unknown_rather_than_answering_about_itself():
    """Without `--build` the row's writer is unknown, and the human-readable
    line has to say so - a consumer reading "can emit -> yes" and taking it
    for an answer about a row is the whole failure mode."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        from vitai.cli import main
        main(["can-emit", "rhr"])
    out = buf.getvalue()
    assert "unknown" in out
    assert "which build wrote that row" in out


def test_the_question_reaches_the_agent_surface(tmp_path):
    from vitai.mcp import TOOLS, call

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")
    assert call(root, "can_emit", {"field": "rhr"}) == "yes"
    assert call(root, "can_emit", {"field": "rhr", "build": "0.1.0"}) == B.UNKNOWN
    assert set(TOOLS["can_emit"]["properties"]) == {"field", "build"}

    assert call(root, "absence", {"field": "rhr", "build": None}) == B.UNKNOWN
    assert call(root, "absence", {"field": "rhr",
                                  "build": B.this_build()}) == B.NOT_MEASURED


def test_the_agent_must_say_which_build_it_means(tmp_path):
    """`build` is required on `absence` and optional on `can_emit`, which is
    the difference between the two questions. An agent that omits it gets an
    error rather than a confident answer about the wrong build."""
    from vitai.mcp import TOOLS, call

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")

    assert TOOLS["absence"]["required"] == ["field", "build"]
    assert "required" not in TOOLS["can_emit"] or \
        TOOLS["can_emit"]["required"] == ["field"]
    with pytest.raises(TypeError):
        call(root, "absence", {"field": "rhr"})


def test_a_rootless_tool_answers_as_itself_not_as_schema(tmp_path):
    """`method: None` was documented as "a module-level function of the same
    name" and implemented as "return schema()". It cost nothing while `schema`
    was the only rootless tool; the second one would have silently answered as
    the first."""
    from vitai.mcp import TOOLS, call

    root = tmp_path / "content"
    (root / "data").mkdir(parents=True)
    (root / "vitai.toml").write_text('[athlete]\nname = "T"\n', encoding="utf-8")

    rootless = {name for name, spec in TOOLS.items() if spec["method"] is None}
    assert rootless == {"schema", "can_emit", "absence"}, rootless
    for name in ("can_emit", "absence"):
        args = {"field": "rhr"} | ({"build": None} if name == "absence" else {})
        assert call(root, name, args) != call(root, "schema", {})
