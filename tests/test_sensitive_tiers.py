"""Two tiers, and the coarse one is what leaves (#205).

The old stance was privacy by not storing the thing: `place` was documented as
coarse and never an address. Blunt, and it throws away real utility, because
"outdoors" cannot tell the park an athlete likes from the one they avoid. So
the precise tier becomes storable, `place` keeps its name and its meaning, and
everything that leaves sees the coarse value unless something named a release.

THE CLAIM THIS RAISES, and the reason these tests are heavier than a new
field's usually are. Not storing a precise value is safe because there is
nothing to leak. Storing one moves the claim from "we do not hold this" to
"we hold it and it does not escape" - a much stronger claim, and one that has
to actually hold, in every surface, including the ones nobody thought about.
A precise value that leaks cannot be un-leaked.

So the load-bearing test here is not any single assertion about `place`. It is
`test_no_public_surface_emits_the_precise_tier`, which enumerates the public
API rather than naming the methods a person remembered, and fails when method
twenty-six arrives. #205's first commitment is that a gate implemented per
caller will be correct in the callers somebody remembered; a test written per
caller has the identical defect.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from vitai import mcp
from vitai.api import Vitai, init
from vitai.db import CONTRACT_VERSION
from vitai.schema import (KEYS, PRECISE_KEYS, REDACTED, SENSITIVE, coarse,
                          precise_keys, validate_record)

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
# The one the shipped record carries. Named once so a fixture rename cannot
# leave these tests quietly checking for a string nothing writes.
LEAK = "Example Fitness, 3 Sample Road"


def _session(**kw) -> dict:
    rec = {k: None for k in KEYS["sessions"]}
    rec.update({"date": "2030-05-01", "type": "run", "distance_km": 5.0,
                "source": "watch", "_gen": 1})
    rec.update(kw)
    return rec


def _record(tmp_path: Path) -> Vitai:
    v = Vitai(init(tmp_path / "content"))
    v.append("sessions", {"date": "2030-05-01", "type": "run",
                          "distance_km": 5.0, "source": "watch",
                          "place": "home", "place_precise": LEAK})
    return v


# --- the classification -------------------------------------------------------

def test_a_precise_value_needs_a_coarse_answer_beside_it():
    """The invariant the whole design rests on: a coarse answer exists for
    every precise one, so no read path can be left with nothing to show."""
    problems = validate_record(
        "sessions", _session(place_precise="12 Example Street"))

    assert any("needs 'place'" in p for p in problems), problems
    assert validate_record("sessions", _session(
        place_precise="12 Example Street", place="home")) == []


def test_the_coarse_tier_alone_is_still_a_complete_row():
    """Nothing here makes the precise tier compulsory. An athlete who never
    wants to write one is not now writing an incomplete record."""
    assert validate_record("sessions", _session(place="home")) == []
    assert validate_record("sessions", _session()) == []


def test_an_old_line_carrying_a_precise_value_still_owes_the_coarse_one():
    """THE GENERATION GUARD IS DELIBERATELY ABSENT, and this is the row that
    decides it. Every other new key gets the G25 skip - an older line never
    owed it - and that skip is exactly wrong here, because the rule fires only
    when the precise field HAS A VALUE, and a line carrying one was written by
    something that knew the field existed. With the guard, a writer stamping
    an old `_gen` could file an address with no coarse answer and pass, which
    is the one row this rule exists to refuse."""
    problems = validate_record(
        "sessions", _session(_gen=1, place_precise="12 Example Street"))

    assert any("needs 'place'" in p for p in problems), problems


def test_g25_still_holds_for_a_line_that_never_had_the_field():
    """The half the missing guard must not have broken."""
    old = _session(_gen=1)
    old.pop("place_precise", None)

    assert validate_record("sessions", old) == []


def test_the_classification_is_on_the_field_and_not_the_dataset():
    """#205's shape: sensitivity is a property of the field. Two datasets
    carry the same pair, and neither is sensitive as a whole."""
    assert SENSITIVE["sessions"] == {"place_precise": "place"}
    assert SENSITIVE["context"] == {"place_precise": "place"}
    assert precise_keys("sessions") == ("place_precise",)
    assert precise_keys("weight") == ()


def test_the_discovery_surface_says_which_fields_have_no_column():
    """`field_types` is the accessor published so consumers stop guessing at
    the shape, and it described the precise tier as an ordinary column - with
    REAL affinity, for a street address, because the text list had never heard
    of it. A consumer building its own projection from that would have typed
    an address as a number and expected a column that does not exist.

    `coarse_companion` is the entry that says otherwise, and it names the
    field that IS projected rather than being a bare flag, because a consumer
    told only "this is sensitive" still has to guess what to show instead.
    """
    from vitai.api import field_types

    fields = field_types("sessions")["sessions"]

    assert fields["place_precise"]["coarse_companion"] == "place"
    assert fields["place_precise"]["affinity"] == "TEXT"
    assert fields["place"]["coarse_companion"] is None
    assert field_types("weight")["weight"]["kg"]["coarse_companion"] is None


def test_the_key_is_dropped_and_never_nulled():
    """A null is indistinguishable from an athlete who never wrote one, which
    is the difference between "you are not being shown this" and "there is
    nothing here".

    BOTH ROWS, and the second is the one that matters. Checking only the
    populated row let a version that dropped on VALUE rather than on KEY
    PRESENCE pass the whole suite - and the engine writes null for a key it
    does not know rather than omitting it, so the null shape is the one nearly
    every real row carries. Under that version every new-generation row in the
    default projection carried `place_precise: null`, which is the exact state
    this design calls worse than no key.
    """
    populated = coarse("sessions", _session(place="home", place_precise=LEAK))
    empty = coarse("sessions", _session(place="home", place_precise=None))

    assert "place_precise" not in populated
    assert "place_precise" not in empty
    assert populated["place"] == "home"


def test_no_row_of_the_default_projection_carries_the_key_at_all(tmp_path):
    """The same property one level up, over a real record rather than one
    row: not "the value is hidden" but "the key is not there"."""
    v = _record(tmp_path)
    v.append("sessions", {"date": "2030-05-02", "type": "run",
                          "distance_km": 6.0, "source": "watch"})

    rows = v.dataset("sessions")

    assert len(rows) == 2
    assert not [r for r in rows if "place_precise" in r]


def test_a_precise_reader_cannot_write_into_the_default_projection(tmp_path):
    """THE ALIASING HOLE, and "structurally cannot" is what makes it one.

    Coarsening returned the caller's own object when there was nothing to
    drop, so the two caches held THE SAME dicts for every row without a
    precise key - most of any record. A consumer that took the precise view
    and annotated its rows, which is the consumer that path exists for, then
    planted the value into the default projection for every later reader of
    that instance.
    """
    root = init(tmp_path / "content")
    # A LEGACY LINE, written by hand, with the key genuinely absent. The
    # engine writes null for a key it does not know, so a row it appended
    # always carries the key and the aliasing shortcut never fired on one -
    # which is why a test built from `append` alone passed with the shortcut
    # put back. Every line written before the field existed looks like this.
    (root / "data" / "sessions.jsonl").write_text(json.dumps({
        "date": "2030-05-01", "type": "run", "distance_km": 5.0,
        "source": "watch", "place": "home", "_gen": 1}) + "\n",
        encoding="utf-8")
    v = Vitai(root)

    for row in v.precise("sessions", release="an enrichment pass"):
        row["place_precise"] = LEAK

    assert LEAK not in json.dumps(v.dataset("sessions"))
    assert LEAK not in json.dumps(v.situation(), default=str)
    assert not [r for r in v.dataset("sessions") if "place_precise" in r]


def test_coarsening_never_mutates_the_row_it_was_given():
    """The engine's own arithmetic reads the same objects a consumer does, so
    coarsening in place would quietly change what the build computes over."""
    row = _session(place="home", place_precise=LEAK)

    coarse("sessions", row)

    assert row["place_precise"] == LEAK


def test_coarsening_copies_a_dataset_that_has_no_sensitive_field_either():
    """THE BRANCH NEARLY EVERY ROW TAKES, and it was the one not covered.

    `coarse()` documents "ALWAYS A COPY, including when there is nothing to
    drop", and returned the caller's own object whenever the DATASET had no
    sensitive field. Eighteen of the twenty are in that branch, so the
    guarantee held for `sessions` and `context` and was false everywhere else.

    The test above passes either way: it only ever asked about `sessions`. A
    test scoped to the datasets somebody was thinking about has the same defect
    as a gate scoped that way, which is the defect this feature exists to
    abolish.
    """
    row = {"date": "2030-05-01", "kg": 80.0}

    assert "weight" not in SENSITIVE, "this test needs a dataset with no tier"
    assert coarse("weight", row) is not row


def test_the_two_views_never_hand_back_the_same_row_objects():
    """The consequence, rather than the mechanism.

    `precise()` takes any dataset name, so both views of `weight` existed and
    shared all 64 of the demo's rows. A consumer that took the precise view and
    annotated its rows - the consumer this path is built for - wrote into what
    every later reader of the default projection saw, on the same instance.
    """
    v = Vitai(DEMO)

    for name in ("sessions", "weight"):
        default = v.dataset(name)
        exact = v.precise(name, release="test: view identity")
        shared = [a for a, b in zip(default, exact) if a is b]

        assert default, name
        assert not shared, f"{name}: {len(shared)} row objects shared"

    rows = v.precise("weight", release="test: annotate the precise view")
    rows[0]["_written_by_a_consumer"] = True

    assert "_written_by_a_consumer" not in v.dataset("weight")[0]


# --- the boundary -------------------------------------------------------------

def _public_calls(v: Vitai):
    """Every public method that returns something, called with defaults.

    ENUMERATED FROM THE CLASS rather than from a list somebody maintains.
    There is deliberately no roster of method names here: a roster is the
    per-caller pattern #205 exists to abolish, moved into the test file. A
    method added tomorrow is swept in without anybody remembering it, and the
    ones needing arguments are called by name in their own test below.
    """
    for name in sorted(dir(v)):
        if name.startswith("_") or name in ("root", "config", "on", "as_of"):
            continue
        attr = getattr(v, name)
        if not callable(attr):
            continue
        try:
            yield name, attr()
        except TypeError:
            continue                    # needs arguments; covered explicitly
        except Exception:
            continue                    # refuses on this record; nothing left


def test_no_public_surface_emits_the_precise_tier(tmp_path):
    """THE LOAD-BEARING TEST. Twenty-five public methods hand a caller the
    same dict that came off the JSONL line, and a gate implemented per caller
    is correct in the callers somebody remembered. So this does not name them:
    it walks the class, calls everything callable with no arguments, and
    asserts the shipped precise value appears in none of it.

    On a COPY: calling everything includes calling the writers."""
    v = Vitai(demo_copy(tmp_path))
    leaked = []
    for name, out in _public_calls(v):
        if LEAK in json.dumps(out, default=str):
            leaked.append(name)

    assert not leaked, f"the precise tier reached {leaked}"


def test_the_sweep_would_notice(tmp_path):
    """A sweep that called nothing would pass the test above for the wrong
    reason. So this asserts the COARSE partner of the same row comes through
    the same walk.

    The canary is the shipped session's `place` and not the word "gym", which
    also occurs in a context row's `facilities` string - so the first version
    of this was satisfied even if no session row travelled at all.
    """
    v = Vitai(demo_copy(tmp_path))
    coarse_value = [r["place"] for r in v.dataset("sessions")
                    if r.get("place_precise") is None and r.get("place")]
    saw = [name for name, out in _public_calls(v)
           if any(f'"place": "{p}"' in json.dumps(out, default=str)
                  for p in set(coarse_value))]

    assert saw, "the walk reached nothing carrying session rows"


# Methods the sweep cannot call because they need arguments. Every one is
# either exercised by name below or named here as deliberately out of scope,
# so a method added tomorrow that takes an argument FAILS the completeness
# test until somebody decides which it is. Without this, the sweep's own
# `except TypeError: continue` was a silent exemption for half the class -
# which is the per-caller defect this whole change exists to abolish, moved
# into the test file.
ARG_TAKING_COVERED = {"dataset", "day", "derived", "precise", "append",
                      "append_many", "claim", "said",
                      # #311 returns a STORED ROW - the register line itself -
                      # rather than a vocabulary answer the way `capability`
                      # does, so it is covered here rather than excused below.
                      "instrument"}
ARG_TAKING_OUT_OF_SCOPE = {
    # Writes and administration. None return a record row they read back.
    "init", "build", "conform", "implementation", "infer",
    "accept_inferences", "assert_delivery", "artifact", "keep", "pin_policy",
    "add_artifact", "remove_artifact",
    # Computed scalars, strings and vocabulary answers. Where they read rows
    # at all they read them through the door above, so what they return is
    # already coarse; none passes a stored row through.
    # `capability` answers a vocabulary value about an INSTRUMENT (#171):
    # a competence, a construct and a basis. It reads capability rows through
    # `dataset`, which is the door above, and returns no row from a sensitive
    # dataset - the athlete is not in it.
    "capability",
    "check", "window", "ramp", "may", "project", "plan_for", "urgent",
    "safety_banner", "pending_checks", "gated", "session_weeks",
    "contributions", "milestones", "churn", "field_types", "schema",
    "last_recorded", "key", "state", "compass", "best_effort", "why_absent",
    "set_progression", "working_weight", "item_energy", "quantity_range",
    "is_failed_attempt", "is_reference", "key_from_phrase", "artifact_faults",
    # Route and track helpers. They take a session row FROM the caller and
    # answer about it; they read nothing back out of the record.
    "route", "same_route", "session_route", "session_track",
}


def demo_copy(tmp_path) -> Path:
    """The shipped demo, somewhere writable.

    `_public_calls` CALLS every zero-argument public method, and some of those
    write. Pointing it at `examples/demo` appended to the shipped fixture on
    every suite run - see the sweep below for the whole argument. Anything that
    sweeps takes a copy; the read-only assertions can stay on the original.
    """
    import shutil

    root = tmp_path / "demo"
    shutil.copytree(DEMO, root)
    return root


def test_every_argument_taking_method_is_accounted_for(tmp_path):
    """The completeness half. The sweep skips anything raising TypeError, so
    without this a new arg-taking reader would be outside the guarantee and
    nothing would say so.

    ON A COPY, because the sweep CALLS every zero-argument public method and
    some of those write. `pin_policy` (#148) is the first with an all-optional
    signature, so it ran against the shipped demo and appended a `thresholds`
    row to it on every suite run - leaving `examples/` dirty and quietly
    breaking the demo-drift check every PR here is verified with. Listing the
    method would fix this instance; copying fixes the class, and the next
    writer with a default-only signature does not have to be remembered.
    """
    v = Vitai(demo_copy(tmp_path))
    skipped = set()
    for name in sorted(dir(v)):
        if name.startswith("_") or name in ("root", "config", "on", "as_of"):
            continue
        attr = getattr(v, name)
        if not callable(attr):
            continue
        try:
            attr()
        except TypeError:
            skipped.add(name)
        except Exception:
            continue

    unaccounted = skipped - ARG_TAKING_COVERED - ARG_TAKING_OUT_OF_SCOPE
    assert not unaccounted, (
        f"{sorted(unaccounted)} take arguments, so the sweep never calls "
        f"them. Exercise them by name or record why they are out of scope")
    assert ARG_TAKING_COVERED <= skipped | set(dir(v))


def test_the_argument_taking_readers_are_covered_too():
    """The row-returning ones, called by name because the sweep cannot."""
    v = Vitai(DEMO)

    assert LEAK not in json.dumps(v.dataset("sessions"))
    assert LEAK not in json.dumps(v.dataset("context"))
    assert LEAK not in json.dumps(v.day("2030-06-18"), default=str)
    assert LEAK not in json.dumps(v.derived("session_weeks"), default=str)
    assert LEAK not in json.dumps(v.instrument("scale"), default=str)
    # And it really does return a row, so the line above is not passing on an
    # empty answer - which is how a redaction check goes quietly vacuous.
    assert v.instrument("scale")["name"]


def test_a_write_echoes_back_the_coarse_row(tmp_path):
    """THE SURFACE THE READ DOOR CANNOT COVER. `append`, `claim` and `said`
    hand back the row they just wrote without going through it.

    The argument for leaving them is that the caller supplied the value, so an
    echo withholds nothing it does not already have. Not enough: `vitai
    append` prints the echo to stdout and the MCP `claim` tool returns it, so
    an agent harness that logs every tool result logs the address without
    anything ever naming a release. The write path is not a reason to be a
    second egress surface.
    """
    v = Vitai(init(tmp_path / "content"))

    one = v.append("sessions", {"date": "2030-05-01", "type": "run",
                                "distance_km": 5.0, "source": "watch",
                                "place": "home", "place_precise": LEAK})
    many = v.append_many("sessions", [{
        "date": "2030-05-02", "type": "run", "distance_km": 6.0,
        "source": "watch", "place": "home", "place_precise": LEAK}])

    assert "place_precise" not in one
    assert one["place"] == "home"
    assert not [r for r in many if "place_precise" in r]
    # And the value really did land: coarsening the echo is not dropping it.
    assert [r for r in v.precise("sessions", release="checking the write")
            if r.get("place_precise") == LEAK]


def test_the_other_write_doors_echo_through_the_same_one():
    """`claim` and `said` return `self.append(...)`, so they inherit the
    coarsened echo. Pinned by reading the source, because the day one of them
    starts building its own return value nothing else would notice."""
    import inspect

    from vitai import api

    for method in (api.Vitai.claim, api.Vitai.said):
        assert "self.append(" in inspect.getsource(method), method


def test_the_cli_write_echo_does_not_print_it(tmp_path):
    """The surface the argument above is actually about."""
    root = init(tmp_path / "content")
    row = json.dumps({"date": "2030-05-01", "type": "run",
                      "distance_km": 5.0, "source": "watch",
                      "place": "home", "place_precise": LEAK})
    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "append", "sessions",
         "--root", str(root)],
        input=row, capture_output=True, text=True, check=True)

    assert LEAK not in out.stdout, out.stdout
    assert "place" in out.stdout


def test_the_engine_reads_through_the_same_door(tmp_path):
    """Not luck, and worth pinning as the decision it is: nothing in the
    engine computes on a precise tier, so the arithmetic can read the coarse
    projection. A field the maths needed would be a field this classification
    should not hold."""
    v = _record(tmp_path)

    assert not v.validate()["problems"]
    assert v.dataset("sessions")[0]["place"] == "home"
    assert "place_precise" not in v.dataset("sessions")[0]


# --- the named release --------------------------------------------------------

def test_the_precise_tier_is_reachable_by_naming_a_release(tmp_path):
    """Stored, not discarded. The whole point of the two tiers is that the
    precise value is really there."""
    rows = _record(tmp_path).precise(
        "sessions", release="showing the athlete their own record")

    assert rows[0]["place_precise"] == LEAK


def test_a_release_with_no_purpose_is_refused(tmp_path):
    """#205's third commitment: permission is per use, not a standing flag. A
    setting toggled once and never revisited is a checkbox rather than
    consent, and a caller that cannot say what it is about to do with an
    address has not decided to do it."""
    v = _record(tmp_path)
    for empty in ("", "   ", None):
        with pytest.raises(ValueError) as raised:
            v.precise("sessions", release=empty)
        assert "naming what this is for" in str(raised.value)


def test_the_named_path_does_not_poison_the_default_one(tmp_path):
    """Two caches, one load. A consumer that asked for the precise tier once
    must not leave it visible to the next reader of the same instance."""
    v = _record(tmp_path)

    v.precise("sessions", release="a one-off")

    assert "place_precise" not in v.dataset("sessions")[0]


# --- the surfaces the read path does not cover --------------------------------

def test_the_read_model_has_no_column_for_it(tmp_path):
    """A read model is a serialisation, so it is inside the boundary. A null
    column would be worse than no column: it reads as "nobody wrote one"
    rather than "you are not being shown this"."""
    v = _record(tmp_path)
    v.build()

    con = sqlite3.connect(v.root / "derived" / "health.db")
    cols = [c[1] for c in con.execute("PRAGMA table_info(sessions)")]

    assert "place" in cols
    assert "place_precise" not in cols
    assert PRECISE_KEYS
    assert LEAK.encode() not in (
        v.root / "derived" / "health.db").read_bytes()


def test_a_message_that_never_names_the_field_is_redacted_too():
    """THE LEAK THE FIRST VERSION SHIPPED. Redaction only rewrote problems
    that named the field in quotes, on the reasoning that every message
    quoting a value also names where it came from. False: `bad date {v!r}`,
    `bad start_time` and `bad measured_at` name no field in quotes at all.

    The scenario is not exotic - it is what a column-shifted import does. A
    flattened export puts the address into `date` while `place_precise` also
    holds it, and the refusal came back reading `bad date '<the address>'`,
    out through validate(), the load report's warnings, the CLI and the MCP
    validate tool, with the value sitting in the row unredacted.
    """
    problems = validate_record("sessions", _session(
        date=LEAK, place=" ", place_precise=LEAK))

    assert problems
    assert not any(LEAK in p for p in problems), problems
    assert any(REDACTED in p for p in problems), problems


def test_the_redaction_is_wired_into_the_only_door_that_matters():
    """A test that calls the helper directly proves the helper works and NOT
    that anything calls it. Unwiring it from `validate_record`'s exit left the
    whole suite green, because no message in the live corpus both named the
    field and quoted its value - so the wiring had never once been exercised.
    This goes through `validate_record`, which is what every consumer reaches.
    """
    problems = validate_record("sessions", _session(
        date="not-a-date", place="gym", place_precise="not-a-date"))

    assert problems
    assert not any("not-a-date" in p for p in problems), problems


def test_it_reaches_the_consumer_surfaces_and_not_only_the_function(tmp_path):
    """Where those strings actually go. A validation problem is not an
    internal object: it is printed by `vitai validate`, returned by the MCP
    validate tool, and carried in the load report's warnings."""
    root = init(tmp_path / "content")
    data = root / "data" / "sessions.jsonl"
    data.write_text(json.dumps({
        "date": LEAK, "type": "run", "distance_km": 5.0, "source": "watch",
        "place": " ", "place_precise": LEAK, "_gen": 1}) + "\n",
        encoding="utf-8")

    out = subprocess.run(
        [sys.executable, "-m", "vitai.cli", "validate", "--root", str(root)],
        capture_output=True, text=True)

    assert LEAK not in out.stdout, out.stdout
    assert LEAK not in out.stderr
    assert LEAK not in json.dumps(mcp.call(root, "validate", {}), default=str)


def test_redaction_names_itself_rather_than_deleting_silently():
    """A message with the value snipped out reads as a message that never had
    one. A reader debugging a refusal has to know something was withheld."""
    from vitai.schema import _redacted

    out = _redacted("sessions", _session(place_precise=LEAK, place="gym"),
                    ["'place_precise' is " + repr(LEAK)])

    assert out == [f"'place_precise' is {REDACTED}"]


def test_the_prompt_path_takes_its_rows_from_the_coarse_door():
    """A model that phrases anything has already read the record, and if it is
    an API then every prompt is a disclosure. The inference prompt serialises
    fourteen daily rows and ten sessions verbatim; it takes them from
    `datasets()`, so it inherits the boundary rather than needing its own
    gate. Pinned because the day it stops doing that, nothing else would
    notice."""
    import inspect

    from vitai import api

    source = inspect.getsource(api.Vitai.infer)

    assert "self.datasets()" in source


# --- the surfaces built on top ------------------------------------------------

def test_the_cli_does_not_emit_it():
    """The CLI has thirty-five print sites over the API and no chokepoint of
    its own, which is exactly why the gate is not there. Both the JSON path
    and the human one, because `day`'s human path re-derives its own
    projection from `r.items()`."""
    for args in (["dataset", "sessions", "--json"],
                 ["dataset", "context", "--json"],
                 ["day", "--date", "2030-06-18"],
                 ["situation"]):
        out = subprocess.run(
            [sys.executable, "-m", "vitai.cli", *args, "--root", str(DEMO)],
            capture_output=True, text=True, check=True)

        assert LEAK not in out.stdout, args
        assert LEAK not in out.stderr, args


def test_the_mcp_tools_do_not_emit_it():
    """One harness over the same methods, so it inherits - pinned rather than
    assumed, because "it inherits" is the sentence that precedes every gate
    with a hole in it."""
    for tool, args in (("dataset", {"name": "sessions"}),
                       ("day", {"on": "2030-06-18"}),
                       ("situation", {})):
        out = mcp.call(DEMO, tool, args)

        assert LEAK not in json.dumps(out, default=str), tool


def test_the_shipped_record_exercises_both_tiers():
    """#204's corollary. A fixture holding only the empty case proves nothing
    about the populated one, and this field's whole point is the difference
    between them - so the demo carries rows with a precise tier and rows
    without, and the boundary tests above are checking a real value rather
    than an absence that was never there."""
    rows = Vitai(DEMO).precise("sessions", release="checking the fixture")
    rows += Vitai(DEMO).precise("context", release="checking the fixture")
    with_precise = [r for r in rows if r.get("place_precise")]

    assert with_precise, "no shipped row carries a precise tier"
    assert [r for r in rows if r.get("place") and not r.get("place_precise")]
    for row in with_precise:
        assert row.get("place"), row


def test_the_read_model_says_which_contract_the_absence_belongs_to(tmp_path):
    """A consumer finds `place` and no `place_precise`, and has to be able to
    learn that the absence is a decision rather than a field nobody got round
    to. The read model carries the contract it was built under, which is where
    that answer lives; the number itself is not asserted, because a test
    pinned to a literal stops meaning anything the next time it moves."""
    v = _record(tmp_path)
    v.build()
    con = sqlite3.connect(v.root / "derived" / "health.db")

    stamped, = con.execute(
        "SELECT value FROM meta WHERE key = 'contract'").fetchone()

    assert stamped == CONTRACT_VERSION
