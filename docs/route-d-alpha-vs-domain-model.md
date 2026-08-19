# Route D: the contract treadmill, measured, and the backlog partitioned

Route D was named in loadline's `docs/roadmap.md` on 2026-08-17, deferred with
route B, and carried for three days. It is two things: a claim to test, and a
partition to produce. This document does both, and it produces no code.

Everything below is measured against commits and diffs in `vitai`,
`loadline` and `vitai-lens` as of **2026-08-19**:

| repo | head | contract |
|---|---|---|
| vitai | `9fb0564` | 54 |
| loadline | `2bbfb0c` | pinned at 52 |
| vitai-lens | `2d1e7c1` | 54 |

Nothing here is taken from the roadmap's prose. Where the roadmap and the
commits disagree, the commits win and the disagreement is stated.

---

## Part 1: the cheapest test, run

The roadmap named the test itself, so it is run as written:

> The cheapest test that would confirm or kill this: for the last four
> contract bumps, count how many changed anything an athlete can see in this
> client. Near zero means contracts should batch to a stated cadence instead
> of being chased.

### What "the last four" turns out to mean

The phrase has two readings, because the client is two contracts behind the
engine. Both are reported, because the gap is itself part of the answer.

Every bump is a clean `+1` on `CONTRACT_VERSION` in `src/vitai/db.py`, so the
bumps are unambiguous:

| contract | vitai commit | date | absorbed by loadline |
|---|---|---|---|
| 51 | `8b50d34` | 2026-08-16 | `ed755b1`, 2026-08-17 |
| 52 | `8466d1d` | 2026-08-17 | `b3af716`, 2026-08-17 |
| 53 | `2254a17` | 2026-08-17 | **not absorbed** |
| 54 | `e6aa734` | 2026-08-18 | **not absorbed** |

So the last four ENGINE bumps are 51 to 54, and the last four bumps the client
has actually ABSORBED are 49 to 52. The table below covers both, and adds 47
and 48 so the series is long enough to argue with.

### The count

Each row is judged by reading the absorbing commit's diff and asking one
question: after this commit, is there any state of the record in which the app
renders something it did not render before?

| contract | absorbing commit | client diff | athlete-visible? |
|---|---|---|---|
| 47 | `4b9592d` | `crossings.js` +92, `app.js` +70, new `renderCrossing` | **YES** |
| 48 | `20f8e61` | `crossings.js` +48, `app.js` +18 | **YES** |
| 49 | `8b0b56f` | 3 files, 1 line each | no |
| 50 | `a140583` | 3 files, 1 line each | no |
| 51 | `ed755b1` | `gapfill.js` +51, `gapcard.js` +11, `consent.js` +21 | **code yes, screen no** (below) |
| 52 | `b3af716` | 1 line in the artifact, 1 in `app.js` | no |
| 53 | not absorbed | - | no |
| 54 | not absorbed | - | no |

**Answer to the test as posed: zero of the last four engine bumps (51 to 54)
have changed anything an athlete can see. On the last four ABSORBED bumps (49
to 52), the count is zero or one depending on how strictly you read
"can see" - and the honest reading is zero.**

The claim is confirmed, not killed.

### The three that are trivially zero

`8b0b56f` (49) and `a140583` (50) are the same commit twice: the CI checkout
ref, the `CONTRACT` constant in `app.js`, and the `emitted.contract` stamp in
`read-model.json`. Three files, one line each, no behaviour anywhere.

`b3af716` (52) is zero by the author's own finding, written into `app.js` at
the time:

> 52 ASKED NOTHING OF THIS CLIENT, and that is a finding rather than a shrug.
> [...] This artifact carries no `comparability` dataset at all [...] so there
> is no column here to widen and no sentence here to correct.

That comment is the treadmill describing itself. The absorption still cost a
commit, a re-emit, a CI pin move and a README badge.

### The one that looks like a counter-example, and is not

Contract 51 is the interesting row and the reason this test is worth running
rather than assuming.

`ed755b1` is real work. `gapfill.js` gains `recordedAbsence()`, `gapOffer()`
learns that a recorded reason outranks an inferred one, and `gapcard.js` gains
a sentence the athlete would read:

    the record already answers this: <reason> (<fields>), recorded <date>

The surface is wired: `chart.js:22` imports `gapCard` and calls it twice. This
is not one of the four inert modules the 2026-08-18 birdseye found.

**It fires on nothing.** Measured on the artifact this client ships
(`src/artifact/read-model.json` at `origin/main`):

- 165 rows across `daily`, `sessions` and `weight` carry the `absent_reason`
  key.
- **0 of them are non-null.**

