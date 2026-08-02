# Schema: exact fields and config changes

Ordering of this file follows build order: (1) partial-order resolution config,
(2) resolution outcome vocabulary, (3) derivation lineage, (4) instrument
capability dataset, (5) qualifications, (6) small vocabulary additions, (7) the
`accuracy` ban. Everything is additive under G25 (new keys get a generation,
old lines keep validating). No field is ever removed.

## 1. Resolution config: from total order to partial order

Basis: prioritized repairs (Staworko/Chomicki/Marcinkowski 2012, DOI
10.1007/s10472-011-9241-8): the priority relation is a partial preorder over
conflicting claims, not a total order over source names. Two consequences the
current config cannot express: "no opinion" (a detectable tie instead of a
silent alphabetical tiebreak) and #167's rule as DEFAULT semantics (with no
measurement present nothing dominates a narrative claim, so it wins with no
conditional-rank machinery; conditional rank would violate independence of
irrelevant alternatives and is rejected).

### 1.1 New config surface (`vitai.toml`)

```toml
[resolution]
# LEGACY, kept working: a list is canonicalised to a chain of edges.
# source_order = ["scale-a", "watch-b", "app-c"]

# SUCCESSOR: explicit dominance edges. Each entry: winner, loser.
# Absence of a path between two sources = no opinion = tie on conflict.
edges = [
  ["scale-a", "app-c"],
  ["watch-b", "app-c"],
]

# Per-field overrides remain, same shape, same successor form:
[resolution.per_field.kcal_in]
edges = [["food-log", "watch-b"]]
```

| property | value |
|---|---|
| type | list of 2-element string lists |
| validation | no self-edge; cycle detection over the transitive closure at load (a cycle is a config error, refused at build with the cycle printed); duplicate edge tolerated |
| semantics | claim A dominates claim B for a field iff a directed path exists from A's source to B's source in the field's edge set (per-field edges REPLACE, not extend, the default set for that field, matching current `_ladder` behaviour) |
| migration (G89) | (1) successor exists: `edges`; (2) ONE canonicaliser: `config.resolution_edges()` converts a legacy `source_order` list into chain edges `[(s[i], s[j]) for i<j]`; nothing else ever reads `source_order`; (3) every reader (resolution, validate, report) calls the canonicaliser. `source_order` stays legal forever. |
| failure mode | an operator writes edges believing order in the list matters (it does not). Mitigated: `vitai validate` prints the computed dominance relation for any contested pair found in the record. |

### 1.2 Capture-class dominance (the #167 fix)

Not config: an engine-level partial-order layer composed BEFORE source edges.

| rule | statement |
|---|---|
| CAPTURE-DOM | for one (date, field) contest, a claim whose capture class is `measurement` dominates a claim whose capture class is `testimony`, regardless of source edges. |
| class map | `measurement` = {connector, file_export, ble, photo}; `testimony` = {narrative, manual_entry}; `derived` and `unknown` are NEITHER class (they neither dominate nor are dominated by this rule; source edges and restatements decide, as today). |
| where it lives | new key `class` in `semantics/capture.toml` entries; closed vocab `measurement \| testimony \| computed \| unknown` |
| P2 compliance | the class is a property of the capture registry (engine semantics, versioned in the repo), not athlete data; registry changes are code changes with the registry's `version` bump. |
| what it does NOT do | does not touch fields only testimony covers (reps, RPE, pain): with no measurement-class witness the rule is vacuous, which is #167's availability condition falling out of partial-order semantics instead of being configured. |
| failure mode | photo is classed `measurement` but `may_transcribe = true` (a misread digit). Accepted: restatements already ranks photo below ble/export within the class; the class rule only fires ACROSS classes. |

## 2. Resolution outcome vocabulary (Belnap-shaped)

Field-level outcome, new column in `justifications` and `explanations` output
(read-model change, contract bump):

| outcome | meaning | canonical value |
|---|---|---|
| `resolved` | a dominating claim existed | winner's value |
| `tie` | conflicting claims, no dominance path either way (Belnap Both) | **null** + tripwire `unresolved_tie` naming both values and both sources |
| `unwitnessed` | no claim carried the field (Belnap Neither, already the None case) | null |

