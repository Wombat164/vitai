"""The content-addressed artifact store (#80).

The evidence behind a value was discarded the moment it was read: an athlete
photographs a gym console, a model reads the numbers off it, the numbers enter
the record, and the photograph is stored nowhere. So the richest
single-instrument reading in a record is also the one that cannot be checked.

EVERYTHING HERE IS SYNTHETIC BYTES. The mechanism is public; the artifacts are
personal data and live only in a private record. A gym photograph can contain
other people's faces, a location, a name badge - so no artifact, no manifest
row and no hash of a real one belongs in this repository, including in its
tests.
"""

import pytest

from vitai.api import Vitai
from vitai.artifacts import (DirectoryStore, digest, faults, is_reference,
                             live_manifest, removed_refs, verify)
from vitai.cli import main
from vitai.schema import KEYS, validate_record

PHOTO = b"synthetic bytes standing in for a console photograph"
OTHER = b"different synthetic bytes"


def repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def manifest_row(ref, **kw):
    row = {"date": "2030-05-01", "sha256": ref, "media_type": "image/jpeg",
           "bytes": len(PHOTO), "captured_at": None, "origin": None,
           "kind": None, "note": None, "removed": None, "reason": None}
    row.update(kw)
    return row


# ---- content addressing ---------------------------------------------------------

def test_the_address_is_the_content():
    assert digest(PHOTO) == digest(PHOTO)
    assert digest(PHOTO) != digest(OTHER)
    assert is_reference(digest(PHOTO))


def test_a_filename_is_not_an_address():
    """A hash cannot drift from the row that cites it, the way a path can."""
    for bad in ("photo.jpg", "sha256:short", "", None, "sha256:" + "z" * 64):
        assert is_reference(bad) is False, bad


def test_the_same_bytes_are_stored_once(tmp_path):
    store = DirectoryStore(tmp_path / "artifacts")
    first, second = store.put(PHOTO), store.put(PHOTO)
    assert first == second
    assert len(store.refs()) == 1


def test_adding_the_same_artifact_twice_is_idempotent(tmp_path):
    root = repo(tmp_path)
    v = Vitai(root)
    a = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    b = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-02")
    assert a["sha256"] == b["sha256"]
    assert len(v.dataset("artifacts")) == 1, "one copy, one manifest row"


# ---- verify, in both directions --------------------------------------------------

def test_a_missing_artifact_is_reported(tmp_path):
    """The direction that matters: a value's evidence was lost while the
    value stayed."""
    store = DirectoryStore(tmp_path / "artifacts")
    ref = digest(PHOTO)
    found = verify(store, {"artifacts": [manifest_row(ref)],
                           "weight": [{"artifact": ref}]})
    assert any(f["kind"] == "missing" for f in found)


def test_a_corrupted_artifact_is_detected(tmp_path):
    """Fixity: the stored bytes must hash to their own address, or this is
    not the artifact that was cited."""
    store = DirectoryStore(tmp_path / "artifacts")
    ref = store.put(PHOTO)
    path = next(p for p in (tmp_path / "artifacts").rglob("*") if p.is_file())
    path.write_bytes(OTHER)
    found = verify(store, {"artifacts": [manifest_row(ref)]})
    assert any(f["kind"] == "corrupt" for f in found)


def test_an_orphan_is_reported_but_costs_disk_not_truth(tmp_path):
    store = DirectoryStore(tmp_path / "artifacts")
    store.put(PHOTO)
    found = verify(store, {"artifacts": []})
    assert [f["kind"] for f in found] == ["orphan"]


def test_a_row_citing_an_artifact_never_in_the_manifest_is_reported(tmp_path):
    store = DirectoryStore(tmp_path / "artifacts")
    found = verify(store, {"artifacts": [],
                           "weight": [{"artifact": digest(PHOTO)}]})
    assert any(f["kind"] == "unbacked" for f in found)


def test_a_clean_store_reports_nothing(tmp_path):
    store = DirectoryStore(tmp_path / "artifacts")
    ref = store.put(PHOTO)
    assert verify(store, {"artifacts": [manifest_row(ref)],
                          "weight": [{"artifact": ref}]}) == []


# ---- removed is not missing -------------------------------------------------------

def test_a_deletion_leaves_a_tombstone_rather_than_rewriting_the_row(tmp_path):
    """The store is append-only, so a deletion cannot rewrite the observation
    that cites an artifact - and should not want to. A tombstone keeps a
    retention DECISION distinguishable from data LOSS, which are completely
    different facts.
    """
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    v.remove_artifact(added["sha256"], "contains another gym member",
                      on="2030-05-03")
    rows = v.dataset("artifacts")
    assert len(rows) == 2, "the original row stays; a tombstone is appended"
    assert live_manifest(rows) == {}, "nothing is held any more"
    assert added["sha256"] in removed_refs(rows)


