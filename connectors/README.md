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

## Cross-app adjustment semantics (document them or double-count)

Verified against a live wearable + calorie-app pairing: platforms do not
just export numbers, they ADJUST each other, and a connector that ignores
those semantics ingests fiction. The recurring mechanics to document per
vendor pair:

- **Projection vs actual**: device platforms report an extrapolated
  full-day burn intraday; it converges only at day end. Connectors ingest
  COMPLETED days (this is also why the reference Polar connector skips the
  current day).
- **Adjustment formula + clamps**: calorie apps compute
  `adjustment = device burn - own baseline assumption`, often with
  negative values clamped off. The adjusted intake target is DERIVED, not
  observed - the record stores measured intake and measured burn, never a
  vendor's adjustment arithmetic.
- **Exercise pass-through**: watch-recorded sessions typically flow into
  the calorie app as explicit exercise entries reconciled against the
  daily total. Ingesting both the session AND an exercise-inflated daily
  figure double-counts; take the device's daily total as the single
  kcal-out truth and sessions as their own records.

## Hard rules for any connector

- **Connectors write CLAIMS, never truth.** Tag every line with `source`
  and let the engine's resolution layer adjudicate overlaps
  (per-quantity precedence, fuzzy activity matching). A connector must
  never pre-merge sources, re-add another platform's exercise calories,
  or "helpfully" sum anything - a calorie is eaten once and burned once,
  and enforcing that is the ENGINE's job.
- Emits appends to `data/*.jsonl` only; never touches `derived/`, never
  edits a line, never invents a key.
- Everything it writes passes `vitai validate` before commit.
- Secrets (API tokens) live in the athlete's secret store or environment,
  never in either repo.
- Prefer per-session/per-day summaries over raw telemetry: vitai stores
  observations, not sample streams.
- **Vendor-derived insights** (VO2max, recovery/readiness scores, adaptive
  TDEE, training load, race predictors) are NOT observations - ingest them
  tagged `derived + source`, so the engine treats them as foreign-model
  estimates (second opinions to corroborate/challenge/backfill), never as
  raw truth and never as the anchor that audits estimates. See G23 in
  docs/cross-metric-inference.md.

## Status

No code connectors yet - by design. When the first one lands it will live
here as `connectors/<vendor>/` with its own README stating which API it
uses, what it fetches, and what it deliberately ignores.

**Verified candidates (2026-07-28), all legitimate personal-use paths:**

- **WHOOP**: developer API OAuth-scoped to the member's own data (recovery,
  strain, sleep, workouts, webhooks); no approval below 10 members;
  100 req/min, 10k req/day. Maps onto `daily` + `sessions`.
- **Polar AccessLink v3**: personal client, no approval gate; daily
  activity, sessions, sleep, nightly recharge. Gotchas a connector must
  handle: transactional endpoints discard data on commit (persist before
  committing), ~30-90 day history window (no deep backfill), resting HR
  needs deriving.
- **Strava v3 "Single Player Mode"**: personal app auths only its owner,
  zero review; 100 read req/15min; webhooks. Gotchas: `calories` requires
  the per-activity detail call; use `sport_type` (`type` deprecated); the
  2026 API agreement bans AI-training uses and long re-serving caches -
  personal single-athlete archiving sits in the personal-tracking
  carve-out, which a connector README must state rather than ignore.
- Apps without APIs reachable by proxy: several training-plan apps push
  completed workouts INTO Strava and expose planned workouts as ICS
  calendar feeds - prefer those official side-doors over scraping.

**Adjacent, planned**: a `vitai-schedule` skill - calendar-aware session
placement (free/busy conflict querying, real events with travel time,
participant invites, hard respect for calendars declared read-only in the
content repo's CLAUDE.md). Calendars are rails like Google Calendar API,
Microsoft Graph, CalDAV and ICS; the personal binding stays in the content
repo.
