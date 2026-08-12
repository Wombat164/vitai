"""One writer per file, so a merge is a set union (#105).

The record is single-writer today, and the moment a second capture device
appears - for a health system that is always the phone - two devices append to
one file and a consumer sync client resolves the collision by last-writer-wins
or by leaving a `conflicted copy`. For an append-only JSONL that silently
discards one device's writes.

## Actor per file

    data/
      daily.laptop.jsonl      <- only the laptop ever appends here
      daily.phone.jsonl       <- only the phone ever appends here

**No two devices ever write the same file, so no conflict is possible.** Not
"conflicts are resolved" - structurally cannot occur. Merge is set union,
which every sync transport already does correctly for disjoint files.

## Which makes the transport content-blind, and that is the point

A sync layer built on this moves opaque files. It never parses a row, never
knows a schema, and therefore:

- it cannot corrupt data it cannot read;
- it needs no contract bump when the schema moves;
- and holding the athlete's own key becomes nearly trivial, because a server
  that never could read the content has nothing to be trusted with.

That last one is worth stating plainly: the property a zero-knowledge design
buys with cryptography, this buys by never looking. Any design that needs the
transport to merge CONTENT has already given that up.

## The database is derived, and is never synced

`data/*.jsonl` is the record; `derived/health.db` rebuilds from it in seconds.
Syncing the artifact would make a disposable file load-bearing - and worse,
SQLite's main file and its WAL are separate files that must stay consistent,
so a client that uploads them independently produces a database that is
corrupt rather than merely stale.

## What union does not solve

**Duplicate capture.** The same workout pulled from a vendor on the laptop and
again on the phone is two rows describing one event, from two files, both
legitimate appends. Union does not deduplicate and nothing else would notice.

So identity is resolved at BUILD rather than at write: a device that was
offline still converges, because the dedupe happens over whatever files are
present whenever they arrive. Deduping at write would require the writer to
have seen the other device's file, which is exactly the coupling actor-per-file
exists to remove.

**The collision this whole scheme prevents - two machines with no slug set,
both appending to the plain file - is not detectable once it has happened.**
`write_path` sends an unslugged writer to `<dataset>.jsonl` and never stamps
`device` on the row (#367); a second unslugged machine writing the same file
produces rows that are byte-for-byte the same shape as a single machine's,
because the field that would tell them apart is exactly the one both writers
lack. There is no scan of `<dataset>.jsonl` worth writing here: anything it
flagged would be a guess dressed as a finding. The fix is upstream, at
`vitai init` time, before a second device's first write - not a check after.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# `daily.laptop.jsonl` - dataset, device, suffix. The device slug is
# constrained so a filename cannot smuggle a path separator or a second dot,
# either of which would make the dataset ambiguous.
_NO_INSTANT = datetime.min.replace(tzinfo=timezone.utc)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

# Fields that describe the WRITE rather than the observation. Two devices
# recording one real event legitimately differ here, so they are excluded when
# asking whether two rows are the same event.
WRITE_FIELDS = ("device", "recorded_at", "_gen", "supersedes")


def is_slug(value: object) -> bool:
    return bool(SLUG_RE.match(str(value or "")))


def stream_paths(data_dir: Path, name: str) -> list[Path]:
    """Every file that makes up one logical dataset, in a stable order.

    `daily.jsonl` and `daily.*.jsonl` together. A single-file record keeps
    working untouched - it is simply an actor whose name is nothing, which is
    what every existing record is.
    """
    plain = data_dir / f"{name}.jsonl"
    out = [plain] if plain.exists() else []
    for path in sorted(data_dir.glob(f"{name}.*.jsonl")):
        # LOWERCASED before the check. Writers are strict - `write_path`
        # refuses anything but a lowercase slug - but a reader that silently
        # ignores a file full of real data is the worst outcome available,
        # and on a case-insensitive filesystem `weight.laptop.jsonl` can come
        # back from the directory as `weight.Laptop.jsonl`. Windows CI caught
        # exactly that: the device's whole stream vanished from the union.
        if is_slug(path.name[len(name) + 1:-len(".jsonl")].lower()):
            out.append(path)
    return out


def device_of(path: Path, name: str) -> str:
    """The device a file belongs to, or "" for the unsuffixed one.

    Lowercased, so one device is one device however the filesystem hands its
    name back. The slug is also the ORDERING tiebreak, and a build that
    ordered by `Laptop` on one machine and `laptop` on another would stop
    being reproducible.
    """
    stem = path.name[len(name) + 1:-len(".jsonl")].lower()
    return stem if path.name != f"{name}.jsonl" and is_slug(stem) else ""


def write_path(data_dir: Path, name: str, device: str | None) -> Path:
    """Where THIS device appends.

    The one place a writer picks a file, so "a device only ever writes its
    own" is a property of the code rather than a convention to remember.
    """
    if not device:
        return data_dir / f"{name}.jsonl"
    if not is_slug(device):
        raise ValueError(
            f"{device!r} is not a device slug - lowercase letters, digits and "
            "hyphens, up to 32 characters. It becomes part of a filename, so "
            "a dot or a separator would make the dataset ambiguous")
    return data_dir / f"{name}.{device}.jsonl"


def event_key(name: str, rec: dict) -> str:
    """What makes two rows the same real event, across devices.

    The vendor's own id where there is one - `activity_id` exists on
    `sessions` for exactly this reason, being what dedupes a re-run import.
    Otherwise a content address over the OBSERVATION fields, with the
    write-side fields excluded: two devices pulling one workout stamp
    different `recorded_at` values and carry different `device` slugs, and
    neither difference makes it two workouts.

    Deliberately NOT `line_key`. That answers "which line does a correction
    name", which is a question about one file's history; this answers "are
    these the same happening", which is a question across files.
    """
    if name == "sessions" and rec.get("activity_id"):
        return f"{name}:activity:{rec['activity_id']}"
    payload = {k: v for k, v in rec.items()
               if k not in WRITE_FIELDS and v is not None}
    # JSON, not a separator join. Field values are free text and nothing
    # forbids the separators, so `note: "hi\u241fsource\u241escale"` collided
    # with a row that really had that source - two different rows, one key,
    # and `deduplicate` dropping a real one. `str()` also erased types, so 1
    # and "1" collided in any untyped field.
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)
    return f"{name}:content:{hashlib.sha256(body.encode()).hexdigest()}"


def merge(streams: list[tuple[str, list[dict]]], name: str) -> list[dict]:
    """Union the device streams into one deterministic sequence.

    Ordered by (recorded_at, device, position within that device's file). The
    device slug is the tiebreak that makes the order TOTAL, so two devices
    building the same record produce byte-identical output - which is the
    property that lets anyone rebuild and check rather than having to trust
    whoever ran the build.

    Rows with no `recorded_at` sort first and keep their file order, so a
    legacy single-file record resolves exactly as it always did.
    """
    from .clocks import stamp_instant

    tagged = []
    for device, rows in streams:
        for position, row in enumerate(rows):
            stamp = row.get("recorded_at")
            # `stamp is not None` FIRST, so absent sorts BEFORE present - the
            # canon `clocks.order_key` sets, and the opposite of what a plain
            # `""` comparison gives. And the INSTANT, never the text: two
            # stamps either side of a timezone change order by wall clock as
            # strings, which is the #37 trap this record already knows about.
            tagged.append(((stamp is not None,
                            stamp_instant(stamp) or _NO_INSTANT,
                            device, position), row))
    return [row for _, row in sorted(tagged, key=lambda t: t[0])]


def duplicate_indices(rows: list[dict], name: str) -> dict[int, int]:
    """{index of a duplicate: index of the row it duplicates}.

    ONLY ACROSS DEVICES. Two identical weigh-ins on one day from one machine
    are two real weigh-ins - the athlete stepped on twice - and reporting them
    as one happening captured twice fires on today's single-file records the
    moment anyone calls this. A duplicate capture is by definition two devices
    describing one event.

    Indices rather than rows, because a caller can legitimately hold the same
    dict object twice: keying on `id()` made `[r, r]` drop BOTH copies,
    including the one being kept.

    Keys are computed once. Recomputing them per candidate is a sha256 over
    the dataset for every duplicate found, which on a re-synced file is
    quadratic in the worst case that actually happens.
    """
    first: dict[str, int] = {}
    out: dict[int, int] = {}
    for i, row in enumerate(rows):
        key = event_key(name, row)
        seen = first.get(key)
        if seen is None:
            first[key] = i
        elif str(rows[seen].get("device") or "") != str(row.get("device") or ""):
            out[i] = seen
    return out


def duplicates(rows: list[dict], name: str) -> list[dict]:
    """Rows describing an event another row already describes.

    Returned rather than dropped, so a caller can report them. The FIRST in
    merge order is kept: with a total order that is a deterministic choice
    rather than whichever device happened to sync first.
    """
    return [rows[i] for i in sorted(duplicate_indices(rows, name))]


def deduplicate(rows: list[dict], name: str) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) - one canonical row per real event."""
    dup = duplicate_indices(rows, name)
    return ([r for i, r in enumerate(rows) if i not in dup],
            [rows[i] for i in sorted(dup)])
