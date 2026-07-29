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
      +---------------------------- the next day is shaped by it -------------------------+
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
39. Is the streak at risk tomorrow (calendar says travel)? - [G8 + G5 calendar context - NOTE: the calendar half depends on increment 6 (G5), not increment 4 where streaks ship; not fully answerable until then]
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

### 2.16 Goal contribution, milestones, achievements

140. Does ONE event have ONE result? - no: it fans out to every active goal with a SEPARATE per-goal verdict. Walk +2k steps: steps-goal + and calorie-goal +. Run +2k unplanned: calorie-goal + but running-goal neutral/negative and health-goal negative (unbudgeted ramp). [G18: per-goal contribution model]
141. Does exceeding a target always count as progress? - no. A calorie/steps goal is monotonic (more counts). A running or health goal has GUARDRAILS: volume beyond the plan is ramp-rate the athlete didn't budget - it does not advance the goal and may regress it (injury risk is the variable, not distance). [G18: contribution policy per goal]
142. How does a goal know which events feed it, and with what sign? - each goal declares a CONTRIBUTION POLICY: which metrics/activities count, monotonic-or-guarded, and the guardrail (e.g. running goal: planned sessions and within ramp-rate count +; unplanned excess counts 0/-). [G18]
143. When the run helped the calorie goal but hurt the running goal, what does the coach say? - the truth, per goal: "congratulated on the movement and the deficit; but that was unplanned volume - did you consider injury? it doesn't advance your running or health goal, only the calorie one." The injury-attribution doctrine (ramp rate, not weight) drives the caveat. [G18 x coach voice]
144. What is a milestone vs an achievement? - a MILESTONE is a threshold crossed on the way to a goal (halfway to target weight; first sub-25:00 5k), DERIVED deterministically from data + goals. An ACHIEVEMENT is a recorded accomplishment worth keeping (completed a race, hit a streak best), which may be auto-derived or hand-logged. [G18: milestones derived, achievements recordable]
145. When is a milestone celebrated vs noted vs held back? - per the athlete's nudge preference (Q83) and voice rules: celebrate genuine progress, never manufacture it, never celebrate a number that came from a guardrail violation. [G18 x G7]
146. Are milestones/achievements the game's currency? - the game MINTS from verdicts + milestones (attainment, not volume); the ledger stays host-side (G9). vitai records the events; the economy is the consumer's. [G18 x G9]
147. Does an abandoned goal keep its milestones? - yes - the record is history; a milestone reached under a since-abandoned goal still happened. [G18 x G6 lifecycle]

### 2.17 Abstract, external, periodic, interrogable goals

148. Can a goal live entirely in ANOTHER app (Strava Local Legend, a segment crown, a Duolingo streak)? - yes: `metric: external` with a `tracker` reference. vitai cannot auto-verdict it, but it models, tracks (manual/achievement check-ins), reinforces and QUERIES it. [G19: external goals]
149. What does the coach anchor its reinforcement on - the metric or the WHY? - the motivator. "How's your Local Legend attempt going, trying again tonight?" beats "fitness tonight?" because it names the intrinsic driver. The motivator is a first-class, reinforced field, not a note. [G19]
150. Should the app proactively ask about a goal at login/opportune moments? - yes, a distinct PROACTIVE motivator-anchored check-in mode (separate from the weekly review): surfaces the live goal, its progress, and a specific next-step nudge ("6th of 8 gym visits - up for it tonight?"). Rationed and preference-gated (Q83). [G19: proactive check-in coaching mode]
151. Is a goal a one-shot or a recurring container? - either: `period` (none|weekly|monthly|...) makes it recurring with a per-period target and a running count; `on_period_end` defines rollover (reset|carry|escalate). "8 gym visits this month" is a monthly container tracked toward 8. [G19: periodic goals]
152. WHY 8 gym visits - why is the count itself important? - the target is usually a PROXY for a deeper aim (8 visits ~ a consistency habit); `rationale` holds the why-this-number so the coach can interrogate and adjust the scaffold rather than treat the number as sacred. [G19: goal rationale/proxy-awareness]
153. What about next month - and what if I make it or miss it? - `on_success`/`on_miss` model the meaning and the next-period move (escalate the target, hold, or reflect) - never punishment (voice rules); a missed monthly count informs next month, it does not shame. [G19]
154. Is any of this fitness-specific? - no. A goal is a goal: the SAME model serves a language streak, a side-project cadence, a reading habit. This is the platform's goal engine; fitness is one domain of it. [G19 x the platform contract]

### 2.18 Temporal validity - the plan is a timeline, not a current state

155. Looking at a diary day 3 months ago, what goals/targets was I attaining THAT day - not today? - the record must reconstruct the state IN FORCE on that date (goal, calorie target, macros, planned sessions), which may differ greatly from today's. [G20: as-of reconstruction]
156. Are calorie targets, macros, and the planned week mutable current-state or dated history? - today they are current-state (vitai.toml / plan.md prose), so editing them silently rewrites how every past day is judged - the same audit-destroying flaw as unversioned thresholds (G14), now generalized: ALL policy is effective-dated. [G20 generalizes G14]
157. Is HOW OFTEN goals/targets change itself a metric? - yes: churn is a first-class derived signal (edits per goal, per period). Stable plans and thrash look different and mean different things. [G20: change-as-metric]
158. What stops moving the goalposts to fake progress? - nothing blocks it (the athlete owns the record), but an unreasoned or suspiciously-timed change (target loosened right after a bad week, deadline pushed the day it would be missed) INVITES questioning - a coach prompt and an inference signal, never a silent accept. Every change should carry a reason (`set_by` + a why). [G20: anti-gaming, gamification-adjacent]
159. If I loosen a goal, does my past progress re-score against the new easier target? - no: past weeks are judged against the target that was IN FORCE then; loosening today changes only today-forward. The audit chain shows the loosening as an event, dated. [G20 x G14]
160. Can the lens/diary show the goal + targets banner for any historical day? - yes, from the as-of reconstruction - the diff between then and now is itself informative (and a stats-junkie view). [G20 x lens]
161. Does effective-dating apply to PERFORMANCE goals too, not just calorie/macro config? - yes, to ALL of them: a 5k pace target of 5:00/km two months ago is effective-dated exactly like a macro. Browsing back reconstructs that target. [G20, universal]
162. Two months ago I aimed for 5:00/km and hit it; now I run 4:30 - does browsing back feel like a shortfall? - NO. A past day is judged against the standard IN FORCE then, so hitting 5:00 reads as the win it was. Present fitness never retro-diminishes past achievement. [G20 x voice: framing rule]
163. What IS the 5:00 -> 4:30 improvement, then? - the ARC, the good news: a positive trajectory shape (G17) the coach celebrates. Progress is measured against who you WERE, and the distance travelled is the story - not a gap against who you are now. [G20 x G17 x voice]

