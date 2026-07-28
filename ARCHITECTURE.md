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
