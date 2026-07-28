# Security model

## The one thing to understand

vitai the tool holds no data. Your health record lives in a separate,
private content repo that you create and control. The safety of that data
is dominated by two choices the tool cannot make for you: keeping the
content repo private, and choosing what you let an LLM read.

## Threat model, plainly

- **The engine** (`vitai build|validate|status`) is offline: stdlib-only
  Python, no network calls, no telemetry, reads and writes only inside the
  content repo you point it at. Its outputs are deterministic and
  reviewable.
- **The skills** are instructions for an LLM agent (e.g. Claude Code)
  operating on your content repo. Anything that agent can read, its model
  provider processes. If that is not acceptable for some of your medical
  data, do not put that data where the agent works, or use a local model.
  The skills instruct the agent to append + validate rather than rewrite,
  but instructions are not a sandbox - your agent harness's permission
  system is the actual enforcement layer.
- **Ingestion** (`vitai-ingest`) handles screenshots, exports, API
  responses and web pages. Treat fetched web content as untrusted input:
  the skill's contract (schema-valid appends only, show your work, validate
  before done) exists partly so injected content cannot silently rewrite
  your record.

## What vitai does not guarantee

- It does not encrypt your content repo; use a private remote and disk
  encryption as you see fit.
- It does not anonymize anything; the record is designed to be personal.
- It cannot prevent an over-permissioned agent from doing over-permissioned
  things; configure your harness's write permissions to the content repo
  deliberately.

## Not a medical device

vitai is not a medical device and provides no medical advice. It is a
record, an arithmetic engine, and coaching heuristics. Decisions about
injury, medication, or symptoms belong with a clinician - the skills are
explicitly written to gate, not to diagnose.

## Reporting a vulnerability

Report privately via GitHub Security Advisories:
<https://github.com/Wombat164/vitai/security/advisories/new>

No public issues for security reports, please. Reports are handled
promptly and credited if you want credit.
