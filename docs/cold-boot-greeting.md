# Cold boot: what the coach knows before you say hello

The integration test for the whole model. The athlete opens the app and says
"hello there." What happens between the tap and the greeting exercises nearly
every gap at once - context assembly (G42), the question loop (G39), situational
context (G34), goals-as-data (increment 1), the semantic-trajectory registry
(G40), the voice invariants (P7), and the firewall (P4). This doc traces it.

## The stance: a coach beside you, not a chatbot and not a stalker

The app is **not** a blank prompt waiting for input - a coach who forgets you
between sessions is not a coach. But it is **not** a surveillance system either.
The reconciling rule:

> **Stated context over live surveillance.** On boot the app assembles what it
> has been TOLD and GRANTED, not what it could scrape. It knows the athlete is
> on holiday in a hot town because they SET that mode (G34), not because it
> pinged GPS. It refreshes granted, genuinely-volatile world-state (weather for
> the known place, today's synced steps, today's calendar) and nothing else. It
> does not reach for GPS, photos, or the mic on "hello."

Every fact in the greeting traces to a granted source or a stated fact
(provenance / the JTMS model, G29) - the coach can always answer "why do you
know that". Consent is data (G32): each integration is granted once, ingested at
consent-time (G5), never silently hoovered live.

## The boot sequence (six steps, cheap-first)

1. **Assemble the standing state from the LOCAL world model - no network.** This
   is the G42 always-on summary: goals in force today (`state(today)` from
   increment 1), current phase + effective-dated targets, mode + facilities
   (G34), recent trend, live tripwires, and known routes/preferences (the G40
   registry). Fast, offline, and enough to be useful even with no signal.
2. **Refresh granted, volatile world-state only.** Weather for the KNOWN place
   (it gates the plan - a heatwave forbids a midday run), today's accomplishments
   synced (steps, sessions), today's calendar events. Network, but only granted
   sources, and only what changes fast enough to matter.
3. **Compute today's contribution state (G18).** Steps vs goal, calorie balance
   so far, what's counted vs unbudgeted - deterministically, in the engine.
4. **Find the live decision (a JITAI decision point).** Is there a time-sensitive
   choice the athlete would want surfaced now? A scheduled session whose window
   is closing; a constraint that just changed (heat + an evening obligation).
   Rank candidates by `info-gain x coaching-value / capture-cost` (G39).
5. **Assemble the greeting under the capture-cost budget.** Celebrate what is
   genuinely real, surface the ONE live decision, offer options. Not a wall of
   stats - one or two things (P8's economy extended to the greeting itself).
6. **Ask only what cannot be derived.** The athlete's INTENT / energy for the
   session - never their steps, the weather, or their schedule, which the app
   already knows. A question the app could have answered itself is a nag.

## Intent: engage, inform, help decide - never chastise

Asked point-blank whether the app's job is to inform, engage, correct, or
chastise: the ordering is **engage and serve first, inform second, help decide
third; correct only gently and only facts (a threshold, never character);
chastise never** (P7). A missed session in a heatwave on holiday is not a
failure and the app is structurally forbidden from framing it as one. The
greeting is an opportune JITAI touch, not a report card; the fallback when a plan
slips is framed as still-winning, because on a good cut it usually is.

## What it retrieves vs queries vs never touches

| Source | When | Example |
|---|---|---|
| Local world model (DB) | always, first, offline | goals in force, phase, mode, trend, routes |
| Granted volatile world-state | boot refresh, network | weather for known place, today's steps, today's calendar |
| Opt-in enrichment | at INGEST with consent, not on boot | photo geodata, Maps/Waze history (G35) |
| Live GPS / mic / camera | only if explicitly invoked; never on greeting | - |

## The firewall in the greeting

The numbers in the greeting (steps, deficit, pace) are deterministic engine
outputs; the warmth is narration OVER them (P4). The LLM assembles a friendly
sentence; it never computes the 12,000 or the deficit from whatever happened to
be in its context window. Context assembly (G42) feeds narration only.

## Worked example (generic)

State (all either stated by the athlete or granted): on holiday in a hot coastal
town; new goals logged yesterday; actively cutting; a run on the imported plan
for this evening; partner has an early-evening appointment so the athlete has the
kids until ~9pm; the athlete has said they won't run until it cools and prefers
daylight; a favourite out-and-back route is in the registry. By late morning the
step goal is nearly met.

The greeting the sequence produces:

> "Nice - step goal all but done before lunch. On tonight's planned run: it's
> still on the plan, but it's a scorcher and you don't run till it cools -
> sunset's late enough that once you're free around 9 you'd get cooling air and
> just enough light for the short version of your usual route. Still up for it?
> No pressure - you're on a proper cut and today's deficit is already in good
> shape; if it doesn't happen, an easy walk after dinner closes it out and it
> still counts. Holiday week - we're not chasing perfect."

Every clause traces to a source: step goal (contributions, G18), "scorcher"
(granted weather), "don't run till it cools / prefers daylight" (stated
preferences), "free around 9" (calendar + the obligation), "your usual route"
(G40 registry), "proper cut / deficit in good shape" (goals + engine), "holiday
week" (G34 mode). The only thing asked is the one thing unknowable: the
athlete's intent. Nothing was scraped; nothing was shamed; one decision was
surfaced at the right moment.

## Principle map

- **G42** context assembly - the standing summary + volatile refresh + the
  minimum sufficient working set.
- **G39** the greeting as a JITAI decision point under a capture budget; ask only
  the underivable.
- **G34** mode/facilities set the baseline and gate the plan (heat, holiday).
- **increment 1** goals-as-data give `state(today)` and the contribution verdict.
- **G40** the route registry supplies "your usual route" without a map query.
- **G32/G5** consent-as-data + enrichment-at-ingest = stated-context-over-
  surveillance.
- **P7** engage/serve, never chastise; the fallback still wins.
- **P4** numbers computed, warmth narrated.
