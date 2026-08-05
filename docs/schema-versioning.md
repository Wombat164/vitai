# Schema versioning and deprecation

**#261 step 1, the docs half.** What counts as a breaking change, how a
retired thing announces itself, and how our three version numbers relate to
the rule IEEE 1752.1 states.

This is policy, not code. Nothing here changes behaviour today; it settles
what the existing behaviour is supposed to mean, so the next schema change is
argued against a written rule rather than against whoever remembers most.

## Why adopt someone else's rule

The engine already has a versioning discipline, spread across G25, G89 and the
contract table, and it is substantially the same rule 1752.1 writes down. What
we lacked was a **statement of when a change is breaking** that could be
checked rather than felt.

Adopting the standard's wording costs nothing and buys two things: the argument
about a specific change stops being about taste, and the mapping obligation
#261 commits us to gets easier, because the version semantics on both sides
already agree.

Where the standard and our practice differ, our practice wins and the
difference is recorded here as a mapping rather than smoothed over. That is
#261's standing rule: **conformance is a mapping obligation we can prove, not
model replacement.**

## The rule, adopted verbatim

From IEEE 1752.1:

> **Major** version changes on a breaking change, defined as changing the
> datatype of an existing property **or** adding a required property.
> **Minor** version changes on adding or removing an optional property.

Two things about that definition are worth stating out loud, because both have
bitten this repo.

**Adding a required property is breaking.** It is the one that does not look
like it. Every existing line becomes invalid the moment the field lands, which
is precisely the failure G25 was raised for: "additive nullable fields
currently break validation of every pre-existing line" was a CODE-VERIFIED
CRITICAL, and the fix was that new fields arrive **optional and nullable**.
The standard's rule is the same rule from the other side: if you find yourself
adding a required property, you are making a major change and old data is
about to stop validating.

**Removing an optional property is only minor.** That is the standard's call
and we take it with a caveat, below, because removal is where G89 lives.

## Our three version numbers, and which one the rule governs

We carry three, and they answer different questions. Conflating them is a
recurring source of confusion, so:

| number | versions | moves when | gate? |
|---|---|---|---|
| `contract` | the READ MODEL - the built SQLite shape | a table or column changes shape | **yes**, a consumer gates on it |
| `generations` (per dataset) | the LINE SHAPE - what a row owed when it was written | a dataset's field set changes | yes, per dataset |
| `engine` (`__version__`) | the package | any release, including a docs fix | **never**. Provenance for a bug report |

**The 1752.1 rule governs `generations`**, because that is our per-schema
version: it describes the shape of a line in one dataset, which is what a
1752.1 schema file describes.

`contract` is a different axis with no equivalent in the standard. It versions
the projection rather than the record, it is a single integer across all
datasets, and it moves on merge order rather than on issue order. It is not a
semver and must not be read as one.

`engine` gates nothing, deliberately. It moves for a docs fix and stands still
while the schema moves, so a pin that gates on it is telling itself a
comforting lie. (It was also wrong for a full release - see #266 - which is why
it now has a test.)

### The mapping, stated so it can be proved

Our generations are monotonic integers, not `major.minor` pairs. Exporting to
1752.1 therefore needs a rule, and this is it:

- A generation increment that **added an optional nullable field** maps to a
  **minor** bump.
- A generation increment that **changed a datatype or added a required field**
  maps to a **major** bump.
- Because our integer does not distinguish them, the migration table is the
  authority on which kind each increment was, and it already records that per
  row.

This is lossy outward and that is normal. What it must never be is lossy
inward: nothing here licenses replacing a generation integer with a semver
string.

## Deprecation is in-band, and it is the half we do not have

The standard's shape: a superseded schema keeps a `deprecation` object
carrying a **reason**, a **`supersededBy`** pointer and a **date**. A consumer
that fetches the old thing learns it is old **from the thing itself**.

That property is the whole value, and #261 exists partly because we learned it
the hard way in reverse: Open mHealth was analysed and recommended before
anyone noticed every schema in it carried exactly such an object pointing at
1752.1. The deprecation was in-band and we still missed it, which is an
argument for making ours machine-readable rather than prose.

**We do not have this.** Retirement today is G89 plus a migration-table row,
and G89 is stronger than the standard in one respect and weaker in another.

**Stronger: G89 is a three-part change.** A retirement is not done until the
successor exists, old lines keep validating, the forward map lives in ONE
table, and **every reader prefers the new name**. The standard has nothing
about readers. The `hip_pain` instance is why: the mapping was correct, old
rows kept gating, the suite stayed green, and the pain verdict still resolved
against the retired name, so new data quietly lost a linkage. A `deprecation`
object would not have caught that. G89 does.

**Weaker: nothing carries the deprecation.** A consumer reading our schema
cannot see that `status` was retired in favour of `lifecycle_status`; it has
to read the CHANGELOG or the contract table, both prose. Contract 25 kept
`status` as a column carrying the same value precisely so consumers would not
break, which was right, and means a consumer has no signal at all that it is
reading a retired name.

**Committed here:** a retired key gains a machine-readable deprecation record -
reason, successor, date - and G89's three parts remain the definition of done.
The standard supplies the announcement; G89 supplies the discipline. Neither
replaces the other, and shipping the announcement without the discipline would
be the worse half.

Where that record lives is an implementation question (schema-side, so that
`api.schema()` can carry it, is the obvious candidate given #266 just
established that pattern) and is deliberately not decided in a docs change.

## Vocabulary binding by persistent URL

Adopted. A field that draws on an external vocabulary names it **by persistent
URL** rather than restating its members, and more than one vocabulary per
field is allowed (1752.1 names SNOMED CT, LOINC and IEEE 11073-10101).

This is `docs/vocabularies.md`'s "registry, not code" rule extended one step:
a vocabulary we did not author should be referenced, not copied. Copying is
how a restated enum drifts from its source, and the drift is silent because
both look like valid data.

The caution from #260 applies unchanged and is not weakened by this: binding
by URL is not licence to bundle someone's database. Share-alike attaches to
the DATABASE, so referencing a vocabulary at runtime and shipping a copy of it
are different acts with different consequences.

## What this does not commit us to

- **Not `unit-value` yet.** Moving the unit out of the field name is #260's
  most expensive change and is a separate decision (see the README's units
  clause, added in #264). This document settles VERSIONING, not shape.
- **Not the typed unit-value family.** Pre-coordinated; see
  `docs/prior-art-schemas.md`.
- **Not `major.minor` strings on our datasets.** The rule is adopted; the
  numbering stays ours, with the mapping above.

## Changelog

- 2026-08-05 - written. #261 step 1, docs half: the breaking-change
  definition adopted verbatim, mapped onto our three version numbers, and the
  in-band deprecation gap recorded against G89.
