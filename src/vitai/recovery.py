"""Key custody as a product surface: an untested backup is not a backup (#107).

HYOK is settled (#106): the athlete holds the key, the service cannot decrypt,
there is no recovery path. That makes custody a product surface rather than a
footnote - the tool is now responsible for getting someone to hold a secret
correctly, forever, with no safety net.

## The thing that matters more than which manager to recommend

**The failure mode is not "never stored the key". It is "BELIEVED they stored
it".** A key pasted into a note app that later syncs to a dead account, a
screenshot on a phone that gets wiped, a password manager whose master
password was itself never written down. Each of those feels like storage and
is not.

So the athlete has to PROVE recovery, at setup, before any data exists worth
losing - and again after any rotation. A restore drill run while the record is
empty costs nothing and is the only evidence the loop closes. Everything else
here is secondary to that, which is why `setup` cannot return success without
one.

## Two forms, not two options

A 256-bit key is 64 hex characters. Nobody transcribes that correctly, and a
single-character error is indistinguishable from a wrong key - so the athlete
learns their backup was bad at the only moment it matters.

- **A checksummed phrase**, for paper. Transcribable by hand and VERIFIABLE on
  entry: a typo is detected and reported as a typo rather than silently
  producing garbage that will not open anything.
- **The raw key**, for a password manager. The working copy.

Both, never either. A design that offers only the second has made the password
manager a single point of failure for a decade of health history, and
`single_point_of_failure` says so rather than leaving the athlete to notice.

## Why not BIP-39 words, yet

A word list is the better paper form - words are easier to transcribe than
characters, and BIP-39 is the obvious prior art. It is not vendored here
because its wordlist's licence has not been checked, and this repo's rule is
to check before vendoring rather than after (the same discipline that kept
Open Food Facts out of a shipped table and wger out of the exercise registry).

So the phrase uses Crockford's base32, which is designed for exactly this
problem: it excludes I, L, O and U so the characters that get confused on
paper cannot occur, and it is case-insensitive. It is a worse phrase than
words and an honest one, and swapping it for a word list later is a change to
this module alone.
"""

from __future__ import annotations

import re
import secrets

KEY_BYTES = 32

# Crockford's base32: no I, L, O or U. Those are the characters that get
# misread from paper - 1/I/l, 0/O - and excluding them means a transcription
# error becomes an INVALID character rather than a different valid key.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(ALPHABET)}
# The substitutions a human actually makes, folded on the way in. Reading
# these as errors would be technically correct and unhelpful: the athlete
# wrote what they saw.
_CONFUSED = {"I": "1", "L": "1", "O": "0", "U": "V"}

GROUP = 4
CHECK_CHARS = 6

# The BCH checksum from bech32 (BIP-173), applied over THIS alphabet's 5-bit
# values rather than bech32's own characters - the code is over GF(32)
# symbols, so the guarantee travels with the values and not the spelling.
#
# A TRUNCATED HASH IS NOT A CHECKSUM. The first version took four characters
# of sha256, which detects a typo only with probability 2^-20 per candidate:
# across the 1600-odd single-character mutations of one phrase a collision is
# roughly one key in six hundred away, and it produces a VALID DIFFERENT KEY
# with no complaint. That is exactly the failure this whole module exists to
# prevent, so the guarantee has to be structural rather than probabilistic.
#
# This code detects ANY error of up to four characters in a string of this
# length. Not "almost always" - always.
_GEN = (0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)


def _polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ value
        for i, gen in enumerate(_GEN):
            if (top >> i) & 1:
                chk ^= gen
    return chk


def generate() -> bytes:
    """A new key, from the system CSPRNG.

    Never derived from a device identifier or anything guessable: a key that
    can be regenerated from something knowable is not a key, and the whole
    HYOK claim rests on nobody else being able to produce it.
    """
    return secrets.token_bytes(KEY_BYTES)


def _checksum(body: str) -> str:
    values = [_DECODE[c] for c in body] + [0] * CHECK_CHARS
    chk = _polymod(values) ^ 1
    return "".join(ALPHABET[(chk >> 5 * (CHECK_CHARS - 1 - i)) & 31]
                   for i in range(CHECK_CHARS))


def _encode(raw: bytes) -> str:
    width = (len(raw) * 8 + 4) // 5
    # LEFT-ALIGNED into the character grid: 32 bytes is 256 bits and 52
    # characters hold 260, so the value is shifted up by the difference and
    # `_decode` shifts it back. Reading the top five bits off an unaligned
    # integer silently produced a phrase that did not round-trip.
    bits = int.from_bytes(raw, "big") << (width * 5 - len(raw) * 8)
    return "".join(ALPHABET[(bits >> (5 * (width - 1 - i))) & 31]
                   for i in range(width))


def _decode(text: str, size: int) -> bytes:
    bits = 0
    for char in text:
        bits = bits * 32 + _DECODE[char]
    width = (size * 8 + 4) // 5
    bits >>= (width * 5 - size * 8)
    return bits.to_bytes(size, "big")


