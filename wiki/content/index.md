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

## What is new in 0.4.0

**The engine grew a surface a client application can build on.** Everything
before this assumed the consumer was a person at a terminal or an agent that
had read the source. A client is neither.

**The whole situation, in one call.** What would stop a decision, then what is
true now, then what the engine will not vouch for. It replaces fifteen calls a
consumer would otherwise stitch together, each one a chance to stitch it wrong.

**Writing back, with provenance the engine stamps.** A caller supplies what was
stated and nothing else, because a caller that could set provenance could file
a recollection as a device reading.

**An MCP adapter**, derived from the API rather than written beside it, so it
structurally cannot expose a capability the API lacks.

**Refusals say which kind of no.** A reason is required with a refusal and
forbidden without one, so a new refusal cannot ship unlabelled.

**Protocol, and the unanchored interval.** A measurement can name the
conditions it was taken under, and a bounded interval of honest but unanchored
claims resolves EMPTY rather than being backfilled. Discovering your own error
never costs you standing.

Earlier increments brought total provenance, the set as the atom of strength
training, and the medical boundary drawn and enforced. See the changelog.

> Sparse and continuous beats rich and abandoned.
