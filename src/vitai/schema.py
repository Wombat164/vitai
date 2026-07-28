"""Health-domain dataset schemas.

Conventions: ISO-8601 dates; units in the key name (kg, _km, _s, _g, _h);
null for unknown, never omit a key; one object per line.

`validate_record` is deliberately practical rather than exhaustive: it exists
so an LLM (or a tired human) appending lines gets caught on the mistakes that
actually corrupt a record - missing keys, bad dates, wrong types, unknown
session types - not to enforce ceremony.
"""

from __future__ import annotations

from datetime import date

# dataset -> ordered keys (column order for the SQLite read model)
KEYS: dict[str, list[str]] = {
    "weight": ["date", "kg", "source", "note"],
    "daily": ["date", "steps", "distance_km", "active_min", "kcal_out", "kcal_in",
              "protein_g", "sleep_h", "rhr", "hip_pain", "alcohol", "note"],
    "sessions": ["date", "type", "distance_km", "duration_s", "avg_hr", "max_hr",
                 "cadence", "kcal", "location", "rpe", "note"],
}

SESSION_TYPES = {"run", "gym_a", "gym_b", "walk", "test", "other"}

# key -> allowed python types when not null (bool checked before int: bool is int)
_NUMERIC = (int, float)
_TYPES: dict[str, tuple[type, ...]] = {
    "kg": _NUMERIC, "steps": (int,), "distance_km": _NUMERIC, "active_min": (int,),
    "kcal_out": (int,), "kcal_in": (int,), "protein_g": _NUMERIC, "sleep_h": _NUMERIC,
    "rhr": (int,), "hip_pain": (int,), "duration_s": (int,), "avg_hr": (int,),
    "max_hr": (int,), "cadence": (int,), "kcal": _NUMERIC, "rpe": (int,),
}

# extra keys that are always legal (the supersedes mechanic)
META_KEYS = {"supersedes"}


def _bad_date(v: object) -> bool:
    if not isinstance(v, str):
        return True
    try:
        date.fromisoformat(v)
        return False
    except ValueError:
        return True


def validate_record(dataset: str, rec: dict) -> list[str]:
    """Problems with one record; empty list means valid."""
    problems: list[str] = []
    keys = KEYS[dataset]
    for k in keys:
        if k not in rec:
            problems.append(f"missing key '{k}' (use null for unknown, never omit)")
    for k in rec:
        if k not in keys and k not in META_KEYS:
            problems.append(f"unknown key '{k}'")
    if _bad_date(rec.get("date")):
        problems.append(f"bad date {rec.get('date')!r} (ISO-8601 YYYY-MM-DD)")
    for k, types in _TYPES.items():
        if k in keys and (v := rec.get(k)) is not None and k in rec:
            if isinstance(v, bool) or not isinstance(v, types):
                problems.append(f"'{k}' should be a number or null, got {v!r}")
    if dataset == "daily" and (a := rec.get("alcohol")) is not None:
        if not isinstance(a, bool):
            problems.append(f"'alcohol' should be true/false/null, got {a!r}")
    if dataset == "sessions" and rec.get("type") not in SESSION_TYPES:
        problems.append(f"'type' must be one of {sorted(SESSION_TYPES)}, got {rec.get('type')!r}")
    if dataset == "daily" and (p := rec.get("hip_pain")) is not None:
        if isinstance(p, int) and not isinstance(p, bool) and not 0 <= p <= 10:
            problems.append(f"'hip_pain' is a 0-10 scale, got {p!r}")
    return problems
