---
title: Architecture
---

Condensed from the repo's
[ARCHITECTURE.md](https://github.com/Wombat164/vitai/blob/main/ARCHITECTURE.md).

## Two repos: public tool, private person

The tool (this repo) holds engine code, skills and templates. Your content
repo holds the person: narrative, thresholds, data. Nothing personal ever
lands in the tool - enforced in CI by a hash-based personal-content gate.

## Three layers

1. **Content** - markdown narrative + append-only JSONL observations.
2. **Engine** - deterministic Python (stdlib only): supersedes resolution,
   SQLite read model, weekly rollup, tripwires. No LLM in the number path;
   when model and engine disagree, the engine wins.
3. **Intelligence** - LLM skills (`vitai-onboard`, `vitai-coach`,
   `vitai-ingest`, `vitai-redteam`) that read the engine's outputs and the
   narrative, and write only schema-valid appends plus explicit,
   changelogged narrative edits.

## Why plain text

Every incumbent either locks the record (proprietary formats, gated APIs,
PDF-only exports) or has no coaching intelligence. Plain text under git is
the only format that survives every vendor change, diffs meaningfully,
and lets an LLM read your whole story. See the
[prior-art dossier](https://github.com/Wombat164/vitai/blob/main/docs/prior-art.md)
for the survey behind this claim.

## Deliberately not built

No server, no daemon, no app (yet - and any future app reads this schema),
no vendor lock, no code connectors until a manual record has proven
durable. Ingestion is LLM-mediated through `vitai-ingest` with
validate-before-done.