def to_phrase(key: bytes) -> str:
    """The paper form: grouped, checksummed, transcribable by hand."""
    if len(key) != KEY_BYTES:
        raise ValueError(f"a key is {KEY_BYTES} bytes, got {len(key)}")
    body = _encode(key)
    full = body + _checksum(body)
    return "-".join(full[i:i + GROUP] for i in range(0, len(full), GROUP))


def normalise(text: str) -> str:
    """Upper-cased, ungrouped, with the confusable characters folded."""
    out = re.sub(r"[^0-9A-Za-z]", "", str(text or "")).upper()
    return "".join(_CONFUSED.get(c, c) for c in out)


def from_phrase(text: str) -> tuple[bytes | None, str]:
    """(key, "") or (None, what is wrong with it).

    THE point of the checksum: a single-character transcription error is
    reported AS A TYPO, naming where, rather than producing a key that is
    merely different. Without it the athlete finds out their backup was wrong
    at the only moment it matters, and cannot tell a mistyped key from the
    wrong key entirely.
    """
    cleaned = normalise(text)
    if not cleaned:
        return None, "nothing to read - a recovery phrase is letters and digits"

    body_len = (KEY_BYTES * 8 + 4) // 5
    expected = body_len + CHECK_CHARS
    if len(cleaned) != expected:
        short = expected - len(cleaned)
        return None, (
            f"a recovery phrase is {expected} characters and this one has "
            f"{len(cleaned)} - "
            + (f"{short} appear to be missing" if short > 0
               else f"{-short} too many"))

    body, check = cleaned[:body_len], cleaned[body_len:]
    if check != _checksum(body):
        at = _first_difference(body, check)
        if at is not None:
            where = (f" - the error is in group {at // GROUP + 1}, "
                     f"character {at % GROUP + 1}")
        else:
            # No single body character explains it, so the typo is in the
            # check group itself - which is still a typo, and saying "somewhere
            # in the last group" is more use than saying nothing.
            where = (f" - and no single character of the first "
                     f"{len(body) // GROUP} groups explains it, so look at "
                     "the last group")
        return None, (
            "this phrase does not check out, so it was mistyped rather than "
            f"being a different key{where}. Check it against the paper copy")
    return _decode(body, KEY_BYTES), ""


def _first_difference(body: str, check: str) -> int | None:
    """Which position, if changing exactly one character would make it valid.

    Compared against the check characters AS TYPED. Comparing against
    `_checksum(body)` - the checksum of the text that is already known to be
    wrong - can only ever match the unmodified body, so it never found
    anything and the message never named a group.

    A single-character error is the overwhelmingly common one, and naming the
    group turns "this is wrong" into "look at this bit", which is the
    difference between a fixable transcription and a lost decade.
    """
    target = check
    for i, actual in enumerate(body):
        for candidate in ALPHABET:
            if candidate == actual:
                continue
            if _checksum(body[:i] + candidate + body[i + 1:]) == target:
                return i
    return None


def single_point_of_failure(custody_backends: list[object]) -> list[str]:
    """Warnings about where the only copy lives.

    A password manager whose master password is itself unrecorded is one
    forgotten password away from destroying a decade of health history, and
    the athlete will not think of it unless something says so. One copy of
    anything irrecoverable is a warning; one copy in a thing that itself needs
    a secret is a louder one.
    """
    live = [b for b in custody_backends if _verifies(b)]
    if not live:
        return ["no custody backend can produce the key right now, so nothing "
                "sealed under it could be recovered"]
    if len(live) == 1:
        return [
            "the key exists in exactly one place. A manager whose master "
            "password is itself unrecorded is one forgotten password away "
            "from a decade of health history, and there is no recovery path "
            "by design - keep the paper phrase somewhere else as well"]
    return []


def _verifies(backend: object) -> bool:
    try:
        return bool(backend.verify())
    except Exception:  # noqa: BLE001 - a backend that raises has not verified
        return False