`recordedAbsence()` returns `null` for every row of the demo, so
`settled.by === "row"` is unreachable and the new sentence never renders. The
same was true at the absorbing commit itself and at the next one: 165 carrying,
0 non-null, at `ed755b1` and at `b3af716` alike.

The regression test passes because it builds its own artifact by hand.
`tests/absence-rows.test.mjs` declares a literal three-row `weight` series
containing `absent_reason: "asked-and-declined"` and asserts against that. It
is a correct unit test. It is not evidence that anything reaches a screen.

Nor can the operator's own record supply the value. Searching both repos:
`absent_reason` appears in loadline only in `emit_artifact.py` (which passes it
through) and in the committed artifact. No importer, no capture path and no
composer writes it. In vitai it is validated and read, never generated. The
field is author-supplied. Today a non-null `absent_reason` can only arrive by
hand-editing a JSONL line.

So contract 51's absorption added correct, wired, tested client code on a path
no athlete can currently reach. Counting it as "changed something an athlete
can see" would be counting the fixture, which is the exact failure the
2026-08-18 birdseye named:

> the fixture that makes a test pass is also the thing most likely to be
> hiding the defect

### What the older pair proves, and why it strengthens the case

Contracts 47 and 48 were not treadmill. `4b9592d` put a crossing sentence on
the home screen - "the most recent thing that is true of the athlete" - firing
on any record with two weight readings. `20f8e61` taught the same surface the
`band` kind and made an unknown kind render as a visible gap instead of
silently vanishing from the list.

So the series is: **two substantive absorptions, then four that were not.** The
treadmill is a recent property that sharpened over six days, not a permanent
condition. That makes the batching recommendation stronger rather than weaker:
there is a demonstrated difference between a contract that asks something of a
client and one that does not, the clients cannot tell which is which until they
absorb it, and four of the last six turned out to be the second kind.

### The roadmap's own arithmetic, checked

The roadmap claims "17 of the 74 downstream commits in that window (23%) exist
only to follow the engine's contract number", over 2026-08-11 to 2026-08-17.

- **74 downstream commits reproduces exactly**: 58 in loadline plus 16 in
  vitai-lens on `origin/main` in that window.
- **17 does not reproduce exactly, and the spread is the useful part.** Under
  the strictest rule - the entire diff touches nothing but the pin ref, the
  `CONTRACT` constant, the `emitted.contract` stamp and the README badge -
  the count is **4 in loadline** (`f96cf26`, `8b0b56f`, `a140583`, `d290ac3`),
  5.4% of that repo's commits. Under a looser rule - the commit exists because
  of the cadence, including absorptions that did real reconciling work - it is
  **19 across the two clients**, 26%.

The roadmap's 17 sits inside that range and its 74 is exact, so its arithmetic
is sound. The two numbers to quote from here on are **4 commits that changed
nothing but a number** and **19 commits that existed because of the cadence**.

### The evidence nobody planned: one client already batched

`vitai-lens` went from contract 50 straight to 53 (`a554fe6`, 2026-08-17),
skipping 51 and 52 entirely. Nothing broke. The commit that landed 53 is
substantive (`index.html` +57, a new `tools/test_absence.js`), because 53 was
one of the bumps that actually asked something. Its next move, `2d1e7c1` to
contract 54, is titled "Follow the engine to 54, and **say why nothing else
moved**".

So batching has already been run as an experiment, by accident, in the repo
that tracks head most aggressively. It cost nothing and it removed two
no-op absorptions. Meanwhile loadline, the repo that carries the product
position, has spent four of its last six absorptions moving a number.

### What follows, stated so it can be argued with

1. **Contracts should batch to a stated cadence.** The number to state is a
   cadence, not a lag tolerance: absorb on a fixed day, or absorb when the
   engine's changelog names a field this client reads, whichever comes first.
2. **The engine should say, per contract, whether a client is asked anything.**
   `b3af716`'s comment is that statement written downstream, after the cost was
   paid. Written upstream in the changelog fragment it costs one line and saves
   three client absorptions per no-op bump.
3. **A published field with no reader is the client-side twin of this problem**
   and is already filed as loadline#67. #386 is the engine-side twin. Both
   belong to the same measurement: what is published, and what is read.

---

## Part 2: ALPHA and DOMAIN MODEL

### The rule

**ALPHA**: on the path to the capture nobody else can do, as
`loadline/docs/objectives.md` states that position. Concretely, an issue is
ALPHA if at least one of these fires, and the rule that fired is recorded per
issue:

- **A1 - named consumer.** An open loadline issue, or the live work order's
  client-facing tracks, names it.
- **A2 - wrong answer.** It describes an answer a client renders wrongly
  today, not a capability that is absent.
