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
| `data/plans.jsonl` | what a day was meant to be, resolved later | `slug`, `for_date`, `activity`, `tier`, `outcome` |
| `data/thresholds.jsonl` | threshold change | `key`, `value`, `change_kind`, `reason` |
| `data/capabilities.jsonl` | what an instrument can and cannot measure, dated | `origin`, `measures`, `competence`, `construct` |
| `data/instruments.jsonl` | the entity behind an origin, over an interval | `origin`, `from_date`, `to_date`, `maker` |
| `data/comparability.jsonl` | whether two instruments are on the same footing, EARNED by overlap | `field`, `origin_a`, `origin_b`, `status`, `basis` |
| `data/protocols.jsonl` | a measurement's conditions, declared or corrected | `slug`, `text` |
| `data/achievements.jsonl` | recorded accomplishment | `title`, `goal`, `source` |
| `data/context.jsonl` | situational mode change | `mode`, `facilities`, `place` |
| `data/regimes.jsonl` | interval a whole class of claims went unanchored | `from_date`, `to_date`, `dataset`, `field` |
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
| 3 | 0.3.0 | Adds `measurements` + `context` datasets, generation-2 provenance/context fields on `daily` and `sessions`, and the resolution layer: primary tables now hold CANONICAL rows, with `claims`, `resolution`, `justifications`, `conservation` and `retractions` alongside | Nothing required. `hip_pain` is retired, not removed: old lines keep validating and are read as `pain` at site `hip`. `sessions.location` is retired too, but is NOT the same case and never was read forward - this row said it was, and was wrong. It split into `place` and `route`, which are different types rather than new spellings, and free text is a valid value of neither. Old lines keep validating and the column still holds what they said; no successor inherited it, so nothing built on `place` or `route` sees it. Whether a location was a place or a route is yours to state (see contract 38). A single-source repo resolves to exactly what it built before. To adopt: start writing `source` on new lines, and add `[resolution.precedence]` to `vitai.toml` when a second source appears |
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
| 28 | unreleased | `session_weeks`: sessions, distance and duration per week per session type, with a row for every week in range including the ones holding nothing | Nothing required, and a reader that ignores the table sees today's behaviour. **Do not re-bucket the types** - the vocabulary is the engine's, and a consumer that mapped them onto its own dropped 17 of 43 sessions with their distance and drew a plausible chart anyway. **A week of zeros means the record holds no sessions for it**, never that the athlete did nothing: those are different facts and telling them apart needs coverage. `distance_km` and `duration_s` sum only the rows carrying one and are null where none did, so a count of 3 beside a distance drawn from 1 is a partly logged week rather than a short one |
| 29 | unreleased | `verdicts` gains `statistic` (what KIND of number `value` is, from `semantics/statistics.toml`) and `window_days` (over what population) | Nothing required, and a reader that ignores the column sees today's behaviour. **Read it before rendering a weekly figure**: one column carried a maximum, a week-over-week change and six averages, and `steps` at 9752 for a week is the DAILY AVERAGE - read as a weekly total it describes a week five thousand steps a day short of the one that happened. `pain_gate` is a MAXIMUM, because a gate is about the worst day, and `energy_availability` is a composite of summaries with different denominators rather than any mean. **The safety floors are means over FOURTEEN days on a row keyed by one week**, which is what `window_days` exists to say. Terms are IEEE 1752.1's `descriptive-statistic` VERBATIM where they reach, checked against the published enum rather than asserted - `standard deviation` has a space there where our slug has a hyphen; a between-window comparison has no term there and carries a `vitai`-namespaced one instead of being bent into `average`. Present wherever there is a value and absent on a refusal, which has no number to describe |
| 30 | unreleased | `goal_progress` gains `observed`: the latest value of a LEVEL metric, where `counted` is a sum | Nothing required. **A goal to reach a level is not a goal to accumulate**, and one scored as the latter reported nothing at all - no count, no percentage, no breach. A level goal now carries `observed` and null `counted`; a flow goal the reverse, which is how a consumer tells the shapes apart without being taught which metrics accumulate. `room_left` and `breach` work unchanged from contract 24. **Scored only where the direction is DECLARED**: polarity defaults to `floor`, and scoring an undeclared level against that default upgrades a null to an inversion - a goal 6.1 kg over its loss target reporting `achieved`. An undeclared level reports nothing, as before. **`weight` only**: `measurements` holds levels too and is out, being entity-attribute-value - a goal there would score against the latest reading of any kind. Levels in `daily` are not covered either - a resting-heart-rate goal still scores as an accumulation, because `daily` is a flow dataset and separating them needs a per-metric declaration. `validate` gains an advisory where a level goal declares no polarity, since the `floor` default reads a goal to lose weight as one to gain it |
| 31 | unreleased | `medical` gains `body_side` (which side an episode is on) and `events` gains `outcome` (what became of a fixture whose date arrived) | Nothing required; both are optional and an older line never owed either. **A side is what stops a gate over-restricting**: gating "the knee" bans a movement the athlete performs perfectly well on the other leg, and a gate reason now names the side where one was recorded. `outcome` is a SECOND AXIS beside `status`, not more values on it - `status` is what the fixture IS, `outcome` is what became of it, so a cancelled fixture carries no outcome and an outcome on a future date is refused. **Absent means nobody has said**, never "did not happen": rendering an unanswered outcome as a miss accuses an athlete of skipping a race the record knows nothing about |
| 32 | unreleased | `verdicts` gains `answers`: what the engine will VOUCH for on a row, beside the `reason` it will not | Nothing required, and a reader that ignores the column sees today's behaviour. **`direction` means the engine vouches only for ahead, behind or on track**, and a consumer must not present the figure as the thing being judged. A client cannot derive this: it would have to reimplement the per-field policy and every client would derive it differently. Four metrics are direction-only. `energy_availability` is a difference of two inexact aggregates, which amplifies the relative error rather than averaging it, so a remaining-budget figure can carry uncertainty larger than itself; and `weight_rate` fails on measurement rather than on principle - the pre-registered run measured a median `u_rate / half-band` of 1.74 and found MORE THAN HALF of scored weeks admit no verdict word at all - which does not support `direction` either, and whose own remedy is the refusal predicate #171 owns. Present on every judged row, absent on every refusal, which is `reason`'s totality in the other direction |
| 33 | unreleased | the `plans` dataset: what a day was MEANT to be, with `sessions.planned` retired | Nothing required, and a record with no plans has an empty table. **A plan is not a session** - `sessions` means this happened, and a skipped row there sums to zero and counts as one, corrupting every count silently. So a plan is its own row and a session cites it via `session_ref`. Identity is a SLUG because a plan is resolved later and must stay nameable while `outcome` moves. **Three things a consumer must not do.** `unresolved` means nobody has answered, NEVER a missed session, and any adherence figure over plans must state how many were unresolved. `reason` is COM-B (Michie et al 2011), a classification and never a score - nothing totals, ranks or trends it. And `tier` is not authorship: `set_by` carries that, and a coach-set plan can be as binding as a self-set one |
| 34 | unreleased | `derived_by` and `derived_build` on every dataset carrying a lineage: WHO computed a value this engine did not | Nothing required on an older line, and both are absent unless `capture` is `derived_external`. **`derived_external` said only "not this engine"**, which was enough with one consumer - #158 settled that several clients read one record on the same terms and any may derive, so two clients computing a pace agree when both are right and differ when one has a bug, with nothing to tell them apart. TWO fields rather than a slug, because an identifier like `client-0.1.0-a3f2` crams orthogonal facts into something a consumer must parse. **`by-hand` is a real value** - the one such row in every shipped fixture is an athlete taking a mean on paper - and it takes no build. **No install identifier**, deliberately: it is a tracking key, `device` already names the writing machine, and admitting one needs a rule about where it may travel |
| 35 | unreleased | `place_precise` on `sessions` and `context`, storable at last - and NO COLUMN FOR IT | The record's old stance was privacy by not storing the thing: `place` was documented as coarse and never an address. That is blunt, and it discards real utility, because "outdoors" cannot tell the park an athlete likes from the one they avoid. So the precise tier becomes storable, `place` keeps its name and its coarse meaning, and **a precise value is refused unless a coarse one travels with it** - required rather than derived, because reducing an address to "home" needs a lookup the build forbids or a mapping only the athlete holds, and a guessed coarse value would be wrong in the direction of looking right. **The read model is inside the boundary**: the coarse tier is the default egress form, dropped once at the read door, so every surface inherits it including this one. A column would be null on every row, and a null reads as "nobody wrote one" rather than "you are not being shown this". A consumer needing the precise tier names a release through `Vitai.precise()`. What it costs, recorded rather than discovered: a precise value that leaks cannot be un-leaked, and the claim moves from "we do not hold this" to "we hold it and it does not escape" |
| 36 | unreleased | `seq` on every dataset whose key can collide, and `supersedes_seq` beside `supersedes` | `line_key` falls back to `<date>/<source>`, so two runs on one day from one watch shared a name - 71 per cent of sessions on a live record. Contract 33 fixed what a reference RETIRES; what stayed broken was naming an EARLIER row, so five rows of one key written as a chain could not be repaired by appending at all. **Two fields, never a parsed reference**: `supersedes` is untouched, same spelling and same meaning, and every reference already written keeps doing what it did; the position travels in its own field. Spelling it into the reference as `K#n` was tried and abandoned, because nothing stops a bare key containing the separator and disambiguating by lookup made the meaning of a stored reference depend on what else was in view. **Stored, not computed** - read-time ordinals renumber when a device syncs a row stamped earlier. **Machine-set**: a caller may not supply `seq`, and it is the higher of the count of visible rows and one past the highest position among them. **What it does not fix**: two machines offline together stamp the same number, and `validate` reports that as a key nothing can name apart |
| 37 | unreleased | `avg_power` on `sessions` | The one field on a cycling row that is a MEASUREMENT rather than an estimate: `kcal` is modelled from heart rate and mass and `distance_km` from wheel size or GPS, while power is read from a strain gauge. The engine had nowhere to put watts, so any FIT ingest had to discard it. **`avg_power` rather than `power`**: a bare `power` is ambiguous between average, maximum and normalised, and normalised is the figure cyclists quote. No `max_power` and no normalised power - max is a spike a consumer can take from the track, and normalised is a weighted derivation this engine would be computing rather than recording |\n
| 38 | unreleased | An `unread_retired_value` tripwire, and the register behind it: `schema.KEY_FORWARD` names the one callable that reads each retired key forward, `schema.TERMINAL_RETIREMENT` says why the others are never read and what to do instead, and the two partition every retirement | **Nothing required, and nothing changes about what is stored.** A record carrying a terminally-retired key - `sessions.location` or `sessions.planned` - now sees one `review` tripwire per field saying no successor inherited those values and how to restate them. It is a `review`, not a fault: the lines are valid, they were the right way to write it at the time, and the engine will not guess which successor a value belonged to. Contract 3's row claimed `location` was read forward; it never was, and that claim is corrected there rather than left to be found by grep |
| 39 | unreleased | `verdicts` gains `observed_days`: how many days of the stated window actually held the metric | **Nothing required.** Contract 29 added `window_days` because a statistic with no stated population is half an answer; that was the denominator, and this is the numerator. Without it a `sleep` average over a `window_days` of 7 is indistinguishable from an average of one night - and this corpus publishes exactly that, judged against a floor. No threshold comes with it: the engine states the fraction and does not decide how thin is too thin |
| 40 | unreleased | `provenance` gains `field_sources`: on a MERGED row, which source supplied each field | **Nothing required, and nothing changes on a row with one writer.** A watch and a rowing console recording one session resolve to one row whose `source` reads `matrix-console+polar` - true of the whole row and of no single value in it. A consumer emitting a per-value `source` was uniformly wrong for half of them. `explanations` is not this: it records the winner of a CONTEST, and complementary instruments never contest. Derived, never stored, and absent unless the row is a merge |
| 41 | unreleased | `verdicts` gains `provisional`: the window includes a day the record marks `partial` | **Nothing required.** `daily.coverage` has been validated since generation 2 and read by nothing, so a weekly figure built over a day that was still being logged rendered exactly like one built over finished days - the case that produced a well-formed row asserting an intake shortfall that had not happened. Scoring an open day is fine; scoring it as final is not. A second field rather than a third value of `answers`, because a provisional magnitude is still a magnitude. Absent coverage is NOT read as complete |
| 42 | unreleased | `provenance` gains `field_origins`: which INSTRUMENT supplied which field, beside the `field_sources` map that says which FEED did | **Nothing required.** #325 asks which instrument supplied which field; contract 40 answered about the channel, which its own comment distinguishes - `source` is the feed a value arrived by, `origin` is the device that observed it. They come apart on the case the issue narrates: a hand-merged console row carrying a watch's heart rate forward attributed `avg_hr`, `max_hr` and `kcal` to the console, the exact fields the issue names as false of that source. A second map rather than a replacement, because `origin` is optional and folding them would delete the answer wherever it is absent. A claim that does not name its instrument contributes no entry |
| 43 | unreleased | `goal_progress` gains `milestones_total`: every milestone the goal has crossed, beside the `milestones` count that only ever meant THIS BUCKET | **Nothing required.** `milestones` counts crossings in the current bucket and its name never said so - on the shipped corpus a goal with 33 crossed milestones reported 0, because all 33 were earlier weeks. The old column keeps its exact meaning, because a consumer reading it today is reading a per-bucket figure and widening it would change every one of those readings invisibly. The rest of #330 needed no column: a `milestones` table already held date, goal, period, fraction, value, target and label, and the rungs NOT yet crossed are derived by `Vitai.milestone_ladder` |
| 44 | unreleased | A `capabilities` dataset: what an INSTRUMENT can and cannot measure, dated | **Nothing required.** An instrument change looks exactly like a physiological one, and `origin` said which instrument observed a value while nothing said what it is competent at. Categorical only - `competence` is measures / proxy / absent / unknown, a `construct` is required beside a proxy because an uncertainty figure cannot catch a wrong measurand, and there is no offset, tolerance or vendor figure anywhere. Keyed on `origin`, the identity the engine already uses. Silence resolves to `unknown` rather than to a default in a file, which is #148's defect one dataset over |
| 45 | unreleased | An `instruments` dataset: the ENTITY behind `origin`, over an interval | **Nothing required.** Contract 44 gave that identity capabilities and said a register would later give it an entity. The join is `(origin, date)`, never `origin` alone: "my watch" in 2026 and "my watch" in 2030 are different objects, and a lookup on the identity attributes every historical reading to whatever is on the wrist now. Overlapping intervals for one origin are refused at validation, or a reading belongs to two instruments at once. Named `instruments` and not `devices` because `device` is already on every dataset and names the MACHINE THAT WROTE THE LINE DOWN - the axis kept deliberately apart from the instrument that observed the value. Resolved on `origin` alone: 4331 of 9673 origin-bearing rows name a channel and no instrument, so a `source or origin` fallback would have made a re-export read as an instrument change. Every field optional but the identity and the start, and an unregistered origin resolves to nothing and renders exactly as it does today |
| 46 | unreleased | A `comparability` dataset: whether two instruments' readings of one field may be read as one series, EARNED BY OVERLAP and never asserted | **Nothing required.** The default is NOT COMPARABLE - deriving a trend across a source change needs an explicit statement that the two sides are on the same footing, never an assumption because both are called weight. Keyed on `origin_a`/`origin_b`, the same identity `capabilities` already uses for an instrument. `basis` is `overlap` and only `overlap`, closed to one value, because the whole point is that this cannot be asserted from a datasheet, a vendor figure or an athlete's say-so. Three statuses - `comparable`, `offset`, `not_comparable` - and **`offset` does not license a spanning derivation**: it records that a difference was measured and how big it was, never a licence to apply that number to a reading, which would be fabricating a measurement. The weight-rate instrument-seam refusal lifts only when every pair behind the window resolves to `comparable`. The resolver answers a pair ORDER-INSENSITIVELY even though the stored identity is not: asking whether a scale and a DEXA agree is one question regardless of which one is named first |
| 47 | unreleased | A `crossings` dataset: round-number and personal-first milestones, GOAL-INDEPENDENT and history-wide, plus `height_cm` joining `MEASUREMENT_KINDS` | **Nothing required.** `milestones` needs a declared goal and a scoring bucket; "you broke 80 kg" and "that is your lowest ever" are true or false of the weight series alone, so a new table rather than a fake goal and fraction forced into that one. Two kinds: `round_number` mints on crossing a multiple of 5 kg in either direction (a CHOICE of ladder, not a derivation), `personal_first` on a reading that is the lowest or highest the record has seen so far - the very first reading mints nothing, since it is trivially both and has no `previous_value` to cite as evidence. Every row carries that evidence pair, `previous_value`/`previous_date`: the last reading on the OTHER side of the crossing, without which a row would assert a fact about the series rather than cite one. Reads the CANONICAL weight series, never raw claims, for the same reason `milestones` does. `height_cm` needs no contract number of its own - it widens an existing TEXT column's legal values rather than reshaping one - and ships here because it was decided in the same loop; nothing in this contract reads it yet, and the band-crossing (BMI) milestone it will eventually feed stays undecided |
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

0.5.0 (August 2026); see the Schema migrations table above for exactly
which contract each release shipped. The engine, the skills and the boundary
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
