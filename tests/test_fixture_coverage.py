"""A dataset cannot ship without the shipped example knowing it exists.

`generate_demo.py` builds the example and `--check` byte-compares it, so the
demo cannot drift from its generator. Nothing checked whether the generator
knew a dataset existed at all.

Adding `instruments` (#311) I wrote `examples/demo/data/instruments.jsonl` by
hand. The generator had never heard of it, so `--check` reported drift on a
file nothing could regenerate - a message that reads exactly like the ordinary
"regenerate and commit" and is not fixable that way. The full suite, five
gates and ruff were all green - thirty-six test files read the demo, and not
one of them asks whether a dataset reaches it at all - and the `demo` job is
the fast one nobody reads. It was red across two pushes.

So this is an ALLOWLIST that fails closed: every dataset is either written by
the demo generator or written down here as deliberately absent, with the
reason. Not every dataset belongs in one athlete's example. The absence has to
be a decision somebody made rather than one nobody saw.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from vitai.schema import KEYS

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
sys.path.insert(0, str(ROOT / "examples"))


# Datasets the demo deliberately does not write, and why. An entry here is a
# decision; an entry that gains a writer has to leave, or the register rots
# into a list of excuses the way any backlog does.
DEMO_OMITS = {
    "artifacts":
        "the demo ships no bytes, and an artifact row with a content address "
        "behind which nothing is stored would make the example's own "
        "`verify_artifacts` report a fault on a clean checkout",
    "protocols":
        "no row in the demo sets `protocol`, so there is nothing for a "
        "protocols row to be the procedure of; what the demo says about how "
        "it weighs is a journal line, which is a claim about practice rather "
        "than a declared procedure",
    "regimes":
        "a regime is a bounded interval in which a figure means something "
        "else, and the demo is deliberately uneventful - inventing one would "
        "add a confound to the record that exists to be readable",
    # THE HONEST ABSENCE, and the one worth reading. This is not a dataset the
    # demo forgot; it is one the demo CANNOT write, and the reason is the rule
    # itself rather than a gap in the fixture.
    "overlaps":
        "the demo's scale and DEXA overlap on two same-day readings and an "
        "overlaps census needs three, so writing one would mean inventing a "
        "third paired day to satisfy a fixture register - which is the "
        "fabrication the whole dataset exists to refuse, arriving through a "
        "test; the demo's comparability row keeps its `overlap_ref` sentence "
        "for exactly this reason, and that pairing is the fact",
}


def _demo_writes() -> set[str]:
    """Datasets the generator declares it writes.

    FROM A REGISTER THE GENERATOR EXPORTS, not from anything derived. Two
    earlier shapes were both wrong in the way this file exists to prevent.

    Reading the committed directory would call a hand-written file covered,
    which is the case that prompted all of this.

    Substring-matching the generator's SOURCE for `("name",` was the second
    attempt and is worse, because it looks careful. It reports a dataset as
    written when its name appears in a comment - so commenting out a writer,
    the most natural way to remove one, leaves the gate green. It was already
    armed: `("equipment",` sits in that file today inside a tuple of
    set-configuration keys, so the day `equipment` became a dataset the demo
    would ship without it and nothing would say so. And it went red on a
    behaviour-preserving refactor of the writer loop, printing advice that
    would not have fixed anything - which is how a gate gets deleted.

    `generate_demo.WRITES` is a register, and `main` asserts its own writer
    loop matches it, so the two cannot drift.
    """
    from generate_demo import WRITES

    return set(WRITES)


def test_every_dataset_is_written_by_the_demo_or_declared_absent() -> None:
    missing = sorted(set(KEYS) - _demo_writes() - set(DEMO_OMITS))
    assert not missing, (
        f"{missing} exist in the schema and the demo generator does not write "
        f"them. Either write them in `generate_demo.py` or add them to "
        f"DEMO_OMITS with the reason - a dataset the shipped example has never "
        f"heard of is one no consumer of that example can discover")


def test_the_register_does_not_keep_what_has_been_fixed() -> None:
    """The half that stops this becoming a place to put things. A dataset that
    gains a writer has to leave the register."""
    stale = sorted(set(DEMO_OMITS) & _demo_writes())
    assert not stale, (
        f"{stale} are declared absent from the demo and the generator writes "
        f"them. Remove them from DEMO_OMITS")


def test_no_declared_absence_names_a_dataset_that_does_not_exist() -> None:
    """Back-pressure the other way: a renamed or retired dataset must not sit
    here forever explaining why something nobody has heard of is missing."""
    unknown = sorted(set(DEMO_OMITS) - set(KEYS))
    assert not unknown, unknown


def test_every_committed_demo_file_is_one_the_generator_produces() -> None:
    """THE FAILURE THAT PROMPTED THIS, stated directly rather than as drift.

    `--check` compares bytes, so a hand-written file it cannot regenerate
    reports as drift and the advice it prints - regenerate and commit - does
    not fix it. This says the actual thing: the generator does not produce
    this file."""
    import tempfile

    from generate_demo import _build, _read_all

    # THE WHOLE TREE, and the same suffix set `--check` compares. The first
    # version globbed `data/*.jsonl` only, so a hand-written track under
    # `tracks/` walked past it - and that directory is the one where the
    # personal gate permits coordinates ON THE GROUNDS that they are the
    # generator's own output. A file nobody generated sitting there makes that
    # grounds false, which is a worse failure than the one this started with.
    # BUILT INTO A SCRATCH DIRECTORY, which is what `--check` does. Asking the
    # generator what it produces by running it is the only answer that cannot
    # drift from what it actually produces.
    scratch = Path(tempfile.mkdtemp()) / "demo"
    _build(scratch)
    produced = set(_read_all(scratch))
    on_disk = set(_read_all(DEMO))
    orphans = sorted(on_disk - produced)
    assert not orphans, (
        f"{orphans} are committed under examples/demo and the generator does "
        f"not produce them. Regenerating will not fix this: give them a source "
        f"in `generate_demo.py`, or delete them")


def test_the_declared_absences_are_really_absent() -> None:
    """A reason for an absence that is not an absence is worse than no reason:
    it tells the next reader not to look."""
    for name in DEMO_OMITS:
        path = DEMO / "data" / f"{name}.jsonl"
        rows = ([json.loads(line) for line
                 in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if path.exists() else [])
        assert not rows, (name, len(rows))


@pytest.mark.parametrize("name,reason", sorted(DEMO_OMITS.items()))
def test_each_absence_gives_a_reason_worth_reading(name: str, reason: str) -> None:
    """A register whose entries say "not needed" teaches nothing.

    Word count is the weakest of the three checks here and was the only one in
    the first version, which was close to theatre: "not applicable to a
    single-athlete demo because it is out of scope for us right now" is
    fourteen words and says nothing. The two below are the ones with teeth."""
    assert len(reason.split()) >= 12, (name, reason)


def test_no_two_absences_share_a_reason() -> None:
    """The copy-paste case, which word count cannot see: a new dataset added
    to the register by duplicating the line above it inherits an explanation
    that was true of something else."""
    seen: dict[str, str] = {}
    for name, reason in sorted(DEMO_OMITS.items()):
        assert reason not in seen, (name, seen.get(reason))
        seen[reason] = name


def test_each_absence_talks_about_its_own_dataset() -> None:
    """A reason that never names what it is about has usually drifted from it.

    This is the check that would have caught the `protocols` entry, which
    claimed the demo's weigh-ins name a protocol slug and that the procedure
    lives in the README. Neither was true: no demo row sets `protocol` at all,
    and the prose about weighing is a journal row."""
    for name, reason in sorted(DEMO_OMITS.items()):
        stem = name.rstrip("s")
        assert stem in reason.lower(), (name, reason)


# --- the same register one level down: FIELDS, not datasets (#423) ------------
#
# THE DEFECT THIS EXISTS FOR. `examples/demo` carried zero rows with a stated
# absence - none in `weight`, none in `daily`, none in `sessions` - while
# contract 51 shipped six reason codes and `test_field_population` reported the
# pair covered, because `bea` writes two. That register pools the demo and the
# fifteen personas, so a field one persona writes reads as written. The demo is
# not one fixture among sixteen: it is the one downstream clients build from, and
# `vitai-lens` rebuilds it through the real engine deliberately, because a demo
# assembled by any other route would only prove the lens can read a database
# this repo made. A client could therefore rebuild at contract 53, raise its
# pin, render all six absence reasons as one grey square, and pass every job it
# has. A FIXTURE THAT DOES NOT EXERCISE A FEATURE CANNOT PROVE A CLIENT HANDLES
# IT, and that is the same shape as #412 one level out: a check that passes
# because the case never occurs.
#
# WHY THE SCOPE IS "SOME FIXTURE WRITES IT AND THE DEMO DOES NOT", and not
# "every field the schema declares". The complementary class - a field NOTHING
# in this repo writes - is already registered, with reasons, in
# `test_field_population.UNWRITTEN`. Restating those 34 entries here would put
# one fact in two lists, and the fact this repo keeps relearning is that two
# copies of one register drift. So the two are disjoint by construction and
# there is a test below that says so. What this file adds is exactly the class
# the pooled measurement hides: the corpus PROVES the field is writable, and the
# fixture a client reads does not present it.
#
# A BACKLOG, NOT AN APPROVAL, on `UNWRITTEN`'s terms. Nothing below is endorsed.
# Some entries are decisions that should never leave; some are plain gaps, and
# they say which they are, because an entry that reads like a decision and is
# really a shrug is worse than no entry. The second half of the gate is what
# stops it rotting: a field that reaches the demo has to LEAVE the register.
#
# GROUPED BY REASON RATHER THAN ONE LINE PER FIELD, which is a deliberate
# difference from `DEMO_OMITS` above. That register has four entries and can
# afford a sentence with teeth each. Forty fields at twelve words apiece would
# be forty sentences written to clear a gate, which is the failure
# `test_each_absence_gives_a_reason_worth_reading` warns about in as many words.
# The fields that share a cause share an entry, and the entry has to survive
# being read.
DEMO_FIELD_OMITS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # --- contract 52, and the answer is the same refusal the dataset is built
    # on. Checked because #423 asked whether it was the same shape as 51: it is
    # unexercised here too, and unlike 51 it CANNOT be fixed from this record.
    ("A DECISION. The demo's one comparability row is `comparable` over an "
     "overlap of two same-day pairs, and `bias` is refused beside "
     "`comparable` outright. The two paired days are 07:15 and 19:33 against "
     "the clinic's 10:15, so the observed differences (-1.2 and +0.2 kg on "
     "scale minus dexa) are not separable from the athlete's own day - this "
     "record's rollup says so itself, refusing to read the weight trend "
     "because weigh-ins span 12.3 h, which alone accounts for about 1.02 kg. "
     "Writing `difference_lo`/`difference_hi` would publish that number as a "
     "cross-instrument range, which is the fabrication contract 52 exists to "
     "refuse arriving through a fixture register. And the engine already "
     "refuses to make a statement about a pair from two differences - `MIN_PAIRS` "
     "is 3, because 'two differences are the observations themselves rather "
     "than a statement about the pair' - so the ends would assert over two "
     "pairs what the census beside them may not assert at all. `vera` earns "
     "them over 101 paired days; the demo's two cannot write the contract 53 "
     "census, which is the same absence recorded above.",
     ("comparability.bias", "comparability.spread",
      "comparability.difference_lo", "comparability.difference_hi")),
    # --- the protocols omission, reaching the observation rows it would sit on
    ("A DECISION, and a consequence of the `protocols` entry above rather than "
     "a separate one: no demo row may name a procedure while the demo ships no "
     "procedure to name. Declaring `protocol` on a weigh-in or a measurement "
     "with nothing behind the slug would make that entry's own sentence false.",
     ("weight.protocol", "measurements.protocol")),
    # --- the artifacts omission, same shape
    ("A DECISION, and the `artifacts` entry above reaching the row that would "
     "point at one. `otto` photographs a club ergometer console, so his "
     "sessions name the image; the demo ships no bytes, and a session naming "
     "an artifact nothing stores would make its own `verify_artifacts` report "
     "a fault on a clean checkout.",
     ("sessions.artifact",)),
    # --- what this athlete's instruments actually report
    ("A DECISION. The demo's watch reports a sleep DURATION and the record "
     "carries it as `sleep_h`. The four personas logging the interval need it "
     "for a question the demo does not ask - `bea` works nights, so her sleep "
     "sits in the middle of the calendar day and which day it belongs to is "
     "the whole point.",
     ("daily.sleep_start", "daily.sleep_end")),
    ("A DECISION. The demo's four instruments are all still in use, so their "
     "interval is open at the far end. `to_date` is what closes one, and "
     "inventing a retirement date would date it to today - the schema says so "
     "where the field is declared.",
     ("instruments.to_date",)),
    ("A DECISION. The demo's sets are typed into a gym app or written in a "
     "notebook between sets, with the athlete as `origin`; `read_by` names who "
     "read a value off an instrument's display, and there is no display in "
     "that chain.",
     ("sets.read_by",)),
    ("A DECISION. The demo's gym block is a barbell, one bodyweight movement "
     "and two machines, recorded at the resolution the athlete has - "
     "`seat_pos`, `machine`, `angle_class`. `maja` trains on circuit machines "
     "with numbered levers and pads, timed sets in rounds, a prescribed tempo "
     "and unilateral work, and those eight fields are that record's shape "
     "rather than a hole in this one.",
     ("sets.angle_deg", "sets.lever_pos", "sets.pad_pos", "sets.round",
      "sets.side", "sets.tempo", "sets.duration_s")),
    ("A DECISION. `maja` logs off printed packaging, so her rows carry what a "
     "label states. The demo's intake is a calorie app's day summary and its "
     "meals resolve against a food table, and neither knows fibre, sugar or "
     "sodium - a fixture cannot present a figure its stated source does not "
     "publish.",
     ("daily.fibre_g", "daily.sugar_g", "daily.sodium_mg",
      "meals.fibre_100g", "meals.sugar_100g", "meals.sodium_mg_100g")),
    ("A DECISION. Nothing in the demo's medical rows is the kind of state "
     "`expects` exists for: a GLP-1 agonist, or breastfeeding, where the "
     "safety layer must stop reading a real signal as a failure. The demo has "
     "a calf strain, a physio visit and an achilles niggle, and giving the "
     "athlete a medication to populate a field would be the invention this "
     "corpus refuses.",
     ("medical.expects",)),
    ("A DECISION. No demo event was cancelled or moved, so nothing needs the "
     "field that explains why one was: the 5k took place and said so in "
     "`outcome`. `maja`'s gym closure was called off and her `reason` says the "
     "works were postponed.",
     ("events.reason",)),
    ("A DECISION. Each of the demo's four threshold changes already says why "
     "in `reason`, which is the field that carries the argument; a `note` "
     "beside it would be the same sentence written twice, and one of the two "
     "copies would drift.",
     ("thresholds.note",)),
    ("A DECISION. The demo's goals are floors, ceilings and one approach, and "
     "`target_hi` is the far end of a BAND - a target with two sides. There is "
     "no band goal here, and `polarity: band` is what would earn the second "
     "number.",
     ("goals.target_hi",)),
    ("A DECISION. This athlete answers to nobody in the record: no coach, no "
     "training partner, no one told. `accountability` names who else knows, "
     "and the demo's goals carry the argument for existing in `rationale` "
     "instead of a second free-prose field beside it.",
     ("goals.accountability", "goals.note")),
    # `weight.note` LEFT THIS REGISTER at #427, and what it turned on is worth
    # keeping. The entry said a per-weigh-in `note` would be "prose about a
    # number rather than the number", and that was right for every row this
    # record then had: on a row carrying `kg`, a sentence beside the reading is
    # a second, unvalidatable account of it.
    #
    # It stops being true on a row carrying NO reading. The morning the scale
    # read 71.2 and the record rejected it has no number to be prose about -
    # `absent_reason: error` says the class of failure and cannot say that the
    # scale had been moved onto the bath mat, and contract 51 forbids parking
    # the rejected value in `kg` where a reader would take it for a weigh-in.
    # So the note is the only place the fact can live, and the register's own
    # argument is what says where it may not.
    # --- and now the gaps, said as gaps -----------------------------------
    ("A GAP, NOT A DECISION, and the sharpest one here. The demo writes the "
     "RETIRED spelling of the goal-standing axis: every goals line carries "
     "`status`, which contract 25 retired in favour of `lifecycle_status`, and "
     "no line carries the current key. Legal forever and read forward by "
     "`policy`, so nothing is broken - but the engine has already been bitten "
     "by exactly this shape once (#273, a rule that read the old key alone and "
     "silently skipped every goal written since the split), and a client whose "
     "only fixture is the demo would never meet the current spelling. Left "
     "here rather than fixed because rewriting thirteen goals lines moves the "
     "goal story the whole demo narrative is built on.",
     ("goals.lifecycle_status",)),
    ("A GAP, NOT A DECISION. The same clinic scan is provenance-complete in "
     "`weight` - origin `dexa`, capture `connector`, evidence 'clinic scan' - "
     "and provenance-bare in `measurements`, where the `body_fat_pct` row it "
     "produced carries `source` alone. Nothing justifies the difference; it is "
     "the shape the two writers were written in.",
     ("measurements.origin", "measurements.capture", "measurements.read_by")),
    ("A GAP, NOT A DECISION. The demo records the carrying chain on its "
     "weigh-ins - `vendor-app>vendor-api` - and not on its runs, though both "
     "arrive by connector from a registered instrument, and its watch reports "
     "an average heart rate without the peak the same file would hold. `nora` "
     "has both.",
     ("sessions.path", "sessions.max_hr")),
    ("A GAP, NOT A DECISION. The demo's one achievement, 'First 21 km in one "
     "run', is dated 2030-06-24 and names the 21.1 km run of 2030-06-23 - "
     "which is precisely the event-versus-entry split `occurred_date` was "
     "added for. Not filled here because 2030-06-23 is a Sunday: the "
     "effective date would move into the previous ISO week, and that is a "
     "derived-tier change rather than a fixture one.",
     ("achievements.occurred_date",)),
    ("A GAP, NOT A DECISION. The demo's day summary carries energy and "
     "protein, the two figures its goals and the protein floor read, and "
     "stops there. Carbohydrate and fat are ordinary macros any calorie app "
     "reports, so their absence says something about this generator rather "
     "than about the athlete.",
     ("daily.carb_g", "daily.fat_g")),
)


def _flat_field_omits() -> list[str]:
    return [f for _reason, fields in DEMO_FIELD_OMITS for f in fields]


def _written(paths: list[Path]) -> set[tuple[str, str]]:
    """(dataset, field) pairs carrying a non-null value on some row.

    MEASURED, NOT ASSERTED, and measured the same way `test_field_population`
    measures it, so "written" means one thing in both files.
    """
    out: set[tuple[str, str]] = set()
    for path in paths:
        dataset = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for key, value in json.loads(line).items():
                if value is not None:
                    out.add((dataset, key))
    return out


def _gap(demo: set[tuple[str, str]], anywhere: set[tuple[str, str]],
         machinery: set[str], omitted_datasets: set[str]) -> set[str]:
    """Fields some fixture writes, on a dataset the demo does write, that no
    demo row carries.

    A PURE FUNCTION over two measurements, so the rule can be tested against
    inputs this repo does not contain - see the control at the bottom of this
    file. The version that reads the real corpus inline cannot be shown to fail.
    """
    return {f"{ds}.{k}" for ds, k in anywhere - demo
            if k not in machinery and ds not in omitted_datasets}


def _measure_fields() -> set[str]:
    from vitai.schema import KEYS

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_field_population import MACHINERY

    demo = _written(sorted((DEMO / "data").glob("*.jsonl")))
    personas = _written(sorted(
        (ROOT / "tests" / "fixtures" / "personas").glob("*/data/*.jsonl")))
    declared = {(ds, k) for ds, keys in KEYS.items() for k in keys}
    return _gap(demo, (demo | personas) & declared, MACHINERY, set(DEMO_OMITS))


def test_every_field_some_fixture_writes_reaches_the_demo_or_is_registered() -> None:
    """The check #423 asked for, and it would have caught #423.

    `weight.absent_fields` and `weight.absent_reason` sat in this gap - written
    by `bea`, absent from the fixture every downstream client builds from - and
    the pooled register was green about both.
    """
    new = sorted(_measure_fields() - set(_flat_field_omits()))
    assert not new, (
        f"{len(new)} field(s) are written somewhere in this repo's fixtures and "
        f"nowhere in the demo: {new}. Either write them through "
        f"`examples/generate_demo.py` - never by editing the JSONL - or add "
        f"them to DEMO_FIELD_OMITS with the reason and whether it is a decision "
        f"or a gap. A client whose only fixture is the demo cannot test what the "
        f"demo does not present")


def test_the_field_register_does_not_keep_what_has_been_fixed() -> None:
    """The half that stops a backlog becoming a list of excuses."""
    stale = sorted(set(_flat_field_omits()) - _measure_fields())
    assert not stale, (
        f"{stale} are registered as absent from the demo and the demo now "
        f"writes them (or nothing writes them anywhere, which belongs in "
        f"`test_field_population.UNWRITTEN` instead). Remove them")


def test_the_field_register_names_real_fields() -> None:
    """A typo exempts nothing and hides a real gap."""
    from vitai.schema import KEYS

    every = {f"{ds}.{k}" for ds, keys in KEYS.items() for k in keys}
    unknown = sorted(set(_flat_field_omits()) - every)
    assert not unknown, f"{unknown} name no field in the schema"


def test_no_field_is_registered_twice() -> None:
    """Two reasons for one absence means one of them is wrong, and the reader
    cannot tell which."""
    flat = _flat_field_omits()
    dupes = sorted({f for f in flat if flat.count(f) > 1})
    assert not dupes, dupes


def test_the_two_registers_stay_disjoint() -> None:
    """THE ANTI-DRIFT CONTROL, and the reason this register is scoped the way it
    is. A field NOTHING writes belongs to `test_field_population.UNWRITTEN`; a
    field the corpus writes and the demo does not belongs here. A field in both
    lists is one fact in two places, which is how the next reader learns to
    trust neither."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_field_population import UNWRITTEN

    both = sorted(set(_flat_field_omits()) & set(UNWRITTEN))
    assert not both, (
        f"{both} are registered in both DEMO_FIELD_OMITS and UNWRITTEN. The "
        f"first says the demo lacks a field the corpus has; the second says "
        f"nothing has it at all. They cannot both be true")