def test_a_removed_artifact_reads_as_a_decision_not_a_fault(tmp_path):
    store = DirectoryStore(tmp_path / "artifacts")
    ref = digest(PHOTO)
    found = verify(store, {
        "artifacts": [manifest_row(ref),
                      manifest_row(ref, date="2030-05-03", removed=True,
                                   reason="another member in shot")],
        "weight": [{"artifact": ref}]})
    kinds = [f["kind"] for f in found]
    assert kinds == ["removed"], kinds
    assert "not a fault" in found[0]["detail"]


def test_a_removal_must_say_why():
    """Deleting evidence is a decision worth recording, and the reason is
    what distinguishes it from data loss."""
    ref = digest(PHOTO)
    assert any("reason" in p for p in validate_record(
        "artifacts", manifest_row(ref, removed=True)))
    assert validate_record("artifacts", manifest_row(
        ref, removed=True, reason="another member in shot")) == []


# ---- the reference on an observation ----------------------------------------------

def test_an_observation_may_cite_an_artifact():
    row = {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None,
           "artifact": digest(PHOTO)}
    assert validate_record("weight", row) == []


def test_a_filename_reference_is_rejected():
    row = {"date": "2030-05-01", "kg": 80.0, "source": "scale", "note": None,
           "artifact": "photo.jpg"}
    assert any("content address" in p for p in validate_record("weight", row))


def test_one_artifact_can_back_several_rows(tmp_path):
    """A single console photograph carries distance, pace, power and stroke
    rate, which is why the manifest is its own dataset rather than a column."""
    from vitai.artifacts import cited
    ref = digest(PHOTO)
    where = cited({"sessions": [{"artifact": ref}, {"artifact": ref}],
                   "daily": [{"artifact": ref}]})
    assert set(where[ref]) == {"sessions", "daily"}
    assert set(where) == {ref}


# ---- the surface -------------------------------------------------------------------

def test_the_cli_lists_gets_and_verifies(tmp_path, capsys):
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01",
                           note="rower summary screen")
    v.append("weight", {"date": "2030-05-01", "kg": 80.0, "source": "scale",
                        "note": None, "artifact": added["sha256"]})
    capsys.readouterr()

    main(["artifact", "ls", "--root", str(root)])
    assert "rower summary screen" in capsys.readouterr().out

    out = tmp_path / "got.bin"
    main(["artifact", "get", added["sha256"], "--root", str(root),
          "--out", str(out)])
    capsys.readouterr()
    assert out.read_bytes() == PHOTO

    main(["artifact", "verify", "--root", str(root)])
    assert "all present and intact" in capsys.readouterr().out


def test_the_manifest_travels_in_the_read_model_and_the_bytes_do_not(tmp_path):
    """A consumer can see WHAT is held and check a hash it already has,
    without the read model carrying anybody's photographs."""
    import sqlite3
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        rows = con.execute("SELECT sha256, media_type, bytes FROM artifacts"
                           ).fetchall()
        cols = {r[1] for r in con.execute("PRAGMA table_info(artifacts)")}
    finally:
        con.close()
    assert rows == [(added["sha256"], "image/jpeg", len(PHOTO))]
    # The manifest columns are the manifest KEYS and nothing else, so a field
    # carrying bytes could only arrive by being declared in the schema - which
    # this then fails on.
    assert cols == set(KEYS["artifacts"])


def test_a_content_address_survives_the_read_model_as_text(tmp_path):
    """The `activity_id` lesson (#43): REAL affinity would mangle an opaque
    token, and a mangled hash is a hash that matches nothing."""
    import sqlite3
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    main(["build", "--root", str(root)])
    con = sqlite3.connect(root / "derived" / "health.db")
    try:
        got, = con.execute("SELECT sha256 FROM artifacts").fetchone()
    finally:
        con.close()
    assert got == added["sha256"] and isinstance(got, str)


def test_getting_an_absent_artifact_says_WHICH_fact_it_is(tmp_path):
    """Deleted, lost and never-here are three different facts, and the
    message says which - rather than referring the athlete to a check that
    has nothing to report for a hash no row mentions."""
    root = repo(tmp_path)
    v = Vitai(root)
    out = str(tmp_path / "got.bin")

    with pytest.raises(SystemExit, match="ever mentioned this hash"):
        main(["artifact", "get", digest(PHOTO), "--root", str(root),
              "--out", out])

    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    v.remove_artifact(added["sha256"], "another member in shot", on="2030-05-02")
    with pytest.raises(SystemExit, match="athlete deleted it"):
        main(["artifact", "get", added["sha256"], "--root", str(root),
              "--out", out])

    second = v.add_artifact(OTHER, "image/jpeg", date="2030-05-04")
    v.artifacts.drop(second["sha256"])
    with pytest.raises(SystemExit, match="lost rather than deleted"):
        main(["artifact", "get", second["sha256"], "--root", str(root),
              "--out", out])