def setup(custody_backends: list[object], transport, cipher,
          key: bytes | None = None) -> dict:
    """Generate, store, and PROVE recoverable. Fails if the drill does.

    The drill is not a step that can be skipped for now and done later,
    because "later" is after there is something to lose. It runs here, while
    the record is empty, and `ok` is false without it.
    """
    from .conform import drill

    key = key or generate()
    stored, problems = [], []
    for backend in custody_backends:
        try:
            backend.store(key)
            # READ BACK. A backend whose `store` merely does not raise was
            # counted as a copy, so a silent no-op reported two copies where
            # there was one - and suppressed the single-point-of-failure
            # warning, which is the one thing this function owes the athlete.
            if _retrieve(backend) == key:
                stored.append(backend)
            else:
                problems.append(
                    f"{type(backend).__name__} accepted the key and does not "
                    "give it back, so it is not a copy of it")
        except NotImplementedError:
            # A read-only backend (a key already in the environment, or on
            # paper) is a legitimate shape and not a failure - but it only
            # counts as a copy if it actually holds THIS key.
            if _verifies(backend) and _retrieve(backend) == key:
                stored.append(backend)
            else:
                problems.append(
                    f"{type(backend).__name__} cannot be written to and does "
                    "not already hold this key, so it is not a copy of it")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{type(backend).__name__}: {e!r}")

    if not stored:
        return {"ok": False, "key": None, "phrase": None,
                "problems": problems or ["no custody backend accepted the key"],
                "warnings": []}

    # EVERY backend, not just the first. Second and later copies were stored
    # and never proven, which is the same "believed they stored it" failure
    # one level up.
    for backend in stored:
        proof = drill({"setup-drill.jsonl": b"proof that the loop closes"},
                      key, cipher, transport, backend)
        problems += [f"{type(backend).__name__}: {p}"
                     for p in proof["problems"]]
    # And clean up after it. The drill blob was left in the production
    # transport for ever, to be carried through every future rotation or to
    # sit there sealed under a retired key.
    from .sync import blob_id
    try:
        transport.delete(blob_id(key, "setup-drill.jsonl"))
    except Exception as e:  # noqa: BLE001
        problems.append(f"the setup drill blob could not be removed: {e!r}")
    if problems and stored:
        problems.append(
            "the key was already written to "
            + ", ".join(sorted(type(b).__name__ for b in stored))
            + " before this failed. It is on disk and has not been shown to "
              "you - re-run setup, which overwrites it, rather than leaving "
              "a key nobody has a copy of")
    return {
        "ok": not problems,
        # The key and phrase are returned to be DISPLAYED once, never written
        # anywhere by this function - see the module docstring.
        "key": key.hex() if not problems else None,
        "phrase": to_phrase(key) if not problems else None,
        "problems": problems,
        "warnings": single_point_of_failure(stored),
    }


def _retrieve(backend: object) -> bytes | None:
    try:
        return backend.retrieve()
    except Exception:  # noqa: BLE001
        return None


def rotate(old_key: bytes, new_key: bytes, names: list[str], transport,
           cipher) -> dict:
    """Re-encrypt the whole blob set under a new key.

    Feasible precisely because the record is a few MB - which is the payoff
    for the log-not-database decision showing up somewhere unexpected.

    The old blobs are removed only after every new one is written and read
    back. A rotation that deletes as it goes and then fails halfway leaves a
    blob set encrypted under two keys, one of which the athlete has already
    been told to discard.
    """
    from .sync import blob_id, plan_download, plan_upload

    if old_key == new_key:
        return {"ok": False, "rotated": 0,
                "problems": ["the new key is the same as the old one"]}
    if not names:
        # Reporting success here told the athlete to discard the old key
        # while every blob was still sealed under it.
        return {"ok": False, "rotated": 0,
                "problems": ["nothing was named to rotate, so nothing was - "
                             "keep the old key"]}
    written, problems = [], []
    for name in sorted(names):
        try:
            blob = transport.get(blob_id(old_key, name))
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}: could not be read: {e!r}")
            continue
        if blob is None:
            problems.append(f"{name}: nothing stored under the old key")
            continue
        try:
            contents = plan_download(old_key, name, blob, cipher)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}: could not be opened: {e!r}")
            continue
        if contents is None:
            problems.append(f"{name}: does not open under the old key")
            continue
        ident, sealed = plan_upload(new_key, name, contents, cipher)
        try:
            transport.put(ident, sealed)
            back = transport.get(ident)
        except Exception as e:  # noqa: BLE001
            # A transport that raises must produce a REPORT, not a traceback -
            # this is the path whose whole promise is "keep the old key until
            # this succeeds", and a crash keeps no promise.
            problems.append(f"{name}: could not be re-encrypted: {e!r}")
            continue
        if back != sealed or plan_download(new_key, name, back,
                                           cipher) != contents:
            problems.append(f"{name}: did not read back after re-encrypting")
            continue
        written.append(name)

    if problems:
        # Leave the old blobs alone. Half a rotation is recoverable; half a
        # rotation with the originals deleted is not.
        return {"ok": False, "rotated": len(written), "problems": problems,
                "detail": "nothing was deleted - the old key still opens the "
                          "whole set, so keep it until this succeeds"}
    stale = []
    for name in written:
        try:
            transport.delete(blob_id(old_key, name))
        except Exception as e:  # noqa: BLE001
            stale.append(f"{name}: {e}")
    if stale:
        return {"ok": True, "rotated": len(written), "problems": [],
                "detail": "every blob is now readable under the new key, but "
                          "the old copies of " + "; ".join(stale)
                          + " could not be removed - they are still sealed "
                            "under the old key and should be deleted by hand"}
    return {"ok": True, "rotated": len(written), "problems": []}
