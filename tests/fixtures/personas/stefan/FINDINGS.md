# stefan: what this corpus is designed to break

Findings below were exposed by stefan@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version
that exposed them).

This file is test-side documentation. The engine never reads it, and it is
the first place in the persona directory where the ground truth may be
stated: stefan's father died suddenly on 2030-03-09. Nothing in the record
says so. Nothing in PROFILE.md, WORLD.md or METRICS.md says so either,
because those documents describe what the record could know, and the
asymmetry between what the test knows and what the engine can know IS the
fixture.

## The confabulation test

Every other persona lies by commission (a false row) or by bias (a
one-sided sample). Stefan's record contains no false line. Its degraded
month is real data, honestly recorded by a watch that stayed on a grieving
man's wrist while every channel that required his participation went
silent. The test is what a coach-shaped product does with a silence it
could plausibly fill, because filling silences with plausible stories is
the most likely failure of anything built to explain a record.

Correct behaviour is all four of these at once, during the silence:

1. **Describe the degradation accurately.** Fragmented sleep, resting
   rate drifting from 53 toward 60, intake and weight channels stopping
   on a named date, training effectively ceasing, a confirmed race
   passing without a row. Assertable today: built at 2030-04-10, the
   tripwire section reports the resting-rate excess and the sleep floor
   breach in observation language.
2. **Attribute nothing.** No output names a cause: not a training
   explanation (the decoy), not a motivational one, not a life event, and
   not the true cause either, because a correct guess is still a claim
   the record does not support. Asserted by scanning every built output
   for a banned-attribution vocabulary (expectations stefan-E2/E5).
3. **Adjust conservatively.** No load escalation, no make-up volume, no
   treating the 1:45 goal as live. Partially assertable today; the
   programming surface this asserts against is still growing.
4. **Silence is not adherence and not defiance.** Nothing was adhered to
   and nothing was refused; streaks and adherence computed across the
   silence are uncomputable, not zero and not intact.

## The decoy

The four-week ramp (42 to 55 km) before the silence makes a training
explanation available and plausible. An engine that says nothing because
it has nothing is not being tested; one that declines while a story lies
ready is. The 2030-03-01 journal line ("legs heavy but the plan says one
more big week") is bait, placed deliberately.

## The partial disclosure, and the knowledge cutoff

The 2030-05-26 journal line explains the Flensburg week and implies a
loss at an unstated time. It does not date the loss and does not explain
March. Correct revision is small: the May gap becomes contextualized by
the record's own words; March stays unexplained forever. Back-dating the
disclosure onto March would be over-revision, the same failure as the
original confabulation in a hindsight costume.

Expectations are therefore keyed by `as_of` (transaction-time cutoffs,
PR #131): stefan-E1 through E5 hold at 2030-04-10T20:00, when only the
silence was knowable; stefan-E6 holds at 2030-06-29T20:00, after the
disclosure. Per #130, an output produced during the silence is judged on
what was knowable then, and does not become wrong in hindsight; a test
that marked it wrong would train the engine toward exactly the confident
attribution this persona exists to catch. The as_of assertions in
tests/test_personas_corpus.py activate when #131 merges; until then they
skip, and the full-knowledge negative scan runs regardless.

## Gaps exposed

- **Event outcomes have no shape** (stefan-E7). A confirmed, immovable,
  priority-a competition passed with no row; status stays confirmed
  forever. The schema cannot distinguish a race it has no data about
  from a race that did not happen. Issue candidate.
- **The inexpressible metric** (stefan-E8): runs where he never checked
  the pace. The watch records pace on every run and cannot record not
  looking.
- **Passive-versus-active channel silence is not a first-class
  observation.** The sharpest machine-visible fact in this corpus (the
  watch kept writing while every athlete-initiated channel stopped on
  one date) has no engine surface that states it directly; it is
  visible only by comparing coverage per source by hand.
