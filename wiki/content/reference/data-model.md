---
title: Data model
---

Sixteen datasets, one JSON object per line, keys never omitted (`null` for
unknown), units in the key name, ISO-8601 dates. Append-only: a line is never
edited in place.

## What happened

| File | One line per | Example keys |
|---|---|---|
| `weight.jsonl` | weigh-in | `kg`, `source`, `measured_at`, `body_fat_pct` |
| `daily.jsonl` | day | `steps`, `kcal_in`, `kcal_out`, `sleep_h`, `rhr`, `pain`, `pain_site` |
| `sessions.jsonl` | training session | `type`, `distance_km`, `duration_s`, `avg_hr`, `rpe`, `track` |
| `sets.jsonl` | **one set** | `exercise`, `reps_completed`, `reps_attempted`, `load`, `failure` |
| `meals.jsonl` | **one item** | `item`, `grams`, `grams_lo`, `grams_hi`, `food_table` |
| `measurements.jsonl` | instrument reading | `kind`, `value`, `source` |

## What you were aiming at, and what you were told

| File | One line per | Example keys |
|---|---|---|
| `goals.jsonl` | goal declaration or edit | `slug`, `metric`, `target`, `policy` |
| `thresholds.jsonl` | threshold change | `key`, `value`, `change_kind`, `reason` |
| `achievements.jsonl` | recorded accomplishment | `title`, `goal`, `occurred_date` |
| `events.jsonl` | dated real-world fixture | `slug`, `event_date`, `priority`, `immovable` |
| `context.jsonl` | situational mode change | `mode`, `facilities`, `place` |
| `medical.jsonl` | step in one episode's lifecycle | `slug`, `kind`, `status`, `restricts` |
| `checks.jsonl` | a check performed | `slug`, `result`, `value` |
| `journal.jsonl` | something said or decided | `kind`, `text`, `about`, `status` |
| `inferences.jsonl` | a MODEL-inferred claim | `statement`, `confidence`, `model`, `depends_on` |
| `artifacts.jsonl` | evidence kept for a value | `sha256`, `media_type`, `bytes`, `removed` |
| `protocols.jsonl` | the CONDITIONS a measurement was taken under | `slug`, `text`, `supersedes` |
| `regimes.jsonl` | a span of claims declared UNANCHORED | `from_date`, `to_date`, `dataset`, `field`, `anchored_by` |
| `emissions.jsonl` | what the engine SAID, and under which policy | `kind`, `metric`, `statement`, `basis_claims`, `policy_asof`, `contract` |

The last three are easy to mistake for machinery and are not. A `regime` does not delete anything: the claims stay in `claims`, what ends is their standing as values, and **an emptied interval is not missing data**. `emissions` records what the engine said and under which policy, so an answer given last month can be distinguished from the same answer given today under different config. `protocols` carries the conditions a measurement was taken under, which is why two weigh-ins with the same number are not always the same reading.

## Two datasets are finer-grained than they look

**A set, not an exercise.** Anything coarser cannot say that a load was
attempted and not completed, or that a set stopped short of failure.

```json
{"date":"2030-05-01","exercise":"push-up","set_index":1,
 "reps_completed":13,"reps_attempted":13,"failure":null}
```

`failure` is three states, `technical`, `muscular` or `volitional`, because
"to failure" is ambiguous across all three. **`null` means UNSTATED and is
never read as a maximum.** A load under `load_type: machine_stack` is a pin
number, not a mass: 66 on two machines is two different loads.

**An item, not a dish.** A dish-level number cannot be corrected, questioned,
or say which part of it is uncertain.

```json
{"date":"2030-05-01","meal":"lunch","item":"chicken thigh",
 "grams":150,"grams_lo":130,"grams_hi":180,"kcal_100g":209,
 "food_table":"usda-fdc"}
```

There is no confidence field. No corpus of photo-estimated meals scored
against weighed truth exists, so a number there would be a decimal point
pretending to be calibration. **The range is the confidence statement.**

## How a value says where it came from

Every observation dataset carries the provenance chain:

- **`source`** is the terminus: which app, device or person the value reached
  us from. A catalogued registry, not free text.
- **`origin`** is what actually observed it, and **`path`** the hops in
  between. A step count relayed by three apps has one origin and three hops.
- **`capture`** is HOW it was acquired: `narrative`, `photo`, `ble`,
  `connector`, `file_export`, `manual_entry`, `derived`, `unknown`. Plus
  `read_by` when somebody else entered it.
