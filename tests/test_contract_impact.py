"""The contract-impact declaration, and the gates that stop it rotting (#451).

#450 measured what the contract cadence costs downstream: across contracts 47
to 52, one of the client's six absorptions was a forced move and three moved a
number and nothing else. The declaration this file guards is the mechanism -
the engine states what each contract TOUCHED, the client states what it READS,
and the verdict is the intersection.

Every test here exists because of a specific way such a declaration dies:

- nobody adds a row for the new contract        -> `every_contract_declares`
- a row is added that names nothing real        -> `every_surface_resolves`
- a contract declares an empty list             -> `no_contract_touches_nothing`
- the row disagrees with what actually moved    -> `the_note_head_is_covered`
- a change kind sits in the vocabulary unused   -> `every_change_kind_is_used`
- silence starts meaning safety                 -> `an_unstated_read_set_moves`
- it stops being reachable by a consumer        -> `the_published_payload...`
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from vitai.api import contract_impact, schema
from vitai.contracts import (FLOOR, FORCES_MOVE, assess, declaration, impact,
                             touched, unresolved)
from vitai.db import CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[1]


# ---- the declaration is complete and real -----------------------------------

def test_every_contract_from_the_floor_declares_what_it_touched():
    """The way this dies first is that nobody adds the row.

    It is invisible when it happens - nothing fails, the contract ships, and
    the client that trusted the declaration is told a contract touched nothing
    when it touched something. That is worse than having no declaration, so
    the gate is on the WHOLE range rather than on the newest entry.
    """
    declared = set(declaration())
    owed = set(range(FLOOR, int(CONTRACT_VERSION) + 1))
    assert not owed - declared, (
        f"contracts {sorted(owed - declared)} moved CONTRACT_VERSION and "
        f"declared nothing in semantics/contract_impact.toml")


def test_the_declaration_invents_no_contract():
    """A row for a contract that does not exist tells a client to handle a
    shape it will never see - the same defect `test_neither_table_invents_a_
    contract` catches one table over."""
    ahead = {n for n in declaration() if n > int(CONTRACT_VERSION)}
    assert not ahead, f"declared contracts the engine never shipped: {sorted(ahead)}"


def test_nothing_is_declared_below_the_floor():
    """The floor is a promise that below it the API refuses rather than
    answering partially. A stray row under it makes the refusal a lie."""
    below = {n for n in declaration() if n < FLOOR}
    assert not below, (
        f"contracts {sorted(below)} are declared below the stated floor of "
        f"{FLOOR}; either move the floor or drop them, but the two must agree")


def test_every_surface_resolves_to_something_a_client_can_reach():
    """An entry naming a surface nothing publishes tells nobody anything.

    This is the vacuity shape applied to a declaration: it is not enough for
    a row to exist, it has to be able to matter to somebody. The catalogue is
    derived from `schema.KEYS`, `db.DERIVED_TABLES`, `schema.META_KEYS` and
    the public methods on `Vitai` - never from the declaration itself, because
    a control that reads the data it validates agrees with it by construction.
    """
    bad = []
    for n, entries in sorted(declaration().items()):
        for e in entries:
            why = unresolved(e["surface"])
            if why:
                bad.append(f"contract {n}: {e['surface']} - {why}")
    assert not bad, "declared surfaces that resolve to nothing:\n  " + "\n  ".join(bad)


def test_no_contract_touches_nothing():
    """THE GATE AGAINST THE TREADMILL ITSELF, and the reason it is here rather
    than in a lint.

    `CONTRACT_VERSION`'s own comment says "bump when a table/column changes
    shape". A contract that can name no surface it touched is a bump that
    should not have happened, and the cost of one is paid downstream: every
    client re-emits, moves a pin, and lands a commit that changes a number.

    Failing at the moment the contract is written costs the author a sentence.
    Not failing costs three client absorptions per no-op bump, which is what
    #450 measured.
    """
    empty = [n for n, entries in declaration().items() if not entries]
    assert not empty, (
        f"contracts {sorted(empty)} declare no touched surface. A contract "
        f"that touched nothing published is a bump that should not have "
        f"happened - drop the bump, or name what moved")


def test_every_change_kind_is_one_of_the_closed_three():
    kinds = {e["change"] for entries in declaration().values() for e in entries}
    assert kinds <= set(FORCES_MOVE), (
        f"undeclared change kinds: {sorted(kinds - set(FORCES_MOVE))}")


def test_every_change_kind_in_the_vocabulary_is_used():
    """The vacuity rule turned on this design's own vocabulary.

    `retired` and `meaning` were drafted and dropped because nothing between
    47 and 54 exercises them. A kind nobody uses is a kind nobody has had to
    get right, and it will be wrong the first time somebody reaches for it -
    so the contract that needs one adds it, with an entry that uses it.
    """
    used = {e["change"] for entries in declaration().values() for e in entries}
    unused = set(FORCES_MOVE) - used
    assert not unused, (
        f"change kinds declared and never used: {sorted(unused)}. Add one "
        f"when a contract needs it, not before")


# ---- the declaration agrees with what actually moved -------------------------

def _note_heads() -> dict[int, str]:
    """The first clause of each contract note in `db.py`.

    The notes have a stable shape - ``# 52: `difference_lo` and
    `difference_hi` on `comparability` - the two ends of ...`` - and the head
    is the part before the dash. It names what moved, in backticks, and it was
    written by the person who moved it.
    """
    src = (ROOT / "src" / "vitai" / "db.py").read_text(encoding="utf-8")
    start = src.index("# Bump when a table/column changes shape")
    block = src[start:src.index("CONTRACT_VERSION =", start)]
    notes: dict[int, str] = {}
    cur = None
    for line in block.splitlines():
        m = re.match(r"^# (\d+): (.*)$", line)
        if m:
            cur = int(m.group(1))
            notes[cur] = m.group(2)
        elif cur is not None and line.startswith("#"):
            notes[cur] += " " + line[1:].strip()
    return {n: re.split(r"\s+-\s+", text, maxsplit=1)[0]
            for n, text in notes.items()}


def _declared_tokens(contract: int) -> set[str]:
    """Every table, column and meta name the declaration mentions."""
    tokens: set[str] = set()
    for e in touched(contract):
        body = e["surface"].split(":", 1)[-1]
        head, _, field = body.partition(".")
        tokens.add(head)
        if field:
            tokens.add(field)
            tokens.add(f"{head}.{field}")
    return tokens


def test_the_declaration_covers_what_the_contract_note_says_moved():
    """UNDER-DECLARING IS CAUGHT BY THE ENGINE'S OWN WORDS.

    This is what stops the file being filled in carelessly, and it is the
    reason the design needs no honesty from the author. `db.py` already
    carries a note per contract naming what moved; a declaration that omits
    one of those names disagrees with the engine's own account of itself.

    Only identifiers that RESOLVE are demanded. A note head also names values
    (`band`, `outage`), which are not surfaces and have nothing to declare.
    """
    heads = _note_heads()
    missing = []
    for n in sorted(declaration()):
        head = heads.get(n)
        if head is None:
            continue
        declared = _declared_tokens(n)
        for token in re.findall(r"`([^`]+)`", head):
            resolves = any(unresolved(form) is None
                           for form in (token, f"meta:{token}",
                                        f"report:{token}"))
            if not resolves:
                continue                       # a value, not a surface
            if token in declared:
                continue
            head_part = token.split(".")[0]
            if head_part in declared:
                continue
            missing.append(f"contract {n}: db.py names `{token}` and the "
                           f"declaration does not")
    assert not missing, "\n  ".join([""] + missing)


# ---- the verdict, and the direction it fails in ------------------------------

def test_an_unstated_read_set_is_told_to_move():
    """SILENCE MUST NEVER MEAN SAFETY.

    A client that has not said what it reads has told us nothing, and a
    verdict of "you may stay" derived from nothing is the one outcome here
    that can cost a client a silently dropped row.
    """
    assert assess(52, 54, None)["must_move"] is True


def test_an_empty_read_set_is_not_a_stated_one():
    """The live fail-open this was found by, rather than a hypothetical.

    `--reads ""` split to `[]`, which is not None, so the verdict came back
    STAY having matched nothing at all. Fixed in `assess` and not in the CLI,
    because the API is a door too and a control on one caller is not a
    control.
    """
    assert assess(52, 54, [])["must_move"] is True
    assert assess(52, 54, [" ", ""])["must_move"] is True


def test_a_reader_of_a_widened_vocabulary_must_move():
    """Contract 48 moved no column and a client matching `kind` exhaustively
    drops every `band` row. That is the case a boolean could not carry."""
    verdict = assess(47, 48, ["crossings"])
    assert verdict["must_move"] is True
    assert [r["surface"] for r in verdict["because"]] == ["crossings.kind"]


def test_a_client_that_does_not_read_the_surface_may_stay():
    """The measured case: the client pinned at 52 reads none of what 53 and 54
    touched, so it may stay, and #450 found nothing broke while it did."""
    verdict = assess(52, 54, ["daily", "sessions", "weight", "crossings"])
    assert verdict["must_move"] is False
    assert {r["surface"] for r in verdict["not_yours"]} == {
        "overlaps", "comparability.overlap_ref",
        "meta:supersedes_device", "meta:supersedes_seq"}


