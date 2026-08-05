---
title: vitai
---

**The AI health coach you own.** Your health, on the record.

Most fitness apps own your data, hide their logic, and give everyone the same
advice. vitai inverts all three.

|  | what that means in practice |
|---|---|
| **You own the record** | Plain-text JSONL in a private git repo you control. Every vendor app can be replaced without losing a day of history. |
| **The numbers are auditable** | A deterministic engine you can read in an afternoon. Same input, same output, and no model anywhere near the arithmetic. |
| **The coaching is yours specifically** | An LLM carrying your full profile and a set of skills, reading the engine's output and never recomputing it. |

> [!tip] New here?
> Start with the [[how-to/get-started|getting-started guide]]. It ends with a
> real rollup built from your own first entries.

## The three layers

```
your content repo           the engine               the intelligence layer
(private, plain text)       (deterministic)          (LLM skills)

profile.md                                           coach
plan.md            ----->   vitai build     ----->   onboard
data/*.jsonl                -> health.db             ingest
vitai.toml                  -> weekly.md             redteam
                            -> verdicts
```

The split is the whole design. The engine never guesses and the model never
does arithmetic. Where they disagree, the engine wins.

## Find your way

| I want to | start here |
|---|---|
| Set it up and log my first entries | [[how-to/get-started\|Getting started]] |
| Know what every command does | [[reference/cli\|CLI reference]] |
| Know what gets recorded, field by field | [[reference/data-model\|Data model]] |
| Understand why it is built this way | [[explanation/architecture\|Architecture]] |
| Build a client, dashboard or connector | [[explanation/platform\|The platform contract]] |
| Know what it refuses to do, and why | [[explanation/medical-boundary\|The medical boundary]] |

Source: [github.com/Wombat164/vitai](https://github.com/Wombat164/vitai)

## What is new in 0.5.0

Contract 19 to 27. Everything is additive: old lines keep validating, and a
consumer that ignores every new column sees the behaviour it had before.

**The theme, if there is one: a record that holds a number and a record that
stands behind it are different records.** Most of this release is the second
kind arriving in pieces.

- **Say what a subjective number is out of.** A stored `rpe: 7` is "quite
  light" on one standard scale and "very hard" on another, and nothing in the
  record said which. Sessions, sets and daily rows can now declare the scale -
  and where none is declared, a reader must not invent one.
- **Best efforts, persisted.** The fastest 1k, 5k, 10k, half and full inside
  every stored track. The question a runner asks first, and one no field could
  answer, because a distance and a duration make two runs of different lengths
  comparable on neither.
- **A goal says which way progress runs.** A ceiling and a floor are not the
  same goal with the sign flipped. Holding 1100 kcal against a 1200 cap used
  to report 641 per cent and mint celebratory milestones for breaching it.
- **Whether a goal is still being pursued and whether it was reached are two
  questions.** One column used to answer both.
- **A build is a function of the record.** An unqualified build takes its
  viewpoint from the record's own last date rather than the wall clock, so the
  same record built on two different days gives the same database.
- **A refusal that means "not yet".** `pending` says the question is
  answerable and the data has not arrived, and carries the date it is due -
  earned from the source's own arrival history, never declared in config.
- **What the engine told you, and when.** A judgement nobody was shown had no
  consequence worth retracting.
- **What a computed value stands on.** A number can name the rows it was
  computed from, and how, in the athlete's own words. Declared, never
  re-executed.

> [!warning] Worth knowing if you already keep a record
> One supersede used to retire **every** row sharing its key, so a correction
> aimed at one of ten sessions retired all ten. That is silent data loss
> through the correction path, and it is fixed.

> [!note] Earlier increments
> Total provenance, the set as the atom of strength training, and the medical
> boundary drawn and enforced. See the
> [changelog](https://github.com/Wombat164/vitai/blob/main/CHANGELOG.md).

## The rule the whole design serves

> [!quote]
> **Sparse and continuous beats rich and abandoned.**
