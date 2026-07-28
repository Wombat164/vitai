# The loop: one day, fully traced

Design document, July 2026. Takes ONE ordinary event - **"I walked 10,000
steps today"** - and traces it through the entire system: capture, history,
analysis, goal-matching, inference, feeling, reward, retention. Every
question the system cannot answer is a numbered gap; the gaps drive the v3
schema proposal at the end. Grounded in [prior-art.md](prior-art.md) (what
Strava/Runna-class products already do for running, and what nobody does
for whole-life context).

Status tags: **[SHIPPED]** works in v0.2.0 - **[PARTIAL]** exists but
incomplete - **[GAP Gn]** numbered gap, addressed in section 4.

## 1. The loop, stage by stage

```
   capture -> observe -> derive -> contextualize -> infer -> coach -> feel -> reward -> evolve goals
      ^                                                                                    |
      +---------------------------- the next day is shaped by it -----------------------—-+
```

1. **Capture** - the 10k steps arrive as `{"date":...,"steps":10000,...}` in
   `daily.jsonl`, via a connector pull (watch platform), a screenshot
   through the ingest skill, or a typed line. Cost ceiling: the WEEKLY
   interactive budget is ~3 minutes total - a single day's capture must be
   passive or one line, near-zero. [SHIPPED]
2. **Observe** - append-only, `null` for unknown, supersedes for
   corrections. The line records THAT it happened; provenance in `source`
   fields where present. [SHIPPED for steps; PARTIAL for provenance on
   daily lines - GAP G1]
3. **Derive** - `vitai build`: the steps join the 7-day average, the weekly
   steps-floor verdict row, tripwires. Deterministic, rebuildable.
   [SHIPPED] But comparisons beyond the window (vs last month, vs all
   Julys, personal records) are absent. [GAP G2]
4. **Contextualize** - was it a walk-commute, a hike with the kids, rain or
   shine, a known route, during a phone call? The current schema cannot say.
   [GAP G3, G4, G5]
5. **Infer** - `vitai infer`: a model reads rollup + recent lines and may
   append "steps rise on office days" with evidence and confidence.
   [SHIPPED mechanically; starved of context until G3-G5 land]
6. **Coach** - the coach skill judges against plan and goals; today it can
   answer "floor met?" but not "which goal did this serve, and how far
   along is it?" because goals are prose in `plan.md`, not data. [GAP G6 -
   the biggest one]
7. **Feel** - did the athlete enjoy it? Feel proud, indifferent, guilty?
   Nothing captures subjective state. [GAP G7]
8. **Reward** - streaks, milestones, game currency. Verdict rows exist as
   the mint signal; streaks and a reward ledger do not. [GAP G8, G9]
9. **Evolve** - a good week nudges the plan; the plan edit is visible in
   git, but goal lifecycle (declared, revised, achieved, abandoned - and
   WHEN) is not queryable. [GAP G6 again]
10. **Retain/forget** - what of this day survives 5 years? Under what legal
    basis, deletable how? Partially designed, not yet written down as
    policy. [GAP G10]

## 2. The question bank

Each question tagged with where the answer lives - a dataset/derivation
**[SHIPPED]**, or a gap **[Gn]**. This bank doubles as the acceptance test
for the v3 model: v3 is done when every question has a non-gap tag.

### 2.1 The raw event and its provenance

1. How many steps today? - daily.steps [SHIPPED]
2. Which device/app measured them? - [G1: per-line `source` on daily]
3. When did the line enter the record (vs the day it describes)? - git history; [G1 adds `recorded_at` only if ingestion lags matter - default: git is enough]
4. Was it corrected later, and why? - supersedes chain [SHIPPED]
5. Is 10,000 the raw count or device-rounded? - [G1: source implies precision]
6. Did two devices disagree today? - two lines, two sources; last-wins today [G1: keep both, arbitration rule documented]
7. Was the day complete (watch worn all day) or partial? - [G1: `coverage` flag or note]
8. Is this a manual claim or a measured value? - [G1: source="manual"]
9. What ELSE was recorded today? - all datasets keyed by date [SHIPPED]
10. What was NOT recorded today that usually is? - coverage vs recent pattern [G2: derived coverage report exists only as counts]

### 2.2 History and comparison