def test_get_refuses_a_path_and_refuses_to_guess_a_destination(tmp_path):
    """`get` took an arbitrary string and made it a path, which turned it
    into a general-purpose file copier; and a default destination writes
    personal bytes into whatever directory the command ran from."""
    root = repo(tmp_path)
    (tmp_path / "secret.txt").write_bytes(b"not an artifact")
    with pytest.raises(SystemExit, match="not a content address"):
        main(["artifact", "get", "../secret.txt", "--root", str(root),
              "--out", str(tmp_path / "leak.bin")])
    assert not (tmp_path / "leak.bin").exists()
    with pytest.raises(SystemExit, match="needs --out"):
        main(["artifact", "get", digest(PHOTO), "--root", str(root)])


def test_nothing_on_the_artifact_path_transmits_one():
    """Storing an artifact is not consent to transmit it.

    Asserted as a property of the modules rather than trusted to review, and
    read off the parsed IMPORTS rather than the source text - grepping the
    text makes the prose that explains the rule trip the rule. All three
    files on the path, not just the store: `api.py` and `cli.py` are where
    the bytes actually move. `pathlib` is deliberately allowed and is the
    reason `_path` validates its reference before touching a filesystem.
    """
    import ast
    from pathlib import Path as _P
    src = _P(__file__).resolve().parents[1] / "src" / "vitai"
    reaches_out = {"urllib", "http", "requests", "httpx", "socket", "smtplib",
                   "ftplib", "webbrowser", "ssl", "asyncio"}
    for name in ("artifacts.py", "api.py", "cli.py"):
        imported = set()
        for node in ast.walk(ast.parse((src / name).read_text())):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & reaches_out, (name, imported & reaches_out)


# ---- what the review of this feature found ------------------------------------------

def test_a_reference_can_never_become_an_arbitrary_path(tmp_path):
    """The worst thing this module could be talked into. `drop` on a
    traversing reference deleted a DATASET file - an append-only violation
    reached through the one API whose job is to delete things.
    """
    store = DirectoryStore(tmp_path / "artifacts")
    victim = tmp_path / "weight.jsonl"
    victim.write_text("a data line\n")
    for verb, arg in (("drop", "../weight.jsonl"), ("get", "../weight.jsonl"),
                      ("drop", "photo.jpg"), ("get", "sha256:" + "A" * 64)):
        with pytest.raises(ValueError, match="not a content address"):
            getattr(store, verb)(arg)
    assert victim.exists(), "a dataset file was deleted through a reference"


def test_a_removal_that_leaves_the_bytes_behind_is_a_fault(tmp_path):
    """The only finding here about a promise made TO the athlete rather than
    about the record - and the only one they cannot discover themselves. The
    orphan scan used to subtract removed refs, which excluded exactly this.
    """
    store = DirectoryStore(tmp_path / "artifacts")
    ref = store.put(PHOTO)
    found = verify(store, {"artifacts": [
        manifest_row(ref, recorded_at="2030-05-01T09:00:00+02:00"),
        manifest_row(ref, recorded_at="2030-05-02T09:00:00+02:00",
                     removed=True, reason="another member in shot")]})
    assert [f["kind"] for f in faults(found)] == ["not_erased"]


def test_re_adding_a_removed_artifact_is_a_new_decision(tmp_path):
    """It must not read as "already in the manifest" and silently put the
    bytes back while the manifest still says deleted."""
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    v.remove_artifact(added["sha256"], "another member in shot", on="2030-05-02")
    again = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-03",
                           note="cropped, kept deliberately")
    rows = v.dataset("artifacts")
    assert len(rows) == 3, "add, tombstone, add - three decisions"
    assert not again.get("removed"), "the tombstone was returned as the new row"
    assert added["sha256"] in live_manifest(rows)
    assert faults(v.verify_artifacts()) == []


def test_a_backdated_removal_still_removes(tmp_path):
    """`date` on a manifest row can be the day the photograph was TAKEN, so
    ordering retention decisions by it lets a removal sort before the add it
    revokes - and the artifact reads as held while its bytes are gone.
    Decisions order by transaction time.
    """
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-05")
    v.remove_artifact(added["sha256"], "another member in shot", on="2030-05-01")
    rows = v.dataset("artifacts")
    assert live_manifest(rows) == {}
    assert added["sha256"] in removed_refs(rows)
    assert faults(v.verify_artifacts()) == [], "a removal is not a fault"
    assert not (root / "artifacts").exists() or v.artifacts.refs() == set()