@pytest.mark.parametrize("reason,fields", DEMO_FIELD_OMITS)
def test_each_field_absence_says_which_kind_it_is(
        reason: str, fields: tuple[str, ...]) -> None:
    """A GAP and a DECISION are different facts with different futures, and a
    register that blurs them is a list of excuses with better prose. Length is
    the weak half of this check, as it is for `DEMO_OMITS` above; the half with
    teeth is that the entry has to commit."""
    assert reason.startswith(("A DECISION", "A GAP")), reason
    assert len(reason.split()) >= 20, (fields, reason)


def test_no_two_field_absences_share_a_reason() -> None:
    """The copy-paste case: a new group added by duplicating the one above it
    inherits an explanation that was true of something else."""
    seen: dict[str, tuple[str, ...]] = {}
    for reason, fields in DEMO_FIELD_OMITS:
        assert reason not in seen, (fields, seen.get(reason))
        seen[reason] = fields


def test_the_field_measurement_can_fail() -> None:
    """THE CONTROL ON THE GATE, without which none of the above is evidence.

    Written against inputs this repo does not contain, because a measurement
    exercised only by the corpus it measures is a measurement whose failure
    nobody has seen. Every clause of `_gap` is what one of these turns on.
    """
    demo = {("weight", "kg")}
    anywhere = demo | {("weight", "absent_reason"), ("weight", "recorded_at"),
                       ("overlaps", "paired_days")}
    assert _gap(demo, anywhere, {"recorded_at"}, {"overlaps"}) == \
        {"weight.absent_reason"}, "the plain case does not report"
    assert _gap(anywhere, anywhere, set(), set()) == set(), \
        "a demo writing everything still reports something"
    assert _gap(demo, anywhere, {"recorded_at", "absent_reason"},
                {"overlaps"}) == set(), "machinery is not exempted"
    assert _gap(demo, anywhere, {"recorded_at"}, set()) == \
        {"weight.absent_reason", "overlaps.paired_days"}, (
        "a dataset the demo deliberately omits is not exempted, so every field "
        "of it would be reported and the register would hold the same decision "
        "twice")


