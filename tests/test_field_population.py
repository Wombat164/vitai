"""A field specified and never written is worse than an absent one (#204).

An absent field is an obvious gap. A validated, documented, empty field looks
like a solved problem in every audit, every schema tour and every review, and
the gap is only found by counting rows. That counting kept being redone by
hand, which is why the class kept being rediscovered - so it is done here, on
every build.

TWO FAILURE MODES, and separating them is what makes the principle actionable.

  SPECIFIED AND NEVER WRITTEN. The schema promises something the record cannot
  deliver, and every consumer written against it degrades silently to the null
  path. This reads as covered.

  WRITTEN AND NEVER READ. The worse of the two: an athlete or an importer did
  the work of recording something and the engine discards it. Mode one wastes
  a reviewer's attention; mode two wastes the record's own evidence.

FOUR DISEASES PRESENT AS ONE SYMPTOM, so "tell importers to write it" treats
only the third:

  - `sessions.planned` CANNOT be written. It lives on a session row, and
    `sessions` has no occurred flag, so a plan that was not followed has no row
    to live on. The one case the field exists to serve is the one it
    structurally cannot represent.
  - `daily.coverage` has NO SINGLE WRITER. One field on a row several sources
    write to, so whichever importer sets it wins uncontested and its opinion
    becomes the whole day's claim.
  - `thresholds` and `meals` have NO PRODUCER. Nothing generates them; they
    wait for a surface that was never built.
  - `weight.kg_lo`/`kg_hi` have NO CONSUMER. The producer exists and works.

WHY THESE ARE REGISTERS AND NOT A RED BUILD. Failing on all 104 at once would
be a check with no legal path to green, which is the #38 mistake and the
reason a check like this gets deleted rather than satisfied. So the lists
below are a BACKLOG, not an approval: nothing here is endorsed, and the tests
fail on anything NEW in either mode, and equally on an entry that has since
been fixed. The second half is what stops the register becoming a place to put
things - a field that gains a writer or a reader has to leave the list.

MEASURED, NOT ASSERTED. "Written" means non-null on some row of this repo's
own fixtures: the demo and the nine personas. "Read" means named by a module
other than the two that merely declare and project every key - `schema.py`
lists them and `db.py` copies them into SQLite, and neither is a consumer, as
`kg_lo` demonstrates by being in the read model with nothing reading it.
"""

from __future__ import annotations

import glob
import json
import pathlib

# Machine-stamped or structural: present on nearly every row by construction,
# and not what this is about.
MACHINERY = {"recorded_at", "device", "supersedes", "date", "_gen"}

# THE BACKLOG. Not an approval - see the module docstring.
UNWRITTEN = (
    "artifacts.bytes",
    "artifacts.captured_at",
    "artifacts.kind",
    "artifacts.media_type",
    "artifacts.note",
    "artifacts.origin",
    "artifacts.reason",
    "artifacts.removed",
    "artifacts.sha256",
    "daily.artifact",
    "daily.carb_g",
    "daily.derived_from",
    "daily.derived_op",
    "daily.fat_g",
    "daily.fibre_g",
    "daily.origin_evidence",
    "daily.path",
    "daily.read_by",
    "daily.sleep_end",
    "daily.sleep_start",
    "daily.sodium_mg",
    "daily.sugar_g",
    "emissions.basis_claims",
    "emissions.contract",
    "emissions.kind",
    "emissions.metric",
    "emissions.policy_asof",
    "emissions.statement",
    "emissions.surface",
    "emissions.week",
    "events.reason",
    "goals.target_hi",
    "inferences.depends_on",
    "inferences.note",
    "meals.derived_from",
    "meals.derived_op",
    "meals.fibre_100g",
    "meals.path",
    "meals.sodium_mg_100g",
    "meals.sugar_100g",
    "measurements.artifact",
    "measurements.derived_from",
    "measurements.derived_op",
    "measurements.modelled",
    "measurements.origin_evidence",
    "measurements.path",
    "measurements.protocol",
    "measurements.read_by",
    "protocols.slug",
    "protocols.text",
    "regimes.anchored_by",
    "regimes.dataset",
    "regimes.field",
    "regimes.from_date",
    "regimes.kind",
    "regimes.note",
    "regimes.source",
    "regimes.text",
    "regimes.to_date",
    "sessions.artifact",
    "sessions.derived_from",
    "sessions.derived_op",
    "sessions.location",
    "sessions.modelled",
    "sets.angle_deg",
    "sets.derived_from",
    "sets.derived_op",
    "sets.duration_s",
    "sets.lever_pos",
    "sets.pad_pos",
    "sets.path",
    "sets.resistance_level",
    "sets.round",
    "sets.side",
    "sets.tempo",
    "thresholds.note",
    "weight.artifact",
    "weight.body_fat_hi",
    "weight.body_fat_lo",
    "weight.body_fat_pct",
    "weight.kg_hi",
    "weight.kg_lo",
    "weight.modelled",
)

