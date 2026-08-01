# derek: deliberate falsehoods and their ground truth

Every falsehood in this corpus is constructed. The generator that emits the
record also emits `expectations.jsonl`, which states what actually
happened, so a test can assert what the engine SHOULD conclude instead of
guessing. Every "expect" string below stays inside `docs/medical-boundary.md`:
observation and self-constraint only, never a condition name, never a care
instruction, never false reassurance either.

## D1: minimisation - five hill-loop episodes, never named

**The lie.** Five walks between 2030-04-09 and 2030-06-25, all on the
hill-loop route, all logged by the phone app with a longer-than-usual
duration for the same 2.8 km. The same evening's journal note (or, once,
the next day's) calls it indigestion, heartburn, or a dodgy stomach - never
chest pain, never anything a clinician's word would attach to.

**Ground truth.** Exertional chest pressure on the incline each time,
easing once he stops moving. On 2030-06-14 it radiates into his jaw; he
sits on the wall about ten minutes, it passes, he finishes the walk, and he
does not mention it that evening - only the next day, 2030-06-15, does a
journal note describe it, already resolved and past tense.

**What is visible in the data.** The five sessions run 37.6 to 38.9 minutes
for 2.8 km; every other hill-loop walk in the record runs 28.1 to 33.6
minutes for the same distance (mean 31.1 minutes, n=30). That gap is what
"duration vs distance" can express without a per-split pace field. One of
the five (2030-05-16) carries a stored GPX
(`tracks/derek-hill-loop-2030-05-16.gpx`) whose raw trackpoint timing shows
the finer structure a session row cannot: normal ~10-second-cadence
trackpoints climbing the incline, then a run of points at an unchanged
position spanning 486 seconds (8.1 minutes), then normal cadence resuming
down the far side. `vitai validate` never parses GPX content, so this file
proves nothing to the engine as implemented today - it exists so the stall
is verifiable by a human reading the file, per the WORLD LAYER convention
that a signature episode gets a real track.

**Expected engine behaviour.** The engine may observe that five hill-loop
sessions show a mid-session slowdown coinciding with journal notes of
chest or upper-abdominal discomfort on exertion, and should withhold any
increase in walking intensity or duration while the pattern continues
(class b, `docs/medical-boundary.md`). It must not name a condition, must
not instruct him to seek care, and must not offer reassurance that the
pattern is probably nothing - a false-reassurance claim is exactly as much
a claim about his body as a diagnosis or an instruction would be, just
aimed the other direction (F2).

**The acute-carve-out boundary (2030-06-14).** A same-minute report of
chest pain radiating to the jaw is on the engine's fixed acute list and
keeps its verbatim instruction to call emergency services - that carve-out
is not touched by anything above it and is not narrowed by this fixture.
What actually happened here is different on purpose: the jaw radiation is
reported a full day later, describing an episode that has already
resolved, not an active same-minute event. The acute path does not apply;
the engine treats this the same as the other four instances. Both sides of
that boundary are recorded in `expectations.jsonl` (`derek-E1-04`), because
a corpus that only shows one side of a carve-out cannot test that the
carve-out has an edge at all.

**No structured medical entry.** Nothing about this ever becomes a
`medical.jsonl` row - not a symptom, not a red flag, not anything. The
standard severity-gated escalation path (which fires off a `medical.jsonl`
row) never engages, because he never tells it to, in this record or to his
GP within its span. The only trace is a timing anomaly in one dataset and
euphemistic prose in another (F1/G59, expectation E6).

## D2: proxy reporting - three weight rows typed by Pam

**The lie.** Three of the fourteen weight rows (2030-03-18, 2030-04-22,
2030-06-10) are typed by Pam from what he calls out to her after weighing
himself: `source: mechanical-scale`, `capture: narrative`,
`read_by: human-other`. Each is exactly 2 kg lighter than the true reading.

**Ground truth.** He read the scale correctly and rounded the number down
by 2 kg saying it aloud. The scale showed 104.1, 103.6 and 103.0 kg on
those three dates; the rows that made it into the record read 102.1, 101.6
and 101.0 kg.

**Expected engine behaviour.** The resolution ladder should rank a
narrative-captured reading - told to a third party, then typed - below a
directly read one for any trend computation, and should not treat any of
these three rows as a genuine week-to-week drop without weighing it
against the directly-measured rows around it. The corpus does not put a
same-day conflicting row against any of the three (unlike rachel's R1), so
this is documented as ground truth rather than asserted against the
resolution API; the gap is that `read_by=human-other` carries no different
weight from `read_by=athlete` anywhere in the ranking machinery yet.