# --- what a shipped fixture owes about its own holes (#428) -------------------
#
# THE REASON FOR THIS CHANGED WHEN #428'S THIRD OPTION LANDED, and the entry is
# rewritten rather than left standing on an argument that stopped being true.
# It used to say the rollup would MISCOUNT a silent hole, because `readings`
# subtracted stated absence only. It no longer does: the coverage section now
# reports observed, explained-absent and silent apart, and a fixture with a
# silent hole would render one - correctly.
#
# What survives is a different and smaller claim, about the fixtures rather
# than about the engine. `examples/demo` is what every conformance client
# calibrates against, and a shipped record whose own holes go unexplained
# teaches the shape this contract exists to end. The engine may report an
# unexplained hole; a fixture should not have one to report.
#
# So this is no longer load-bearing for the count, and it is still worth
# holding. It also keeps the corpus honest about the fact stated in
# `test_the_absence_line_is_exercised_only_by_construction` below: the branch
# that renders a silent hole cannot be reached from anything this repo ships.


def _silent_holes(rows: list[dict], field: str) -> list[dict]:
    """Rows whose `field` is null and which say nothing about why.

    A PURE FUNCTION over rows, on `_gap`'s pattern, so its own failure can be
    shown against a row this repo does not contain.
    """
    from vitai.schema import absent_fields

    return [r for r in rows
            if r.get(field) is None and field not in absent_fields(r)]