def test_a_read_set_stated_by_column_is_taken_at_its_word():
    """A client that says it reads `crossings.metric` is not told about
    `crossings.kind`. Asking a client to be precise and then ignoring the
    precision is how a read-set stops being worth stating."""
    assert assess(47, 48, ["crossings.metric"])["must_move"] is False
    assert assess(47, 48, ["crossings.kind"])["must_move"] is True


def test_added_alone_never_forces_a_move():
    """Every `added` surface across the declared range, checked as one claim:
    adopting a new column is a choice and a choice is not a migration."""
    for n in sorted(declaration()):
        adds = [e["surface"] for e in touched(n) if e["change"] == "added"]
        if not adds:
            continue
        assert assess(n - 1, n, adds)["must_move"] is False, (
            f"contract {n} forces a move on surfaces it only added")


def test_below_the_floor_refuses_rather_than_answering_partially():
    with pytest.raises(ValueError, match=str(FLOOR)):
        impact(31, 54)


def test_the_default_upper_bound_is_this_engine():
    assert contract_impact(52, reads=["weight"])["contract_to"] == int(CONTRACT_VERSION)


# ---- it stays reachable by the consumer it exists for ------------------------

def test_the_published_payload_carries_the_declaration():
    """A declaration a client cannot reach without importing private surface
    is one it will re-derive and get wrong - the argument `schema()` already
    makes for `fields`, `ordering` and `phase_rule`."""
    published = schema()["impact"]
    assert published["floor"] == FLOOR
    assert published["changes"] == dict(FORCES_MOVE)
    assert set(published["contracts"]) == {str(n) for n in declaration()}


