---
title: CLI reference
---

All commands run from (or take `--root` pointing at) a content repo.

## vitai init PATH

Stamps a content-repo skeleton: narrative templates, `vitai.toml`, empty
`data/*.jsonl`, `derived/`. Refuses a non-empty target (except `.git`).

## vitai build

`data/*.jsonl` -> `derived/health.db` (SQLite read model, rebuilt from
zero) + `derived/weekly.md` (rollup). Reads thresholds from `vitai.toml`;
an absent threshold disables its verdict rather than guessing a default.
Schema problems are warnings here - `validate` is the strict gate.

## vitai validate

Schema-checks every data line (including superseded ones): missing keys,
unknown keys, bad dates, wrong types, unknown session types, out-of-range
pain scores. Exit 1 on any problem. Fix by APPENDING corrections, never by
editing lines.

## vitai status

One line: latest weight, 7-day average and rate, firing-tripwire count.

## vitai verdicts

Weekly goal-attainment rows as JSONL on stdout - one object per
(week, metric) with `value`, `target` and a closed verdict vocabulary
(`on_target | ahead | behind | no_data`). The same rows live in the read
model's `verdicts` table. Each row also carries the `goal` it serves. This is
the contract a game economy or dashboard consumes; see
[[explanation/platform|the platform page]].

## vitai goals

Where each active goal stands: counted progress against target, percentage,
the dates it was declared and last moved, its motivator, and the recent
per-goal contributions behind the number.

    vitai goals                      # active goals, last 10 contributions
    vitai goals --recent 0           # progress only
    vitai goals --on 2030-05-01      # as the goals stood on that date
    vitai goals --json               # one JSON object per goal, for scripts

Progress is COUNTED progress. For a `guarded` goal that means volume beyond
its ramp guard is reported separately as unbudgeted rather than folded in -
the number reflects what was banked, not what was logged.

A closing section lists policy edits worth a question: a target or threshold
loosened within a week of a week that metric was missed, shown with whatever
reason the athlete recorded. It is a prompt for the coach, not a judgment -
nothing is blocked, and an explained deload is meant to read as one.

## vitai milestones

The milestone rungs a goal has for the period it is being scored in - passed
and not - with the next one marked. `milestones` in the read model lists what
was CROSSED; this adds the ones still ahead, so a client can say how many
there are and which comes next without slicing the target into quarters
itself.

    vitai milestones                 # every goal with a ladder
    vitai milestones --slug lean     # one goal
    vitai milestones --json          # one JSON object per rung, for scripts

A rung reads passed when counted progress REACHED ITS VALUE, which stays true
when a target moves; where a crossing exists it carries the date it was minted
on. Not every goal has a ladder: it needs a live floor goal with a target that
this engine scores. Caps, approaches, daily buckets, finished or abandoned
goals, and anything scored elsewhere have no rungs, and the command says so
rather than inventing quarters.

## vitai resolve

Where the record's numbers came from when more than one source claimed the
same thing.

    vitai resolve                    # every contested field, with the reason
    vitai resolve --date 2030-06-09  # just that day
    vitai resolve --json             # JSONL, for scripts

Three sections, in order: the contested fields (which source won, over what,
and why - marked `!` where the sources actually disagreed rather than merely
overlapped), the conservation tripwires, and anything retracted.

This is routine output, not an error report. "Why does the record say 2,443
when my app says 2,844" should always have an answer, and the answer is
per-quantity precedence: the watch measured the burn, the app modelled it,
and the record holds one of them rather than their sum.

## vitai check

Adjudicate a stated value against the record. **Exits 1 if REFUTED.**

    vitai check --date 2030-06-01 --metric distance_km --type run --says 9
    -> REFUTED: stated 9, record sum 8.01 (delta -0.99, -12.4%)