def _weight_rows() -> list[tuple[str, dict]]:
    paths = (sorted((DEMO / "data").glob("weight.jsonl"))
             + sorted((ROOT / "tests" / "fixtures" / "personas")
                      .glob("*/data/weight.jsonl")))
    out = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append((str(path.relative_to(ROOT)), json.loads(line)))
    return out


def test_no_shipped_weigh_in_is_missing_without_saying_so() -> None:
    """Every null `kg` in the corpus is EXPLAINED."""
    silent = [(where, r) for where, r in _weight_rows()
              if _silent_holes([r], "kg")]
    assert not silent, (
        f"{len(silent)} weight row(s) carry no `kg` and no `absent_fields` "
        f"saying why: {[(w, r.get('date')) for w, r in silent][:5]}. The "
        "rollup will report them as unexplained, which is correct and is not "
        "the point: this corpus is what conformance clients calibrate "
        "against, and a shipped record whose own holes go unexplained teaches "
        "the shape contract 51 exists to end. State the absence on the row")


def test_the_absence_line_is_exercised_only_by_construction() -> None:
    """MEASURED, so the sentence above is a fact rather than a belief.

    The rollup's absence line has a branch for a silent hole and nothing this
    repo ships can reach it - which is #424's subject one file over, and the
    reason `test_vitai.py` exercises that branch against rows written by hand.
    If the corpus ever gains one, the test above goes red first and this says
    why the synthetic case stopped being the only one.
    """
    from vitai.report import holes

    rows = [r for _where, r in _weight_rows()]
    explained, unexplained = holes(rows, "kg")
    assert explained, "no shipped weigh-in states an absence at all"
    assert not unexplained, (
        f"{unexplained} silent hole(s) in the corpus - the branch is reachable "
        "now, so the synthetic case in test_vitai.py is no longer the only "
        "thing exercising it")


