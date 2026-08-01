"""Transport, custody and cipher as engine interfaces (#108).

The operator's framing, and it is the right one: auth, backup and sync are
well-defined engine interfaces, and the in-app offering is a GOLDEN PATH -
one implementation, not a privileged one.

## The test that decides whether the interface is real

**The bundled implementation must pass the same conformance suite as a third
party's, with no privileged access.** Every layered architecture that failed
did so the same way: the first-party implementation quietly used a capability
the interface never exposed, and third parties could never quite match it.

So `vitai conform` is the deliverable, not the prose. A written contract
produces implementations that mostly work and fail strangely; a conformance
suite produces implementations that either pass or do not.

## Transport - deliberately stupid

    put(blob_id, blob) -> None      idempotent: same id and bytes is a no-op
    get(blob_id) -> bytes | None
    list(prefix) -> [blob_id]
    delete(blob_id) -> None

**Opaque bytes only. No hook that ever sees plaintext.** This is not a style
preference: a transport that understands content can decrypt, so the
interface's IGNORANCE is the security property, and it must be impossible to
extend it into knowledge. #105 is what makes that affordable - one writer per
file means merge is a set union, and nothing has to read a row to reconcile.

## Custody - where the key comes from

    retrieve() -> bytes | None      may prompt, may unlock, may fail
    store(key) -> None
    verify() -> bool                can the key be retrieved right now?

`verify()` is not decoration. It is what makes a restore drill a scheduled
operation rather than a one-off at setup: a custody backend that has silently
stopped working is exactly the failure that stays invisible until it matters.

## Backup is not a subsystem

With a content-addressed, append-only blob set, **a backup is a copy of the
blob set at a point in time**. There is no separate backup interface: a second
transport configured for retention rather than convergence IS the backup, and
restore is `list()` plus `get()` against it. That falls out of #105 rather
than being designed.

## What stays in the engine

Blob-ID derivation, the name-to-ID map, size padding, ordering, rebuild: all
here. A provider that must be trusted to encrypt correctly is a provider that
can get it wrong, and nobody can audit every transport they might plug in.
**Providers move bytes and hold secrets. They never decide anything.**

## And the engine ships no cipher, which is a refusal rather than a gap

vitai is stdlib-only, and the standard library has no authenticated
encryption - `hashlib` and `hmac`, but no AEAD. The options were to take a
dependency, to hand-roll a cipher, or to ship none.

Hand-rolling is how this goes wrong. So `Cipher` is a contract with no
bundled implementation, and `plan_upload` REFUSES to hand a transport
anything that has not been through one. An unencrypted blob never reaches a
provider by default, and the way to get one there is to say so explicitly,
which is a decision someone makes rather than one they inherit.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path
from typing import Protocol

# A blob id is opaque ON THE WIRE (#106). `sessions.phone.jsonl` discloses
# that the athlete trains and owns two devices; sync timestamps disclose their
# training rhythm. A ciphertext-only server still learns holidays, illness and
# routine unless the NAMES are opaque too, and that is cheap now and a
# migration later.
PREFIX = "blob:"

# What a directory-backed transport will accept as a filename. The engine
# only ever derives hex ids; this is what stops anything else becoming a path.
_SAFE_BODY = re.compile(r"^[A-Za-z0-9-]{1,128}$")

# Sizes are padded to buckets before upload, for the same reason. Byte-exact
# sizes leak how much was logged on a given day, which is a training diary
# written in metadata.
#
# POWERS OF TWO, which is what the comment always said and what the code did
# not do. Rounding to a multiple of 4 KiB hides nothing once a file is past a
# few KiB: an append-only `sessions.jsonl` after some months leaks its growth
# at 4 KiB granularity every sync. Exponential buckets bound the leak to a
# RATIO instead - a file only changes bucket when it doubles, which no single
# day's logging does.
PAD_FLOOR = 4096


class Transport(Protocol):
    """Bytes in, bytes out, addressed by an opaque id.

    Implementations: a local directory, a mirror across several, a memory
    store, and anything an athlete points at. All equal - if the bundled one
    can do something a user's own cannot, the interface is decoration.
    """

    def put(self, blob_id: str, blob: bytes) -> None: ...
    def get(self, blob_id: str) -> bytes | None: ...
    def list(self, prefix: str = "") -> list[str]: ...
    def delete(self, blob_id: str) -> None: ...


class Custody(Protocol):
    """Where the key comes from. May prompt, may unlock, may fail."""

    def retrieve(self) -> bytes | None: ...
    def store(self, key: bytes) -> None: ...
    def verify(self) -> bool: ...


class Cipher(Protocol):
    """Authenticated encryption. NO IMPLEMENTATION SHIPS - see the module
    docstring: the standard library has no AEAD and hand-rolling one is how
    this goes wrong."""

    def seal(self, key: bytes, plaintext: bytes) -> bytes: ...
    def open(self, key: bytes, blob: bytes) -> bytes | None: ...


# --- what the engine decides ---------------------------------------------------

def blob_id(key: bytes, name: str) -> str:
    """The opaque id a file is stored under.

    Derived with an HMAC under the athlete's own key, so the mapping from
    `sessions.phone.jsonl` to an id is not computable by anyone holding the
    blobs. A plain hash of the name would be: the filenames are a short,
    guessable set, and a server could simply hash the obvious candidates.

    Deterministic, so the same file lands on the same id every sync and `put`
    is idempotent rather than accumulating copies.
    """
    if not key:
        raise ValueError("a blob id is derived under the record's own key - "
                         "without one the mapping is guessable by anyone "
                         "holding the blobs, which is the whole point of it "
                         "not being the filename")
    digest = hmac.new(key, name.encode("utf-8"), hashlib.sha256).hexdigest()
    return PREFIX + digest


def bucket(size: int, floor: int = PAD_FLOOR) -> int:
    """The padded size for a payload: the next power of two, floored."""
    out = floor
    while out < size:
        out *= 2
    return out


def pad(blob: bytes, floor: int = PAD_FLOOR) -> bytes:
    """Pad to a power-of-two bucket, length-prefixed so it is reversible.

    Byte-exact sizes are a training diary written in metadata: a server that
    cannot read a single row still sees which days were heavy.
    """
    body = len(blob).to_bytes(8, "big") + blob
    return body + b"\0" * (bucket(len(body), floor) - len(body))


def unpad(blob: bytes) -> bytes:
    if len(blob) < 8:
        raise ValueError("a padded blob carries an 8-byte length prefix and "
                         "this one is shorter than that")
    size = int.from_bytes(blob[:8], "big")
    if size > len(blob) - 8:
        raise ValueError(f"the length prefix says {size} bytes and only "
                         f"{len(blob) - 8} follow - the blob is truncated")
    return blob[8:8 + size]


def plan_upload(key: bytes, name: str, contents: bytes,
                cipher: Cipher | None) -> tuple[str, bytes]:
    """(blob id, blob) for one file - and the one place plaintext stops.

    REFUSES without a cipher. Not "warns": an unencrypted blob handed to a
    provider is indistinguishable from an encrypted one once it has left, and
    the failure is silent and permanent. The way to send plaintext is to pass
    a cipher that does not encrypt, which is a sentence someone has to write
    down.
    """
    if cipher is None:
        raise ValueError(
            "no cipher: vitai will not hand a transport anything it has not "
            "sealed. The standard library has no authenticated encryption and "
            "this engine does not hand-roll one, so a cipher is something you "
            "supply - see docs on the Cipher contract")
    sealed = cipher.seal(key, pad(contents))
    return blob_id(key, name), sealed


def plan_download(key: bytes, name: str, blob: bytes,
                  cipher: Cipher | None) -> bytes | None:
    """The reverse. None when the blob does not open under this key."""
    if cipher is None:
        raise ValueError("no cipher: a blob written by vitai is sealed, and "
                         "opening it needs the cipher that sealed it")
    opened = cipher.open(key, blob)
    return None if opened is None else unpad(opened)


# --- the bundled implementations, which are ordinary implementations ------------

class DirectoryTransport:
    """A local directory. The golden path, and nothing more than that."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, blob_id: str) -> Path:
        # An ALLOWLIST, not a check for separators. Rejecting only `/` and
        # `\` let `blob:` through as the root itself - which wrote a file
        # where the directory should be and bricked the store - and `blob:..`
        # through as its parent. A NUL crashed. And an id ending `.part` was
        # storable but invisible to `list`, so it vanished from every restore.
        body = blob_id[len(PREFIX):] if blob_id.startswith(PREFIX) else ""
        if not body or not _SAFE_BODY.match(body):
            raise ValueError(
                f"{blob_id!r} is not a blob id this transport can store. An "
                "id is opaque and is never a path: letters, digits and "
                "hyphens, 1 to 128 characters")
        return self.root / body

    def put(self, blob_id: str, blob: bytes) -> None:
        path = self._path(blob_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(blob)
        tmp.replace(path)

    def get(self, blob_id: str) -> bytes | None:
        path = self._path(blob_id)
        return path.read_bytes() if path.is_file() else None

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.exists():
            return []
        return sorted(PREFIX + p.name for p in self.root.iterdir()
                      if p.is_file() and not p.name.endswith(".part")
                      and (PREFIX + p.name).startswith(prefix))

    def delete(self, blob_id: str) -> None:
        self._path(blob_id).unlink(missing_ok=True)


class MemoryTransport:
    """No filesystem at all.

    Here to prove the engine assumes nothing about a path - an interface with
    one implementation is a refactor waiting to happen, and the one that
    catches a hidden assumption is the one shaped least like the first.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, blob_id: str, blob: bytes) -> None:
        self._blobs[blob_id] = blob

    def get(self, blob_id: str) -> bytes | None:
        return self._blobs.get(blob_id)

    def list(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._blobs if k.startswith(prefix))

    def delete(self, blob_id: str) -> None:
        self._blobs.pop(blob_id, None)


class MirrorTransport:
    """Writes to several transports and reads from the first that answers.

    Which is also what a BACKUP is: a second transport configured for
    retention rather than convergence. There is no backup subsystem here
    because there does not need to be one - that falls out of #105's
    append-only content-addressed blob set rather than being designed.
    """

    def __init__(self, *legs: Transport) -> None:
        if not legs:
            raise ValueError("a mirror needs at least one transport")
        self.legs = legs

    def put(self, blob_id: str, blob: bytes) -> None:
        # EVERY leg is attempted and every failure is named. Stopping at the
        # first exception left the mirror silently diverged - `get` and
        # `list` both answered from the leg that HAD worked, so every read
        # path reported success while the backup leg was empty. On the
        # component whose whole job is to be the backup.
        failed = []
        for leg in self.legs:
            try:
                leg.put(blob_id, blob)
            except Exception as e:  # noqa: BLE001 - re-raised together below
                failed.append(f"{type(leg).__name__}: {e}")
        if failed:
            raise OSError(
                f"{blob_id} reached {len(self.legs) - len(failed)} of "
                f"{len(self.legs)} legs and the mirror is now divergent: "
                + "; ".join(failed))

    def get(self, blob_id: str) -> bytes | None:
        for leg in self.legs:
            if (blob := leg.get(blob_id)) is not None:
                return blob
        return None

    def list(self, prefix: str = "") -> list[str]:
        return sorted({b for leg in self.legs for b in leg.list(prefix)})

    def delete(self, blob_id: str) -> None:
        failed = []
        for leg in self.legs:
            try:
                leg.delete(blob_id)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{type(leg).__name__}: {e}")
        if failed:
            # The mirror image of the put case: a half-deleted blob comes
            # back through the union on the next read.
            raise OSError(
                f"{blob_id} was deleted from only "
                f"{len(self.legs) - len(failed)} of {len(self.legs)} legs, so "
                "it will reappear through the surviving one: "
                + "; ".join(failed))


class FileCustody:
    """A key in a file. The working copy, and the simplest thing that works."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def retrieve(self) -> bytes | None:
        try:
            key = bytes.fromhex(self.path.read_text().strip())
        except (OSError, ValueError):
            return None
        # `bytes.fromhex("")` is `b""`, which is not None - so an empty or
        # whitespace-only key file made `verify()` answer True. That is
        # precisely the "custody backend that has silently stopped working"
        # the drill exists to catch, reporting itself as healthy.
        return key or None

    def store(self, key: bytes) -> None:
        import os

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Created 0600, not created-then-chmodded. Writing first left the key
        # world-readable for the window between the two calls, and left it
        # that way permanently if anything crashed in between.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key.hex())

    def verify(self) -> bool:
        return self.retrieve() is not None


class EnvCustody:
    """A key from the environment - a different trust model, not a lesser one.

    Here because two implementations are what make the interface real. This
    one cannot `store`, and that is the interesting part: a custody backend
    that is read-only is a legitimate shape, and the conformance suite has to
    say so rather than assuming every backend can write.
    """

    READONLY = "this custody backend reads an environment variable and cannot "\
               "write one - set it in the environment that starts vitai"

    def __init__(self, variable: str, environ: dict[str, str] | None = None
                 ) -> None:
        self.variable = variable
        self._environ = environ

    def _env(self) -> dict[str, str]:
        import os
        return self._environ if self._environ is not None else dict(os.environ)

    def retrieve(self) -> bytes | None:
        try:
            key = bytes.fromhex(self._env().get(self.variable, ""))
        except ValueError:
            return None
        # An UNSET variable read as `b""`, so `verify()` said True on a
        # backend holding nothing at all.
        return key or None

    def store(self, key: bytes) -> None:
        raise NotImplementedError(self.READONLY)

    def verify(self) -> bool:
        return self.retrieve() is not None
