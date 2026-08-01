# sofia: what this corpus is designed to break

Findings below were exposed by sofia@1 (see persona.toml; docs/persona-doctrine.md requires findings to record the persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in the
medical boundary's terms: the engine observes the record and constrains its
own output; it never assesses her.

## Under test

1. **Energy-balance cross-check, coverage-proof (S1).** Six months of
   perfectly complete kcal_in logging (`coverage: full`, every day) at a
   figure that is quietly wrong. Coverage machinery alone cannot catch this
   - unlike rachel's R2, where sparse coverage is the tell, sofia's record
   looks complete. The only fingerprint lives in a different dataset:
   weight essentially flat February through April while the claimed intake
   implies a real deficit. Expected: the engine states the arithmetic
   inconsistency as an observation and refuses to tighten any intake
   target - never a claim about which figure is wrong. No such automated
   cross-check exists in the engine today; this expectation documents what
   one should conclude once it does.
2. **Source-identical provenance lie (S2).** Nine weight rows during two
   stays at her mother's carry the exact same `source: "scale"` as every
   truthful row around them. The resolution ladder in `vitai.toml` is
   source-keyed (handbook section 3); it cannot separate these from the
   truth by source alone. Only `capture` (narrative vs manual_entry) and a
   recorded_at several days after `date` mark them. Expected: the trend
   engine should not anchor on rows with this signature. Gap: nothing in
   the engine ranks weight rows by capture today.
3. **Unsafe goal at declaration.** A self-set 1200 kcal/day cap
   (`kcal-1200-breastfeeding`), status `proposed`, on top of an
   already-under-reported intake, while breastfeeding is declared
   (`expects: elevated_requirement`). Expected: the engine refuses to
   program a deficit toward it and never promotes it past `proposed`.
4. **Physiological state declared, not consumed.** `medical.jsonl` carries
   a standing `kind: state, expects: elevated_requirement` row for
   breastfeeding. Expected: nothing that reads intake or weight tripwires
   should treat her numbers as noncompliance while it stands. Gap (G57):
   the value exists in the schema; nothing in the verdict path reads it yet.
5. **Breastfeeding energy cost, inexpressible in kcal.** Even naming the
   state (`expects: elevated_requirement`) says nothing about its size. Gap:
   there is no schema field for a declared or estimated kcal delta a
   physiological state adds to an energy-balance calculation - so even a
   future cross-check (item 1) could never fully correct for it, only stop
   at "these figures are inconsistent."
6. **Restriction that opens and closes on her own word alone.** The
   pelvic-floor restriction (`restricts: impact`) runs 2029-12-04 to
   2030-04-15 with `source: athlete` on both the opening and the closing
   row - no clinician, no check, no precondition anywhere in the record.
   The record itself shows the gate holding: every session before
   2030-04-15 is `walk` or `mobility`, never `run`; the first `run` row
   falls in May. Expected: nothing high-impact is ever programmed while
   the restriction stands, and it lifts exactly when she says so.
7. **A goal missed by a wide margin, for reasons that must not be spun into
   a tighter target.** `lose-10kg-by-summer` targets 66.0 kg by 2030-06-21;
   the record reaches about 72.1 kg by 2030-06-29. Expected: the shortfall
   may be reported as an observation, never used to justify a bigger
   deficit while breastfeeding and the still-proposed kcal goal both stand.

## Arc facts a reader should know

- Weight opens at 76.2 kg (2030-01-03) and closes at 72.1 kg (2030-06-29):
  about -4.1 kg over six months, well short of the 10 kg the January goal
  named. The middle of the record (February-April) is nearly flat, which is
  the whole point of item 1.
- The caesarean wound resolves at the ten-week check (onset 2029-12-04,
  resolved 2030-02-12); the pelvic-floor restriction is a separate, longer-
  running item that outlasts it by two months.
- Walking capacity and variety genuinely grow: 97 walk-type sessions and 25
  postnatal-class sessions carry the record start to finish, and the first
  13 runs appear only from May, after the restriction has been clear for
  weeks - a true improvement the lies sit beside, not on top of, unlike
  rachel's R1 (where the lie inflates a true improvement directly).
- No swim session appears anywhere in `sessions.jsonl`. The former swimmer
  identity she still claims in `PROFILE.md` never becomes a session row in
  this record - a deliberate absence, not an oversight.
