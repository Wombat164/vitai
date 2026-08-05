---
title: Get started
---

By the end of this page you will have a private record of your own, one real
entry in it, and a rollup built from that entry. It takes about ten minutes.

> [!info] What you are setting up
> Two things, kept apart on purpose. **This repo** is the engine: public code,
> no data. **Your content repo** is your record: private, plain text, yours.
> The engine never holds your data and your record never holds code.

## 1. Install the engine

```bash
git clone https://github.com/Wombat164/vitai
cd vitai
pip install -e .
```

There is nothing else to install. The engine is pure Python 3.11 or newer with
**zero third-party dependencies**, which is enforced in CI rather than merely
intended.

## 2. Stamp your content repo

```bash
vitai init ~/health
cd ~/health
git init && git remote add origin <YOUR PRIVATE REMOTE>
```

> [!warning] Two things to get right now rather than later
> **Keep the content repo private.** It will hold your real record.
>
> **If you sync through a cloud-drive folder, keep the git repo outside the
> synced path.** A live `.git` directory corrupts under drive sync. A private
> git remote is the sync you want.

## 3. Fill in who you are

`vitai init` leaves four files for you:

| File | What it holds |
|---|---|
| `profile.md` | physiology, history, constraints, medical gates |
| `plan.md` | the working plan. Section 0 is always the open actions |
| `vitai.toml` | your thresholds: rate-of-loss phases, easy-HR cap, resting-HR baseline, steps floor, pain gate |
| `CLAUDE.md` | operating instructions for the AI that picks this up: settled decisions, sensitivities |

> [!tip] You do not have to write these by hand
> The `vitai-onboard` skill fills all four through an interview plus whatever
> data you already have exported from other apps.

The thresholds live in **your** file, not in the engine. The engine is the same
for everyone; the numbers it judges you against are yours.

## 4. Record your first entry

Use `vitai claim`. It takes what you said and the quantities you are stating,
and writes the line:

```bash
vitai claim --dataset weight  --said "75.9 on the scale this morning" kg=75.9
vitai claim --dataset daily   --said "quiet day, slept ok" steps=5855 sleep_h=7.0
vitai claim --dataset sessions --said "easy 10k" type=run distance_km=9.74 duration_s=3660 rpe=6
```

> [!warning] Do not hand-write JSON into `data/*.jsonl`
> It looks like it should work and it will fail `vitai validate`. **A line must
> carry every key its dataset declares**, with `null` for anything unknown -
> a key that is simply absent is an error rather than a blank. A weight line
> has 22 fields; you do not want to type them.
>
> `claim` fills them, and it stamps the provenance itself: `capture:
> narrative`, `source: stated-in-chat`, and the clock. That is deliberate - a
> caller that could set its own provenance could file a recollection as a
> device reading.

Your words are kept verbatim in the line alongside the number, which is why
`--said` is worth filling in properly rather than leaving off.

See the [[reference/data-model|data model]] for every field each dataset
accepts, and [[reference/cli|the CLI reference]] for the rest of `claim`.

## 5. Build, and read what it says

```bash
vitai validate     # schema-check every line first
vitai build        # data/*.jsonl -> derived/health.db + derived/weekly.md
vitai status       # the one-line version
```

`vitai status` gives you the state in a sentence. On day one, with one
weigh-in, that sentence is short:

```
75.9 kg (2026-08-05) - tripwires: none
```

Nothing is wrong. A rate needs more than one morning to exist, so the engine
does not print one. As the record fills, the same command says more:

```
75.9 kg (2030-06-29) - 7d avg 76.2, losing 0.34 kg/week - tripwires: 4
```

**The engine states what it can see and declines the rest.** You will meet
that everywhere: it would rather answer thinly than confidently.

`derived/weekly.md` is the fuller read. **Judge on the rate line, never on a
single morning** - one weigh-in carries hydration, glycogen and food-transit
noise, so the rolling trend is the measurement.

Everything under `derived/` is disposable. Delete it and `vitai build` rebuilds
it from zero, which is the point: the record is the truth and everything else
is a projection of it.

## 6. Commit, and repeat weekly

```bash
git add -A && git commit -m "week of $(date +%Y-%m-%d)" && git push
```

The weekly loop is designed to take about three minutes: append a handful of
lines, validate, build, commit.

> [!quote]
> **Sparse and continuous beats rich and abandoned.**
>
> A thin record you keep for two years is worth more than a rich one you
> abandon in March. Every design decision here serves that.

## When you get something wrong

**Never edit a line, and never delete one.** Append a correction naming what it
replaces, with `--corrects <date>/<source>`:

```bash
vitai claim --dataset weight --said "misread it, 76.9" kg=76.9 \
            --corrects 2026-08-05/stated-in-chat
```

The file now holds two lines and the record holds one live row, carrying 76.9.
The original stays in the file and in git history; the engine reads the
correction and stops counting the row it replaced.

That rule is what makes the record auditable: you can always see what you
believed at the time and what you later learned, and nothing can quietly
rewrite the past. It also means a mistake costs you nothing but a line.

> [!note] Reading the record back
> Use `vitai dataset <name>` rather than parsing the JSONL yourself. Applying
> the correction rule by hand has more edges than it looks and getting it
> wrong loses rows quietly. See the [[reference/cli|CLI reference]].

## Where to go next

| You want to | Read |
|---|---|
| Know every command | [[reference/cli\|CLI reference]] |
| Know every field | [[reference/data-model\|Data model]] |
| Understand the design | [[explanation/architecture\|Architecture]] |
| Build a client or connector | [[explanation/platform\|The platform contract]] |
| Know what it refuses to do | [[explanation/medical-boundary\|The medical boundary]] |
