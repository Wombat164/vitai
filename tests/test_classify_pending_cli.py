"""The dry run an importer can actually reach from a shell (#448).

#425 landed `pending_problems` and `Record.classify_pending` as an API-only
read surface. P9 (`docs/model.md`, `ARCHITECTURE.md` 2a, `docs/plan-v3.md` 7b)
says a capability ships as BOTH a CLI command and a `vitai.api` method, the CLI
being a thin harness over the same API rather than a parallel path - and an
importer spooling a file and appending it is exactly the caller that runs from
a shell.

THE INPUT DOOR IS `append`'s, and that is the point rather than an economy.
This command answers what `vitai append` would do with these rows, so it has to
read the same bytes the same way; a second reader is a second answer waiting to
happen. `append` takes JSONL on stdin and takes it nowhere else, so `--from`
would have been an input door the write does not have, and a file classified
through it could not then be appended by the same means.

THE PROSE IS NOT BEHIND A FLAG. The refusal sentences are the sentences
`append_many` will raise with, and a dry run whose default output is quieter
than the failure it predicts is not a dry run: an operator would read `refused`
and have to run the real write to learn why. They print BELOW the table rather
than in it - the verdicts are a table and the sentences are prose, and a column
wide enough for a paragraph is neither.

Synthetic data only. The 1,354 -> 3,091 day is #425's own fixture: a
MyFitnessPal day exported at lunchtime and completed after dinner.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta
from typing import NamedTuple

from vitai.api import Vitai
from vitai.cli import main
from vitai.jsonl import PENDING_VERDICTS, append_many, load, pending_problems

HELD, COMPLETED = 1354, 3091
DAY, SOURCE = "2030-05-01", "mfp-export"
REF = f"{DAY}/{SOURCE}"
UNSYNCED = "2030-04-01/mfp-export"


def _repo(tmp_path):
    root = tmp_path / "content"
    main(["init", str(root)])
    return root


def _daily(**kw):
    """A daily row as an importer legally prepares it: NO `recorded_at`."""
    row = {"date": DAY, "kcal_in": None, "source": SOURCE, "note": None,
           "steps": None, "_gen": 8}
    row.update(kw)
    return row


def _jsonl(*rows) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


class Run(NamedTuple):
    out: str
    err: str
    status: int | str


def _run(argv, stdin, capsys) -> Run:
    """One CLI invocation, its streams, and the status it exited with.

    The buffer is drained first: `_repo` prints as it stamps the skeleton, and
    a leftover greeting line inside `out` makes a JSONL assertion fail on a
    line this command never wrote.
    """
    capsys.readouterr()
    sys.stdin = io.StringIO(stdin)
    status: int | str = 0
    try:
        main(argv)
    except SystemExit as e:
        status = e.code if isinstance(e.code, int) else str(e.code)
    finally:
        sys.stdin = sys.__stdin__
    captured = capsys.readouterr()
    return Run(captured.out, captured.err, status)


# ---------------------------------------------------------------- P9 itself

def test_the_capability_is_reachable_from_the_cli(tmp_path, capsys):
    """THE DEFECT #448 NAMES. `Vitai.classify_pending` answers the question an
    importer asks and no command reached it, so the answer existed only for a
    caller that could already import Python.

    Against the tree as it was this failed on argparse: `invalid choice:
    'classify-pending'`.
    """
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])

    out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                       _jsonl(_daily(kcal_in=COMPLETED, supersedes=REF)),
                       capsys)

    assert status == 0
    assert "correction" in out
    assert REF in out


def test_the_command_is_a_harness_over_the_api_and_not_a_second_path(
        tmp_path, capsys):
    """P9's actual claim: the same answer, not an answer of the same shape.
    `--json` emits the API's dicts, so a consumer shelling out and a consumer
    importing read one contract."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])
    pending = [_daily(kcal_in=COMPLETED), _daily(kcal_in=COMPLETED, supersedes=REF),
               _daily(kcal_in=COMPLETED, supersedes=UNSYNCED)]

    out, _err, status = _run(["classify-pending", "daily", "--json", "--root", str(root)],
                       _jsonl(*pending), capsys)

    assert status == 0
    assert [json.loads(ln) for ln in out.splitlines() if ln.strip()] == \
        Vitai(root).classify_pending("daily", pending)