def test_the_silent_hole_measurement_can_fail() -> None:
    """THE CONTROL. Written against rows this repo does not contain, because a
    check that only ever sees a clean corpus is a check nobody has watched
    fail."""
    stated = {"date": "2030-05-01", "kg": None, "absent_fields": "kg",
              "absent_reason": "not-performed"}
    silent = {"date": "2030-05-02", "kg": None}
    other = {"date": "2030-05-03", "kg": None, "absent_fields": "source",
             "absent_reason": "not-performed"}
    present = {"date": "2030-05-04", "kg": 80.0}

    assert _silent_holes([silent], "kg") == [silent], "a bare null is a hole"
    assert _silent_holes([stated], "kg") == [], "a stated absence is not"
    assert _silent_holes([other], "kg") == [other], (
        "a reason about a DIFFERENT field explains nothing about this one")
    assert _silent_holes([present], "kg") == [], "a reading is not a hole"


# --- every published code, in the artifact clients read (#427) ----------------
#
# THE RULE, AND IT IS NOT "MORE COVERAGE": a field the engine publishes must
# appear in the artifact every conformance client reads, IN EVERY FORM IT CAN
# TAKE. Six absence codes published and one exercised is five codes whose
# rendering no client has ever been forced to get right, and the first one to
# appear in a real record appears in production.
#
# THIS ALREADY HAPPENED, which is why the bar here is every value rather than
# `test_a_vocabulary_field_shows_more_than_one_of_its_values`'s more-than-one.
# A downstream client absorbed contract 51 and dropped every row whose only
# content was an absence, because nothing in the demo it calibrates against had
# one. It was correct against its fixtures and wrong about the record. The
# general register one file over holds the floor for forty vocabularies; this
# holds the ceiling for the one that has already cost something.
#
# SCOPED TO THE DEMO, deliberately. A persona proves the engine can hold the
# state; only the demo proves a client meeting it has been made to render it,
# because the demo is what `vitai-lens` rebuilds through the real engine.


