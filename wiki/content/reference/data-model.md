---
title: Data model
---

Three health-domain datasets, one JSON object per line, keys never omitted
(`null` for unknown), units in the key name, ISO-8601 dates.

## data/weight.jsonl

```json
{"date":"2030-05-01","kg":80.0,"source":"app","note":null}
```

## data/daily.jsonl

```json
{"date":"2030-05-01","steps":12000,"distance_km":9.1,"active_min":300,
 "kcal_out":2900,"kcal_in":2200,"protein_g":150,"sleep_h":7.5,"rhr":52,
 "hip_pain":0,"alcohol":false,"note":null}
```

`hip_pain` is a 0-10 scale and drives the pain-gate tripwire.

## data/sessions.jsonl

```json
{"date":"2030-05-01","type":"run","distance_km":8.0,"duration_s":2700,
 "avg_hr":148,"max_hr":null,"cadence":170,"kcal":500,"location":null,
 "rpe":6,"note":null}
```

`type` is one of `run`, `gym_a`, `gym_b`, `walk`, `test`, `other`. Pace and
averages are derived on build, never stored.

## Corrections: append, never mutate

```json
{"date":"2030-05-01","kg":80.4,"source":"scale",
 "supersedes":"2030-05-01/app","note":"recalibrated"}
```

The loader drops superseded lines; git history plus the supersedes chain is
the audit trail.

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
```