- **A3 - published surface.** It is part of what a client reads: field types,
  aliases, symbols, the emitted datasets, the consumer-facing reference, or a
  gate protecting one of those.
- **A4 - differentiator.** It is capture of what has no form anywhere else,
  and a client surface for it is live work.

**DOMAIN MODEL**: everything else. Good work, none of it wrong, none of it
currently reachable by an athlete. The default is DOMAIN MODEL: absent a named
consumer, an issue is not on the alpha path. That default is what makes the
partition falsifiable rather than a matter of taste.

`#25` (the work order) is deliberately left unlabelled. It is the instrument,
not the subject.

### The measurement that decides most of it

Of **78 open vitai issues**, the number named by any open loadline issue is
**two**: #372 (by loadline#65) and #402 (by loadline#79). Three more name a
client from the engine side: #399 and #400 (both raised by vitai-lens) and
#404 (which names loadline#64 and loadline#79).

Five issues out of 78 have a client on either end of them. That is the drift
claim measured rather than asserted.

### ALPHA: 11 issues

| issue | rule | why |
|---|---|---|
| #372 | A1 | The forward band for weight. loadline#65 names it directly. |
| #402 | A1 | Error bands must be earned. loadline#79 names it three times. |
| #404 | A1 | A protocol is the reading's uncertainty budget; the issue itself names loadline#64 (the capture side) and loadline#79. |
| #381 | A1 | `weight_rate` is silent exactly when it changes. Work order track 1 item 4 calls #381 and #372 "the pair behind loadline's trend rendering". |
| #400 | A2 | The published alias `pulse` resolves to a field the record will not vouch for. Two clients, one question, two different metrics. This is a wrong answer, today, in a shipped surface. |
| #393 | A2 | Four MyFitnessPal activity strings declared in neither spelling. Same family as #390, which blocked a live record moving off contract 40. Undeclared strings revert relayed sessions to `other` on re-import. |
| #399 | A3 | Publish a display symbol, or say why a client must keep its own. Found by vitai-lens trying to delete its local unit table and failing. |
| #386 | A3 | 26 fields including all of `device` are exempted from coverage rather than decided. Its client-side consequences are already filed: loadline#85 ("the artifact gives two answers about `device`") and loadline#67 (no module says which artifact fields it reads). |
| #419 | A3 | The consumer-facing data-model reference is five datasets behind and no test can see it. This is the document a client integrator reads first. |
| #61 | A4 | Photo capture as a first-class input, which is the differentiator in its purest form: a gym console is an instrument the record otherwise never has. Live client work in loadline#63, #87 and #90, the last of which is Program B item 2. |
| #378 | A4 | Where an artifact's bytes may travel. loadline#90 keeps a photograph's bytes by hash and the 2026-08-18 birdseye records that the unprotected-bucket question "has no answer". This is the engine half of that. |

### DOMAIN MODEL: 66 issues

Grouped by what they are, not by number, because the groups are the argument.

**The design-essay cluster** (already parked by the work order, and the
partition agrees): #220 state model, #231 journeys, #232 eliciting a journey,
#233 motivation, #215 object registry, #195 norms, #197 preferences, #118 route
retrospective, #119 episode layer, #120 relating episodes, #84 places, #23
route analysis.

**The positioning cluster** (also already parked): #251 conformance mark, #261
IEEE 1752.1, #109 accounts, #106 hosted sync, #31 and #30 hosted vitai and the
Strava MCP direction, #129 persona corpus migration.

**Taxonomy and the model of a life**: #194 goals conflate objectives with
means, #198 habits, #213 habits binding cue and protocol, #226 prescribed
versus performed, #227 costable prescriptions, #225 circuit existence, #230
swimming vocabulary, #237 appraisals, #236 behaviour-change prior art, #144
performance goals, #192 feasibility, #193 projecting a proposed act, #28 state
changes require the athlete.

**Provenance and measurement theory**: #167 testimony versus measurement, #168
qualifications, #169 platform versus channel, #171 instrument capability, #173
construct validity, #174 sustained honest error, #148 thresholds outside the
record, #156 logical identity, #262 where a modelled number lives, #263
architecture schema, #358 two measurands on one instrument, #361 which build
wrote an ordinary row, #420 which build wrote a derived row, #417 which dataset
a comparability field lives on.

**Datasets and capture breadth**: #56 athlete-defined activities, #62 vendor
drift, #83 what was ridden, #85 the athlete's own baselines, #87 unlogged
movement, #93 the coverage ledger, #95 `vitai locate`, #101 FIT sets, #123 test
reports, #138 medication effects, #141 energy balance, #203 anchoring the day to
sleep, #214 sleep diary, #218 the loads dataset, #224 the asking channel, #230
is above, #260 connector contract, #436 single-valued vocabulary fields.