UNREAD = (
    # Written by ines from row one, and read by nothing that groups a trend
    # by it. The reading she took on the gym scale after dinner is labelled
    # `fed-evening-clothed` and still enters the weekly mean beside her
    # `fasted-post-void` ones, which is her expectation ines-E2.
    "weight.protocol",
    # Written by ines, validated by `schema`, and rendered by nothing.
    # Validation is not a consumer: `kg_lo` is validated too, and the
    # issue names it as the example of mode two. A client that wants to
    # show "4 out of 10" still cannot, because nothing carries the bound
    # to the surface (#246 gave the record the fact; a consumer for it
    # is separate work).
    "daily.mood_scale",
    "daily.pain_scale",
    "sessions.rpe_scale",
    "sets.rpe_scale",
    "achievements.occurred_date",
    "daily.alcohol",
    "daily.coverage",
    "daily.feel",
    "daily.pain_side",
    "goals.accountability",
    "goals.on_miss",
    "goals.on_period_end",
    "goals.on_success",
    "goals.rationale",
    "medical.onset_date",
    "medical.provider_type",
    "sessions.planned",
    "sessions.setting",
    "sessions.weather",
    "sessions.with",
)


def _measure() -> tuple[set[str], set[str]]:
    """(unwritten, unread) over this repo's own fixtures and modules."""
    from vitai.schema import KEYS

    root = pathlib.Path(__file__).resolve().parents[1]
    written: set[tuple[str, str]] = set()
    for f in (glob.glob(str(root / "tests/fixtures/personas/*/data/*.jsonl"))
              + glob.glob(str(root / "examples/demo/data/*.jsonl"))):
        dataset = pathlib.Path(f).stem
        for line in pathlib.Path(f).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for key, value in json.loads(line).items():
                if value is not None:
                    written.add((dataset, key))

    consumers = [p.read_text(encoding="utf-8")
                 for p in (root / "src" / "vitai").glob("*.py")
                 if p.name not in ("schema.py", "db.py")]

    unwritten, unread = set(), set()
    for dataset, keys in KEYS.items():
        for key in keys:
            if key in MACHINERY:
                continue
            name = f"{dataset}.{key}"
            if (dataset, key) not in written:
                unwritten.add(name)
            elif not any(f'"{key}"' in t or f"'{key}'" in t for t in consumers):
                unread.add(name)
    return unwritten, unread


def test_no_new_field_is_specified_and_never_written():
    """A field nothing writes promises something the record cannot deliver."""
    unwritten, _ = _measure()
    new = sorted(unwritten - set(UNWRITTEN))
    assert not new, (
        f"{len(new)} field(s) are specified and written nowhere in this "
        f"repo's own fixtures: {new}. Either write them in the demo or a "
        "persona - a fixture that only holds the populated case proves "
        "nothing about the empty one - or add them to UNWRITTEN with the "
        "reason, which records a gap rather than hiding one")


def test_no_new_field_is_written_and_never_read():
    """The worse mode: the record holds evidence and the engine discards it."""
    _, unread = _measure()
    new = sorted(unread - set(UNREAD))
    assert not new, (
        f"{len(new)} field(s) are populated and read by nothing: {new}. "
        "Either read them or add them to UNREAD. A field written and never "
        "read wastes the record's own evidence, which is worse than a field "
        "nobody writes")


def test_the_backlog_does_not_keep_what_has_been_fixed():
    """THE HALF THAT STOPS THIS BECOMING A PLACE TO PUT THINGS. A register
    that only ever grows is a list of excuses; a field that gains a writer or
    a reader has to leave it, or the next reader of this file learns nothing
    from its length."""
    unwritten, unread = _measure()
    stale_w = sorted(set(UNWRITTEN) - unwritten)
    stale_r = sorted(set(UNREAD) - unread)
    assert not stale_w, (
        f"{stale_w} now have writers - remove them from UNWRITTEN")
    assert not stale_r, (
        f"{stale_r} now have readers - remove them from UNREAD")


def test_the_registers_name_real_fields():
    """A typo in either list silently exempts nothing and hides a real gap."""
    from vitai.schema import KEYS

    every = {f"{ds}.{k}" for ds, keys in KEYS.items() for k in keys}
    unknown = sorted((set(UNWRITTEN) | set(UNREAD)) - every)
    assert not unknown, f"{unknown} name no field in the schema"


# --- the fixture corollary --------------------------------------------------

def test_a_vocabulary_field_shows_more_than_one_of_its_values():
    """A fixture that only holds the populated case proves nothing about the
    empty one, and one that holds a single value proves nothing about the
    distinction.

    The demo stamped `coverage: full` on every row it wrote, so `partial`
    never appeared and the field's first consumer would have been tested
    against a constant - validating the schema rather than the behaviour.
    Corrected since; pinned here so it stays corrected, and stated in the
    general form for the vocabularies that follow.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    seen: dict[str, set] = {}
    for f in (glob.glob(str(root / "tests/fixtures/personas/*/data/daily.jsonl"))
              + [str(root / "examples/demo/data/daily.jsonl")]):
        for line in pathlib.Path(f).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key in ("coverage",):
                if row.get(key) is not None:
                    seen.setdefault(key, set()).add(row[key])
    assert len(seen.get("coverage", set())) > 1, (
        "every populated `coverage` row carries one value, so the states the "
        "field exists to distinguish are untested")
