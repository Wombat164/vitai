<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/vitai-lockup-dark.svg">
    <img src="assets/vitai-lockup.svg" alt="vitai" width="320">
  </picture>
</p>

<p align="center"><b>The AI health coach you own.</b> Your health, on the record.</p>

<p align="center">
  <a href="https://github.com/Wombat164/vitai/actions/workflows/ci.yml"><img src="https://github.com/Wombat164/vitai/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Wombat164/vitai/releases/latest"><img src="https://img.shields.io/github/v/release/Wombat164/vitai?color=0EA5A0" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Wombat164/vitai?color=84CC16" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-7C8899" alt="Python 3.11+">
  <a href="SECURITY.md"><img src="https://img.shields.io/badge/read-SECURITY.md-FFB000" alt="read SECURITY.md"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#the-three-layers">How it works</a> &middot;
  <a href="#the-data-model">Data model</a> &middot;
  <a href="#skills">Skills</a> &middot;
  <a href="https://wombat164.github.io/vitai/">Docs site</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

Most fitness apps own your data, hide their logic, and give everyone the same
advice. vitai inverts all three: your record is plain text in a **private git
repo you control**, the numbers come from a **deterministic engine** you can
read in an afternoon, and the coaching comes from an **LLM loaded with skills
and your full profile** - not a one-size-fits-all algorithm. Progress you can
prove, in a record no vendor can take away.

### At a glance

|  |  |
|---|---|
| **Your data lives** | in a private git repo you own, as plain-text JSONL |
| **The engine is** | pure Python 3.11+, **zero dependencies**, deterministic, offline |
| **The LLM does** | coaching and ingestion. It never computes a number you are judged on |
| **Corrections** | append a new line; nothing is ever edited or deleted |
| **Weekly cost** | designed to stay under three minutes |
| **It will not** | diagnose, screen for, or tell you to see anyone about a condition |

