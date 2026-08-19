"""What each contract touched, and whether a given client has to move (#451).

The migration table already carries "What an existing repo must do" and it is
good. For contracts 47 to 54 it says, in order: Nothing required / No column
moved / No field moved / Nothing required / Nothing required / Nothing required
/ One thing required / Nothing required. Seven of eight already say a client
need not move, and the client that consumes this engine moved eight times
anyway.

So the defect was never missing information. It was that

1. the information is prose, so a CI step cannot read it and a human must,
   every time, for every client; and

2. "Nothing required" answers a DIFFERENT QUESTION from the one a client is
   asking. It means *your existing code keeps working*. A client is asking
   *may I stay where I am*, nothing answered that, and so tracking head became
   the only defensible posture and every bump became a move.

This module answers the second question mechanically. `semantics/contract_impact.toml`
states what each contract TOUCHED; a client states what it READS; the answer is
the intersection. Measured on real absorptions in #450, one of loadline's six
absorptions of contracts 47 to 52 was a forced move and three moved a number
and nothing else.

WHY THERE IS NO "client_action" FIELD, which is the load-bearing design
decision. That question has one safe answer - `yes` - which is never wrong and
costs the author nothing, so a field shaped like it converges on `yes` within a
month and stops carrying information. The engine is never asked the question
whose lazy answer is yes. It states surfaces and change kinds, both of which
are checkable, and the client derives the verdict.

FAIL CLOSED. A client that does not say what it reads is told to move. The
answer "you may stay" is only ever produced from a stated read-set, because the
alternative - silence meaning safety - is how a gate stops being one.
"""

from __future__ import annotations

import tomllib
from importlib import resources

# THE FLOOR, and it is a declaration rather than an accident. Backfilling 46
# contracts by re-reading prose is exactly the "somebody fills in a field"
# failure this design exists to prevent, and a wrong backfilled entry is worse
# than an absent one because it will be trusted. 47 is where the evidence was
# read commit by commit. Below it this module REFUSES rather than answering
# partially: a partial answer to "may I stay" is the same shape as a wrong one.
FLOOR = 47

# The three change kinds, and what each one does to a READER of that surface.
# Closed, and each member carries a consequence rather than a description.
#
# `retired` and `meaning` were drafted and dropped: nothing between 47 and 54
# exercises them, and an unused member of a closed vocabulary is the vacuity
# this repo already gates on elsewhere. The contract that needs one adds it,
# and `test_contract_impact.py` fails if a kind sits here unused.
FORCES_MOVE = {
    # A new table, column or field. Everything that worked before still works;
    # adopting it is a CHOICE, and a choice is not a migration.
    "added": False,
    # A closed vocabulary gained a member. `kind in ("a", "b")` was exhaustive
    # and is not any more, so the reader silently DROPS rows rather than
    # erroring on them - which is worse than a break, because it looks fine.
    "widened": True,
    # A value that was always present may now be absent or refused. A reader
    # that treats it as always present reads a null as a fact.
    "narrowed": True,
}

# Surface namespaces, and they exist because the three have three different
# AUDIENCES. A client knows which one it is, so the answer partitions cleanly
# rather than telling every consumer about every change.
AUDIENCE = {
    "table": "reader of the read model",
    "meta": "author of lines",
    "report": "reader of the report",
}


def _namespace(surface: str) -> str:
    """Which of the three grammars a surface is written in."""
    for prefix in ("meta", "report"):
        if surface.startswith(prefix + ":"):
            return prefix
    return "table"


def declaration() -> dict[int, list[dict]]:
    """The raw declaration, contract number to its list of touched surfaces."""
    path = resources.files("vitai") / "semantics" / "contract_impact.toml"
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    return {int(n): list(body["touches"]) for n, body in raw.items()}


def touched(contract: int) -> list[dict]:
    """Every surface `contract` touched, with its audience and consequence."""
    entries = declaration().get(int(contract), [])
    out = []
    for e in entries:
        ns = _namespace(e["surface"])
        out.append({
            "contract": int(contract),
            "surface": e["surface"],
            "change": e["change"],
            "audience": AUDIENCE[ns],
            "forces_move": FORCES_MOVE[e["change"]],
        })
    return out


def _covers(read: str, surface: str) -> bool:
    """Does a client reading `read` see `surface`?

    A client declares what it reads at whatever granularity it knows. Most
    declare tables (`weight`), some declare columns (`weight.absent_reason`),
    and one that authors corrections declares `meta`. All three have to work,
    so a read matches a surface it EQUALS or CONTAINS - `crossings` covers
    `crossings.kind`, and `meta` covers `meta:supersedes_seq`.

    Deliberately not the other way round. A client declaring `crossings.kind`
    is NOT told about `crossings.metric`, because it said which column it reads
    and taking that seriously is the whole point of asking.
    """
    read = read.strip()
    if not read:
        return False
    if read == surface:
        return True
    # `meta` and `report` name a whole namespace when written bare.
    if read in ("meta", "report") and surface.startswith(read + ":"):
        return True
    for sep in (".", ":"):
        if surface.startswith(read + sep):
            return True
    return False


