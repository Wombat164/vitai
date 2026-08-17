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
own fixtures: the demo and the nine personas.

"READ" USED TO MEAN "THE NAME APPEARS SOMEWHERE" (#412), which is not the same
claim and is the weaker one by a long way. The check read every module under
`src/vitai/` except `schema.py` and `db.py` as TEXT and asked whether the key's
name occurred in it as a quoted string. A docstring satisfied that. So did an
error message, an `argparse` flag, an MCP tool's JSON-schema property, a prompt
template, and a validation allowlist - though three entries below say in as many
words that validation is not a consumer. Worst of all, THE MODULE THAT WRITES
THE FIELD satisfied it: a producer names the key in order to store it, and the
name is then present. A field could be added, declared, written by the engine
and consumed by nobody, and this register would have been green about it, which
is precisely the class it exists to catch. Found in #411 and fixed here; every
field the register had ever passed was only as good as that heuristic, so the
number that matters is how many stopped passing when it was tightened. FOURTEEN
did, and what they were is recorded below rather than summarised: eleven were
one field, `seq`, on eleven datasets, and it is machinery (see `MACHINERY`); the
other three are real, and they are the last three entries in `UNREAD`.

WHAT COUNTS AS READING, NOW. A read is a LOAD: the key's name used to fetch a
value out of a mapping. Three forms count, and they are all the ways this
codebase actually does it.

  - Directly - `row["kg"]`, `row.get("kg")`, `row.pop("kg")`.
  - Through a NAME TABLE - a list, tuple, set or dict of field names that is
    iterated or membership-tested into such a lookup. `meals._PER_100` and
    `modifiers.MACHINE_SCOPED` are real examples; a table that is only ever
    compared against, like `api.EMISSION_FIELDS`, is validation and does not
    count.
  - Through an ARGUMENT - a name table or a name passed to a function that uses
    that parameter as a lookup key. `resolution.JUSTIFICATION_LINK` reaches
    `inferences.depends_on` this way and no other, so leaving this form out
    would have made a real consumer invisible.

Anything else is not a read. Storing under the name is not. Listing it in the
schema roster is not. A docstring, a message, a flag name or a prompt is not.

WHAT COUNTS AS THE WRITER. A read is a read from somewhere that is not the
writer, so the writer has to be named, and naming it as two filenames is what
let this slip in the first place. It is defined here by ROLE, derived from what
a module DOES, so that splitting or renaming a file cannot loosen the gate in
silence:

  - THE DECLARING module is the one that defines `KEYS`. It declares every key
    and consumes none. Found by the assignment, not by being called `schema.py`.
  - THE PROJECTING module is the one that copies the record into the read model.
    It enumerates every column and asks about none, as `kg_lo` demonstrated by
    sitting in the read model with nothing reading it. Found by its `sqlite3`
    import, not by being called `db.py`.
  - A PRODUCING module is one that reaches the record's write door - `append`
    or `append_many`, which is the only way a row is ever added - AND names the
    field in a store position. It is a writer of that field and of no other.

A producing module's own load of its own field is not counted as a read. It may
be a genuine consumer and it may be the producer reading back what it just
wrote; the point is that this register cannot tell those apart, and a gate that
guesses in the writer's favour is the gate that just failed. So the answer for
such a field is not "assume it is read" but "classify it": machinery, or an
entry below with the reason.

THE LIMIT, STATED. Module granularity is coarse and the write door is narrow. A
field carried between rows inside a module that never appends - `set_by`, copied
forward at `policy.py` into a superseding row - still counts as read here, and
transport is not consumption. That is the next tightening, not this one.
"""

from __future__ import annotations

import ast
import glob
import json
import pathlib

# Machine-stamped or structural: present on nearly every row by construction,
# and not what this is about.
#
# `seq` joined this set in #412 rather than joining the register (eleven
# datasets carry it, and all eleven stopped passing when the read gate was
# tightened). It belongs here for the same reason `device` does, and the two sit
# in the same guard: `jsonl` REFUSES a caller-supplied `seq` - "seq is
# machine-set and must not be supplied" - and stamps it during the append. It is
# the row's position among the rows sharing its key, assigned by the writer and
# read back by `jsonl.position_of` so a correction can name a row rather than a
# day. Written and read by one module is what a structural field looks like, and
# it is a different fact from "the record holds evidence the engine discards" -
# recording it eleven times as the second would have been eleven false entries.
MACHINERY = {"recorded_at", "device", "supersedes", "date", "_gen", "seq"}

# THE BACKLOG. Not an approval - see the module docstring.
UNWRITTEN = (
    # `comparability.bias` and `comparability.spread` LEFT THIS REGISTER
    # (#402). The entry here was right for as long as it stood: the demo's one
    # row is `comparable`, the status that leaves both null, and writing an
    # `offset` row to populate them would have asserted a cross-instrument
    # difference no fixture had measured - the exact fabrication #33 refuses.
    #
    # `vera` has the measurement. A hundred-odd runs recorded by two GPS
    # sources, paired by date, with a median difference and a range that were
    # observed rather than chosen. The register worked exactly as intended:
    # it held the fields empty until a record could fill them honestly.

    # #402, on the two datasets whose absence case belongs to another change.
    # `weight` carries the mechanism: `bea` records a shift day she chose not
    # to weigh on, which is the state this field exists for and the one her
    # own protocol already described in prose.
    #
    # The `daily` and `sessions` cases are the OUTAGE shape - a watch that
    # stopped reporting takes steps, distance and heart rate together - and
    # contract 49's `false_zero` and #405's `outage` question kind are the
    # change that owns detecting it. Writing an outage-shaped day here to
    # populate this register would be inventing the fixture that work needs,
    # ahead of the work, in a corpus somebody else is editing.
    "daily.absent_fields",
    "daily.absent_reason",
    "sessions.absent_fields",
    "sessions.absent_reason",
    # #413, and a DECISION rather than a backlog item. `vera` writes the
    # corpus's only census - 101 paired days over `sessions.distance_km`, none
    # dropped - and there is nothing true to put in its `note`. Her window has
    # no ambiguity to explain, no gap to account for and no bound the two
    # dates do not already give, so a line here would be prose written to
    # clear a register.
    #
    # That is the same refusal this dataset is built on, arriving one level
    # up: the demo cannot write a census at all because its overlap is two
    # days and three is the floor, and inventing a third paired day to satisfy
    # `test_fixture_coverage` would be the fabrication in the data rather than
    # in the narrative. Both absences are honest and both are recorded.
    #
    # It leaves this list the day a record holds a window that needs
    # explaining - a stretch where one instrument was in a drawer, an overlap
    # that ended for a reason the dates cannot show - which is exactly the
    # case `note` exists for.
    "overlaps.note",
    "daily.artifact",
    "daily.path",
    # `inferences.depends_on` and `inferences.note` LEFT THIS REGISTER (#386).
    # The demo's third inference rests on exactly two claims and names both.
    # The other two could not carry the link honestly - one rests on two weeks
    # of rows and the other on the record's full range, so any list short
    # enough to read would be a partial justification presented as the whole
    # one, which is worse than the null it replaced.
    #
    # WRITING IT FOUND A DEFECT, which is this register's argument in one
    # line: `depends_on` had been a list in the schema since generation 2 with
    # no row ever carrying one, so `db.LIST_COLS` had never been told, and a
    # consumer reading the projection would have taken the JSON array as a
    # bare string and dropped the link without failing. A field nothing writes
    # is not merely uncovered, it is a place a defect sits undisturbed.
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
    # recorded rather than hidden. TWO personas write the sleep interval and
    # neither reason replaces the other: `marcus` logs it every night, and
    # `bea` logs one on the days her watch is on - a night worker whose sleep
    # sits in the middle of the calendar day, and who has none at all on the
    # days she is working.
    #
    # `sleep_end` LEFT THIS REGISTER when #212's coarse tier landed: it is the
    # anchor `Vitai.phases` places a timed row against, so the record's own
    # account of when the athlete woke is what decides whose morning a weigh-in
    # happened in. That is the register working - an entry that gains a reader
    # has to go.
    #
    # `sleep_start` still has none. When the athlete went to BED is not what
    # the day is anchored on, and its reader is #203.
    "daily.sleep_start",
    # WRITTEN AND NOT YET READ, and this one is a DECISION rather than a
    # backlog item (#404). Two personas declare what their weigh-in protocol
    # fixes, and nothing in the engine reads it.
    #
    # That is deliberate and the alternative was worse. The consumer is a band
    # whose width reflects the conditions a protocol leaves free, which is
    # #402 - and #402's own rule says a band comes from a measured overlap, a
    # per-reading `u_obs` or an athlete-stated range and from nowhere else. No
    # record holds the same-day pairs differing in ONE declared condition that
    # would earn it, so a reader written now could only be reading the COUNT of
    # uncontrolled conditions and calling it a magnitude, which is the exact
    # arithmetic #404 says must not happen.
    #
    # So the register is doing its job by naming this, and the honest answer is
    # that the evidence half has to exist before the reading half can. It
    # leaves this list the day a band is earned rather than assumed.
    "protocols.controls",
    # WRITTEN AND NOT YET READ, and a decision rather than a backlog item
    # (#402). `bea` records a shift day she chose not to weigh on, and nothing
    # in the engine reads the reason.
    #
    # That is the shape this field was landed in. Its consumers are on the
    # capture side - a client letting somebody tap a gap and explain it - and
    # in the coverage work that would count explained holes separately from
    # silent ones. Neither exists here, and a reader written now would have to
    # decide what an unexplained hole is WORTH, which is #402's band question
    # and is blocked on evidence no record holds.
    #
    # The rule the field ships with is the reason it is safe to leave unread:
    # a reason explains a hole and never fills one, so nothing downstream that
    # ignores it reads a number that is not there.
    "weight.absent_fields",
    "weight.absent_reason",
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
    # --- THE THREE THE TIGHTENED GATE FOUND (#412) ---
    #
    # None of these is new to the repo. All three were passing on a name
    # appearing in a place that consumes nothing, and each one is here with the
    # place named, so the next reader can check the claim rather than trust it.
    #
    # `inferences.evidence` - the dates and datasets an inference stands on.
    # Its only occurrence outside the schema is inside the PROMPT TEMPLATE in
    # `inference.py`, which is a string telling a model what shape to answer in;
    # the engine never reads the field back off the row. Its sibling
    # `depends_on` does have a consumer - the retraction cascade in
    # `resolution.py` follows it, which is why that one is not here - and the
    # difference between the two is the whole point: `depends_on` names claims
    # the cascade can walk, `evidence` is prose about where a claim came from
    # and nothing can walk it. It leaves this list when something does.
    "inferences.evidence",
    # `emissions.policy_asof` - which policy was in force when an assertion was
    # delivered. Named once outside the schema, in `EMISSION_FIELDS`, which is
    # the allowlist of what a CALLER may state on an emission row. That is a
    # write-side control and the register is explicit that validation is not a
    # consumer; nothing reads the value afterwards to say a verdict was made
    # under a policy since replaced, which is the question the field exists for.
    "emissions.policy_asof",
    # `plans.tier` - how binding a plan was. Deferred for the SAME reason
    # `plans.serves` above is, and the two are one gap seen twice: what would
    # read either is adherence per tier, and #221 refuses that figure until it
    # can state how many plans were unresolved. `serves` makes the tier
    # discriminable and `tier` is the thing it discriminates, so neither can
    # leave this list before the other.
    "plans.tier",
)


# --- what counts as reading a field, and who counts as its writer (#412) -----

# The record's write door. A row reaches the file through `jsonl.append` or
# `jsonl.append_many` and through nothing else, and `Vitai.append` /
# `Vitai.append_many` wrap them. Two arguments or more, because `list.append`
# takes exactly one and would otherwise make every module in the repo a writer.
DOOR = {"append", "append_many"}

# Expressions a name table can hide behind before it reaches a lookup. A name
# bound to anything else - a call, a comprehension - is not followed, because
# following it would be guessing.
_LITERALISH = (ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict,
               ast.Name, ast.BinOp, ast.Subscript)


class _Module:
    """One engine module, read for what it does with field names.

    Everything this class decides is decided from syntax. That is a limit and
    it is the right one for a register: a static answer is the same on every
    machine and every run, where a runtime answer would depend on which code
    paths the harness happened to exercise, and a field read only by a command
    nobody called would look unread.
    """

    def __init__(self, name: str, tree: ast.Module):
        self.name = name
        self.loaded: set[str] = set()      # fetched out of a mapping by name
        self.stored: set[str] = set()      # put into a mapping under that name
        self.declares_keys = False         # defines the schema roster
        self.projects = False              # copies the record into the read model
        self.reaches_door = False          # can append a row to the record
        self._tables: dict[str, list] = {}   # name -> expressions bound to it
        self._keyvars: set[str] = set()      # names used AS a lookup key
        self._keyparams: dict[str, set[int]] = {}   # func -> param positions
        self._read(tree)

    # -- following a name to the strings it can stand for --------------------
    def _names_in(self, node, depth: int = 0) -> list[str]:
        if depth > 4:
            return []
        if isinstance(node, ast.Constant):
            return [node.value] if isinstance(node.value, str) else []
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [n for e in node.elts for n in self._names_in(e, depth + 1)]
        if isinstance(node, ast.Dict):
            out = []
            for k, v in zip(node.keys, node.values):
                if k is not None:
                    out += self._names_in(k, depth + 1)
                out += self._names_in(v, depth + 1)
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return (self._names_in(node.left, depth + 1)
                    + self._names_in(node.right, depth + 1))
        if isinstance(node, ast.Name):
            return [n for v in self._tables.get(node.id, ())
                    for n in self._names_in(v, depth + 1)]
        if isinstance(node, ast.Subscript):
            # one entry out of a name table is still a name from that table
            return self._names_in(node.value, depth + 1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("items", "values", "keys"):
            return self._names_in(node.func.value, depth + 1)
        return []

    def _read(self, tree: ast.Module) -> None:
        bound: dict[str, list] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                for t in targets:
                    if isinstance(t, ast.Name) and node.value is not None:
                        bound.setdefault(t.id, []).append(node.value)
                        if t.id == "KEYS":
                            self.declares_keys = True
            elif isinstance(node, ast.Import):
                self.projects |= any(a.name.split(".")[0] == "sqlite3"
                                     for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.projects |= (node.module or "").split(".")[0] == "sqlite3"
        self._tables = {k: v for k, v in bound.items()
                        if all(isinstance(x, _LITERALISH) for x in v)}

        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                key, store = node.slice, isinstance(node.ctx, (ast.Store, ast.Del))
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    (self.stored if store else self.loaded).add(key.value)
                elif isinstance(key, ast.Name) and not store:
                    self._keyvars.add(key.id)
            elif isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        self.stored.add(k.value)
            elif isinstance(node, ast.Call):
                fn = node.func
                called = (fn.attr if isinstance(fn, ast.Attribute)
                          else fn.id if isinstance(fn, ast.Name) else None)
                if called in DOOR and len(node.args) + len(node.keywords) >= 2:
                    self.reaches_door = True
                if isinstance(fn, ast.Attribute) and node.args:
                    arg = node.args[0]
                    literal = isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    if fn.attr in ("get", "pop"):
                        if literal:
                            self.loaded.add(arg.value)
                        elif isinstance(arg, ast.Name):
                            self._keyvars.add(arg.id)
                        else:
                            self.loaded.update(self._names_in(arg))
                    elif fn.attr == "setdefault" and literal:
                        self.stored.add(arg.value)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args.posonlyargs + node.args.args
                positions = {i for i, a in enumerate(args) if a.arg in self._keyvars}
                if positions:
                    self._keyparams.setdefault(node.name, set()).update(positions)

        for node in ast.walk(tree):
            # a table iterated with its member used as a key
            if isinstance(node, (ast.For, ast.comprehension)):
                targets = [t.id for t in ast.walk(node.target)
                           if isinstance(t, ast.Name)]
                if any(t in self._keyvars for t in targets):
                    self.loaded.update(self._names_in(node.iter))
            # a table a key is tested against before being used as one
            elif isinstance(node, ast.Compare):
                for op, right in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) \
                            and isinstance(node.left, ast.Name) \
                            and node.left.id in self._keyvars:
                        self.loaded.update(self._names_in(right))
            # a name handed to a function that uses that parameter as a key
            elif isinstance(node, ast.Call):
                fn = node.func
                called = (fn.attr if isinstance(fn, ast.Attribute)
                          else fn.id if isinstance(fn, ast.Name) else None)
                for i in self._keyparams.get(called, ()):
                    if i < len(node.args):
                        self.loaded.update(self._names_in(node.args[i]))

    def reads(self, key: str) -> bool:
        """Does this module CONSUME `key`, as opposed to declaring, projecting
        or writing it? A role module never does; a producer of this field is
        not credited for loading back what it wrote."""
        if self.declares_keys or self.projects:
            return False
        if self.reaches_door and key in self.stored:
            return False
        return key in self.loaded


def _engine(root: pathlib.Path) -> list[_Module]:
    """Every module of the engine. `rglob`, not `glob`: a consumer moved into a
    subpackage would otherwise be invisible and its field would read as unread,
    which is a red build for a fixed problem."""
    return [_Module(p.name, ast.parse(p.read_text(encoding="utf-8")))
            for p in sorted((root / "src" / "vitai").rglob("*.py"))]


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

    engine = _engine(root)

    unwritten, unread = set(), set()
    for dataset, keys in KEYS.items():
        for key in keys:
            if key in MACHINERY:
                continue
            name = f"{dataset}.{key}"
            if (dataset, key) not in written:
                unwritten.add(name)
            elif not any(m.reads(key) for m in engine):
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


# --- the control on the gate itself (#412) ----------------------------------
#
# The register is only as good as what it counts as reading, and the previous
# answer was wrong for two years without a test going red - because there was
# no test of the measurement, only tests USING it. These are that test, and
# they are written against sources that do not exist in this repo, so a field
# with the shape that used to slip through is refused before anybody writes it.


def _synthetic(source: str) -> _Module:
    return _Module("synthetic.py", ast.parse(source))


def test_the_module_that_writes_a_field_does_not_thereby_read_it():
    """THE DEFECT, PINNED. A producer names a key in order to store it, and
    that name used to be the whole evidence that something read it."""
    writer = _synthetic("""
def record(vit, low, high):
    row = {"difference_lo": low, "difference_hi": high}
    vit.append("comparability", row)
""")
    assert writer.reaches_door
    assert not writer.reads("difference_lo")
    assert not writer.reads("difference_hi")


def test_a_writer_reading_back_its_own_field_is_still_not_a_read():
    """The near miss: the producer loads the value it just wrote. It may be a
    consumer and it may be transport, and a register that cannot tell them
    apart must not guess in the writer's favour."""
    loop = _synthetic("""
def record(vit, row):
    row["seq"] = 0
    vit.append("weight", row)
    return row.get("seq")
""")
    assert not loop.reads("seq")


def test_a_reader_that_never_writes_is_a_read():
    """The other half, or the tightening would just be a broken gate."""
    for source in ('def show(row):\n    return row["kg_lo"]\n',
                   'def show(row):\n    return row.get("kg_lo")\n'):
        assert _synthetic(source).reads("kg_lo")


def test_naming_a_field_in_prose_is_not_a_read():
    """A docstring, a message, a flag and a tool schema all named the field and
    all consumed nothing."""
    prose = _synthetic('''
"""The weekly verdict, which does not use `sleep_start` at all."""

def cli(parser):
    parser.add_argument("--sleep-start", dest="sleep_start")
    raise ValueError("sleep_start is not settable here")

TOOL = {"properties": {"sleep_start": {"type": "string"}}}
''')
    assert not prose.reads("sleep_start")


def test_a_validation_allowlist_is_not_a_read():
    """Stated three times in the register above and counted as a read anyway."""
    guard = _synthetic("""
EMISSION_FIELDS = frozenset({"statement", "policy_asof"})

def check(row):
    for key in row:
        if key not in EMISSION_FIELDS:
            raise ValueError(key)
""")
    assert not guard.reads("policy_asof")


def test_a_name_table_that_reaches_a_lookup_is_a_read():
    """All three forms the engine actually uses. Leaving any of them out would
    have hidden a real consumer and produced a false entry in the register -
    which is the same defect as the one being fixed, pointing the other way."""
    iterated = _synthetic("""
MACROS = ("protein_g", "fat_g")

def total(row):
    return sum(row.get(k) or 0 for k in MACROS)
""")
    assert iterated.reads("fat_g")

    tested = _synthetic("""
DAILY_METRICS = {"active_min", "steps"}

def pick(row, metric):
    if metric in DAILY_METRICS:
        return row.get(metric)
""")
    assert tested.reads("active_min")

    passed = _synthetic("""
LINK = {"inferences": "depends_on"}

def _deps(rec, field):
    return rec.get(field) or []

def cascade(rec):
    return _deps(rec, LINK["inferences"])
""")
    assert passed.reads("depends_on")


def test_the_two_role_modules_are_found_by_what_they_do():
    """Named as roles rather than as filenames, because two filenames is how
    this slipped. A module is the declaring one because it defines `KEYS` and
    the projecting one because it talks to SQLite - so splitting or renaming
    either cannot quietly hand the gate a new consumer."""
    declaring = _synthetic('KEYS = {"weight": ["kg"]}\n\ndef check(row):\n'
                           '    return row["kg"]\n')
    assert declaring.declares_keys and not declaring.reads("kg")

    projecting = _synthetic('import sqlite3\n\ndef project(row):\n'
                            '    return row["kg"]\n')
    assert projecting.projects and not projecting.reads("kg")

    root = pathlib.Path(__file__).resolve().parents[1]
    engine = _engine(root)
    assert sum(m.declares_keys for m in engine) == 1, (
        "the roster is declared in more than one module, or in none - the gate "
        "exempts whichever module declares it and cannot exempt a role that "
        "moved")
    assert sum(m.projects for m in engine) == 1, (
        "the read model is built somewhere other than where this expects, so "
        "the projection is either counted as a consumer of all 100+ columns "
        "or not exempted at all")
    assert sum(m.reaches_door for m in engine) >= 1, (
        "no module reaches `append`, so every writer would be credited with "
        "reading what it writes and this gate would be back where it started")


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
