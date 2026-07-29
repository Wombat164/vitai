# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

Increment 1 - goals are data, contribution, and temporal validity
(G6 + G14 + G18 + G19 + G20). Read-model contract bumped to **2**.

### Added
- **`goals.jsonl`** - goals are data, not prose in `plan.md`. A goal carries
  its `metric`, `target`, contribution `policy`, `period`/`on_period_end`,
  `deadline`, lifecycle `status`, and the fields that make it answerable
  rather than just measurable: `motivator` (the why the coach anchors on),
  `rationale` (why *this* number), `on_success`/`on_miss`, `accountability`.
  A goal that lives in another app is `metric: "external"` plus a `tracker` -
  vitai models and reinforces it but never invents a verdict for it (G19).
  `dataset`/`session_type` scope which events feed a goal, because
  `distance_km` means walking on a `daily` line and running on a `sessions`
  one.
- **`thresholds.jsonl`** - every threshold is effective-dated (G14), with a
  `change_kind` separating a real policy change from a correction of a
  mis-entered number. `kcal_target` and `protein_g_target` live here rather
  than in `vitai.toml`, because a target edited weekly must be dated.
- **`achievements.jsonl`** - hand-recorded accomplishments, with a `source`
  carrying authorship so they are never confused with derived milestones.
- **`contributions`** - the fan-out (G18). One event is judged against every
  goal in force that day, each with its own signed verdict:
  `advances | partial | unbudgeted | neutral | regresses`. A goal declares
  `monotonic` (more always counts) or `guarded` (volume beyond `guard_pct`
  above the recent baseline is unbudgeted ramp and does NOT advance the
  goal). One walk can advance a steps goal and a calorie goal at once; one
  big unplanned run can advance the calorie goal while the running goal
  declines to credit it.
- **`milestones`** - target fractions crossed by COUNTED progress only, so a
  30 km week off a 12 km base mints nothing. The engine will not congratulate
  an athlete for the behaviour most likely to injure them.
- **`plan_churn`** - policy edits as a first-class derived signal (G20): what
  moved, which way, and a `suspicious` flag when a loosening lands within a
  week of a week that metric was missed. It carries the athlete's own
  `reason`, so an explained deload reads differently from a silent retreat.
  Nothing is blocked - the athlete owns the record; the flag invites a
  question.
- **`state(date)`** - as-of reconstruction. `Vitai.state(d)` returns the
  goals and thresholds in force on a date, which is what every judgment now
  uses.
- **`vitai goals`** (and `Vitai.goals()`, `.contributions()`, `.milestones()`,
  `.churn()`, `.state()`) - active goals with counted progress, percentage,
  declared/last-edited dates, recent per-goal contributions, and any flagged
  edits. CLI and API land together (P9).

### Fixed
- **Editing a threshold no longer re-scores the past.** Weekly verdicts are
  computed against the thresholds in force on each week's Monday, so lowering
  a floor today cannot turn last March's misses into hits on the next
  rebuild. This was the audit-trail flaw G14 named; the regression test is
  `test_past_week_keeps_the_threshold_in_force_then`.
- **Same-day corrections on identity-keyed datasets.** A correction that
  shares its slug and date with the line it replaces used to supersede
  itself, dropping both lines. Supersedes resolution is now positional: a
  line can only be retired by a LATER one, and a retired line still passes
  its reference on so a chain resolves.
- **Same-day events with mixed null types no longer break the build.** The
  contribution ordering tiebreak compared record items directly, which raises
  when two events on one date hold different types under the same key.

### Changed
- `meta.contract` is **2**. Existing repos need no migration: `vitai build`
  creates the new files and tables, and a repo with no goals simply has empty
  ones. See the migration table in the README.
- The demo athlete now carries the goal story: a monotonic steps goal (raised
  once, mid-block), a guarded running goal, an external segment goal, a
  missed travel week, and a floor loosened three days later - which the churn
  flag catches.

## [0.2.3] - 2026-07-28

Foundations F3 - temporal foundations (G30).