def test_the_verdict_words_are_the_ones_the_module_publishes(tmp_path, capsys):
    """A verdict a reader of the CLI cannot enumerate is a string to guess at,
    and the enumeration already exists."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])

    out, _err, _ = _run(["classify-pending", "daily", "--json", "--root", str(root)],
                  _jsonl(_daily(kcal_in=COMPLETED),
                         _daily(kcal_in=COMPLETED, supersedes=REF),
                         _daily(kcal_in=COMPLETED, supersedes=UNSYNCED)),
                  capsys)
    said = [json.loads(ln)["verdict"] for ln in out.splitlines() if ln.strip()]

    assert said == ["restatement", "correction", "unmatched"]
    assert set(said) <= set(PENDING_VERDICTS)


# ------------------------------------------------- one input door, not two

def _peer_ahead(tmp_path):
    """A laptop holds the day, stamped a day ahead of the clock asking."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)],
                device="laptop",
                now=datetime.now().astimezone() + timedelta(days=1))
    return root


def test_the_dry_run_reads_stdin_exactly_as_the_write_does(tmp_path, capsys):
    """THE REASON THERE IS NO `--from`. Blank lines and `//` comments are
    `append`'s reader being lenient, and a dry run that answered about a
    different set of rows than the write consumes would be worse than no dry
    run - a caller acts on it.

    So the same text goes through both commands and the counts agree.
    """
    root = _repo(tmp_path)
    text = ("// an exporter's header comment\n"
            + json.dumps(_daily(kcal_in=HELD)) + "\n"
            + "\n"
            + json.dumps(_daily(date="2030-05-02", kcal_in=COMPLETED)) + "\n")

    dry, _err, status = _run(["classify-pending", "daily", "--json", "--root", str(root)],
                       text, capsys)
    assert status == 0
    classified = [json.loads(ln) for ln in dry.splitlines() if ln.strip()]

    written, _err, status = _run(["append", "daily", "--root", str(root)], text, capsys)
    assert status == 0
    appended = [json.loads(ln) for ln in written.splitlines() if ln.strip()]

    assert [a["row"] for a in classified] == [1, 2]
    assert len(classified) == len(appended) == 2


def test_a_line_the_write_would_reject_is_rejected_here_in_the_same_words(
        tmp_path, capsys):
    """The other half of one reader: a malformed line fails identically, and
    names the same line number, on both commands."""
    root = _repo(tmp_path)
    text = json.dumps(_daily(kcal_in=HELD)) + "\nnot json\n"

    dry = _run(["classify-pending", "daily", "--root", str(root)], text, capsys)
    write = _run(["append", "daily", "--root", str(root)], text, capsys)

    assert isinstance(dry.status, str) and dry.status == write.status
    assert "line 2" in dry.status


def test_an_empty_batch_is_refused_rather_than_answered_about(tmp_path, capsys):
    """`append` exits on nothing to write; asking about nothing is the same
    mistake one command earlier."""
    root = _repo(tmp_path)

    _out, _err, status = _run(["classify-pending", "daily", "--root", str(root)], "\n", capsys)

    assert isinstance(status, str) and "stdin" in status


# ---------------------------------------------- the prose, and where it goes

def test_the_refusal_sentences_are_the_ones_the_engine_would_raise(
        tmp_path, capsys):
    """WHAT MAKES THE SENTENCES REACHABLE WITHOUT A SECOND COMMAND.
    `pending_problems` returns the sentences `append_many` raises with;
    `classify_pending` hands each of them back as the `reason` of the row it
    refuses. So printing the reasons prints the problems - checked as an
    equality rather than claimed, because the day the two diverge this command
    would quietly under-report a failing write."""
    root = _peer_ahead(tmp_path)
    pending = [_daily(kcal_in=COMPLETED, supersedes=REF)]

    out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                       _jsonl(*pending), capsys)
    problems = pending_problems(root / "data", "daily", pending)

    assert problems, "the fixture produced no refusal to print"
    assert status == 2
    for sentence in problems:
        # The stamp inside the sentence is the one the asking write WOULD
        # carry, and these are two different asks a moment apart, so what has
        # to match is the sentence either side of it.
        head, _, tail = sentence.partition(" and this write is stamped ")
        assert head in out, (head, out)
        assert tail.split(", ", 1)[1] in out


