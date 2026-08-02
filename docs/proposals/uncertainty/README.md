# Uncertainty, precedence and provenance: a proposal

**Status: PROPOSAL, not doctrine.** Nothing here is decided. Phase 0 exists
specifically to decide whether most of it should be built at all.

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

**Do not import numeric accuracy figures.** No incumbent platform models
measurement error at all. Where published figures exist they cover the random
term only and are contradicted by field observation. A borrowed
population-level figure is a confident wrong number about confidence. Store
instrument identity, comparability and competence; compute coverage, which is
honest because it comes from the data itself; and admit numeric uncertainty
only from this record's own replicates or overlap windows.

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