**Superseded or overtaken**: #102 front-end architecture (loadline exists and
answered it), #130 bitemporal evaluation, #155 archive stewardship.

### The roadmap's five examples, checked rather than inherited

The roadmap named five issues as the domain-model drift. All five hold, but two
of them hold for a reason worth writing down.

| issue | roadmap says | verdict |
|---|---|---|
| #231 journeys | domain model | **Confirmed.** Already parked by the work order. No client asks for it. |
| #198 habits | domain model | **Confirmed.** Pure taxonomy: a cued behaviour with a formation state. No consumer. |
| #226 prescribed versus performed | domain model | **Confirmed.** A prescription is a template with no client that renders one. |
| #173 construct validity | domain model | **Confirmed, with a carve-out.** The general issue is domain model. Its concrete instance is #400, which is ALPHA: `pulse` resolving to a field the record will not vouch for is construct validity biting a live client. The pattern is worth generalising - the alpha slice of a domain-model issue is usually already filed separately, and that is the slice to take. |
| #261 IEEE 1752.1 | domain model | **Confirmed.** Already parked in the positioning cluster. |

### The eleven close calls, and which way to push them

The partition is only useful if the contested cases are visible. These are the
ones where a reasonable operator flips the label, with the argument on each
side rather than a verdict.

| issue | labelled | the case for flipping |
|---|---|---|
| #386 | ALPHA | It is a gate, not a surface. Nothing an athlete sees changes when it lands. Counter: the work order makes it the stated precondition for unparking the modelling cluster, so it gates the partition itself. |
| #419 | ALPHA | It is documentation. Counter: it is the published contract a client integrator reads, and no test can see it, which is the eighth instance of the pattern. |
| #61 | ALPHA | No engine blocker is named by the client's photograph issues. Counter: loadline#87 is titled "rework the composer, starting from what a photograph does to the egress machinery", which is engine-shaped. |
| #378 | ALPHA | Needed only once the first photograph is kept, which has not happened. Counter: the birdseye says decide before the first one is kept, and that is exactly what this is. |
| #213 | DOMAIN MODEL | **The strongest unpark candidate.** "The engine cannot say whether a measurement was expected today" is the precise question loadline's gap surface asks and currently answers by inference from context rows. Contract 51 was the engine's partial answer to it. |
| #224 | DOMAIN MODEL | loadline's gapcard is a client-side implementation of the asking channel, built without one. If the client keeps building asking surfaces, the engine's version stops being speculative. |
| #232 | DOMAIN MODEL | It carries a section headed "What loadline needs from the engine". Worth reading as a symptom: that section was written by the engine side, and no loadline issue asks for any of it. A client-need section the client did not ask for is the drift in one paragraph. |
| #62 | DOMAIN MODEL | loadline#94 ("this importer can never produce a correction verdict") is the same family. Neither names the other. |
| #56 | DOMAIN MODEL | Athlete-defined activities are the differentiator by definition. It flips to ALPHA the moment the composer offers activity names rather than free narrative. |
| #148 | DOMAIN MODEL | It is a correctness issue, not a capability. Counter-counter: nothing in the alpha reads `as_of`. |
| #262 | DOMAIN MODEL | #402 is ALPHA and needs its answer to the interval-kind question. Arguably #402 should carry the part of #262 it depends on. |

### What the partition does not settle

- **It does not rank.** ALPHA is a filter, not an order. Eleven issues in one
  bucket still need the work order to sequence them, and the work order is
  itself stale: `#25` was rewritten against contract 47, the engine is at 54,
  its "74 open" is now 78, and its item 8 ("FILE THIS - it is the only engine
  blocker in a 13-issue client program") was filed and closed as #391 and
  shipped as contract 54.
- **It does not say close anything.** DOMAIN MODEL is not WONTFIX. Three
  issues do look overtaken rather than deferred (#102, #171 whose phase 0
  already refuted its own justification, #251 stalled on trademark), but
  closing is a separate decision on separate evidence.
- **It is a snapshot.** 78 open on 2026-08-19, against 84 on 2026-08-17 and 79
  on 2026-08-18. The backlog is converging, which weakens the urgency of the
  partition without touching its argument.

---

## Applying it

`scripts/route_d_labels.sh` applies the two labels exactly as tabled above. It
is deliberately not run as part of this work: applying a judgement to 77 issues
is the operator's decision, and this document is the evidence for making it.

    scripts/route_d_labels.sh --dry-run   # print every action, change nothing
    scripts/route_d_labels.sh --apply     # create the labels and apply them

It refuses to run without one of those two flags.
