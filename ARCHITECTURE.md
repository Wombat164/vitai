# Architecture

## 1. The split: public tool, private person

vitai is two repos by design:

| Repo | Visibility | Holds | Changes |
|---|---|---|---|
| **vitai** (this) | public | engine code, skills, templates, connector doctrine | when the tool improves |
| **your content repo** | private | `profile.md`, `plan.md`, `vitai.toml`, `data/*.jsonl`, `derived/` | weekly |

Nothing about a person ever lands in the public repo - not as defaults, not as
examples, not as test fixtures. Template and test values are synthetic.

The content repo is the durable asset. Every vendor app (calorie counter,
watch platform, training-plan app) can be replaced without losing history,
because history is plain text under git.

## 2. The three layers

### Content (markdown + JSONL, human- and LLM-authored)

- `profile.md` - physiology, medical history, constraints, motivations. Slow.
- `plan.md` - the working plan; section 0 is always "open actions". Often.
- `CLAUDE.md` - operating instructions for any LLM picking up the work:
  settled decisions, standing sensitivities, how the athlete works. This file
  is what makes the system portable across assistants and vendors.
- `vitai.toml` - the athlete's thresholds: rate-of-loss phases, easy-HR cap,
  resting-HR baseline, steps floor, pain gate.
- `data/*.jsonl` - append-only observations. **Never edit a line**; supersede.

### Engine (Python, deterministic)

```
data/*.jsonl --(supersedes resolution)--> records
records --> derived/health.db     (SQLite read model, rebuilt from zero)
records --> derived/weekly.md     (rollup: weight trend + rate verdict,
                                   training by week, tripwires, coverage)
```

Principles, in priority order:

1. **Deterministic and idempotent.** Same input, same output, every run.
   `derived/` is disposable; deleting it loses nothing.
2. **No LLM in the number path.** The LLM reads `derived/weekly.md`; it never
   computes a rolling average or a rate. When model and engine disagree, the
   engine wins. (This is the same never-hallucinate-engine pattern used for
   memory tooling elsewhere; it exists because LLM arithmetic drifts and
   determinism audits.)
3. **Append-only with supersedes.** A correction is a new line with
   `"supersedes":"<date>/<source>"`. `git log` plus the supersedes chain IS
   the audit trail.
4. **Derive, never store, anything computable.** Pace, rolling averages,
   weekly totals: computed on build, absent from data.
5. **Conservation - the golden rule.** The record describes ONE body: a
   calorie is eaten once and burned once, a step is taken once, a workout
   happened once - no matter how many apps witnessed it. Observations are
   therefore CLAIMS by sources; when sources overlap (a watch and a
   calorie app both describing the same day, two platforms logging the
   same run), the engine RESOLVES them to one canonical value per physical
   quantity - by precedence and fuzzy overlap-matching, never by summing.
   Session energy is an attribution WITHIN the day's total, not an
   addition to it. Conservation violations (sessions exceeding the day's
   burn, duplicate activities) are surfaced as tripwires, not silently
   "fixed".
