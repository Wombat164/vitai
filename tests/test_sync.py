"""Transport, custody and cipher as engine interfaces (#108).

Synthetic data only (public repo). The load-bearing test here is not that the
bundled implementations work - it is that they pass the SAME suite a third
party's would, with no privileged access. Every layered architecture that
failed did so because the first-party version quietly used a capability the
interface never exposed.
"""

import ast
import hashlib
import os
from pathlib import Path

import pytest

from vitai import conform, sync
from vitai.cli import main
from helpers_cipher import ToyCipher
from vitai.sync import (DirectoryTransport, EnvCustody, FileCustody,
                        MemoryTransport, MirrorTransport, blob_id, pad,
                        plan_download, plan_upload, unpad)


KEY = bytes(range(32))


# ---- the test that decides whether the interface is real -------------------------------

@pytest.mark.parametrize("build", [
    lambda tmp: DirectoryTransport(tmp),
    lambda tmp: MemoryTransport(),
    lambda tmp: MirrorTransport(DirectoryTransport(tmp), MemoryTransport()),
])
def test_every_bundled_transport_passes_the_same_suite(build, tmp_path):
    """The bundled implementations are ORDINARY implementations. If one could
    do something a third party's could not, the interface is decoration."""
    assert conform.failures(conform.transport(build(tmp_path))) == []


@pytest.mark.parametrize("build", [
    lambda tmp: FileCustody(tmp / "key"),
    lambda tmp: EnvCustody("K", {"K": KEY.hex()}),
])
def test_every_bundled_custody_passes_the_same_suite(build, tmp_path):
    assert conform.failures(conform.custody(build(tmp_path))) == []


def test_at_least_two_of_each_ship():
    """An interface with a single implementation is a refactor waiting to
    happen. The one that catches a hidden assumption is the one shaped least
    like the first, which is why a memory transport is here at all."""
    transports = [n for n in dir(sync) if n.endswith("Transport")]
    custodies = [n for n in dir(sync) if n.endswith("Custody")]
    assert len(transports) >= 2, transports
    assert len(custodies) >= 2, custodies