def test_a_tombstone_for_a_hash_never_added_cannot_launder_a_citation(tmp_path):
    """Otherwise any mistyped or fabricated removal converts "this value
    cites evidence that never existed" into "the athlete deleted it"."""
    store = DirectoryStore(tmp_path / "artifacts")
    ref = digest(PHOTO)
    found = verify(store, {
        "artifacts": [manifest_row(ref, removed=True, reason="never existed")],
        "weight": [{"artifact": ref}]})
    assert [f["kind"] for f in faults(found)] == ["unbacked"]


def test_re_adding_the_original_repairs_a_corrupted_artifact(tmp_path):
    """The obvious thing an athlete would try. It was a no-op, because `put`
    only wrote when the path was absent and `add_artifact` returned early on
    a manifest row that already existed.
    """
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    damaged = next(p for p in (root / "artifacts").rglob("*") if p.is_file())
    damaged.write_bytes(b"truncated")
    assert "corrupt" in [f["kind"] for f in v.verify_artifacts()]
    v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    assert v.artifacts.get(added["sha256"]) == PHOTO
    assert faults(v.verify_artifacts()) == []


def test_a_manifest_row_that_fails_validation_leaves_no_bytes_behind(tmp_path):
    """The row is appended first on purpose: the reverse order fails towards
    personal bytes on disk that nothing in the record points at, which
    nothing would ever surface."""
    from vitai.jsonl import DataError
    root = repo(tmp_path)
    v = Vitai(root)
    with pytest.raises(DataError):
        v.add_artifact(PHOTO, "image/jpeg", date="the fifth of May")
    assert v.artifacts.refs() == set()


def test_a_removal_that_fails_validation_leaves_the_bytes_alone(tmp_path):
    """Recording the decision is recoverable; destroying the evidence first
    is not - and it reports permanent data loss for a deliberate deletion."""
    from vitai.jsonl import DataError
    root = repo(tmp_path)
    v = Vitai(root)
    added = v.add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    with pytest.raises(DataError):
        v.remove_artifact(added["sha256"], "another member", on="not-a-date")
    assert v.artifacts.get(added["sha256"]) == PHOTO
    assert added["sha256"] in live_manifest(v.dataset("artifacts"))


def test_an_empty_artifact_is_stored_and_reported_as_empty(tmp_path, capsys):
    """Zero bytes is what a truncated capture looks like, so it must not
    print as "size unknown" - the one number that would say so."""
    root = repo(tmp_path)
    Vitai(root).add_artifact(b"", "image/jpeg", date="2030-05-01")
    capsys.readouterr()
    main(["artifact", "ls", "--root", str(root)])
    assert "0 bytes" in capsys.readouterr().out


def test_text_is_not_an_artifact(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(TypeError, match="an artifact is bytes"):
        Vitai(root).add_artifact("a filename.jpg", "image/jpeg",
                                 date="2030-05-01")


def test_a_stray_file_in_the_store_is_not_an_artifact(tmp_path):
    """`refs()` named every file by its own filename, so a README produced a
    finding about a hash that does not exist."""
    store = DirectoryStore(tmp_path / "artifacts")
    ref = store.put(PHOTO)
    (tmp_path / "artifacts" / "README.txt").write_text("where the photos live")
    body = ref[len("sha256:"):]
    (tmp_path / "artifacts" / "zz").mkdir()
    (tmp_path / "artifacts" / "zz" / body).write_bytes(PHOTO)
    assert store.refs() == {ref}, "shape and shard, not just any file"


def test_an_artifact_nothing_cites_yet_is_a_note_not_a_failure(tmp_path, capsys):
    """A photograph is stored before the row that cites it exists. Failing
    the check on that would teach the athlete to ignore it - and the one
    finding worth reading is the one that says a value's evidence is gone.
    """
    root = repo(tmp_path)
    Vitai(root).add_artifact(PHOTO, "image/jpeg", date="2030-05-01")
    capsys.readouterr()
    main(["artifact", "verify", "--root", str(root)])   # does not exit non-zero
    out = capsys.readouterr().out
    assert "UNUSED" in out and "note(s)" in out


def test_the_check_fails_when_a_value_can_no_longer_be_backed(tmp_path):
    ref = digest(PHOTO)
    found = verify(DirectoryStore(tmp_path / "artifacts"),
                   {"artifacts": [manifest_row(ref)],
                    "weight": [{"artifact": ref}]})
    assert [f["kind"] for f in faults(found)] == ["missing"]
