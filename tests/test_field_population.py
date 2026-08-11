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
  - `daily.coverage` HAD no consumer, and #186 gave it one: a weekly verdict
    built over a day the record marks `partial` carries `provisional: true`,
    a column of its own beside the verdict rather than a value in `answers` -
    the row still scores, and says its inputs were not closed. The writing
    half of that issue is still open - one
    field on a row several sources write to, so whichever importer sets it
    wins uncontested - but reading it errs the safe way, since over-marking a
    figure as not-final is the direction the issue asks for.
  - `thresholds` and `meals` have NO PRODUCER. Nothing generates them; they
    wait for a surface that was never built.
  - `weight.kg_lo`/`kg_hi` had NO CONSUMER. The producer existed and worked,
    and #46 gave them one: they are the interval that decides whether a change
    in body composition is one the instrument could see.

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
    "daily.artifact",
    "daily.path",
    "inferences.depends_on",
    "inferences.note",
    # #280, and they sit beside the lineage fields they qualify: a dataset
    # with no derived row in any fixture has nothing to say about who
    # derived it either. Written where a derived row exists - `weight` by
    # hand and `daily` by software - so both halves of the distinction are
    # exercised somewhere.
    "meals.derived_by",
    "meals.derived_build",
    "measurements.derived_by",
    "measurements.derived_build",
    "sessions.derived_by",
    "sessions.derived_build",
    "sets.derived_by",
    "sets.derived_build",
    # A person has no build, so the one by-hand row leaves this null.
    "weight.derived_build",
    "meals.derived_from",
    "meals.derived_op",
    "meals.path",
    "measurements.artifact",
    "measurements.derived_from",
    "measurements.derived_op",
    "measurements.modelled",
    "measurements.origin_evidence",
    "measurements.path",
    "regimes.anchored_by",
    "sessions.derived_from",
    "sessions.derived_op",
    "sessions.location",
    "sessions.modelled",
    "sets.derived_from",
    "sets.derived_op",
    "sets.path",
    "sets.resistance_level",
    "weight.artifact",
    "weight.modelled",
)

UNREAD = (
    # WRITTEN AND NOT YET READ, which is the worse of the two gaps and is
    # recorded rather than hidden. `bea` logs a sleep interval on the days her
    # watch is on - a night worker whose sleep sits in the middle of the
    # calendar day, which is the case the corpus had no record of. Nothing in
    # `src/` reads either boundary yet; the reader is #203, anchoring the day
    # to the athlete's sleep rather than to midnight. This leaves the register
    # the day that lands.
    "daily.sleep_end",
    "daily.sleep_start",
    # WRITTEN AND NOT YET READ. `otto` photographs the club ergometer's
    # console, so every artifact row says when the shutter went - which is a
    # different instant from `recorded_at` (when the row was written) and from
    # the session's `start_time` (when the piece began). Nothing reads it yet.
    # It is the field that would let a consumer ask whether the evidence was
    # captured at the time or reconstructed afterwards, which is exactly the
    # question a photographed value invites.
    "artifacts.captured_at",
    # WRITTEN AND NOT YET READ, all seven from `maja`. She logs off packaging,
    # so her rows carry what the label states: fibre, sugar and sodium, per
    # day and per hundred grams. The engine reads energy, protein, fat and
    # carbohydrate and stops there. `sets.tempo` is the same shape one dataset
    # over - the record holds how long each rep took and nothing asks.
    #
    # These are the honest kind of gap: the record now HAS the evidence and
    # the engine does not use it, which is worse than not having it and is why
    # this register exists. They leave the day something reads them.
    "daily.fibre_g",
    "daily.sodium_mg",
    "daily.sugar_g",
    "meals.fibre_100g",
    "meals.sodium_mg_100g",
    "meals.sugar_100g",
    "sets.tempo",
    # NOT A GAP, and this is the one entry here that records a decision
    # rather than a backlog item (#205). The register measures "read" as the
    # key's name appearing in a consumer, and by that measure the precise tier
    # is unread by design: nothing in the engine computes on it, no rollup
    # renders it, and the read model has no column for it. It exists to be
    # RELEASED, deliberately, through `Vitai.precise()` - which takes the
    # dataset name rather than the field name and so cannot name it here.
    #
    # A field the engine's arithmetic wanted would be a field this
    # classification should not hold, so this staying on the list is the
    # correct steady state rather than something to fix later.
    "context.place_precise",
    "sessions.place_precise",
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
    # The declared scales from #246. Written by the engine and read by nothing
    # INSIDE it, which is what an interface field looks like before a consumer
    # exists: their whole purpose is that a CLIENT stops inventing a
    # denominator. vitai-lens is the one that will read them first.
    "daily.mood_scale",
    "daily.pain_scale",
    "sessions.rpe_scale",
    "sets.rpe_scale",
    "daily.alcohol",
    # #280. Interface fields, and the same shape as the declared scales above:
    # written by the record and read by nothing INSIDE the engine, because
    # their whole purpose is that a CLIENT can tell its own derivation from
    # another client's, and from its own two versions ago. The engine has no
    # question that needs them - it knows what IT computed.
    "daily.derived_by",
    "daily.derived_build",
    "weight.derived_by",
    # --- the plans dataset (#221), three fields and two different reasons ---
    #
    # `requires` and `setting` are BLOCKED, not deferred. Both are answered by
    # asking the state model whether something held on a day - did the
    # condition obtain, was the outdoor session rained off, was the room in
    # the roof 28 degrees - and that model is #220 and does not exist. The
    # engine holds them and refuses to guess. What it does do already is
    # refuse `did_not_activate` on a plan that names no condition, so the
    # value cannot become a kinder word for skipped.
    #
    # `serves` is deferred rather than blocked. It is what makes a plan's TIER
    # discriminable, and validation refuses a `programme` plan that names
    # nothing - but validation is explicitly not a consumer here. What would
    # read it is adherence per tier, and #221 is emphatic that any such figure
    # must state how many plans were unresolved or it repeats the defect that
    # let a mostly-unjudgeable record display near-perfect adherence. Half of
    # that here would be the flattening number rather than the honest one.
    "plans.serves",
    "plans.setting",
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
