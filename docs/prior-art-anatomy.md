# Prior art: naming the place that hurts

`pain_site` shipped as free text. That meant "knee", "Knee", "left knee" and
"patella" were four unrelated places, none of them countable, none comparable
across a year, and none groupable into "anything in the lower limb". Before
inventing a body-part list we swept the existing work, because people have
been arguing about how to name anatomical locations for considerably longer
than this project has existed.

The one-line verdict: **the structural question is already settled by two
independent standards - post-coordinate laterality - and the vocabulary
question has a validated answer at exactly our scale in the self-report
literature. What we should NOT do is import a clinical ontology.**

---

## 1. Clinical terminologies (SNOMED CT, FMA, UBERON)

The obvious move is to adopt a real terminology. It is the wrong move here,
for three separate reasons.

**SNOMED CT** has a body-structure hierarchy and is the reference standard
that FHIR binds to. It is also **not redistributable by us**: use inside a
member country needs a (free) Affiliate License, and per the license terms
end users without one "are not permitted to distribute or share SNOMED CT
Content or Derivatives". vitai is a public MIT repo that anyone may fork and
redistribute, so bundling SNOMED content - or arguably even a table of its
concept ids as mappings - puts a licensing hazard into every downstream copy.
**Avoid as bundled content.** An operator who holds an Affiliate License can
map to it in their own private content repo; that is their license to use,
not ours to assume.

**UBERON** is openly developed and covers human anatomy well, but it is a
multi-species ontology - "over 13000 classes representing structures that are
shared across a variety of metazoans", with a composite version beyond 40,000
classes. **Avoid**: cross-species generality is precisely the axis we do not
need, and the size is a liability rather than a feature for a record whose
weekly cost must stay under three minutes. (We did not confirm UBERON's exact
licence text during this sweep; it is moot given the scope mismatch, and
should be checked before any future use.)

**FMA** (Foundational Model of Anatomy) is the same story at greater depth:
a reference ontology for anatomists, not a picker for a tired athlete on a
Sunday evening.

The general point: a clinical terminology optimizes for *precision across all
of medicine*. We are optimizing for *an athlete correctly and quickly saying
where it hurts, every week, for years*. Those are different problems, and
solving the first one here would break the second.

## 2. The structural pattern: post-coordinate laterality (adopt)

Two standards, arrived at independently, make the same call:

- **HL7 FHIR `BodyStructure`** splits `includedStructure.structure` (the body
  site) from `includedStructure.laterality`, with `qualifier` and
  `bodyLandmarkOrientation` alongside. Laterality is explicitly *not*
  pre-coordinated into the structure code.
- **openEHR `CLUSTER.anatomical_location`** mandates exactly one element -
  the body site name - and hangs laterality, aspect, region and anatomical
  line off it as separate qualifiers.

**Adopt directly.** `pain_site` names a structure; `pain_side` carries
`left | right | bilateral | null`. This is the single most load-bearing
decision in the design, and it is not ours: two mature standards converged on
it. It also has a mundane practical benefit - folding sides into names would
double the vocabulary and reintroduce the exact ambiguity ("left knee" vs
"knee") the registry exists to remove.

The corollary we added: structures are marked `paired` or not. A paired site
with a pain score and no side is rejected, because "my knee hurts" does not
tell a coach which knee to stop loading. A midline site with a side is also
rejected, because claiming one is false precision.

## 3. The vocabulary: validated self-report instruments (adapt)

The closest prior art to what vitai actually does - an athlete reporting
their own pain, repeatedly, under a tight time budget - is the self-report
pain-map literature, not clinical coding.

- **Michigan Body Map (MBM)**: a validated self-report instrument covering 35
  predefined body areas. Validation across 402 patients in five studies;
  administration takes 39-44 seconds with errors in 7.2% of possible areas.
  The revised version added front and back images and "improved guidance on
  right-sidedness vs left" - i.e. the failure mode they had to design against
  is exactly the laterality problem section 2 solves structurally.
- **ACR 2016 Widespread Pain Index (WPI)**: a coarser 19 regions across five
  areas. Simpler, but cannot distinguish achilles from calf, or groin from
  hip - distinctions a training record needs, because they imply different
  causes and different load changes.

**Adapt, do not adopt wholesale.** Both instruments are validated for
*assessing chronic widespread pain*, which is not what we are doing; their
purpose does not transfer, but their granularity does. `semantics/
body_sites.toml` takes MBM-scale granularity and trims it to the
musculoskeletal sites a training record can act on, keeping the WPI's coarse
regions as the rollup level.

## 4. Sports-specific coding: OSIICS (adopt as mapping)

**OSIICS** (Orchard Sports Injury and Illness Classification System, v16 in
2025) is one of two systems adopted by the IOC at the 2019 Lausanne consensus
meeting on injury and illness surveillance in sport. Its codes lead with a
body-region letter, then a pathology-type character, then further detail
(`C` = chest, with `CXBxx` for breast structures within it; `L` = lumbar,
which absorbed the old buttock code `B` in 2019). It is **free to use with
acknowledgement**, and the v16 paper is CC BY.

**Adopt as an outbound mapping**, not as our vocabulary: it is a diagnosis
coding system with over 1500 options, aimed at surveillance databases, so it
is the wrong thing to make an athlete choose from - but it is exactly the
right thing for the record to be *translatable into*, since it is what sports
medicine actually uses.

Honesty about what shipped: only the region letters we could verify against a
primary source are recorded (`H` head, `N` neck, `S` shoulder, `U` upper arm,
`E` elbow, `C` chest, `L` lumbar). The rest are deliberately blank. A wrong
code that looks authoritative is worse than an absent one, and completing the
map needs the official OSIICS code table.

## What this changes for vitai

1. `semantics/body_sites.toml` is the first **curated registry** (P5) to
   exist - versioned, human-mergeable knowledge that is neither data nor
   code, with its evidence recorded in its own comments.
2. `pain_site` becomes a closed vocabulary with aliases, so the athlete keeps
   writing "IT band" or "lumbar" and the engine stores `knee` or
   `lower_back`. The vocabulary is something the ingest skill maps onto, not
   something the athlete has to learn.
3. `pain_side` post-coordinates laterality, validated against whether the
   structure is paired.
4. A two-level `region -> site` hierarchy makes "anything in the lower limb"
   answerable with a dictionary lookup rather than an ontology reasoner.
5. Nothing restrictively-licensed is vendored, so the repo stays MIT-clean
   and forkable.

Deliberately still open: pain is currently one score at one site per day.
Multiple simultaneous sites, and pain *quality* (sharp / dull / burning,
where the McGill Pain Questionnaire is the obvious prior art), are not
modelled. Neither is needed to gate training load, which is what the pain
field exists for today.

## Key sources

- Terminologies: SNOMED CT licensing (SNOMED International / UMLS Affiliate
  License Agreement); UBERON (obophenotype); FMA.
- Structure: HL7 FHIR `BodyStructure`; openEHR `CLUSTER.anatomical_location`.
- Self-report instruments: Michigan Body Map (preliminary validation, *PAIN*
  2016; University of Michigan MPR); ACR 2016 revised fibromyalgia criteria
  (Widespread Pain Index).
- Sports coding: OSIICS v16 (2025), *Journal of Sport and Health Science*,
  CC BY; IOC 2019 Lausanne consensus.
