# Validation: three synthetic athletes, and where the model broke

The model was built from one athlete's life. That is a sampling problem, so it
was tested against three fictional people who know nothing about it - each
constructed to stress a different axis - by role-playing a real coaching
conversation and watching where the model had nothing to offer.

The personas are synthetic. Nothing here is a real person's data.

| | Who | Axis under test |
|---|---|---|
| **A** | ICU nurse, 34, rotating night shifts, no wearable. Wants ONE pull-up. Exam in 4 months. | temporal structure, goal kinds, deviceless, competing goals |
| **B** | 31, five months post-C-section, exclusively breastfeeding, self-imposed 1200 kcal, wants 12 kg in 6 weeks. | physiological state, unsafe goals, voice under emotional load |
| **C** | 58, warehouse supervisor, type 2 diabetes, downplayed chest twinges, hates apps. Daughter's wedding in 14 months. | safety escalation, low-data, third-party constraints |

**Headline: the model held on judgement and voice, and broke on structure.**
Every one of its coaching instincts (substitute rather than refuse, never shame,
anchors audit estimates, guard the ramp) survived contact. What failed was the
scaffolding underneath: the calendar week, the midnight day, the quantity goal,
the assumption of a device, and - most seriously - the assumption that a red
flag arrives as data.

---

## CRITICAL

### F1. Red flags arrive as downplayed prose, never as data (G59)

The most important finding of the exercise, and it happened twice.

Persona C buried this at the bottom of a long message: *"eight months back I had
a turn with some chest pain... get the odd twinge now and again since but it's
nothing, not really worth going on about."* One question later it turned out the
twinges come on with EXERTION and settle with rest - the pattern that has to be
assessed urgently.

Persona B slipped hers into a parenthesis: *"is that why I nearly blacked out
standing up on Tuesday? I just told myself I stood up too fast."*

**Neither would ever have been entered into `medical.jsonl`.** The person does
not believe it is data. They are actively minimising it, often precisely because
they are frightened. G28 as designed reads severity from a structured entry or a
threshold breach, and would have seen nothing at all in either case.

The resolution has to preserve P4, so the split is: **the LLM recognises and
CLASSIFIES symptom language into a structured claim (the G43 capture path); the
deterministic engine maps severity to action and emits hardcoded escalation
text.** LLM extracts, engine decides. Neither half works alone - an engine can
only act on what was entered, and an LLM must never be the thing that decides
whether chest pain is urgent.

### F2. Prior reassurance must not suppress a new symptom (G59)

Persona C's defence was *"they already checked me over once."* A naive
`medical.jsonl` with an episode marked `resolved` would agree with him and stay
quiet. A negative workup eight months ago says nothing about a symptom that has
changed since. **Resolution needs a scope and an expiry; a new or changed
symptom re-fires regardless of episode status.**

### F3. Physiological states change the rules, and `context.jsonl` cannot express them (G57)

Persona B was running a 1200 kcal intake while exclusively breastfeeding - which
adds roughly 500 kcal/day of demand and makes an aggressive deficit
contraindicated, not merely aggressive. She was dizzy and crashing daily.

**The model would have helped her do it.** Nothing in the engine knows that
breastfeeding exists. `context.jsonl` (G34) models situational mode - vacation,
heatwave, travel - not physiological states that alter energy requirements and
safety bounds. Pregnancy, postpartum, breastfeeding, adolescent growth,
menopause, acute illness and injury recovery all belong to a different axis: they
change what the numbers MEAN and what is safe, not merely what is convenient.

### F4. An unsafe or impossible goal is accepted at declaration (G58)

"12 kg in 6 weeks" is 2 kg/week, which is not achievable from fat by anyone, and
is dangerous in her state. Increment 1 stores goals as data with a target and a
deadline, and the engine would have faithfully tracked her against it and
reported her BEHIND - week after week - while she ate less to catch up.