def _demo_absence_reasons() -> dict[str, set[str]]:
    """Reason codes the demo writes, per dataset."""
    out: dict[str, set[str]] = {}
    for path in sorted((DEMO / "data").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            reason = json.loads(line).get("absent_reason")
            if reason is not None:
                out.setdefault(path.stem, set()).add(reason)
    return out


def test_the_demo_exercises_every_absence_reason() -> None:
    """All six, or the ones missing are states no client has been tested on."""
    from vitai.schema import ABSENT_REASONS

    written = set().union(*_demo_absence_reasons().values() or [set()])
    missing = sorted(ABSENT_REASONS - written)
    assert not missing, (
        f"{len(missing)} of {len(ABSENT_REASONS)} absence reasons never appear "
        f"in examples/demo: {missing}. A client can render them as the same "
        "grey square and pass every job it has - which is what happened. Write "
        "a row the record earns, in the generator, rather than relaxing this")


def test_the_demo_writes_no_reason_the_schema_does_not_publish() -> None:
    """The other direction, and it is not symmetry for its own sake: a typo
    would leave a published code unexercised while this file reported the set
    complete."""
    from vitai.schema import ABSENT_REASONS

    written = set().union(*_demo_absence_reasons().values() or [set()])
    assert not written - ABSENT_REASONS, sorted(written - ABSENT_REASONS)


def test_each_contract_51_dataset_states_an_absence() -> None:
    """`weight`, `daily` and `sessions` are the three datasets that permit a
    row whose values are null, and a client renders each of them separately.
    Six codes all landing on one dataset would leave the other two exactly as
    untested as before."""
    from vitai.schema import KEYS

    permitted = {ds for ds in ("weight", "daily", "sessions")
                 if "absent_reason" in KEYS[ds]}
    written = _demo_absence_reasons()
    missing = sorted(permitted - set(written))
    assert not missing, (
        f"{missing} permit a stated absence and the demo states none there, so "
        "a client's rendering of that dataset's holes is untested")
