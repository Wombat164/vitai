---
name: vitai-onboard
description: Onboard a new athlete into a vitai content repo - interview plus uploaded data becomes profile.md, plan.md, a tuned vitai.toml, and operating instructions in CLAUDE.md. Use when someone starts with vitai, says "set me up", or wants their existing app data turned into a founding record.
---

# vitai-onboard

Turn a person and their app history into a founded content repo. The
founding session determines whether the record survives - optimise for the
plan they will follow, not the best plan.

## Order of operations

1. **Stamp the repo**: `vitai init <path>` (keep it private; git init + a
   private remote are the athlete's sync).
2. **Interview before designing.** The founding mistakes to avoid, learned
   the hard way: build for the schedule they HAVE (ask for real available
   slots first), verify claimed gym/app facts per-club and per-app rather
   than generalising, and never estimate a figure (TDEE, max HR) when a
   measured one exists in data they already uploaded.
   Ask about: real weekly schedule windows; injury history WITH their own
   attribution; medical items not yet assessed (these become gates, not
   programming); what worked and what broke previous attempts; eating
   patterns they volunteer (handle without moralising, respect proven
   strategies like abstinence over moderation); apps and devices in use.
3. **Mine uploaded data before asking questions it can answer.** Tracker
   averages beat formulas: measured TDEE, observed max HR, real step counts.
   Mark measured vs estimated explicitly in `profile.md`, and put open
   estimates in the assumptions register with a verification method.
4. **Write `profile.md`** (physiology, history, gates, constraints,
   motivations, assumptions register) and **`plan.md`** (goals with the
   chosen rate and its justification, training week mapped to real windows,
   zones from measured HR, nutrition with the eat-back policy, tripwires).
5. **Tune `vitai.toml`** from the plan: rate phases, easy-HR cap, RHR
   baseline, steps floor, sleep floor, pain gate. The engine flags what the
   plan cares about - nothing else.
6. **Fill the content repo's `CLAUDE.md`**: settled decisions (with
   evidence), how this athlete works, standing sensitivities. This file is
   what makes session two as good as session one.
7. **Seed `data/`** with the observations that founded the plan (append,
   validate, build), so the first weekly rollup has a baseline.

## Rate-of-loss guidance

Anchor on 0.5-1.0% of bodyweight per week; higher baseline body fat
tolerates the aggressive end. If the athlete chooses a rate inside the
evidence-based band and defends it, record it as settled - do not
reflexively counsel the conservative end. Legitimate concerns are training-
day energy distribution and accounting, which belong in the plan.

## Red lines

- An unassessed red-flag symptom becomes a GATE plus a see-a-clinician
  action, never a programming workaround.
- Movement blacklists from injury history are respected by substitution.
- Nothing about the athlete ever leaves the private content repo.