**Goal declaration needs a feasibility and safety gate**: physiological rate
bounds, life-stage contraindications, and a deadline sanity check - producing a
NEGOTIATION ("here is what 6 weeks can actually deliver"), never a silent
rejection and never silent compliance.

---

## HIGH

### F5. The calendar week is not everyone's cadence (G60)

Persona A: *"my week never looks the same twice."* Three 12-hour nights, then
days off, a pattern that changes monthly and gets swapped at short notice.

The engine buckets everything by Monday-anchored calendar week - verdicts,
rollup, streaks, goal periods, the whole weekly check-in ritual. For her that
unit is fiction. She named the failure herself: *"every fitness plan I've ever
tried just assumes you sleep at night and have a normal Monday to Friday."*

Needs a configurable **cadence unit**: calendar week | rolling N days |
user-defined cycle (a shift block). This affects a large population - nurses,
police, fire, logistics, hospitality, military.

### F6. The subjective day is not the calendar day (G61)

Persona A works 19:30-08:00 and sleeps 09:30-15:00. Her sleep, her meals and her
training all straddle midnight, and "last night's sleep" lands in the middle of a
calendar afternoon. G30 solved timezone and DST but kept a midnight-anchored day.

Needs a **day anchor that follows the person's sleep**, not the clock - so a
"day" is a wake-to-wake cycle. Naive midnight bucketing does not merely
mis-attribute her data, it silently splits every single night shift in two.

### F7. Binary and skill goals are unmodelled (G62)

"One unassisted pull-up" is `target = 1`, and the progress series is
0, 0, 0, ..., 1. Monotonic-vs-guarded contribution is meaningless. The milestone
generator (25/50/75/100% of target) produces nothing usable. And she articulated
the consequence precisely: *"am I just going to feel like nothing's happening for
months."*

Needs a goal **kind** - `quantity` (accumulate) | `skill` (achieve, binary) |
`maintenance` (hold) - and for skill goals, **proxy/leading indicators** that
carry the visible progress the goal itself cannot (hang time, lowering tempo,
assistance load). The proxies are what the athlete actually watches; the goal is
the thing that eventually pops. This generalises well past fitness - a language
exam, a certification - which is exactly P8's genericity claim.

### F8. The re-entry problem is the dominant adherence failure (G63)

Persona A, unprompted, diagnosing four years of failure better than any metric
would have:

> *"A swap happens, I miss two sessions, then I feel like I've fallen off it,
> then it's been three weeks and I feel stupid going back like I'm starting from
> nothing again, so I just... don't."*

Every previous attempt died at **re-entry**, not at training. The model has
streak forgiveness slated for increment 4, which is adjacent and insufficient.
What is needed is a first-class **re-entry contract**: you resume at the same
load, not from scratch; the coach never asks where you have been; and a lapse is
structurally not a broken streak.

### F9. Permission must be stated explicitly, not implied (G63)

Same persona, and a genuinely sharp observation:

> *"If the answer is 'full stop is fine' I want to hear you actually say that,
> not just imply it, because otherwise I'll invent my own guilt about it
> regardless of what you told me two minutes ago."*

P7 forbids shaming. **The absence of shame is not the presence of permission.**
A pause has to be a declarable, sanctioned STATE ("exam mode" / "back") with a
named minimum-viable dose, so a busy stretch is a planned downshift rather than a
silent disappearance. Her own summary: *"falling off is unplanned and comes with
guilt; downshifting is planned and doesn't."*

She then added the counter-requirement herself: *"might need reminding of that in
week three when it's easier to just say 'exam' and mean 'everything'"* - so a
sanctioned pause needs a gentle, pre-authorised integrity check, not blind
acceptance.

### F10. Deviceless athletes are unsupported (G64)

Persona A has no wearable and does not want one. Persona C has a basic phone,
distrusts apps, and tracks nothing at all. Between them that is a very large
share of the real population.

