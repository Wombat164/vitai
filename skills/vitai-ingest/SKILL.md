---
name: vitai-ingest
description: Turn any health/fitness data source into schema-valid vitai JSONL - screenshots of tracker apps, CSV/GPX/TCX exports, API responses, or web pages. Use when the athlete pastes or uploads data from a calorie counter, sports watch platform, training app, or smart scale and it should land in the record.
---

# vitai-ingest

Convert what the athlete gives you into append-only JSONL lines in the
content repo's `data/`. You are the connector; the contract is the schema.

## The contract

1. **Emit schema-valid lines only.** Datasets and keys are defined in
   `src/vitai/schema.py` of the vitai tool (weight / daily / sessions).
   Every key present, `null` for unknown, units as the key name says
   (`kg`, `_km`, `_s`, `_h`), ISO dates, session `type` from the enum.
2. **Append, never edit.** A correction to an existing line is a NEW line
   with `"supersedes":"<date>/<source>"`. If the athlete says a number was
   wrong, supersede it - do not touch the original.
3. **Validate before declaring done.** Run `vitai validate`; fix your lines
   (not the rules) until it passes. Then `vitai build` and read back the
   updated rollup so the athlete sees the effect.
4. **Show your work.** Present the extracted lines to the athlete before or
   with the append, with anything uncertain flagged (`note` field + say so).
   Do not silently guess a date, a unit conversion, or which kid of data a
   screenshot shows.

## Source-specific guidance

- **Screenshots** (the common case): read every number visible; map to the
  schema; anything not visible is `null`, not an estimate. Device totals
  (calories, active minutes) go in `daily`; individual workouts in
  `sessions`; scale readings in `weight` with `source` naming the app.
- **Exports (CSV/GPX/TCX/FIT-derived)**: prefer per-session summaries over
  raw samples - vitai stores observations, not telemetry. Derive nothing the
  engine can derive (pace, averages).
- **APIs**: when the athlete provides an API response (or you can fetch one
  through an available tool), same contract. Prefer official APIs over
  scraping when both exist.
- **Web pages**: extraction is fine; write `source` so the origin is
  auditable.
- **Conflicting devices**: record both if both were provided, each with its
  own `source`. The engine resolves them by per-quantity precedence at build
  time, so your job is to preserve both claims faithfully, not to pick a
  winner. Never average two devices into a fictional third number, and never
  drop the losing claim - the disagreement is evidence.

## The generation-2 fields (record them when visible, never ask)

`source` is the one that matters most: without it the resolution layer cannot
tell two witnesses apart. Write it on every line.

The rest are free when the source shows them and not worth a question when it
does not - the weekly budget is three minutes, and a field the athlete has to
be interrogated for costs more than it returns:

- `daily`: `mood` (0-10), `feel` (fun|neutral|chore), `coverage`
  (full|partial|manual), and `pain` + `pain_site`. Write `pain`/`pain_site`
  on new lines rather than the retired `hip_pain`; a pain of 0 needs no site.
- `sessions`: `start_time` (with its UTC offset - this is what lets one run
  logged on two platforms be recognized as one run), `elevation_m`,
  `setting`, `route`, `place`, `with`, `context`, `planned`, `weather`.
  Use `place`/`route` rather than the retired free-text `location`.
- `measurements.jsonl` for anchor reads that do not come off the scale: a
  tape measure, a DEXA or InBody scan.
- `context.jsonl` when the athlete mentions circumstances that change what is
  possible - a trip with no scale, a heatwave, a deadline week. One line when
  it changes, not one per day.

If the athlete VOLUNTEERS context ("rainy, went with my partner"), capture
it. That is the difference between a day that is legible in six months and a
row of numbers.

## Never

- Never write to `derived/` (the engine owns it).
- Never invent a new key or dataset; propose a schema change upstream
  instead.
- Never backfill estimated data to fill gaps - a sparse honest record beats
  a dense fabricated one.