def test_the_prose_prints_by_default_and_below_the_table(tmp_path, capsys):
    """The one design question #448 names, answered both ways at once: the
    verdicts stay a scannable table, one line per row, and the sentences print
    under it keyed by row number rather than in a column."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])

    out, _err, _ = _run(["classify-pending", "daily", "--root", str(root)],
                  _jsonl(_daily(kcal_in=COMPLETED)), capsys)
    lines = out.splitlines()

    table = [ln for ln in lines if ln.startswith("  1  ")]
    assert len(table) == 1
    assert "restatement" in table[0]
    assert len(table[0]) < 60, table[0]

    prose = [ln for ln in lines if ln.startswith("row 1:")]
    assert len(prose) == 1
    assert "supersedes" in prose[0]
    assert lines.index(prose[0]) > lines.index(table[0])


def test_a_row_with_nothing_to_explain_gets_no_paragraph(tmp_path, capsys):
    """`new` carries an empty reason, and printing an empty one would put a
    blank paragraph under every ordinary import."""
    root = _repo(tmp_path)

    out, _err, _ = _run(["classify-pending", "daily", "--root", str(root)],
                  _jsonl(_daily(kcal_in=HELD)), capsys)

    assert "  1  new" in out
    assert "row 1:" not in out


# ------------------------------------------------------- the shell contract

def test_a_refused_batch_exits_two_and_says_the_whole_write_is_refused(
        tmp_path, capsys):
    """`append_many` is all-or-nothing, so one refused row means NO row lands
    - and a table of five verdicts with one `refused` in it does not say that.

    Exit 2 is `may` and `safety`'s status for 'the answer is no', which makes
    `classify-pending ... && append ...` the correct shell sentence rather
    than a thing a script has to parse JSON to decide.
    """
    root = _peer_ahead(tmp_path)

    # A row the record has never seen, and a correction the peer's stamp
    # defeats. The batch is legal apart from the second row, which is the
    # case where "one refused row" and "no row lands" differ.
    out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                             _jsonl(_daily(date="2030-05-02", kcal_in=COMPLETED),
                                    _daily(kcal_in=COMPLETED, supersedes=REF)),
                             capsys)

    assert status == 2
    assert "  1  new" in out and "  2  refused" in out
    assert "would raise over 1 of 2 row(s), and no row would land" in out


def test_an_answerable_batch_exits_zero(tmp_path, capsys):
    """The other side of the same sentence: a restatement is not a refusal,
    and exiting non-zero on it would stop an import the engine accepts."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])

    _out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                     _jsonl(_daily(kcal_in=COMPLETED)), capsys)

    assert status == 0


def test_json_mode_still_emits_the_rows_when_the_write_is_refused(
        tmp_path, capsys):
    """The status is for the shell and the rows are for the consumer. Exiting
    before printing would make the machine-readable mode blind in exactly the
    case it is most needed."""
    root = _peer_ahead(tmp_path)

    out, _err, status = _run(["classify-pending", "daily", "--json", "--root", str(root)],
                       _jsonl(_daily(kcal_in=COMPLETED, supersedes=REF)), capsys)
    rows = [json.loads(ln) for ln in out.splitlines() if ln.strip()]

    assert status == 2
    assert [r["verdict"] for r in rows] == ["refused"]
    assert rows[0]["reason"]


# ------------------------------------------------------------ what it is not

