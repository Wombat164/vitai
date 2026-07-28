#!/usr/bin/env python3
"""Personal-content gate: fails CI if any private identifier leaks into the tree.

The deny list is stored as SHA-256 hashes of lowercase word tokens, so this
public file cannot itself leak the terms it guards. Every word-token in every
tracked text file is hashed and compared. If this gate fires, the flagged file
contains something private to the maintainer's deployment - remove or
generalize it; never weaken the gate.

Run locally:  python scripts/personal_gate.py
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

DENY_HASHES = {
    "062e15b367d5e6518172fece401a33722e7d54467dd151c80dc9b4af0f512d32",
    "126f72640eff50fd5142ef4613a4f14cfdf9f5d12be1109a22ab22bb5df14439",
    "1ff60eb35fab5c78be3a5d9094f0982a9cb173ec1d9e71a24adf54631b002275",
    "269b39e441b1ee5afeb76e0aa3b60cb92e4e6e42e2616e039a5a1e60f0ca0db0",
    "29b9f822d6743ad888afccb75bd93dd21be157b4e1d56eaeb1089db0dd5d5176",
    "3f56e90b04e7a4b50e3ec2446c13055e9cb1d0851c17c9ce8a52ea3ca76623cc",
    "51bb8028e0679fe845206aa74d0941e263db4a50603796c6de71a49dc1a97479",
    "5a957036d2571bd16805c08dc37d99f79454122ad330e111c64a65bf94213c42",
    "68168224c4721b509979d5b69f689b4445e00852510b89f713570dcaa7e7a7bc",
    "7c69eaa12b767fb061b485bcf2ee1807df48d5c4d878de4ff644959017fd1428",
    "7c79999975bea340f544585317d18d4c2229dd8b990f8b50af9a52f35a0a939b",
    "9d618f68808c434622373ac20b2af5da7f4845601ad6fabdebd169e08380540f",
    "aa1d1ac2e612a92ebe7c8f9b976c73c88b097faf8f32af47b4cdce97a694dd60",
    "c67946687e2d14bd8af0d5ceb85b43af09d96b4671ce4b28842870c3ec0c59bf",
    "ea80d867ed4f37fb63b6ec568df28a81da3604556271a2f0536bb0b9f7f47cfa",
    "f0ac7198b27419aefeb6889cc72116246970a54f1fb911b8347422f7efc51fff",
    "ff7efa9ab15c1f6cc542f89ebff56191efc89872db51721f98f5105fee03122f",
}

TEXT_EXT = {".py", ".md", ".toml", ".yml", ".yaml", ".svg", ".txt", ".json",
            ".jsonl", ".ts", ".cfg", ".ini", ""}
TOKEN_RE = re.compile(r"[a-zA-Z]+")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [Path(p) for p in out.stdout.splitlines()]


def main() -> int:
    bad = 0
    for path in tracked_files():
        if path.suffix.lower() not in TEXT_EXT or not path.exists():
            continue
        if path.name in ("Outfit-600.ttf",) or path.suffix in (".png", ".ttf"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = {
            tok for tok in {t.lower() for t in TOKEN_RE.findall(text)}
            if hashlib.sha256(tok.encode()).hexdigest() in DENY_HASHES
        }
        if hits:
            # Do not print the terms themselves; the file/line is enough.
            print(f"PERSONAL-CONTENT GATE: {path} contains {len(hits)} denied term(s)")
            bad += 1
    if bad:
        print(f"FAILED: {bad} file(s). Remove or generalize the private content.")
        return 1
    print("personal gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