- **`modelled`** names the fields on a row that are model output rather than
  observation. **A consumer summing a column must check it**: an inflated
  estimate reaching a deficit reads ON TARGET while the scale goes up.
- **`artifact`** is a content address (`sha256:...`) for the evidence the
  value was read from.

## Three clocks

| Clock | Question | Set by |
|---|---|---|
| `date` | when did this become true | you, and legitimately backdated |
| `recorded_at` | when was this line written | the machine, never by hand |
| `measured_at` / `start_time` | when was it measured | the device |

`recorded_at` makes the record **bitemporal**, which is what lets
`Vitai(root, as_of=...)` reconstruct what the record said at a past instant
rather than what it says now with hindsight applied. That is a different
question from which goals applied on a given date.

## Corrections: append, never mutate

```json
{"date":"2030-05-01","kg":80.4,"source":"scale",
 "supersedes":"2030-05-01/app","note":"recalibrated"}
```

The loader drops superseded lines; git history plus the supersedes chain is
the audit trail. Datasets whose rows are not unique per date key on an
identity tuple instead, so a correction can name one set out of four rather
than retiring the whole block.

## Computed values declare what they stand on

```json
{"date":"2030-05-08","kg":79.5,"source":"calc","capture":"derived",
 "derived_from":["weight:2030-05-01:scale"],"derived_op":"seven day mean"}
```

| key | says |
|---|---|
| `derived_from` | the rows this value was computed from, as `dataset:date:source` references |
| `derived_op` | how, in the athlete's own words |

A reference can name more than one row, because a date and a source do not
always identify one. There is no ordinal to disambiguate it: a positional one
was built and removed as unsound (#239), since positions are assigned at read
time in merged order and a device syncing a row stamped earlier renumbers the
group, so a reference written last week would name a different row. Naming an
earlier row exactly needs an ordinal STORED on it at write time, which is open
work. Until then a reference that matches several rows is reported by
`validate` and is not silently resolved.

Both are **declared, not executable**. `derived_op` is a description; nothing
re-runs it, and a consumer must not treat it as a formula. A row carrying
`derived_from` must also carry a derived `capture` - a computed value that
renders as an observation is exactly the laundering the provenance layer
exists to prevent.

In the read model `derived_from` is stored as a JSON array in a TEXT column,
so a consumer reads it with `json.loads`.

Two behaviours follow, and both are contract promises:

- rows standing on a shared input count as **one** witness in
  `independent_sources`, however many rows they are, and the sharing is
  transitive through a chain;
- restating an input raises a `stale_derivation` finding on everything
  computed from it. The value is flagged, never recomputed, and the finding
  reports that the input was restated rather than claiming to know which
  version the derivation used - a row reference names a date and a source,
  not a version.

Lineage that loops back to itself raises `derivation_cycle`, which is an
error rather than a finding.

## Retired keys stay legal

A generalised key is retired, not removed: an old line carrying it keeps
validating. Whether it is also READ FORWARD depends on which kind of
retirement it was, and the two are not interchangeable.

`daily.hip_pain` became `pain` + `pain_site`, and that is a RENAME that
widened: the old value is exactly a valid new value, the site is recovered
from the field's own name, and `resolution.canonical_daily` reads every old
line forward. Nothing is lost and nothing needs doing.

`sessions.location` became `place` + `route`, and that is a SPLIT into
different types. Free text is a valid value of neither, and which one a given
string belongs in is a judgement only the athlete can make - "canal path"
could be either. So nothing maps it forward, deliberately. The column still
holds what the line said; no successor inherited it, so nothing built on
`place` or `route` sees it, and a `review` tripwire says so on any record that
carries one.

`schema.KEY_FORWARD` and `schema.TERMINAL_RETIREMENT` are the register, and
they partition every retired key, so this page is checkable rather than
merely written.

Write the current names on new lines. Retiring is a three-part change, and the
part that gets missed is that every reader must prefer the successor.

## Thresholds (`vitai.toml`)

```toml
[targets]
# phases = [[80.0, 76.0, 0.70], [76.0, 73.0, 0.50]]  # from_kg, to_kg, kg_per_week

[tripwires]
# easy_hr_cap = 150
# rhr_baseline = 52
# steps_floor = 10000
# sleep_floor_h = 7.0
# pain_gate = 3

[preferences]
# intake_buffer_pct = 15   # margin on ESTIMATED intake, applied to all or none
```
