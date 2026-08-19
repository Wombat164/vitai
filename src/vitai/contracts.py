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

FAIL CLOSED. A client that does not say what it reads is told to move, and one
that names surfaces this engine does not publish is refused rather than
answered - a read that resolves to nothing is silence with extra characters,
and "you may stay" is only ever produced from a read-set that could have said
otherwise.

REACH THIS AS `vitai.contracts`, or through `api.contract_impact` and the
`vitai contract-impact` command, which are the supported doors. It is a module
in a package and not a loose file: loading it by path under its own name leaves
the relative imports below with no package to resolve against, and a client
that did so worked only for as long as it stayed on the one code path that
never took them.
"""

from __future__ import annotations

import hashlib
import json
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

# Surface namespaces, and they exist because they have different AUDIENCES. A
# client knows which one it is, so the answer partitions cleanly rather than
# telling every consumer about every change.
#
# `payload` IS NOT LIKE THE OTHER THREE and #453 is the record of why. The
# other three name things that move WITH the contract number, so a contract
# row can declare them. The payload - what `api.schema()` publishes - moves
# BETWEEN contract numbers: #350 moved eight aliases out of it with no bump,
# #331 added `display_name` to it with no bump, #400 moved six words in it
# with no bump. Three precedents, all correct, because making a vocabulary fix
# a migration is the treadmill #450 measured.
#
# So `payload` exists for the READ-SET rather than for the declaration. A
# client says it reads the payload, is believed, and is told that no contract
# row will ever answer for it - `payload_digest` does. A contract row in this
# namespace is refused by `test_no_contract_declares_a_payload_surface`,
# because it would be claiming a versioning this engine does not do.
AUDIENCE = {
    "table": "reader of the read model",
    "meta": "author of lines",
    "report": "reader of the report",
    "payload": "reader of the published shape",
}

# What `payload_digest` must NOT carry. Both are the same string - the engine
# version - and `schema()`'s own docstring already says it is not a gate: it
# moves for a docs fix and stands still while the shape moves. A digest that
# carried it would fire on every release, and a stale-payload alarm that fires
# when nothing is stale is one a client learns to ignore.
#
# The third exclusion is the digest itself, which is published inside the
# thing it sums.
PROVENANCE = ("engine", "payload_digest")


def _namespace(surface: str) -> str:
    """Which grammar a surface is written in."""
    for prefix in ("meta", "report", "payload"):
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
    # A namespace names all of itself when written bare.
    if read in AUDIENCE and surface.startswith(read + ":"):
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

    # A READ THAT NAMES NOTHING IS SILENCE WITH EXTRA CHARACTERS (#453), and
    # this was the same fail-open one argument to the left. `weght.kg` - one
    # transposition in a map a person maintains - matched no surface, so every
    # touched row landed in `not_yours` and the verdict came back "may stay".
    # A read-set of pure typos earned the reassuring answer.
    #
    # REFUSED RATHER THAN DROPPED, and refused whole rather than partly. A
    # client whose map is 29 parts right is the dangerous case: the verdict
    # would be computed over 29 surfaces and read as the answer for 30. This
    # is the rule the floor already states - a partial answer to "may I stay"
    # has the same shape as a wrong one.
    payload = None
    if stated:
        from .api import schema
        # ONE BUILD, shared by the catalogue and the digest. Asking for both
        # separately paid for `schema()` twice on every verdict.
        payload = schema()
        cat = catalogue(payload)
        bad = [(r, unresolved(r, cat)) for r in reads if r and r.strip()]
        bad = [(r, why) for r, why in bad if why]
        if bad:
            raise ValueError(
                "this read-set names surfaces this engine does not publish, "
                "and a verdict computed over less than a client reads is the "
                "one answer here that can cost a silent data loss: "
                + "; ".join(f"{r} ({why})" for r, why in bad))

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
        # NAMED BACK RATHER THAN SILENTLY IGNORED (#453). A payload read can
        # never appear in `because` - no contract row is allowed to name one -
        # so a client that declared some and saw them nowhere in the answer
        # would reasonably conclude the verdict covered them. It does not.
        "payload_reads": sorted(r for r in (reads or ())
                                if r and (r == "payload"
                                          or _namespace(r) == "payload")),
        # CARRIED ON EVERY VERDICT, including one where no payload read was
        # declared, because the client that has not thought about the payload
        # is the one that needs telling it moves on its own clock.
        "payload_digest": (payload_digest() if payload is None
                           else _digest_of(payload)),
    }


def catalogue(payload: dict | None = None) -> dict:
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
    - `report` is the public read surface on `Vitai`: things that reach a
      consumer through the report and have no table. `questions` is one, which
      is why contract 49 could not move a column and still asked something.
      METHODS AND PROPERTIES BOTH - a `property` is not `callable()`, and
      asking that question rejected `report:policy`, which a real client reads
      and this engine really publishes.
    - `payload` is what `api.schema()` returns, by top-level key, each mapped
      to every key beneath it at any depth. So `payload:fields.aliases` and
      `payload:impact.floor` both resolve and neither resolves under the
      other. Derived from the payload for the reason the rest of this is
      derived: a list kept beside it would agree with it and catch nothing.
    """
    return {ns: _namespace_catalogue(ns, payload) for ns in AUDIENCE}


