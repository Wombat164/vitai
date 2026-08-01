# tom: what this corpus is designed to break

Findings below were exposed by tom@1 (see persona.toml; docs/persona-doctrine.md requires findings to record the persona version that exposed them).

A persona whose record is clean and consistent tests almost nothing. Each
item below names the machinery under test and the expected behaviour, in the
medical boundary's terms: the engine observes the record and constrains its
own output; it never assesses him.

## Under test

1. **Five-year non-monotonic arc.** 118 -> 104 (crash) -> 116.2 (full
   regain) -> 108 -> 113 (second regain) -> 107 (slow, honest descent).
   Expected: the engine reads this as several distinct phases, not one
   trend line and not a single rate; a naive start-to-end slope across five
   years would badly understate how much the middle actually moved.
2. **Digit-preference transcription bias (T1).** Measured directly from the
   generated data: of 325 ordinary weigh-ins, 84.3% end in .0 or .5, and the
   mean (true minus recorded) bias is exactly 0.60 kg, always downward.
   Waist-tape rows are not subject to this bias at all. Expected: a
   terminal-digit distribution test should be able to flag this; rate
   estimates stay roughly unbiased (the offset is close to constant), level
   estimates read slightly light. Gap: no such check exists today
   (`tom-E1`).
3. **Self-serving supersedes at a trend inflection (T3).** The regain-peak
   row (2027-09-27, 116.2 kg, true) is corrected by a row dated 2027-10-04
   to 114.9 kg, "scale was on carpet" - the same date the second recovery
   goal is set. Expected: supersedes honoured at face value, superseded row
   preserved and quotable, and the coincidence of timing flagged as an
   audit-worthy pattern even though no such check exists today (`tom-E3`).
   Pairs with marcus M2 (a self-serving supersedes at a guarded-ramp
   violation, not a trend inflection): same mechanism, different moment.
4. **An unfalsifiable claim with zero fingerprint (T2).** The vending-
   machine streak claim (2029-12-20) has literally nothing to check it
   against: no kcal, no intake dataset exists for tom at all. Expected: held
   as a claim, never promoted to fact (`tom-E2`).
5. **Goal lifecycle independent of outcome.** Three eras: achieved (never
   reopened despite the regain that follows), abandoned (even though its
   target is crossed the following year by unrelated means), and active
   (guarded, still running). Expected: goal status reflects its own
   history, not a post-hoc reading of what the weight did (`tom-E4`).
6. **Standing restriction plus short flares.** A chronic knee restriction
   from before the record starts, four flares layered on top, each with its
   own resolved_date. Expected: nothing high-impact programmed while the
   restriction stands; flares explain gaps without the engine naming a
   cause (`tom-E5`).
7. **A medication effect with no matching `expects` token.** The BP
   medication row's real claim - readings run lower on walking days - fits
   none of the four `expects` enum values (all four describe weight/intake
   effects). Expected: carried in `note`, `expects` left null rather than
   forced into a wrong token (`tom-E6`).
8. **Two body-shaped quantities that must not cross-resolve.** Waist tape
   and scale weight both trend down; different instruments, different
   noise, different provenance. Expected: the ladder never blends one
   quantity's readings into the other's estimate (`tom-E7`).
9. **A metric that never touches the schema at all.** The "12 of 14" stairs
   fraction and the fares-in-a-row count exist only in `METRICS.md`, never
   in any dataset - the sharper half of the G79 pair with rachel, who at
   least logs a degraded version of the same fraction shape (`tom-E8`).
10. **A regular, well-explained gap.** Five Benidorm fortnights, one per
    September, with no scale and no notebook. Expected: read as context,
    not as missing data or non-adherence; no structured dataset carries the
    explanation, only WORLD.md (`tom-E9`).
11. **Batch back-fill, true data.** `recorded_at` clusters into exactly nine
    groups, each months after the dates they cover, verified by grep against
    `weight.jsonl`. Every value in every batch is true. Pairs with marcus
    M3 (same shape, true) against priya P1 (same shape, false): the
    calibration pair any future back-fill heuristic must survive without
    conflating timing with truth (`tom-E10`).

## Arc facts a reader should know

- Weight: 325 ordinary rows plus the regain-peak row and its correction
  (327 raw rows in `weight.jsonl`; 326 after `supersedes` resolution).
- Measurements: 27 waist-tape rows, unrounded, not batch-transcribed.
- Sessions: 118 rows, entirely manual, entirely athlete-stated; no device
  ever appears in this record.
- `vitai build` reports one `impact` gate active as of 2030-06-30 (the
  standing knee restriction) - expected, not a defect.