6. **Anchors audit estimates; trends are the measurement.** Quantities
   fall in three epistemic classes: ANCHORS (body mass, body
   measurements, labs - the body's own ground truth), MEASURED FLOWS
   (device HR, steps, durations), and MODELED ESTIMATES (calorie burn
   models, food logging). When estimates and anchors disagree over time -
   the logged deficit says one rate, the scale trend says another - the
   anchor wins and the estimate is recalibrated (energy-balance
   back-calculation, MacroFactor-style). And weight anchors as a
   TENDENCY, never a point: single weigh-ins carry hydration, glycogen
   and food-transit noise, so the rolling trend is the measurement and no
   verdict ever consumes a single morning.

### The three data tiers

| Tier | Lives in | Written by | Rebuildable? | Feeds the number path? |
|---|---|---|---|---|
| **Observed** | `data/weight,daily,sessions.jsonl` | human / ingest | no - it IS the truth | yes |
| **Derived** | `derived/` (SQLite + rollup + verdicts) | the engine | always, from observed | is the number path |
| **Inferred** | `data/inferences.jsonl` | a model (`vitai infer`) | no - model calls are neither free nor deterministic | NEVER |

Inferred knowledge is a first-class dataset precisely because it is neither:
it carries provenance (model, evidence, confidence), is append-only like
everything else, is schema-validated before a byte lands, and is projected
into the read model for consumers - but no verdict, rate or tripwire ever
reads it. Corrections flow through `supersedes` like any other line.

### Semantics (curated knowledge - the layer between numbers and coaching)

A curve is not yet a meaning. Between the deterministic derivations and the
LLM sits a **semantics registry** (`semantics/`, versioned in-repo, neither
data nor code): the engine extracts a uniform SHAPE GRAMMAR for every metric
at every timescale (value, slope, acceleration, extrema with prominence,
plateaus, variance, band position, lagged cross-features), and the registry
maps each (metric x timescale x shape) to a MEANING, an evidence basis, and
a coaching stance. Meaning is metric-specific: a 90-day weight minimum is a
milestone, a one-day maximum is water; a rising 7-day RHR is fatigue, a
falling 90-day RHR is fitness. Verdicts and tripwires are the ACTIVATED
subset of this registry; the dashboard annotates charts from it; the coach
quotes it instead of improvising; and `vitai infer` extends it - confirmed
inferences graduate INTO the registry by human merge, the same
claims-into-truth pattern as the data layer. This keeps interpretation
auditable and versioned instead of trapped in model vibes.

### Intelligence (LLM + skills)

The layer the athlete actually talks to. Skills are Claude Code compatible
(`skills/<name>/SKILL.md`) but deliberately harness-agnostic in wording - any
agent runtime that can read files and run `vitai` commands can use them.

The skills' contract with the other layers:

- Read `profile.md`, `plan.md` (especially settled decisions), `CLAUDE.md`,
  and `derived/weekly.md`. Trust the engine's numbers.
- Write data ONLY as appended, schema-valid JSONL, and run `vitai validate`
  before presenting it as done.
- Update narrative files with explicit changelogs and struck-through
  corrections, never silent edits.
- Respect the content repo's standing sensitivities without re-litigating
  them (the founding deployment's examples: a max HR that is genuinely above
  the formula estimate, a chosen rate of loss inside evidence-based bounds,
  a gated injury, an eating pattern to be handled without moralising).

## 2b. The platform: build a game or dashboard on the engine

vitai is consumable as a library, and the read model is a versioned
contract. A third party (a game, a dashboard, a coach portal) builds on
three surfaces:

1. **`vitai.api.Vitai(root)`** - typed reads over one user's store:
   `datasets()`, `verdicts()`, `rollup()`, `build()`, `status_line()`.
2. **The read model** (`derived/health.db`) - one table per dataset plus
   `verdicts` (week, metric, value, target, verdict) and `meta`
   (`contract` version, bumped on any shape change). The `verdicts` table
   is the game-economy interface: deterministic weekly goal-attainment
   rows, exactly the signal a "your real goals are the premium currency"
   economy should mint from.
3. **`vitai verdicts`** - the same rows as JSONL on stdout, for non-Python
   consumers.

### Single-user or multi-user?

**The per-user store stays the atom. Multi-user is horizontal, not a
schema.** A game backend serving thousands of players holds one content
store per user (a directory; the record plus its derived SQLite) and
instantiates the engine per user:

```python
coach = Vitai(f"/data/users/{user_id}")
coach.build()
economy_input = coach.verdicts()
```

Why not one big multi-user database:

- **Scaling**: per-user stores are embarrassingly parallel - no shared
  write state, no contention, no migrations across tenants. SQLite-per-
  tenant at thousands of users is a proven, boring pattern; a host that
  outgrows local disk shards by user id, which is trivial when users never
  join.
- **Privacy blast radius**: thousands of users' health records in one
  database is a breach jackpot and a GDPR liability magnet. Per-user
  stores make deletion `rm -rf` and export `tar` - per user, provably.
- **The queries games actually need are per-user.** A leaderboard or
  economy aggregates VERDICTS (five small rows per user-week), not raw
  health records. That aggregation belongs in the HOST's own database,
  fed from `verdicts()` - vitai never grows cross-user joins.
- **The ownership story survives**: any player can take their directory
  and leave. That is the product's founding promise, and a multi-user
  schema would quietly break it.

A hosted deployment that wants central storage still can - sync the
per-user stores wherever you like - but the engine's contract stays
single-user, and that is deliberate.

## 3. Ingestion doctrine (the long-term direction)

The founding deployment proved that manual entry costs about three minutes a
week and cannot break. Integrations therefore earn their way in, in this order:

1. **LLM-mediated, on demand** (now): the athlete pastes a screenshot, an
   export file, an API response, or a URL; the `vitai-ingest` skill extracts
   schema-valid JSONL, shows its work, validates, and appends. This already
   covers any source an LLM can read - which is any source.
2. **API-first connectors** (when the record has survived months): thin
   fetchers for platforms with real APIs (calorie counters, watch platforms,
   training apps), still emitting the same JSONL through the same validation.
3. **Webcrawl fallback** for vendors without APIs, LLM-driven, same contract.

A connector is never allowed to write `derived/`, edit a line, or invent a
schema. Everything funnels through append + validate + build.

## 4. What is deliberately not built

- **No server, no daemon, no database service.** ~20 numbers a week do not
  need infrastructure. SQLite is a derived read model, not a store.
- **No app (yet).** If one ever exists it reads this schema; it does not
  invent another. The failure mode to avoid: four weekends on the tool
  instead of training.
- **No vendor lock.** Plain text, stdlib-only Python, MIT.

## 5. Repo layout

```
vitai/
├── src/vitai/            engine + CLI (stdlib only, Python >= 3.11)
│   ├── cli.py            init | build | validate | status
│   ├── config.py         vitai.toml loading + defaults
│   ├── jsonl.py          append-only loader with supersedes resolution
│   ├── schema.py         health-domain dataset schemas
│   ├── db.py             SQLite read model
│   ├── report.py         weekly rollup + tripwires
│   └── templates/        what `vitai init` stamps into a content repo
├── skills/               the intelligence layer (SKILL.md packages)
├── connectors/           doctrine + stubs (see connectors/README.md)
└── tests/                pytest, synthetic data only
```