### 2.19 Forecasting - projecting anchors and fitness forward

164. Where will my weight/body-fat/5k-time be in 4/8/12 weeks IF I hold this plan? - a forecast derivation runs SCIENTIFIC models over planned inputs (planned activities + intake plan) from current anchors + fitness indicators (HR, load, pace) and projects the trajectory. [G21: forecasting layer]
165. Which models, and can it use several or blend them? - a curated MODEL REGISTRY (like the semantics registry): weight via thermodynamic (~7700 kcal/kg), adaptive-TDEE (MacroFactor-style), metabolic-adaptation; fitness via Banister impulse-response (CTL/ATL/TSB), load-to-pace, VO2max trend. The engine runs enabled models AND an ensemble (accuracy-weighted). [G21: model registry + ensembles]
166. Does a forecast ever pretend to be certain? - never: every projection carries a PREDICTION INTERVAL that widens with horizon, visually rendered as a band/fan - a point prediction without a margin is forbidden. Forecasts are the ESTIMATE class (principle 6), clearly marked, never anchors/observations, and NEVER feed verdicts (verdicts judge actuals). [G21]
167. When the next real anchor lands, what happens? - it SCORES every model's past prediction for that date; rolling accuracy reweights the ensemble and sets each model's interval width (continuous backtesting - the anchor auditing the forecast, G16 generalized). [G21: calibration loop]
168. If reality departs from a model that was accurate until now, is the MODEL wrong or is something REAL happening? - the interesting case: a model that backtested well then diverges signals a real-world regime change (a plateau, an adaptation stall, illness, a life event) - NOT model error. "The prediction was correct up until now" is itself the plateau signal; distinguish model-error (inaccurate all along) from regime-change (accurate, then broke) and flag the latter as an event. [G21 x G16 x G17]
169. Is the forecast an LLM guess? - NO. Models are formulas in the deterministic number path; the LLM explains a divergence and may PROPOSE a candidate model, which is backtested and only trusted if it earns accuracy - the same claims-into-truth graduation as the semantics registry. [G21, no-LLM-in-numbers]
170. For any past day, which model was projecting my future, and what did it say? - `forecast(date)`: as-of provenance (G20) - browse back to see which model(s) were mapping your next days/weeks/months from that date, their bands, and whether reality landed inside them. [G21 x G20]
171. Do forecasts consume raw multi-source data or the canonical truth? - the resolved canonical values (conservation, G15); a forecast built on double-counted calories forecasts fiction. [G21 x G15]
172. What does the lens show? - fan-chart forecast bands over the actual trajectory, per-model and ensemble; a backtest-accuracy panel (which model has been right, stats-junkie gold); the as-of "what was predicted for today, 8 weeks ago" overlay. [G21 x lens]

### 2.20 Cross-metric inference (does sleep affect my running? did the wine ruin it?)

173. Does poor sleep hurt my performance, and by how much? - a lagged HEDGED hypothesis: real in the literature (skill -21%, endurance -5.5%, RPE up) but confounded by load/heat/stress/time-of-day in n-of-1 data; surfaced "for you, so far", scoped to session type, never asserted. [G22, full evidence base in docs/cross-metric-inference.md]
174. A lower-HR run burned MORE kcal - is that a mystery? - no: the HR->kcal model (tier 1, known physiology) leaked; the deterministic explanation is duration/body-mass/hills/heat-cardiac-drift/device-algorithm - an explained decoupling, not an anomaly. [G22: leaky-model contradiction]
175. Late-night gym burned less than a morning session of the same duration - circadian metabolism? - almost certainly NOT: in-session EE is ~constant across clock time; the likely cause is device kcal noise (+/-20-30%) or accumulated fatigue lowering output. Do not adjust session kcal for time of day. [G22, circadian is a near-null result]
176. I lost 2kg but my average km/h didn't improve - did the model fail? - no: an expectation-vs-actual signal (G21). Candidates: water/glycogen not fat lost, muscle loss, deficit fatigue/RED-S, near the body-fat floor, or noise over too short a window - enumerated, never "the formula failed". [G22 x G21]
177. Only 3 gym sessions in two weeks - is that a motivation problem? - probably context: correlate the external-load composite (calendar/work/travel/stress) against frequency at a load-leads lag; a context-driven dip gets a reduced-dose target + neutral acknowledgment, NOT a broken-streak alert. Never shame. [G22, behavioral-contextual]
178. Can the coach say "the wine caused your bad run"? - NEVER. Single-incident causal narration is structurally excluded; a bad day enumerates candidate co-factors, names no culprit. The word "causes" is banned outside established physiology. [G22: causal-language firewall]
179. Won't mining many metric pairs nightly manufacture fake insights? - yes if unguarded, so the guards are mandatory and deterministic: detrend before correlating, effective-N (not calendar-N), multiple-comparisons budget/FDR, a-priori lags, change-point segmentation, non-random-missingness policy, out-of-sample backtest before graduation. [G22: statistical guards]
180. How does a mined pattern become trusted knowledge? - the graduation pipeline: infer proposes -> tier-2 hedged hypothesis, flagged -> survives an out-of-sample temporal backtest -> enters the registry STILL hedged (only literature-grade physiology is tier-1 asserted fact) -> coach cites with the hedge re-asserted (anti confidence-laundering). [G22 x knowledge extraction]

### 2.21 Vendor insights - second opinions from other apps' backends

