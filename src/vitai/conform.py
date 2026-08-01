"""The conformance suite: what makes the interface real (#108).

A written contract produces implementations that mostly work and fail
strangely. A conformance suite produces implementations that either pass or do
not, and that is the difference between "anyone can implement" and "anyone can
implement CORRECTLY".

**The bundled implementations run this as ordinary implementations.** That is
the whole test of whether the layering is real: every layered architecture
that failed did so because the first-party version quietly used a capability
the interface never exposed, and third parties could never quite match it. If
the bundled transport can do something an athlete's own S3 bucket cannot, the
interface is decoration.

Deterministic and stdlib-only, like everything else - a conformance suite that
needs a test framework is one a third party has to adopt a test framework to
run.
"""

from __future__ import annotations

from .sync import PREFIX

# Bytes chosen to break a transport that assumes text: a NUL, a newline, a
# lone high byte that is not valid UTF-8, and something long enough to cross a
# buffer. A transport that round-trips ASCII and mangles these is one that
# will corrupt a sealed blob, which is exactly what nobody notices until a
# restore.
PROBES: tuple[bytes, ...] = (
    b"",
    b"\x00",
    b"\n\r\n",
    b"\xff\xfe\xfd",
    bytes(range(256)) * 40,
)


def _case(name: str, ok: bool, detail: str = "") -> dict:
    return {"case": name, "ok": ok, "detail": detail}


# The suite writes and deletes, so it must never be able to touch a real blob.
# Ids live in their own namespace, generated here rather than supplied: taking
# a caller's `sample_id` and mutating its last byte meant pointing the suite at
# a live store OVERWROTE the athlete's blobs whose ids happened to end 00-04,
# and left the probes behind to be treated as real by the next restore.
NAMESPACE = "conformance-probe-"


def probe_ids(count: int) -> list[str]:
    return [f"{PREFIX}{NAMESPACE}{i:02x}" for i in range(count)]


def transport(impl, sample_id: str | None = None) -> list[dict]:
    """Every case a transport must satisfy. Returns findings, never raises.

    NON-DESTRUCTIVE: every id is in the conformance namespace and everything
    written is removed at the end, so this is safe to run against a live
    store. `sample_id` is accepted and ignored, kept only so an existing
    caller does not break.

    It never needs the athlete's key either - a third party can run it against
    their own transport with no record present at all.
    """
    ids = probe_ids(len(PROBES) + 2)
    out: list[dict] = []

    for blob_id, probe in zip(ids, PROBES):
        try:
            impl.put(blob_id, probe)
            got = impl.get(blob_id)
        except Exception as e:  # noqa: BLE001 - a contract report, not a crash
            out.append(_case(f"round-trip {len(probe)}B", False, repr(e)))
            continue
        out.append(_case(
            f"round-trip {len(probe)}B", got == probe,
            "" if got == probe else
            "get returned something other than exactly what put stored - a "
            "transport that transforms bytes will corrupt a sealed blob"))

    # Idempotence: the same id and the same bytes is a no-op, because a sync
    # runs repeatedly and must not accumulate copies.
    try:
        # A NON-EMPTY probe. Using the empty one let a transport that APPENDS
        # on a duplicate put pass - `b"" + b"" == b""` - which is exactly the
        # accumulating-copies failure this case is named for.
        twice = b"the same bytes, twice"
        impl.put(ids[-1], twice)
        impl.put(ids[-1], twice)
        got = impl.get(ids[-1])
        out.append(_case("idempotent put", got == twice,
                         "" if got == twice else
                         "putting the same id and bytes twice must be a "
                         "no-op - a sync runs repeatedly"))
    except Exception as e:  # noqa: BLE001
        out.append(_case("idempotent put", False, repr(e)))

    # Overwrite: the same id with DIFFERENT bytes takes the new ones. Blob ids
    # are derived from a filename, and a file's contents change every append.
    try:
        impl.put(ids[1], b"first")
        impl.put(ids[1], b"second")
        got = impl.get(ids[1])
        out.append(_case("overwrite", got == b"second",
                         "" if got == b"second" else
                         "an id must carry the LATEST bytes put under it - a "
                         "file's contents change on every append"))
    except Exception as e:  # noqa: BLE001
        out.append(_case("overwrite", False, repr(e)))

    try:
        listed = set(impl.list())
        out.append(_case("list includes what was put",
                         set(ids[:2]) <= listed))
        out.append(_case("list respects a prefix",
                         set(impl.list("nope:")) == set()))
    except Exception as e:  # noqa: BLE001
        out.append(_case("list", False, repr(e)))

    try:
        impl.delete(ids[0])
        out.append(_case("delete removes", impl.get(ids[0]) is None))
        impl.delete(ids[0])
        out.append(_case("delete is idempotent", True))
    except Exception as e:  # noqa: BLE001
        out.append(_case("delete", False, repr(e)))

    try:
        missing = impl.get(f"{PREFIX}{NAMESPACE}absent")
        out.append(_case("absent reads as None", missing is None,
                         "" if missing is None else
                         "a blob that was never stored must read as absent, "
                         "not raise - a restore walks ids it may not have"))
    except Exception as e:  # noqa: BLE001
        out.append(_case("absent reads as None", False, repr(e)))

    # Leave nothing behind. A suite that litters a live store leaves blobs a
    # later restore would treat as real.
    for blob_id in ids:
        try:
            impl.delete(blob_id)
        except Exception:  # noqa: BLE001 - reported by the delete case above
            pass
    return out


