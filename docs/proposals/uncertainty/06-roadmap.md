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
P0a + P1c + #148 policy-as-of + P2 refusal shape --> P3 emission memory
                                                     + retraction cascade [C]
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

### GATE A: RUN AND RESOLVED, 2026-08-02

Ran over the private record. Numbers are in the comment on #171; only rates and
counts leave that repository.

| measure | result | pre-stated row |
|---|---|---|
| refusal rate, total dispersion | **76.9 %** | `R_B >= 0.60` **FIRED** |
| straddle rate (interval covers the whole band) | 53.8 % | |
| median u_rate / half-band | **1.74** | |
| verdict flips | **12**, 23 % of scored weeks | `flips > 0` **FIRED** |
| band coverage | 20.4 % overall | variant A unavailable for 47 of 52 weeks |

**Decision, per the rule stated before the run: the decision unit is wrong, not
the metadata.** A capability registry prices instrument noise, which is not the
term that dominates this measurand, so it cannot rescue a single weekly verdict.
The margin is not marginal: the median `u_rate / half-band` is 1.74 - a
standard uncertainty ratio, so the 95 per cent half-width is about 3.4 times
the entire decision half-band - and more than half of scored weeks admit no verdict word at
all.

**Phase 2 scope is therefore set:**

- **DROP** the capability dataset as a route to better verdicts. It survives
  only for seam detection (#33), where the term is bias, is permanent, and is
  the one thing a longer window cannot fix.
- **SHIP** the refusal predicate regardless of the rate, on the flips alone.
  Each flip is a false all-clear or false alarm in the engine today.
- **CHANGE THE DECISION UNIT.** This is the actual remedy and needs no new
  schema: a fortnightly rate with a guard band, or refuse-by-default weekly.
- The per-field expected-outcome table in `00` becomes **shipped policy**. The
  record's own dispersion landed inside the literature range, which was the
  pre-stated condition for adopting it with no further data collection.

**F2 confirmed, by a sharper route than the coverage threshold.** Coverage is
20.4 % overall, above the 0.10 floor, but the split by source is the finding:
every device and connector source sits at 0 %, and the only fully banded source
is a hand-kept sheet. Because a partial budget understates, a week computes
under variant A only when every row in it carries a band. Uncertainty metadata
is absent exactly where the contested data arrives, and present only where a
human already wrote it down.

**Blocker discovered downstream of the gate:** the verdict vocabulary must be
widened BEFORE any refusal ships. Filed as #177, sequenced in phase 2 below.

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

**Scope after GATE A (see above), which has run:** the capability dataset is
**cut as a route to better verdicts** and survives only for seam detection.
The refusal predicate ships regardless, on the flips. The decision unit changes
rather than the metadata. Rows below are re-scoped accordingly.

**Ordering constraint discovered after the gate:** `no_data` already carries
four distinct states, distinguishable today only by inspecting which fields are
null, and a fifth case removes the row entirely. The refusal work adds two more.
**#177 must land first, as its own contract bump.** If refusals ship under the
existing token the reason is unrecoverable from the rows afterwards, and
recovering it later would need the policy of the day (#148). The `undecidable`
word below is the coarse half of that answer; the reason field is the other
half, and it is the half that keeps cases 7 and 8 from repeating this.

| item | effort | notes |
|---|---|---|
| **#177 verdict-vocabulary widening: reason field + suppression stops being an absence** | days | **BLOCKS every refusal-emitting row below**; own contract bump |
| capabilities dataset: competence flag + construct notes + `accuracy` ban | days | **re-scoped by GATE A: seam detection only, not verdicts.** Categorical payload; u only from own data |
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

## Phase 3: emission memory + retraction cascade `[C]`

The largest single item in the whole proposal, sized honestly: it is the
first requirement that needs the engine to REMEMBER ITS OWN OUTPUTS, which
is an architectural addition (a new event-class dataset plus an API delivery
surface), not a field. Verified blocker: no `verdicts` dataset exists;
verdicts are rebuilt and overwritten, so today nothing can answer "what did
the engine tell me last week, and does it still hold".

| item | effort | notes |
|---|---|---|
| `emissions.jsonl` + `api.assert_delivery` | days | surfaced-assertions-only decision recorded in 01-schema 8b (build purity forces it, cost seconds it) |
| forward/backward direction table + recompute-or-refuse split | days | the core rule: forward-looking recomputes from the anchor; backward-looking refuses over an emptied interval with reason; totality enforced by test |
| `basis_retracted` join + warning counterfactual backtest | days | extends the G24/G36 anchor-audit loop with a retraction trigger; output "N fired on a basis later retracted; M would still fire" |
| materiality gate | afternoon | the phase-0 guard-band predicate REUSED verbatim as the surfacing gate: a recompute surfaces only when it crosses a decision boundary. One predicate, two callers, no second calibration to drift. |
| #148 policy-as-of | week | PROMOTED from known defect to PREREQUISITE (see 04-issue-rewrites): replaying an assertion needs the policy in force at its date, not today's. Partial precedent exists (week-Monday thresholds, G14/G20); the gap is config overlay, resolution ordering and registries (G31). Until it lands, the emission log records but cannot verify (`still_holds` blocked; everything else in this phase proceeds). |

**GATE B (phase 3 entry):** P0a shipped (regimes exist to retract), P1c
shipped (lineage names an emission's basis), P2's refusal payload shape
shipped (the backward-looking refusal reuses it). #148 gates only the
verification half; do not hold the whole phase on it.

Failure mode of the phase: unlogged surfacing by a non-bundled consumer
leaves assertions invisible to retraction; accepted residual risk, recorded
in 01-schema 8b with the reason (logging computation instead of delivery
records the wrong event).

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

I36-I50 (05-loadline.md) adopt in lockstep with the phase that emits each
payload: I37/I38 with phase 0a, I43 with phase 1, I36/I39/I40/I41/I42/I44
with phase 2, I45-I47 with the phase-2 report layer, I48-I50 with phase 3.
A rule adopted before its payload exists is a fiction; the changelog entry
lands per phase.