### Fixed
- **Rolling windows are calendar-day, not entry-count.** A "7d avg" now
  averages values within the last 7 CALENDAR days, and the weight-rate line
  compares two calendar-separated windows - not the last N list entries.
  Under irregular logging the old behavior silently mis-scoped every "the
  trend, not a single point" number (a "7d avg" could span three weeks).
  Regression tests included.

### Added / doctrine
- The **day-boundary rule** is now written doctrine (event's local day at the
  moment it happened; effective-dated for relocations). The timezone/offset
  FIELD is deferred to increment 2, where `start_time` gives it a consumer -
  a date-only daily summary has no timezone ambiguity.

## [0.2.2] - 2026-07-28

Foundations F0 - in-repo demo athlete + CI demo job (see PR #4).

## [0.2.1] - 2026-07-28

Foundations F1+F2 from the restructured v3 plan - the robustness the feature
increments depend on, shipped before them.

### Fixed
- **Schema-evolution robustness (G25)** - the code-verified critical bug: an
  additive nullable field no longer invalidates lines written before it
  existed. Per-line schema generation (`_gen`, default 1); a key is required
  only if its introduction generation is <= the line's generation. Shape-
  history-stability regression test included.
- **Ingestion/build integrity (G26)** - one malformed line no longer aborts
  the whole build. `read_lines` returns (good rows, errors) and never raises
  on a bad line; `build` quarantines and reports, proceeding from the good
  rows; `validate` reports every malformed line, not just the first. `vitai
  init` writes a `.gitattributes` pinning LF on the append-only JSONL.

### Added
- `jsonl.load_report` (records + quarantined-parse errors); `schema`
  generation helpers (`key_generation`, `line_generation`).

## [0.2.0] - 2026-07-28

### Added
- **Platform surface**: `vitai.api.Vitai(root)` library class (typed reads,
  `verdicts()`, `rollup()`, `build()`); the read model is now a versioned
  contract (`meta.contract`) with a new `verdicts` table (week, metric,
  value, target, verdict) - the deterministic weekly goal-attainment rows a
  game economy or dashboard consumes. `vitai verdicts` emits them as JSONL.
- **Third data tier - inferred knowledge**: `data/inferences.jsonl`
  (kind/statement/confidence/model/evidence, schema-validated, append-only,
  supersedes-capable), projected into the read model, never read by the
  number path.
- **`vitai infer`** (opt-in via `[inference]` in vitai.toml): pluggable
  model backends - `claude-cli` (your authenticated Claude Code CLI) and
  `openai-compatible` (Ollama, llama.cpp, LiteLLM, hosted) - with strict
  parse-and-validate (invalid lines rejected, never repaired) and
  `--dry-run`.
- ARCHITECTURE: "The platform" section - single-user store as the atom,
  multi-user as horizontal per-user stores (scaling, GDPR blast radius,
  aggregate-verdicts-not-records rationale).

### Changed
- `vitai build` now also projects verdicts into the read model.

## [0.1.0] - 2026-07-28

### Added
- Deterministic engine: append-only JSONL with `supersedes` resolution,
  health-domain schemas (weight/daily/sessions) with a practical validator,
  SQLite read model rebuilt from zero, weekly rollup with rate verdict and
  configurable tripwires (`vitai.toml`).
- CLI: `vitai init | build | validate | status`.
- Skills (Claude Code compatible): `vitai-onboard`, `vitai-coach`,
  `vitai-ingest`, `vitai-redteam`.
- Content-repo templates stamped by `vitai init`.
- Connector doctrine (`connectors/README.md`): LLM-mediated first, API-first
  code connectors only once a record has proven durable.
- Brand v1 (`assets/`): v-pulse mark, wordmark/lockup (outlined Outfit),
  dark-mode + mono variants, social card, BRAND.md incl. verbal identity.
- Research dossier (`docs/prior-art.md`): 7-angle prior-art sweep with
  uniqueness verdict.
- Community + scrutiny scaffolding: CONTRIBUTING, SECURITY (threat model +
  not-a-medical-device), Contributor Covenant 3.0, issue forms, PR template,
  dependabot, SHA-pinned CI (hygiene gate incl. hash-based personal-content
  gate + Linux/Windows test matrix), gated PyPI Trusted Publishing release
  workflow, Quartz v4 docs site source.
