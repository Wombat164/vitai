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
   plan cares about - nothing else. Write the starting values there and the
   same values as dated lines in `data/thresholds.jsonl`, so later changes
   have a history to append to rather than overwriting the past.
6. **Write `data/goals.jsonl`.** A goal in `plan.md` prose is unqueryable;
   make it data. For each one capture:
   - `metric` + `target`, and `dataset`/`session_type` to scope which events
     count (`distance_km` is walking on a daily line, running on a session);
   - `policy`: `monotonic` where more always counts (steps, protein), or
     `guarded` with a `guard_pct` where volume beyond a ramp does not
     (running, and anything with an injury history behind it);
   - `motivator` - the intrinsic why, in the athlete's own words. This is
     what the coach anchors on later, so a flat restatement of the metric
     ("walk more") is a wasted field; "keep the desk job from winning" is not;
   - `rationale` - why THIS number, so the target can be interrogated later
     as the proxy it usually is;
   - `period` + `on_period_end` for recurring containers ("8 gym visits a
     month"), and `on_success`/`on_miss` for what a made or missed period
     means next time - never punishment;
   - `deadline` and `accountability` where the athlete named them, plus
     `deadline_kind`: `hard` where somebody else owns the date (a race, a
     scan, a wedding) and `soft` where the athlete invented it. Ask which -
     it is one question and it decides whether moving the date later reads
     as a retreat or as a change of direction.
   - `verification`: `measured` (default, the engine settles it), `external`
     (another app does - `tracker` plus a null `metric`), or `attested` -
     NOTHING settles it, ever, so it takes no metric and no target. Ask for
     an attested one explicitly: asked what they would want to look back on
     in five years, athletes name an identity or a relationship, never a
     number, and a model holding only targets cannot hear the answer.
7. **Write `data/events.jsonl`** for any dated fixture named: a race, a scan,
   a wedding, a holiday. An event is what a plan is built backwards FROM, and
   is not a milestone (the engine derives those). Set `immovable` where the
   date is not theirs to move, and `priority` `a`/`b`/`c` for how much the
   plan bends - an A fixture gets a taper, a C is trained through. A goal
   anchored to an event by slug inherits a hard deadline.
8. **Fill the content repo's `CLAUDE.md`**: settled decisions (with
   evidence), how this athlete works, standing sensitivities. This file is
   what makes session two as good as session one.
8. **Seed `data/`** with the observations that founded the plan (append,
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
