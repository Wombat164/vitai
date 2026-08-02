# Roadmap: sequenced, gated, sized

Effort scale: `afternoon` / `days` / `week` / `NEEDS-DATA` (blocked on data
the project does not have). Every phase names its gate. Contract bumps
(read-model vocabulary changes) are marked `[C]`.

```
P0a regimes+protocol+detector ---\
P0b phase-0 refusal count --------+--> GATE A --> P2 uncertainty machinery [C]
P1  partial-order resolution [C] -/              (scope set by GATE A)
P1b identity primitive (#169) --> P1c derived_from (#170) --> P1d qualifications (#168)
                                                          --> P1e capture-class dominance (#167)
issue hygiene (04) first, independent of everything
```

## Phase 0a: regimes, protocol, restatement detector (SHIP FIRST)

Independent of phase 0's outcome, of identity, and of the whole registry
question. Cheapest real value in the set.

| item | effort | deliverable |
|---|---|---|
| `protocol` field + `protocols.jsonl` + validation | afternoon | 01-schema s7 |
| `regimes.jsonl` + resolution application + trust-invariance test | days | 01-schema s8, 02-engine 5b, 03-tests s8 |
| `semantics/variation.toml` + `restatement_runs` detector | afternoon | 01-schema s9, 02-engine 5b |
| protocol seam tripwire | afternoon | 02-engine 5b |

Gate: none (doctrine-compliant, no numbers invented). Failure mode: regime
scoping bugs empty the wrong days; covered by the as-of and byte-identity
tests before merge.

## Phase 0b: the refusal count (00-phase0-experiment.md)

| item | effort |
|---|---|
| experiment branch patch + counting script + run over the private record | afternoon |
| write the numbers into the gate decision | hour |