Rule: a tie is NEVER broken by sort order, recency, or name. Determinism is
preserved because null is deterministic. Recency and restatements still apply
WITHIN a source (same-source correction path, #70/#140) before tie detection:
two claims from one source are one witness corrected, not a conflict.

Failure mode: tie-as-null regresses records that relied on the alphabetical
fallback. Mitigated: the tripwire says exactly which edge to add, and the
legacy `source_order` chain canonicalises to a total order, so existing
configs see zero behaviour change until they adopt `edges`.

## 3. Derivation lineage (#170)

FHIR `Observation.derivedFrom` (0..*), not PROV binary derivation. Declared
lineage only: semiring provenance (Green/Karvounarakis/Tannen 2007) shows
declared lineage suffices for staleness DETECTION; re-execution is only needed
for drift correction and is not specced.

New keys on `weight`, `daily`, `sessions`, `measurements`, `sets`, `meals`
(gen-3 additions to KEY_GENERATION):

| field | type | null | vocabulary | per | validation |
|---|---|---|---|---|---|
| `derived_from` | list of claim-id strings | yes | claim ids (`dataset:date:source[:ordinal]`) | observation | each id parses under `claim_id` grammar; list non-empty if present; a row may not derive from itself |
| `derived_op` | string | yes | free text, declared not re-executable (e.g. `"sum"`, `"same-route-reversed"`) | observation | requires `derived_from` |

Capture registry addition (`semantics/capture.toml`), the actor split #170
asks for:

```toml
[capture.derived_external]
label = "Computed outside the engine from named rows in this record"
aliases = ["athlete-derived", "reconstructed"]
may_transcribe = false
has_artifact = true            # the inputs are the artifact
restatements = 2               # costly side: inputs may include testimony
class = "computed"
```

Validation: `derived_from` present requires capture in {derived,
derived_external}. Consequences wired in `02-engine.md`: a derived value never
corroborates its own inputs (ancestor check), and a superseded input flags
every dependant as stale (`stale_derivation` tripwire), reusing the existing
`retractions` cascade shape.

## 4. Instrument capability dataset

Names from W3C SSN/SOSA `ssn-system` (Section 5.1) wherever one exists;
numeric noun from GUM (standard uncertainty), bias from VIM 2.18 (ssn-system
has no bias term). The trust axis stays hand-declared (edges, qualifications)
indefinitely; no learning.

**Direction reversal (stream 2), superseding the original brief.** A
per-source numeric accuracy import is NOT built: only power meters publish
figures, those cover the random term only, field observation contradicts
them by up to 20 %, one vendor's marketing figure is half its own service
tolerance, and the backbone sources of a typical record publish nothing.
A borrowed number would be a confident wrong number about confidence, which
is the exact defect #171 warns against. What IS stored: instrument identity,
a competence flag, a comparability class earned by overlap, and numbers ONLY
where THIS record measured them itself. Borrowed figures may be archived as
annotations (`u_given` + basis) but are never canonicalised into an
engine-consumed `u`.

New PRIVATE-RECORD dataset `capabilities.jsonl`, policy-dataset semantics
(effective-dated, append-only, identity-keyed like `goals`; it never enters
the observation resolver):

| field | type | null | vocabulary | notes |
|---|---|---|---|---|
| `date` | ISO date | no | | effective-from (P2: no current-state values; a new line with the same identity key supersedes from its date forward) |
| `system` | string | no | source/origin slug | `sosa:madeBySensor` framing: names the instrument, matching `origin`, falling back to `source` |
| `field` | string | no | a dataset column | which measurand this row describes |
| `condition` | string | yes | open vocab, lowercase-kebab (`open-sky`, `indoor`, `treadmill`) | ssn `Condition`; null = unconditional |
| `u` | number | yes | | STANDARD uncertainty, converted by the engine from `u_given`; never written by hand |
| `u_given` | number | yes | | the figure as stated by its basis document |
| `u_given_as` | string | yes (required with u_given) | `standard \| expanded_k2 \| ci95 \| ci99 \| limits \| triangular \| display_step` | ONE canonicaliser converts (GUM Type B table: /2, /1.960, /2.576, /sqrt(3), /sqrt(6), *0.29) |
| `u_relative` | bool | no (default false) | | proportional (GPS distance) vs absolute (a scale) |
| `u_eval` | string | yes (required with u_given) | `type_a \| type_b` | GUM 4.2/4.3 evaluation route |
| `u_condition` | string | yes | `repeatability \| intermediate \| reproducibility` | VIM 2.15 note 2: precision is meaningless without its specified condition |
| `bias` | number | yes | | known systematic offset (VIM 2.18). The engine NEVER auto-corrects (P4: no silent adjustment); a declared bias powers seam detection (#33) and renders as a labelled offset. GUM 6.3.1 noted in the field doc: a known bias belongs here, not widened into `u`. |
| `resolution_step` | number | yes | | display step dx (ssn `Resolution`); u contribution 0.29*dx, folded in by the canonicaliser only when `u` is otherwise absent (GUM 4.3.10 double-counting ban: never added to an observed-scatter u) |
| `definitional_u` | number | yes | | VIM 2.27 floor from measurand looseness (fasted? clothed? time of day?). Weight already has a code-level cousin: `clocks.DIURNAL_KG_PER_DAY` is the diurnal component of definitional uncertainty under another name; the capability row makes it declarable per measurand. |
| `basis` | string | yes (required with u_given) | `datasheet \| validation-study \| own-replicates \| overlap \| judgement` | the parameter's own provenance, as #171 correctly demands |
| `basis_ref` | string | yes | free text citation, or the overlap claim ids | |
| `competence` | string | no (default `unknown`) | `measures \| proxy \| absent \| unknown` | the #171 "zero, unknown, wide are three different things" state, now the PRIMARY payload: does this system measure this field at all. `absent` feeds the resolution competence filter (02-engine); `proxy` requires `construct_note`. |
| `construct_note` | string | yes (required when competence = proxy) | free text | the THIRD axis (stream 2): construct validity - the field does not mean what its name says. Live class of defect: a resting-HR proxy can run far above the continuous nightly minimum, exceeding every instrument error in the validation literature; no u, bias or trust parameter would ever catch it. |
| `note`, `recorded_at`, `supersedes` | as elsewhere | | | standard machinery |

Identity key: (`system`, `field`, `condition`). Every quantity nullable:
`unknown` is representable and never defaults to a plausible number. A row with
`u = null` and a `note` is a legitimate, honest entry ("no validated figure
exists for this device generation").

**Numeric-u validation rule (the reversal, enforced):** `u` is computed by
the canonicaliser ONLY when `basis` is `own-replicates` or `overlap`. Rows
with basis `datasheet | validation-study | judgement` keep `u = null`; their
`u_given` is retained as an auditable annotation and may inform rendering
copy, never arithmetic. Coverage (existing `daily.coverage`, plus
`coverage_pct` below) is the one accuracy-adjacent quantity computable
honestly from the record's own data with zero borrowed literature, and it is
prioritised over any imported figure.

### 4.1 Comparability is earned by overlap, never asserted

New dataset `comparability.jsonl` (policy semantics), the #33 machinery:

| field | type | null | vocabulary |
|---|---|---|---|
| `date` | ISO date | no | effective-from |
| `field` | string | no | dataset column |
| `system_a`, `system_b` | string | no | instrument slugs |
| `status` | string | no | `comparable \| offset \| not-comparable` |
| `bias` | number | yes (required when status = offset) | the measured cross-instrument offset |
| `spread` | number | yes | dispersion of the paired differences |
| `basis` | string | no | `overlap` (the only legal value) |
| `overlap_ref` | string | no | claim ids or an interval of simultaneous dual recording |

Default with no row: NOT comparable (#33's acceptance criterion). `status`
other than `not-comparable` REQUIRES overlap evidence: simultaneous dual
recording is the only route to a comparability declaration (the
dual-recording norm; a record can produce precision and bias separated
empirically on the athlete's own data this way, with zero borrowed
literature). Cross-instrument bias is PERMANENT: it does not average out
over any window, and smoothing across a seam launders it into a plausible
trend - so the seam machinery ships alongside the weight trend filter, never
instead of it.

Failure modes stated: (a) borrowed literature figures are population-level and
device-generation-specific; `basis`/`basis_ref` make that auditable, and the
render layer must not present a `judgement`-based u as a datasheet one
(loadline I-rule); (b) condition-scoped rows require the OBSERVATION to know
its condition, which sessions mostly do not record: an observation matching no
condition row falls back to the unconditional row or to null, never to the
nearest condition.

## 5. Qualifications dataset (#168)

Blocked on row identity (#169/#170 convergence); schema reserved now so the
design does not drift:

`qualifications.jsonl`: `date`, `targets` (list of claim ids), `scope` (list of
fields, null = whole row), `kind` (`interpretive | doubt`), `text` (the
athlete's words), `effect` (`annotate | demote`; `demote` legal only with
`kind = doubt`), `recorded_at`. Semantics fixed by #168 as rewritten:
interpretive never changes a computed value; doubt-demote inserts a
per-observation edge (this claim below every other witness for the scoped
fields) into the partial order, visible as a ranking outcome. Suppression is a
label, never a deletion.

## 6. Small vocabulary additions (FHIR cribs, reserved)

| field | vocab | where | why |
|---|---|---|---|
| `absent_reason` | `not-performed \| unable-to-obtain \| unknown` | daily/coverage territory (#93, #146) | FHIR dataAbsentReason: structured null-with-reason; distinguishes active silence from passive |
| `record_status` | `preliminary \| final \| amended \| entered-in-error` | all observation datasets, default `final` | FHIR Observation.status; `entered-in-error` is the label form of suppression-not-deletion (#143). Additive, no reader required to consume it in v1. |

Both are gen-3, nullable, validated as closed vocab. Specced here so #93/#146
work slots in without rework; no engine consumer in this roadmap.

### 6.1 Per-row additions from shipped designs (stream 2)

| field | type | null | per | source design | why |
|---|---|---|---|---|---|
| `algo_version` | string | yes | observation rows | Apple `HKSourceRevision.version`, Oura `sleep_algorithm_version` | the ONLY defence against a vendor silently changing what a field means; without it an algorithm change is indistinguishable from a real change (#33 applied to software). One string, gen-3. |
| `coverage_pct` | number 0-100 | yes | sessions (daily already has `coverage`) | WHOOP `percent_recorded` / `total_no_data_time_milli` | self-computable quality; prioritised over borrowed figures |
| `client_record_id` | string | yes | observation rows | Apple SyncIdentifier / Health Connect clientRecordId | writer-scoped identity: the shipped answer to same-source intraday revisions, feeding the #169 identity primitive |
| `client_record_version` | integer | yes | observation rows | SyncVersion / clientRecordVersion | monotonic per `client_record_id`; a higher version supersedes without a `supersedes` line |

Alignment notes, no new fields needed:

- Health Connect `recordingMethod` (ACTIVELY_RECORDED / AUTOMATICALLY_RECORDED
  / MANUAL_ENTRY / UNKNOWN) is the existing `capture` axis with UNKNOWN
  first-class; the capture classes of section 1.2 map onto it (measurement ~
  automatically/actively recorded, testimony ~ manual entry). Cited in
  `capture.toml` as shipped precedent.
- Health Connect `DEVICE_TYPE_*` (15-value closed enum) is the existing
  `sources.toml` kinds axis; reconcile the kind list against it and add a
  gym-console value where missing.
- Where derivation kinds form a small closed set, encode the derivation in
  the FIELD NAME (the TrainingPeaks `hrTSS`/`rTSS`/`TSS` pattern): the only
  provenance mechanism that survives a UI, an export, a screenshot and a
  conversation. Complements `derived_from`, never replaces it.

## 7. Protocol: `sosa:usedProcedure` as a field

The distinguishing feature of a well-anchored measurement is that it names its
conditions. This extends the EXISTING anchor concept (`resolution.py`
`QUANTITY_CLASS = "anchor"` for weight/measurements; G24/G36 anchor-audit
loop): a protocol-anchored measurement is an anchor, and the span between
anchors under no protocol is an unanchored interval (section 8).

| field | type | null | vocabulary | per | validation |
|---|---|---|---|---|---|
| `protocol` | string | yes | lowercase-kebab slug | observation (weight, measurements; extendable) | slug shape only; unknown slugs legal (open registry) |

Definition of each slug lives in `protocols.jsonl` (policy dataset, optional):
`date` (effective), `slug`, `text` (the procedure in the athlete's words),
`supersedes`. A slug used before being defined is legal; validate advises.

Epistemic rule, load-bearing: a row with NO protocol is a different epistemic
class from one with a protocol, not a row with a missing optional field. The
unprotocolled row carries the measurand's FULL definitional uncertainty
(VIM 2.27), which for body mass dominates instrument error; the protocolled
row does not. Two consequences:

- capability rows (section 4) may scope `condition` to a protocol slug: the
  protocol IS the specified condition of a precision figure (VIM 2.15 note 2
  unified with ssn `Condition`; ISCD's facility-specific precision studies
  are the same principle).
- comparability: two rows under DIFFERENT protocols (or one with, one
  without) are not two samples of one series. A rate or trend across a
  protocol change carries a seam flag: the #33 calibration-seam argument
  applied to protocol rather than instrument.

Failure mode: protocol proliferation (a new slug per whim) fragments series
into incomparable shards. Mitigated: seam flags are advisory on protocol
changes (review), refusing only when the athlete declared the protocols
non-comparable; and `protocols.jsonl` makes slugs enumerable so validate can
report the count.

## 8. Regimes: honest sustained error over an interval

A new first-class concept, distinct from #168. #168 is a per-observation
qualification (one suspect reading). A regime is a bounded INTERVAL during
which a whole class of claims was unanchored - an ill-defined measurand
honestly restated - ending at a discoverable instant, typically the first
protocol-anchored measurement. High trust, low accuracy, sustained: the
empirical proof that the two axes are separate.

New dataset `regimes.jsonl` (policy semantics, append-only):

| field | type | null | vocabulary | notes |
|---|---|---|---|---|
| `date` | ISO date | no | | declaration date (when discovered) - P2: the record can reconstruct what was believed before the discovery |
| `from_date` | ISO date | no | | interval start (inclusive) |
| `to_date` | ISO date | no | | interval end (inclusive); >= from_date |
| `dataset` | string | no | resolved dataset name | scope |
| `field` | string | no | a column of that dataset | scope |
| `kind` | string | no | `unanchored` (closed vocab, one value for now) | |
| `source` | string | yes | | optionally narrows to one source's claims |
| `text` | string | no | free text | the athlete's own account |
| `anchored_by` | string | yes | claim id or protocol slug | what ended the regime |
| `recorded_at`, `supersedes` | as elsewhere | | | standard machinery |

Semantics (INVALIDATES WITHOUT REPLACING - the easy-to-get-wrong part):

1. Claims inside the interval matching the scope are labelled
   `superseded_by_regime` (label, NEVER deleted; they stay in `claims`).
2. The affected days' resolved values are EMPTY (null, outcome `unanchored`).
   The anchoring measurement is evidence that the earlier claims were
   unanchored, NOT evidence of what the true values were. No backfill, ever.
   "A blank beats a confident wrong number", applied to an interval.
3. HARD CONSTRAINT, trust invariance: applying a regime touches no trust,
   credibility, or dominance parameter of the athlete or any source.
   Discovering your own error must never cost you trust - trust is about
   intent and care, accuracy is about the number, and self-correction is
   evidence of care. The engine has no learned trust parameter (by design,
   see 02-engine section 9), and this rule keeps it that way: a regime is
   data about an interval of claims, not about a reporter. Tested
   byte-identically (03-tests section 9).

Boundaries are DECLARED first, detected second: the athlete usually knows
when the protocol started or the device changed, and a declared boundary
needs no statistics. Changepoint detection (CUSUM, Page 1954; PELT, Killick
et al. 2012) is an optional later audit, not built now.

## 9. Expected-variation registry (restatement-run detector input)

`semantics/variation.toml` (engine registry, versioned):

```toml
version = 1
[variation.weight.kg]
min_spread_abs = 0.2     # a value this constant across a window is suspect
window_days = 5
note = "day-to-day body-mass fluctuation makes an exactly constant series evidence of restatement rather than observation"
```

Open registry: fields absent here are never checked (the deny-list direction
`cannot_observe` already uses: an omission accuses nobody). Feeds the
constant-value detector in 02-engine; output is ADVISORY only.

## 10. The `accuracy` ban

Verified: no field named `accuracy` exists anywhere in `src/`. The retirement
path is therefore a prevention rule, which is cheaper than G89 retirement:

- `validate_record` rejects a key literally named `accuracy` on any dataset
  with: `'accuracy' is not a quantity (VIM 2.13): state a standard
  uncertainty 'u' with 'u_given_as', a 'bias', or a 'resolution_step' in
  capabilities.jsonl`.
- Should external content ever ship an `accuracy` field, G89 applies in full:
  successor = the capability triple, one canonicaliser mapping the float to
  `u_given` + `u_given_as = "limits"` (the conservative reading), every reader
  prefers the successor.
