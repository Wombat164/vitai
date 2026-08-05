# Engine changes, module by module

Stdlib only throughout (`math`, `statistics`, `itertools`). Each section states
what is trivial, what needs data the project does not have, and the failure
mode. Nothing below changes `clocks.py` logic: the record is bitemporal
(Snodgrass) and stays so; `start_time`/`measured_at` are phenomenon time, i.e.
valid time at instant granularity, NOT a third clock. The only genuine third
instant (decided vs recorded vs effective) applies to ASSERTIONS (goals,
thresholds, capabilities) and is already carried by `date` + `recorded_at` +
policy semantics; document it in `docs/model.md` as a deliberate local
extension and never call the record tri-temporal.

## 1. `config.py`: partial-order canonicaliser

| change | detail |
|---|---|
| new | `resolution_edges(field) -> frozenset[tuple[str, str]]`: reads `[resolution].edges` + per-field; canonicalises legacy `source_order` lists to chain edges. The ONLY reader of `source_order` (G89 part two). |
| new | load-time cycle check over transitive closure (DFS, stdlib): a cycle refuses the build naming the cycle. |
| trivial | yes; ~40 lines. |
| failure mode | transitive closure cost is O(V^2) worst case; source-name count is tens, irrelevant. |

## 2. `resolution.py`: dominance instead of `_rank`

| change | detail |
|---|---|
| replace | `_rank` index lookup with `_dominates(a, b, edges) -> bool` (path existence in precomputed closure). |
| winner selection | per field: (0) COMPETENCE FILTER, before availability is even tested: a claim whose system's capability row declares `competence: absent` for the field is excluded from the witness set with an explanation (per-instrument refinement of the existing kind-level `cannot_observe` deny list, reusing its accuse-nobody default: no capability row = no exclusion). This is the guard against the presence-is-not-quality failure, named in the wild: intervals.icu uses any existing stream "valid data or not", so a garbage stream beats a clean one by mere presence; (1) collapse same-source claims by capture-restatements then recency exactly as today (a correction is not a conflict); (2) apply CAPTURE-DOM (measurement class beats testimony class, `01-schema.md` 1.2); (3) among survivors, a claim dominated by another drops; (4) one survivor: `resolved`; several with equal values: `resolved` (agreement, witnesses counted); several with `_disagrees` values: **`tie`** - canonical field = null, tripwire `unresolved_tie` listing every (source, value), explanation row with `outcome: "tie"`. |
| unranked source | quarantine as "no opinion" (tie), never auto-rank. The two shipped policies are both arbitrary orderings masquerading as policy: one incumbent promotes a new source to the top, this engine's legacy `_rank` drops it to alphabetical last. The tie outcome with its repair-path tripwire replaces both. |
| coverage announcement | `validate`/report prints which datasets RESOLVE (`RESOLVED_DATASETS`) and which pass through untouched. Lesson from Health Connect's partial dedup (Activity and Sleep only; everything else summed across apps unconditionally, so two writers double a quantity): a partial resolution policy that does not announce its own coverage is more dangerous than none. One string, computed from constants. |
| determinism | null is order-independent. Property test in `03-tests.md`: permuting input rows never changes any output row. |
| `_why` | extended: `"neither dominates: no edge between X and Y; add one under [resolution].edges"`. |
| `_unattributed_losses` | KEPT, reconciled with #167 (see 04): an unattributed row losing stays a review tripwire (a missing stamp is a writer omission); an ATTRIBUTED testimony claim losing to a measurement-class claim is the correct outcome and trips nothing. The two rules key on different predicates and do not conflict. |
| effort | 1-2 days including tests; the merge loop shape survives. |
| failure mode | tie-null starves a downstream consumer that assumed a value. That is the point (blank beats confident wrong number), and the tripwire is the repair path. |

## 3. New module `uncertainty.py`

The only new module. All stdlib-trivial. Public functions:

```python
RECT, TRI = sqrt(3.0), sqrt(6.0)
DIVISOR = {"standard": 1.0, "expanded_k2": 2.0, "ci95": 1.960,
           "ci99": 2.576, "limits": RECT, "triangular": TRI}

def standard_u(given: float, given_as: str) -> float:
    """GUM Type B conversion. display_step: u = 0.29 * dx (GUM F.2.2.1)."""

def combine(terms: list[tuple[float, float]]) -> float:
    """Quadrature with sensitivity coefficients: sqrt(sum (c_i*u_i)^2).
    Valid ONLY over independent inputs; callers establish independence via
    provenance.shares_ancestor. 'Re-derivation amplifies error' is not a rule:
    c_i = df/dx_i may be < 1. The invariant that DOES hold: the result is
    >= every single contribution |c_i|*u_i, so a derivation never removes
    its inputs' uncertainty."""

def fuse(us: list[float], independent: bool) -> float:
    """Two witnesses of one quantity. independent=True: inverse-variance,
    u = 1/sqrt(sum 1/u_i^2) (may beat the best input). independent=False or
    unestablished: covariance-intersection posture (#94, Julier/Uhlmann 1997)
    degraded to its qualitative rule: u = min(us) - combined confidence never
    exceeds the best single source. Never overconfident by construction."""

def discount(u: float | None, untrusted_hops: int, hop_u: float) -> float | None:
    """Subjective-logic discounting SHAPE (Josang 2016): an unreliable hop
    moves mass into UNCERTAINTY - it widens u, it never flips or demotes the
    value. hop_u is a per-hop Type B judgement term, quadrature-added."""
```

`discount` needs a per-hop `hop_u` figure the project does not have: NOT
DELIVERABLE as a default until the pending error-magnitudes stream lands or a
`judgement`-basis capability row supplies one. Ship the function; wire nothing
to it by default; `trust_ceiling`'s ordinal stays the shipped behaviour.

GUM 5.2.4 shared-influence restructuring is a MODELLING rule, not code: a
shared influence (one device behind two series, a body-mass parameter inside a
vendor calorie model) becomes an explicit input named in `derived_from`, so
leaves are independent and `combine` becomes valid. Enforced by the incest
check below, documented in the module docstring.

## 4. `provenance.py`: ancestry and citations