181. Garmin gives a VO2max, WHOOP a recovery score, MFP an adaptive TDEE, Strava a Relative Effort - do we use them? - yes, as valuable INPUT, but as a distinct class: FOREIGN-MODEL ESTIMATES (another vendor's science over their data), never observations, never anchors. [G23: vendor-insight ingestion]
182. Is a Garmin VO2max ground truth? - no: it is a black-box estimate with its own error (device EE 27-93%, VO2max estimates noisy), ingested tagged `derived + source + model-opaque` - audited by the anchors like any estimate, trusted for its evidence not its UI. [G23 x principle 6]
183. What do we DO with a vendor insight? - three ways: CORROBORATE (agrees with vitai's own derivation -> confidence up, an ensemble member in forecasting), CHALLENGE (disagrees -> a flagged signal worth explaining), BACKFILL (vitai has no model for it yet -> a hedged stand-in, clearly marked as the vendor's opinion). [G23]
184. When a vendor score contradicts vitai's SSoT, who wins? - the SSoT: it is transparent, resolved from raw observations + anchors, and auditable; the vendor is a black box. But the disagreement is logged and interesting - a vendor readiness score cratering while vitai's signals look fine is itself a hypothesis to surface. [G23 x G15]
185. Does a vendor insight ever get counted twice or summed with our own? - never: conservation (G15) applies - a vendor's kcal or load is a competing CLAIM about the same physical quantity, resolved by precedence, not added to vitai's. And a vendor estimate cannot masquerade as the anchor that audits it. [G23 x G15 x principle 6]

### 2.22 Situational context, facilities, and geodata

186. Should the coach explain/comfort a scary number without being asked? - YES: a big single-day deficit, two apps disagreeing, a weight spike - explain it naturally, anchor on the trend, reassure. Comfort is coaching; a worried athlete disengages. [G34, coach behavior]
187. Is a missing weigh-in on holiday non-compliance? - NO: no scale at the location EXPLAINS the missingness. Context turns "missing data" into "expected gap" - reassure ("re-anchor when home"), never flag it, never shame. [G34 x P7 x G27]
188. Can the athlete run in a heatwave with no gym/AC? - the plan must know: FACILITY + weather availability constrains what the coach prescribes (no midday run in a heatwave, no gym where there's none - adapt to early/indoor/rest). [G34, context constrains the plan/scheduler]
189. Does "vacation" vs "deadline week" vs "weekend with friends" change how a week reads? - yes: MODE sets the baseline and expectations (a good fortnight on holiday is not a trend; a social weekend explains alcohol + a step dip). A dated situational mode is first-class context. [G34, effective-dated P2]
190. Where do routes and GPS of runs/walks/commutes live, and where I was at what time? - geodata: route/elevation on sessions, plus a where-was-I-when signal fed from MANY sources - photo geodata, calendar events, Google Maps / Waze route history, chat mentions - to infer mode/facility/place. [G35: geodata & location-time provenance]
191. Isn't storing my GPS a privacy risk? - coarse by default (place/route-slug, not raw traces - the G32 minimization line); finer opt-in per the athlete; multi-source location is claims (P1), reconciled, and enrichment is stored-at-ingest not fetched-at-derive (G5). [G35 x G32 x G5]
192. Did I lose 6 kg of fat, or 6 kg? - NEITHER cleanly: in a real cut, fat mass can fall ~3 kg (a clean straight line) while the scale falls ~6 kg - the rest is lean/glycogen/water. Scale weight is a LOSSY proxy; judge the fat-mass trajectory, store `kg`+`body_fat_pct` and DERIVE the split. [G36]
193. So how many calories is 1 kg for me? - name the denominator first. Physiological energy per SCALE-kg is ~6,000-6,500 for a well-run cut (a scale-kg is a fat+lean+water blend, all cheaper than pure fat). But TRACKED-deficit per FAT-kg often reads far ABOVE 7,700 (five-figure) - and that is not physiology (a fat-kg is always ~7,700), it is your tracking running optimistic (TDEE logged high, food logged low). The excess IS your correction factor: multiply logged deficit by ~0.7 to get the real one. [G36, calibration]
196. Why did it take me ~11,000 tracked kcal to drop 1 kg of fat, not 7,700? - because ~7,700 is physiology and ~11,000 is your LOGS. The 1.4x gap is tracking optimism (generous expenditure model + under-logged intake + no metabolic-adaptation discount), not a slow metabolism. The fix is the calibration, not more deficit: trust your tracked deficit ~30% less. The adaptive-TDEE + anchor-audits-source loop learns this number for you. [G36 x G24, adaptive-TDEE]
197. I've got a GPX - now what? Extraction isn't the point. - right: a GPX is a list of points until the engine INTERPRETS it. Tier-1 geometry is deterministic (from->to, loop/lap/point-to-point, distance, elevation, "120 m shorter than usual because you cut the car park") and lives in the number path - no confidence score, it's computed truth. [G35 tier 1, P4]
198. What's my "normal route"? - the modal path for an origin->destination pair, learned by clustering your past traversals into a named canonical route ("gym commute", "Fort loop") in the route registry - effective-dated, because routes change (construction, a move, a new shortcut) and a past walk is judged against the library in force THEN. [G35 tier 2, P5 x P2]
199. Where could I add 100 m, or a km, or walk somewhere quieter? - that's a MODEL suggestion over external map data (OSM graph, road-class weights), not a fact about your data: it lives in the proposals layer with provenance, never the number path, and is always anchored on a goal (hit the step/distance target) + a stated preference (quiet/green/safe). The coach offers it opportunely ("moat loop is 2.4 km on a quieter path - want it today?"), never asserts it. [G35 tier 3 = G22/G23 vendor-model class]
200. Isn't routing me around my own neighbourhood the most sensitive data of all? - yes: "avoid busy streets" implies map/road data around home and routine spots, so this tier is strict opt-in, coarse-area by default, and routing runs on-boundary (local), never by shipping home coordinates to a third party. Geometry+facts store at ingest (deterministic); live routing suggestions are non-deterministic proposals - which is precisely why they sit in a different, lower tier. [G35 x G32 x G5]
194. Bioimpedance says I lost muscle - did I? - almost certainly not on a short window: an FFM read can bounce ~1 kg in a week (hydration), so short-term FFM is too noisy to call muscle change. Store the reading WITH its band and downgrade trust; never announce muscle loss off a jittery signal. [G37 x G36]
195. Can the app tell it was a holiday without me saying so? - yes: an overnight >1 kg jump reads as a feast (water/glycogen), a run of `intake==expenditure` exact ties reads as placeholder fills (counting stopped), and a weight plateau while the deficit still books reads as the cut paused. Infer mode=holiday + a low-trust window; confirm, don't overwrite. [G38 x G34 x G26]
201. From one walk, what should the app WONDER? - did I stop, where, how long; did I break a sweat; was it a loop or an errand; how busy the street; was I with someone; did I buy something. The event spawns the question SET automatically - the skill is not answering all of them but knowing WHICH it can answer and which only you can. [G39]
202. Which of those answer themselves? - stop/where/how-long/sweat/shape/pace are AUTO from GPS+HR (deterministic); shop-nearby/street-busyness are INFERENCE needing external map data (opt-in); with-a-kid / bought-something / why-you-stopped are USER-ONLY - not in any sensor at any fidelity. The app fills the first, hedges the second, asks at most 1-2 of the third, and never the same one twice in a day. [G39, answerability tiers]
203. Isn't this just a fancy activity tracker? - no: it is a guardrailed WORLD MODEL of you - a symbolic belief-state (facts+provenance, goals+context, update rules), not a learned net. Every value is inspectable, effective-dated, firewalled; the LLM only narrates and asks. The richest signal today was an ABSENCE (an untracked 8-min gap = the real stop), which a tracker logs as nothing and a world model reads as an event. [world-model frame]
204. What happens to my data after years - does it bloat forever? - no: raw ages to LOSSLESS cold-store (never deleted or lossily cut - determinism + old-day correction need it whole), while the warm read model keeps a per-metric fidelity ladder (14d full ... 10y 1/20). Old HR samples decay to gist, weigh-ins stay full, an old walk keeps its route SUMMARY not its 800 raw points. Reversible: any period rehydrates and rebuilds bit-identical. [G41]
205. When I message the coach, does it reload my whole life? - no: it assembles the minimum sufficient context for THAT moment - a compact standing summary + recent full detail + whatever old period your question makes relevant, paged back up from cold ("vs my last cut" rehydrates the 2y-old block). Same pattern as MemGPT/Letta and your own MEMORY.md index. The number-path still computes over the full record, never the window. [G42 x P4]
206. I open the app and say "hello" - what does it already know, and what does it ask? - it has assembled a standing state (goals in force, phase, mode, today's steps + calendar + weather for your KNOWN place) BEFORE you speak, then surfaces the one live decision (tonight's run, given heat + your evening obligation) and asks only the thing it cannot derive: your intent. It does NOT ping GPS/photos on hello - stated context over surveillance. Full trace in [cold-boot-greeting.md](cold-boot-greeting.md). [G42 x G39 x G34]
207. Is the app there to inform, engage, correct, or chastise me? - engage/serve first, inform second, help you decide third; correct only gently and only facts; CHASTISE never (P7). A missed run in a heatwave on holiday is not a failure and the app cannot frame it as one. The greeting celebrates what's real, surfaces one decision, offers options, and the fallback still counts as a win. [P7 x G39]
208. I said "I like running to Zwin" in chat - how does that become something the app KNOWS? - it is parsed into a proposed typed claim (preference: prefers-destination=Zwin, domain=running), effective-dated, provenance=stated-in-chat, and you confirm it; then a lookup (active running preferences) retrieves it later. The model grows from what you say - the ask-loop run in reverse. [G43]
209. How long is my run to Zwin and back, and does it hit tonight's target? - first check YOUR OWN history (Strava/Polar GPX = deterministic distance/time); only if you have no such route does it fall to an external OSM estimate (tagged inference). Then reconcile that route's distance/time against tonight's target (from the coach or your Runna import) - fits? propose it; short? extend or pick another. [G44 x G45]
210. What should the app look up LIVE vs just know? - it routes every fact: STORED (goals/mode/preferences/your routes) it reads; DERIVED (route length, time-at-pace, deficit) it computes; LIVE (weather/fire-risk, trail closures, bus times, novel routing) it looks up only when a decision needs it, only if granted, coarsened. Safety (a fire advisory on a reserve run) jumps the queue and is raised unprompted. On boot it reads stored + granted-volatile only. [G46]
211. Can I bus/drive out and run one-way home? - yes, a multi-modal journey: a transit leg (bus schedule / drive+park) + a one-way run leg sized to your goal ("bus east, run the 12 km back along the coast"). The app plans the composite, not just loops from your door. [G44]
212. You gave me a whole home workout then asked at the END whether I own a step - wrong order? - yes, and it is a design bug not a slip: a question whose answer CHANGES the plan is BLOCKING and belongs before it (or as an explicit branch, "step -> A, bare floor -> B"). A confident plan built on an unstated assumption, footnoted by the question that would have changed it, is the failure mode. [G47]
213. Do I have to tell it every session what's in the flat? - no: equipment / AC / noise-constraints attach to the PLACE, asked once when the place enters the model, reused forever. "Do you have a step?" is a one-time fact, not a per-session question. [G48]
214. How does it know WHEN a session is even possible? - dependents' ages + routine (awake / screen-time / asleep), the partner's schedule and the calendar produce availability WINDOWS, intersected with the heat and daylight windows. A proposal lands in a real window ("20:00 while they're on the sofa - they can join" vs "21:00 once they're down, keep it quiet"), and dependent-care can veto a plan outright (a stairwell session means leaving the flat). Ages are DATA - never guessed. [G49]
215. My preferences differ by situation - how is that not a contradiction? - they are SCOPED: "runs to Zwin" is place-scoped, "short circuits" may be cutting-phase-scoped, "no burpees" is global. Most-specific wins on conflict, and the coach can name which preference drove a proposal. Learned from what you SAY (higher trust) and what you actually DO vs skip (lower trust, never asserted back as if you'd said it). [G50]
216. Why does the app need to know about my partner, my kids, my colleagues? - because people are CONSTRAINT SOURCES, not just contacts. Their state changes what I can do: my partner is on the crosstrainer so I cannot use it; they go out so I hold the kids and cannot leave for a 5k; a friend is free and runs my pace so a solo run becomes a joint one. Relationship, participation capability, availability/travel state, coarse restriction. [G51]
217. Isn't storing data about other people creepy? - it would be, so the line is hard: MINIMUM FOR PLANNING only - available or not, can-they-join, a coarse restriction ("not running for now"). NEVER their medical detail, their metrics, or their location history. Their health data is theirs, in their own record if they want one; minors get extra restraint. A person entity is a planning aid, not a dossier. [G51 x G32]
218. The flat has a crosstrainer - so I can always use it? - no: having an asset and it being FREE are different facts. Shared assets have exclusive use over a window, so a household member's session blocks mine, and the same applies to the car (no car -> no drive-to-trailhead journey). The real slot is (my free window) x (asset free) x (care duty clear), and a blocked asset is a reason the coach states, not a silent omission. [G52 x G48]

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
| G18 | **Goals are flat - no contribution model, no milestones** (operator doctrine, 2026-07-28) | CRITICAL, part of G6 | One event feeds many goals with DIFFERENT signs: a walk advances steps + calorie goals; an unplanned +2k run advances the calorie goal but NOT the running/health goal (unbudgeted ramp, injury risk) and may regress it. Goals need a CONTRIBUTION POLICY (which events count, monotonic vs guarded, the guardrail) so exceeding a target isn't blindly "progress". Milestones (thresholds crossed, derived) and achievements (recorded accomplishments) are first-class; the coach's per-goal verdict is what makes "congratulate the walk, question the run" possible. |
| G19 | **Goals too concrete - no external/abstract, periodic, motivator-reinforced, interrogable goals** (operator doctrine, 2026-07-28) | HIGH, part of G6 | A goal may live in ANOTHER app (Strava Local Legend), be RECURRING (8 gym visits/month with rollover), and its motivator - not its metric - is what the coach should reinforce ("how's your Local Legend attempt going?"). Goals need: `external` metric + tracker ref, a first-class reinforced `motivator`, `period`+`on_period_end`, a `rationale` (why THIS number - it's a proxy), `on_success`/`on_miss` meaning, and a PROACTIVE motivator-anchored check-in mode. Domain-agnostic: same engine for a language streak or a side-project. |
| G20 | **No temporal validity - the plan is treated as current-state, not a timeline** (operator doctrine, 2026-07-28) | CRITICAL, generalizes G14 | ALL goals, targets and metrics change - performance (5k pace, distances, HR zones) as much as calorie/macro config; the record must reconstruct the state IN FORCE on any past date (the diary shows THAT day's targets), never re-score history against a newer target. ALL policy effective-dated (G14 generalized). Change is a metric (churn), unreasoned/suspiciously-timed edits invite questioning (anti-goalpost-moving, surfaced never blocked). FRAMING RULE: a past achievement is judged against its own standard and never retro-diminished by present fitness - hitting 5:00/km then was a win; running 4:30 now is the ARC, celebrated as trajectory, not a shortfall. |
| G21 | **No forecasting layer** (operator doctrine, 2026-07-28) | HIGH | The engine describes past/present but cannot PROJECT: future anchors (weight, body measurements) and fitness from current metrics + planned inputs, via a curated registry of scientific models (thermodynamic + adaptive-TDEE weight; Banister/CTL-ATL-TSB, load-to-pace fitness) and their ensembles, with mandatory visual prediction intervals. Each new anchor backtests + reweights the models (calibration = anchor auditing forecast, G16 generalized); a model accurate-until-it-diverges signals a real regime change (plateau/stall), not model error. Predictions are the ESTIMATE class - deterministic formulas not LLM guesses, never feeding verdicts - and are effective-dated with model provenance (browse any past day to see which model was mapping your future). |
| G22 | **No cross-metric inference layer** (operator examples + researched, 2026-07-28) | HIGH | Relating metrics (sleep->performance, weight->pace, HR->kcal, context->adherence) on one person's sparse autocorrelated data manufactures spurious insight unless disciplined. THREE trust tiers: deterministic physiology (encode, may state cause), hedged hypothesis ("for you, so far", never graduates to fact), structurally-excluded single-incident causal narration (banned). Mandatory statistical guards (detrend, effective-N, multiple-comparisons, a-priori lag, change-point, missingness, out-of-sample backtest). Causal-language firewall: no "causes" outside tier 1, enumerate co-factors never name one, n-of-1 ceiling, medical->clinician, never-moralise. Evidence base + full design: docs/cross-metric-inference.md. |
| G23 | **No vendor-insight ingestion/adjudication** (operator doctrine, 2026-07-28) | MEDIUM | Other apps (Garmin VO2max, WHOOP recovery, MFP adaptive TDEE, Strava Relative Effort, Runna predictor) compute their own science-backed estimates. Ingest them as a distinct class - FOREIGN-MODEL ESTIMATES (principle 6, class 3), tagged derived+source+opaque, never observations/anchors - and use them to CORROBORATE / CHALLENGE / BACKFILL vitai's own derivations (ensemble members in forecasting). Same critical eye: black boxes with their own errors, audited by the anchors, arbitrated by the transparent SSoT, subject to conservation (a competing claim, never summed, never the auditing anchor). |

### Consolidating gaps G24-G33 (whole-model redteam, 2026-07-28)

Found by the four-lens whole-model review; each fills a symmetry hole in a
core principle (see [model.md](model.md) Part 3 for the full mapping).

| # | Gap | Severity | Principle it fills |
|---|---|---|---|
| G24 | **Source-reliability learning** - observation sources earn/lose precedence by backtest against anchors, not a static onboarding rank (anchor-audits-SOURCE). | HIGH | P1 |
| G25 | **Schema-evolution robustness** - CODE-VERIFIED: additive nullable fields break validation of every pre-existing line; needs per-line schema generation + a "key postdates this line" validator rule + a shape-history-stability test. Blocks increment 1. | CRITICAL | P8 / artifact-1 |
| G26 | **Ingestion/build integrity** - parse fault-tolerance (one bad byte must not abort the whole build); exact-duplicate detection; per-line identity for connector idempotency (Q127); cross-OS + hash-seed determinism; LF gitattributes. | HIGH | P1 (syntactic) |
| G27 | **Cold-start & maturity** - minimum-N per derivation; a cold/warming/stable signal the deterministic engine surfaces (its own doubt); calendar-day not entry-count rolling windows. | HIGH | P3 |
| G28 | **Safety escalation** - DETERMINISTIC severity->action (not LLM prose): cardiac/red-flag symptom class, absolute-danger thresholds, a RED-S composite, a fast path bypassing the weekly cadence, the written never-shame carve-out. | CRITICAL | P4 / P7 |
| G29 | **Correction cascade & unified provenance** - `vitai explain <metric> <date>`; a correction that retracts/annotates already-surfaced milestones/streaks/inferences/backtests; resolution decisions as routine explanations. "Late truth cascades" as one named doctrine. | HIGH | P6 |
| G30 | **Temporal foundations** - timezone/offset on date + start_time; an explicit dated day-boundary rule; DST arithmetic. Determinism is only accidental without it. | HIGH | P2 / P1 |
| G31 | **Registry & config effective-dating** - registries get as-of + decay audit; streak definitions migrate out of mutable vitai.toml; thresholds get a correction marker; estimate-vs-estimate ties break on accuracy not home-team. | MEDIUM | P2 / P5 |
| G32 | **Access scope & consent-as-data** - per-consumer redaction/ACL; a consent ledger as data; deletion cascade widened to all artifacts + host boundary; household/minor stance. | MEDIUM (HIGH hosted) | P5 / P8 |
| G33 | **Reflexivity & the subtractive primitive** - coach-induced-change as a G22 confound class; per-metric suppression ("leave this alone"); capture-level observer effect; units storage-vs-display. | MEDIUM | P7 / P8 |
| G34 | **Situational context & facilities** (operator, 2026-07-29) - a dated `context.jsonl` (mode: vacation/work/conference/weekend/social/deadline/heatwave/travel + facilities: scale/gym/AC/routes + location) that: sets the baseline (mode-aware), EXPLAINS missingness (no scale -> weigh-in expected-absent, never non-compliance/shame), CONSTRAINS the plan+scheduler (no heatwave run, no gym where there's none), and drives PROACTIVE explain/comfort when a number looks scary. | HIGH | P7 / P8 / P2 |
| G35 | **Geodata & location-time provenance** (operator, 2026-07-29) - routes/GPS on sessions + a where-was-I-when signal fed from many sources (photo geodata, calendar events, Maps/Waze route history, chat mentions) to infer mode/facility/place. Coarse-by-default (place/route-slug not raw traces, G32), finer opt-in; multi-source = claims (P1); stored-at-ingest (G5). | MEDIUM | P1 / G5 / G32 |
| G36 | **Composition-resolved weight & the partitioning model** (operator, 2026-07-29) - scale weight is a LOSSY proxy for the goal-relevant quantity (fat) and cannot by itself tell fat loss from recomposition. Observed atoms = `kg` + `body_fat_pct`; fat mass and fat-free mass are DERIVED (never stored, rebuildable). The trustworthy signal is the weeks-smoothed fat-mass trajectory, not net scale weight - a holiday water/glycogen swing moves weight without moving fat, and bioimpedance FFM is too noisy to read short-term muscle change. A p-ratio partition forecast predicts fat- and lean-mass trajectories separately (calibrated, not the fixed textbook assumption); a recomposition detector fires when fat-trend<0 AND FFM-trend>=0. Personal kcal-per-kg is CALIBRATED from the fat/lean split (~6,000-6,500 kcal/scale-kg for a well-run cut), not the naive 7,700. | HIGH | P1 / P3 / P4 |
| G37 | **Measurement-uncertainty intervals on OBSERVATIONS** (operator, 2026-07-29) - an observed reading carries an instrument band (`kg_lo`/`kg_hi`, `body_fat_lo`/`body_fat_hi`), distinct from a FORECAST error band. A wide band (bioimpedance, a jittery scale) downgrades trust in that reading without discarding it; band ordering (lo<=point<=hi) is validated. Epistemic tiering now spans observations, not just inferences. | MEDIUM | P3 / P1 |
| G38 | **Context & data-quality INFERRED from record shape** (operator, 2026-07-29) - mode (G34) and tracking-lapse (G26) can be READ OFF the data when undeclared: `intake==expenditure` exact ties for N days = placeholder fill (not measurement); an overnight >1 kg jump = water/glycogen feast, not fat; a plateau while a deficit is still booked = the cut paused. The engine flags low-trust runs and proposes a mode; the athlete confirms. Inference, never silent overwrite (P1). | MEDIUM | G34 / G26 / P1 |
| G39 | **Event -> tiered question loop** (operator reframe + prior-art sweep, 2026-07-29) - an event posts to a BLACKBOARD; knowledge sources fill a SLOT SCHEMA, each slot tagged `auto-filled / inferred-hedge / must-ask / skipped` (the answerability tiering). Unfilled slots ranked by info-gain x coaching-value / capture-cost (active learning + Horvitz); asked at a JITAI decision point under an EMA budget, no same-day re-ask ("never nag"). Auto facts stated, inferences hedged, only user-only slots asked. A skipped slot is data. See [prior-art-world-model.md](prior-art-world-model.md). | HIGH | P3 / P7 / P8 |
| G40 | **Semantic-trajectory layer** (prior-art sweep, 2026-07-29) - GPS->narrative, deterministic-first: STOP/MOVE segmentation (CB-SMoT speed/radius/time), speed-band mode (walk<7/run<15/bike<25/car), two-stage POI enrichment (lookup + time prior, LLM only for the ambiguous residual). Privacy is a PIPELINE property: on-device reverse-geocode against a cached POI tile, coarsen to 100-300 m before any cloud hop. The concrete build of G35 tiers 1-2. Gaps/absences (the untracked 8-min stop) are first-class events. | MEDIUM | P4 / P1 / G35 |
| G41 | **Data lifecycle: lossless cold-store + progressive warm rollup** (operator, 2026-07-29) - raw is NEVER lossily reduced (determinism + late-correction need it); it ages to high-ratio LOSSLESS cold-store (columnar+zstd / Gorilla). The warm read model carries a per-metric, effective-dated retention/rollup LADDER (14d full ... 10y 1/20), per value-density (HR decays fast, weigh-ins forever, old geodata's warm form is its G40 summary). Rollups are derived, provenance-tiered, reversible; coarse old data confesses its fidelity (G27). Prior art: RRDtool/Whisper/Prometheus/Timescale/Gorilla - but cold-store lossless instead of delete. DEFERRED until data grows. | MEDIUM | P4 / P3 / P2 / P5 |
| G42 | **Moment-relative context assembly** (operator, 2026-07-29) - the coach loads the minimum SUFFICIENT slice at moment T: a compact standing state summary (MEMORY.md-index analogue) + full recent detail + any old period the CURRENT QUERY pages in, rehydrated to higher fidelity on demand. Recency + relevance + question drive the working set; the G41 ladder is only the default. Firewall: assembly feeds NARRATION only, never the number-path. Prior art: MemGPT/Letta virtual context management, ACT-R retrieval, the operator's own MEMORY.md discipline. Couples to G41. DEFERRED. | MEDIUM | P4 / P8 / P3 |
| G43 | **Conversational capture -> typed claims** (operator, 2026-07-29) - the model GROWS from what you say: a chat statement ("I like running to Zwin", "Meerminlaan 30 is the flat") is parsed into a PROPOSED typed claim (context/goals/preferences/places), effective-dated, provenance=stated-in-chat, confirmed by the athlete, never silently written. The G39 loop run in reverse (extract + confirm, not ask). LLM proposes STRUCTURE not numbers (P4). | HIGH | P1 / G39 / P4 |
| G44 | **Places, routes & multi-modal journeys** (operator, 2026-07-29; extends G40) - named PLACE entities (coarse coords, G32); ROUTES between them SOURCED (own Strava/Polar history = deterministic w/ real distance/time; external OSM route = inference); route matching/adaptation (exact / near-match / route-fresh, own-history wins); JOURNEYS composite/multi-modal (transit leg + one-way run leg sized to the goal - "bus east, run 12 km home"). | MEDIUM | G40 / P1 |
| G45 | **Plan <-> route <-> goal reconciliation** (operator, 2026-07-29) - a scheduled session's TARGET (coach plan OR Runna/external) vs a candidate route's ESTIMATED params: does the route ACHIEVE the target? match->propose, mismatch->extend/shorten/alt + say why. Multi-source plans (coach vs Runna) reconciled like conserved claims - one canonical target, not summed. | MEDIUM | P1 / increment-1 |
| G46 | **Source router + gated live world-lookups** (operator, 2026-07-29; extends G42) - every needed fact routes to STORED (read DB) / DERIVED (compute) / LIVE-LOOKUP (external). Live gated by CONSENT + NECESSITY (only when a decision needs it, not on every boot) + PRIVACY (on-boundary). SAFETY (fire advisory, closure on the route) overrides the capture budget, surfaced proactively. On boot: stored + granted-volatile only; defer routing/transit/fire. The machinery under the cold-boot greeting. | HIGH | P4 / G32 / G42 |
| G47 | **Blocking vs enriching questions** (operator, 2026-07-29; refines G39) - a slot whose value would CHANGE the recommendation is BLOCKING: resolve it BEFORE the answer (ask first, or branch explicitly "step -> A, bare floor -> B"). Enriching slots may trail or drop. NEVER a confident single plan resting on an unstated assumption + a footnote asking the question that would have changed it. Prefer branching when cheap. An unknown must be visibly unknown (saying "at their age" without holding the age is fabrication). | HIGH | G39 / P7 / P1 |
| G48 | **Per-place facility & equipment inventory** (operator, 2026-07-29; extends G34/G44) - a PLACE carries persistent effective-dated EQUIPMENT (step/band/kettlebell/mat/bike) + AMENITIES (AC/fan/stairwell/garden/scale) + CONSTRAINTS (neighbours/noise/floor/space/hours). Captured ONCE on place-onboard or from chat (G43), reused forever. Turns "do you have a step?" from a per-session question into a one-time fact; the planner may only propose what the place affords. | MEDIUM | G34 / G44 |
| G49 | **Household, dependents & availability windows** (operator, 2026-07-29) - WHO is around and WHEN a session is possible: dependents with AGES (data, never assumed - gates what they join and whether they can be left), their routine (awake/screen/asleep), partner schedule, and the resulting availability WINDOWS intersected with heat/daylight (G34) + calendar. A proposal must land in a real window ("20:00 while they're on the sofa" vs "21:00 once down, keep it quiet"). Dependent-care is a hard constraint that can veto a plan. | MEDIUM | P2 / G34 |
| G50 | **Context-scoped preferences** (operator, 2026-07-29) - a preference carries a SCOPE `{place?, mode?, phase?, time-of-day?, weather?, with-whom?}`: "runs to Zwin" is place-scoped, "short circuits" may be phase=cutting-scoped, "no burpees" is global. Most-specific wins (CSS-like), ties by strength then recency; the coach can name which preference drove a proposal. Learned from statement (G43, higher trust) AND behaviour (done-vs-skipped, lower trust, never asserted as stated). | MEDIUM | P2 / P5 / G43 |
| G51 | **Person model: people as typed entities AND constraint sources** (operator, 2026-07-29; subsumes G49 dependents) - a `people` dataset: relationship (partner/child/family/friend/colleague/coach), household + dependent flags (age as DATA), participation capability (sports/level/what they can join), availability + travel state (home/out/away/holiday/conference, WITH-me or without), coarse restriction ("no running till X", not a diagnosis). Key semantic = CONSTRAINT PROPAGATION: their presence can block me (shared asset, G52), their absence can block me (care duty falls to me), their availability can expand me (partner run, kids join). THIRD-PARTY PRIVACY IS A HARD LINE: minimum-for-planning only, never their medical detail / metrics / location history; a person entity is a planning aid, not a dossier. | HIGH | P2 / G32 |
| G52 | **Shared-resource contention & allocation** (operator, 2026-07-29; extends G48) - G48 says a place HAS an asset; this says whether it is FREE. Shared assets (crosstrainer, car, bike, mat, bookable slot) have exclusive use over a window; a household member's use BLOCKS mine. Generalizes past equipment (partner has the car -> the drive-to-trailhead journey is off). The real schedulable slot = (my free window) x (asset free) x (care duty clear). A blocked asset is a REASON the coach states, never a silent omission. | MEDIUM | G48 / P2 |

Merges (not new gaps): G1 folds into G15; G2 becomes a projection of G17;
G10 scope-widens into G32; the "late truth cascades" pattern unifies G16 +
G21 + G29 as one doctrine. Full rationale in model.md Part 4.

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

- **`goals.jsonl`** [G6, G18, G19]: `date` (declared), `slug`, `title`,
  `metric` (weight_kg | steps | distance_km | race_time_s | gym_visits |
  manual | **external**), `tracker` (G19: for `external` goals, where it
  lives - e.g. `strava:local-legend:<segment>`, `duolingo:streak`;
  vitai can't auto-verdict it, tracks via manual/achievement check-ins),
  `target`, `deadline`, `status` (active|paused|achieved|abandoned),
  `set_by`, `motivator` (G19: the reinforced WHY - the coach anchors its
  reinforcement here, not on the metric; may reference an ambition slug),
  `accountability`, `rest_days`,
  `contribution` (G18: `monotonic` | `guarded:<rule>`),
  `period` (G19: none|weekly|monthly|... - recurring container with a
  per-period target and running count),
  `on_period_end` (G19: reset|carry|escalate),
  `rationale` (G19: why THIS target - it is usually a proxy for a deeper
  aim, e.g. gym_visits=8 ~ a consistency habit; lets the coach interrogate
  the number instead of treating it as sacred),
  `on_success` / `on_miss` (G19: what the outcome MEANS and the
  next-period move - reflection/escalation, never punishment), `note`.
  Edits = supersedes within slug. Verdicts gain goal linkage for
  computable metrics; `manual` = human-judged, `external` = lives in
  another app (both no auto-verdict). Domain-agnostic by design (G19): the
  same shape serves a language streak or a side-project cadence.
- **`achievements.jsonl`** [G18]: recorded accomplishments worth keeping -
  `date`, `slug` (which goal, or null for standalone), `kind`
  (milestone | achievement | pr), `title`, `metric`, `value`,
  `source` (derived | manual), `note`. Milestones are usually auto-derived
  (a threshold crossed); achievements may be hand-logged (finished a
  race). Persist through goal abandonment - a thing that happened
  happened.
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
- **`thresholds.jsonl`** [G14, G20]: `date` (effective-from), `key`
  (steps_floor | easy_hr_cap | **calorie_target | protein_g | carbs_g |
  fat_g** | ...), `value`, `set_by`, `reason`, `note`. Generalized from
  thresholds to ALL effective-dated policy: the calorie target and macros
  live here too (retired from mutable `vitai.toml`, which stays the
  bootstrap/current view). The engine judges each week/day against the
  value IN FORCE then; editing a value changes only today-forward.
  Every change carries a `reason` (G20 anti-gaming). Planned-session
  structure, when it becomes data, follows the same effective-dating.
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
  to `2`).
- **`contributions`** [G18]: per (event, goal) the SIGNED verdict a
  contribution policy produces - the deterministic fan-out that lets the
  coach say "advanced your calorie goal, not your running goal" and lets a
  milestone fire only on genuine, in-policy progress. The event->many-goals
  matrix, computed at build.
- **`milestones`** [G18]: thresholds crossed on the way to active goals,
  derived (halfway-to-target, first-time-under-a-race-time,
  N-week-streak-best). Feed the achievements record + the game mint;
  never fire on a guardrail-violating number.
- **as-of reconstruction** [G20]: a deterministic function `state(date)` ->
  the goals, thresholds, targets and macros IN FORCE on that date (latest
  effective-dated record with `date <= D`, honoring supersedes). Every
  historical derivation uses it; the lens diary banners a past day with
  its OWN targets; the then-vs-now diff is a stats-junkie view.
- **`plan_churn`** [G20]: change-as-metric - edits per goal/target per
  period, time-to-first-edit after declaration, and a flag for
  suspiciously-timed changes (a target loosened right after a missed week,
  a deadline pushed as it would be breached). Feeds a coach questioning
  prompt and an inference signal; surfaced, never blocking.

The forecasting layer [G21] (deterministic; uses the model registry, scored
continuously; predictions are estimates, never anchors and never fed to
verdicts):

- **model registry** (`models/`, curated + versioned like `semantics/`):
  one entry per (target, model) - inputs, formula, parameters, provenance.
  Weight: thermodynamic (~7700 kcal/kg), adaptive-TDEE, metabolic-
  adaptation. Fitness: Banister impulse-response (CTL/ATL/TSB),
  load-to-pace, VO2max trend. Each is a scientific formula, not a guess.
- **`forecasts`** derivation: for each forecastable target, run enabled
  models + an accuracy-weighted ensemble over the PLANNED inputs (planned
  sessions, intake plan) from the current canonical anchors and fitness
  features -> a dated trajectory with a PREDICTION INTERVAL that widens
  with horizon. Model provenance stamped on every projection.
- **`backtest`** derivation: each landed anchor scores every model's prior
  prediction for that date; rolling error reweights the ensemble and sets
  interval widths. This is the anchor auditing the forecast (G16
  generalized from one energy model to many).
- **divergence detection**: separate model-error (inaccurate throughout)
  from REGIME-CHANGE (backtested well, then broke) - the latter is a real
  event (plateau/adaptation-stall/illness/life), flagged via the shape
  registry (G17), never silently re-fit away.
- **`forecast(date)` as-of provenance** (G20): which model(s) projected
  forward from any past date, their bands, and whether reality landed
  inside - browsable in the diary and lens.

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