def impact(since: int, upto: int) -> list[dict]:
    """Every touched surface in (`since`, `upto`], newest contract last.

    `since` is where the client IS, so it is exclusive: a client at 52 has
    already absorbed 52 and is asking about 53 and 54.
    """
    since, upto = int(since), int(upto)
    if since < FLOOR - 1:
        raise ValueError(
            f"this engine declares contract impact from {FLOOR} onward and "
            f"will not answer for {since}. A partial answer to 'may I stay' "
            f"has the same shape as a wrong one, so it is refused instead. "
            f"Read the migration table in README.md for contracts below "
            f"{FLOOR}."
        )
    rows: list[dict] = []
    for n in range(since + 1, upto + 1):
        rows.extend(touched(n))
    return rows


def assess(since: int, upto: int, reads: list[str] | None) -> dict:
    """Must a client at contract `since`, reading `reads`, move to `upto`?

    `reads` of None OR EMPTY means the client did not say, and the answer is
    then ALWAYS "move" - not because it is true, but because a verdict of "you
    may stay" that was never earned is the only outcome here that can cost a
    client a silent data loss.
    """
    rows = impact(since, upto)
    # AN EMPTY READ-SET IS NOT A STATED ONE, and this was a live fail-open
    # before it was a comment: `--reads ""` split to `[]`, which is not None,
    # so the verdict came back STAY having matched nothing. A client that
    # says it reads nothing has told us nothing, and the rule this module
    # opens with is that "you may stay" is only ever produced from a read-set
    # that could have said otherwise.
    #
    # Fixed HERE rather than in the CLI on purpose: the API is a door too, and
    # a control that lives on one caller is one the other caller does not have.
    #
    # AND IT IS THE NON-BLANK COUNT, not the list length. The first fix was
    # `bool(reads)`, which a list of blanks passes: `[" ", ""]` is truthy,
    # matches nothing, and came back STAY. A guard that a caller can satisfy
    # without saying anything is the same fail-open one indirection down.
    stated = any(r and r.strip() for r in (reads or ()))
    reasons, ignored = [], []
    for row in rows:
        seen = (not stated) or any(_covers(r, row["surface"]) for r in reads)
        if seen and row["forces_move"]:
            reasons.append(row)
        elif not seen:
            ignored.append(row)
    return {
        "contract_from": int(since),
        "contract_to": int(upto),
        "reads_stated": stated,
        "must_move": bool(reasons) or not stated,
        "because": reasons,
        "not_yours": ignored,
        "touched": rows,
    }


def catalogue() -> dict[str, set[str]]:
    """Every surface a client can reach, by namespace.

    DERIVED FROM THE ENGINE'S OWN DECLARATIONS rather than restated here, for
    the reason a gate is not allowed to read the data it validates: a
    catalogue kept beside the declaration would agree with it by construction
    and would catch nothing.

    - `table` is the built read model: the record datasets `schema.KEYS`
      declares, plus the derived tables `db.DERIVED_TABLES` does. Together
      these are the tables `build_db` creates, which is what a client opens.
    - `meta` is `schema.META_KEYS`: line-level fields on the append shape that
      are never columns, so a READER cannot see them and an AUTHOR must.
    - `report` is the public read methods on `Vitai`: surfaces that reach a
      consumer through the report and have no table. `questions` is one, which
      is why contract 49 could not move a column and still asked something.
    """
    from .db import DERIVED_TABLES
    from .schema import KEYS, META_KEYS

    tables = {name: set(cols) for name, cols in KEYS.items()}
    for name, cols in DERIVED_TABLES.items():
        tables.setdefault(name, set()).update(cols)
    return {"table": tables, "meta": set(META_KEYS), "report": None}


def unresolved(surface: str) -> str | None:
    """Why `surface` names nothing a client can reach, or None if it resolves.

    An entry nothing can read tells nobody anything, which is the vacuity this
    check exists for.
    """
    cat = catalogue()
    ns = _namespace(surface)
    body = surface.split(":", 1)[1] if ns != "table" else surface

    if ns == "meta":
        if body not in cat["meta"]:
            return f"'{body}' is not one of schema.META_KEYS"
        return None

    head, _, field = body.partition(".")

    if ns == "report":
        from .api import Vitai
        member = getattr(Vitai, head, None)
        if member is None or head.startswith("_") or not callable(member):
            return (f"'report:{head}' names no public read method on Vitai, "
                    f"so nothing publishes it")
        # A report surface has no declared column list to check `field`
        # against; that it is a real published method is what can be checked.
        return None

    if head not in cat["table"]:
        return f"'{head}' is not a table in the read model"
    if field and field not in cat["table"][head]:
        return f"'{head}' has no column '{field}'"
    return None