def test_the_cli_answers_and_its_exit_code_is_the_answer():
    """P9: the capability ships as a command as well as a method, and the CI
    step this exists for reads the exit code rather than the prose. Three
    outcomes, three codes: 0 stay, 1 move, 2 cannot answer."""
    def run(*args):
        return subprocess.run([sys.executable, "-m", "vitai.cli",
                               "contract-impact", *args],
                              capture_output=True, text=True)

    stay = run("--since", "52", "--upto", "54", "--reads", "weight,daily")
    assert stay.returncode == 0, stay.stderr
    assert "STAY" in stay.stdout

    move = run("--since", "47", "--upto", "48", "--reads", "crossings")
    assert move.returncode == 1
    assert "MOVE" in move.stdout

    refused = run("--since", "31", "--upto", "54", "--reads", "weight")
    assert refused.returncode == 2
    assert str(FLOOR) in refused.stderr

    silent = run("--since", "52", "--upto", "54")
    assert silent.returncode == 1, "an unstated read-set must not exit 0"


# ---- the human-readable copies cannot drift from the machine-readable one ----

DOC_PATHS = ("README.md", "wiki/content/explanation/platform.md")


def _rendered_row(entry: dict) -> str:
    verdict = "**must move**" if entry["forces_move"] else "need not move"
    # A CONDITION IS PART OF THE VERDICT (#464), not a footnote. A published
    # row reading `must move` beside a declaration that says `must move unless
    # one-writer` is the disagreement this issue was raised for, one table
    # over - so the rendering carries it and this gate holds the two together.
    if entry.get("unless"):
        verdict += f" unless `{entry['unless']}`"
    return (f"| `{entry['surface']}` | {entry['change']} | "
            f"{entry['contract']} | {verdict} |")