> [!NOTE]
> **New here?** The [Quickstart](#quickstart) is four commands. If you would
> rather read first, [the docs site](https://wombat164.github.io/vitai/) is
> organised by what you are trying to do.

## See it

A synthetic demo athlete lives in [`examples/demo/`](examples/demo/)
(script-generated, CI-verified). `vitai build --root examples/demo` turns
plain-text data into this rollup:

```
## Weight
| Date | kg | 7d avg |
| 2030-06-30 | 78.0 | 78.1 |

**Rate:** +0.26 kg/week vs target 0.35 - **ON TARGET**
> Judge on this line, never a single morning.

## Tripwires
- **Sleep 6.9h avg** - under the 7h floor
- Steps 9,808/day avg - floor met
```

and `vitai verdicts --root examples/demo` emits the machine-readable contract a
game or dashboard consumes:

```json
{"week": "2030-04-22", "metric": "weight_rate", "value": 0.36, "target": 0.35, "verdict": "on_target"}
```

## The three layers

```
CONTENT   (your private repo)   profile.md, plan.md, vitai.toml, data/*.jsonl
    |
ENGINE    (this repo, code)     append-only JSONL -> SQLite + weekly rollup
    |                           deterministic, rebuildable, no LLM in the numbers
INTELLIGENCE (this repo, skills)  LLM coaching, ingestion, onboarding, red-teaming
                                  reads the engine's outputs, never recomputes them
```

- **Content is private.** Your body, your history, your plan. It never touches
  this repo. `vitai init` stamps out a content repo skeleton for you.
- **The engine is deterministic.** One JSON object per line, append-only,
  corrections supersede rather than overwrite, and everything derived (SQLite
  database, weekly rollup, tripwires) is rebuilt from scratch on every run.
  If the LLM and the engine disagree about a number, the engine is right.
- **The intelligence layer is where the value is.** Skills (Claude Code
  compatible `SKILL.md` packages) that know how to coach a weekly check-in,
  turn a screenshot or API response or web page into schema-valid data lines,
  onboard a new athlete into a profile and plan, and red-team that plan against
  the recorded evidence.

## Quickstart

```bash
pip install -e .
vitai init ~/health        # stamp a private content repo skeleton
cd ~/health
# ... fill profile.md, tune vitai.toml, append data lines ...
vitai build                # data/*.jsonl -> derived/health.db + derived/weekly.md
vitai status               # one-line state: latest weight, 7d rate, tripwires
vitai validate             # schema-check every data line before committing
```

Weekly cost is designed to stay under three minutes: append a handful of JSONL
lines, `vitai build`, commit. The rule the whole design serves:

> **Sparse and continuous beats rich and abandoned.**

## The data model

One JSON object per line, keys never omitted (`null` for unknown), units in
the key name.

Field names carry a **display** unit, for human writability. The
**authoritative** unit is [UCUM](https://ucum.org/), declared per field in the
schema registry and per connector in its manifest, so a connector author never
has to infer a unit from a name. See
[docs/schema-versioning.md](docs/schema-versioning.md).

Three datasets record what happened:

| File | One line per | Example keys |
|---|---|---|
| `data/weight.jsonl` | weigh-in | `kg`, `source`, `measured_at` |
| `data/daily.jsonl` | day | `steps`, `kcal_in`, `kcal_out`, `sleep_h`, `rhr`, `pain`, `pain_site` |
| `data/sessions.jsonl` | training session | `type`, `distance_km`, `duration_s`, `avg_hr`, `rpe`, `track` |
| `data/sets.jsonl` | **one SET**, not one exercise | `exercise`, `reps_completed`, `reps_attempted`, `load`, `failure` |
| `data/meals.jsonl` | **one ITEM**, not one dish | `item`, `grams`, `grams_lo`, `grams_hi`, `food_table` |
| `data/measurements.jsonl` | anchor read off an instrument | `kind`, `value`, `source` |

...and these record what you were aiming at, or what the engine was told, dated:

| File | One line per | Example keys |
|---|---|---|
| `data/goals.jsonl` | goal declaration or edit | `slug`, `metric`, `target`, `policy`, `motivator` |
| `data/thresholds.jsonl` | threshold change | `key`, `value`, `change_kind`, `reason` |
| `data/achievements.jsonl` | recorded accomplishment | `title`, `goal`, `source` |
| `data/context.jsonl` | situational mode change | `mode`, `facilities`, `place` |
| `data/medical.jsonl` | step in one condition's lifecycle | `slug`, `kind`, `severity`, `status`, `restricts` |
| `data/events.jsonl` | dated real-world fixture | `slug`, `kind`, `event_date`, `priority`, `immovable` |
| `data/checks.jsonl` | a check performed and its result | `slug`, `result`, `value` |
| `data/journal.jsonl` | something said, worried about, decided | `kind`, `text`, `about`, `status` |
| `data/inferences.jsonl` | a MODEL-inferred claim | `statement`, `confidence`, `model`, `depends_on` |
| `data/artifacts.jsonl` | evidence kept for a value | `sha256`, `media_type`, `bytes`, `removed` |

Two of those are deliberately finer-grained than they look. **A set, not an
exercise**: anything coarser cannot say that a load was attempted and not
completed, or that a set stopped short of failure, and `failure: null` means
UNSTATED and is never read as a maximum. **An item, not a dish**: a dish-level
number cannot be corrected, cannot be questioned, and cannot say which part of
it is uncertain.

`sessions.start_time` should carry a UTC offset. Naive local time is still
legal - existing rows are history, not mistakes - but two shapes cannot be
compared as instants, so the engine declines the comparison and says so rather
than guessing an offset. `vitai validate` reports a mixed record as an
advisory.

Every dataset also carries **`recorded_at`** - transaction time, stamped by
`vitai append` (pipe JSONL to import in bulk), never written by hand. It is a
hybrid logical clock at microsecond resolution, so a thousand rows written in
one loop still order against each other. `date` says when something became true
and may be backdated; `recorded_at` says when the line was written and may
not. Together they order two rows that share a date, which file position used
to do by accident.

Corrections are appended with `"supersedes":"<date>/<source>"` - a wrong line
is never edited. The audit chain is the point: how a number changed is often
more informative than the number. Goals and thresholds supersede by slug
(`"<slug>@<date>"`), and appending a same-slug line WITHOUT `supersedes` is an
edit rather than a correction: both lines stay, and the pair is the history.

Because policy is dated, every past day is judged against the targets that
were in force *then*. Loosening a goal today cannot turn last month's misses
into hits on the next rebuild. The engine derives how often policy moves
(`plan_churn`) and flags a loosening timed right after a miss - a prompt to
explain, never an accusation.

Targets and tripwires (rate-of-loss phases, easy-run HR cap, resting-HR
baseline, steps floor, pain gate) start in the content repo's `vitai.toml`,
not in code - the engine is the same for everyone, the thresholds are yours.
Once you change one, record it in `thresholds.jsonl` so the old value keeps
governing the weeks it governed.

Five design decisions that shaped the rest. Expand what you need.

<details>
<summary><b>Safety is a branch, not a sentence</b></summary>


One decision in this system is not a coaching input: whether the engine
stops. It used to live as prose in a skill file, which meant a coach
optimising for adherence could reason around it, soften it, or simply not
reach it. Prose can be argued with; a branch cannot.

So the rules are code, the escalation messages are constants, and no part of
either is generated. The engine has triggers that depend on nothing a model
judged - a body site that is never assumed musculoskeletal, thresholds
outside physiological range, and a composite over numbers you already log -
and it also honours a red flag a skill raises. The asymmetry is deliberate: a
model can only ever **add** an escalation, never remove one.

An open medical episode that restricts an activity is a **gate**: a
deterministic fact about a date. A coach may explain a gate. It cannot clear
one, defer one, or suggest a substitution around one. Gates clear when the
record says the episode resolved.

Anything urgent surfaces the moment the record is rebuilt rather than waiting
for the weekly rollup, and `vitai safety` exits non-zero while it stands.

Some rules fire with **no configuration at all** - absolute resting-heart-rate
bounds, an intake floor, a protein floor - because a safety net you have to
switch on protects only the people who already knew they needed it. The
text rules read free-text notes too, since frightened people write "it's
nothing, not really worth going on about" rather than filling in a field.

The most serious finding raises a **hold**: not a louder warning but
a suspension, routed through the same gate mechanism, so no plan or session is
issued while the record still shows the pattern.

None of it is diagnosis. Every escalation states what was observed and what
vitai will therefore not do, and the thresholds are deliberately conservative
bounds outside which no training is programmed - the resting-heart-rate floor
sits below a trained athlete's genuinely low rate, because a layer that
refuses at normal physiology teaches people to ignore it.


</details>

<details>
<summary><b>Where it hurts</b></summary>


`pain_site` is a closed vocabulary rather than free text, so "knee", "Knee",
"IT band" and "patella" are one countable place rather than four unrelated
ones. Sides are a separate field (`pain_side`), following HL7 FHIR and
openEHR - both post-coordinate laterality rather than folding it into the
site name. A paired structure needs a side to be actionable; a midline one
refuses it.

The vocabulary lives in `semantics/body_sites.toml` - a curated registry:
neither data nor code, versioned in-repo, with its evidence in its own
comments. Granularity follows the Michigan Body Map, a validated self-report
instrument, trimmed to the musculoskeletal sites a training record can act
on. No clinical ontology is vendored; see
[docs/prior-art-anatomy.md](docs/prior-art-anatomy.md) for why.


</details>

<details>
<summary><b>One truth per quantity</b></summary>


Two sources will eventually describe the same day, and a calorie is burned
once. The engine resolves competing claims into ONE canonical value per
quantity - field by field, by source precedence - and never sums them. The
watch can win `kcal_out` while the food ledger wins `kcal_in`, on the same
day. One run logged on two platforms is matched by overlapping timestamps
and collapses to one run.

Raw claims are all retained, and `vitai resolve` explains every contested
field: which source won and why. Physically impossible arithmetic (sessions
burning more than the day did) is flagged as a conservation tripwire and
never quietly fixed - the contradiction is the useful part.

Each canonical value carries a justification, so a correction cascades:
retract the observation and anything that stood on it retracts too, rather
than lingering as a belief whose evidence no longer exists.


</details>

<details>
<summary><b>What a computed value stands on</b></summary>


Some numbers are observed and some are worked out from other numbers, and the
record says which. A row that was computed names its inputs in `derived_from`
and describes the arithmetic in `derived_op`, in the athlete's own words.

Both are DECLARED, not executable. `derived_op` is a description rather than a
formula, and nothing re-runs it - not a consumer, and not the engine. That is
deliberate: a lineage you can read is checkable by a person, where a lineage
you can execute quietly becomes a second implementation of the number that
drifts from the first.

Declaring the inputs buys two things that are hard to get any other way.

**A derived value never corroborates its own inputs.** Two rows computed from
one scale reading are that reading twice with arithmetic on top, so they count
as ONE witness rather than two, and agreement between them raises no
confidence. Sharing is transitive: a value derived from a value derived from a
reading is still not a second look at the athlete.

**A restated input flags everything standing on it.** Correct a reading and
every value computed from it raises a `stale_derivation` finding. The stale
number is left exactly where it is, visibly flagged - the engine cannot re-run
a description, so it cannot produce a corrected value, and a confident wrong
one is worse than an old one you can see is old.

The finding says the input was RESTATED and asks which version was used. It
does not claim to know: a row reference names a date and a source rather than
a version of that row, so a derivation from the corrected value reads the same
as one from the original. Where the engine cannot tell, it says so instead of
guessing.

Lineage that leads back to itself, directly or around a loop, is an error
rather than a finding - a value cannot be an input to its own computation.


</details>

<details>
<summary><b>Schema migrations</b></summary>


| Contract | Version | Change | What an existing repo must do |
|---|---|---|---|
| 1 | 0.2.0 | Founding tables + `verdicts`, `meta` | - |
| 2 | 0.3.0 | Adds `goals`, `thresholds`, `achievements` datasets; `contributions`, `milestones`, `plan_churn`, `goal_progress` derivations; a `goal` column on `verdicts`; `dataset`/`session_type` scope fields on goals | Nothing required - `vitai build` creates the new files and tables, and a repo with no goals simply has empty ones. To adopt: append goal lines, and move any threshold you have since changed out of `vitai.toml` into `thresholds.jsonl` |
| 3 | 0.3.0 | Adds `measurements` + `context` datasets, generation-2 provenance/context fields on `daily` and `sessions`, and the resolution layer: primary tables now hold CANONICAL rows, with `claims`, `resolution`, `justifications`, `conservation` and `retractions` alongside | Nothing required. `hip_pain` is retired, not removed: old lines keep validating and are read as `pain` at site `hip`, and the same applies to `sessions.location` -> `place`/`route`. A single-source repo resolves to exactly what it built before. To adopt: start writing `source` on new lines, and add `[resolution.precedence]` to `vitai.toml` when a second source appears |
| 4 | 0.3.0 | Adds the `medical` dataset and the safety layer's outputs: `gates` (what is blocked today and why) and `escalations` (deterministic severity-to-action) | Nothing required. **A consumer that renders training suggestions MUST read `gates`**, or it will propose activity the record has already blocked |
| 5 | 0.3.0 | Adds the `checks` dataset, `onset_date`/`precondition` on `medical`, `occurred_date` on `achievements`, and `status`/`precondition` on `gates` | Nothing required. **A consumer reading `gates` MUST now check `status`**: a row with status `cleared` is reported but does not block. Not-done is not pass - a gate whose check was never recorded stays uncleared |
| 6 | 0.3.0 | Adds the `events` dataset (dated real-world fixtures), `deadline_kind`/`event`/`verification`/`change_kind` on `goals` (generation 2), `deadline_kind` on `plan_churn`, and `days_to_deadline`/`event`/`verification` on `goal_progress` | Nothing required; gen-1 goal lines keep validating unchanged. **Two things a consumer must act on.** A `goal_progress` row with `verification` of `attested` has no metric, no target and no progress: render it as a goal nothing can measure, never as 0%. And a `plan_churn` row is only a retreat from a deadline when `deadline_kind` is `hard` - a consumer reading `deadline_pushed` alone will accuse the athlete of gaming a date they invented |
| 7 | 0.3.0 | Adds `recorded_at` (transaction time) to **every** dataset and `measured_at` (observation time, HH:MM local) to `weight`. Resolution orders by `(date, recorded_at)` instead of falling back to file position | Nothing required, and the migration is a read no-op: absent sorts before present, so a file of unstamped rows resolves in exactly the order it always did. **A consumer that reconstructs history MUST order by both clocks**, or a same-date correction resolves by whatever order the rows happen to be in. A `weight_rate` verdict may now be `nodata` because the weigh-in times behind it are spread widely enough to account for the rate. To adopt: write new rows through `vitai append` / `Vitai.append()`, which stamps the clocks the machine owns |
| 8 | 0.3.0 | `goal_progress` gains `dataset` (the scope the goal actually draws from, inferred from the metric where the row left it unset) and `scope` (`declared` \| `inferred` \| `ambiguous` \| `undeclared`) | Nothing required. **A consumer must not read an unset `dataset` as "the default"** - unstated and stated-as-daily are different things. And a goal the engine cannot score - attested, external, or drawing on a dataset it does not count from - now reports `counted` and `progress_pct` as **null rather than 0**. Render that as "not scored here", never as a goal at 0% |
| 9 | 0.3.0 | Adds `track` (repo-relative path to the stored GPX/FIT/TCX), `activity_id` (the platform's opaque id) and `activity_source` (who ASSIGNED that id, not necessarily who recorded it) on `sessions` | Nothing required. **`activity_id` is TEXT and must never be read as a number** - leading zeros and ids past 2^53 both occur. It is also the per-row identity a session lacked, so a correction can name one of two runs on a day instead of retiring both |
| 10 | 0.3.0 | Provenance as a CHAIN: `origin` (what observed reality), `path` (the ordered hops it travelled) and `origin_evidence` on the observation datasets, plus a `provenance` table carrying how many INDEPENDENT instruments observed each resolved row | **Two changes a consumer must make.** `witnesses` on `justifications` and `explanations` now counts distinct ORIGINS rather than rows, so five platforms carrying one device's file is **1**, not 5. And a `resolution` row carries `independent`: false means the two values are one measurement seen at two points on one pipe, so the spread measures pipeline fidelity and must never be read as agreement |
| 11 | 0.3.0 | The acquisition axis: `capture` (how a value was acquired) and `read_by` (who did the reading, where one happened) on the observation datasets; `origin`/`path`/`origin_evidence` reach `sessions`; `provenance.trust` gains a `transcribed` level. Also 11: the resolution audit - `resolution` gains `discarded` and `unattributed_loser`, plus an `unattributed_claim_lost` tripwire | **A `transcribed` value MUST NOT be rendered as device-measured** - a photograph of a console read by a model is an inference over an artifact, not a reading of an instrument. A consumer showing a canonical value can now say what it beat. There is deliberately no contract 12 in this sense: the two changes shipped within an hour under 11, so gating on 11 gets both |
| 12 | 0.3.0 | `modelled` on the observation datasets names the FIELDS on a row that are model outputs rather than observations; `type_source` on `sessions` says how a categorical label was assigned | **A consumer summing a column MUST check `modelled`**: an inflated estimate reaching a deficit reads ON TARGET while the scale goes up. A `type` carrying `vendor-classified` is a third-party model's guess, not something the athlete or a device asserted |
| 13 | 0.3.0 | The artifact store: an `artifacts` manifest table (hash, media type, size, why it was kept) and an `artifact` reference on weight, daily, sessions and measurements, so the evidence a value was read FROM survives alongside the value | **Two things not to get wrong.** A reference is a content address (`sha256:...`), not a path, and resolving one to bytes is a LOCAL lookup - the manifest travels in the read model, the artifacts do not, and nothing in this contract authorises transmitting one. And **REMOVED IS NOT MISSING**: an artifact the athlete deleted leaves a tombstone with a reason, and rendering that as broken evidence turns a retention decision into a data-loss alarm |
| 14 | 0.3.0 | A `sets` table, one row per SET: an attempted load that could not be completed, whether a set was taken to failure, and what kind of number a load is. Also `rpe` widens from integer to numeric across every dataset carrying it | **A NULL `failure` means UNSTATED and MUST NOT be read as maximal** - a set logged against a stated max read as one and was not, which is the defect this dataset exists for. And a `load` under `load_type: machine_stack` is a **pin number, not a mass**: 66 on two machines is two different loads, never comparable across machines and never rendered in kilograms. The `rpe` widening is strictly looser, so no row that validated before stops validating |
| 15 | 0.3.0 | A `meals` table, one row per INGREDIENT of a photographed meal, with a gram estimate, a gram RANGE, and the per-100 g composition figures as the food table gave them alongside the table's name | **Three things not to get wrong.** Energy and macros are DERIVED from the quantity and are not columns, so an item whose portion is corrected cannot keep a figure computed from the old one. There is **no confidence column and there will not be one** - the range IS the confidence statement. And **A MEAL IS NOT A DAY**: these rows never feed `daily.kcal_in`, a total must never be rendered without its range, and summing meals into a day asserts the athlete ate nothing they did not photograph |
| 16 | 0.4.0 | `device` on EVERY dataset, naming the machine that wrote the line down - distinct from `source`, which names the instrument that observed the value. Readers take `<dataset>.<device>.jsonl` alongside `<dataset>.jsonl` and union them | **One consumer-visible change**: a dataset may contain rows written by several machines, ordered by (recorded_at, device, position), and that order is TOTAL - two devices rebuilding the same file set produce byte-identical output. **A consumer must not treat two rows describing one event from two devices as two events**; `duplicate_captures()` reports them and the engine never merges them silently. A phone and a laptop are not two instruments, and conflating them would manufacture corroboration out of a sync |
| 17 | 0.4.0 | `meta` gains a `policy` row: a content hash of the config that is NOT in the append-only record | Nothing required, and nothing to adopt. It exists so two reconstructions taken under different `vitai.toml` files can be known to be incomparable. **The row is optional** - a read model built without a digest omits it, so absence means "built without one", never "pre-17" |
| 18 | 0.4.0 | `verdicts` gains `reason`: `no_data` was one word for four states, distinguishable only by which fields were null | Nothing required, and a reader that ignores the column sees the previous behaviour. **One change to notice**: a contraindicated or suppressed metric now appears as a labelled row rather than as an absence, so a consumer counting rows will see more of them. A removed row and an uncomputed metric were different facts rendered identically |
| 19 | 0.4.0 | `protocol` on weight and measurements (the CONDITIONS a measurement was taken under); the `protocols` and `regimes` datasets | Nothing required. **A consumer must not read an emptied interval as missing data**: a regime declares that a span of claims was UNANCHORED, the claims stay in `claims`, what ends is their standing as values, and nothing is filled in behind them. A row with no `protocol` is a different epistemic class from one with a protocol, not a row with a field missing |
| 20 | 0.5.0 | `derived_from` and `derived_op` on weight, daily, sessions, measurements, sets and meals: which rows a computed value stands on, and how, in the athlete's own words | Nothing required. **Both are DECLARED, not executable** - `derived_op` is a description, so do not re-run it and do not assume the engine did. Two behaviours to expect: rows standing on a shared input now count as ONE witness in `independent_sources` however many rows they are, so a consumer reading that field may see it fall; and a value whose input the record later retracted raises a `stale_derivation` tripwire and is left in place, flagged rather than corrected. Contract 20 also carries the five `daily` macro totals, the three per-100 g `meals` figures and the two `sleep` instants, which landed before it was released |
| 21 | 0.5.0 | `emissions`: what the engine TOLD the athlete, and when. Pass-through, append-only, never resolved | Nothing required, and an existing repo simply has an empty one. **Read it as DELIVERED, not computed**: it holds the assertions a consumer surfaced, not the verdicts the engine calculated, because a judgement nobody was shown had no consequence to retract. Written at delivery time through `api.assert_delivery`, never at build - a build that appended to the record would make a rebuild non-idempotent. `basis_claims` is a JSON array in a TEXT column |
| 22 | 0.5.0 | `verdicts` gains a `pending` reason and a `due` date: the question is answerable and not yet | Nothing required, and a reader that ignores both sees today's behaviour. **Do not treat `pending` as permanent**: it degrades to `no_input` once `due` passes, and the row keeps `due` so a late source reads as late rather than as still coming. `due` is earned from the source's own arrivals, so a source with no established cadence refuses with `no_input` exactly as before |
| 23 | 0.5.0 | `meta` gains a `built_on` row, and an unqualified build takes its viewpoint from the RECORD's last date rather than the wall clock | Nothing required, and an explicit `--on` behaves exactly as before. **Two things change for a build nobody dated**: it is now reproducible - the same record built on two days gives the same database - and `goal_progress` is populated where it was silently empty, because the viewpoint no longer lands on a day when no goal was in force. Read `built_on` to say 'as of X' rather than guessing |
| 24 | 0.5.0 | goals gain `polarity` (floor, ceiling, band, approach) and `target_hi` for a band's upper bound; `goal_progress` gains `polarity`, `target_hi`, `room_left`, `distance` and `breach` | Nothing required: an absent polarity reads as `floor`, which is what both existing policies already meant, so no row re-scores. **Do not assume `progress_pct` is present** - it is the FLOOR's measure and is null for the other three, because a percentage of a limit consumed is what made holding 1100 against a 1200 cap report 641%. A ceiling reports `room_left`, an approach reports `distance`, and `breach` says under or over. Milestones are minted for floors only. A goal whose title says cap while scoring as a floor now raises a validate advisory |
| 25 | 0.5.0 | goal status splits into two axes: `goals` gains `lifecycle_status` and retires `status`; `goal_progress` gains `lifecycle_status` and `achievement_status` | Nothing required. **Old lines keep validating** and read forward through one canonicaliser - `paused` becomes `on_hold`, `abandoned` becomes `cancelled`, and `achieved` SPLITS into lifecycle `completed` plus achievement `achieved`. `status` keeps its column on `goal_progress` carrying the same value as `lifecycle_status`, so a consumer reading the old name is unaffected. `achievement_status` is DERIVED and never authored: a goals line is a declaration, and the engine does not write its opinion into one |
| 26 | 0.5.0 | a declared SCALE beside each subjective number: `rpe_scale` on sessions and sets, `mood_scale` and `pain_scale` on daily, naming a slug from `semantics/scales.toml` | Nothing required. **Absent means unstated and a consumer must not invent a denominator** - rendering "4 out of 10" against an undeclared scale asserts a bound the record never carried, and the honest render is the bare number and a note that no scale was declared. Where a scale IS declared the value is validated against its range. Post-coordinated rather than fixed per field, so an imported row can say which scale its source used - a vendor export may well be the other one |
| 27 | 0.5.0 | `best_efforts`: the fastest 1k, 5k, 10k, half and full of every stored track, one row per (track, distance) | Nothing required. **Read `basis` before quoting a time** - `device` means the window was measured against the watch's own cumulative distance, an observation, and `derived` means against the haversine sum the engine computes, which is not. `seconds` is ELAPSED: a stop inside the window counts, because excluding it would be the engine deciding which pauses were real. A track shorter than a window yields no row for it, which is the record declining to answer rather than a zero |

This table is the summary and `src/vitai/db.py` is the source: the same
history lives beside `CONTRACT_VERSION`, at more length and with the
reasoning. The two had drifted - this table stopped at contract 8 and the
wiki's at 4, while the engine was at 16 - and a test now holds all three
together, because that drift was invisible until somebody went looking.


</details>

## Skills

| Skill | What it does |
|---|---|
| `vitai-onboard` | Interview + uploaded data -> `profile.md`, `plan.md`, tuned `vitai.toml` |
| `vitai-coach` | The weekly check-in: read the rollup, judge the rate line, adjust |
| `vitai-ingest` | Screenshots / exports / APIs / web pages -> schema-valid JSONL lines |
| `vitai-redteam` | Gap analysis of the plan against the recorded evidence |

Install by pointing your agent harness at `skills/` (Claude Code: copy or
symlink into `~/.claude/skills/`). Each skill assumes the content repo layout
that `vitai init` produces.

## Build on vitai

The engine is a platform surface: `vitai.api.Vitai(root)` gives typed reads
over one user's store, `derived/health.db` is a versioned contract (tables
per dataset + `verdicts` + `meta`), and `vitai verdicts` emits weekly
goal-attainment rows as JSONL. A game or dashboard hosting thousands of
users runs one store per user and aggregates verdicts in its own database -
the per-user record stays the atom, by design (see
[ARCHITECTURE.md](ARCHITECTURE.md), "The platform").

The reference consumer is
**[vitai-lens](https://github.com/Wombat164/vitai-lens)** - a local-first
stats dashboard (trends, heatmaps, weekly loads, verdict strips) that reads
`health.db` entirely in the browser. It exists in a separate repo on
purpose: it consumes the same contract any third party would.

A model can also write back: `vitai infer` (opt-in via `[inference]` in
`vitai.toml`, backends: your Claude CLI or any OpenAI-compatible endpoint
such as Ollama) reads the rollup and recent data, and appends
schema-validated knowledge to `data/inferences.jsonl` - the third data
tier: append-only, provenance-carrying, and never part of the deterministic
number path.

## Connectors

Deliberately thin, see [`connectors/README.md`](connectors/README.md). The
integration doctrine is LLM-mediated: API-first where an API exists, webcrawl
or export-file fallback where it does not, and in every case the LLM emits
schema-valid JSONL that `vitai validate` checks before anything is committed.
Hard-coded per-vendor sync daemons are a non-goal until a manual record has
proven durable.

## Status

0.5.0 (August 2026), contract 27. The engine, the skills and the boundary
enforcement work, and the surface a client application needs is in place: the
whole state in one call, a write path that stamps its own provenance, a version
to pin against, and refusals that say which kind of no. Connectors are doctrine
plus stubs. Built from a real, in-use personal
deployment, and validated against ten synthetic athletes who each break
something.

> [!NOTE]
> **vitai logs training, nutrition and body data; builds and adjusts training
> programmes; and lets you read your own record.** It is not intended to
> identify, monitor, explain, treat or compensate for any disease, injury or
> condition. Where the record is incomplete, or where you have flagged
> something, the engine declines to produce a programme and says only that.
> What you do about your health is yours to decide.
>
> See [the medical boundary](https://wombat164.github.io/vitai/explanation/medical-boundary)
> for what that means in practice and how it is enforced, and
> [SECURITY.md](SECURITY.md) for the threat model and data-privacy notes.

## Documentation

**Start here:** the [docs site](https://wombat164.github.io/vitai/), built from
`wiki/` and organised by what you are trying to do - getting started, CLI
reference, data model, architecture, the platform contract, the boundary.

The files below are the engineering record. They are written for someone
changing the engine, not for someone using it.

| Read this | when you want |
|---|---|
| **[docs/model.md](docs/model.md)** | the spine: eight principles, five artifact kinds, the full gap map. **Read first.** |
| **[docs/medical-boundary.md](docs/medical-boundary.md)** | what the engine is for, what it may say, and the one exception. **Read before touching anything about injury, pain or care.** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | the layers, and what is deliberately not built |
| [docs/vocabularies.md](docs/vocabularies.md) | one axis per vocabulary, post-coordinate, registry not code |
| [docs/schema-versioning.md](docs/schema-versioning.md) | what counts as a breaking change, and how a retired key announces itself |
| [docs/persona-doctrine.md](docs/persona-doctrine.md) | how the ten synthetic athletes work, and what makes one valid |
| [docs/the-loop.md](docs/the-loop.md) | the design conversation: a 185-question acceptance bank |

<details>
<summary><b>Research and prior art</b></summary>

- [docs/prior-art.md](docs/prior-art.md) - the landscape survey behind the
  design, and why the position is unoccupied
- [docs/prior-art-schemas.md](docs/prior-art-schemas.md) - which published
  health, activity, calendar, plan and provenance schemas are worth conforming
  to, and which are dead. Red-teamed; carries a staleness caveat
- [docs/prior-art-world-model.md](docs/prior-art-world-model.md) - vitai as a
  guardrailed world model
- [docs/prior-art-anatomy.md](docs/prior-art-anatomy.md) - naming the place
  that hurts
- [docs/cross-metric-inference.md](docs/cross-metric-inference.md),
  [docs/plan-v3.md](docs/plan-v3.md)

</details>

Brand assets and usage: [assets/BRAND.md](assets/BRAND.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: tests land with
the change, no personal data ever (CI-gated), the engine stays
deterministic, and PRs scope themselves honestly. Security reports go
privately via [Security Advisories](https://github.com/Wombat164/vitai/security/advisories/new),
never public issues.

## License

MIT.
