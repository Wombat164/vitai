# Prior art survey (July 2026)

Input to [model-v2.md](model-v2.md). Produced by a multi-agent research sweep
(7 angles, ~40 sources) with a final validation pass; confidence caveats at
the end are part of the deliverable, not an apology.

## The verdict

**The combination vitai targets is unoccupied.** No product found - commercial,
open-source, or research - is simultaneously (a) LLM-native in its coaching,
(b) user-owned with a plain-text record, (c) deterministic in its number path,
(d) coupled to medical/injury data, and (e) motivationally designed (let alone
game-coupled). Every neighbor holds at most two of those:

| Closest neighbors | Has | Lacks |
|---|---|---|
| **OpenHealth** (GitHub, AGPL) | LLM chat over unified clinical + wearable + lifestyle data, self-hosted, local models via Ollama | Web-app-with-database (Prisma), not a plain-text record; no deterministic progress engine; no skills architecture |
| **ai-fitness-coach** (Rich627, GitHub) | Claude-native, local, user-owned; workouts/nutrition/sleep/weight | SQLite not plain text; no engine/intelligence split; no medical layer; hobby-scale |
| **Google PH-LLM / Personal Health Agent** (research) | Strongest technical validation of LLM coaching: fine-tuned Gemini over wearable timeseries + biomarkers, beat human-expert exam averages (fitness 88% vs 71%) | Explicitly not a product; Google-hosted, closed, the opposite of user-owned |
| **Fasten Health** (GitHub) | Self-hosted personal FHIR record aggregator (conditions, labs, meds, immunizations) | Zero fitness side, zero LLM; import-only (no live provider sync); complementary, not competing |
| **Runna** | The best adherence philosophy found: plan recalculates around interruptions, no red X for missed workouts, accept/reject suggestions | Closed plan engine, no LLM layer, no data ownership |
| **MacroFactor** | Best deterministic nutrition engine: TDEE derived from intake-vs-weight-trend, weekly rebalancing | Closed app/cloud; nutrition only |
| **Frontiers 2025 LLM health-journaling prototype** (academic) | Local-first, user-owned AI health journaling with cloud/local LLM toggle; profile holds conditions/allergies/medications | Journal entries, not a structured record + engine; EHR integration is stated future work; not a maintained product |

## Landscape by category

### Training platforms (Strava, TrainingPeaks, Runna, Garmin, GoldenCheetah)

- The industry-standard progress math is the **impulse-response family**:
  per-session stress score (TSS/TRIMP-class) rolled into CTL (~42-day EWMA,
  "fitness"), ATL (~7-day, "fatigue"), TSB = CTL - ATL ("form"). GoldenCheetah
  implements it open-source. NOTE: the interpretation bands are vendor
  conventions, not physics - TrainingPeaks markets +15..+25 TSB as peak form
  while GoldenCheetah docs call 0..+5 ideal; any implementation must treat
  bands as configuration, not truth.
- Strava's schema is activity + streams + a social layer (kudos culture is
  its retention engine); no nutrition, no medical, anywhere.
- Garmin has the richest wellness telemetry (sleep/stress/HRV/body battery)
  but gates it behind a commercial-partner API; consumer export is FIT/TCX/
  GPX/CSV, each lossy in its own way, and wellness metrics drop at every
  cross-platform hop.
- **Nobody in this category offers a plain-text or user-owned canonical
  export.**

### Weight/nutrition apps (MFP, Cronometer, MacroFactor, Noom)

- MacroFactor's adaptive TDEE (from logged intake vs weight trend, weekly
  rebalance) is the reference mechanic for the nutrition side of a coach.
- Noom is the psychology reference (CBT lessons, human coaches) and the
  cautionary tale: daily weigh-ins called demoralizing, color-coded food
  moralising criticized, contraindicated for disordered-eating histories.
- Portability is dire: MFP exports GDPR CSVs that no competitor can import
  (proprietary food IDs); logs are functionally stranded. Terra API exists
  precisely because the apps won't interoperate.