An LLM's narration is as untrustworthy a source as any vendor estimate, and
the engine already adjudicates sources rather than believing them. This
applies the same rule to the coach's own sentences - including the athlete's
recollection, which it lets a coach verify kindly ("the record has 8.0 - does
that match what you remember?") instead of either believing it or
contradicting it from nowhere.

Three verdicts, and the third matters: **NOT-IN-RECORD** is not REFUTED.
Absence cannot refute a claim. Tolerance comes from
`[preferences] check_tolerance` (2% by default).

## vitai day / window / ramp

Read-only dumps, so a number is never stated from memory.

    vitai day --date 2030-06-01     # everything for one date, merged claims included
    vitai window --days 14          # totals over N CALENDAR days, by session type
    vitai ramp --type run           # week-on-week volume + its base-size caveat

`ramp` always prints its caveat last: a ramp percentage over a one-week base
is not a trend, and the engine says so rather than leaving each caller to
remember. `day` deliberately shows claims that were merged away - the point of
a factual dump is that it reveals what the canonical row is hiding.

## vitai safety

Active escalations and gates. **Exits 2 while anything urgent stands**, so a
script, a cron job or a game backend can ask "is this athlete safe to train
today" without parsing prose.

    vitai safety                     # today
    vitai safety --on 2030-06-30     # as of a date
    vitai safety --all               # every escalation in the record
    vitai safety --json

Nothing in the output is generated. The escalation text is fixed in
`safety.py` and the same string appears wherever it surfaces - CLI, rollup,
read model. A coach may explain it and may not rewrite it.

Anything urgent dated today also prints at `vitai build` time, on stderr,
before any coaching output exists to bury it. That is the fast path: the
weekly cadence is right for coaching and wrong for danger.

## vitai project

If I do this, what then. A proposed quantity against a target you declared.

```
vitai project <dataset> <field=number> [...] [--root ROOT] [--on YYYY-MM-DD] [--json]
```

    vitai project daily kcal_in=500
    -> intake-cap: 2870 now, 3370 if you do - OVER the 2600 you declared by 770

**Nutrition only, and it states rather than advises.** The purpose sentence
says this engine logs nutrition and *builds training programmes* - two
different entitlements in one breath. So a projected intake gets the record and
nothing further: what it would do to a target you declared, and no verdict on
whether to. Projecting a session is refused rather than answered in the same
voice, because an app that answered both would have widened its own purpose
quietly.

**A hypothetical is not a claim.** Nothing here is written: no append, no
resolution, no rollup. Every row is marked `projection`, and a test compares
every byte of the record before and after.

**Arithmetic on your own numbers.** Nothing is imported and nothing looked up -
a projection built from a food table would be a figure about somebody else, so
a quantity this record has never seen is refused rather than estimated. It
projects against `daily`-period goals only: a weekly target has no answer to
"if I eat this now".

Same rows from `Vitai.project(dataset, values, on)` and the `project` MCP tool.

## vitai may

May this activity be done today. **Exits 2 unless the answer is `allowed`.**

```
vitai may <activity> [--root ROOT] [--on YYYY-MM-DD] [--json]
```

A gate says `restricts: impact`, and "am I allowed to run", "is walking
gated" and "can I bike instead" used to get the same paragraph. The mapping to
resolve that was never missing - `semantics/session_types.toml` declares that
a run falls under `impact` and a walk does not - but there was no way to ask.

**Three answers, and the third is the point.** `blocked` carries the gate's own
sentence and the classes that matched; `allowed` says no gate in force covers
it; `unknown` refuses, and a consumer must not read it as permitted. That is
why the exit code is non-zero for both of the last two: a shell reading exit 0
as permission would turn "nobody has said" into a green light for something
nobody assessed. `blocked` exits 2, `unknown` exits 3.

**`unknown` has two causes.** Nobody has classified the activity, or a gate in
force restricts particular MOVEMENTS rather than an activity - "no loaded hip
hinging" bars some strength work and permits the rest, so "may I do strength"
has no answer at this granularity and the per-exercise check is where that one
is answered. Both refuse, and the reason says which it is.

A client must not resolve `restricts` into activities itself. Deciding that
walking is low-impact is a claim about a body, which the medical boundary bars
a client from making and which this engine does not make either - it reads
what the registry declares.

Same answer from `Vitai.may(activity, on)` and the `may` MCP tool.

## vitai context

The situational mode in force on a date - what was going on around the
athlete, which is what lets the engine tell a missing weigh-in apart from a
skipped one.

    vitai context                    # today
    vitai context --on 2030-06-01    # as it stood then
    vitai context --json

## vitai infer (opt-in)

Runs the intelligence layer through a pluggable model backend (your Claude
CLI, or any OpenAI-compatible endpoint like Ollama), configured in the
`[inference]` section of `vitai.toml`. The model reads the rollup and
recent data and emits candidate knowledge; every line is schema-validated
and invalid lines are REJECTED (never repaired) before anything is appended
to `data/inferences.jsonl`. `--dry-run` prints without appending. Inferred
knowledge never feeds the deterministic number path.

## The client surface (#158)

Three commands are what a third-party agent reaches for, and they are the
reason this page exists at all. Anything the flagship app can do is reachable
here, on the same terms: a capability that works only inside the app is a
defect in the interface, not a convenience of the app.

```
vitai situation [--root ROOT] [--on YYYY-MM-DD] [--recent RECENT]
```

Everything a coach needs to know before it says anything: what is open, what
is gated, what was recently recorded. `--on` pins the viewpoint; the default
is the record's own horizon, not the wall clock, so a stale record answers as
of the last day it knows about rather than assuming nothing has changed.

```
vitai claim [--root ROOT] [--dataset DATASET] [--said SAID]
            [--read-by READ_BY] [--corrects DATE/SOURCE]
```

Append what someone said, with its provenance. `--corrects` supersedes an
earlier line rather than editing it. It appends claims and never touches the
deterministic number path.

`claim` is for something OBSERVED - it stamps `capture`, `read_by` and
`source`, the vocabulary of a value that was acquired. A plan was not
acquired, it was decided, so it has its own verb:

```
vitai plan [--root ROOT] [--set-by SET_BY] [--corrects SLUG@DATE]
           [--on YYYY-MM-DD] field=value [field=value ...]
```

Between them, `claim` and `plan` are the write paths an agent gets. Asking
`claim` for a plan refuses and names `plan` instead, rather than failing on
the three fields it would have stamped.

```
vitai mcp [--root ROOT]
```

Serve the same surface over MCP. First-class, not an adapter bolted on: the
CLI and the MCP server expose the same operations with the same vocabulary.

## vitai classify-pending

```
vitai classify-pending [--root ROOT] [--json] <dataset>
```

**What `vitai append` would make of these rows, before it makes it.** Reads
JSONL on stdin - the same rows `append` takes, through the same reader - and
answers one verdict per row: `new`, `restatement`, `correction`, `unmatched`
or `refused`. Nothing is written.

```
daily: 3 pending row(s) - 1 new, 1 restatement, 1 unmatched
row  verdict      target
  1  restatement  -
  2  new          -
  3  unmatched    2030-04-01/mfp-export

row 1: the record already holds a row keyed '2030-05-01/mfp-export' and this
one names no target, so it is a second claim rather than a correction ...
```

The question an importer could not ask. It spools an export and appends it,
and the thing it needs to know first is what the import will do to the day it
already sent. Comparing timestamps is the wrong way to ask: a pending row has
no `recorded_at`, may not author one, and will not have one until the append
assigns it (#425). So a correction is read off `supersedes`, which the author
wrote - an undeclared re-export comes back `restatement`, two live claims, and
the reason names the field that would make it a correction.

**The prose prints by default, beneath the table.** A `refused` row's reason is
the sentence `append_many` will raise with; a dry run quieter than the failure
it predicts would send you to the real write to find out why. The verdicts stay
a table and the sentences go under it, each keyed by the rows it is about -
one refusal covers every row naming the same reference, and the engine reports
it once.

**A refused batch exits 2**, the status `may` and `safety` use for "the answer
is no", so this is the shell sentence:

```
vitai classify-pending daily < day.jsonl && vitai append daily < day.jsonl
```

The append is all-or-nothing, so one refused row means none of them land, and
the summary says so. `--json` emits the same dicts `Vitai.classify_pending`
returns, and emits them before the non-zero exit: the status is for the shell,
the rows are for the consumer.

**There is no `--from FILE`.** `append` reads stdin and reads it nowhere else,
so a path on the dry run alone would be an input door the write does not have,
and a file classified through it could not be appended by the same means. `<
file` is the shell's answer.

## Reading the record

```
vitai dataset [--root ROOT] [--json] [--as-of INSTANT] <name>
```

One dataset's live rows, with `supersedes` already applied - `--json` for the
rows themselves, and the default for a summary of how many survived, over what
span, and which declared fields carry a value.

**This is how you read a dataset, and reading the JSONL yourself is
unsupported.** The correction rule has more edges than it looks: chains,
corrections that correct corrections, event datasets that never retire, and
the fact that a correction carries the same `<date>/<source>` as the row it
names. A consumer that re-derived it in nine obvious lines dropped every row
sharing a reference's key AND dropped each correction along with its target,
so its copy of the record got shorter every time somebody fixed a typo, and
one correction at a time it looked like nothing (#258).

`--as-of` is a KNOWLEDGE CUTOFF: what the record knew at that instant,
ignoring everything appended since. Not `--on`, which the sibling read commands
use for a different axis - `on` is the valid-time viewpoint, as of what *day*
something is judged, and this command judges nothing. Conflating the two is
easy and the familiar spelling is the wrong one here. A bare date means UTC
midnight; a naive instant is refused, because guessing a timezone makes the
same command answer differently on two machines.

One thing it does not yet do (#148): a threshold with no dated row still falls
back to today's `vitai.toml`, so a reconstruction is not yet policy-complete.

Same rows from `Vitai.dataset(name)` in the API and from the `dataset` MCP
tool. Rows are raw claims; `vitai resolve` is where two sources disagreeing
gets adjudicated.

An unparseable line is quarantined rather than raised, so a read proceeds from
the good rows. `--json` reports that on stderr, leaving the JSONL on stdout
parseable; the MCP tool returns rows only, so an agent that needs to know asks
`validate`.

```
vitai derived [--root ROOT] [--json] <table>
```

One DERIVED table's rows, by the name the contract gives it - `best_efforts`,
`session_weeks`, `verdicts`, `goal_progress` and the rest. These are build
output, rebuilt from the record every time and never a place to write.

Keyed by table name because that is the name a consumer has: the contract
history names tables, and several of these were reachable only under a command
whose name differs. `best_efforts` had no public path at all, which left a
private attribute, a direct query against a table the contract exists to
insulate you from, or re-parsing the tracks - at which point the number is
yours rather than the engine's.

**These are not aliases for the named commands.** `vitai goals` computes from
the raw claims; the `goal_progress` table computes from the resolved canonical
rows. Where one session reached the record twice, the two report different
progress against the same goal, because the raw read counts the duplicate. The
same holds for the contributions behind `vitai goals`, and for churn as soon
as a contested goal or threshold row exists. Pick one and stay on it.

**Read `basis` before quoting a `best_efforts` time.** `device` means the
window was measured against the watch's own cumulative distance, an
observation; `derived` means against the haversine sum the engine computes,
which is not. On a real 11 km track the two differ by twenty seconds over ten
kilometres.

Same rows from `Vitai.derived(name)` and from the `derived` MCP tool.

```
vitai events [--root ROOT] [--json] [--on YYYY-MM-DD]
vitai meals  [--root ROOT] [--on YYYY-MM-DD] [--json]
vitai sets   [--root ROOT] [--machine MACHINE] [--on YYYY-MM-DD] [--json]
             [{list,progression}]
vitai journal [--root ROOT] [--kind KIND] [--status STATUS] [--about ABOUT]
```

Dated fixtures, itemised meals, strength sets, and what the athlete said.
`sets progression` reads load and reps over time for one movement; `--machine`
scopes it, because a stack number is a pin position and 66 on two machines is
two different loads.

## Tracks

```
vitai route [--root ROOT] [--session REF] [--against GPX] [--barometric]
            [--json] [gpx]
```

Deterministic geometry for one GPS or TCX track: length, elevation gain,
stops, shape, and the best efforts inside it. `--against` compares two tracks
for route similarity. `--barometric` trusts the file's own elevation instead
of smoothing GPS vertical noise. Never compute route geometry outside this
command: an improvised script is not reproducible and its numbers are not
evidence.

## Evidence, keys and conformance

```
vitai artifact [--root ROOT] [--out PATH] [--date YYYY-MM-DD]
               {ls,get,verify} [sha256:<64 hex>]
vitai key     [--root ROOT] {new,check} [phrase ...]
vitai conform [--root ROOT] [--transport IMPL] [--custody IMPL] [--at PATH]
vitai schema  [--json]
vitai append  [--root ROOT] dataset
```

`artifact verify` re-hashes stored evidence and reports what no longer
matches. `key check` verifies a written-down phrase before you rely on it.
`conform` runs an implementation of a transport or custody interface against
the engine's own suite, which is how a third-party implementation proves
itself rather than asserting. `schema` prints the dataset shapes, `--json` for
machine use. `append` takes JSONL on stdin and validates before writing;
invalid lines are rejected, never repaired.

## The rollup (`derived/weekly.md`)

- **Weight**: last 14 points with 7-day rolling average, plus a rate line -
  `ON TARGET` / `FAST - raise intake` / `SLOW - check logging` against the
  phase target from `vitai.toml`.
- **Training by week**: km, run/gym counts, average easy-run HR with an
  easy-cap flag.
- **Tripwires**: resting-HR drift, pain gate, sleep floor, steps floor.
- **Coverage**: how sparse the record is (sparse is fine; abandoned is not).
