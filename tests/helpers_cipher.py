"""A stand-in for the cipher the engine deliberately does not ship.

`sync.Cipher` is a contract with no implementation: the standard library has
no authenticated encryption and hand-rolling one is how this goes wrong. The
tests still need SOMETHING in that slot to prove the slot works, so this is a
keyed XOR with an HMAC tag - named so nobody mistakes it for encryption, and
kept out of `src/` so it can never be reached by anything but a test.
"""

import hashlib
import hmac


class ToyCipher:
    """NOT a cipher. It exercises the seam and nothing more."""

    def seal(self, key: bytes, plaintext: bytes) -> bytes:
        body = bytes(a ^ b for a, b in zip(plaintext,
                                           self._stream(key, len(plaintext))))
        return hmac.new(key, body, hashlib.sha256).digest() + body

    def open(self, key: bytes, blob: bytes) -> bytes | None:
        tag, body = blob[:32], blob[32:]
        if not hmac.compare_digest(tag, hmac.new(key, body,
                                                 hashlib.sha256).digest()):
            return None
        return bytes(a ^ b for a, b in zip(body, self._stream(key, len(body))))

    @staticmethod
    def _stream(key: bytes, size: int) -> bytes:
        out = b""
        while len(out) < size:
            out += hashlib.sha256(key + len(out).to_bytes(8, "big")).digest()
        return out[:size]
