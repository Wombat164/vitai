# Prior art: vitai as a guardrailed world model

The analyzer/coach we are building is, in effect, a **world model of a person**:
a structured internal representation of the athlete (facts, goals, context,
physiology, history, and the system's own uncertainty) that the coach reasons
over. Before building the event-interpretation and question-generation layers,
we swept four established fields to ground the design and avoid reinventing (or
misnaming) known work. Findings, with adopt / adapt / avoid calls.

The one-line verdict: **the framing is legitimate and the deterministic-first
architecture is well-trodden - what is novel in vitai is the *combination*
(a firewalled, provenance-tiered, effective-dated world model whose LLM only
narrates and asks), not any single mechanism.**

---

## 1. Is it really a "world model"? (world models + digital twins)

Two distinct meanings of "world model" exist and must not be conflated:

- **ML sense** (Ha & Schmidhuber *World Models* 2018; Hafner *Dreamer*/DreamerV3;
  LeCun *JEPA* / *A Path Towards Autonomous Machine Intelligence* 2022): a
  *learned latent-dynamics network* - observations compressed into a latent
  state, a net predicts how it evolves, an agent plans by imagining rollouts.
- **General / cognitive-science sense**: an internal *state + transition rules*
  used to reason, predict, and act. Control theory and BDI agents mean this.

vitai is squarely the second, and a different species from the first. It is
closest to a **belief-state personal digital twin**. The health-DT literature
(Frontiers 2026 *Human digital twins*; npj Digital Medicine 2024 systematic
review - only 18/149 studies met NASEM's real DT criteria; *MyDigiTwin*) draws
the line: a digital twin = data + *individualized* + *some* predictive capacity,
continuously updated, distinct from an EHR (stores, doesn't predict) and from
population models (don't individualize). The LLM-personalization work is even
sharper: *Know You Before You Speak* splits **user-state** (current condition) /
**world-model** (how it evolves) / **semantic-memory** (retrievable facts), and
states plainly that true user state is *never directly observed* - only
inferred and held as a belief.

**Adopt:** the label "world model", qualified ONCE and explicitly as
*symbolic belief-state + transition rules*, not a learned latent net. This
pre-empts the obvious ML-reader objection and cites real prior art (*Know You
Before You Speak*) for the three-way split - which maps 1:1 onto vitai:
semantic-memory = our facts+provenance tiers; user-state = goals+context;
world-model = the effective-dated update/derivation rules. Adopt too the
"true state is unobservable, we hold an estimate" framing - it legitimizes P3's
epistemic tiers as recognized *belief-state modeling*, not an ad-hoc hack.

**Avoid:** the ML *mechanism*. No part of vitai's state may become a trained
latent vector - an opaque RSSM/VAE latent is the exact opposite of auditable,
and "predict in latent space to discard unpredictable detail" (JEPA's pitch)
must never become an excuse to drop provenance.

**Adapt:** the *counterfactual / scenario* capability (MyDigiTwin's what-if;
JEPA's "predict only what's predictable") - but implement it as a deterministic
rules/query layer over the effective-dated facts (a future `vitai simulate`),
never a learned simulator in the state loop. If real forecasting is ever wanted,
bolt it on as a **clearly-labeled, separately-audited prediction tier** that
*reads* symbolic state and writes back tagged with its own (lowest) provenance
tier - never letting a learned predictor upgrade or overwrite a fact (preserves
P3: confidence never launders upward).

## 2. The firewall is a named pattern (neuro-symbolic + guardrails + provenance)

vitai's hard rule - the deterministic engine owns every number, the LLM only
narrates - is recognized prior art, not a personal quirk:

- **Neuro-symbolic AI** (IJCAI 2025 survey's Symbolic->LLM / LLM->Symbolic /
  LLM+Symbolic taxonomy; AlphaGeometry2 = *LLM proposes, symbolic solver
  verifies*). vitai is the "LLM+Symbolic" cell: engine = symbolic layer,
  LLM = neural layer. **Adopt the taxonomy as vocabulary.**
- **"LLM proposes, verifier disposes"** / **Zero-Mental-Math** ("Trust the
  Server, Not the LLM"): route all arithmetic and policy logic to deterministic
  tools; the LLM is a citation-copy-machine that never emits a final number.
  **Adopt directly** - external validation that our firewall is a known-good
  pattern. **Avoid RAG for numbers** (retrieval is probabilistic in the middle);
  RAG is fine only for the LLM's *narrative* pulling from vetted engine outputs.
- **Guardrails tooling** (NeMo Guardrails, Guardrails AI, constrained decoding):
  **adapt, don't adopt wholesale** - those guard chat safety/format, not
  domain-number correctness. Right takeaway: a schema/validator gate sits
  between any LLM output and anything persisted, even narration; reject-and-
  reprompt on violation, never silently accept.
- **Provenance** (W3C PROV Entity/Activity/Agent triad; data lineage): **adapt
  the triad in spirit** (claim = Entity, engine-run = Activity, source =
  Agent) but **avoid full PROV-O/RDF machinery** - a lightweight per-claim
  `provenance: {source, method, run_id, effective_date}` gives the same
  trust/retraction capability at our scale.

## 3. Provenance tiers as a truth-maintenance system (the deepest borrow)

The single most load-bearing find, arriving independently from *two* agents:
**JTMS / ATMS** (Doyle 1979; de Kleer 1986). A belief is a node with a
*justification*; revoke the justification and every dependent belief
cascade-retracts. This is exactly the mental model our observed / derived /
inferred tiers and our "late-truth-cascades" correction doctrine (G29) need.

**Adopt** the JTMS logic as the model for claims: each claim is a node with
`{value, tier, justification (source refs / derivation chain), effective_date}`;
invalidating a justification (a correction, a retracted observation) cascades to
everything derived or inferred from it. A user saying "no, I had no kid with me"
must retract the dependent "stroller-pace" hypothesis, not leave it stale.
**Avoid** building a full ATMS engine - the labeled-assumption-set idea plus a
simple cascade-invalidate rule captures ~90% of the value. Confidence is a
property of *tier + source*, never a vibe the LLM assigns; the LLM may *surface*
a tier and ask, but never upgrades or downgrades one itself.

## 4. Event -> questions -> auto / infer / ask (the coaching loop)

The "one event spawns questions; some auto-answerable, some only the user can
answer" design has a clean prior-art skeleton:

- **Blackboard architecture** (Hearsay-II; Nii 1986): one event posts to a
  shared structure; independent knowledge sources (GPS parser, weight-log
  checker, calendar checker, weather API) opportunistically fill slots; whoever
  answers first wins; unfilled slots surface as questions. **Adopt** - natural
  fit, low complexity, no fixed pipeline order.
- **Slot-filling / dialogue-state tracking**: model an event as a slot schema
  (who / what / where / purchase / mood) with a **fill-source tag per slot**
  {auto-filled, inferred-hedge, must-ask, skipped}. **That tag IS the
  answerability tiering** the athlete described.
- **What to ask** - **active learning / value-of-information** (uncertainty
  sampling, BALD/EPIG) + **Horvitz mixed-initiative** (1999): rank unfilled
  slots by `expected-information-gain x downstream-coaching-value / ask-cost`;
  only the top 1-2 survive per event. **Adopt.**
- **When to ask** - **JITAI** (Nahum-Shani) + **EMA burden** research: gate
  every nudge through a decision point (post-walk) with a hard capture-cost
  budget, mandatory skip/defer, and **no same-day re-ask**. **Adopt** - this is
  what operationalizes "never nag" (P7/P8, the 3-minute budget).
- **BDI / SOAR / ACT-R**: **avoid** as architecture (too heavy); borrow only
  BDI's *intention-commitment* idea - once a slot is inferred/committed this
  event, don't re-derive it.

## 5. GPS trace -> narrative (semantic trajectories)

Turning a GPX into "you stopped 8 min here, then walked home" is a mature
field, and it is **deterministic-first** exactly as our mandate wants:

- **Stop/move model** (Spaccapietra 2008 *conceptual view on trajectories*;
  CONSTAnT): the atomic unit is a **STOP** (stayed > threshold in place) or a
  **MOVE** (transit). **Adopt as our core structure** - `Stop{start,end,loc,
  label}` / `Move{path,mode}` is literally "stopped 8 min" as a data type.
- **Detection algorithms**: CB-SMoT (speed-variance clustering), DB-SMoT
  (bearing), POSMIT (per-point stop probability); classic stay-point rule
  (Zheng 2008): distance ~200 m, time ~20-30 min. **Adopt a CB-SMoT-style
  deterministic first pass** (speed < X for > Y sec within R m) - cheap,
  explainable, per-user tunable, no ML. **Adapt** POSMIT's stop-*probability*
  as a confidence layer for noisy urban GPX, not the primary detector.
  (Note: our live walk analysis already did the crude version - a >=25 s
  sub-0.4 m/s dwell test, and catching the *untracked* 8-min gap between two
  point-to-point walks as the real stop. Formalize it as CB-SMoT.)
- **Mode detection**: speed bands first (walk < 7, run 7-15, bike 15-25, car >
  25 km/h) before any ML classifier - overkill for single-user data. **Adopt.**
- **POI enrichment**: two-stage - segment into stops, THEN annotate each stop
  with a POI-category -> activity lookup + time-of-day prior. **Adopt the
  two-stage architecture; avoid LLM-per-stop as the primary path** (cost /
  latency / privacy) - deterministic lookup first, LLM only to disambiguate the
  ambiguous residual.
- **Privacy is a pipeline property, not a bolt-on**: geo-indistinguishability
  (planar-Laplace, Andres et al.) / spatial cloaking; **on-device reverse-geocode
  against a locally cached POI tile so no raw coordinate crosses a network
  boundary**; if a cloud lookup is unavoidable, coarsen to a 100-300 m cell
  first. **Adopt** - this is the concrete implementation of G35 tier-3's
  "on-boundary, opt-in, home-area is the most sensitive geodata" rule.

---

## What this changes for vitai

Convergent architecture the four fields hand us (all deterministic-first,
LLM-at-the-edge):

1. **Frame** vitai explicitly as a symbolic, guardrailed world model / belief-
   state twin (section 1) - one qualifying sentence in `model.md`.
2. **Claims become JTMS-style nodes** with justification + cascade retraction
   (section 3) - deepens P1/P3 and unifies with the G29 correction cascade.
3. **Event intake = blackboard + slot schema with per-slot fill-source tags**;
   unfilled slots ranked by info-gain x coaching-value / cost; asked through a
   JITAI decision point under a hard EMA-style budget (section 4) -> the new
   gap for the question loop.
4. **Geodata interpretation = stop/move segmentation (CB-SMoT) + speed-band mode
   + two-stage POI enrichment, on-device/coarsened** (section 5) -> makes G35's
   three tiers concrete and privacy-correct.
5. **Any learned forecasting is a separate, lowest-tier prediction layer** that
   never writes facts (section 1) -> a guardrail on the increment-7 forecaster.

None of this is a learned latent net; all of it is inspectable, effective-dated,
and firewalled - which is precisely the property no ML world model or mechanistic
digital twin in the survey keeps.

## Key sources

- World models: Ha & Schmidhuber 2018; Hafner DreamerV3; LeCun JEPA / *Path
  Towards AMI* 2022. Digital twins: Frontiers 2026 *Human digital twins*; npj
  Digital Medicine 2024 review; MyDigiTwin. Belief-state: *Know You Before You
  Speak*; *PersonalAI*.
- Firewall: IJCAI 2025 neuro-symbolic survey; AlphaGeometry2; NeMo Guardrails;
  Guardrails AI; "Trust the Server, Not the LLM"; W3C PROV.
- Truth maintenance: Doyle 1979 (JTMS); de Kleer 1986 (ATMS).
- Ask/infer: Hearsay-II / Nii 1986 (blackboard); Horvitz 1999 (mixed-initiative);
  BALD/EPIG (active learning); Nahum-Shani (JITAI); EMA burden literature.
- Semantic trajectories: Spaccapietra 2008; CB-SMoT / DB-SMoT / POSMIT; Zheng
  2008 stay-points; Andres et al. geo-indistinguishability.