def custody(impl) -> list[dict]:
    """Every case a custody backend must satisfy.

    A READ-ONLY backend is legitimate - a key held in the environment, or on
    paper - so `store` raising `NotImplementedError` is a pass. What is not
    legitimate is `verify` disagreeing with `retrieve`, because that is the
    check a scheduled restore drill relies on.
    """
    out: list[dict] = []
    key = bytes(range(32))

    # PUT BACK whatever was there. `vitai conform --custody file --at
    # <where the real key lives>` overwrote it with the probe key, and every
    # sealed blob became unrecoverable - a diagnostic tool destroying the one
    # secret it exists to check.
    prior = None
    try:
        prior = impl.retrieve()
    except Exception:  # noqa: BLE001 - reported by the retrieve case below
        pass

    writable = True
    try:
        impl.store(key)
    except NotImplementedError:
        writable = False
        out.append(_case("store", True, "read-only backend, which is a "
                                        "legitimate shape"))
    except Exception as e:  # noqa: BLE001
        out.append(_case("store", False, repr(e)))
    else:
        out.append(_case("store", True))

    try:
        got = impl.retrieve()
    except Exception as e:  # noqa: BLE001
        out.append(_case("retrieve", False, repr(e)))
        return out

    if writable:
        out.append(_case("retrieve returns what was stored", got == key,
                         "" if got == key else
                         "a key that comes back different is a key that will "
                         "not open anything, and nothing says so until a "
                         "restore"))
    agrees = impl.verify() == (got is not None)
    out.append(_case(
        "verify agrees with retrieve", agrees,
        "" if agrees else
        "verify is what a scheduled drill relies on - a backend that has "
        "silently stopped working is exactly the failure that stays invisible "
        "until it matters"))

    if writable and prior is not None and prior != key:
        try:
            impl.store(prior)
        except Exception as e:  # noqa: BLE001
            out.append(_case("restores the prior key", False, repr(e)))
        else:
            out.append(_case("restores the prior key",
                             impl.retrieve() == prior))
    return out


def failures(findings: list[dict]) -> list[dict]:
    return [f for f in findings if not f["ok"]]


def drill(records: dict[str, bytes], key: bytes, cipher, transport_impl,
          custody_impl) -> dict:
    """The restore drill: can this record actually be recovered?

    #107's point, and the reason it is an engine capability rather than a
    setup step. The failure mode is not "the athlete never stored the key" -
    it is "the athlete BELIEVED they stored it". A key pasted into a note app
    that later syncs to a dead account feels like storage and is not.

    So the drill is: put the record through custody and transport, get it back
    the same way, and compare. It runs while the record is empty and costs
    nothing, and it is the only evidence the loop closes.
    """
    from .sync import blob_id, plan_download, plan_upload

    problems: list[str] = []
    restored = 0
    if not custody_impl.verify():
        return {"ok": False, "restored": 0,
                "problems": ["custody cannot produce a key right now, so "
                             "nothing sealed under it could be recovered - "
                             "this is the drill's whole purpose and it has "
                             "already failed"]}
    held = custody_impl.retrieve()
    if held != key:
        problems.append(
            "custody returned a different key from the one in use: anything "
            "sealed under the current key would not open after a restore")

    for name, contents in sorted(records.items()):
        try:
            ident, blob = plan_upload(key, name, contents, cipher)
            transport_impl.put(ident, blob)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}: upload failed: {e!r}")
            continue
        fetched = transport_impl.get(blob_id(held or key, name))
        if fetched is None:
            problems.append(f"{name}: not retrievable after upload - the id "
                            "derived on the way back does not match the one "
                            "it was stored under")
            continue
        try:
            back = plan_download(held or key, name, fetched, cipher)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}: could not be opened: {e!r}")
            continue
        if back != contents:
            problems.append(f"{name}: restored bytes differ from the original")
        else:
            restored += 1

    # Counted from the records that came back, not `len(records) - problems`:
    # a key mismatch adds a problem that is not about any one record, and the
    # subtraction reported restoring -1 of them.
    return {"ok": not problems, "restored": restored, "problems": problems}
