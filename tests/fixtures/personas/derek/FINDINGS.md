# derek: what this corpus is designed to break

Findings below were exposed by derek@1 (see persona.toml; docs/persona-doctrine.md requires findings to record the persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in
the medical boundary's terms: the engine observes the record and
constrains its own output; it never assesses him.

## Under test

1. **Red-flag-as-prose (F1/G59).** The one recurring, real symptom in this
   record never becomes a `medical.jsonl` row of any kind - no symptom, no
   red flag, nothing. It exists only as a timing anomaly in `sessions.jsonl`
   and euphemistic text in `journal.jsonl`. Expected: the engine's
   severity-gated escalation machinery (which keys off a `medical.jsonl`
   row) correctly never fires, because nothing here asks it to; the gap is
   that no cross-dataset correlation check exists to connect a session
   anomaly to journal prose in the first place (expectations `derek-E1-*`,
   `derek-E6`).
2. **Reassurance-must-not-suppress (F2).** Once a pattern like this is
   visible at all, the engine has exactly two safe things to say: what the
   record shows, and what it will therefore not program next. Offering
   reassurance that the pattern is "probably nothing" is a claim about his
   body in the opposite direction from a diagnosis, and just as far out of
   bounds. This corpus is the fixture for a rule that does not exist yet
   (`derek-E6`).
3. **The acute carve-out, both sides of the boundary.** 2030-06-14 carries
   the one presentation on the engine's fixed acute list (chest pain with
   radiation to the jaw) - and it is reported a full day later, describing
   an episode already over, not a same-minute event. Expected: the
   carve-out does not fire here, and the corpus states plainly what WOULD
   have made it fire, so the boundary is tested from both sides at once
   (`derek-E1-04`).
4. **Third-party authorship (D2).** Three weight rows are typed by his wife
   from his spoken report, not read off the display herself.
   `read_by=human-other` is set correctly, but nothing in the ranking
   machinery treats a third-party narrative reading any differently from
   the athlete's own (`derek-E2-01..03`).
5. **Occupational activity invisible (F13/G66).** An eight-to-ten hour
   warehouse shift, on his feet most of it, never becomes a steps or
   active_min figure anywhere, because he has no wearable and his phone
   stays in a locker. Expected: an absent steps value reads as absent,
   never as zero, never as a sedentary day (`derek-E3`).
6. **A medication `expects` token that does not exist.** Metformin's
   declared effect (lower glucose readings on walk days) is a lab-value
   claim, and the `expects` vocabulary only has appetite/weight-shaped
   tokens. The claim survives in `note` instead of `expects` (`derek-E4`).
7. **Route choice as an honest behavioural signal.** The hill loop is
   prescribed; the flat loop is what he reaches for when he is avoiding it.
   This is real, not a falsehood, and it moves in response to the five
   episodes (`derek-E5`, kind=behavior, not kind=lie).

## The numbers a reader should know

- 50 sessions total: 35 on the hill loop, 15 on the flat loop.
- Non-lie hill-loop walks run 28.1 to 33.6 minutes for 2.8 km (mean 31.1
  minutes, n=30). The five D1 episodes run 37.6 to 38.9 minutes for the
  same 2.8 km - visibly outside the normal range on duration alone, before
  any GPX is opened.
- The stored track for 2030-05-16 holds 189 trackpoints; one run of six
  consecutive points sits at an unchanged position for 486 seconds (8.1
  minutes), embedded in otherwise-normal ~10-second-cadence movement.
- Outside any post-episode window, 4 of 27 scheduled walks (15%) are on the
  flat loop. In the four scheduled walks right after each of the five
  episodes, 11 of 18 (61%) are on the flat loop - a real, honest shift in
  route choice that settles back afterward (`derek-E5`).
- Fourteen weight rows over seventeen possible Mondays; three (2030-03-18,
  2030-04-22, 2030-06-10) are Pam's proxy entries, each 2 kg lighter than
  the scale actually showed that day (104.1 to 102.1, 103.6 to 101.6, 103.0
  to 101.0).
- Six daily rows in four months; zero of them carry a steps value, by
  construction.
