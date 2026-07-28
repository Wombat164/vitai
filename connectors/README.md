# Connectors

Deliberately thin, deliberately last. The founding deployment proved manual
entry costs about three minutes a week and cannot break; integrations earn
their way in only after a record has proven durable.

## The doctrine

1. **LLM-mediated first (available today, costs nothing to maintain).**
   The `vitai-ingest` skill already turns screenshots, export files, API
   responses and web pages into schema-valid JSONL. That covers any source
   an LLM can read - which is any source. This is the default connector.
2. **API-first when code earns its place.** Calorie counters, watch
   platforms and training apps mostly have real APIs (OAuth'd, rate-limited,
   occasionally gated behind partner programs). A code connector is a thin
   fetcher that emits the SAME JSONL through the SAME `vitai validate` gate -
   it holds no state, owns no schema, and writes nothing but appends.
3. **Webcrawl fallback, LLM-driven,** for vendors without APIs. Same
   contract. Respect the vendor's terms; the athlete is exporting their own
   data.

## Hard rules for any connector

- Emits appends to `data/*.jsonl` only; never touches `derived/`, never
  edits a line, never invents a key.
- Everything it writes passes `vitai validate` before commit.
- Secrets (API tokens) live in the athlete's secret store or environment,
  never in either repo.
- Prefer per-session/per-day summaries over raw telemetry: vitai stores
  observations, not sample streams.

## Status

No code connectors yet - by design. When the first one lands it will live
here as `connectors/<vendor>/` with its own README stating which API it
uses, what it fetches, and what it deliberately ignores.