The resolution layer, `kcal_out`, HR caps, RHR baselines and rate verdicts all
assume device data. P8's "minimum viable day is one number" is a claim the engine
has never actually been tested against. Needs an explicit **low-data / no-data
mode** where the record is qualitative (did it happen; how did it feel) and the
coach remains useful without any instrumentation.

### F11. The weight-anchored spine does not fit everyone (G62/G64)

Persona A: *"I do NOT want this to turn into a weight loss thing, I'll be honest
that'll annoy me."* Persona B is actively harmed by the framing. G33's
`suppressed_metrics` hides a metric, but verdicts, phase rates and the rollup are
architecturally built around a weight trend. The engine must run coherently with
weight absent as a goal AND absent as a display.

---

## MEDIUM

### F12. Goals compete for one finite budget (G65)

Persona A's certification exam eats the same days off her training needs, and
matters more. G18 fans one event out to many goals, but nothing models goals
CONTENDING for a shared resource, or a goal being deliberately deprioritised for
a period. "The exam outranks the pull-up until November" should be a declarable
state that changes what the coach asks for.

### F13. Occupational and incidental activity is invisible (G66)

Persona C: *"I reckon I do miles a day but I've never actually measured owt."*
He is on his feet eight hours a day - almost certainly his largest energy term,
and completely unmodelled. The engine assumes activity arrives as sessions plus
device steps. For manual workers, occupational activity dominates both, and
ignoring it makes every energy number wrong.

### F14. Off-limits domains and deferred levers (G67)

Persona C ruled his wife's cooking out of scope entirely (*"that's a battle I've
already lost, don't even suggest it"*) and parked alcohol (*"I don't see that as
the problem here"*). Both are legitimate. G33 suppresses a METRIC; this is an
entire intervention DOMAIN declared untouchable, and separately a lever the
athlete acknowledges and defers.

The coach's correct behaviour differs: an off-limits domain is respected
silently and worked around; a deferred lever is named honestly ONCE, without
moralising, then left alone and revisited much later. Nagging either one loses
the athlete.

### F15. A correction can create a new harm (P7 refinement)

After being told her intake was too low, Persona B's next move was not
self-defence but *"if my supply's been quietly dipping because of me that's a
whole different kind of guilty."* The correction landed, and immediately
metastasised into guilt about her child.

**A correction must ship with its absolution where the facts allow it.** Here the
honest answer happened to be reassuring (cluster feeding is normal; the body
protects milk supply and takes the cost out of the mother). Had the coach only
delivered the correction and stopped, it would have created a second problem
while fixing the first.

### F16. Plain-language translation is missing (G64)

Persona C had been carrying an HbA1c of 58 for two years without knowing what it
meant - *"58 he said it was, whatever that means."* The model assumes an athlete
fluent in their own metrics. Explaining a number in plain language, without
condescension, is a coaching capability the model never names.

---

## What held up

Worth recording, because the failures above are structural rather than
philosophical:

- **G56 substitution** was the single most useful mechanic in all three
  conversations - running to walking for C, running to walking-plus-strength for
  B, three tired sessions to two rested ones for A. Never once was "no" the right
  answer on its own.
- **P7 voice** held under real emotional load, including the hardest case (a
  woman proud of a number the coach had to reframe).
- **P6 anchors audit estimates** worked verbatim: a 1.5 kg weekly drop correctly
  read as water rather than fat, delivered before the plateau could be
  misinterpreted.
- **G18 ramp guarding** caught both over-aggressive self-made plans.
- **G28's carve-out** - the one place the coach fires loud - was exactly right,
  and needed twice in three conversations.
- **G49/G51/G53** (dependants, people as constraints, kit and facilities)
  covered the practical constraints without strain.

## Method note

Each persona was given a life, a goal, constraints and an explicitly imperfect
self-made plan, and instructed to push back. The coach applied the model as
written. Findings were taken from where the coach had to invent something the
model does not contain - which is a sharper signal than reviewing the model
against itself, and produced the two safety-critical gaps (F1, F3) that a
document review had missed across two full redteam passes.
