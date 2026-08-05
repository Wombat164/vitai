# Uncertainty, precedence and provenance: a proposal

**Status: PROPOSAL, not doctrine**, except where marked settled below.

**Phase 0 has run (2026-08-02) and it cut the largest item in this proposal.**
The experiment that gated the work refused more than three quarters of scored
weeks under the record's own dispersion, and more than half admitted no verdict
word at all, so the capability registry is **dropped as a route to better
verdicts** and survives only for seam detection. Twelve verdicts in the shipped
engine were found to flip, so the refusal predicate ships regardless. The actual
remedy is to change the decision unit, which needs no new schema. Numbers and
reasoning are at GATE A in `06-roadmap.md`.

Three further questions are settled rather than open:

- **Condition scoping** is per field. The slot is gated and stays unpopulated
  (`01-schema.md` s4b).
- **The #73 precedence conflict does not exist.** #73's dominant instance was a
  device losing to a device through a stamping bug, and its tripwire fires on
  unattributed rows rather than on low-ranked ones (comment on #167).
- **`no_data` must be widened before any refusal ships** (#177), because it
  already carried four states separable only by which fields were null.

These documents came out of one working session: an adversarial review of
issues #167 to #171, three prior-art surveys (measurement science, computer
science on conflicting claims, and how nine incumbent platforms actually
behave), and a synthesis pass. Several claims in the original issues turned
out to be false and are corrected here and in comments on those issues.

## Read in this order

| file | what it decides |
|---|---|
| `00-phase0-experiment.md` | the cheap experiment that gates everything else, with pass and fail thresholds stated in advance |
| `06-roadmap.md` | sequencing, effort, and an explicit NOT BUILDING table |
| `01-schema.md` | fields, vocabularies, effective dating, retirement paths |
| `02-engine.md` | module by module, including what is not deliverable |
| `03-tests.md` | named tests with fixtures and assertions |
| `04-issue-rewrites.md` | dispositions for #167 to #171, ready to apply |

The client-side rendering rules live in the client repo, not here.

## The three findings that matter most

**The precedence ladder is a prioritized repair whose defect is totality.**
A total order over source names cannot say "no opinion", so it breaks ties by
sort order. The published construct is a partial order over conflicting
claims, under which the behaviour #167 asks for is the default semantics
rather than a new rule, and a genuine tie surfaces as a refusal.

**No imported accuracy CLAIMS in arithmetic.** No incumbent platform models
measurement error at all. Where published figures exist they cover the random
term only and are contradicted by field observation. A borrowed
population-level figure is a confident wrong number about confidence. Store
instrument identity, comparability and competence; compute coverage, which is
honest because it comes from the data itself.

Numeric uncertainty enters arithmetic from exactly **three** routes, and the
distinction is between a *claim about what an instrument can do* and an
*observation or a definition*:

1. **This record's own replicates and its own overlap windows.** `u` is
   canonicalised only when `basis` is `own-replicates` or `overlap`.
2. **A per-reading figure the source reports alongside the reading**
   (`u_obs`), which is an observation rather than an import, is carried with
   provenance, is adjudicated like any other claim, and is never an anchor.
3. **Definitional constants**: a display resolution step, a declared
   measurand looseness, a unit conversion, a cited published formula
   coefficient, a scale's declared range. These are not accuracy figures and
   live in the registry with their citation.

What stays banned is unchanged and is the whole point: a datasheet,
validation-study or judgement figure keeps `u = null`, and its `u_given`
survives as an auditable annotation that may inform rendering copy and never
arithmetic.

*Reworded 2026-08-05 (#264). The schema in `01-schema.md` already drew all
three lines correctly - the `u_obs` slot, the `basis`-gated canonicaliser, and
the `resolution_step` contribution. Only this prose summary was absolute, and
read literally it banned the engine's own design and blocked #171.*

**Accuracy and trust are different axes, and there is a third.** A value can
be measured perfectly by a working instrument and still not mean what its
field name says. That construct error can exceed every instrument error in
the literature, and neither accuracy metadata nor a trust parameter detects
it.

## Prior art, so none of this is reinvented

Measurement vocabulary comes from the international metrology guides, which
are explicit that accuracy is not a quantity. The trust and accuracy
separation is thirty years old in the data quality literature. The
conflicting claims problem is prioritized repair. Naming a derived value's
inputs is a published provenance relation. Statistical truth discovery is
deliberately NOT adopted, for a stated reason: it needs redundancy this kind
of record does not have, and its own benchmarks show it underperforming
random guessing below that threshold.

Full citations are in the individual documents.
