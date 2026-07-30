# Prior art: Strava's official MCP connector

Swept 2026-07-30 against the live endpoint (`https://mcp.strava.com/mcp`) with a
subscriber account, full eligibility. This records the **actual** tool surface,
because the marketing description and the tool surface do not agree and the
difference changes a design decision.

Companion: #29 (why the developer API is not used), #30 (local frontend), #31
(hosted product). Read #29 first.

**No athlete values appear in this document.** It records shapes, field names
and provenance flags only. The engine repository is public.

## Access

- Remote HTTP MCP, OAuth with PKCE, scopes `read read_all activity:read
  activity:read_all profile:read_all` - all read, consistent with the
  read-only claim.
- **Subscriber-gated.** An `eligibility` tool exists specifically to report
  this, and it is the only tool a non-eligible account sees.
- **Claude-exclusive** at the client-product level (Claude web, desktop, Claude
  Code). Not "any MCP client" - see #30.

## The surface: ten tools

| Tool | Returns |
|---|---|
| `health` | liveness |
| `eligibility` | subscriber check; the only tool visible when ineligible |
| `get_athlete_profile` | name, location, gender, weight, measurement preference, current focus |
| `list_activities` | activity ledger; date range, ordering, cursor pagination; optional reduced polyline and tags |
| `get_activity_performance` | per-activity: HR/power flags, averages, calories, perceived exertion, PRs, segment efforts, best efforts, laps |
| `get_activity_streams` | time-series: time, location, heart_rate, watts, cadence, distance, altitude, velocity_smooth, grade_smooth, moving, temp |
| `get_athlete_zones` | HR (5), power (7) + FTP, run pace (5); source strings per family; `as_of_date` for historical lookup |
| `get_gear` | bikes and shoes, retired status, total distance |
| `get_club_info` | clubs |
| `get_training_plan` | **a marketing link to Runna. Not data.** |

### What is NOT there, contrary to the announcement

Strava's own materials advertise **Readiness** and **Fitness trends**. **There
is no readiness tool and no Fitness & Freshness tool.** Those answers are
evidently produced by the assistant computing them from `list_activities`, not
by Strava exposing their proprietary load model.

This matters: the connector's most-cited unique value - a second, independent
load model to arbitrate against our Banister CTL/ATL/TSB - **does not exist**.
What the assistant would be "arbitrating against" is its own arithmetic over
the same activity list we already hold. That is not a second opinion; it is an
echo. Corrected in #29 and #30, where an earlier draft claimed otherwise.

`get_training_plan` is the same shape of overpromise: a tool that returns an
advertisement. Recorded so nobody plans around it.

## Provenance flags: a partial retraction of the G88-inverted finding

#29 argued the vendor fails to declare its own provenance. **In the MCP surface
that is field-specific, not systemic.** Strava declares more than expected:

- `ftp_is_estimated` - explicitly flags a computed FTP
- `heart_rate_zone_source`, `power_zone_source`, `run_zone_source` - name the
  derivation per zone family
- `sample_race_pace.is_estimated` - flags whether the anchoring effort was real
- `has_heartrate`, `has_device_watts` - "inferred from stream presence", their
  words, so the flag itself is a heuristic and should be treated as one

**This is the good pattern and worth copying**: the estimate travels with a
declaration that it is an estimate. Our own derived values should do the same.

The G88-inverted finding still stands where it was raised - `total_elevation_gain`
(barometric or DEM-corrected) and `calories` (theirs or an upload partner's)
remain unflagged. The correction is that it is a gap in specific fields, not a
vendor-wide posture.

## Tiering, applied to this surface

**OBSERVATION** - `get_activity_streams` is the prize: device time series
including `location`, at selectable resolution, maximum granularity when the
parameter is omitted. `elapsed_time`, device laps.

**VENDOR INSIGHT** - `relative_effort`, `total_calories`, `elevation_gain`,
`avg_speed` / `max_speed` (both derived from their moving-time inference),
`achievement_count` / `pr_count`, estimated FTP and anything derived from it.

**COMPUTE OURSELVES** - everything in the third tier of #29, unchanged.

## The rule this surface does not change

**Nothing obtained here may be persisted.** It is a transient vendor query
(#29): consulted, never written to `data/*.jsonl`, never cited in a verdict.
The reason is P4 and it is independent of any licence question - a live remote
call is not reproducible, so it cannot back a number.

This bites hardest exactly where the surface is most tempting. `get_activity_streams`
returns GPS, which is real route data that `vitai route` could analyse - but
analysing it would produce numbers with no reproducible provenance. **The route
path stays on device files from the bulk export.** The MCP may tell us a track
exists; the archive is what we measure.

## Practical notes

- `list_activities` returns metric regardless; the caller is told to check
  `measurement_preference` on the profile and convert. Conversion is ours.
- Date-range filtering plus ascending order makes "when did this athlete
  actually start" and "where are the training gaps" cheap single queries. This
  is the connector's genuine strength: **fast reconnaissance over a long
  history**, to find out what the bulk export should be searched for.
- Rate limits exist per minute and per day; the numbers are unpublished.
- Response sizes are large. A month of a multi-session athlete is a substantial
  payload, and it all lands in the context window. Query narrowly.

## Verdict

The connector is a **reconnaissance instrument, not a data source.** It is very
good at answering "what is in this athlete's history and where are the holes",
which is precisely the question to ask *before* requesting a bulk export. It is
not a second opinion, it is not a load model, and it cannot be a record.
