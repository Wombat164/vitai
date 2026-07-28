# vitai

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/vitai-lockup-dark.svg">
  <img src="assets/vitai-lockup.svg" alt="vitai" width="320">
</picture>

**The AI health coach you own.** Your health, on the record.

Most fitness apps own your data, hide their logic, and give everyone the same
advice. vitai inverts all three: your record is plain text in a **private git
repo you control**, the numbers come from a **deterministic engine** you can
read in an afternoon, and the coaching comes from an **LLM loaded with skills
and your full profile** - not a one-size-fits-all algorithm. Progress you can
prove, in a record no vendor can take away.

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

Three health-domain datasets, one JSON object per line, keys never omitted
(`null` for unknown), units in the key name:

| File | One line per | Example keys |
|---|---|---|
| `data/weight.jsonl` | weigh-in | `kg`, `source` |
| `data/daily.jsonl` | day | `steps`, `kcal_in`, `kcal_out`, `sleep_h`, `rhr`, `hip_pain` |
| `data/sessions.jsonl` | training session | `type`, `distance_km`, `duration_s`, `avg_hr`, `rpe` |

Corrections are appended with `"supersedes":"<date>/<source>"` - a wrong line
is never edited. The audit chain is the point: how a number changed is often
more informative than the number.

Targets and tripwires (rate-of-loss phases, easy-run HR cap, resting-HR
baseline, steps floor, pain gate) live in the content repo's `vitai.toml`, not
in code - the engine is the same for everyone, the thresholds are yours.

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

## License

MIT.
