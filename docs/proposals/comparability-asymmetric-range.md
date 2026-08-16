# Can a `comparability` row carry an asymmetric range?

**Status: DECIDED for the schema half, OPEN for the band half.** The schema
half is implemented in the change that carries this file (contract 52). The
band half is named here and left to the operator, with the reasoning written
down so it can be argued with rather than rediscovered.

This is the question #410 left behind, in its own words:

> The asymmetry does not fit in the row, and the engine says so. `bias` and
> `spread` are each a single number, so a range running further one way than
> the other cannot be written down. [...] **#402 has to decide whether
> `comparability` gains a field before a band can rest on this.**

## The question is two questions, and they have different answers

Read literally, that sentence bundles a schema question with a rendering
question, and the reason this took a document rather than a commit message is
that they come apart:

1. **Can the row hold the asymmetry?** It cannot today, and it should be able
   to. **Yes, and implemented.**
2. **Does holding it let a band rest on it?** **No, and adding the fields does
   not change that by one step.** That remains blocked on a decision this
   change deliberately does not take.

Answering only the first and calling the issue closed would be the failure the
issue exists to prevent. So the fields land, and the refusal lands with them.

## The evidence, restated from the record rather than from prose

`vera` is the first record anywhere with a measured cross-instrument overlap.
Phone against watch, `sessions.distance_km`, 101 paired days:

```
$ vitai calibrate --root tests/fixtures/personas/vera \
      --dataset sessions --field distance_km --origin-a phone --origin-b watch
phone vs watch, distance_km: 101 paired day(s)
    status:  offset
    bias:    0 (median difference)
    spread:  1.26 (full observed width, NOT a plus-or-minus)
    range:   -0.03 to 1.23
```

The differences run from -0.03 to +1.23 about a median of 0.00. That is not
noise with a shape; it is the finding. The phone rides in a chest pocket and
loses fix under the forest canopy, so it under-reads by up to a kilometre and
over-reads by thirty metres at most. One long tail, no matching tail.

**What the record could hold, before this change:**

```json
{"field": "distance_km", "origin_a": "phone", "origin_b": "watch",
 "status": "offset", "bias": 0.0, "spread": 1.26, "basis": "overlap",
 "note": "the road runs agree to within tens of metres; the forest loop is
          where they part, and it parts one way only"}
```

**The asymmetry survived only in the `note`.** That is the whole defect in one
line. The engine measured a number, the athlete wrote the row, and the only
carrier the schema offered for the shape of the disagreement was a sentence in
English. Every other consumer - the SQLite projection, the API, a third-party
reader, the client - sees `bias: 0.0, spread: 1.26` and nothing else.

And `bias: 0.0` with `spread: 1.26` is not merely incomplete, it is
*invitingly* wrong. The single most natural thing to do with a centre and a
width is to halve the width, which yields -0.63 to +0.63. Counted against the
101 differences that produced it, that band is wrong in both directions at
once:

- **Too wide on the short side.** It claims disagreement down to -0.63 km. The
  deepest low reading in 101 runs is -0.03 km, and **no observation at all**
  falls below -0.63. Six hundred metres of low-side disagreement that never
  happened.
- **Too narrow on the long side.** It stops at +0.63 km. **Twenty-one of the
  101 runs** are above it, out to +1.23 km - and those twenty-one are the
  finding, because they are the canopy runs.

The low tail is 0.03 km deep and the high tail is 1.23 km deep, a ratio of
forty to one, and the row records neither. Both the API and the CLI say not to
halve the spread. Neither warning is in the data.

## What has to hold, and how each option is scored against it

Taken from the issue, from #171, from contract 49, and from the client:

| # | constraint | source |
|---|---|---|
| C1 | A band must be EARNED. Where the width is unknown the correct rendering is NO BAND, not a vague one | loadline I4a |
| C2 | State how a figure was obtained, or call it a bound rather than an uncertainty | GUM reporting minimum |
| C3 | Do not invent a coverage factor. 101 days of trail running support no distributional assumption | #402 |
| C4 | No in-band sentinel. Smuggling a value through a type is the disease contract 49 cured | openEHR `accuracy = -1`, rejected |
| C5 | `basis` stays locked to `overlap`; silence resolves to `not_comparable`; `offset` records a measured difference without licensing a derivation across it | #33, #171, `policy.comparability` |
| C6 | A field specified and never written, or written and never read, is a register entry that has to be argued for | `test_field_population.py` (#204, #386) |

---

## Option 1 - the row gains the observed tails. RECOMMENDED, IMPLEMENTED

Two optional numeric columns, `difference_lo` and `difference_hi`, holding the
lowest and highest paired difference actually observed over the overlap, on the
same signed convention `bias` already uses (later-sorted origin minus
earlier-sorted).

```json
{"status": "offset", "bias": 0.0, "spread": 1.26,
 "difference_lo": -0.03, "difference_hi": 1.23, "basis": "overlap"}
```

**What a client can honestly draw from it.** A statement, and a comparison
view - never a band on a value:

- *In words:* "over 101 paired runs the phone and the watch differed by between
  -0.03 and +1.23 km, with a median difference of 0.00 km." Every number in
  that sentence was observed.
- *As geometry, in an instrument-comparison surface:* the observed range of the
  DIFFERENCE, drawn asymmetrically about the median, labelled as an observed
  range over a named overlap with its pair count. This is a picture of two
  instruments, not of a measurement.
- **Not** a band around any `distance_km` value. Not before this change and not
  after it. See "What this does not buy" below.

**What it costs.**

- A contract bump, 51 to 52, on a dataset two pinned clients consume. Additive
  and optional: every existing row keeps validating, and a client that ignores
  the columns behaves exactly as it does today.
- Two more columns on a row that may be rare. Real, and the answer to it is
  that the corpus already has the case: `vera` fills them the day they exist,
  so this is not schema written ahead of a record.
- A written-and-not-yet-read register entry (C6), because nothing in the engine
  reads them. Argued below rather than waved through.
- Redundancy: `spread` equals `difference_hi - difference_lo`. Two numbers
  stating one fact can drift. Answered by making the identity a validation rule
  rather than a convention - see "the rules the fields ship with".

**What it forecloses.** Very little, and that is the strongest argument for it.
The columns are observations under the `basis` and `overlap_ref` that already
qualify `spread`. They assert no distribution, no coverage factor and no
licence. If option 3's separate `overlaps` dataset is ever built, these two
columns are the cheapest possible thing to migrate: a row that already carries
its tails needs no re-derivation to move.

**Why the name is `difference_lo`/`difference_hi` and not something shorter.**
The repo's `_lo`/`_hi` convention means "bounds on the named quantity" -
`kg_lo` bounds `kg`, `target_hi` bounds `target`. Under that convention:

- `bias_lo`/`bias_hi` would read as bounds on the BIAS, which is a confidence
  interval on the median. That is exactly the claim C3 forbids, and the name
  would smuggle it in.
- `spread_lo`/`spread_hi` would read as bounds on the SPREAD, which is a claim
  about how well the width itself is known. Also not what these are.
- `difference_lo`/`difference_hi` reads as bounds on the difference, which is
  precisely what they are - and it names the row's implicit subject out loud
  for the first time. `bias` and `spread` have always been statistics OF the
  difference; nothing on the row said so.

**The rules the fields ship with** (all enforced in `_comparability_problems`,
all with a test):

1. Numeric, checked like `bias` and `spread` - `"banana"` is refused.
2. Both or neither. A range with one end is not a range; the same argument
   `_band_problems` already makes for `target`/`target_hi`.
3. `difference_lo <= difference_hi`.
4. Forbidden beside `not_comparable`, exactly as `bias` and `spread` are:
   nothing was measured to have a range.
5. `spread` is required beside them, and must equal `difference_hi -
   difference_lo`. This is the redundancy answered: the two spellings of one
   width are checked against each other rather than trusted to agree.
6. Where `bias` is present, `difference_lo <= bias <= difference_hi`. A median
   outside the range it came from is an incoherent row.
7. **Not required beside `offset`.** A writer who honestly knows a width and
   not its ends must not be forced to invent the ends - that would be the
   fabrication the dataset exists to refuse, arriving through a validation
   rule. Required-beside would also invalidate every `offset` row written
   before contract 52, which is a break this change has no reason to take.

Rule 7 is the one worth noticing. It means the fields express three states
rather than two, and the third is the honest one: a width whose ends are
recorded, a width whose ends are not, and no width at all.

### What this does not buy, stated as plainly as the fields themselves

**The tails do not earn a band, and #372 still has nothing to build on.** Two
independent reasons, either sufficient:

1. **`offset` does not lift the seam.** `policy.comparability` and
   `all_comparable` are unchanged: only `comparable` licenses reading a series
   across a change of instrument, and no overlap can establish that on its own.
   A row that may not be read across is not a row a band can be derived from,
   whatever columns it carries.
2. **Observed extrema are not a coverage interval.** The minimum and maximum of
   101 differences are the two most sample-dependent numbers in the set: they
   can only widen as more days arrive, and they carry no statement about the
   102nd run. Drawing them as an error band would put a coverage claim on a
   figure that has none, which is C1's failure with better data behind it -
   and better data behind a fabricated claim is worse, not better, because it
   is more persuasive.

So a client meeting a `comparability` row after this change is under exactly
the rule it was under before it: **it may not draw a band from a comparability
row alone.** What changed is that the row can now state what was measured
without losing half of it, and that a reader who ignores the warning and halves
the spread can now be *contradicted by the row itself* rather than only by a
docstring they never read.

---

## Option 2 - the row stays as it is, and a band may not rest on it. LOSES

`spread` remains a bound, the tails stay beside the row in
`overlap_calibration`'s `observed` key, and the client is told a
comparability row cannot support a band.

**What a client can honestly draw from it.** The same statement as option 1, if
and only if it calls `overlap_calibration` rather than reading the record. From
the record alone: a centre and a width, with the asymmetry gone.

**What it costs.** The cost is the reason it loses, and it is not "a missing
feature":

- **The record is lossy.** `vitai calibrate` measures four numbers and the
  dataset can store two. An athlete who appends the proposed row destroys the
  asymmetry on write. A repo whose doctrine is that evidence lives in the
  record cannot have its only writer produce evidence the record cannot hold.
- **The asymmetry lives in prose.** `vera`'s row carries it as "it parts one
  way only" in a `note`. This repo has spent several contracts removing exactly
  that shape - a fact stated in English beside data that contradicts it.
- **The warning is not where the danger is.** "Do not read `bias` plus or minus
  half the `spread`" appears in a module docstring, an API docstring and a CLI
  line. It does not appear in `data/comparability.jsonl`, in the SQLite
  projection, or in anything a third-party reader touches. The most dangerous
  consumer is the one that never sees the surface carrying the warning.
- **It leaves #372 with nothing to build on** - which is true, and true under
  option 1 as well. That is not a cost that separates them.

**What it forecloses.** Nothing permanently; it defers. But it defers by
leaving a known-lossy write path in place, and every `comparability` row
written meanwhile loses its shape irrecoverably unless the raw claims survive
to be re-derived from.

**The strongest version of this option, and why it still loses.** The honest
case for option 2 is #386: 61 schema fields are exercised by no corpus row, and
adding model ahead of a reader compounds that debt. It is a live objection in
this repo and it parks a whole design cluster. It loses here on two specifics.
First, these fields have a WRITER the day they land - `overlap_calibration`
fills them and `vera` carries them - which is more than `absent_reason` had
when it shipped one contract ago on the same reasoning. Second, the debt #386
describes is fields that *cannot* be filled honestly; these are fields whose
values are already computed, already returned, and already discarded at the
schema boundary.

---

## Option 3 - a separate `overlaps` dataset, cited by `overlap_ref`. LOSES NOW, MAY WIN LATER

The full evidence of a paired-measurement window as its own dataset - pair
count, ambiguous days, first and last date, median, low, high - with
`comparability` remaining the DECLARATION that cites it. `overlap_ref` becomes
a key into that dataset instead of a sentence.

**What a client can honestly draw from it.** Everything option 1 offers, plus
the pair count and the dropped-day count as data rather than as prose, which is
what a reader actually needs to decide whether to trust the figure at all.

**What it costs.** A new dataset, its generation, its validation, its resolver,
its sensitivity classes, its display names - and a **breaking** change to
`overlap_ref`, whose current value is a human sentence on every existing row.
That is not additive, and both pinned clients absorb it.

**What it forecloses.** Nothing, and this is very likely the right long-term
shape. `overlap_ref` being prose is a real smell: a reference that is a
sentence is not a reference, and it is the field carrying the C2 reporting
minimum today. It loses NOW because it is a large speculative build for a
dataset with exactly one row in one fixture, and because option 1 is a strict
subset of it - the two columns migrate into it unchanged if it is ever built.

**This one deserves an issue.** It is the shape the evidence points at, and it
should be filed rather than left in a proposal.

---

## Option 4 - a derived view: the resolver re-computes the tails at read time. LOSES

`Vitai.comparability()` returns the tails alongside the in-force row by
re-running `overlap_calibration` over the raw claims.

**What a client can honestly draw from it.** The same as option 1, from an API
call.

**What it costs / forecloses.** It loses on principle rather than on effort. It
breaks the boundary the module is built on - "the engine measures; the record
declares" - by having a resolver answer a question the record did not state.
It would answer for pairs no row was ever written about. And it would put a
DERIVED figure beside a DECLARED one in a single return, which is precisely the
confusion `overlap_calibration` and `comparability()` are two separate calls to
avoid. It also silently changes its answer when raw claims are appended, under
a row whose whole purpose is to be a dated, superseded statement.

---

## Option 5 - one field instead of two. LOSES

Since `spread` already holds the width, one number fixes the range: store
`difference_lo` alone, or store the median's offset within the width.

**What it costs / forecloses.** It saves one column and charges every consumer
an arithmetic step to recover the other end - and a consumer doing arithmetic
on a comparability row is the exact behaviour this dataset spends three
docstrings discouraging. It also makes the tails depend on `spread` being
present and correct, where option 1 makes the two check each other. Rejected
for the same reason `target`/`target_hi` are two columns.

---

## Option 6 - a coverage-qualified interval. REJECTED BY THE CONSTRAINTS

Give the row a coverage factor, or an expanded uncertainty, or a stated
interval with its `k` - the shape `01-schema.md` designs for `u_given` /
`u_given_as` / `u_eval`.

**Rejected outright**, and named here only so nobody re-proposes it. C3 forbids
inventing a coverage factor, and there is nothing to derive one from: 101
paired days of trail running support no distributional assumption, and the
dominant term in the disagreement is not random at all - it is the canopy,
which is a property of the route rather than of the instrument. A `k` on this
row would be a confident wrong number about confidence, on the one dataset in
this engine whose entire reason for existing is that such numbers must be
earned.

---

## Two findings this raised that are NOT in scope here

**`spread` does not say how it was obtained.** C2's reporting minimum is
satisfied for COMPARABILITY by `basis: overlap`, but not for the FIGURE:
`spread: 1.26` from a full observed range and `spread: 1.26` from a published
plus-or-minus doubled are indistinguishable in the row. Today only one writer
exists and it always means the full observed range, so nothing is wrong yet -
but the second writer will make it wrong silently. The tails partly cover it,
since `spread == difference_hi - difference_lo` on a row carrying them is
unambiguously a full observed range; they do not cover the rows without them.
Worth an issue.

**The pairing rule is same-date, exactly one reading per origin.** Named in
#410 and unchanged here. `vera` loses nothing to it, and a record whose two
instruments both log several activities a day would see its overlap shrink for
a reason that has nothing to do with the instruments. The dropped-day count is
the signal, and it is returned but not recorded - which is part of what option
3 would fix.

---

## What is left for the operator

**The band decision itself.** Everything above establishes that a
`comparability` row can now STATE an asymmetric observed range. It establishes
equally that nothing may DRAW a band from one. The open question, unchanged in
substance by this change and not taken by it:

> Under what conditions, if any, may a client render an error band derived from
> a measured overlap - given that `offset` does not lift the seam, and that
> observed extrema carry no coverage claim?

Three ways that could go, none of them taken here:

1. **A band never rests on `comparability` alone.** The dataset describes a
   PAIR; a band describes a VALUE; attaching one to the other is the part of
   #402 that was never built. Cleanest, and it means #372 needs a different
   input entirely.
2. **A band may rest on a `comparable` row** - which does lift the seam - and
   never on an `offset` one. Coherent with everything already decided, and it
   makes the athlete's declaration the gate, which is where this engine puts
   every other lifting decision. Needs someone to decide what a band means when
   `bias` is forbidden beside `comparable`.
3. **An observed range may be rendered as an observed range, never as an error
   band**, in a surface about instruments rather than about values. This is
   arguably already permitted and needs no new rule - but it needs saying,
   because the difference between the two renderings is a caption, and a
   caption is not a control.

That is a decision about what a client may show a person. It is not an
engineering fact and this change does not take it.