def _namespace_catalogue(ns: str, payload: dict | None = None):
    """One namespace of the catalogue, built on its own.

    ONE AT A TIME because the payload one is not free: `api.schema()` costs
    about a second, almost all of it `field_types` over 208 fields, and
    resolving a table surface has no business paying for it. Resolving one
    surface built the whole catalogue at first, which turned a 24-test file
    into an 83-second one.
    """
    if ns == "table":
        from .db import DERIVED_TABLES
        from .schema import KEYS
        tables = {name: set(cols) for name, cols in KEYS.items()}
        for name, cols in DERIVED_TABLES.items():
            tables.setdefault(name, set()).update(cols)
        return tables
    if ns == "meta":
        from .schema import META_KEYS
        return set(META_KEYS)
    if ns == "report":
        from .api import Vitai
        return {name for name in dir(Vitai) if not name.startswith("_")}
    from .api import schema
    body = schema() if payload is None else payload
    return {key: _keys_under(value) for key, value in body.items()}


def _keys_under(value) -> set[str]:
    """Every mapping key anywhere inside `value`.

    Flat on purpose. A client declares what it reads at the granularity it
    knows - `payload:fields.display_name` is a spec key three levels down and
    `payload:fields.daily` is a dataset one level down - and both are honest
    answers to "what do you read". The check is that the name exists under
    that payload key, not that it exists at a depth somebody chose.
    """
    out: set[str] = set()
    stack = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                out.add(str(k))
                stack.append(v)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return out


def _digest_of(payload: dict) -> str:
    """The digest of a payload, with provenance and the digest itself removed.

    NO `default=` ENCODER on the dump, deliberately. A fallback would let an
    unserialisable value through and hash its `repr`, which on most objects
    carries a memory address - so the digest would change every run and be
    read as the payload moving. An unserialisable payload should be a loud
    failure here rather than a quiet one in a client's CI.
    """
    body = {k: v for k, v in payload.items() if k not in PROVENANCE}
    builds = body.get("builds")
    if isinstance(builds, dict):
        # `builds.this` is the engine version again, one level down.
        body["builds"] = {k: v for k, v in builds.items() if k != "this"}
    blob = json.dumps(body, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def payload_digest() -> str:
    """A bit that changes when the published shape does, and not otherwise.

    THE ANSWER TO THE QUESTION `assess` CANNOT ANSWER. The payload is not
    contract-versioned, so a client cannot ask "may I stay" about it - there
    is no number to stay at. It can ask "has it moved", and the remedy when it
    has is to re-read the payload, which costs nothing and is never wrong.

    THAT ASYMMETRY IS THE WHOLE DESIGN. How much resolution a declaration owes
    a consumer is set by how expensive the remedy is. Migrating a read model
    is expensive, so the contract declaration is a table of surfaces and a
    client must be told whether the change is one of its. Re-reading a
    vocabulary is free, so one bit is enough, and one bit cannot rot the way a
    hand-kept table can.
    """
    from .api import schema
    return _digest_of(schema())


def unresolved(surface: str, cat: dict | None = None) -> str | None:
    """Why `surface` names nothing a client can reach, or None if it resolves.

    An entry nothing can read tells nobody anything, which is the vacuity this
    check exists for. Used on both sides now: on the DECLARATION, so a contract
    cannot claim to have touched something that does not exist, and on a
    client's READ-SET, so a client cannot be told it may stay on the strength
    of surfaces it named wrongly.

    `cat` is the catalogue, passed in when a caller is resolving many surfaces:
    building it reads the whole published payload, and doing that once per read
    turned a verdict into a hundred of them.
    """
    ns = _namespace(surface)
    if cat is None:
        cat = {ns: _namespace_catalogue(ns)}
    body = surface.split(":", 1)[1] if ns != "table" else surface

    # A namespace written bare names all of itself, which `_covers` has always
    # accepted. It said nothing here, so the two halves of one grammar
    # disagreed and only the half nothing called was strict.
    if surface in AUDIENCE:
        return None

    if ns == "meta":
        if body not in cat["meta"]:
            return f"'{body}' is not one of schema.META_KEYS"
        return None

    head, _, field = body.partition(".")

    if ns == "report":
        if head.startswith("_") or head not in cat["report"]:
            return (f"'report:{head}' names no public read surface on Vitai, "
                    f"so nothing publishes it")
        # A report surface has no declared column list to check `field`
        # against; that it is really published is what can be checked.
        return None

    if ns == "payload":
        if head not in cat["payload"]:
            return (f"'{head}' is not a key of the shape api.schema() "
                    f"publishes")
        if field and field not in cat["payload"][head]:
            return f"nothing under 'payload:{head}' is named '{field}'"
        return None

    if head not in cat["table"]:
        return f"'{head}' is not a table in the read model"
    if field and field not in cat["table"][head]:
        return f"'{head}' has no column '{field}'"
    return None
