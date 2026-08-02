"""A stable, unique reference to one row. The primitive #168, #169 and #170 need.

Three issues converge on this, which is usually the sign that the missing
thing is one piece rather than three: a qualification has to name the
observation it qualifies (#168), a source that is a platform and a channel has
to name which reading it relayed (#169), and a derived value has to name the
rows it came from (#170). None of them can be built on a reference that points
at more than one row.

WHAT ALREADY EXISTED, because most of this was wiring rather than design:

- `resolution.claim_id` gives `dataset:date:source`, which is stable across
  rebuilds because it is derived from content rather than from position. It is
  the right shape and it is not unique: measured on the demo corpus it
  collided on 8 of 11 `sets` rows and 4 of 5 `meals`, because date and source
  are far too coarse for a dataset that holds many rows per day.
- `schema.IDENTITY_KEY` already declares what actually identifies a row in
  exactly those datasets: a set is (session_start, exercise, block, round,
  set_index), a meal item is (meal, item), a goal is its slug.

So this joins them. Where the schema declares an identity, use it. Where it
does not, fall back to date and source, and disambiguate repeats with an
ordinal.

THE ORDINAL IS THE HONEST WEAKNESS AND IS NAMED HERE rather than discovered
later. Two readings from one scale on one morning are distinguishable only by
their order in the file, and file order is not a property the record
guarantees: #37 established that an ordering a formatter can change is not an
ordering, and #164 found a correction silently failing because the merged
order put it before its target. So an ordinal-disambiguated reference is
stable only as long as nothing reorders those rows, and a caller that needs a
permanent handle for a repeated same-source reading needs the record to carry
one. `client_record_id` in the proposal is that handle; until it exists, this
function reports the ambiguity rather than papering over it.
"""

from __future__ import annotations

from .schema import IDENTITY_KEY, KEYS

UNKNOWN_SOURCE = "unknown"


def row_ref(dataset: str, rec: dict, ordinal: int = 0) -> str:
    """A reference to one row, stable across rebuilds.

    Content-derived, never positional except for the ordinal, which is only
    reached when the record itself cannot tell two rows apart.
    """
    ident = IDENTITY_KEY.get(dataset)
    if ident is not None:
        parts = (ident,) if isinstance(ident, str) else ident
        keyed = ":".join(_part(rec.get(k)) for k in parts)
        return f"{dataset}:{keyed}"
    base = f"{dataset}:{_part(rec.get('date'))}:{_part(rec.get('source'))}"
    return f"{base}:{ordinal}" if ordinal else base


def _part(value) -> str:
    if value is None or value == "":
        return UNKNOWN_SOURCE
    return str(value).replace(":", "_")


def refs(dataset: str, rows: list[dict]) -> list[str]:
    """A reference per row, with ordinals assigned where they are needed.

    Ordinals are assigned in the order given, so the caller decides what
    "first" means. Every caller in this engine passes the merged order, which
    is the same order the build resolves in.
    """
    seen: dict[str, int] = {}
    out = []
    for rec in rows:
        base = row_ref(dataset, rec)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(row_ref(dataset, rec, ordinal=n) if n else base)
    return out


def ambiguous(dataset: str, rows: list[dict]) -> list[dict]:
    """Rows the record cannot tell apart without counting them.

    Reported rather than resolved, because the fix is a field the record does
    not have yet. A caller that targets one of these is targeting a position,
    and a position is not an identity: the reference works until somebody
    regenerates the file in a different order, and then it silently points at
    a different reading.
    """
    counts: dict[str, int] = {}
    for rec in rows:
        base = row_ref(dataset, rec)
        counts[base] = counts.get(base, 0) + 1
    return [{"ref": ref, "rows": n} for ref, n in sorted(counts.items())
            if n > 1]


def identifiable(dataset: str) -> bool:
    """Can every row of this dataset be named without counting?

    True where the schema declares an identity. False where a reference falls
    back to date and source, which repeat.
    """
    return dataset in IDENTITY_KEY


def unidentifiable_datasets() -> list[str]:
    """Every dataset whose rows can repeat under one reference.

    The list #169's `client_record_id` would shorten, stated so the gap is
    countable rather than argued about.
    """
    return sorted(name for name in KEYS if name not in IDENTITY_KEY)
