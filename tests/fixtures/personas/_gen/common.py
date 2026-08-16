"""Shared helpers for the persona corpus generators.

Every persona builder in this package (`rachel.py`, and future ones) writes
plain Python dicts that already carry every key a dataset expects, then hands
them to the functions in this module to become JSONL text, a GPX track file,
or a TOML config. Nothing here talks to the network or the wall clock: a
persona's data must be exactly reproducible from its seed, every time, on
every machine.

The skeleton-plus-override pattern (`record`) mirrors the one used by
`examples/generate_demo.py`: start from a dict holding every key in the
dataset's schema, set to null, then apply the caller's overrides. That is
what guarantees a generator can never "forget" a key - the schema itself
enumerates what has to be there.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from vitai.schema import CURRENT_GENERATION, KEYS

# --- schema pin ---------------------------------------------------------------
#
# The schema is versioned twice, and the package version is neither. The
# contract version (vitai.db.CONTRACT_VERSION) versions the READ MODEL: the
# built SQLite shape that expectations are asserted against. The per-dataset
# generation (vitai.schema.CURRENT_GENERATION) versions the LINE SHAPE: which
# keys a row written at generation N owed. A fixture generator cares about
# both, because it writes lines and its ground truth is asserted against a
# built database.
#
# The package version is recorded below as provenance for a bug report and
# nothing else. It moves independently of both real versions, in both
# directions: it rises for a docs fix with no schema change, and it sits
# still while the schema moves underneath it. It must never be compared as a
# drift signal.
#
# A mismatch here is not a warning. A fixture exists to be asserted against,
# so a generator authored against a different shape is a broken fixture, and
# a log line that scrolls past in green CI verifies nothing. Generation stops.
VITAI_VERSION_AT_AUTHORING = "0.2.3"  # provenance only, never compared
# Re-pinned for #105, which added a nullable `device` to every dataset and so
# advanced every generation by one. REVIEWED rather than bumped: the builders
# None-fill from `KEYS[dataset]`, so `device` lands absent on every persona
# row - which is the correct reading for a corpus that predates multi-device
# support, and nothing here should assert a machine it never had. The contract
# is unchanged at 15; only the generations moved.
# Re-pinned for #148, which added a `policy` row to the read model's `meta`
# table. REVIEWED rather than bumped: no builder here reads `meta` or builds
# a read model at all - they write JSONL - and no dataset shape moved, so
# every generation below is unchanged. Confirmed by regenerating: the
# committed corpora came back byte-identical, which is the evidence that the
# contract move did not reach them.
# Re-pinned for #171 track 2, which added `protocol` to weight and
# measurements and the `protocols` and `regimes` datasets. REVIEWED rather
# than bumped: no builder here writes either new dataset or the new field, and
# the builders None-fill from `KEYS[dataset]`, so `protocol` lands absent on
# every persona row, and `_gen` moves with it. That is the correct reading:
# none of these athletes declared a procedure, and asserting one they never
# followed would be inventing evidence. The corpora DID change - nine weight
# and measurement files gained `"protocol": null` and a bumped `_gen` - which
# is the ordinary consequence of regenerating a corpus against a wider schema,
# and is reviewed here rather than waved through.
# Re-pinned for #170, which added `derived_from` and `derived_op` to weight,
# daily, sessions, measurements, sets and meals. REVIEWED rather than bumped,
# on the same reading as `protocol` above: no builder here emits a computed
# value, the builders None-fill from `KEYS[dataset]`, so both fields land
# absent on every persona row and `_gen` moves with them. Absent is the honest
# answer - every quantity these athletes record is observed rather than
# derived, and declaring a lineage none of them has would be inventing exactly
# the evidence the field exists to make checkable. The corpora DO change: six
# datasets gain two null columns and a bumped `_gen`.
# Re-pinned for phase 3, which added the `emissions` dataset. REVIEWED rather
# than bumped, and this one is a NEW DATASET rather than a widened line, so it
# is worth being explicit: no builder here writes an emission, and none should.
# An emission records that the ENGINE told this athlete something, which is an
# event produced by a consumer at delivery time, not a fact about the person.
# Inventing one would assert that a judgement was surfaced to someone it was
# never surfaced to. No persona ships an emissions file at all - these
# builders only write datasets they have content for, and an absent file is an
# empty dataset - and their existing lines are untouched, because a new
# dataset appends nothing to the datasets already in the wild.
# Re-pinned for #188 and #190, which added five macro totals plus two sleep
# instants to daily (two generations - unrelated facts) and three per-100 g
# figures to meals. REVIEWED rather than bumped, and the reading differs
# between the two halves, so both are stated rather than reusing the sentence
# above.
#
# MACROS: absent is honest and also uncomfortable. No builder writes fat,
# carbohydrate, fibre, sugar or sodium, so they land null - but this is not the
# same "none of these athletes did this" that `protocol` was. Nine personas
# already carry protein on ZERO of 4530 daily rows, so the corpus has no
# athlete who eats deliberately and tracks it, and the new columns EXTEND that
# gap rather than record one. Null-filling is still correct today: no shipped
# behaviour reads these fields, and a persona built from the schema would only
# confirm the schema. The fixture work belongs with the behaviour; until then a
# null column honestly says nobody logged it.
#
# SLEEP INSTANTS: absent is honest without qualification. Every persona records
# `sleep_h` as a duration because that is what their sources give; not one has
# a device or export that reports when the night began. Inventing a bedtime to
# fill the column would fabricate exactly the evidence a day anchor would later
# be built on.
#
# The corpora DO change: daily gains seven null columns, meals three, and
# `_gen` moves on both.

# Re-pinned for #202, which adds the `pending` refusal reason and `due`. Both
# live on VERDICT rows, which are computed rather than recorded, so no builder
# here writes either and no persona line changes. The pin moves because the
# read model did.
# Re-pinned for #207: `meta` gains a `built_on` row and an unqualified build
# takes its viewpoint from the record rather than the clock. Neither touches a
# data line - both are properties of the BUILD - so no persona line changes and
# nothing is reviewed here beyond the pin itself.
# Re-pinned for #200, which adds `polarity` and `target_hi` to goals. REVIEWED
# rather than bumped: no builder declares a polarity, absence reads as `floor`,
# and a floor is exactly what both existing policies already meant, so every
# persona goal scores precisely as it did. `_gen` moves on the goals lines and
# nothing else does.
#
# FIVE of their goals now raise the new polarity advisory - sofia's 1200 kcal
# cap, tom's two weight targets, nora's ramp cap and stefan's race time. That is
# the advisory doing its job rather than a fixture defect. Declaring a polarity
# on their behalf would be editing what those people said they wanted, which is
# an editorial decision about the personas and not a migration.
# Re-pinned for #235, which splits goal status into a declared lifecycle axis
# and a derived achievement one. REVIEWED rather than bumped: no builder
# DECLARES a lifecycle, so every persona goal keeps the `status` it was
# authored with and reads forward through the one canonicaliser. The goals
# lines gain a null `lifecycle_status` and a bumped `_gen`, which is the
# ordinary consequence of regenerating against a wider schema, and every
# counted value and milestone count across all nine came back identical.
# Re-pinned for #235, which splits goal `status` into `lifecycle_status` and a
# derived `achievement_status`. REVIEWED rather than bumped: no builder writes
# either new field, the builders None-fill from KEYS, and `status` stays legal
# forever under G25 - so every persona goal declares exactly what it declared
# and resolves through the one canonicaliser. The corpora DO change: goals
# lines gain a null `lifecycle_status` and a bumped `_gen`.
#
# Note this lands in the same session as #200's polarity bump, which took the
# generation from 4 to 5; this takes it to 6. Two independent widenings of one
# dataset, reviewed separately because they are separate claims about what a
# goal is.
# Re-pinned for #246, which adds a declared scale beside each subjective
# number. REVIEWED rather than bumped: no builder declares one, so every
# persona keeps its bare `rpe`, `mood` and `pain` - which is the honest state
# and the one the fixture set needs, because absent-means-unstated is the case
# a consumer has to handle and the demo now covers the declared one.
#
# Re-pinned for #247, which adds the `best_efforts` table. Nothing here
# changes: it is a DERIVED table computed from stored tracks, and no persona
# ships one, so every persona yields zero rows and no data line moves.
# Re-pinned again at MERGE time, to 27. Both #246 and #247 were authored
# against 26 and each re-pinned to it; #246 merged first and kept it, so the
# combined tree is 27. Neither change moves a persona data line - one adds
# scale columns no builder declares, the other a derived table no persona
# ships - and both re-pin notes above stand as the review that established it.
# Re-pinned for #208, which adds the `session_weeks` table. Also DERIVED, and
# computed from `sessions` rows the personas already ship - so unlike the two
# above it will produce rows for most of them. It still moves no data line:
# nothing here writes a session, reads a week or declares a field, and the
# only thing in a persona that changes is the contract stamp in its
# `persona.toml`. Verified by regenerating and diffing rather than asserted.
# Re-pinned for #261 step 2, which adds `statistic` to `verdicts`. A DERIVED
# column, computed from rows the personas already ship, so like the three
# above it moves no data line: nothing here writes a verdict or declares a
# statistic, and the only change in a persona is the contract stamp in its
# `persona.toml`. Verified by regenerating and diffing rather than asserted.
# Re-pinned for #273, which adds `observed` to `goal_progress`. A DERIVED
# column and the first one here that will actually MOVE a number rather than
# only appear: a persona holding a weight goal now scores it against the
# latest weigh-in where it previously scored nothing. That is a change to
# what the read model says, not to any data line - no builder writes a goal
# polarity or an observation - and the diff is checked rather than asserted.
# Re-pinned for #145, which adds `body_side` to `medical` at generation 6.
#
# UNLIKE the derived-column re-pins above, this one DOES move persona lines:
# 28 medical rows each gain an explicit `body_side: null` and a generation
# stamp, because the builders write every key. What does not move is any
# VALUE - checked by diffing rather than asserted, and the count of
# non-generation changes is zero.
#
# `null` is right for all 28. The key is optional, an episode written before
# it never owed one, and filling a side in for a persona nobody re-examined
# would be inventing a clinical fact to make a fixture look complete.
#
# #139 moves `events` the same way, for the same reason: a fixture gains an
# explicit `outcome: null`, which is the ordinary state of one - nobody has
# said - and never "did not happen".
# Re-pinned for #185/#189, which adds `answers` to `verdicts`. A DERIVED
# column on a derived table: no persona line changes, only the contract stamp.
#
# Re-pinned for #221, which adds the `plans` dataset and retires
# `sessions.planned`. Two moves in one, and both are additive to a persona:
# the new dataset is EMPTY for all ten (no builder writes a plan, and
# inventing one would be inventing a day's intention for a person nobody
# re-examined), and the retirement makes `planned` stop being expected rather
# than stop being legal - it is null on all persona session rows anyway, which
# is the finding that motivated the whole dataset.
#
# The retirement DOES restamp every session row: 2245 of them move from
# generation 11 to 12. Checked rather than asserted - no value changes, and no
# key is added or removed on any of them.
# Re-pinned for #280, which adds `derived_by` and `derived_build` to the six
# datasets carrying a lineage. Additive and required only on a
# `derived_external` row from this generation on - no persona writes one, so
# every persona line gains two explicit nulls and a generation stamp, and no
# value moves.
# Re-pinned for #325's `field_origins` (contract 42), and the review the gate
# demands is recorded rather than implied: every builder was checked for a
# write to a provenance row or a read of `field_sources`, and there is none -
# the nine mentions across four builders are all prose. The map is derived
# from `origin` on raw claims the builders already write, so no line shape
# moves, no generation stamps, and no persona value changes.
# Re-pinned for #330's `milestones_total` (contract 43), and the gate's review
# recorded rather than implied: no builder writes a `goal_progress` row or a
# milestone - the only mention across all ten is a comment. A DERIVED column
# computed from goals and events the personas already ship, so like the
# derived-column re-pins above it moves no data line, and the only change in a
# persona is the contract stamp in its `persona.toml`. Verified by
# regenerating and diffing rather than asserted.
# Re-pinned for #171's `capabilities` dataset (contract 44), and the review
# the gate demands is recorded rather than implied: no builder writes a
# capability row - the only mention across all ten is a sentence of prose in
# `yasmin.py` - so every persona gets an empty `capabilities.jsonl` and nothing
# else moves. A NEW DATASET rather than a new column, which is the first of
# those here; the shape is the same as the derived-column re-pins above,
# because a dataset no builder writes contributes no lines to diff.
# Re-pinned for #311's `instruments` dataset (contract 45), and this one is
# NOT the empty re-pin the two above were. `ines` registers her kit, because
# her record already contains the confound the register exists for: she weighs
# 65.80 kg at the gym on 2030-05-30, against 64.14 kg at home the same morning
# and 64.06 kg four days later, and nothing in the record said those numbers
# came off different scales. A dataset that ships exercised by nobody proves
# nothing about the populated case, which is what the two re-pins above left
# open. The other nine personas get an empty `instruments.jsonl`.
# Re-pinned for #33 item 2's `comparability` dataset (contract 46), and the
# review the gate demands is recorded rather than implied: no builder writes
# a comparability row - the only mention across all ten is this comment - so
# every persona gets an empty `comparability.jsonl` and nothing else moves.
# The populated case (`scale` vs `dexa` on `kg`) ships in `examples/demo`
# instead, which is the fixture #33's own acceptance criterion is checked
# against.
# Re-pinned for #370's contract 47. Reviewed and nothing here moves: the new
# `crossings` table is DERIVED (built from `weight` at build time, same as
# `milestones`), so no generator writes a line for it and it needs no entry
# in `AUTHORED_AGAINST_GENERATIONS`, which only tracks raw dataset LINE
# shapes. `height_cm` joining `MEASUREMENT_KINDS` widens the legal values of
# `measurements.kind`, an existing field - it adds no key, so `measurements`
# keeps generation 11 below. No persona builder emits `height_cm` and none is
# asked to; the review this pin demands is that fact, stated rather than
# implied.
# Re-pinned for #370's contract 48, the band-crossing third: `crossings.kind`
# gains `band`, and like `round_number`/`personal_first` before it that is a
# DERIVED-table vocabulary widening (built from `weight` and `measurements`
# at build time), so it needs no entry in `AUTHORED_AGAINST_GENERATIONS`
# either - no generator writes a `crossings` line, and `measurements` stays
# generation 11, because `height_cm` was already a legal `kind` value as of
# the previous pin and this PR adds no new KEY to that dataset.
#
# UNLIKE the previous pin, one builder DOES move here: `yasmin.py` gains a
# `data/measurements.jsonl` she did not ship before, one `height_cm` row at
# generation 11 (every key her file already knows how to write). That is a
# NEW FILE for one persona, not a new generation for the dataset - the same
# distinction #311's `instruments` re-pin above draws between a dataset
# nobody writes and one whose shape does not move. Measured before choosing
# her: of the personas with a height stated in `WORLD.md` and a real weight
# series, hers is the one whose canonical BMI (165 cm) actually crosses a
# `BAND_LEVELS` boundary - five times, both directions, matching her own
# "failed attempts" record - while `tom` (175 cm) and `rachel` (162 cm) stay
# above the topmost `BAND_LEVELS` edge at every weight they record and would
# have needed invented numbers to exercise this feature at all.
AUTHORED_AGAINST_CONTRACT = "49"  # vitai.db.CONTRACT_VERSION is a string
AUTHORED_AGAINST_GENERATIONS = {
    # #171: a new dataset, empty for every persona. Generation 3 rather than 1
    # because every dataset gets the blanket `recorded_at` and `device`
    # blocks; a key registered above the founding generation can only ever
    # exempt more lines, and there are none here to exempt.
    "capabilities": 3,
    # #311: a new dataset. Generation 3 for the same reason as `capabilities`
    # above - the blanket `recorded_at` and `device` blocks - and populated
    # for `ines` rather than empty everywhere.
    "instruments": 3,
    # #33 item 2: a new dataset, empty for every persona, generation 3 for
    # the same blanket-block reason as `capabilities` above.
    "comparability": 3,
    # #221: a new dataset, empty for every persona.
    "plans": 1,
    "achievements": 5,
    "artifacts": 4,
    "checks": 4,
    "context": 5,
    "daily": 14,
    "emissions": 1,
    "events": 4,
    "goals": 6,
    "inferences": 5,
    "journal": 4,
    "meals": 6,
    "measurements": 11,
    "medical": 6,
    "sessions": 16,
    "sets": 7,
    "protocols": 1,
    "regimes": 2,
    "thresholds": 3,
    "weight": 12,
}


def assert_schema_unmoved() -> str:
    """Stop generation if the installed engine's schema shape differs from
    the shape these generators were authored against, naming exactly which
    datasets moved. Returns the one-line pin statement for ordinary output
    when everything matches.

    There is no public accessor for either number, so this reaches into
    vitai.db.CONTRACT_VERSION and vitai.schema.CURRENT_GENERATION directly;
    that is private surface and a known parity hole (the CLI can print a
    contract, the API cannot hand you one)."""
    from vitai.db import CONTRACT_VERSION
    live_gens = dict(CURRENT_GENERATION)
    problems = []
    if CONTRACT_VERSION != AUTHORED_AGAINST_CONTRACT:
        problems.append(
            f"contract version moved {AUTHORED_AGAINST_CONTRACT} -> {CONTRACT_VERSION}")
    for name in sorted(set(AUTHORED_AGAINST_GENERATIONS) | set(live_gens)):
        pinned, live = AUTHORED_AGAINST_GENERATIONS.get(name), live_gens.get(name)
        if pinned != live:
            if pinned is None:
                problems.append(f"dataset added since authoring: {name} (gen {live})")
            elif live is None:
                problems.append(f"dataset removed since authoring: {name} (was gen {pinned})")
            else:
                problems.append(f"{name} generation moved {pinned} -> {live}")
    if problems:
        detail = "; ".join(problems)
        raise SystemExit(
            "persona generators were authored against a schema shape the "
            f"installed vitai no longer has: {detail}. Review every _gen/ "
            "builder against the change, regenerate, re-review the committed "
            "corpora, then update the pins in _gen/common.py. Refusing to "
            f"generate. (vitai package version at authoring was "
            f"{VITAI_VERSION_AT_AUTHORING}; recorded as provenance, not "
            "compared.)")
    return (f"schema pin holds: contract {AUTHORED_AGAINST_CONTRACT}, "
            f"{len(AUTHORED_AGAINST_GENERATIONS)} dataset generations unchanged")


# --- dates and clocks ---------------------------------------------------------


def daterange(start: date, end: date):
    """Every calendar day from `start` to `end`, inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def irish_offset(d: date) -> str:
    """UTC offset for Ireland on a given date, kept deliberately simple.

    Irish Summer Time runs from the last Sunday of March to the last Sunday
    of October; this approximates that window with fixed calendar dates
    (25 March to 25 October) rather than computing the exact Sunday, which is
    accurate enough for a synthetic record and never needs to be exact to the
    day. Winter (the rest of the year) is plain UTC, +00:00.
    """
    if date(d.year, 3, 25) <= d <= date(d.year, 10, 25):
        return "+01:00"
    return "+00:00"


