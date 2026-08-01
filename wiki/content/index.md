---
title: vitai
---

**The AI health coach you own.** Your health, on the record.

vitai is three layers: a **private content repo** (your profile, plan and
append-only data - plain text, yours forever), a **deterministic engine**
(`vitai build` turns the record into auditable numbers: rate verdicts,
tripwires, rollups), and an **intelligence layer** of LLM skills that coach
against those numbers without ever recomputing them.

- Repo: [github.com/Wombat164/vitai](https://github.com/Wombat164/vitai)
- New here? Start with the [[how-to/get-started|getting-started guide]].
- What the CLI does: [[reference/cli|CLI reference]].
- What gets recorded: [[reference/data-model|data model]].
- Why it's built this way: [[explanation/architecture|architecture]].
- What it will not do, and why: [[explanation/medical-boundary|the medical boundary]].
- Building on it: [[explanation/platform|the platform contract]].

## What is new in 0.3.0

**Provenance became total.** A number can now say which instrument produced
it, how it was acquired, whether it was measured at all, and what the record
said about it at any past instant.

**Strength training became first-class.** The set is the atom, with an
exercise registry, modifier axes, and reads that refuse rather than guess.

**The boundary was drawn and enforced.** The engine states what the record
shows, declines to issue a plan, and routes nobody, with a deterministic lint
over the whole public surface so the line cannot erode quietly.

> Sparse and continuous beats rich and abandoned.
