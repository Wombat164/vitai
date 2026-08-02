# Validation tests

All fixtures synthetic. Naming follows the existing suite (`tests/test_*.py`).
Each row: test, fixture shape, assertion. Property tests use seeded
`random.Random` loops (stdlib; no hypothesis, zero-dep rule).

## 1. Partial-order resolution (`test_resolution.py` additions)

| test | fixture | assertion |
|---|---|---|
| `test_tie_is_refused_not_alphabetical` | two weight claims, same date, sources `alpha`/`beta`, values 70.0/72.0, NO edge between them | canonical `kg` is None; one `unresolved_tie` tripwire naming both (source, value) pairs; explanation `outcome == "tie"` |
| `test_tie_never_broken_by_input_order` (property) | the fixture above, input list permuted over all orderings, plus a seeded 50-case generator of 3-source ties | byte-identical resolve() output across permutations |
| `test_edge_gives_dominance` | same fixture + edge `["alpha","beta"]` | canonical 70.0; explanation reason mentions the edge |
| `test_dominance_is_transitive` | edges a>b, b>c; claims from a and c | a wins with no direct edge |
| `test_cycle_refused_at_load` | edges a>b, b>c, c>a | config load raises, message names the cycle |
| `test_legacy_source_order_unchanged` | a fixture with `source_order` list, ported from an existing passing test | identical canonical output before/after the canonicaliser change (regression: legacy totality preserved) |
| `test_iia_edge_is_context_free` | contest A vs B resolved; add unrelated claim C from a third source | winner between A and B unchanged (independence of irrelevant alternatives) |
| `test_same_source_correction_is_not_a_tie` | two claims from ONE source, later `recorded_at` differs | later wins as today; no tie, no tripwire |

## 2. Capture-class dominance (#167 semantics)