| change | detail |
|---|---|
| new | `ancestors(rec, index) -> set[str]`: origin plus transitive `derived_from` closure (index: claim_id -> rec, built in resolve()). Cycle-guarded. |
| new | `shares_ancestor(a, b, index) -> bool`: supersedes `shares_origin` for corroboration decisions (shares_origin kept as the no-lineage fast path). This is data-incest detection: two inputs meeting at a fusion point with a common ancestor are one observation re-entering by two paths. |
| wire | `independent_witnesses` / `is_independent`: a claim with `derived_from` NEVER corroborates any claim in its ancestor closure (#170: agreement by construction is not evidence). |
| new (cheap steal, Dong et al. 2010) | `relay_signature(a, b, field) -> bool`: shared improbable formatting (identical decimal-string beyond plausible independent rounding, e.g. both "2.226") as relay EVIDENCE feeding a `review` tripwire for #169. Deterministic string comparison; evidence only, never a merge decision. |
| citations | module docstring: the origin-divergence rule is Dong, Berti-Equille, Srivastava PVLDB 2009 (DOI 10.14778/1687627.1687690), derived here empirically; CI posture Julier/Uhlmann 1997; trust/accuracy split Wang & Strong 1996, ISO/IEC 25012, W3C DQV. Cite, no discovery claim. |
| NOT built | the Bayesian dependence estimator (declared lineage already exists; inferring a possessed fact is strictly worse); any truth-discovery reliability learning (below the ~4-8 conflicting-values-per-item floor every method underperforms random: Waguih & Berti-Equille arXiv:1409.6428). |

## 5. `resolution.py` (second pass): staleness cascade

Reuse the `retractions` shape: an input named in some row's `derived_from`
that is superseded or retracted yields a `stale_derivation` tripwire naming
the dependant. Declared lineage suffices for detection (semiring provenance);
no re-execution. ~30 lines beside the existing cascade loop.

## 5b. `resolution.py` (third pass): regimes and the restatement-run detector

| change | detail |
|---|---|
| regime application | after merge, before canonical output: a claim whose (dataset, date, field[, source]) falls inside a `regimes.jsonl` interval is labelled `superseded_by_regime` in `claims`; the resolved field for those days is null with outcome `unanchored`. NEVER backfilled from the anchoring measurement: the anchor proves the interval was unanchored, not what its values were. Applies the same as-of discipline as policy datasets: a build "as of" a date before the regime's declaration `date` reproduces the pre-discovery view (P2). |
| trust invariance | applying a regime reads no trust input and writes no trust output. Mechanically checkable because trust surfaces are enumerable: dominance edges (config), capture classes (registry), `trust_ceiling` (per-claim function of path/capture). Test: resolve() over claims OUTSIDE the interval is byte-identical with and without the regime row (03-tests 9). This encodes the rule that self-correction must never lower the reporter's standing: a regime is data about an interval of claims, not about a source. |
| protocol seam | a rate/trend whose window spans a protocol change (different `protocol` values, or protocolled vs not) gains a `protocol_seam` tripwire, severity review - the #33 seam shape, protocol instead of instrument. Weight-rate consumes it like the #37 timing check: report the number, refuse the verdict word only if the athlete declared the protocols non-comparable. |
| algorithm seam | same machinery keyed on `algo_version`: a series whose window spans an `algo_version` change on one source gains an `algorithm_seam` tripwire (review). A vendor changing what a field means is indistinguishable from a real change without this. |
| instrument seam + overlap calibration | new function `overlap_calibration(rows_a, rows_b, key) -> {n, median_offset, spread}` (stdlib `statistics`): paired same-day/same-activity values from two systems during a dual-recording window; output is the evidence a `comparability.jsonl` row cites. A rate across two systems with no `comparable`/`offset` row REFUSES with the seam named (#33's acceptance criterion). Cross-instrument bias is permanent - it does not average out - so this refusal never relaxes with window length, unlike the dispersion refusals. |
| constant-value detector | new function `restatement_runs(rows, registry)` (stdlib, ~40 lines): for each field in `semantics/variation.toml`, scan date-ordered resolved values; a run of identical values spanning >= `window_days` in a quantity expected to vary by >= `min_spread_abs` yields an ADVISORY tripwire `constant_value_run` naming the run's first and last date (the suspected regime boundaries) and suggesting a `regimes.jsonl` declaration. Extends the EXISTING restatement concept (capture.toml `restatements` ranks what the record SAYS about acquisition; this detects the same phenomenon from value SHAPE when the record says nothing) - one concept, two evidence routes, cross-referenced in both docstrings. Never a hard error: some true series are genuinely flat. |

## 6. `verdicts.py`: interval, guard band, two gates

Gated on phase 0 (see thresholds in `00-phase0-experiment.md`). Shipped form:

| piece | detail |
|---|---|
| MDC from own replicates | `mdc95 = 2.77 * sem`, `sem` = pooled within-week SD of weight readings (the phase-0 pooled_sd; SD*sqrt(1-ICC) reduces to this when the replicate design is within-week repeats). Clinical MDC literature = Bland-Altman repeatability coefficient = ISO 5725-6 r = 2.8*sigma_r; one statistic, three names, documented once. Stdlib `statistics`. |
| guard band (JCGM 106) | acceptance interval = decision band shrunk by `K95 * u_rate` at each edge (guarded acceptance). A rate inside the band but within the guard zone renders ON with a stated conformance caveat instead of a bare word; naive threshold comparison runs up to 50 % error at the threshold, which is the number that justifies the machinery. |
| two gates, two messages | gate 1 DETECTABLE: is \|rate\| < MDC-derived rate noise? Verdict payload gains `detectable: false` ("could be measurement noise"). Gate 2 WORTHWHILE: the athlete's own declared band/target IS the MIC anchor (no population SWC needed, which the n=1 record cannot supply). Distinct messages; a change can be detectable and not worthwhile, or worthwhile-sized but undetectable, and the second must refuse. |
| vocabulary | one new verdict word `undecidable` (interval spans the whole band). Closed-vocab addition = read-model contract bump (CONTRACT_VERSION in db.py). `no_data` keeps meaning "nothing to compute from"; `undecidable` means "computed, and the instrument cannot support a verdict" - the I5-style distinction between an empty record and a refusing one. **PREREQUISITE, #177 (contract 18, ahead of this): `no_data` already carried FOUR states, separable only by inspecting which fields were null (input missing / no policy configured / measurement cannot support a judgement), plus a fifth that removed the row entirely. A `reason` column now answers "why not" while the verdict word answers "can a judgement be rendered", which is one question with one answer. The word below is the coarse half; the reason is the half that stops cases seven and eight from repeating this. Suppression also stops being an absence: a removed row and an uncomputed metric were different facts rendered identically.** |
| refusal payload shape (WHOOP `score_state` precedent: SCORED / PENDING_SCORE / UNSCORABLE) | copy both structural choices: the refusal CARRIES A REASON, and the judged value is ABSENT from the verdict row rather than present-with-a-warning - a dimmed number still gets read, screenshotted and compared. Applied at the VERDICT layer only: the rate stays fully available on the value/chart surfaces. This deliberately AMENDS the #37 honest-pair shape (value + NODATA in one row) for `undecidable` rows, with the rationale recorded; existing timing-NODATA rows migrate in the same contract bump so the payload has one refusal shape, not two. |
| per-field refusal policy | seeded from the phase-0 expected-outcome table: kcal_out at day resolution is never scored against a target (ordinal within one source only); body-fat-percent levels are never scored; steps/sleep verdict machinery operates at trend windows only. Encoded as data (which metrics the interval machinery covers), not scattered conditionals. |
| untouched | pain_gate, symptom rows, safety floors (G68): safety fires on points, never refuses on uncertainty; a floor breach with wide u still fires (costly side). |
| per-field scope (stream 2 settled it) | weight_rate and rhr ship first (own-record Type A). Steps and sleep: trend windows only. kcal_out at day resolution and body-fat-percent levels: never scored, encoded as policy data, not conditionals. Intake floors keep firing on points (safety, above). |

## 6a. New module `emissions.py`: retraction reaches the consequences

The largest single architectural item in this proposal (06-roadmap sizes it):
the first requirement that needs the engine to remember its own outputs.

| piece | detail |
|---|---|
| `api.assert_delivery(rows, surface)` | appends one `emissions.jsonl` row per delivered judgement (01-schema 8b). Called by the surfacing path at delivery, NEVER by build: build stays a pure function of the record, and the event being recorded is "this was asserted to the athlete", which is an observation, not a computation. |
| THE DIRECTIONAL RULE (the core) | Do not backfill the OBSERVATION; DO recompute the CONSEQUENCE - split by direction because they behave oppositely. **Forward-looking** outputs (required rate to a deadline, next-step plan, revised threshold): computable from the current anchor alone; recompute from current best knowledge; an emptied interval never blocks them. **Backward-looking** outputs (progress to date, attainment so far, did-last-week-hit): NOT computable over an emptied interval; REFUSE with reason `unanchored_basis`, using the refusal machinery of section 6 (word + reason, no number at the verdict surface). Silently spanning the gap is the forbidden third behaviour. |
| where the split lives | each computed output kind is classified `forward \| backward` in one table in `emissions.py` (data, not scattered conditionals), consumed by verdicts/report/plan surfaces. |
| `basis_retracted` join | read-model view over `emissions` x current claim status: an emission whose `basis_claims` intersect regime-superseded or retracted claims is flagged. Label, never delete - the row is untouched; the flag is derived. |
| counterfactual audit `warning_backtest()` | for each `kind: warning` emission with `basis_retracted`: recompute the trigger under current knowledge; output `{fired: N, would_still_fire: M}` plus per-warning rows. This EXTENDS the existing anchor-audit backtest concept (G24/G36 anchor-audits-source loop) with a retraction trigger, rather than inventing a parallel mechanism - same loop, new entry point. A warning that would still fire is reassurance; one that would not is the concrete harm the athlete should hear about. |
| MATERIALITY GATE (reuses phase 0) | `material(old, new, boundaries) -> bool`: a recomputed consequence is surfaced only when the change CROSSES A DECISION BOUNDARY (verdict word flips, a threshold or feasibility bound is crossed), not whenever the number moves. This is the guard-band predicate from `00-phase0-experiment.md` reused verbatim - the same "is this distinguishable across a boundary" test serving refusal and surfacing both, which is a point in its favour: one predicate, one set of thresholds, no second calibration to drift. Sub-boundary deltas land in the audit trail only. Alarm-fatigue rationale per loadline I2. |
| #148 dependency (HARD) | answering "does an emission still hold" requires recomputing what the engine said THEN, which needs policy-as-of, not only data-as-of. Week-Monday policy already exists for goals/thresholds (G14/G20 in verdicts.py); the gap is everything else: vitai.toml overlay values, resolution edges, registries (G31 territory). `emissions.policy_asof` records the date; #148 makes it replayable. PREREQUISITE, promoted in 06-roadmap. |
| effort | week-plus: new dataset + API surface + directional classification of every output kind + backtest + gate. Honest sizing in 06-roadmap. |
| failure mode | unlogged surfacing (a consumer skips `assert_delivery`): that assertion is invisible to retraction. Accepted residual risk (01-schema 8b) - logging computation instead would record the wrong event; the bundled client is bound by rule (loadline I50 family), third parties by documentation. |

## 6b. Report layer: the render-only envelope (I45 hook)

The client never recomputes (loadline I22), so the chart envelope across
unanchored/unmeasured spans is EMITTED by the engine, in the report/query
layer only:

| piece | detail |
|---|---|
| new function | `report.chart_envelope(series, field, registry) -> list[dict]`: for each gap or unanchored span between anchored points, emit `{from_date, to_date, state, lo, hi}` where the band grows with gap length from `semantics/variation.toml` (`min_spread_abs` per day, capped; exact growth law documented as an assumption, not physiology). Segment `state` is one of `measured \| unanchored \| never_recorded \| superseded` (the loadline I46 four-state vocabulary, computed from resolution outcomes + regimes + claims labels). |
| firewall (P4) | envelope rows live ONLY in the chart payload. They never enter verdicts, rollups, canonical datasets, or any export surface. Enforced structurally: `chart_envelope` is called by the chart query alone and its output shape (`state` key present, no `source`) fails observation-schema validation by construction. |
| exports | every machine-readable egress emits recorded rows + explicit nulls only; no interpolated coordinate. One test per export path (03-tests). |
| effort | afternoon. |
| failure mode | the band growth law is invented (no published per-measurand random-walk figure). Mitigated: stated as an assumption in the docstring, parameterised by the registry, and render-only so a wrong width misleads a chart, never a number. Stream 2 may supply real figures. |

## 7. `meals.py`: label the algebra, change nothing

`meal_total` sums lo/hi additively: that is interval arithmetic (worst-case
bounds), the correct conservative algebra for BOUNDS, and deliberately not RSS.
The F7c contradiction is real only if these bounds are ever treated as
standard uncertainties. Fix is labelling, not arithmetic:

- `meal_total` output gains `"algebra": "interval-worst-case"`.
- Module docstring states the assumption (perfect positive correlation across
  items is the conservative direction for intake) and the rule: RSS applies
  only to independent standard uncertainties, never to declared bounds; a
  future fusion consumer must convert (`limits` -> u via /sqrt(3)) per item
  BEFORE combining, using `uncertainty.standard_u`.

## 8. `schema.py`

- New keys registered gen-3 in `KEY_GENERATION` (`derived_from`, `derived_op`,
  `absent_reason`, `record_status`).
- `capabilities` dataset keys + validators (`u_given_as` vocab; `u` refused if
  hand-written without `u_given`; identity key present; `lo<=hi` style checks
  where applicable).
- The `accuracy` key ban (01-schema section 7).
- `capture.toml`: `class` key on every entry + `derived_external` entry.

## 9. Explicitly NOT deliverable / NOT built (summary)

| item | why | what would change it |
|---|---|---|
| default per-hop discounting figures | no honest hop_u exists; stream 2 confirmed vendors publish nothing usable | per-record judgement capability rows only, athlete-authored |
| imported accuracy CLAIMS as numeric error parameters | stream 2 reversal: a borrowed datasheet or validation-study figure never enters arithmetic (01-schema s4) | nothing. Three routes are already admitted and are not imports: own replicates, own overlap windows, and a per-reading figure the source reports with the reading (`u_obs`). Definitional constants (`resolution_step`, `definitional_u`) are not accuracy figures. Reworded 2026-08-05, #264 |
| condition-scoped capability matching for sessions | **Settled 2026-08-02, not merely deferred (01-schema s4b).** For conditions this record can legally know, condition-scoping and instrument identity are the SAME distinction, and instrument identity is already an axis: an indoor-rower distance is a different `system` with `competence: proxy`, not a condition on a GPS row. Strip those out and what remains (canopy, urban canyon) must be INFERRED, which P4 bars. The legal cells and the useful cells are disjoint. Checked against the record: every trackpoint carries position, elevation and time only, though the file format has offered fix type, satellite count and dilution of precision for two decades. | do NOT wire `setting` to `condition`. `setting` is an instrument-mode fact and belongs on `system`. `conditions.jsonl` stays empty behind its legality gate: a condition value must be a total function of literal source values, and a predicate over a number is inference wearing a lookup's clothes, which the validator rejects. |
| population SWC / MIC | n=1 record has no between-subject SD | not needed: the declared target band is the anchor; external anchors only if the athlete declares none |
| truth-discovery reliability learning | sparse regime: worse than random below 4-8 conflicting values per item | nothing; recorded as a standing decision in 06-roadmap |
| trust learning of any kind | trust is per-observation-revisable and must stay DECLARED (edges + qualifications); the record cannot supply asymptotic rated interactions | nothing foreseeable |
| re-executable derivations | declared lineage suffices for staleness detection | only if drift CORRECTION is ever wanted, which P4 discourages |
