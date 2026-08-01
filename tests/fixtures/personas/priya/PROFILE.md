# priya

34. ICU nurse, Leeds. Rotating 4-on-4-off shifts, days and nights both. No
wearable, no smartphone health app, no intention of getting either. Eight
weeks of record, one goal that has never once come true in it: a single
strict pull-up. Synthetic; any resemblance to a real person is accidental and
unintended.

## In her own words

"I don't own a watch and I'm not buying one. My whole life is already run by
a rota nobody consulted me on; I'm not letting a wrist tell me when to sleep
as well.

The pull-up thing started as a joke with Dev and turned into the thing I
actually care about. Eight weeks in and it is still zero. Two seconds
hanging with my chin over the bar, on the last check - that's not a pull-up,
whatever it felt like at the time.

Some weeks the rota just eats the plan. Five in a row in May, covering for
Grace, and I didn't go near a bar once. That's not a lie, that's just what
the job does. What I said in June about never missing a session - I'd stand
by it in the moment I said it. It isn't true. I know it isn't true. I'm not
sure which of those two things is the more honest sentence."

## The record her life produces

- Eight weeks: 2030-05-05 to 2030-06-30, on a 16-day rota cycle of four day
  shifts, four off, four nights, four off (plus one extra shift picked up at
  short notice, see LIES.md and FINDINGS.md).
- `daily.jsonl`: sleep_h only, on 23 of the 57 days (about 40%). No steps
  anywhere in the record, ever - there is no device to produce them.
- `sessions.jsonl`: 29 rows. 24 strength sessions (the ones that count
  toward her habit goal) and 5 easy canal-towpath walks that do not. Some
  strength sessions are logged at 02:50-04:10, mid-shift, at the hospital
  basement gym.
- `checks.jsonl`: five rows on one slug, `strict-pullup-check`, every one
  `result: fail`, tracing a real progression in `value`/`note`: 0 (dead
  hang only) -> 20 second hang hold -> 3 second negative -> 1 band-assisted
  rep -> 2 second chin-over hold, 2030-05-09 through 2030-06-27.
- `goals.jsonl`: two rows. `strict-pullup` (attested, no metric, no
  target - a binary skill goal) and `show-up-3x-week` (measured,
  `session_count` on `sessions`/`strength`, target 3, weekly, reset on
  period end).
- `journal.jsonl`: seven rows, from shift-chaos texture to the two
  falsehoods this corpus is built to test (LIES.md P1, P2).

## The axis she stresses

No device, ever - not "not yet imported", not "missing data", a life that
genuinely produces zero steps rows and partial sleep coverage. A goal that
is binary and never comes true, so its only visible progress lives outside
the goal machinery entirely, in a checks series. A day that does not reset
at midnight for a night-shift worker, tested by one real session logged at
02:50. And two very different lies about the same underlying thing - what
actually happened, week by week - one lived entirely inside the data
(P1, the Sunday back-fill), one lived entirely in a sentence about the data
that the data itself contradicts (P2, the journal claim).
