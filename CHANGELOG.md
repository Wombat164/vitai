# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

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