**GATE A** (thresholds pre-stated in 00): decides whether phase 2 builds
interval verdicts weekly, guard-banded/two-week, or refusal-only; and whether
the capability dataset is needed for verdicts at all or only for seams (#33).

## Phase 1: partial-order resolution `[C]`

| item | effort | notes |
|---|---|---|
| `resolution_edges` canonicaliser + cycle check | afternoon | G89 three-part discipline |
| dominance merge + tie outcome + tripwire | days | determinism property tests are the cost centre |
| legacy `source_order` regression suite | afternoon | zero behaviour change for existing configs |

Independent of GATE A. Prerequisite for #167/#168 semantics. Failure mode:
tie-null starving a consumer; mitigated by the legacy-chain default.

## Phase 1b-1e: the issue ladder (order fixed in 04)

| item | effort | depends on |
|---|---|---|
| 1b identity primitive (#169): engine-level activity/row identity every importer inherits | week | nothing (design work is the cost) |
| 1c `derived_from` + ancestry + incest check + staleness flag (#170) | days | 1b |
| 1d qualifications dataset + per-observation demote edge (#168) | days | 1b, phase 1 |
| 1e capture `class` key + CAPTURE-DOM layer (#167) | afternoon | phase 1; lands WITH 1d |
| relay-formatting evidence (`relay_signature`) | afternoon | nothing; anytime |

## Phase 2: uncertainty machinery (scope set by GATE A) `[C]`

Framing from stream 2, which sizes this phase: NOBODY in the industry models
measurement error - no incumbent ships error bars, intervals or propagation.
Shipping this is a first, because it is genuinely hard rather than
overlooked. Therefore the categorical, self-computable and identity-based
mechanisms lead, and anything requiring borrowed numeric parameters is cut
(reversal recorded in 01-schema s4).

| item | effort | notes |
|---|---|---|
| capabilities dataset: competence flag + construct notes + `accuracy` ban | days | categorical payload first; u only from own data |
| `comparability.jsonl` + `overlap_calibration` + cross-instrument refusal | days | the #33 machinery; overlap is the only route |
| per-row `algo_version`, `coverage_pct`, `client_record_id`/`_version` | afternoon | cheap, shipped-design cribs; identity fields feed 1b |
| `uncertainty.py` (conversions, combine, fuse, discount) | days | stdlib-trivial; ships regardless of gate (meals/EA propagation uses it) |
| verdict interval + `undecidable` word + reason-carrying refusal payload + guard band + two gates | days | shape follows GATE A; per-field policy seeded from the 00-phase0 expected-outcome table (kcal day-level and body-fat levels never scored) |
| meals algebra label | hour | independent, anytime |
| MDC/pooled-SD plumbing | afternoon | already half-built by phase 0b |
| resolution-coverage announcement line | hour | the partial-policy-must-announce-itself lesson |
| soften the private record's `distance_km` config comment (pass-through claim is only true on clean GPS; past a threshold the platform blends silently) | minutes | private repo task; strengthens the existing ranking |

Formerly NEEDS-DATA, now resolved by stream 2: borrowed Type B seeds are NOT
coming (decisively killed: vendors publish nothing usable); per-hop discount
figures stay unwired; condition/protocol-scoped numeric values arrive only
from the record's own overlap windows and replicates, on the athlete's own
schedule.

Standing flag (no machinery fixes it): for body mass, SAMPLING BIAS (which
day the athlete chooses to step on the scale, against a daily swing several
times the instrument error) outranks every accuracy concern in that field.
The countermeasures are behavioural (protocol + routine) and the weekly-mean
trend filter; no metadata touches it. Recorded so nobody builds a field for
it.

## Standing NOT-BUILDING decisions (recorded so they are not revisited)

| item | reason | citation |
|---|---|---|
| truth-discovery / source-reliability learning (TruthFinder, Accu, LTM, CRH, Investment) | below ~4-8 distinct conflicting values per item every method underperforms random guessing; this record's dominant case is single-source fields. The hand-declared ladder is the CORRECT solution family for the sparse regime; its defect was totality, fixed in phase 1. | Waguih & Berti-Equille arXiv:1409.6428; Pasternack & Roth's metric excludes single-source facts |
| Bayesian copy detection at runtime | lineage is DECLARED in `path`/`derived_from`; inferring a possessed fact is strictly worse. Optional future audit only. | Dong, Berti-Equille, Srivastava PVLDB 2009 |
| Dempster's rule | high conflict manufactures certainty (Zadeh's counterexample), the exact opposite of the wanted behaviour; the Yager/CI posture is already adopted | |
| Beta reputation / TRAVOS / EigenTrust, any learned trust | asymptotic, need repeated rated interactions the record cannot supply; trust stays DECLARED (edges + qualifications) indefinitely | Josang 2016 for the elicited-opinion legitimacy |
| a third clock / "tri-temporal" | the record is bitemporal (Snodgrass); observation time is valid time at instant granularity (SOSA phenomenonTime, FHIR effective[x]). Assertions get decided/recorded/effective as a documented LOCAL rule. `clocks.py` unchanged. | |
| re-executable derivations | declared lineage suffices for staleness detection; recomputation is drift correction, which P4 discourages | Green/Karvounarakis/Tannen 2007 |
| a float field named `accuracy` | not a quantity | VIM 2.13 note 1 |
| conditional source ranks | violates independence of irrelevant alternatives; partial order makes the desired behaviour default semantics | Staworko/Chomicki 2012 |
| imported numeric error parameters (per-source accuracy registry) | vendors publish nothing usable (only power meters publish; figures cover the random term only and are contradicted in the field); a borrowed figure is a confident wrong number about confidence. Categorical competence + overlap-earned comparability + own-data numerics instead. | stream 2 survey (Shcherbina 2017, O'Driscoll 2020, Fuller 2020, Germini 2022) |
| silent blending, silent history recompute, partial dedup without announcement | each observed shipping in an incumbent; each a fabricated provenance claim or data loss dressed as preference | stream 2 incumbent survey |
| day-resolution kcal verdicts; body-fat-percent level verdicts | 20 to >90 % systematic MAPE and +/-4-8 point LoA respectively: no decision band survives | same |

## Research slots (explicitly reserved)

| slot | status | what it fed |
|---|---|---|
| 1. CS truth discovery / subjective logic / PROV mapping | LANDED 2026-08-02; folded in (partial order, discounting shape, Belnap outcomes, FHIR cribs, NOT-BUILDING table) | phases 1, 1e, 2 design |
| 2. incumbent platforms + wearable error magnitudes + biological variation | LANDED 2026-08-02; folded in (per-field expected-outcome table in 00-phase0; the numeric-import reversal; recordingMethod/score_state/reversible-correction cribs; construct-validity axis; overlap-earned comparability; sampling-bias flag; anti-pattern list) | 00, 01 s4/s6.1, 02, 04, this file |

All research is in. The standing rule survives slot closure: literature
figures never override an own-replicates estimate for this athlete
(GUM 4.3.10's spirit); the expected-outcome table is a PRIOR that phase 0b
checks, not a substitute for running it.

## Loadline

I36-I44 (05-loadline.md) adopt in lockstep with the phase that emits each
payload: I37/I38 with phase 0a, I43 with phase 1, I36/I39/I40/I41/I42/I44
with phase 2. A rule adopted before its payload exists is a fiction; the
changelog entry lands per phase.