@pytest.mark.parametrize("path", DOC_PATHS)
def test_the_published_tables_carry_every_declared_row(path):
    """The same failure the three-way contract-history test was written for:
    the README's table stopped at contract 8 and the wiki's at 4 while the
    engine was at 16, and nothing failed while they drifted. A declaration a
    client reads in the docs and an engine that answers differently is worse
    than either alone."""
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [_rendered_row(e)
               for n in sorted(declaration()) for e in touched(n)
               if _rendered_row(e) not in text]
    assert not missing, f"{path} is missing rows:\n  " + "\n  ".join(missing)


@pytest.mark.parametrize("path", DOC_PATHS)
def test_the_published_tables_invent_no_row(path):
    """The other direction. A row in the docs that the declaration does not
    hold tells a client to handle a change that never happened."""
    text = (ROOT / path).read_text(encoding="utf-8")
    real = {_rendered_row(e) for n in declaration() for e in touched(n)}
    found = re.findall(r"^\| `[^`]+` \| \w+ \| \d+ \| .*\|$", text, re.M)
    assert not set(found) - real, (
        f"{path} carries impact rows the declaration does not: "
        f"{sorted(set(found) - real)}")


@pytest.mark.parametrize("path", DOC_PATHS)
def test_no_impact_row_can_be_read_as_a_migration_row(path):
    """A latent trap rather than a live bug, caught while writing the table.

    `test_both_tables_agree_on_which_release_shipped_each_contract` reads any
    line matching ``^| <digits> | <cell> |`` as a migration row and takes the
    second cell as the release that shipped that contract. An impact table
    beginning with the contract number parses as one, and the two tables
    silently merge - which is why the contract number is the THIRD column and
    not the first.

    Checked rather than remembered: the ordering is load-bearing and the
    reason is invisible from the table itself.
    """
    text = (ROOT / path).read_text(encoding="utf-8")
    for entry in (e for n in declaration() for e in touched(n)):
        row = _rendered_row(entry)
        assert row in text
        assert not re.match(r"^\| (\d+) \| ", row), (
            f"this impact row parses as a migration row: {row}")


# --- the audience a namespace advertises, against what it admits (#470) ------

def test_the_report_namespace_admits_any_published_read_not_only_the_report():
    """THE CLAIM AND THE CATALOGUE, pinned together so they cannot drift apart
    again.

    `AUDIENCE["report"]` read "reader of the report" while
    `_namespace_catalogue("report")` admits every public read on `Vitai`. So a
    surface no report renders resolved under it and was described to clients
    as reaching them through the report - and the only declaration ever
    written in that namespace, `report:questions.kind` at contract 49, is one:
    the demo's `questions()` returns rows and its rollup renders none of them.

    This asserts the discrepancy as a DECLARED property rather than leaving it
    a lie. The prefix is historical; what it admits is any published read, and
    the audience string now says so. If somebody later narrows the catalogue
    to things the report really renders, this fails and points at the audience
    string that would then be wrong in the other direction.
    """
    from vitai import contracts

    # It admits a read the report does not render...
    assert contracts.unresolved("report:questions") is None
    # ...and the audience no longer promises the report.
    assert "report" not in contracts.AUDIENCE["report"]
    assert contracts.AUDIENCE["report"] == "caller of a published read"


def test_the_engine_makes_no_other_claim_about_reaching_a_consumer():
    """P9a's enforceable half, as a check rather than a paragraph.

    The engine cannot see whether a client reaches a surface, so the one thing
    it can hold is that it does not ASSERT one. Every audience string here
    describes who could call or read the engine; none claims that anybody
    does. A future string saying a surface IS consumed would be unverifiable
    from this side and fails here.
    """
    from vitai import contracts

    for ns, says in sorted(contracts.AUDIENCE.items()):
        assert says.startswith(("reader of", "author of", "caller of")), (
            ns, says, "an audience names who COULD read it, never that "
                      "anybody does - the engine cannot check the second")
