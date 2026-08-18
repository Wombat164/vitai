"""What a correction actually did, and what the record cannot tell you (#143).

A `supersedes` is accepted, applied, and never characterised. The chain holds
both values, both timestamps and the context they landed in, and nothing looks
at any of it: `retractions` records THAT a claim came down and what brought it
down, `dataset` returns the survivor, and the row that lost is in the file
where nobody reads it.

So this is the read surface for the pair rather than the winner: which fields
moved, which way, how long after the fact, and how many corrections in a row
have moved the same way.

WHAT THIS DELIBERATELY IS NOT, and the constraint is the harder half of the
issue that asked for it. "Three of the last four corrections moved in the same
direction" is a fact about a file. "You are massaging your numbers" is not
something a training log gets to say, and the distance between them is one
rendering step. Two properties keep them apart structurally rather than by
intention:

  IT EMITS NUMBERS, NOT PROSE. There is no message, no severity and no verdict
  word anywhere in what this returns. A consumer that wants to say something
  composes it; the engine states what is in the file. A sentence cannot be
  leaked from a surface that has no sentences.

  IT IS ASKED, NEVER RAISED. This is not a tripwire and does not enter the
  build's findings, which was a deliberate choice and not an omission. A
  tripwire is the engine bringing something up unprompted, and bringing up
  "your corrections trend downward" unprompted IS the accusation, whatever
  words it uses. Answering when asked is not.

AND THE LIMIT IS PART OF THE ANSWER. The persona corpus pairs an honest
back-fill with a flattering one on purpose, and they are structurally
identical - same shape, same fingerprint, opposite ground truth. A run counted
here says the file has that shape. It does not say why, it cannot, and a
consumer that treats the count as evidence about a person has read something
this module did not say. `test_corrections.py` asserts the detector cannot
tell the pair apart, because a detector that appeared to would be claiming a
discrimination it does not have.
"""

from __future__ import annotations

from datetime import datetime

from .identity import refs
from .jsonl import _read_streams, line_key, position_of, retire, target_of
from .schema import IDENTITY_KEY, KEYS, META_KEYS

# Not a quantity anybody corrected: stamped by the engine, or the reference
# that makes this row a correction in the first place.
STAMPED = META_KEYS | {"recorded_at", "device", "read_by", "capture",
                       "origin", "path", "origin_evidence", "artifact"}

# NOT A QUANTITY THAT MOVED, and leaving it in read as though it were. Where a
# reference is `<date>/<source>`, the date is part of what NAMES the row - so a
# correction dated later than its target is not a corrected date, it is a row
# written on another day that retires an earlier one. The naive diff reported
# `date: was 2027-09-27, now 2027-10-04` on a real fixture whose reading was
# never re-dated at all. Carried as `target_date` beside the correction's own
# instead: nothing claimed, nothing hidden.
def identifying(dataset: str) -> frozenset[str]:
    """The fields that NAME a row in this dataset rather than valuing it."""
    # `date` ALWAYS, whatever the dataset keys on. Where the reference is
    # `<date>/<source>` it is half the key; where the dataset is identity-keyed
    # it is the effective-dating axis a later row wins on. Either way it says
    # WHEN this row is, not what it values, and a correction written on a
    # later day has not re-dated anything. The naive diff reported
    # `date: was 2030-05-26, now 2030-05-27` on the shipped goals fixture,
    # whose target was never re-dated at all.
    ident = IDENTITY_KEY.get(dataset)
    if ident is not None:
        keyed = (ident,) if isinstance(ident, str) else ident
        return frozenset(keyed) | {"date"}
    # The `<date>/<source>` fallback, plus the vendor identity that displaces
    # it on `sessions`.
    return frozenset({"date", "source", "activity_id"})


