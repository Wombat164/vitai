"""A content-addressed store for the evidence behind a value (#80).

The evidence was discarded the moment it was read. An athlete photographs a
gym console, a model reads the numbers off it, the numbers enter the record -
and the photograph is not stored anywhere. So the richest single-instrument
reading in a record is also the one that cannot be checked, and if the read
was wrong there is no way to find out.

## Why content addressing rather than filenames

Three reasons, and the third is the one that matters here:

- the same photo added twice is stored once;
- the hash is a FIXITY check, so a corrupted or swapped artifact is
  detectable on read (the PREMIS discipline);
- a hash cannot drift from the row that cites it, the way a path can.

## Removed is not missing

The store is append-only like everything else, so a deletion cannot rewrite
the observation that cites an artifact - and it should not want to. Instead a
TOMBSTONE is appended to the manifest: same hash, `removed` set, reason kept.

A citing row then resolves to "the athlete deleted this" rather than "the
evidence is gone and nobody knows why". Those are completely different facts:
one is a retention decision, the other is a fault. Reporting them the same way
would make the deletion path indistinguishable from data loss, and a record
that cannot forget is a liability - the athlete's right to remove a photograph
must not look like corruption.

## The boundary, which is not negotiable

The MECHANISM is public. The ARTIFACTS are personal data and live only in a
private record. A gym photograph is not a neutral object: it can contain other
people's faces, a location, a name badge, a membership number. So this module
ships the store, the manifest schema and the CLI, and no artifact, no manifest
row and no hash of a real one ever appears in the public repository.

Storing an artifact is also not consent to transmit it. Nothing here uploads,
syncs or attaches anything, and nothing should be added that does.

## The backend is behind an interface on purpose

Binaries in git are a real cost, and the alternatives - git-lfs, a sibling
directory with its own backup, an object store - are an operator decision
about a private record rather than an engine decision. The manifest and the
addressing scheme are identical under all three, so they are built first and
the storage sits behind `ArtifactStore`. The default is a local directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

PREFIX = "sha256:"
MANIFEST = "artifacts"


def digest(payload: bytes) -> str:
    """The content address of these bytes."""
    return PREFIX + hashlib.sha256(payload).hexdigest()


def is_reference(value: object) -> bool:
    """Is this a canonical content address?

    Lowercase hex only. Two spellings of one address would defeat the property
    the whole store rests on - that the same bytes are held once - so the
    canonical form is the only form, and an uppercase hash is rejected rather
    than quietly folded.
    """
    body = str(value or "")
    return (body.startswith(PREFIX) and len(body) == len(PREFIX) + 64
            and all(c in "0123456789abcdef" for c in body[len(PREFIX):]))


class ArtifactStore(Protocol):
    """Bytes in, bytes out, addressed by content."""

    def put(self, payload: bytes) -> str: ...
    def get(self, ref: str) -> bytes | None: ...
    def drop(self, ref: str) -> bool: ...
    def refs(self) -> set[str]: ...


class DirectoryStore:
    """The default backend: one file per artifact, sharded by hash prefix.

    Sharded because a flat directory of thousands of files is slow to list on
    some filesystems and unpleasant to look at on all of them.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, ref: object) -> Path:
        """The file holding this artifact.

        The reference is checked here rather than at the callers, because this
        is the only place it becomes a PATH and every caller would otherwise
        have to remember. Without the check a reference is an arbitrary path
        fragment: `drop("../data/weight.jsonl")` deletes a dataset, which is
        both an append-only violation and the most destructive thing this
        module could possibly be talked into doing. `get` is the same hole
        pointed the other way - it would read any file the process can reach.
        """
        if not is_reference(ref):
            raise ValueError(
                f"{ref!r} is not a content address. An artifact is addressed "
                f"by '{PREFIX}<64 lowercase hex>' and never by a path")
        return self.root / str(ref)[len(PREFIX):][:2] / str(ref)[len(PREFIX):]

    def put(self, payload: bytes) -> str:
        """Store these bytes and return their address.

        Written to a temporary name and renamed, so an interrupted or
        concurrent put cannot leave a truncated file sitting at an address
        that promises to hash to its own contents. The rename is atomic on
        POSIX and overwrites, which also makes re-adding the original the
        repair for a corrupted artifact - the obvious thing an athlete would
        try, and a no-op if this only wrote when the path was absent.
        """
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(
                "an artifact is bytes - read the file rather than passing its "
                f"name or contents as text (got {type(payload).__name__})")
        payload = bytes(payload)
        ref = digest(payload)
        path = self._path(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(payload)
        tmp.replace(path)
        return ref

    def get(self, ref: str) -> bytes | None:
        path = self._path(ref)
        return path.read_bytes() if path.is_file() else None

    def drop(self, ref: str) -> bool:
        path = self._path(ref)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def refs(self) -> set[str]:
        """The addresses actually held.

        Filtered by shape and by shard: a stray README, a half-written `.part`
        or a file in the wrong shard directory is not an artifact, and calling
        one an artifact produces a finding about a hash that does not exist.
        """
        if not self.root.exists():
            return set()
        found = set()
        for p in self.root.rglob("*"):
            if not p.is_file():
                continue
            ref = PREFIX + p.name
            if is_reference(ref) and p.parent.name == p.name[:2]:
                found.add(ref)
        return found


def cited(datasets: dict[str, list[dict]]) -> dict[str, list[str]]:
    """Every artifact reference in the record, and which dataset cites it."""
    out: dict[str, list[str]] = {}
    for name, rows in datasets.items():
        if name == MANIFEST:
            continue
        for row in rows:
            if is_reference(row.get("artifact")):
                out.setdefault(str(row["artifact"]), []).append(name)
    return out


def _decisions(rows: list[dict]) -> list[dict]:
    """Manifest rows in the order the decisions were MADE.

    Transaction time, not valid time. `date` on a manifest row says when the
    artifact belongs in the record - which may be the day the photograph was
    taken - so ordering retention decisions by it lets a removal recorded
    against an older date sort BEFORE the add it revokes, and the artifact
    reads as still held while its bytes are gone. What is held now is a
    question about the order the athlete decided things in, which is
    `recorded_at`, with file order as the tiebreak for rows that predate it.
    """
    numbered = [(str(r.get("recorded_at") or ""), i, r)
                for i, r in enumerate(rows) if is_reference(r.get("sha256"))]
    return [r for _, _, r in sorted(numbered, key=lambda t: (t[0], t[1]))]


def live_manifest(rows: list[dict]) -> dict[str, dict]:
    """The manifest with tombstones applied - what is still held."""
    out: dict[str, dict] = {}
    for row in _decisions(rows):
        if row.get("removed"):
            out.pop(str(row["sha256"]), None)
        else:
            out[str(row["sha256"])] = row
    return out


def removed_refs(rows: list[dict]) -> set[str]:
    """Artifacts the athlete deliberately deleted, and that were once held.

    A tombstone for a hash that was never added does not describe a deletion,
    because there was nothing to delete. Counting one would let a fabricated
    or mistyped removal launder an unbacked citation: the row citing that hash
    would read as "the athlete deleted the evidence" instead of "this cites
    evidence that never existed", turning a fault into a decision.
    """
    added, gone = set(), set()
    for row in _decisions(rows):
        ref = str(row["sha256"])
        if row.get("removed"):
            if ref in added:
                gone.add(ref)
        else:
            added.add(ref)
            gone.discard(ref)
    return gone


# A finding is a FAULT when the record makes a promise it is no longer
# keeping. Two kinds of promise, and both belong here:
#
# - a value can still be checked against the evidence it was read from
#   (`missing`, `corrupt`, `uncited_manifest`);
# - an artifact the athlete deleted is actually GONE (`not_erased`). That one
#   is the only privacy-relevant state in the list, and the athlete has no way
#   to discover it themselves - the manifest says removed and the photograph
#   is still on disk.
#
# The rest are housekeeping or decisions: bytes nothing points at, a
# photograph added before the row that will cite it, a manifest annotation
# that disagrees with a file which provably hashes correctly. Those are worth
# printing and not worth failing on - a check that cries wolf over disk
# hygiene teaches the athlete to ignore the one time it means something.
FAULTS = frozenset({"missing", "corrupt", "unbacked", "not_erased"})


def faults(findings: list[dict]) -> list[dict]:
    """The findings that say a value can no longer be checked."""
    return [f for f in findings if f["kind"] in FAULTS]


def verify(store: ArtifactStore, datasets: dict[str, list[dict]]) -> list[dict]:
    """Fixity and referential integrity, in both directions.

    The direction that matters is a row citing an artifact that is GONE: it
    means a value's evidence was lost while the value stayed, which is the
    failure this store exists to prevent. An orphan is reported too, more
    quietly - it costs disk rather than truth.
    """
    manifest = datasets.get(MANIFEST) or []
    held = live_manifest(manifest)
    gone = removed_refs(manifest)
    on_disk = store.refs()
    citations = cited(datasets)
    findings: list[dict] = []

    for ref, meta in sorted(held.items()):
        payload = store.get(ref)
        if payload is None:
            findings.append({
                "ref": ref, "kind": "missing",
                "detail": "the manifest holds it and the store does not - "
                          "the bytes were lost rather than deleted"})
        elif digest(payload) != ref:
            findings.append({
                "ref": ref, "kind": "corrupt",
                "detail": "the stored bytes do not hash to their own address, "
                          "so this artifact is not the one that was cited"})
        elif meta.get("bytes") is not None and len(payload) != meta["bytes"]:
            # Reachable only after the digest matched, so the bytes ARE the
            # cited artifact and the value is fully backed. Only the manifest's
            # own annotation is wrong, which is worth saying and not worth
            # failing a build over.
            findings.append({
                "ref": ref, "kind": "size_mismatch",
                "detail": f"manifest says {meta['bytes']} bytes, store holds "
                          f"{len(payload)} - the artifact is intact and the "
                          "annotation is wrong"})

    for ref, datasets_citing in sorted(citations.items()):
        where = ", ".join(sorted(set(datasets_citing)))
        if ref in gone and ref not in held:
            findings.append({
                "ref": ref, "kind": "removed",
                "detail": f"cited by {where}; the athlete deleted it. The "
                          "value stands and its evidence is gone by choice - "
                          "not a fault"})
        elif ref not in held:
            findings.append({
                "ref": ref, "kind": "unbacked",
                "detail": f"cited by {where}, and no manifest row ever held "
                          "it - this value cites evidence that never existed"})

    # The deletion the athlete asked for did not happen. Nothing else in this
    # function is about a promise made TO the athlete rather than about the
    # record, and they cannot find it any other way: the manifest says removed
    # and the photograph is still there.
    for ref in sorted(on_disk & gone):
        findings.append({
            "ref": ref, "kind": "not_erased",
            "detail": "the manifest says the athlete deleted this and the "
                      "bytes are still in the store"})
    for ref in sorted(on_disk - set(held) - gone):
        findings.append({
            "ref": ref, "kind": "orphan",
            "detail": "in the store, in no manifest row - costs disk, not truth"})
    for ref in sorted(set(held) - set(citations)):
        findings.append({
            "ref": ref, "kind": "unused",
            "detail": "held, and no row cites it yet; keep it or drop it"})
    return findings