def test_nothing_reaches_into_a_transport_beyond_the_contract():
    """Asserted over the PARSED source rather than by reading: if anything
    here touches a transport's internals, a third party can never match the
    bundled one and the interface is decoration.

    The contract is four methods. `conform.transport` and `conform.drill` are
    the two places an implementation is actually driven, so they are where a
    privileged shortcut would live.
    """
    contract = {"put", "get", "list", "delete", "retrieve", "store", "verify",
                "seal", "open"}
    for module in (sync, conform):
        tree = ast.parse(Path(module.__file__).read_text())
        # Exempt by SCOPE, not by function name. Exempting anything called
        # `put`/`get`/`list`/`delete` meant a privileged access hidden in a
        # helper with one of those names passed - so the exemption is now
        # "defined inside an implementation class", which a helper in
        # `conform` or a module-level engine function cannot claim.
        inside = {n for cls in ast.walk(tree)
                  if isinstance(cls, ast.ClassDef)
                  for n in ast.walk(cls) if isinstance(n, ast.FunctionDef)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node in inside:
                continue
            for call in ast.walk(node):
                # Any attribute that is not part of a contract, and any
                # dynamic reach - `getattr(impl, "_blobs")` slipped straight
                # past a fixed list of private names.
                if isinstance(call, ast.Attribute):
                    target = call.value
                    reaches_self = (isinstance(target, ast.Name)
                                    and target.id in {"self", "sync", "conform"})
                    assert reaches_self or call.attr in contract \
                        or not isinstance(target, ast.Name) \
                        or target.id not in {"impl", "transport_impl",
                                             "custody_impl", "leg"}, (
                            f"{module.__name__}.{node.name} reaches for "
                            f"{call.attr!r} on an implementation")
                if isinstance(call, ast.Call) and isinstance(
                        call.func, ast.Name) and call.func.id == "getattr":
                    arg = call.args[0] if call.args else None
                    assert not (isinstance(arg, ast.Name) and arg.id in {
                        "impl", "transport_impl", "custody_impl"}), (
                        f"{module.__name__}.{node.name} reaches into an "
                        "implementation dynamically")


def test_the_contract_is_exactly_four_methods():
    """A fifth would be the one a third party cannot implement."""
    assert {m for m in dir(sync.Transport) if not m.startswith("_")} == {
        "put", "get", "list", "delete"}
    assert {m for m in dir(sync.Custody) if not m.startswith("_")} == {
        "retrieve", "store", "verify"}


# ---- the transport never sees plaintext -------------------------------------------------

def test_a_transport_is_never_handed_anything_unsealed():
    """REFUSES, not warns. An unencrypted blob handed to a provider is
    indistinguishable from an encrypted one once it has left, and the failure
    is silent and permanent."""
    with pytest.raises(ValueError, match="no cipher"):
        plan_upload(KEY, "weight.jsonl", b"80.0 kg", cipher=None)
    with pytest.raises(ValueError, match="no cipher"):
        plan_download(KEY, "weight.jsonl", b"...", cipher=None)


def test_no_cipher_ships():
    """The standard library has no authenticated encryption, and hand-rolling
    one is how this goes wrong. So the contract exists and no implementation
    does - a refusal rather than a gap.
    """
    import inspect
    for name, obj in vars(sync).items():
        if not inspect.isclass(obj) or name == "Cipher":
            continue
        assert not (hasattr(obj, "seal") and hasattr(obj, "open")), (
            f"{name} looks like a bundled cipher, which this engine must not "
            "ship while the standard library has no AEAD")


def test_the_plaintext_never_reaches_the_stored_blob(tmp_path):
    plain = b"the athlete weighed 80.0 kg on a Tuesday"
    ident, blob = plan_upload(KEY, "weight.jsonl", plain, ToyCipher())
    DirectoryTransport(tmp_path).put(ident, blob)
    on_disk = b"".join(p.read_bytes() for p in tmp_path.iterdir())
    assert plain not in on_disk
    assert b"80.0" not in on_disk


# ---- what the engine decides ---------------------------------------------------------------

def test_a_blob_id_is_not_computable_without_the_key():
    """A plain hash of the name would be: the filenames are a short,
    guessable set, and a server could hash the obvious candidates."""
    name = "sessions.phone.jsonl"
    assert blob_id(KEY, name) != blob_id(bytes(32), name)
    assert hashlib.sha256(name.encode()).hexdigest() not in blob_id(KEY, name)


def test_a_blob_id_is_deterministic_so_a_sync_does_not_accumulate_copies():
    assert blob_id(KEY, "weight.jsonl") == blob_id(KEY, "weight.jsonl")
    assert blob_id(KEY, "weight.jsonl") != blob_id(KEY, "daily.jsonl")


def test_a_blob_id_needs_a_key():
    with pytest.raises(ValueError, match="own key"):
        blob_id(b"", "weight.jsonl")


def test_the_name_never_appears_on_the_wire():
    """`sessions.phone.jsonl` discloses that the athlete trains and owns two
    devices. A ciphertext-only server still learns holidays and illness
    unless the names are opaque too (#106)."""
    ident = blob_id(KEY, "sessions.phone.jsonl")
    for fragment in ("sessions", "phone", "jsonl"):
        assert fragment not in ident


@pytest.mark.parametrize("payload", [b"", b"x", b"\x00" * 10,
                                     bytes(range(256)) * 40])
def test_padding_is_exactly_reversible(payload):
    assert unpad(pad(payload)) == payload
    assert len(pad(payload)) == sync.bucket(len(payload) + 8)


def test_padding_hides_a_days_variation():
    """Byte-exact sizes are a training diary written in metadata: a server
    that cannot read a row still sees which days were heavy."""
    quiet, busy = pad(b"x" * 20), pad(b"x" * 900)
    assert len(quiet) == len(busy)


def test_a_truncated_blob_is_named_rather_than_returning_short_bytes():
    with pytest.raises(ValueError, match="truncated"):
        unpad((50).to_bytes(8, "big") + b"short")
    with pytest.raises(ValueError, match="length prefix"):
        unpad(b"abc")


def test_a_blob_that_does_not_open_under_this_key_reads_as_None():
    _, blob = plan_upload(KEY, "weight.jsonl", b"80.0", ToyCipher())
    assert plan_download(bytes(32), "weight.jsonl", blob, ToyCipher()) is None


# ---- backup is a transport, not a subsystem --------------------------------------------------

def test_a_backup_is_a_second_transport_configured_for_retention(tmp_path):
    """With a content-addressed append-only blob set, a backup is a copy of
    the blob set at a point in time. There is no backup interface here
    because there does not need to be one."""
    live = DirectoryTransport(tmp_path / "live")
    archive = DirectoryTransport(tmp_path / "archive")
    both = MirrorTransport(live, archive)
    ident, blob = plan_upload(KEY, "weight.jsonl", b"80.0", ToyCipher())
    both.put(ident, blob)

    # The live copy is lost; restore is `list()` plus `get()` on the other.
    live.delete(ident)
    assert live.get(ident) is None
    assert archive.list() == [ident]
    assert plan_download(KEY, "weight.jsonl", archive.get(ident),
                         ToyCipher()) == b"80.0"


def test_a_mirror_reads_from_whichever_leg_still_has_it(tmp_path):
    live = DirectoryTransport(tmp_path / "live")
    archive = MemoryTransport()
    both = MirrorTransport(live, archive)
    ident, blob = plan_upload(KEY, "weight.jsonl", b"80.0", ToyCipher())
    both.put(ident, blob)
    live.delete(ident)
    assert both.get(ident) == blob


# ---- the drill --------------------------------------------------------------------------------

def test_the_drill_proves_the_loop_closes(tmp_path):
    """The failure mode is not "never stored the key" - it is "BELIEVED they
    stored it". A key pasted into a note app that later syncs to a dead
    account feels like storage and is not."""
    custody = FileCustody(tmp_path / "key")
    custody.store(KEY)
    got = conform.drill({"weight.jsonl": b"80.0", "daily.jsonl": b"steps"},
                        KEY, ToyCipher(), MemoryTransport(), custody)
    assert got["ok"] and got["restored"] == 2 and got["problems"] == []


def test_the_drill_fails_when_custody_cannot_produce_a_key(tmp_path):
    got = conform.drill({"weight.jsonl": b"80.0"}, KEY, ToyCipher(),
                        MemoryTransport(), FileCustody(tmp_path / "absent"))
    assert got["ok"] is False
    assert "already failed" in got["problems"][0]


def test_the_drill_catches_custody_holding_the_wrong_key(tmp_path):
    """The quiet one: everything looks fine until a restore, because the key
    that seals is not the key that comes back."""
    custody = FileCustody(tmp_path / "key")
    custody.store(bytes(32))
    got = conform.drill({"weight.jsonl": b"80.0"}, KEY, ToyCipher(),
                        MemoryTransport(), custody)
    assert got["ok"] is False
    assert any("different key" in p for p in got["problems"])


# ---- the suite catches a bad implementation ----------------------------------------------------

def test_a_transport_that_mangles_bytes_fails():
    """A transport that round-trips ASCII and corrupts a high byte will
    corrupt a sealed blob - which is exactly what nobody notices until a
    restore."""
    class Lossy(MemoryTransport):
        def put(self, blob_id, blob):
            super().put(blob_id, blob.decode("utf-8", "ignore").encode())

    assert conform.failures(conform.transport(Lossy()))


def test_a_transport_that_raises_on_a_missing_blob_fails():
    """A restore walks ids it may not have."""
    class Strict(MemoryTransport):
        def get(self, blob_id):
            got = super().get(blob_id)
            if got is None:
                raise KeyError(blob_id)
            return got

    failed = conform.failures(conform.transport(Strict()))
    assert any("absent" in f["case"] for f in failed)


def test_a_transport_that_never_overwrites_fails():
    """A blob id is derived from a filename, and a file's contents change on
    every append."""
    class WriteOnce(MemoryTransport):
        def put(self, blob_id, blob):
            if super().get(blob_id) is None:
                super().put(blob_id, blob)

    failed = conform.failures(conform.transport(WriteOnce()))
    assert any(f["case"] == "overwrite" for f in failed)


def test_a_custody_whose_verify_lies_fails():
    """`verify` is what a scheduled drill relies on."""
    class Liar(MemoryTransport):
        def retrieve(self):
            return None

        def store(self, key):
            pass

        def verify(self):
            return True

    assert any("verify" in f["case"] for f in conform.failures(
        conform.custody(Liar())))


def test_a_read_only_custody_is_a_pass_not_a_failure():
    """A key held in the environment, or on paper, is a legitimate shape -
    and the suite has to say so rather than assuming every backend writes."""
    findings = conform.custody(EnvCustody("K", {"K": KEY.hex()}))
    assert conform.failures(findings) == []
    assert any("read-only" in f["detail"] for f in findings)


# ---- the surface ---------------------------------------------------------------------------------

def test_the_cli_runs_a_contract_against_a_bundled_implementation(tmp_path,
                                                                  capsys):
    capsys.readouterr()
    main(["conform", "--transport", "memory", "--at", str(tmp_path)])
    assert "conformance: clean" in capsys.readouterr().out


def test_the_cli_resolves_a_third_party_implementation_by_dotted_path(
        tmp_path, monkeypatch, capsys):
    """The proof that a third party's implementation is reached the same way
    the bundled ones are - resolved by name, constructed, handed to the same
    suite. If the golden path had a shortcut, the interface would be
    decoration.
    """
    (tmp_path / "outside.py").write_text(
        "from vitai.sync import MemoryTransport\n"
        "class Mine(MemoryTransport):\n"
        "    pass\n"
        "class Lossy(MemoryTransport):\n"
        "    def put(self, blob_id, blob):\n"
        "        MemoryTransport.put(self, blob_id, blob[:-1] if blob else blob)\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    capsys.readouterr()
    main(["conform", "--transport", "outside.Mine", "--at", str(tmp_path)])
    assert "conformance: clean" in capsys.readouterr().out

    with pytest.raises(SystemExit, match="contract case"):
        main(["conform", "--transport", "outside.Lossy",
              "--at", str(tmp_path)])


def test_an_unresolvable_implementation_says_so(tmp_path):
    with pytest.raises(SystemExit, match="neither a bundled"):
        main(["conform", "--transport", "nonesuch", "--at", str(tmp_path)])


def test_the_cli_needs_something_to_conform(tmp_path):
    with pytest.raises(SystemExit, match="needs --transport or --custody"):
        main(["conform", "--at", str(tmp_path)])


# ---- what the review of this feature found ------------------------------------------

def test_the_suite_never_destroys_the_key_it_exists_to_check(tmp_path):
    """`vitai conform --custody file --at <where the real key lives>` wrote
    the probe key over it, and every sealed blob became unrecoverable. A
    diagnostic tool destroying the one secret it is diagnosing.
    """
    real = FileCustody(tmp_path / "key")
    real.store(KEY)
    assert conform.failures(conform.custody(real)) == []
    assert real.retrieve() == KEY


def test_the_suite_leaves_a_live_store_exactly_as_it_found_it(tmp_path):
    """It took a caller's id and mutated its last byte, so pointing it at a
    live store overwrote real blobs and left the probes behind to be treated
    as real by the next restore."""
    live = DirectoryTransport(tmp_path)
    mine = blob_id(KEY, "weight.jsonl")
    live.put(mine, b"real data")
    before = set(live.list())
    assert conform.failures(conform.transport(live, sample_id=mine)) == []
    assert live.get(mine) == b"real data"
    assert set(live.list()) == before


def test_an_unset_custody_backend_does_not_report_itself_healthy():
    """`bytes.fromhex("")` is `b""`, which is not None - so `verify()` said
    True on a backend holding nothing at all, which is precisely the silent
    failure the drill exists to catch."""
    assert EnvCustody("NOTHING", {}).verify() is False
    assert EnvCustody("NOTHING", {}).retrieve() is None


def test_an_empty_key_file_does_not_report_itself_healthy(tmp_path):
    (tmp_path / "key").write_text("   \n", encoding="utf-8")
    assert FileCustody(tmp_path / "key").verify() is False


@pytest.mark.parametrize("bad", ["blob:", "blob:..", "blob:a/b", "blob:a\\b",
                                 "blob:x.part", "blob:\x00", "blob:" + "x" * 200,
                                 "notablob"])
def test_a_blob_id_can_never_become_a_path(bad, tmp_path):
    """Rejecting only separators let `blob:` through as the ROOT - which
    wrote a file where the directory should be and bricked the store - and
    `blob:..` through as its parent. An id ending `.part` was storable and
    invisible to `list`, so it vanished from every restore."""
    with pytest.raises(ValueError, match="blob id"):
        DirectoryTransport(tmp_path).put(bad, b"x")


def test_a_mirror_says_so_when_it_diverges(tmp_path):
    """Stopping at the first failure left `get` and `list` both answering
    from the leg that HAD worked, so every read path reported success while
    the backup leg was empty."""
    class Broken:
        def put(self, blob_id, blob):
            raise OSError("the archive is unreachable")

        def get(self, blob_id):
            return None

        def list(self, prefix=""):
            return []

        def delete(self, blob_id):
            raise OSError("the archive is unreachable")

    both = MirrorTransport(MemoryTransport(), Broken())
    ident = blob_id(KEY, "weight.jsonl")
    with pytest.raises(OSError, match="divergent"):
        both.put(ident, b"sealed")
    with pytest.raises(OSError, match="reappear"):
        both.delete(ident)


def test_padding_bounds_the_leak_to_a_ratio_not_four_kilobytes():
    """Rounding to a multiple of 4 KiB hides nothing once a file is past a
    few KiB: an append-only sessions file leaks its growth every sync. A file
    only changes bucket when it DOUBLES."""
    from vitai.sync import bucket
    assert len(pad(b"x" * 100_000)) == len(pad(b"x" * 120_000))
    assert bucket(5000) == 8192 and bucket(9000) == 16384
    for size in (0, 1, 4088, 4089, 100_000):
        assert len(pad(b"x" * size)) & (len(pad(b"x" * size)) - 1) == 0


@pytest.mark.skipif(os.name != "posix",
                    reason="Windows does not model these bits, which is a "
                           "real limitation of this backend there rather "
                           "than a property to assert away - see protected()")
def test_the_key_file_is_never_briefly_world_readable(tmp_path):
    """Writing then chmodding left the key readable in between, and left it
    that way permanently if anything crashed in the window."""
    import stat
    path = tmp_path / "key"
    FileCustody(path).store(KEY)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & 0o077 == 0, oct(mode)
    assert FileCustody(path).protected() is True


def test_a_backend_that_cannot_protect_the_key_says_so(tmp_path):
    """`protected` is a different question from `verify`: whether anyone ELSE
    can read the key, not whether the athlete can. Conflating them would let
    a world-readable key report itself as fine, and on Windows this backend
    genuinely cannot protect it.
    """
    path = tmp_path / "key"
    custody = FileCustody(path)
    custody.store(KEY)
    assert custody.verify() is True
    assert custody.protected() is (os.name == "posix")
    if os.name == "posix":
        path.chmod(0o644)
        assert custody.verify() is True, "still retrievable"
        assert custody.protected() is False, "and no longer private"


def test_a_transport_that_appends_on_a_duplicate_put_fails():
    """The idempotence case used the EMPTY probe, so a transport that
    appended passed it - `b"" + b"" == b""` - which is the accumulating-copies
    failure the case is named for."""
    class Appending(MemoryTransport):
        def put(self, blob_id, blob):
            MemoryTransport.put(self, blob_id,
                                (MemoryTransport.get(self, blob_id) or b"")
                                + blob)

    failed = conform.failures(conform.transport(Appending()))
    assert any(f["case"] == "idempotent put" for f in failed)


def test_the_drill_never_reports_restoring_a_negative_number(tmp_path):
    custody = FileCustody(tmp_path / "key")
    custody.store(bytes(32))
    got = conform.drill({"weight.jsonl": b"80.0"}, KEY, ToyCipher(),
                        MemoryTransport(), custody)
    assert got["restored"] >= 0
