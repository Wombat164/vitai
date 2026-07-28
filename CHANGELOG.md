# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

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