class Stamper:
    """Produces a strictly increasing `recorded_at` for one dataset file.

    `vitai` requires `recorded_at` to carry an explicit UTC offset and to be
    strictly increasing across the whole file, with no exact repeats even
    across different dates (see the handbook, section 0). A separate
    `Stamper` instance per dataset file keeps each file's sequence
    independent, which is what the rule actually asks for.

    The model is simple and realistic: an evening logging session at
    `base_hour:00`, advancing a few seconds for every row logged that same
    day. The per-date counter is keyed by the date itself (a dict), not by
    "was the previous call the same date" - a generator commonly builds one
    kind of row (say, every Wednesday's aqua fit class) in one pass and
    another kind (a Tuesday walk) in a separate pass, so calls for one date
    are rarely consecutive in the order they happen to be made. Keying by
    date directly keeps every same-day stamp distinct regardless of what
    order the passes run in, while different dates never collide because the
    date itself dominates the instant comparison.
    """

    def __init__(self, base_hour: int = 21, step_seconds: int = 45,
                 offset=irish_offset):
        self._base_hour = base_hour
        self._step = step_seconds
        self._offset = offset
        self._counts: dict[date, int] = {}

    def stamp(self, d: date) -> str:
        count = self._counts.get(d, 0)
        self._counts[d] = count + 1
        total_seconds = count * self._step
        hh = self._base_hour + total_seconds // 3600
        mm = (total_seconds // 60) % 60
        ss = total_seconds % 60
        return f"{d.isoformat()}T{hh:02d}:{mm:02d}:{ss:02d}{self._offset(d)}"


def _instant(rec: dict) -> datetime:
    """The `recorded_at` of a row as a real instant, for a correct sort.

    Comparing ISO timestamps as text can misorder rows across a DST change (a
    `+01:00` stamp can sort either side of a `+00:00` one depending on the
    clock values), so every row here is parsed into an aware `datetime` and
    compared as an instant instead. Every row this generator produces carries
    a `recorded_at`, so there is no need for a "missing stamp" fallback path -
    unlike a real record, which may have unstamped legacy lines.
    """
    raw = rec.get("recorded_at")
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.min.replace(tzinfo=timezone.utc)


def sort_rows(rows: list[dict]) -> list[dict]:
    """Sort a dataset's rows the way `vitai` expects a real writer to: by
    date, then by the instant they were recorded, then by whichever identity
    field the dataset carries (source, or the identity key for a
    slug/key-keyed dataset). File order must follow `recorded_at` order,
    because the monotonicity check in the handbook reads file order, not
    date order.
    """
    def key(rec: dict):
        tail = rec.get("source") or rec.get("slug") or rec.get("key") or ""
        return (str(rec.get("date") or ""), _instant(rec), str(tail))

    return sorted(rows, key=key)


# --- record skeletons -----------------------------------------------------------


def record(dataset: str, /, **kw) -> dict:
    """A dataset line with every key from `KEYS[dataset]` present.

    Every value defaults to null; `_gen` defaults to the CURRENT_GENERATION
    for that dataset (queried live, per the handbook's own warning that these
    numbers drift and must never be hardcoded). The caller's keyword
    arguments then override whichever fields it actually knows, exactly the
    "skeleton plus override" builder pattern `examples/generate_demo.py`
    uses for its own `_goal`/`_event` helpers.

    The first parameter is positional-only, so a dataset whose own schema
    carries a field literally named `dataset` (goals does) can set it as an
    ordinary keyword: `record("goals", dataset="daily")`. Wave one of the
    persona build lost time to that collision three times over.
    """
    if dataset not in KEYS:
        raise KeyError(f"unknown dataset {dataset!r}; one of {sorted(KEYS)}")
    rec = {k: None for k in KEYS[dataset]}
    rec["_gen"] = CURRENT_GENERATION[dataset]
    rec.update(kw)
    return rec


# --- writers ---------------------------------------------------------------------


def jsonl_text(rows: list[dict]) -> str:
    """One `json.dumps` per row, newline-joined, with a trailing newline -
    the exact shape `examples/generate_demo.py` writes and `vitai` reads."""
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def persona_toml(slug: str, version: int, seed: int,
                 span: tuple[str, str]) -> str:
    """The persona's machine-readable identity, per docs/persona-doctrine.md.

    Three things drift and they are not one version: the schema shape the
    corpus was last regenerated under (pinned corpus-wide above, restated
    here so a test can assert on the file), the persona version (bumped in
    the persona's module only when the history could change an engine
    output), and the seed (reproducing bytes). The [schema] block is
    deliberately the shape a content repo would embed to pin the engine it
    was authored against; the known "no engine-version pin in the content
    repo" gap is this same problem one level up.
    """
    lines = [
        "# Emitted by generate.py; do not edit by hand. Bump PERSONA_VERSION",
        "# in _gen/" + slug + ".py only when the history could change an",
        "# engine output (docs/persona-doctrine.md).",
        "",
        "[persona]",
        f'slug = "{slug}"',
        f"version = {version}",
        f"seed = {seed}",
        f'span = ["{span[0]}", "{span[1]}"]',
        "",
        "[schema]",
        f'contract = "{AUTHORED_AGAINST_CONTRACT}"',
        "",
        "[schema.generations]",
    ]
    for name in sorted(AUTHORED_AGAINST_GENERATIONS):
        lines.append(f"{name} = {AUTHORED_AGAINST_GENERATIONS[name]}")
    return chr(10).join(lines) + chr(10)


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF-only newlines - the load-bearing part on
    Windows, where the default text-mode write would translate `\\n` to
    `\\r\\n` and corrupt the LF-pinned convention `vitai init` establishes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def stamp_seq_text(rel: str, text: str) -> str:
    """`seq` on every row of a dataset file, the way `append` stamps it (#239).

    ON THE SERIALISED FORM, because every builder returns
    `{"data/weight.jsonl": jsonl_text(sort_rows(rows))}` - text, not rows. A
    helper wired into `write_jsonl` would be dead code no builder calls, and
    the corpus would ship every row carrying `seq: null` at the generation that
    INTRODUCED seq - a shape the append path can never produce, with the drift
    gate passing because generator and fixtures were consistently wrong
    together.

    So it runs where the dataset name and the rows are both available and every
    write and every drift check passes through: `generate.py`'s `_files_for`.
    """
    from vitai.jsonl import line_key
    from vitai.schema import SEQUENCED

    if not (rel.startswith("data/") and rel.endswith(".jsonl")):
        return text
    dataset = rel[len("data/"):-len(".jsonl")]
    if dataset not in SEQUENCED:
        return text
    counts: dict[str, int] = {}
    out = []
    for line in text.splitlines():
        # A comment line is legal in this format and `read_lines` skips it, so
        # parsing every line unconditionally would kill the generator on the
        # first one anybody writes.
        if not line.strip() or line.lstrip().startswith("//"):
            out.append(line)
            continue
        row = json.loads(line)
        key = line_key(dataset, row)
        row["seq"] = counts.get(key, 0)
        counts[key] = row["seq"] + 1
        out.append(json.dumps(row))
    return "\n".join(out) + "\n"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    write_text(path, jsonl_text(sort_rows(rows)))


def write_expectations(path: Path, rows: list[dict]) -> None:
    """`expectations.jsonl` is ground truth emitted by the generator, not a
    vitai dataset - it is never read by the engine and carries no schema
    key list, so it is sorted by `id` alone rather than by date/recorded_at."""
    ordered = sorted(rows, key=lambda r: str(r.get("id") or ""))
    write_text(path, jsonl_text(ordered))


# --- GPX tracks -------------------------------------------------------------------


def gpx_text(day: str, start_hhmm: str, duration_s: int,
             base_lat: float = 51.90, base_lon: float = -8.50,
             name: str = "route") -> str:
    """A short synthetic GPX track, as a string: a loop that drifts and
    returns near its start, with a point every 10 seconds - the same shape
    and cadence as `examples/generate_demo.py`'s own demo track, generated
    deterministically (no RNG) so a persona's tracks never drift between
    generator runs.

    The coordinates are generic values near the Cork, Ireland region and are
    entirely fictional - they exist only so a stored track has somewhere
    plausible to have been recorded, never to name a real place precisely.
    """
    n = max(6, duration_s // 10)
    hh, mm = (int(x) for x in start_hhmm.split(":"))
    start_minutes = hh * 60 + mm
    pts = []
    for i in range(n):
        leg = i if i < n // 2 else n - 1 - i
        lat = base_lat + leg * 0.00006
        lon = base_lon + 0.0012 * math.sin(leg * math.pi / max(1, n // 2))
        ele = round(6.0 + leg * 0.05, 1)
        t_minutes = start_minutes + (i * 10) // 60
        t_seconds = (i * 10) % 60
        t = f"{day}T{(t_minutes // 60) % 24:02d}:{t_minutes % 60:02d}:{t_seconds:02d}Z"
        pts.append((lat, lon, ele, t))
    body = "\n".join(
        f'   <trkpt lat="{lat:.5f}" lon="{lon:.5f}"><ele>{ele}</ele>'
        f"<time>{t}</time></trkpt>" for lat, lon, ele, t in pts)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="vitai-persona-generator" '
            'xmlns="http://www.topografix.com/GPX/1/1">\n'
            f" <trk><name>{name}</name><trkseg>\n"
            f"{body}\n"
            " </trkseg></trk>\n</gpx>\n")