| test | fixture | assertion |
|---|---|---|
| `test_measurement_beats_testimony_regardless_of_edges` | daily kcal_out: `narrative` capture claim vs `connector` capture claim, edge favouring the narrative SOURCE | connector value wins; explanation reason names capture class |
| `test_testimony_wins_when_alone` | reps-style field with only a narrative claim, a device claim present for a DIFFERENT field same date | narrative value canonical for its field (availability is per-field; the #167 trap test, now trivially true) |
| `test_two_utterance_minimal_pair` | identical narrative claim in two fixtures, one with a device row for the same field/date, one without | opposite winners; the fallback win's explanation is marked (visible as class-decided) |
| `test_attributed_testimony_loss_is_not_a_tripwire` | narrative source stamped, loses to device | no `unattributed_claim_lost` tripwire (the #73 reconciliation) |
| `test_unattributed_loss_still_trips` | claim with `source: null` loses | `unattributed_claim_lost` fires (regression, #73 preserved) |

## 2b. Competence, comparability, seams (stream 2)

| test | fixture | assertion |
|---|---|---|
| `test_competence_absent_filters_before_availability` | two claims for one field: source X (capability `competence: absent` for that field) with a value, source Y ranked BELOW X with a value | Y wins; X excluded with an explanation (presence is not quality; the garbage-stream-beats-clean-stream case) |
| `test_no_capability_row_accuses_nobody` | same shape, no capability row for X | X competes normally (deny-list direction preserved) |
| `test_proxy_requires_construct_note` | capability row `competence: proxy`, no `construct_note` | validate flags it |
| `test_borrowed_u_never_canonicalised` | capability row `basis: datasheet`, `u_given: 2.0`, `u_given_as: limits` | `u` stays null; annotation retained |
| `test_own_replicates_u_canonicalised` | same but `basis: own-replicates` | `u` computed (1.1547 for limits 2.0) |
| `test_cross_instrument_rate_refuses_without_comparability` | weight rows from two systems, no comparability row | rate output refuses naming the seam; adding `status: offset` + `bias` + overlap_ref unblocks with the offset rendered |
| `test_comparability_requires_overlap_evidence` | comparability row `status: comparable`, no `overlap_ref` | validate flags it |
| `test_overlap_calibration_pairs` | two synthetic paired series with a known 0.5 offset | `median_offset` == 0.5 within tolerance; `n` == pair count |
| `test_algorithm_seam` | one source's series with `algo_version` changing mid-window | `algorithm_seam` tripwire on the spanning trend; none within either half |
| `test_verdict_refusal_payload_shape` | an `undecidable` week | verdict row carries `reason`, carries NO value; the value remains present in the chart/value query for the same week |
| `test_resolution_coverage_announced` | any build | report names exactly the RESOLVED_DATASETS as resolving and the rest as pass-through |

## 3. Uncertainty module (`test_uncertainty.py`, new)

| test | fixture | assertion |
|---|---|---|
| `test_type_b_conversion_table` | table-driven: (100, standard)->100; (100, expanded_k2)->50; (98, ci95)->50.0; (128.8, ci99)->50.0; (1.732050, limits)->1.0 (a/sqrt(3)); (2.449489, triangular)->1.0; display_step dx=1.0 -> 0.29 | each equals expected within 1e-6 |
| `test_combine_sensitivity_below_one_shrinks` | one input u=1.0, c=0.1 | result 0.1 < input u ("re-derivation amplifies" refuted as a rule) |
| `test_combine_never_removes_uncertainty` (property) | seeded random (c_i, u_i) sets | result >= max(\|c_i\|*u_i) for every i; adding a term never decreases the result |
| `test_correlated_inputs_naive_quadrature_underreports` | two inputs u=1.0 each, KNOWN to share an ancestor (correlation 1). True u of the sum = 2.0; naive quadrature says 1.414 | `fuse(..., independent=False)` returns >= 1.0 (min rule, never below best single); assert naive quadrature (1.414) < true worst case (2.0) is demonstrated in the test body as the documented motivation, and the engine path with `shares_ancestor` True never calls the naive branch |
| `test_fuse_independent_beats_best` | u=[1.0, 1.0], independent | 0.7071 (inverse-variance) |
| `test_fuse_unestablished_is_min` | u=[1.0, 3.0], not independent | exactly 1.0, never less |
| `test_discount_monotone` (property) | seeded u, hops 0..5 | u non-decreasing in hop count; value untouched |

## 4. Data incest (`test_provenance.py` additions)

| test | fixture | assertion |
|---|---|---|
| `test_derived_value_does_not_corroborate_inputs` | session A (device origin `sensor-x`); claim B with `derived_from: [A]`, different source name | `independent_witnesses([A, B]) == 1`; `shares_ancestor(A, B)` True |
| `test_diamond_incest` | origin O; A derived_from O-row, B derived_from O-row via different intermediate rows; fuse A with B | `shares_ancestor(A, B)` True (common ancestor two hops up); witnesses == 1 |
| `test_four_artifact_one_witness` (#94's own test) | four claims, captures narrative/manual_entry/photo/receipt-like, all `origin: athlete` | witnesses == 1 |
| `test_stale_derivation_flag` | input row superseded; dependant names it in `derived_from` | one `stale_derivation` tripwire naming the dependant |
| `test_relay_signature_formatting` | two claims value "2.226" (identical improbable decimals), vs a pair 2.226/2.23 | first pair flagged as relay evidence (review), second not |
| `test_derived_from_cycle_guard` | A derived_from B, B derived_from A (corrupt input) | ancestors() terminates; validate flags it |

## 5. Meals algebra (`test_meals.py` additions)

| test | fixture | assertion |
|---|---|---|
| `test_meal_total_declares_algebra` | any two priced items | `meal_total(...)["algebra"] == "interval-worst-case"` |
| `test_bounds_are_not_rss` | two items each lo/hi = 90/110 | total lo/hi = 180/220 (additive, worst-case), NOT 200 +/- 14.1; the test body documents that RSS here would require independence + standard-u conversion first |

## 6. Verdicts: refusal, guard band, two gates (`test_verdicts.py` additions)

| test | fixture | assertion |
|---|---|---|
| `test_rate_undecidable_when_interval_spans_band` | two weeks of synthetic weights, within-week SD large enough that K95*u_rate > 0.25 + \|rate - target\| | verdict `undecidable` with a `reason`, NO value in the verdict row (WHOOP score_state shape); the rate remains available via the value/chart query |
| `test_rate_verdict_survives_tight_data` | same shape, SD tiny | verdict unchanged vs current engine (regression) |
| `test_guard_band_caveat_at_threshold` | rate just inside band edge, u such that edge sits within K95*u | ON with conformance caveat payload, not bare ON |
| `test_detectable_gate` | \|rate\| < rate-MDC from pooled SD | payload `detectable: false`, message differs from the worthwhile message |
| `test_worthwhile_anchor_is_declared_band` | detectable rate smaller than band | detectable true, worthwhile false; two distinct messages |
| `test_pain_gate_never_refuses` | wide-uncertainty week + pain over gate | pain_gate row fires exactly as today |
| `test_safety_floors_ignore_uncertainty` | intake floor breach with any u | BEHIND fires (costly side; refusal machinery must not quieten safety) |
| `test_refusal_rate_regression` | a fixed 12-week synthetic record with known dispersion (seeded) | refusal count == golden value; any engine change that silently raises or lowers refusals fails here |

## 7. Schema (`test_vitai.py` / validate additions)

| test | fixture | assertion |
|---|---|---|
| `test_accuracy_key_refused` | weight row with `accuracy: 0.1` | validate names VIM 2.13 and points at capabilities |
| `test_capability_u_requires_given_as` | capability row `u_given` without `u_given_as` | flagged |
| `test_capability_unknown_is_legal` | row with `u: null`, note only | zero problems (unknown is first-class) |
| `test_derived_from_requires_derived_capture` | row with `derived_from` and `capture: connector` | flagged |
| `test_capability_effective_dating` | two rows same (system, field, condition), later date | as-of query returns the later from its date, earlier before (P2: reconstructable) |

## 8. Regimes, protocol, restatement runs (`test_regimes.py`, new)

All fixtures synthetic: "an athlete", generic values.

| test | fixture | assertion |
|---|---|---|
| `test_regime_empties_interval` | 7 daily weight claims value 80.0, source `hand-log`; regime row scoping weight.kg over those dates | each of the 7 days resolves kg = null, outcome `unanchored`; the 7 claims remain in `claims` labelled `superseded_by_regime` (label, never deleted) |
| `test_regime_never_backfills` | same + an anchored claim 79.4 with `protocol: "fasted-morning"` dated the day after the interval | no day inside the interval resolves to 79.4 or any non-null value; the anchor's own day resolves 79.4. The obvious wrong implementation, asserted against by name. |
| `test_regime_leaves_source_trust_untouched` | a record with claims inside AND outside the interval from the same source | resolve() output restricted to outside-interval dates is byte-identical with and without the regime row; no dominance edge, capture class, or trust_ceiling value differs anywhere |
| `test_regime_as_of_before_discovery` | regime declared at date D; build as-of D-1 | interval resolves as it did pre-discovery (P2 reconstructability) |
| `test_protocol_seam_flagged` | weight rows week 1 no protocol, week 2 `protocol: "fasted-morning"` | rate spanning the change carries `protocol_seam` tripwire (review); rate within either week does not |
| `test_protocolled_and_bare_are_different_class` | one row with protocol, one without, same day, same source | not merged as one witness pair for comparability purposes; explanation notes the class difference |
| `test_constant_run_advisory` | 6 consecutive days weight 80.0 (variation.toml: min_spread_abs 0.2, window 5) | one `constant_value_run` advisory naming first and last date of the run; severity advisory/review, build succeeds |
| `test_constant_run_ignores_unregistered_fields` | 6 identical rhr values with no variation entry for rhr | no advisory (open registry accuses nobody) |
| `test_true_flat_series_is_only_advisory` | flat run plus an explicit note | advisory still emitted, nothing refused, no value nulled (detector never mutates) |

## 9. Monotonicity invariants (property, seeded)

| invariant | statement checked over generated cases |
|---|---|
| refusals monotone in dispersion | scaling every within-week SD up never converts an `undecidable` into a scored verdict |
| fusion never overconfident | for any partition into dependent groups, fused u >= min input u |
| discounting monotone in path length | appending an untrusted hop never decreases u and never changes the value |
| derivation floor | combined u >= every single \|c_i\|*u_i term |
| tie stability | any permutation + any duplicate-edge addition leaves resolve() output identical |