- Food databases are a moat (MFP's DB, Open Food Facts for wger). A coach
  should mirror daily totals, not rebuild a food database.

### Platform health stores (Apple HealthKit/Health Records, Google Health Connect, Samsung Health)

- Health Connect: 8 data categories + a structurally separate Medical
  Records API (FHIR); permissions per data type; on-device store, no REST.
- Apple: HKClinicalRecord wraps raw FHIR pulled from provider portals
  (allergies, meds, immunizations, labs) alongside fitness samples.
- Both keep clinical data separate from telemetry, and neither models
  user-authored injuries or visits as first-class entities.
- Regulatory tailwind: FHIR is becoming the mandated clinical exchange rail
  (CMS payer APIs due Jan 2027, >90% of US hospitals FHIR-enabled, 71% of
  countries reporting active FHIR use). SMART on FHIR standalone launch is
  the consent pattern for a personal app pulling one's own records.

### Coaching SaaS portability audit

Fitness-coaching platforms are a lock-in case study: of ten audited, only
two offer real structured export (JSON/CSV); the median is PDF-only ("you
can print it - there's a difference"), one contractually bans automated
extraction. Clinical data trends open (FHIR, by regulation) while fitness
data trends closed - vitai rides the open side of both.

### Motivation and adherence science

- Self-determination theory survey data (mHealth): competence (beta .346)
  and autonomy (.312) beat relatedness (.165) as drivers of intrinsic
  motivation; 44% of users of gamified apps did not perceive the
  gamification at all.
- Gamification richness shows an S-curve with an overload zone: past ~+1 SD
  of mechanic-richness, engagement drops ("cognitive strain, conflicting
  feedback"). Few mechanics, done well.
- Streak forgiveness matters more than streaks: streak-freeze users kept
  streaks ~48% longer past day 7 (17.2 vs 11.6 days); rigid chains punish
  correct rest.
- Adherence RATE of self-monitoring (share of prescribed logging days done)
  predicts weight-loss outcomes; a sparse continuous record genuinely beats
  a rich abandoned one - the founding motto is evidence-aligned.
- Runna's "no red X" recalculation and WHOOP's verdict-cited-from-your-own-
  data conversational coach are the two commercial mechanics users are
  reported to actually trust.

### Games that convert real life into in-game progress

See the fun layer in [model-v2.md](model-v2.md) for the design response.

- Alive and loved: Pokemon GO / Pikmin Bloom (distance -> stochastic
  collection rewards), Walkr/Wokamon (steps -> idle progression), Walkscape
  (pedometer-only RuneScape-like; anti-cheat BY CONSTRUCTION, no GPS),
  Zombies, Run! (narrative gating), Zwift (execution-quality stars,
  streaks), Habitica (habits -> RPG, but pay-to-win resentment at 3.9/5).
- Dead or damaged: STEPN (move-to-earn tokenomics collapsed >90% DAU,
  Ponzi-shaped), Sweatcoin (payout ~worthless, "it pays to walk" trust
  damage, cheat-tool ecosystem), Fitocracy (XP layer alone, shut 2022),
  Ring Fit (great in-session, no persistent meta-progression bridge).
- **The gap: no game gates its premium currency on verified goal
  ATTAINMENT** (trend on target, plan adherence, zone discipline). Raw
  volume or single-session quality only. Weight Watchers "Wins" (goal ->
  points -> real rewards) is the closest real-world precedent and is not a
  game; WHOOP is "engine computes verdict, product consumes it" but the
  verdict drives advice, not economy. A peer-reviewed result that
  gamification points earned predicted % weight loss supports the causal
  direction.

## Confidence caveats (kept deliberately)

- Widely-quoted gamification stats (62%->89% adherence, 213% competition
  lift, 340% engagement) trace to vendor marketing (Sahha, StriveCloud, the
  latter's source page dead) - directional at best, never design-load-bearing.
- GPTCoach (CHI 2025), AskEVA, Mindsera and WHOOP's developer API were
  cited but never deep-fetched; their closeness ratings are provisional.
- PH-LLM specifics beyond exam headlines are secondhand (Nature Medicine
  paywall).
- TSB interpretation bands conflict across vendors (see above) - resolved
  in our design by making bands configuration.
- The uniqueness verdict is an absence-of-evidence claim over a bounded
  sweep (~40 sources, GitHub/PyPI/npm/store searches) - strong for
  mainstream, weaker for the long tail of self-hosted quantified-self tools.