11. How does today compare to yesterday? This week's average? - derived [SHIPPED]
12. Vs the same weekday over the last quarter? - [G2: weekday profile]
13. Vs the monthly average, month by month, for a year? - [G2: monthly rollup]
14. Is today a personal record (day/week/month)? - [G2: records table]
15. What is the trend: rising, flat, declining - over 30/90/365 days? - [G2: trend slopes]
16. What is the athlete's "normal" (median band) so today can be judged as within/above/below normal? - [G2: baseline bands]
17. Was today's 10k unusual FOR a Monday-after-long-run? - [G2 x G4: conditional baselines]
18. How many 10k+ days this month vs last? - [G2]
19. What share of days this year met the floor? - [G2: adherence rate over window]
20. When was the last day this high? - [G2]

### 2.3 Goals and plans

21. Which goal(s) do steps serve? - [G6: goals.jsonl with `metric` linkage]
22. Was 10k the target, or the floor, or neither? - vitai.toml threshold vs [G6] goal target - today conflated
23. How long in advance was the goal set? - [G6: goal line's `date` = declaration]
24. When was the goal last edited, and what changed? - [G6: supersedes chain on goals = full edit history with dates]
25. Who set it - athlete, coach skill, onboarding? - [G6: `set_by`]
26. Why this goal - what desire/ambition does it serve? - [G6: `motivation` field linking to profile ambitions]
27. What is the deadline, and is today's pace sufficient to make it? - [G6 + G2: projection]
28. Is the goal active, paused, achieved, abandoned, superseded? - [G6: `status` lifecycle]
29. What did achieving the previous goal look like? - [G6: achieved goals stay in the record]
30. Are two active goals in conflict (cut weight vs build 10k race pace)? - [G6 + coach judgment; inference tier flags it]
31. Did today's steps ALSO serve a non-fitness goal (dog, errands, family time)? - [G3/G5 context + G6 multi-goal tagging]
32. What fraction of the goal's journey is done? - [G6 + G2: progress %]
33. Has this goal been tried and abandoned before? - [G6: prior goal lines with status=abandoned]
34. What was promised to whom (accountability: partner, coach, self)? - [G6: `accountability` field]

### 2.4 Streaks and consistency

35. Is today part of a streak? Which streak, how long? - [G8: derived streaks]
36. What DEFINES the streak - raw 10k days, or floor-met weeks? - [G8: streak definitions live in vitai.toml, derived like verdicts]
37. Does a planned rest day break the streak? - [G8: forgiveness rules - illness/injury/planned rest never break streaks; evidence says rigid chains punish correct rest]
38. What is the longest streak ever? Current vs best? - [G8]
39. Is the streak at risk tomorrow (calendar says travel)? - [G8 + G5 calendar context]
40. What does the streak MEAN - is it correlated with the rate verdict actually improving? - [inference tier over G8 + verdicts]
41. Should the athlete be told about the streak today (motivating) or not (pressure)? - [G7 preference + coach voice rules]
42. Streak vocabulary: days? weeks? "clean weeks"? - [G8: weekly-first, matching the verdict cadence]

### 2.5 Training vs life

43. Was it JUST steps, or part of a recorded session? - sessions.jsonl same date [SHIPPED - a `walk` session]
44. Was it a planned workout or ambient movement? - [G4: sessions get `planned` linkage; ambient = daily only]
45. Did the plan prescribe anything today, and was it done? - [G6: prescriptions as data; today prose-only]
46. Was it a commute turned walk (behavior change working)? - [G3: activity context tag]
47. Does the watch double-count session steps in the daily total? - connector documentation deliverable (platform overlap semantics per vendor); a `source` string alone cannot answer this
48. Was it recovery-pacing after yesterday's hard run? - sessions history + [G4]
49. Should these steps count toward training load? - derived: walks excluded from load by default [G2: load model]
50. Was the day a rest day BY DESIGN? - [G6 plan-as-data; else inference]

### 2.6 Physical context: place, route, weather

51. Was it outside? - [G3: `setting` on session/daily context]
52. A known route? Which? - [G3: `route` slug; routes as a small personal vocabulary]
53. New territory (travel, exploration)? - [G3: route=null + location != home]
54. What was the weather? - [G5: context enrichment - weather joined by date/place at ingest time, stored not fetched-on-read]
55. Did weather change the behavior (rain = treadmill)? - [inference over G5]
56. Where geographically (home, work, holiday)? - [G3: coarse `place` - deliberately coarse; precise GPS stays in the source platform]
57. Elevation/terrain? - sessions distance/elevation if imported [PARTIAL - sessions lack elevation field; G4]
58. Time of day (morning walker vs evening)? - [G4: sessions have no start time today; add `start_time`]

### 2.7 Social context: people

59. Was someone else along? Who? - [G3: `with` - coarse relationship slugs (partner, kid, friend, colleague, dog), never third-party identities beyond what the athlete writes]
60. Is walking-with-partner more consistent than alone? - [inference over G3]
61. Was it family logistics (school run) doubling as movement? - [G3 context tag]
62. Did a companion's presence change intensity? - [inference: G3 x avg pace]
63. Was it a social commitment (club, running pal) - the kind that protects adherence? - [G3 + G6 accountability]
64. Are "guest" sessions (gym with partner) tracked as such? - [G3 `with` on gym sessions]
65. Third-party privacy: what may the record say about OTHER people? - [G10: policy - relationship slugs yes, other people's health data never]
66. Does the family calendar explain today (kids' camp = more steps)? - [G5: calendar-context join, opt-in]

### 2.8 Body state around the event

67. Did the athlete sleep well before it? - daily.sleep_h [SHIPPED]
68. Resting HR trend that morning? - daily.rhr + tripwire [SHIPPED]
69. Any pain during/after? - daily.hip_pain [SHIPPED - single site; G4 generalizes to `pain`+`pain_site`]
70. Menstrual/hormonal phase where relevant? - [G4: optional cycle field, athlete-controlled]
71. Illness brewing (RHR up + sleep down + subjective "off")? - tripwires + [G7 feel] + inference
72. Fuel state - was it fasted, post-meal? - [out of scope by default; note field]
73. Alcohol the night before? - daily.alcohol [SHIPPED]
74. Injury gate status - did the steps violate a medical gate? - [G11: medical.jsonl gates as data; today prose in CLAUDE.md]

### 2.9 Subjective: feeling, motivation, fun

75. How did it FEEL (RPE-like, 1-10)? - sessions.rpe [SHIPPED for sessions; G7 for days]
76. Mood today? - [G7: daily `mood` 0-10 nullable]
77. Was it FUN? - [G7: `feel` tag distinct from effort: fun/neutral/chore]
78. Is motivation trending up or down this month? - [G2 over G7]
79. What does the athlete say in their own words? - note fields [SHIPPED] + [G12: journal.jsonl for longer reflections]
80. Did they feel proud/indifferent/guilty about the 10k? - [G7; and the voice rules FORBID the system from ever inducing the guilt]
81. Do low-mood days precede skipped days (relapse signature)? - [inference over G7 + G2]
82. Which activities correlate with high mood FOR THIS athlete? - [inference; this is the personalization moat]
83. Does the athlete WANT feedback today, or quiet? - [G7 preference: `nudge_ok` profile setting + coach etiquette]
84. Burnout/"gamification exhaustion" signals (rewards ignored)? - [G9 ledger + inference]

### 2.10 The agent's judgment (inference tier)

85. Was 10k GOOD today - relative to goals, body state, context? - the coach's synthesis: verdicts (deterministic) + inferences (contextual) + voice rules; "good" is never a raw-number judgment [SHIPPED mechanics, starved until gaps land]
86. What evidence supports the judgment? - inference `evidence` field [SHIPPED]
87. How confident is the model, and does it say so? - `confidence` [SHIPPED]
88. Which model judged, and when? - `model` + `date` provenance [SHIPPED]
89. Can a wrong inference be retracted? - supersedes on inferences [SHIPPED]
90. Do inferences ever alter the numbers? - NO, by architecture [SHIPPED]
91. Is the agent repeating itself? - prior-inference dedup in the prompt [SHIPPED, weak; strengthen with embedding-free textual dedup]
92. What would the agent LIKE to know that it can't? - inference kind=question [SHIPPED - and these questions are exactly how gaps surface in production]
93. Does the athlete get to disagree, and is the disagreement recorded? - [G12: journal reply / inference superseded with reason]
94. When do we re-run inference - cadence, or on-event? - [policy: weekly with the build; on-demand otherwise; never silently in the background]

### 2.11 Rewards and the game

95. Did today mint anything (XP, currency)? - verdicts as the mint signal [SHIPPED]; the LEDGER of what was minted is the game's, not vitai's [G9: boundary doc]
96. Is the reward for volume (10k) or attainment (floor met, streak intact)? - attainment-first by design (prior-art: volume-rewards are the crowded, gameable space)
97. Can rewards be spoofed by fake lines? - the record is self-reported; single-player honesty model; competitive layers need attested sources [G9 boundary doc]
98. Does a missed day PUNISH (loss aversion) or just not-reward? - never punish: no-red-X philosophy is settled
99. Milestones: first 100k-step week, 1000km year? - [G2 records + G8]
100. Are rewards meaningful to THIS athlete (badges vs data-artifacts vs real-life treats)? - [G7 preference + G9]
101. Does the reward schedule decay (novelty wear-off)? - [G9: game-side concern, informed by G2 engagement data]
102. Is there a "quiet mode" - all tracking, no gamification? - [G9: the game layer is optional by architecture]

### 2.12 Medical and long-horizon life

103. Does a clinician-set restriction apply to today's activity? - [G11: medical.jsonl - visits, injuries, restrictions, resolutions - as data with lifecycle]
104. Is an unassessed symptom trending (the see-a-doctor tripwire)? - tripwires + [G11 links symptom lines to the eventual visit]
105. What did the physio say last month, and did behavior change after? - [G11 visit line + inference correlation]
106. Which long-term ambition does daily movement serve (health-span, race, example-for-kids)? - [G13: profile ambitions as structured entries goals can reference]
107. How has the athlete's relationship with exercise changed over years? - [G12 journal + inference over years]
108. What changed after a major life event (new job, new house, new baby)? - [G12: life-events in journal with `kind`]
109. Is the record useful to show a doctor? - [G11 + export: a medical-view projection]
110. What would the athlete want their future self to know about today? - [G12 journal]

### 2.13 Retention, privacy, GDPR (meta-questions the system must answer about itself)

111. What legal basis covers this health data? - [G10: personal single-user = GDPR household exemption; HOSTED multi-user = Art. 9(2)(a) explicit consent, and the host is the controller - must be stated in the platform docs]
112. Where is the data physically? - user's own repo/remote; hosted: per-user stores, host-declared [G10]
113. How is it deleted - fully, verifiably? - per-user store deletion = directory removal; git history of a personal repo is the user's own [G10: hosted platforms must not keep long-lived backups beyond stated windows]
114. What about inferences derived from deleted data? - [G10: deletion cascades - inferences citing deleted evidence are superseded or removed]
115. Data portability? - the record IS the export; portability is the architecture [SHIPPED]
116. Retention policy: does anything expire? - observed data: keep forever by default (the value compounds); derived: disposable; inferences: prunable [G10 policy doc]
117. Minimization tension: "record everything" vs GDPR minimization? - resolved by USER-owned scope choice: the athlete decides granularity; hosted platforms must default coarse (place not GPS, slugs not names) [G10]
118. Who can read it? - user + explicitly-granted agents; skills state what they read [SHIPPED in SECURITY.md; G10 restates for hosts]
119. Third parties in the record (question 65)? - relationship slugs, never others' health data [G10 policy]
120. Consent lifecycle for the inference layer (model reads health data)? - opt-in `[inference]` config IS the consent act for personal use; hosted needs explicit consent UX [G10]
121. Breach blast radius? - per-user stores; no cross-user database exists to breach [SHIPPED by architecture]
122. Can the athlete see everything an agent wrote vs what they wrote? - provenance: model-written lines carry `model`; human lines don't [SHIPPED for inferences; G1 extends `source` discipline everywhere]

### 2.14 Added by redteam (household, cost, threshold history)

123. Two athletes in one household (partner both on vitai): can their coaches coordinate without cross-user joins? - by architecture, only through each user's own record referencing relationship slugs; shared planning happens at the calendar/skill layer, never in the data layer [policy, documented]
124. Does a shared session appear in BOTH records, and may it? - yes, each athlete's own line about their own body; nothing about the other's physiology [G10 policy]
125. What does the inference layer COST (tokens, latency, money) and is that visible? - [G9-adjacent: `vitai infer` should report tokens/duration; cadence is weekly by policy so cost is bounded]
126. If a threshold (steps floor) changes today, what happens to LAST year's verdicts on rebuild? - without versioned thresholds they silently recompute against today's value - the audit-trail killer. [G14: thresholds as dated data]
127. Can a connector REVISE its own earlier line (an intraday summary that finalizes overnight)? - found live with a real device sync: NO - `supersedes` keys on date+source, so a same-source revision names its own key and eliminates itself in resolution. Interim policy: connectors append completed days only. [G1 grows: per-line identity (a generation or line id) so same-source supersede chains resolve]
128. If the watch says 2,443 kcal and the calorie app says 2,844 kcal for the same day, what does the record say? - ONE canonical kcal_out, chosen by per-quantity precedence (measured device > app assumption), with both claims retained as observations. [G15]
129. If the same run reaches the record via two platforms (device sync AND a hub export), is it two runs? - no: fuzzy overlap-matching (same date, intersecting time, duration/distance within tolerance) collapses them to one physical activity, richer/higher-precedence source wins, the other becomes corroboration. [G15; depends on G4 start_time]
130. Can the day's sessions burn more energy than the day burned? - physically no; if the data says so, that is a CONSERVATION TRIPWIRE (double-count or bad source), flagged never auto-fixed. [G15]
131. Do two daily lines for one date double-count in averages and verdicts? - today YES if both survive resolution (the engine iterates all records) - held off only by connector politeness (skip-existing). Conservation must be engine-enforced, not policy-hoped. [G15, CRITICAL trigger]
132. If the logged energy deficit implies -0.5 kg/week but the scale trend shows -0.2, which is true? - the ANCHOR (trend); the gap measures logging/model error, and the derived implied-TDEE (intake + trend x ~7700 kcal/kg) recalibrates the estimate. [G16: energy-balance audit derivation]
133. Does a single-morning weight spike ever reach a verdict? - never: weight anchors as a tendency; verdicts consume rolling means only (SHIPPED - the rate verdict already averages weeks) - the doctrine is now named, not just implemented.
134. Where do body-fat %, waist, and other body measurements live? - nowhere today. [G16: measurements.jsonl - sparse anchor-class dataset]

### 2.15 Shape semantics (curves mean things)

135. For any metric, what are its value, rate of change, acceleration, extrema, plateaus and variance - at EVERY timescale (last reading, 7d, 30d, 90d, 365d)? - [G17: the uniform shape-feature grammar, one deterministic extractor for all metrics]
136. What does a given shape MEAN for a given metric at a given timescale - is a plateau a stall, an adaptation, or rest working? Is a local minimum a milestone or dehydration? - meaning is metric- and timescale-specific and must be LOOKED UP, not vibed: [G17: the semantics registry - versioned, curated, auditable]
137. Are tripwires and verdicts a separate mechanism from shape semantics? - no: they are the ACTIVATED subset of the registry (shapes wired to thresholds and actions); the registry is the superset the coach and lens draw explanations from. [G17]
138. Who interprets a shape x metric x timescale combination the registry does not cover? - the inference tier, prompted WITH the registry (extend, never reinvent); confirmed inferences graduate into the registry with evidence. [G17 x inference tier]
139. What do cross-metric, lagged shapes mean (short sleep -> next-day easy-HR drift; alcohol -> RHR spike; ramp rate -> pain)? - engine computes lagged features deterministically; registry holds the canonical pairs; inference hunts the long tail. [G17 + G2]

## 3. Redteam findings (the gaps, ranked)

| # | Gap | Severity | Why it matters |
|---|---|---|---|
| G6 | **Goals are prose, not data** | CRITICAL | 14 questions unanswerable; "did this match a goal, when was it set/edited" is the product's core promise and the game's mint needs goal linkage. |
| G7 | **No subjective tier** (mood, feel, fun, nudge preference) | HIGH | Adherence science says feeling drives relapse; the coach is blind to it; "fun" is a stated product pillar. |
| G3 | **No event context** (setting, route, place, companions, activity tags) | HIGH | The whole-life differentiation vs Strava/Runna lives here. |
| G2 | **No long-window comparison engine** (baselines, records, trends, weekday profiles) | HIGH | "How does today compare" is the most natural user question; verdicts only see weeks. |
| G8 | **No streak engine** | MEDIUM | Wanted for motivation + game; must ship WITH forgiveness rules or it does harm. |
| G11 | **Medical layer still prose** | MEDIUM | Designed earlier (visits/injuries/gates as data); not yet schema'd. Prior-art says nobody does this - it's also the moat. |
| G1 | **Provenance discipline incomplete on daily** | MEDIUM | Device disagreement and manual-vs-measured need `source` everywhere. |
| G10 | **Retention/GDPR policy not written** | MEDIUM | Architecture already answers most of it; the platform story (hosts!) makes writing it down mandatory. |
| G12 | **No journal/life-events dataset** | LOW-MED | Long reflections, life events, disagreement-with-agent. |
| G5 | **No enrichment joins** (weather, calendar) | LOW-MED | Valuable context; must be stored-at-ingest (deterministic rebuilds forbid fetch-at-derive). |
| G4 | **Session schema thin** (start_time, elevation, planned-link, generalized pain) | LOW | Straightforward additive fields. |
| G9 | **Game boundary undocumented** (ledger ownership, spoofing stance, quiet mode) | LOW | One doc page; the architecture already implies the answers. |
| G13 | **Ambitions not structured** | LOW | Goals need something to point at ("why"). |
| G14 | **Thresholds unversioned** (found by redteam) | HIGH | `vitai.toml` is mutable current-state; a threshold change silently recomputes ALL history on rebuild - deterministic in the letter, audit-destroying in spirit. Thresholds must become dated data. |
| G15 | **No source reconciliation - conservation unenforced** (operator golden rule, 2026-07-28) | CRITICAL alongside G6 | Multiple sources will claim the same physical day/activity (live already: device + calorie app). The engine must resolve claims to ONE canonical value per quantity - per-quantity precedence, fuzzy activity overlap-matching, session-energy-as-attribution - and surface conservation violations as tripwires. Today two same-date lines would double-count in every average; only connector politeness prevents it. Observations = claims; derived = adjudicated truth. |
| G16 | **Anchor class incomplete** (operator doctrine, 2026-07-28) | MEDIUM | Weight exists but body measurements (fat %, waist, circumferences) have no dataset, and the energy-balance audit (implied TDEE from intake + weight trend, anchor-recalibrates-estimates) has no derivation. Anchors are the top of the precedence ladder and the audit of the whole calorie ledger. |
| G17 | **No shape semantics** (operator doctrine, 2026-07-28) | HIGH, generalizes G2 | Curves mean things: every metric needs its shape features (value, slope, acceleration, extrema, plateaus, variance) extracted uniformly at every timescale, and a SEMANTICS REGISTRY mapping (metric x timescale x shape) to meaning - curated, versioned, auditable. Verdicts/tripwires are the activated subset; the lens annotates charts from it; the inference tier extends it and graduates confirmed findings into it. Without the registry, interpretation lives in model vibes and chat history. |

Redteam notes beyond schema: (a) every new field raises capture cost -
the 3-minute budget is the design's immune system, so ALL context fields
are nullable and screenshot-inferable, and the minimum viable day stays
`steps` alone; (b) subjective capture must never become homework - one
optional `mood`/`feel` pair, not a questionnaire; (c) enrichment joins must
happen at INGEST (stored as observations) or the deterministic-rebuild
property dies; (d) streaks without forgiveness are harm, not motivation;
(e) the more context the record holds, the more the inference prompt must
be curated - context windows are a budget too.

## 4. The v3 model (schema evolution proposal)

Cross-dataset conventions settled by the redteam pass:

- **`date` semantics are named per dataset**: on observations it is the day
  the line is ABOUT; on `goals`/`journal` it is the day of declaration; on
  `medical` it is onset/occurrence. Where both matter, the second one gets
  its own field - never an overloaded `date`.
- **`supersedes` is scoped within `slug`** for lifecycle datasets
  (goals, medical): at most one un-superseded head per slug; a
  status-changing append supersedes the previous head of ITS slug.
- **Flat scalars only**, keeping the JSONL-to-SQLite 1:1 mapping: list-ish
  fields (companions) are comma-delimited slug strings, not JSON arrays.
- **Contract bumps on ANY shape change**, new tables included
  (ARCHITECTURE.md's rule wins; the earlier "additive is free" claim was
  wrong).

New datasets (all append-only, supersedes-capable, validated):

- **`goals.jsonl`** [G6]: `date` (declared), `slug`, `title`, `metric`
  (weight_kg | steps | distance_km | race_time_s | manual), `target`,
  `deadline`, `status` (active|paused|achieved|abandoned), `set_by`,
  `motivation` (free text or ambition slug), `accountability`,
  `rest_days` (weekday letters, feeds streak forgiveness), `note`.
  Edits = supersedes within slug -> "when was it last edited" is the audit
  chain. Verdicts gain goal linkage for the four computable metrics;
  `manual` goals are explicitly human-judged - no auto-verdict, ever
  (renamed from `custom` to say what it means).
- **`journal.jsonl`** [G12, G13, part of G7]: `date`, `kind`
  (reflection|life_event|ambition|feedback), `text`, `tags`, `note`.
  Ambition entries give goals something to reference.
- **`medical.jsonl`** [G11]: `date` (onset/occurrence), `kind`
  (visit|injury|symptom|lab|medication|restriction), `slug` (groups the
  lifecycle of one condition), `title`, `body_site`, `severity`, `status`
  (active|monitoring|resolved), `resolved_date` (closes the episode
  window - REQUIRED for streak forgiveness to be computable: a day is
  "excused" iff it falls in an episode window of a restricting condition),
  `restricts` (what training it gates), `provider_type`
  (gp|physio|specialist - never provider identity by default), `note`.
- **`thresholds.jsonl`** [G14]: `date` (effective-from), `key`
  (steps_floor|easy_hr_cap|...), `value`, `note`. The engine judges each
  week against the threshold IN FORCE that week; `vitai.toml` remains the
  bootstrap and current-state view. Without this, editing a threshold
  rewrites history on rebuild.
- **`measurements.jsonl`** [G16]: sparse anchor-class dataset - `date`,
  `kind` (body_fat_pct | waist_cm | hip_cm | chest_cm | thigh_cm |
  arm_cm | neck_cm | other), `value`, `source`, `note`. Anchors sit at
  the top of the resolution precedence ladder; like weight they are
  judged as TENDENCIES (sparse trend), never single points.

Extended fields (nullable, additive):

- `daily`: `source`, `mood` (0-10), `feel` (fun|neutral|chore), `coverage`
  (full|partial|manual), generalized `pain`+`pain_site` (migration:
  `hip_pain` maps to `pain`+`pain_site="hip"`).
- `sessions`: `source`, `start_time`, `elevation_m`, `setting`
  (outdoor|indoor|treadmill|home), `route` (personal slug), `place`
  (coarse: home|work|travel slug - SUPERSEDES today's free-text `location`,
  which migrates into `place`/`route` and is retired), `with`
  (comma-delimited relationship slugs), `context`
  (commute|family|social|solo|club), `planned` (goal/plan ref), `weather`
  (coarse: dry|rain|hot|cold|wind - stored at ingest).

The resolution layer [G15] (deterministic, runs at build time, BEFORE any
derivation):

- **Claims model**: every observation line carries `source`; multiple
  same-date claims per dataset are expected and all retained. Resolution
  produces ONE canonical record per (date, dataset) that everything
  downstream (rollup, verdicts, baselines, streaks, the read model's
  primary tables) consumes; raw claims are projected into companion
  `*_claims` tables for the stats-junkie audience.
- **Per-quantity precedence** (config, with sane defaults): each FIELD
  resolves independently by source rank - e.g. `kcal_out`: hr-device >
  calorie-app > manual; `kcal_in`: food-ledger > manual; `steps`:
  wrist-device > phone; `weight`: scale > app-sync; `sleep_h`/`rhr`:
  device only. A day's canonical row is thus a field-wise merge of the
  best witness per quantity - never a sum of witnesses.
- **Activity identity (fuzzy overlap-matching)**: two session claims are
  the SAME physical activity when date matches and time intervals
  intersect (needs `start_time`, G4), or - lacking times - when type
  matches and duration ratio is within 0.8-1.25 and distance ratio within
  0.9-1.1. The higher-precedence/richer claim becomes canonical; the other
  is retained as corroboration and excluded from totals.
- **Energy attribution, not addition**: a device's daily `kcal_out`
  already CONTAINS its sessions' energy; session kcal are attributions
  within the day. Cross-app "exercise calories" re-imported from another
  platform are the same joules and never re-added.
- **Conservation tripwires** (flag, never auto-fix): sum(session kcal) >
  daily kcal_out + tolerance; duplicate-suspect sessions that failed the
  fuzzy match narrowly; a date with contradicting high-precedence claims
  (two devices disagreeing beyond tolerance).

New derivations (deterministic, in the read model):

- **`baselines`** [G2]: per metric - median band, trend slopes (30/90/365d),
  weekday profiles, personal records, monthly rollups.
- **`energy_audit`** [G16]: the anchor auditing the ledger - weekly
  implied TDEE back-calculated from canonical kcal_in and the weight
  TREND (~7700 kcal/kg), compared against device kcal_out and logged
  intake. Persistent divergence = model/logging error signal; the anchor
  recalibrates the estimates (MacroFactor-style), never the reverse.
  Weight enters ONLY as the rolling trend - single weigh-ins (hydration,
  glycogen, food transit) are noise by doctrine.
- **`features`** [G17]: the uniform shape grammar, one extractor for ALL
  canonical metrics: last value + freshness, delta and slope per window
  (7/30/90/365d), acceleration (slope-of-slope), local extrema with
  prominence + time-since, plateau spans, variance/stability, position
  vs baseline band, lagged cross-features for registered pairs. Pure
  arithmetic, rebuildable, projected into the read model for the lens.

The semantics registry [G17] (a new artifact class: curated knowledge,
versioned in-repo - `semantics/` - neither data nor code):

- One entry per (metric, timescale, shape): meaning, confidence basis
  (evidence/citation or "operator-settled"), and coaching stance (act /
  watch / ignore / celebrate). Examples: weight 1d max = noise by
  doctrine; weight 90d local min = milestone; rhr 7d slope +5 = fatigue
  tripwire; rhr 90d slope down = aerobic adaptation; weight 21d plateau
  inside a logged deficit = energy-audit trigger, not a stall verdict;
  steps weekday cycle = structure, excluded from trend alarms.
- Verdicts and tripwires REFERENCE registry entries (they are its
  activated subset); the lens pulls chart annotations from it; the coach
  quotes it instead of improvising; `vitai infer` receives it in the
  prompt and proposes ADDITIONS (kind=pattern with evidence), which
  graduate into the registry by human merge - the same
  claims-adjudicated-into-truth shape as everything else in the system.
- **`streaks`** [G8]: per streak definition from vitai.toml - current
  length, best, at-risk flag; forgiveness rules first-class (rest days,
  illness lines, medical restrictions never break streaks).
- `verdicts` v2: gains `goal` column when goals.jsonl lands (contract bump
  to `2` - additive tables are non-breaking, the column is the bump).

Explicitly NOT added: precise GPS traces (stay in the source platform),
food-item logs (the calorie app owns them; totals only), free-floating
key-value context bags (every field earns its place or stays in `note`).

## 5. The UX of the loop (capture must stay cheap)

- **The minimum day is one number.** Everything else is optional and
  screenshot-inferable; the ingest skill fills context fields from what it
  can see and never nags for what it cannot.
- **The daily touch is passive** (connectors) or one line. The
  weekly check-in stays the one interactive ritual: rollup + verdicts +
  streaks + ONE optional subjective question, not a survey.
- **Voice rules apply to the whole loop**: verdict first, never moralise,
  a missed floor is arithmetic. Nudge etiquette is a profile setting the
  coach must respect (question 83).
- **The agent asks at most one question per week back into the record**
  (kind=question) - curiosity is rationed, because every question is
  homework for the athlete.

## 6. Retention and GDPR (the policy, condensed) [G10]

- **Personal single-user use**: the household exemption (Art. 2(2)(c))
  means GDPR does not apply to purely personal processing at all - no
  controller role exists to assign. The content-repo README states this
  plainly.
- **Hosted/multi-user (games, platforms)**: health data is Art. 9 special
  category and large-scale processing of it TRIGGERS a mandatory DPIA
  (Art. 35(3)(b)) before launch. The HOST is controller: explicit consent
  (9(2)(a)) per purpose (tracking, inference, game), per-user stores make
  account erasure (Art. 17) a directory removal and portability (Art. 20)
  a tarball - both provable. **Known limitation**: append-only + git means
  a SINGLE-line erasure request cannot be honored by supersedes alone (the
  bytes persist in history) - hosted deployments need a documented per-line
  purge path (history rewrite or non-git storage of the hosted copy), and
  must say so. Backups must have stated expiry; consent for the inference
  layer is separate from consent for storage.
- **Deletion cascades**: removing observed lines strands inferences citing
  them - the host/coach supersedes or removes inferences whose `evidence`
  no longer resolves. Deterministic derivations rebuild clean by
  construction.
- **Retention tiers**: observed = keep (value compounds; user prunes at
  will), derived = disposable, inferred = prunable and periodically
  re-derivable from what remains.
- **Minimization by coarseness**: place-not-GPS, relationship-slugs-not-
  names, provider-type-not-provider-name. The athlete may go finer in
  their own repo; hosted defaults stay coarse.

## 7. Build order (resequenced by redteam: forgiveness before streaks)

> Execution detail - increments, tests, demo artifacts, timeboxes and
> rabbit-hole escape hatches - lives in [plan-v3.md](plan-v3.md).

1. **goals.jsonl + verdict-goal linkage + thresholds.jsonl** (G6, G14) -
   unlocks a third of the question bank, the game's mint semantics, and
   stops threshold edits from rewriting history.
2. **daily/sessions context + subjective fields** (G1, G3, G4, G7) - one
   additive schema change, one template/skill update.
3. **medical.jsonl** (G11) - episode windows (`resolved_date`) and
   restriction gates land FIRST because streak forgiveness is computed
   from them.
4. **baselines + streaks derivations** (G2, G8) - streaks ship only once
   forgiveness inputs (medical episodes + goal rest_days) exist; shipping
   rigid streaks first would be shipping the harmful version.
5. **journal.jsonl** (G12/G13) and the GDPR policy page (G10) + game
   boundary page (G9).
6. **Enrichment-at-ingest** (G5: weather/calendar) last - valuable, but
   pure context.

## Changelog

- 2026-07-28: created - the 10k-steps trace, 126-question bank, 14 gaps,
  v3 schema proposal. Follow-up to the 7-angle research sweep in
  prior-art.md. Redteamed same day (15 findings integrated: thresholds as
  dated data G14, medical episode windows for computable streak
  forgiveness, build-order resequenced, DPIA + single-line-erasure
  limitations, per-dataset date semantics, slug-scoped supersedes, flat
  scalars, contract-bump rule aligned).
