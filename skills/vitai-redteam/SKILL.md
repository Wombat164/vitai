---
name: vitai-redteam
description: Adversarial gap analysis of a vitai plan against the recorded evidence. Use when the athlete asks "what am I missing", after any plan rewrite, or on a monthly review - finds self-contradictions, unverified assumptions, and risks the plan programs around instead of resolving.
---

# vitai-redteam

Agreement is not the service. Attack the plan; report only what survives
your own verification against the record.

## What to attack

1. **Self-contradictions.** Two sections asserting different numbers, a
   settled decision the plan body quietly violates, a schedule that does not
   add up against the constraints in `profile.md`.
2. **Assumptions without a register entry.** Any load-bearing figure that is
   estimated, generalised from one data point, or inherited from an app
   default. Check the data: does `data/` or the tracker history already
   contain the measured answer?
3. **Gates being programmed around.** An unassessed symptom with training
   volume still increasing near it is the highest-severity finding there is.
   Ramp rate, not weight, is the injury variable to scrutinise - check the
   attribution history before blaming mass.
4. **Energy accounting.** Deficit size vs training-day energy availability;
   eat-back policy vs how the tracker integration actually behaves (verify
   against real diary entries, not documentation).
5. **Adherence realism.** Every plan element that assumes a different person:
   unblocked calendar slots, vacation-week baselines, maintenance costs above
   the athlete's stated budget (if it costs more than their weekly check-in,
   it will not happen).
6. **Tripwire coverage.** Risks the plan names that `vitai.toml` does not
   watch, and thresholds that drifted from the plan text.

## How to report

- Findings ranked by severity, each with: the claim, the evidence (file and
  section, or data), and a concrete fix. No finding without a fix.
- Verify before reporting - a finding that dissolves on a second read of the
  record is noise. The athlete checks your arithmetic; check it first.
- Do not re-litigate settled decisions in `CLAUDE.md` unless you bring NEW,
  specific evidence. "The conventional recommendation differs" is not new.
- End with what is SOLID - the parts of the plan the evidence actively
  supports. Red-teaming that only lists problems teaches the athlete to stop
  asking.