def _instant(rec: dict) -> datetime | None:
    raw = rec.get("recorded_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _lag_days(target: dict, correction: dict) -> float | None:
    """How long the record held the value it later withdrew.

    From TRANSACTION time on both sides, not valid time. The question is how
    long the record said the wrong thing, which is when each line was written;
    the day being described is the same day on both rows by construction.

    None where either side is unstamped, rather than a zero. A missing lag and
    a same-second correction are different facts and the second is
    interesting, so collapsing them would invent the more remarkable one.
    """
    was, now = _instant(target), _instant(correction)
    if was is None or now is None:
        return None
    if (was.tzinfo is None) != (now.tzinfo is None):
        return None            # naive against aware; the difference is a guess
    return round((now - was).total_seconds() / 86400, 3)


def _direction(was: object, now: object) -> str | None:
    """Which way a value moved, where the question has an answer.

    `changed` for anything not two numbers. A word replacing another word has
    no direction, and picking one - alphabetical, or by some ranking of
    session types - would be an ordering this engine never declared.

    Three values and not four. There is no `unchanged`, because `_moved` drops
    a field whose value did not move before this is ever asked - so a fourth
    word would be one no output could contain, and a vocabulary with a member
    nothing can produce invites a consumer to handle a case that never comes.
    """
    numeric = (int, float)
    if isinstance(was, bool) or isinstance(now, bool):
        return "changed"
    if isinstance(was, numeric) and isinstance(now, numeric):
        return "down" if now < was else "up"
    return "changed"


def _moved(dataset: str, target: dict, correction: dict) -> list[dict]:
    """The fields whose values differ, in KEYS order so two runs agree.

    KEYS order rather than sorted or insertion order: sorted would be stable
    too, and KEYS is the order every other surface here presents a row in, so
    a reader comparing this against `dataset()` sees the same sequence.
    """
    naming = identifying(dataset)
    out = []
    for field in KEYS.get(dataset, ()):
        if field in STAMPED or field in naming:
            continue
        was, now = target.get(field), correction.get(field)
        if was == now:
            continue
        out.append({"field": field, "was": was, "now": now,
                    "direction": _direction(was, now)})
    return out


def _applied(dataset: str, rows: list[dict]) -> list[tuple[int, int]]:
    """(target position, correction position) for corrections that really landed.

    THE ENGINE'S OWN ORDER AND THE ENGINE'S OWN OUTCOME, both, because the
    first version of this re-derived the retirement rule and got it wrong on
    three separate axes:

      IT SORTED BY THE STAMP AS A STRING. `+02:00` sorts after `+00:00`
      whatever the instants are, which is the #38 mistake `clocks` and
      `devices.merge` both already carry a warning about. Two rows either side
      of a clock change made it report a value as withdrawn while `dataset()`
      still returned it standing.

      IT COMPARED RAW LINE NUMBERS. Those restart in every device file, so
      across two streams the comparison meant nothing: a correction in
      `weight.jsonl` naming a target in `weight.laptop.jsonl` disappeared from
      this surface entirely, and another shape invented a move nobody made.

      IT NEVER ASKED WHETHER THE CORRECTION APPLIED. A row stamped before its
      target retires nothing, and an `emissions` row never retires anything at
      all - and both were characterised here as though they had, complete with
      a direction that then fed a run.

    So the sequence comes from `_read_streams`, which is the same union
    `load` reads, and the outcome comes from `retire`, which is the function
    that decides it. A correction is reported when THE ROW IT NAMED is gone
    from the survivors. Anything else is a claim about a retirement that did
    not happen, on a surface whose whole justification is stating what is in
    the file.

    ONLY THE TARGET IS CHECKED, never the correction itself. Requiring the
    correcting row to have survived too looked like the same test and silently
    dropped the middle of every chain: B corrects A and is then corrected by
    C, so B is gone from the survivors - but B applied, and a chain that
    reported only its last link would be describing two corrections as one.

    INDEXED BY KEY, one pass. The first version scanned every row for every
    correction, which took 16 seconds on 20000 rows with 1000 corrections -
    the same quadratic shape `jsonl._targets_retired` was rewritten to remove,
    reintroduced one module over.
    """
    from bisect import bisect_left

    survived = {id(r) for r in retire(dataset, rows)}
    by_key: dict[str, list[int]] = {}
    for position, rec in enumerate(rows):
        by_key.setdefault(line_key(dataset, rec), []).append(position)

    out = []
    for position, rec in enumerate(rows):
        if (aimed := target_of(rec)) is None:
            continue
        ref, narrow, actor = aimed
        candidates = by_key.get(ref, ())
        if narrow is not None:
            # A NARROWED CORRECTION NAMES ONE ROW (#239), so the pairing is a
            # lookup rather than a walk backwards. Without this the surface
            # whose whole job is "what a correction actually did" omitted every
            # correction written the way `validate` advises.
            candidates = [c for c in candidates if position_of(rows[c]) == narrow]
            # AND WHICH MACHINE WROTE IT, where the correction says (#391). A
            # position can be occupied twice, so pairing on position alone
            # would report this correction against a peer's row - naming the
            # wrong line in the one surface whose job is saying what happened.
            if actor is not None:
                candidates = [c for c in candidates
                              if rows[c].get("device") == actor]
        cut = bisect_left(candidates, position)
        if not cut:
            continue                  # names nothing earlier; `validate` says so
        target = candidates[cut - 1]
        if id(rows[target]) in survived:
            continue                  # the correction never applied
        out.append((target, position))
    return out


def characterise(data_dir, dataset: str) -> list[dict]:
    """One row per applied correction in `dataset`, in the order they landed.

    Reads the RAW rows rather than the loaded record, because the row a
    correction retired is exactly the row `load` removes. Reading through the
    normal door would leave this able to see only the half that won.

    IN TRANSACTION ORDER, which is the order the runs are counted in and the
    only order in which a run reads correctly. Sorting by `date` looked
    tidier and was wrong: a back-dated correction listed above the one it
    followed, so a reader saw `run 2` printed above `run 1`.

    Rows are named by the engine's own row grammar rather than by line number.
    Line numbers restart in every device file, so "line 3 corrects line 3" is
    unresolvable in a two-device record, and `validate` numbers rows a third
    way again - three vocabularies for one question.
    """
    rows, _ = _read_streams(data_dir, dataset)   # G26: a bad line never aborts
    rows = [rec for _, rec in rows]
    named = refs(dataset, rows)

    out = []
    for target, position in _applied(dataset, rows):
        rec = rows[position]
        out.append({
            "dataset": dataset,
            "date": rec.get("date"),
            "row": named[position],
            "corrects": named[target],
            "reference": str(rec.get("supersedes")),
            "target_date": rows[target].get("date"),
            "lag_days": _lag_days(rows[target], rec),
            "moved": _moved(dataset, rows[target], rec),
            "note": rec.get("note"),
        })
    return _with_runs(out)


def _with_runs(corrections: list[dict]) -> list[dict]:
    """`same_direction_run` per correction: how many in a row moved this way.

    PER FIELD, because a run is only a run within one quantity. Weight moving
    down four times and distance moving down once are five corrections and two
    unrelated sequences, and counting them together would manufacture the
    longer number.

    A BARE COUNT AND NOTHING ELSE. It is 1 for a correction with no
    predecessor in its direction, which is the honest floor rather than a
    null: one correction is a run of one. No threshold is applied here and
    none is published, because a threshold is where the number becomes a
    judgement, and this module does not make one.
    """
    run: dict[tuple[str, str, str], int] = {}
    for correction in corrections:
        counted = []
        for move in correction["moved"]:
            key = (correction["dataset"], move["field"], move["direction"])
            run[key] = run.get(key, 0) + 1
            # Any other direction on this field ends its run.
            for other in list(run):
                if other[:2] == key[:2] and other != key:
                    run[other] = 0
            counted.append({**move, "same_direction_run": run[key]})
        correction["moved"] = counted
    return corrections
