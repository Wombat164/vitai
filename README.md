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
the key name. Three datasets record what happened:

| File | One line per | Example keys |
|---|---|---|
| `data/weight.jsonl` | weigh-in | `kg`, `source` |
| `data/daily.jsonl` | day | `steps`, `kcal_in`, `kcal_out`, `sleep_h`, `rhr`, `hip_pain` |
| `data/sessions.jsonl` | training session | `type`, `distance_km`, `duration_s`, `avg_hr`, `rpe` |

...and three record what you were aiming at, dated:

| File | One line per | Example keys |
|---|---|---|
| `data/goals.jsonl` | goal declaration or edit | `slug`, `metric`, `target`, `policy`, `motivator` |
| `data/thresholds.jsonl` | threshold change | `key`, `value`, `change_kind`, `reason` |
| `data/achievements.jsonl` | recorded accomplishment | `title`, `goal`, `source` |

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

### Schema migrations

| Contract | Version | Change | What an existing repo must do |
|---|---|---|---|
| 1 | 0.2.0 | Founding tables + `verdicts`, `meta` | - |
| 2 | 0.3.0 | Adds `goals`, `thresholds`, `achievements` datasets; `contributions`, `milestones`, `plan_churn`, `goal_progress` derivations; a `goal` column on `verdicts`; `dataset`/`session_type` scope fields on goals | Nothing required - `vitai build` creates the new files and tables, and a repo with no goals simply has empty ones. To adopt: append goal lines, and move any threshold you have since changed out of `vitai.toml` into `thresholds.jsonl` |

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

Early scaffold (July 2026). The engine and skills work; connectors are
doctrine plus stubs. Built from a real, in-use personal deployment.

> [!NOTE]
> vitai is not a medical device and provides no medical advice. It is a
> record, an arithmetic engine, and coaching heuristics; decisions about
> injury, medication or symptoms belong with a clinician. See
> [SECURITY.md](SECURITY.md) for the full threat model and data-privacy
> notes.

## Documentation

- Docs site: <https://wombat164.github.io/vitai/> (built from `wiki/`)
- **Model spine: [docs/model.md](docs/model.md)** - eight core principles,
  five artifact kinds, the full gap map. Read this first.
- Design: [ARCHITECTURE.md](ARCHITECTURE.md) - the layers and what is
  deliberately not built
- The design conversation: [docs/the-loop.md](docs/the-loop.md) (185+
  question acceptance-test bank, gaps G1-G33),
  [docs/cross-metric-inference.md](docs/cross-metric-inference.md),
  [docs/plan-v3.md](docs/plan-v3.md) (the build plan)
- Research: [docs/prior-art.md](docs/prior-art.md) - the survey behind the
  design
- Brand: [assets/BRAND.md](assets/BRAND.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: tests land with
the change, no personal data ever (CI-gated), the engine stays
deterministic, and PRs scope themselves honestly. Security reports go
privately via [Security Advisories](https://github.com/Wombat164/vitai/security/advisories/new),
never public issues.

## License

MIT.