def test_the_dry_run_writes_nothing(tmp_path, capsys):
    """A question that appends is not a question, and this one runs from a
    shell where the next command is the write."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])
    before = sorted((p.name, p.read_bytes())
                    for p in (root / "data").rglob("*.jsonl"))

    out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                             _jsonl(_daily(kcal_in=COMPLETED, supersedes=REF)),
                             capsys)

    # The command RAN, so the untouched file below is a result about it and
    # not about a command that exited before reaching the record.
    assert status == 0 and "correction" in out
    assert sorted((p.name, p.read_bytes())
                  for p in (root / "data").rglob("*.jsonl")) == before
    assert [r["kcal_in"] for r in load(root / "data", "daily")] == [HELD]


def test_an_event_dataset_is_refused_by_the_command_not_by_a_traceback(
        tmp_path, capsys):
    """`emissions` has one door and it is not the generic append, so there is
    no append here to answer about. The API says so; the harness has to hand
    that sentence over rather than let it out as a stack trace."""
    root = _repo(tmp_path)

    _out, _err, status = _run(["classify-pending", "emissions", "--root", str(root)],
                     _jsonl({"nothing": "here"}), capsys)

    assert isinstance(status, str), status
    assert "assert_delivery" in status


def test_an_unknown_dataset_is_refused_with_the_real_list(tmp_path, capsys):
    """Same as `dataset`: argparse refuses the name against the engine's own
    keys rather than a KeyError arriving after a root is resolved."""
    root = _repo(tmp_path)

    run = _run(["classify-pending", "nosuchthing", "--root", str(root)],
               "{}\n", capsys)

    assert run.status == 2
    assert "invalid choice" in run.err
    assert "daily" in run.err


# ------------------------------------------------- the vocabulary an agent
# needs to read the answer

def test_the_verdict_vocabulary_is_published_where_a_consumer_can_read_it():
    """A verdict word a consumer cannot enumerate is a string to guess at, and
    `jsonl.PENDING_VERDICTS` is engine-private: importing it is the asymmetry
    #158 names, where the CLI can reach a fact an agent cannot.

    So it rides in the `schema()` payload the way `session_types` (#350) and
    `ordering` (#308) do - one place, reached by `vitai schema --json` and the
    MCP `schema` tool without either being taught anything.
    """
    from vitai.api import schema

    assert schema()["pending_verdicts"] == list(PENDING_VERDICTS)


def test_the_command_orders_its_tally_by_the_published_vocabulary(
        tmp_path, capsys):
    """And the CLI reads the ORDER off that list rather than off the batch, so
    the same two verdicts read the same way whichever order the rows arrive
    in. Here they arrive restatement-first and the tally still says new
    first."""
    root = _repo(tmp_path)
    append_many(root / "data", "daily", [_daily(kcal_in=HELD)])

    out, _err, _ = _run(["classify-pending", "daily", "--root", str(root)],
                        _jsonl(_daily(kcal_in=COMPLETED),
                               _daily(date="2030-05-02", kcal_in=COMPLETED)),
                        capsys)
    tally = out.splitlines()[0]

    assert "  1  restatement" in out and "  2  new" in out
    assert tally.endswith("1 new, 1 restatement"), tally


def test_one_sentence_covers_its_rows_instead_of_repeating_per_row(
        tmp_path, capsys):
    """One refusal covers every row naming the same reference - the engine
    returns ONE sentence for it and hands the same string back on each row -
    so printing it per row would make the loudest paragraph in the output a
    duplicate, and would say two things are wrong where the write reports one.

    Grouped rather than deduplicated: which rows it is about is the part a
    person acts on.
    """
    root = _peer_ahead(tmp_path)
    twice = [_daily(kcal_in=COMPLETED, supersedes=REF),
             _daily(kcal_in=COMPLETED - 91, supersedes=REF)]

    out, _err, status = _run(["classify-pending", "daily", "--root", str(root)],
                             _jsonl(*twice), capsys)
    problems = pending_problems(root / "data", "daily", twice)

    assert status == 2
    assert len(problems) == 1, "the fixture stopped producing one sentence"
    assert out.count("would retire nothing") == 1
    assert "rows 1, 2: " in out
