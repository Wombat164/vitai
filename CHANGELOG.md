# Changelog

All notable changes to vitai. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

Contract 35. `place_precise` arrives on `sessions` and `context`, and has no
column: the coarse tier is the default egress form, and everything else here
adds accessors over what the engine already knew.

### Added

- **`situation` names the thresholds with no history** (#148, the half
  `policy_digest` only made detectable). `as_of` reconstructs the record by
  filtering on `recorded_at`, which is right for everything the record holds -
  and thresholds live in `vitai.toml`, outside it. A week with no dated row is
  judged by whatever the file says today, so editing a floor in September
  silently re-judges every earlier week that lacked one, reconstructions
  included. Measured on the shipped corpus: 775 distinct judged weeks across
  nine of the ten personas, and not one dated threshold row anywhere.
- **`vitai pin-policy`**, which gives the toml's thresholds the dated history
  the data already has. Explicit, never a build side effect: the engine writes
  to the record only when asked, and it refuses under a knowledge cutoff, since
  a write computed from a partial view must not land in the whole record.
- **It protects nothing already judged, and says so.** The row is dated the
  record's horizon and a weekly verdict takes the policy in force at its
  Monday, so protection starts the Monday after: on the day you pin, zero
  already-judged weeks are covered. The past cannot be pinned and must not be -
  the toml has no history, which is the defect, and writing one from its
  present state would bury that under a fabrication indistinguishable from a
  record.

- **Units and aliases are published, in UCUM** (#310). `vitai schema --json`
  now carries `units` and `aliases` per field beside `types`, `affinity`,
  `sensitivity` and `coarse_companion`. A client was hand-maintaining both:
  the unit map because the unit lived in the field NAME by a convention
  nothing enforces, and the English map because nothing anywhere said that
  "resting heart rate" means `rhr`. The second failed silently - a question
  naming a forgotten metric matched no topic and fell through to a standing
  fact pack.
- **Six kinds of answer, because fewer forced a lie.** A `ucum` code;
  `unit_of` where the unit belongs to another field (a goal's target is in the
  units of its metric); `scale_of` where the row names its own scale;
  `unit_in` where the row names the unit itself (`sets.load` is kilograms on a
  barbell and a pin position on a machine stack, which is not a mass);
  `machine_scoped` for an ordinal on one manufacturer's scale; and `ordinal`
  for a position that indexes rather than measures. Plus `unstated`, for a
  check whose slug is athlete-invented and whose quantity nothing knows.
- **A classification gate**, the shape #299 used for sensitivity: a numeric
  field with no entry fails the build. Built from the shipped corpus rather
  than from `schema._TYPES`, because `_TYPES` has no entry for any of the
  fourteen numbers on `sets` - so a gate reading it walked past `load`, the
  one a strength client most needs.

### Changed

- **A field's unit is immutable, and that replaces the proposed
  `(field, generation)` key.** The generation table was the right instinct and
  rests on `_gen`, which does not hold it: `_gen` is absent on 128 rows across
  13 datasets in the shipped fixtures and defaults to 1, it is not a column in
  the read model so a consumer cannot look it up, and `_carry_meta` takes the
  maximum across merged claims. Changing what a field holds is a NEW FIELD,
  which the retirement register already records - the same property, without
  the unreliable key.
- **Which kind of channel last said anything** (#146). `capture` says how a
  value arrived; a new `initiative` axis on the same registry says whether a
  person had to do anything for it to arrive at all - the active-versus-passive
  split digital phenotyping and mHealth have drawn for years, where the point
  is that the two fail differently and the active side stops first. `situation`
  now carries `unresolved.channels`: when each side last reached the record and
  how long it has been quiet. No contrast field - both numbers are there, and
  emitting the difference only when the active side is the quieter would be the
  engine choosing which shape is worth naming.
- On the corpus that filed it, at the viewpoint its own expectation names, that
  reads: active silent since 2030-03-07, passive current. Two dates - no
  verdict, no threshold, and no word for what the gap means. The record cannot tell a bereavement from a holiday from a phone in a
  drawer, and a persona exists in this corpus to prove that guessing is wrong
  even when the guess is right.

- **What the scale cannot see: fat and fat-free mass, derived** (#46, G36).
  `schema.py` stated the intent - `kg` and `body_fat_pct` are the observed
  atoms and the decomposition is derived, never stored - and nothing was ever
  built. A weight goal is a proxy: two cuts ending at the same weight can be
  opposite outcomes, and a weight-only view says one went down and one went up
  and stops there.
- **Mostly a refusal, and the band comes from the record.** A change is
  resolvable only where the two readings' fat-mass intervals do not overlap,
  computed from `kg_lo`/`kg_hi` and `body_fat_lo`/`body_fat_hi` - which had no
  consumer at all until now. A published repeatability figure for consumer
  bioimpedance would be this engine asserting an accuracy claim about hardware
  it has never seen, so there is no constant anywhere in it. A reading with no
  declared band gets a third answer rather than a cautious no.

- **A restriction that restricts nothing is reported** (#75). A `medical` row
  whose own `kind` is `restriction`, or which names the `precondition` that
  would clear one, while `restricts` is empty. On a live record two such rows
  carried the words "RESTRICTION NOT ENFORCEABLE" in the note - they were
  right, and for three days the record stated a restriction no gate could act
  on while the athlete trained inside it. The note announced its own
  unenforceability, in English, and that announcement was itself unreadable.
  Mechanical rather than a prose scan, and reported per slug head so a later
  row that names the restriction clears it.
- **`avg_power` on `sessions`** (#91, contract 37). The one field on a cycling
  row that is a measurement rather than an estimate - `kcal` is modelled from
  heart rate and mass, `distance_km` from wheel size or GPS, and power is read
  from a strain gauge. The engine had nowhere to put watts, so any FIT ingest
  had to discard it. Named `avg_power` rather than the issue's `power`,
  because a bare `power` is ambiguous between average, maximum and normalised.
- **A track format the engine cannot read says so.** `read_track` dispatched
  on `.tcx` or else GPX, so a `.fit` file went to the XML parser and came back
  as `ParseError: not well-formed (invalid token): line 1, column 0` - true of
  the bytes and useless to the reader. The refusal names the format, says the
  file is not malformed, and says what converting to GPX costs.

- **`seq` and `supersedes_seq`: naming one row of several that share a key**
  (#239, contract 36). `line_key` falls back to `<date>/<source>`, so two runs
  on one day from one watch share a name - 71 per cent of sessions and 93 per
  cent of journal rows on a live record. Contract 33 fixed what a reference
  RETIRES; what stayed broken was naming an EARLIER row, so five rows of one
  key written as a chain could not be repaired by appending at all.
- **Two fields, never a parsed reference.** `supersedes` is untouched - same
  spelling, same meaning, and every reference already written keeps doing
  exactly what it did - and the position travels in `supersedes_seq`. Verified
  by a 10000-case differential against the previous engine over survivors and
  the applied set: zero divergence.
- **Stored, not computed.** Read-time positions renumber when a device syncs a
  row stamped earlier, so a reference written last week names a different row;
  the reproduction is kept as a test. `seq` is machine-set for the reason
  `recorded_at` is, and is the higher of the count of visible rows sharing the
  key and one past the highest position among them, so a machine that can SEE
  positions 3 and 4 does not stamp 2.
- **`validate` says which of the two ambiguities it found.** Where the matched
  rows carry distinct positions it names the `supersedes_seq` to write; where
  nothing can tell them apart it says so, because telling somebody holding a
  five-year-old file to add a vendor identity is advice they cannot take for
  the rows in front of them.
- **A sensitivity class per field, published** (#299). `field_types()` now
  carries `sensitivity` beside the type information, so a client gating egress
  derives its policy instead of hand-maintaining a copy of this schema that is
  wrong the day a field is added here.
- **Per `(dataset, field)`, because a per-name map cannot be right.** `reason`
  is on five datasets: on four it is prose about why a policy changed, and on
  `plans` it is the COM-B axis - a claim about why somebody did not train. One
  name, two disclosures.
- **No default, ever.** An unclassified field raises rather than taking a
  class. The failure this removes is a fallback standing in for a decision
  nobody made, and a default here would move that failure one layer in and
  make it the engine's. The whole table is pinned, so adding a field forces
  the decision at the point it is added - the same shape as #297's generation
  pin.

- **`vitai questions`, and `Vitai.questions()` beside it** (#224, the floor).
  The engine holding a question the record cannot settle, which is the one
  direction nothing here ran in. A deterministic derivation, computable with
  no model configured, no network, no permission layer and no budget.
- **Derive few; do not generate many and suppress.** Every question hangs off
  a plan that is still ahead, so a record with nothing planned produces
  nothing BY CONSTRUCTION rather than by a filter that could be relaxed or
  left switched off. The engine's urge to ask peaks exactly where asking is
  least welcome, and that property has to hold with the budget layer unbuilt.
- **Two kinds.** A `precondition` is a plan naming a condition nothing
  settles; a `clearance` is a planned activity gated on a check nobody has
  done. A gate that is simply blocked is not a question - nothing the athlete
  can say changes it.
- **It does not ask anybody.** No surface here speaks, `nudge_ok` is not read,
  nothing is written, and there is no table in the read model. The wording of
  a question belongs to whatever asks, because "no question may imply a duty"
  lives entirely in phrasing.
- **`plans.requires` has a reader.** It was written by the demo and consumed
  by nothing, and leaves the field-population backlog.

- **`vitai corrections`, and `Vitai.corrections()` beside it** (#143). A
  `supersedes` was accepted, applied and never characterised: `retractions`
  says a claim came down, `dataset` returns the survivor, and the row that
  lost sits in the file with both values, both timestamps and the context they
  landed in. This reports the pair - which fields moved, which way, how long
  the record held the value it later withdrew, and how many consecutive
  corrections to that field moved the same way.
- **It is asked and never raised**, deliberately. Not a tripwire, not in the
  build's findings, no column in the read model, and no message, severity or
  verdict word anywhere in what it returns. A run of same-direction
  corrections is a fact about a file; the engine bringing it up unprompted
  would be an accusation about a person whatever words it chose.
- **And it cannot tell an honest correction from a flattering one.** The
  persona corpus pairs the two on purpose and they are structurally identical.
  A test asserts the output is the same for both, because a detector that
  appeared to separate them would be claiming a discrimination it does not
  have.

- **The retraction ledger reaches `emissions`** (#134). An assertion the
  engine surfaced to a person, whose `basis_claims` name a claim the record
  has since restated - or an inference that has since fallen - now produces a
  ledger entry of kind `emission` and a `review` tripwire. The issue asked to
  extend the justification link beyond `inferences`; the record already had
  three spellings of that link (`inferences.depends_on`, `derived_from` on six
  lineage datasets, and `emissions.basis_claims`) and two read paths between
  them, so this wires up the third rather than adding a fourth field.
  `emissions` is the one artifact here a person was handed, and it was the one
  with no reader.
- **An assertion is never retracted by this, and the entry says so.** The
  engine did say that, on that day, to that surface; what moved is what it
  rested on. Whether the same thing would be said today is `still_holds`,
  which needs the policy in force at the assertion's date (#148).
- **`JUSTIFICATION_LINK`**, naming the field each cascade reads, with a
  control that proves each named dataset is really read by building a record
  and checking an entry appears.
- **`stream` on `vitai resolve --json`**, saying which of the three streams a
  line came from.
- **A shipped example.** `examples/demo/data/emissions.jsonl` carries one
  assertion resting on the demo's one correction and one resting on a claim
  nothing has touched, so the distinction is exercised rather than asserted.

- **Two tiers, and the coarse one is what leaves** (#205, contract 35). The
  record's stance was privacy by not storing the thing: `place` was
  documented as coarse and never an address. That is blunt, and it discards
  real utility, because "outdoors" cannot tell the park an athlete likes from
  the one they avoid. `place_precise` is now storable on `sessions` and
  `context`; `place` keeps its name and its coarse meaning.
- **A precise value is refused unless a coarse one travels with it.**
  Required rather than derived, and the difference is deliberate: reducing an
  address to "home" needs a lookup the build forbids or a mapping only the
  athlete holds, and a guessed coarse value would be wrong in the direction of
  looking right. Same invariant, no pretending.
- **The gate is at the boundary.** The coarse projection is applied once, at
  the read door every surface goes through - twenty-five public methods, the
  CLI's thirty-five print sites, MCP, the SQLite build and the inference
  prompt all read from it - so the default projection structurally cannot
  carry the precise tier. `Vitai.precise(dataset, release)` is the only other
  path and requires a release naming what it is for, because permission per
  use is not a standing flag.
- **The read model has no column for it.** A null column would read as "nobody
  wrote one" rather than "you are not being shown this", which is the same
  reason the key is dropped and not nulled.
- **`coarse_companion` on `field_types()`**, so a consumer building its own
  projection learns which fields have no column and what is shown instead.

### Fixed

- **A spelling made a phantom protocol seam** (found reviewing #315).
  `protocol_seam` compared the raw strings, so `Fasted-Post-Void` and
  `fasted-post-void` were two protocols and a weight rate was declined as NOT
  COMPARABLE for an athlete who weighed the same way both times. The comparison
  now folds the way `vocab.resolve` does - normalise AND decamel, so the
  vendor token shape `FastedPostVoid` matches too - while the reported name
  stays the athlete's own spelling and the ordering comes from `order_key`
  rather than file position. A separator folds to a word boundary and never to
  nothing, so `post-void` and `postvoid` stay two protocols. A refusal that
  fires on a typo is one readers learn to skip past.
- **`SLUG_RE` accepted a trailing newline**, because `$` matches before one in
  Python - so `"hop-test\n"` passed all six slug checks in `schema.py` and a
  value that is a slug plus an invisible character validated clean. Found
  through `protocol`, where the fold then merged it onto the real slug with the
  validator saying nothing, so the fault had no witness anywhere.
- **`rest_s` now has a stated direction** (#225). It is the rest AFTER this
  set, and the schema is where that is defined. It had been stated once, in a
  swimming aside in `exercises.toml` - "the rest before the next is `rest_s`" -
  which is the same rule from the other side, in a sport-specific comment doing
  a schema's job. A direction nothing states is one two importers settle
  differently: the same interval attaches to set 3 for one and set 4 for the
  other, and the rows validate identically either way. Nothing reads the field
  yet, which is why this is free to state and free to get right.
- **Two rules had two homes each, and a sweep now says so.** `anatomy` carried
  a byte-identical copy of `vocab._normalise` - the fold every registry lookup
  uses to decide two spellings are one thing - so widening it for unicode
  dashes would have reached every registry and left `pain_site` resolving the
  old way. And `_numeric` sat in `query`, `resolution` and `safety`, where it
  decides whether a pain score reaches a gate; it is `schema.is_number` now.
- **A test sweeps the engine for byte-identical function bodies** across
  modules and holds the answer to a pinned list. Every expensive defect this
  engine has shipped is the same shape - a forward map at eight readers, a
  second tokeniser, half a fold - and none of them disagreed on the day they
  were written. They disagreed the first time one copy learned something.

- **A rate across a protocol change is declined** (#174, proposal 4).
  `fasted-post-void` and `fed-evening-clothed` differ by breakfast, a day's
  fluid and a pair of shoes, so the two ends of such a rate measure different
  things. The engine already refuses a rate whose weigh-in TIMES are spread
  widely enough to account for it; this is the same refusal with a discrete
  cause - `not_supported` in the verdicts, NOT COMPARABLE in the rollup, with
  no direction word beside it and no size attached, because what a clothed
  weigh-in adds is a per-protocol accuracy claim the engine has no basis for.
- The rollup's rate window now reaches back over the trailing mean its earlier
  anchor stands on. Scoped to the anchor alone, a protocol change the rate was
  standing on went unseen and printed "FAST - raise intake" while the verdicts
  refused the same week. The #37 timing check shares the bound and inherits it.
- `weight.protocol` leaves the field-population backlog: written from row one,
  validated, and until now read by nothing.

- **`BONE_STRESS_PHRASES` widened to the published continuum** - stress
  reaction, stress response, stress injury, stress lesion, stress fx, stress
  fracture, bone stress. Sports medicine names the whole spectrum "bone stress
  injury" and grades it from the imaging-only end to a frank fracture; the
  marker knew only the last of those, so the earliest and most treatable
  presentations read as nothing. `stress fractures` removed: `stress fracture`
  is a prefix of it, so it could never add a match.
- **A work-stress note was still being read as a bone injury** (#115, item 6).
  #67 found "Work stress flare-up" becoming bone-stress injury history and
  holding a healthy athlete's training, and fixed the half where `body_site`
  was null - `str(None)` is the truthy string "None", so the site guard passed
  on every row that omitted one. With a site PRESENT the bare word `stress`
  anywhere in a title still fired. Same harm, one condition along. The phrase
  list already reads every medical title and note, so dropping the loose
  branch costs no sensitivity, and the test that proves it was already there.
- **A screening marker asserted a condition the record only mentioned.**
  "bone-stress injury history" says the athlete HAS one, inferred from a
  phrase in a note. It now reports what the record says.
- Two boundary strings that survived #121: the safety module described its
  thresholds as "conservative SCREENING bounds", and `schema.SEVERITIES`
  defined `red_flag` as "a claim that this needs a clinician now". Both now
  describe what the ENGINE does - that a figure is outside the range it will
  reason about, and that a hardcoded escalation fires - rather than what
  anyone should do about it.
- **A gate nobody could read was a clear run.** `restricts` was matched by set
  intersection on the RAW tokens, so anything the intersection could not hit
  vanished - and `may()` fell through to `allowed`, with the reason "no gate in
  force covers this activity", on a record whose own gate said `blocked`.
- **And the worst case needed no mistake by anybody.** `restricts: gym` is a
  RETIRED activity class: `ACTIVITY_CLASSES` unions the retired values in, so
  the line validates clean, and no session type declares `gym`, so it matched
  nothing. A severe active episode, correctly written against the vocabulary of
  its day, silently stopped gating. Every token now resolves through the
  registry first, so `gym` becomes `strength` and bites - which is the
  retirement doctrine already written in `vocab.py`, applied by the reader that
  was not doing it.
- A token nothing resolves is still tried verbatim, so a gate naming an
  activity outright keeps biting it, and is reported as unreadable only when it
  misses - `may()` answers `unknown` naming the token, and `is_gated()` refuses
  rather than permits. An unreadable gate raises no clearance question: the way
  out is fixing the record, not doing a check.
- **A documented mapping that did not exist** (#126 follow-up). The README's
  migration table and the wiki reference both said `sessions.location` is read
  forward as `place`/`route` the same way `hip_pain` is read as `pain`. Nothing
  reads it forward. Nobody was lying: a RENAME THAT WIDENED and a SPLIT INTO
  OTHER TYPES were assumed to be one kind of event, and only one of them is.
  `hip_pain` -> `pain` is a rename - the old value is exactly a valid new
  value. `location` -> `place` + `route` is a split, and free text is a valid
  value of neither, which is why the split happened. Which successor a string
  belongs in is a judgement only the athlete can make, so nothing maps it, and
  now that is said rather than left to be found by grep.

### Added

- **`schema.KEY_FORWARD` and `schema.TERMINAL_RETIREMENT`** (contract 38).
  `KEY_RETIREMENT` recorded THAT a key was retired and nothing recorded whether
  anything reads it forward. The first names the one CALLABLE that reads each
  mapped key forward - and a test reads that callable's source for the key,
  because a register that certifies an absent reader is worse than no register.
  The second says why the rest are never read, and what to append instead, per
  key: the two terminal retirements here need opposite advice.
- **An `unread_retired_value` tripwire.** One `review` per field, not per line.
  It does not claim the value is lost - the column still holds it - only that
  no successor inherited it, so nothing built on the successors sees it.

- **A gate that could not say where it hurt** (#126, G89 part two). `hip_pain`
  is retired in favour of `pain` + `pain_site`, and `canonical_daily` is meant
  to be the one place an old line is read forward. Eight readers re-implemented
  that map inline, and the copies were not equivalent: they carried the score
  and dropped the site. A legacy record's gate said `pain 4 at unspecified
  site` while the rollup prose two lines below it said `at hip` - one row, one
  day, two answers, and the vaguer one was on the safety surface.
- **A red flag that turned on a word choice.** Found reviewing the above.
  `pain_site` validates against a registry that accepts aliases, and both
  red-flag loops compared the raw string to slug-keyed `RED_FLAG_SITES`. A line
  saying `ribs` - clean, validated, an alias of `chest` - produced no cardiac
  escalation, while the same pain spelled `chest` produced an EMERGENCY. Both
  loops now resolve through the registry.
- One unreadable legacy row was counted as two in the rollup's date tally, and
  a painful row with no site was reported `at hip` - the retired field's joint,
  named for a record that never named it.

### Changed

- A pain gate's slug is now the registry slug rather than the spelling
  written: an existing record writing `IT band` sees `pain:knee` where it saw
  `pain:IT band`. No gate appears or disappears - firing turns on the score -
  but a consumer keyed on the slug sees a changed identity, and the gate and
  the prose now agree.

- **The rollup leads with what is blocking** (#76). Measured on a live record,
  83 per cent of the document was one table and everything actionable sat in
  its last thirteen lines. Gates, then safety, then tripwires now come before
  any table, and "nothing gated" and "nothing firing" are stated rather than
  left blank.
- **Gates sit above tripwires, which their own comment already claimed.** It
  said gates "outrank tripwires and sit above them in the reader's eye", and
  the code emitted them afterwards - on the shipped demo, `## Gates` at line
  56 and `## Tripwires` at 52.
- **A week of cycling is no longer a week of nothing.** The training table
  counted running and strength, and every other session still created its week
  row - so a 20 km ride, a swim and a walk each rendered `| 0.0 | 0 | 0 | - |
  - |`, identical to a week nobody trained. The table gained a column for
  everything else, which is why the issue's ask to suppress all-zero rows is
  not the fix it looks like: most of them were weeks somebody trained in a way
  the table could not describe.
- **The training table is bounded**, to `rollup_weeks` (default 12), and says
  how many earlier weeks it did not show.
- **The easy-cap flag says whose cap it is.** `vitai.toml` has no history, so
  `OVER +2` against a run from years earlier asserts a comparison nobody made.
  Stated once per section rather than implied on every row.
- **The weight rate was measured over one span and divided by another**
  (#142). `status()` compares the mean of the last seven weigh-ins against the
  mean of the seven before them, and divided by the days between the
  eighth-from-last and the last. Where weigh-ins are dense those are near
  enough the same window; where they are not they are unrelated. On flat
  clusters either side of a fourteen-month silence it reported losing 3.43
  kg/week - a rate nobody could have lost, from a record in which no observed
  reading ever changed. Two block means are separated by the distance between
  their centres, which is what it divides by now.
- **`rate_span_days` and `rate_unobserved_days`**, beside the figure. The rate
  had no span published at all, so a figure reaching over 221 days on a real
  corpus was rendered against `mean_kg_span_days` saying 114 - a label added
  (#209) so consumers would stop mislabelling the MEAN's window. Facts rather
  than a verdict: whether a span containing a hole makes the figure unusable
  is the refusal predicate the uncertainty work owns, not a threshold picked
  here.

- **A generation is appended, never inserted** (#295). A dataset's schema
  generation is how many bump blocks appear above a point in `schema.py`, and
  `_gen` is stamped into a line at append time and never rewritten. #287 added
  its block above four that already existed, so fifteen numbers moved - fourteen
  key generations and one retirement - and a number already sitting in records
  started denoting a LATER schema state than the one it was stamped under. G25's
  exemption then read old lines as owing keys that did not exist when they were
  written: on a real record, 280 problems across 140 lines, none of them about
  the contents.
- **It was silent and retroactive, and the remedy was unavailable.** Nothing
  broke when the change merged; the record was correct, the engine was correct,
  and the two disagreed only once a reader compared them. `_gen` cannot be
  rewritten, and appending corrections would restate hundreds of rows to absorb
  a numbering choice that was not the record's mistake. So the fix is in the
  engine and repairs records already written rather than only the next one.
- **The number moved; the column order did not.** `KEYS` order is the read
  model's column order, so the keys stay exactly where they were and only the
  generation assignment moved to its place in merge order. No table, column or
  line shape changes, so the contract is unchanged.
- **`tests/test_generation_numbering.py` pins the whole table** - generations,
  retirements, current generations, and the founding key set that has no
  registration - so the next insertion fails at the point of insertion with the
  moved numbers named, rather than surfacing weeks later as a report about
  somebody's record. Corpus tests could not do this: #287's fixtures were
  regenerated in the same change, so they agreed with the broken numbering and
  stayed green.
- **A missing key is reported as an old line, not as a writer to correct**
  (#296). `append` rebuilds every row from `KEYS`, so a caller cannot omit a key
  and no line the engine wrote can trip this - which made "use null for unknown,
  never omit" advice about something the writer could not have done differently,
  on every one of the 280 rows. The message now states the line's generation and
  the key's, and names the three things that produce it.

- **A justification quoting the engine's own published claim id could never
  fall** (#134). `claim_id` appends an ordinal on `sessions`; the retracted
  set is built from a `supersedes` reference, which cannot know one. A
  consumer copying an id out of the `claims` table wrote a dependency that
  silently never cascaded. Both spellings are now accepted.
- **`vitai resolve --json` could not say which stream a line came from.** Each
  line was labelled `{"kind": <stream>, **row}`, and tripwires and retractions
  carry a `kind` of their own, so the label was overwritten. `kind` is left
  exactly where it was and `stream` is added beside it.

- **Validation problems no longer quote a precise value** (#205). The
  diagnostic channel is an egress surface and it is the one nobody looks at:
  roughly twenty-five messages quote the offending value, and those strings
  travel out through `validate()`, the load report's warnings, the CLI and the
  MCP validate tool. A column-shifted import that put an address into `date`
  returned it verbatim.

- **`api.field_types()`, and a `fields` key on `api.schema()`** (#257). What
  each field of each dataset may hold (`types`), how it is projected
  (`affinity`), and whether it is a list needing JSON decoding (`container`).
  `KEYS` was public and the types were not, so a consumer building a queryable
  projection could check its column names against the engine and had to guess
  or copy everything else. One copied, and the copy went several increments
  stale. Carried on `schema()` rather than behind a fourth accessor, so `vitai
  schema --json` and the MCP `schema` tool reach it without either being
  taught anything.
- **`db.column_affinity()` and `db.LIST_COLS`**, the two facts that accessor
  needed and that lived in private names.


- **`__version__` was 0.4.0 on a 0.5.0 engine.** The release bumped
  `pyproject.toml` and left the package constant behind, so `vitai --version`,
  `schema()["engine"]` and the MCP server's reported version all named the
  previous release. Its only job is to be accurate about which engine is
  running. A test now holds the two in step.
- **The two public contract tables were checked for coverage and not for
  agreement**, which is the gap #184 recorded while it was live: the README
  said `0.4.0` for contracts 16 to 19 while the wiki still said `unreleased`.
  Both tables had the rows, so the existing check could not see it.

## [0.5.0] - 2026-08-04

Contract 19 to 27. The increment where the engine learned to say how much it
vouches for a number, and stopped answering questions it had not understood.

Everything here is additive: old lines keep validating and a consumer that
ignores every new column sees the previous behaviour. What changes is what a
consumer can now ask, and what the engine will now refuse.

### The theme, if there is one

A record that holds a number and a record that stands behind it are different
records. Most of this release is the second kind arriving in pieces: a value
that says which rows it was computed from, a subjective figure that says what
scale it is on, an effort that says whether it was measured or derived, and a
goal that says whether it was reached or merely closed.

The other half came from building a consumer. vitai-lens was tested
adversarially by four subagents playing athletes, and it confabulated - with no
model in it anywhere. Not numbers: every figure it printed was exact. It
fabricated the frames around them. Several refusals in this release exist
because of what that found.

### Added

- **`best_efforts`** (contract 27): the fastest 1k, 5k, 10k, half and full
  inside every stored track, one row per (track, distance). The question a
  runner asks first, and one no field could answer - a distance and a duration
  make two runs of different lengths comparable on neither. `basis` says
  whether the window was measured against the device's own cumulative distance
  or the engine's haversine sum, and on a real 11 km run those differ by
  twenty seconds over ten kilometres.
- **Declared scales** (contract 26): `rpe_scale`, `mood_scale`, `pain_scale`.
  A bare RPE is ambiguous between two standard scales in common use, where a
  stored 7 is "quite light" on one and "very hard" on the other. Absent means
  unstated, and a consumer must not invent a denominator.
- **Goal lifecycle split from achievement** (contract 25): whether a goal is
  still being pursued and whether it was reached are two questions, and one
  column answered both.
- **Goal polarity** (contract 24): which direction counts as progress. A
  ceiling and a floor are not the same goal with the sign flipped.
- **`built_on` and a record-derived viewpoint** (contract 23): an unqualified
  build takes its viewpoint from the record's last date rather than the wall
  clock, so the same record built on two days gives the same database.
- **`pending`** (contract 22): a refusal that means "not yet" rather than "no".
- **`emissions`** (contract 21): what the engine told the athlete, and when. A
  judgement nobody was shown had no consequence to retract.
- **`derived_from` and `derived_op`** (contract 20): which rows a computed
  value stands on, and how, in the athlete's own words. Declared, not
  executable.
- **A daily goal period and a nutrition target**, with the declaration gate
  that refuses a target set beneath a safety floor. The floor stays
  non-suppressible underneath it.
- **Exercise requirements**: what a movement needs before it can be
  prescribed, so a plan can be costed against a place.
- **`ines`**, a tenth persona with no history, so her nulls are the real kind
  rather than "the field did not exist yet". She caught a polarity defect on
  her first build.

### Changed

- **One supersede retires one row.** It used to retire every row whose key
  matched, and `line_key` falls back to date-and-source, so a correction aimed
  at one of ten sessions retired all ten. Silent data loss through the
  correction path.
- **Independent sources are counted, not rows.** Rows standing on a shared
  input now count as one witness however many rows they are.
- **`volitional` names the mechanism, not the reserve.** Stopping at a judged
  limit without testing it is `volitional` with `rir: 0`, which is how most
  sets actually end.
- **`validate` distinguishes a line already corrected from one still wrong.**
  A validator whose output can never reach zero is one people stop reading.

### Fixed

- **`best_effort` was up to eleven per cent slow on unevenly sampled tracks.**
  Elapsed time as the window slides is piecewise linear, so the minimum sits
  at a breakpoint - and breakpoints come in two families, the window's end
  crossing a fix and its start crossing one. Only the first was evaluated.
  Verified against a continuous search at 1 mm resolution: 6,372,612 positions
  and 120 candidates now agree to nine decimal places.
- **A few fixes without a device distance no longer lose the basis.** A real
  watch carried `DistanceMeters` on all but the first two of several thousand
  fixes, and an all-or-nothing test threw the device's entire account away.
- **`Vitai.goals()` returned zero rows** on every fixture in the repo, because
  the query surfaces took their viewpoint from the wall clock while `build`
  took its from the record.
- **Achievement ignored polarity**, so a ceiling held 87 kcal over its cap
  reported `achieved`.

### Documentation

- Every contract row now names the release that shipped it. Rows 2 to 15 said
  `unreleased` while 16 to 19 said 0.4.0, which cannot both be true, and the
  README and the wiki disagreed with each other about 16 to 19. Taken from the
  tags: 0.3.0 shipped contract 15, 0.4.0 shipped 19.
- The wiki documented an ordinal syntax that was removed as unsound. It was
  the only place that syntax still existed, which is the worst place for it to
  survive: someone writing a correction against it would get a refusal with no
  explanation.
- The CLI reference documented 14 of 27 commands. The missing ones included
  `situation`, `claim` and `mcp` - the entire client surface, which is
  precisely what a client author opens that page for.
- Three datasets were missing from the data-model reference: `emissions`,
  `protocols`, `regimes`.

## [0.4.0] - 2026-08-02

The increment where the engine grew a surface a client can build on.

Everything before this assumed the consumer was a person at a terminal or an
agent that had read the source. A client application cannot be either. It needs
the whole state in one call, a way to write back that stamps its own
provenance, a version to pin against, and refusals that say WHICH kind of no.
All four landed here.

### Added
- **The whole situation, in one call** (#158 rung 2). `Vitai.situation()` and
  `vitai situation`. The alternative it replaces is fifteen calls a consumer
  stitches together, which is fifteen chances to stitch it wrong, and the
  stitching is exactly the work that must not be duplicated per consumer:
  each one gets it subtly differently and none of them is the engine.

  Shaped for something that has to DECIDE rather than display. It leads with
  what would stop a decision, then what is true now, then what the engine will
  not vouch for. `unresolved` is present even when empty, because a consumer
  rendering an empty section knows it asked, where a missing key tells it
  nothing was said.

- **Write parity: an agent appends a claim and the engine stamps it**
  (#158 rung 4). Two shapes, because there are two acts: a stated quantity,
  and an utterance no quantity can honestly be taken from. Writing nothing for
  the second is what hands the record to whichever tool is willing to write the
  sentence down.

  **The caller supplies what was stated and nothing else.** Provenance is
  stamped by the engine, and a caller that could set it could file a
  recollection as a device reading or manufacture an independent witness out
  of nothing.

- **An MCP adapter** (#158 rung 5). A second harness, never a second surface.
  Tools are DERIVED from the API: each names a method, its description is that
  method's own first docstring line, and a name that does not resolve raises at
  import. So the adapter structurally cannot expose a capability the API lacks,
  nor document one differently. Stdlib only; MCP's stdio transport is a few
  dozen lines of newline-delimited JSON-RPC.

- **`no_data` says which kind of no**, contract 18 (#177). It was one word for
  four states, separable only by inspecting which fields were null: the input
  was missing, no policy was configured, the measurement could not support a
  judgement, or the metric was suppressed and the row vanished entirely.

  A `reason` column now answers "why not" while the verdict answers "can a
  judgement be rendered", which is one question with one answer. **A reason is
  required with a refusal and forbidden without one**, so a new refusal cannot
  ship unlabelled. A reader that ignores the column sees the previous
  behaviour. Suppression also stops being an absence: a removed row and an
  uncomputed metric were different facts rendered identically.

- **Protocol and regimes**, contract 19 (#179). `protocol` names the conditions
  a measurement was taken under, defined in the athlete's own words. **A row
  with no protocol is a different epistemic class**, not a row missing an
  optional field.

  A regime declares a bounded interval during which a class of claims was
  UNANCHORED: honestly restated, never measured under stated conditions. The
  interval **resolves empty and nothing is backfilled** - the measurement that
  ended it is evidence the earlier claims were unanchored, not evidence of what
  the true values were. The claims stay on disk; what ends is their standing as
  values. **No trust parameter moves, and there is none to move**: discovering
  your own error must not cost you standing.

- **Row identity** (#181), the primitive #168, #169 and #170 were all waiting
  on. A qualification has to name the observation it qualifies, a relayed
  reading has to name which reading it relayed, and a derived value has to name
  its inputs. None of them can be built on a reference that points at more than
  one row.

- **The restatement detector** (#176). A number repeated unchanged across days,
  in a quantity the world makes vary, is evidence it was RESTATED rather than
  observed. Advisory, never a fault: it names the run and says that a regime
  declaration is the answer if the athlete meant it.

  It runs AFTER regime application, deliberately: a declared regime has already
  emptied its interval, so the detector cannot re-flag a restatement the
  athlete has already named.

### Changed
- **The MCP adapter's declared surface is now its whole surface** (#183). The
  advertised JSON schema was advisory to the client and the server splatted
  whatever arrived, so a caller could reach parameters the tool deliberately
  did not offer.

### Added
- **A public accessor for the shape this engine emits** (#147). `vitai schema`
  and `api.schema()` return the contract version and the per-dataset
  generations.

  Anything that PINS against this engine needs those two numbers: a fixture
  corpus that must refuse to regenerate when the shape has moved past what it
  was authored against, a content repo recording which engine wrote it, a
  client checking an artifact is still readable. Every one of them had to reach
  into `db.CONTRACT_VERSION` and `schema.CURRENT_GENERATION`, which are private
  and will move. **A pin that reads private surface breaks silently on an
  upgrade**, which is the failure the pin exists to prevent: the guard and the
  thing it guards against sharing a failure mode.

  `contract` versions the READ MODEL, the built SQLite shape a consumer gates
  on. `generations` versions the LINE SHAPE per dataset. They answer different
  questions and a consumer usually needs both. **`engine` is provenance and
  deliberately not a gate**: it moves for a docs fix and stands still while the
  schema moves, and both directions have happened here.

  Takes no `--root`, because the answer is a property of the installed engine
  rather than of anyone's record.
- **A policy digest on the read model, contract 17** (#148). `as_of`
  reconstructs the record by filtering `recorded_at`. That is right for
  everything the record holds and wrong for everything it does not, and
  threshold baselines are in the second category: they live in `vitai.toml`,
  a mutable file with no history.

  `thresholds.jsonl` overlays five keys per week, which was the G14 fix, but
  a week carrying no dated row is still judged against whatever the toml says
  **today** - and the rest of the config (rate phases, the resolution ladder,
  suppressed metrics, the check tolerance, the intake buffer) has no dated
  history at all. So editing a threshold in September silently re-judges
  every historical week that lacked an explicit row. A reconstruction of
  March returns March's data under September's policy.

  This does not fix that. It makes it **detectable**: `meta.policy` carries a
  content hash of the policy the record does not hold, so a reconstruction
  taken under one config and one taken under another can be known to be
  incomparable rather than quietly differing. Build systems put the
  environment in an action's identity for the same reason. The claims in
  `policy.py`, `jsonl.load` and `Vitai.as_of` are narrowed to match what they
  actually deliver; finishing G14, so a toml change is snapshotted into the
  record and `state` becomes total, remains open.

- **A correction that does nothing now says so.** `load` walks the record
  backwards so a line can only be superseded by a LATER one, which is what
  stops a same-day correction sharing its target's key from superseding
  itself. "Later" means later in the MERGED order - `(recorded_at, device,
  position)`, with an unstamped row sorting first - and that is not always
  the order the athlete wrote things in.

  So a correction can sort BEFORE the line it corrects: an unstamped
  correction of a stamped line, a correction stamped a minute earlier by a
  second device's clock, an unstamped correction in a device file whose slug
  sorts first. The walk reaches the target before it ever sees the reference,
  the target survives, and the correction validates, reads correctly to a
  human and does nothing. A typo fixed from 8.04 to 80.4 left 8.04 in the
  record.

  `vitai validate` now reports it, as an ADVISORY: the lines are already on
  disk, they are not malformed, and the record still builds. What was wrong
  was that nothing said so. It asks whether the correction APPLIED - running
  the same retirement `load` runs - rather than looking for the shape, which
  makes it exact and, more importantly, self-clearing: the append that
  repairs the record retires the dead line along with the value it was aiming
  at. The ordering itself is unchanged, because deciding what "later" means
  for a row that declined to say when it was written is a question for the
  clocks doctrine rather than a validator.

- **Key custody: an untested backup is not a backup** (#107). `vitai key new`
  and `vitai key check`, plus a setup that cannot report success without a
  passing restore drill.

  Under hold-your-own-key there is no recovery path, so the failure mode is
  not "never stored the key" - it is **believed they stored it**. A key pasted
  into a note app that later syncs to a dead account feels like storage and is
  not. So the athlete proves recovery while the record is empty and the cost
  of failure is zero.

  **Two forms, never either.** A checksummed phrase for paper and the raw key
  for a manager - a design offering only the second makes the manager a single
  point of failure for a decade of health history, and `setup` says so when
  the key exists in only one place.

  The phrase uses a **BCH checksum**, which detects any error of up to four
  characters, always. A single-character transcription error is reported as a
  TYPO with the group named, not as a wrong key - which is the difference
  between a fixable transcription and a lost decade. Crockford's base32 means
  I, L, O and U cannot occur, so seeing one is always a misreading and is
  folded rather than rejected.

  **Rotation re-encrypts the whole blob set**, feasible precisely because the
  record is a few MB. A half-finished rotation leaves every original in place:
  half a rotation is recoverable, half a rotation with the originals deleted
  is not.

  BIP-39 words would be a better paper form and are not vendored, because the
  wordlist's licence has not been checked and this repo checks before
  vendoring. The engine names no password manager, so there is no referral
  relationship to disclose.

### Added
- **Transport, custody and cipher as engine interfaces, with a conformance
  suite** (#108). `vitai conform --transport X --custody Y`. The suite is the
  deliverable, not the prose: a written contract produces implementations that
  mostly work and fail strangely; a suite produces implementations that either
  pass or do not.

  **The bundled implementations run it as ordinary implementations.** That is
  the test of whether the layering is real - every layered architecture that
  failed did so because the first-party version quietly used a capability the
  interface never exposed. A third party's implementation is resolved by
  dotted path and handed to the same suite.

  Three transports (directory, memory, mirror) and two custody backends (file,
  environment), because an interface with one implementation is a refactor
  waiting to happen - and the one that catches a hidden assumption is the one
  shaped least like the first.

  **Backup is not a subsystem.** A second transport configured for retention
  IS the backup, and restore is `list()` plus `get()`. That falls out of
  #105's append-only blob set rather than being designed.

  **The engine ships no cipher, and that is a refusal rather than a gap.** The
  standard library has no authenticated encryption, and hand-rolling one is
  how this goes wrong - so `Cipher` is a contract with no bundled
  implementation and `plan_upload` REFUSES to hand a transport anything
  unsealed. Blob ids are derived by HMAC under the record's own key, so the
  mapping from a filename is not computable by whoever holds the blobs, and
  sizes are padded to powers of two (#106).

  The restore drill is an engine capability: given a custody backend and a
  transport, put the record through and get it back. The failure mode is not
  "never stored the key" but "believed they stored it".

## [0.3.0] - 2026-08-01

The increment where the record learned to say how it knows things, and the
engine learned to stop talking.

Three threads ran together. **Provenance became total**: origin, path, capture,
value-kind, a catalogued source registry, a content-addressed store for the
evidence behind a value, and transaction time on every dataset, so a number can
now say which instrument produced it, how it was acquired, whether it was
measured at all, and what the record said about it at any past instant.
**Strength training became first-class**: the set is the atom, with an exercise
registry, modifier axes and reads that refuse rather than guess. And **the
medical boundary was drawn and enforced**: the engine states what the record
shows, declines to issue a plan, and routes nobody, with a deterministic lint
over the whole public surface so the line cannot erode quietly.

Nine synthetic athletes now live in the test suite, each built to break
something, each carrying deliberate falsehoods with their ground truth.


### Added
- **Multi-device writes: one writer per file, so a merge is a set union**
  (#105). `data/daily.laptop.jsonl` and `data/daily.phone.jsonl` are disjoint,
  so **no two devices ever write the same file and a conflict cannot occur** -
  not "conflicts are resolved", structurally cannot happen. Readers union
  `<dataset>.*.jsonl` alongside the plain `<dataset>.jsonl`; a single-file
  record is simply an actor whose name is nothing, and keeps working
  untouched.

  **Which makes the sync layer content-blind, and that is the point.** A
  transport built on this moves opaque files: it never parses a row, never
  knows a schema, cannot corrupt data it cannot read, and needs no contract
  bump when the schema moves. Holding the athlete's own key becomes nearly
  trivial as a consequence - a server that never could read the content has
  nothing to be trusted with. The property a zero-knowledge design buys with
  cryptography, this buys by never looking.

  `device` on every dataset, machine-set like `recorded_at` and refused when a
  caller supplies it. Beside `source`, never inside it: `source` says which
  INSTRUMENT observed the value, `device` says which MACHINE wrote it down,
  and conflating them would make a phone and a laptop look like two
  instruments (#35).

  The union is ordered by (recorded_at as an INSTANT, device, position), which
  is total - two devices rebuilding the same file set produce byte-identical
  output. `CLOCK_SKEW_TOLERANCE` now compares against the writing device's own
  history only: actor-per-file dissolves the skew problem rather than solving
  it, because a lagging phone never reads the laptop's stamps. A device whose
  OWN clock jumped backwards is still refused.

  **Duplicate capture** - one workout pulled by both devices - is reported by
  `duplicate_captures()` and converges to one row in the DERIVED numbers, at
  build rather than at write, so a device that was offline still converges.
  The record keeps both lines: both are legitimate appends and an append-only
  file cannot un-append.

  `vitai init` now stamps a `.gitignore` covering `derived/` and `artifacts/`.
  The database is rebuildable in seconds, and a synced SQLite file is corrupt
  rather than merely stale - its main file and WAL must stay consistent.

### Added
- **A deterministic medical-boundary lint over the public surface** (#117).
  `scripts/boundary_gate.py`, blocking in CI beside the personal-content gate.
  #110 fixed `safety.py`; a boundary that lives only in a document regresses
  the first time somebody writes a helpful string, so this is the mechanical
  complement.

  It fails on care directives ("see a doctor", "seek medical attention") and
  on medical-purpose claims ("detects a disease"). Both are the same mistake
  in different grammar: one asserts an instruction the tool cannot help anyone
  carry out, the other asserts a medical purpose, and under FDA general
  wellness and MDCG 2019-11 the trigger is the claim rather than the
  technology.

  **The allowlist is hashed sentences keyed by file, never file paths.**
  Sparing a file would spare whatever is written into it next; sparing a
  hashed sentence means an edit re-triggers review. The acute tier is read
  from `safety.ACUTE` directly, so the two guards cannot drift apart.

  Deliberately narrow. `flag`, `spot` and bare `condition` are not matched:
  this codebase says "red flag" and "precondition" constantly, and a lint that
  cries wolf gets deleted - after which it catches nothing at all.

  Seven sentences in `docs/` are recorded as exemptions with reasons: three
  because the doctrine cannot be written without quoting the rule, and four
  as visible DEBT - they describe routing that #110 removed, so they are now
  false as well as over the line, and #116 owns the rewrite.

### Changed
- **The engine states the observation and refuses to prescribe; it no longer
  routes anybody to care** (#110). `safety.py` was doing three things under one
  heading: refusing to prescribe, routing the user to a clinician, and holding
  an appointment open as a tracked item. The second and third are gone.

  Nine of thirteen `MESSAGES` ended by naming a professional to go and find.
  That is care NAVIGATION, and it was wrong twice over. As design: an
  instruction the tool cannot help anyone carry out is an open item the record
  owner cannot close, re-raised at every review until it is noise. As a claim:
  under FDA general wellness and MDCG 2019-11 / MDR Annex VIII Rule 11 the
  trigger is the CLAIM, not the technology, and those strings were the
  strongest evidence that vitai asserts a medical purpose. The engine does not
  need them to be safe.

  Every constant now states what was observed and what vitai will therefore
  not do. No addressee, no imperative aimed at obtaining care.

  **The acute tier is kept, verbatim and structurally separate.** Chest pain
  and syncope retain "call emergency services", because that is an act the
  person can perform immediately, alone, at any hour - unlike an appointment.
  The list is closed, and a test hashes the strings the runtime actually reads
  so the tier cannot erode a word at a time.

  **Every level exits on the record.** `clinical_hold` used to clear only when
  a clinician had reviewed the athlete, which is not a gate but a wall. And
  both red-flag paths iterated the raw rows, so a flag fired forever - marking
  the episode resolved exited nothing. `LEVEL_EXITS` states the exit per level,
  and a test asserts the behaviour rather than the sentence.

  **An appointment is not a visit.** `kind: visit` records something that
  HAPPENED; a row dated after the line was written is a plan, and vitai does
  not own the record owner's plans for their own body. Measured against the
  record's own transaction time rather than `date.today()`, so validation stays
  deterministic.

  **A standing Tier-1 disclaimer** in `status` and the escalation banner. It
  carries the weight precisely because it never fires.

### Added
- **Reads over sets, and the numbers that refuse to be computed** (#100,
  increment 4 of #59). `vitai sets progression | working-weight | volume |
  tonnage`, plus the matching API methods. The arithmetic is ordinary; half
  the increment is refusals.

  Every load resolves to a SCALE: `mass` (kilograms, comparable anywhere),
  `stack(machine M)` (a pin number, comparable within M only), and
  `ordinal(machine M)` (a resistance level, comparable within M and only as
  ORDER). A stack number and a mass are both spelled in kilograms and are not
  the same kind of thing, which is exactly why summing them looks reasonable
  until someone acts on the total.

  **Tonnage has no grand total, and no `total` key at all** - absent rather
  than `None`, so a consumer asking for one raises instead of rendering zero.
  Per-scale subtotals, with a finding saying they do not add up.

  **A set with `failure: null` is never evidence of a maximum.** Null means
  nobody said, `volitional` means reps were left, and reading either as a
  limit is what gave a real record a max several reps below the truth. Such a
  set still counts fully as volume: the work happened.

  **Bodyweight resolves against the weight trend, or declines.** No weight
  data near the date and the derivation says so rather than assuming a mass.
  A resolved bodyweight tonnage is MODELLED (P3) and gets its own bucket -
  summed with barbell kilos it would dominate the figure with a number nobody
  weighed, and then move when the athlete cuts.

  **Progression is machine-scoped**, and an ordinal difference is reported in
  STEPS, never as a ratio: the scale is not established to be linear or to
  have a zero.

  Every refusal is a named finding carrying the rows. A derivation that
  quietly skips what it cannot handle produces a total that is wrong in the
  direction of looking fine.

### Added
- **`red_s` retired from the code, and two boundary guards that would have
  caught it** (#115, #110). Renamed to `low_energy_availability` throughout,
  and the message keyed `red_s` is DELETED rather than renamed.

  It named a syndrome outright ("a low-energy-availability pattern (RED-S) ...
  this is the syndrome"), which is class (c) of the medical boundary, and it
  survived #133's rewrite for two independent reasons. The boundary test
  asserted class (d), care directives, so it looked for the wrong thing. And
  the string was UNREACHABLE: `_escalation` reads `MESSAGES[trigger]` and
  nothing ever emitted `trigger == "red_s"`, so no behavioural test could see
  it either. Its live successor `clinical_hold` describes the same pattern
  without naming it, which is why deleting rather than renaming is right.

  Two new guards. One asserts no message the athlete READS names a condition,
  scoped to messages on purpose: describing an observable state is fine and
  `clinical_hold` does it, while source comments citing the literature to
  justify a threshold are engineering rationale. The other asserts the module
  never claims to WATCH for anything, over comments as well as strings, and it
  found a live one: a section header read "it is the engine's job to watch for
  it rather than the athlete's". Monitoring for a named condition is the
  strongest assertion of a medical purpose a file can make, and it is worse in
  a comment, which reads as the authors describing what they built.

  Also asserts every `MESSAGES` key is reachable. An unreachable entry in a
  constants table looks like coverage in review and is worth nothing at
  runtime, which is the worst combination available.
- **A knowledge cutoff: what the record said THEN** (#130). `Vitai(root,
  as_of=...)` and `load(..., as_of=...)` reconstruct the record at an instant,
  using only lines whose `recorded_at` precedes it.

  `clocks.py` promised exactly this in its own docstring, telling "what the
  record said on 30 July, as we understood it then" apart from "as we
  understand it now". The record was bitemporal in STORAGE and unitemporal in
  EVALUATION: `recorded_at` was stamped rigorously, refused from callers and
  monotonic by construction, and every single use of it was writing it or
  ordering by it. Nothing ever filtered on it.

  It is not the question `goals_in_force(date)` answers. That is valid time,
  which goals APPLIED on a date using everything known now. This is
  transaction time: what was KNOWN then. A month of degraded data whose cause
  is filed six weeks later reads unexplained under a cutoff inside those weeks
  and explained after, which is the difference between judging a decision and
  judging it with hindsight.

  **The filter runs before the supersedes walk**, and that order is the whole
  correctness argument: a correction written after the cutoff had not been
  made yet, so applying it would produce a state the record never held.

  An unstamped line survives every cutoff, following the clocks canon's own
  rule that absent sorts before present: a legacy line lacks a transaction
  time because it predates the clock, not because it was written later. A
  naive `as_of` is refused, because a cutoff read in the local zone returns
  different records on different machines.
- **An exercise registry, and restrictions that can finally see a set** (#98,
  increment 2 of #59). Two defects, one registry.

  `sets.exercise` was free text, so `push-up`, `pushup` and `press-up` were
  three exercises and no query grouped them. And a restriction could not be
  checked against a set at all: a clinical gate of `pattern=hinge region=hip
  load=loaded` had nothing to match, so the coarse `restricts: strength` gate
  was used instead - and it blocked push-ups. That is collateral damage caused
  *precisely* by the precise gate having nothing to check.

  `semantics/exercises.toml` carries 108 movements whose axes are BORROWED,
  never invented: `pattern`, `load` and `plane` from `restrictions.toml`,
  `region` from `body_sites.toml`. A set inherits them, and the gate the
  clinician described becomes mechanically checkable - a loaded hip hinge is
  blocked, a squat and a push-up are not.

  **Post-coordination throughout.** `incline_dumbbell_bench_press` is never an
  entry; equipment, grip and angle are #99's axes. `pattern` and `region` are
  both LISTS, because a thruster is a squat and a press, and a deadlift loads
  hip, hamstring and lower back - a restriction naming any one of them catches
  it.

  **The set overrides the registry.** Registry `load` is what usually happens;
  the set's `load_type`, or a stated `load`, is what did. An exercise done
  both ways states no default, and a restriction keyed on load abstains until
  the set says.

  **An unknown exercise ABSTAINS**, and so does a restriction keyed on an axis
  the exercise cannot carry, and so does one that parsed to nothing. Never a
  silent `allowed`: a missing gate means the athlete trains on an injury
  nobody flagged, and nothing in the output ever says so.

  Seeded from free-exercise-db (Unlicense, safe to vendor); entries written
  here say `source = "curated"`. Nothing from wger, whose exercise data is
  CC-BY-SA. Lateral raises and hip abduction/adduction are deliberately absent
  until #58 adds the patterns that describe them.
- **`meal` is required on a meal item.** `item` was required and `meal` was
  not, so two items of the same name on one date - two coffees, or one
  ingredient in two unnamed snacks - shared an identity, and a `supersedes`
  naming either was ambiguous. Required now for the same reason `set_index` is
  on `sets`: a row nobody can name is a row nobody can correct. It costs one
  word, and an unnamed snack is `meal: "snack"`.
- **An itemised meal estimate, with a range that never collapses** (#96). A
  photograph of a meal produces an ITEMISED estimate, never one confident
  number. Every app that does photo estimation hands back a total, and the
  total is the least defensible part of the answer: it cannot be corrected,
  cannot be questioned, and cannot say which part it is unsure about.

  `data/meals.jsonl` holds one row per INGREDIENT - a gram estimate, a gram
  RANGE, and the per-100 g composition figures as the food table gave them,
  beside the name of that table. Energy and macros are derived from the
  quantity and never stored, so correcting a portion re-prices the item.

  The split comes from what a photograph can and cannot do. It settles
  COMPOSITION well - "crispy chicken" read as breaded at ~280 kcal/100 g was
  corrected to crispy-skinned thigh at ~240 by looking at the skin. It settles
  PORTIONS badly - with no scale reference, 30 g of chicken either way is 72
  kcal, and no amount of model effort on the pixels recovers that. So asking
  is a first-class step: `vitai meals` lists the unsettled quantities as
  questions, and names which item dominates the range, because "600, and 70 of
  the 90 is how much chicken" tells the athlete which single question would
  collapse it.

  **There is no confidence field and there will not be one.** No corpus of
  photo-estimated meals scored against weighed truth exists, so a number there
  would be a decimal point pretending to be calibration (P4). The range is the
  confidence statement, and a total is never rendered without it.

  **A meal is not a day.** `stated-in-chat` outranks `mfp-export` in the
  precedence ladder, so writing a meal estimate into `daily.kcal_in` would
  displace the athlete's own itemised whole-day entry when it arrived - a
  model's guess beating the athlete's own record, which is #88 one domain
  over. Meal rows never feed `kcal_in`; when both exist the pair is REPORTED
  against the canonical day, because a partial day and a whole day are
  different quantities and neither supersedes the other.

  A stated intake buffer lives in `[preferences] intake_buffer_pct` - policy,
  applied to every estimate or to none, and kept decomposable back into
  estimate and policy. This ships no food data and takes no position on which
  composition table to use: that is a licence question (USDA FoodData Central
  is public domain, Open Food Facts is ODbL share-alike) and it is deliberately
  left open.

  `IDENTITY_KEY` now accepts a tuple, because every item of one plate shares a
  date and a source - so a `supersedes` correcting the chicken retired the
  olives and the tomato with it. That is the #43 defect in a new dataset, and
  in the one whose premise is that the item is the unit of estimate: it has to
  be the unit of correction too.
- **`adduction` and `abduction` on the pattern axis** (#58). Found live, on a
  machine the athlete was about to load. Twelve patterns and none of them
  named adduction, so a seated hip-adduction machine - about as direct a
  loaded hip movement as a gym contains - could not be described by the
  restriction system that exists to protect a hip.

  The coarse `restricts: strength` projection caught it. That is luck rather
  than design: had the restriction been written narrowly, which is exactly
  what post-coordination encourages, the precise form would have been the only
  one and would have said nothing.

  **`plane = frontal` is not a substitute**, and using it as one is the
  mistake this avoids: it would also catch abduction, lateral lunges and side
  planks, a far wider ban than any clinician said, and over-restriction is its
  own harm. A plane is where a movement happens; a pattern is what it does.

  Grounded rather than invented - the registry already carried `flexion`,
  `extension` and `rotate` from standard planes-of-motion terminology, so this
  finishes a vocabulary that was half adopted instead of starting a second one
  (G85).
- **A content-addressed artifact store** (#80). The evidence behind a value
  was discarded the moment it was read: an athlete photographs a gym console,
  a model reads the numbers off it, the numbers enter the record and the
  photograph is stored nowhere. So the richest single-instrument reading in a
  record was also the only one that could never be re-checked - and `#79`'s
  capture axis can say a value was *transcribed* without anything being able
  to say transcribed *from what*.

  `data/artifacts.jsonl` is a manifest (hash, media type, size, why it was
  kept); `artifact` on `weight`, `daily`, `sessions` and `measurements` cites
  a row in it. The reference is a content address (`sha256:...`) rather than a
  path, so it cannot drift from the row citing it, a filename is a validation
  error, and storing the same bytes twice stores one copy. One artifact can
  back several rows, which is why the manifest is its own dataset rather than
  a column - a console photograph carries distance, pace, power and stroke
  rate at once.

  `vitai artifact ls | get | verify`. `verify` checks both directions: PREMIS
  fixity (the stored bytes must hash to their own address) and referential
  integrity (a value whose evidence is gone). It fails on a promise the record
  is no longer keeping - and `not_erased`, an artifact the manifest says was
  deleted whose bytes are still on disk, is one of them: the athlete has no
  other way to find out. An orphan, a not-yet-cited artifact and a deliberate
  deletion are printed and do not fail a build, because a check that cries
  wolf over disk hygiene teaches the athlete to ignore the one finding that
  matters. `artifact get` requires `--out`: where personal bytes land is not
  something a default should guess.

  **Removed is not missing.** Deleting an artifact appends a tombstone with a
  reason rather than rewriting the row that cites it: a retention decision and
  a data loss are completely different facts and the record has to keep them
  apart. A removal without a reason is a validation error.

  The backend is behind an interface and the default is a local directory. The
  mechanism is public; the artifacts are personal data. Nothing here uploads,
  syncs or attaches - storing an artifact is not consent to transmit it - and
  no artifact, manifest row or hash of a real one appears in this repository,
  including in the tests, where the bytes are synthetic.
- **`sets.jsonl`: the set is the atom** (#97, increment 1 of #59). Three facts
  had nowhere to live, and all three were being reconstructed from prose.

  **A failed attempt.** `73 FAILED` after `66x12` is the most informative set
  of a stack progression - an attempted load that could not be completed - and
  there was no field for it. `reps_attempted: 1, reps_completed: 0` says it,
  and it is a different fact from a set never attempted, which is the absence
  of a row.

  **Whether a set was taken to failure.** Push-ups of 13, 12, 10 against a
  stated max of 12 read as maximal and were not: set 2 held 92% of set 1,
  where genuine failure leaves 55-70%. `failure` is three states -
  `technical`, `muscular`, `volitional` - because "to failure" is ambiguous
  across all three. **Null means UNSTATED and must never be read as maximal.**

  **What kind of number a load is.** `load_type` is a closed enum:
  `external` is a mass; `bodyweight` means the load IS the athlete, and gets
  lighter as they cut, for reasons unrelated to strength; `bodyweight_plus`
  is added mass; `assisted` subtracts; and `machine_stack` is a **pin number,
  not a mass** - 66 on two machines is two different loads, so it carries its
  machine and is never rendered in kilograms.

  `set_type` goes in `semantics/set_types.toml` rather than in code, the
  opposite call from `load_type` and for the opposite reason: methodology
  coins set types faster than any sample, while "how does this number resolve
  to a resistance" has no sixth answer to discover.

  `vitai sets [--on DATE] [--json]` and `Vitai.sets()`. `IDENTITY_KEY` now
  accepts a tuple, and `set_index` is REQUIRED - a tightening of the spec,
  because a set nobody numbered shares an identity with every other unnumbered
  set of that exercise, so a correction naming one would retire them all.

  `rpe` widens from integer to numeric wherever it appears, `sessions`
  included: half points are standard on the RIR-anchored scale. Strictly
  looser, so nothing that validated before stops validating.
- **A value can say it was never measured** (#49, #88). The orthogonal
  question to origin and capture: those say which instrument and how it
  reached us, this says whether the number was observed at all.

  A model output arriving in a field whose name and type imply measurement is
  invisible by construction. `kcal_out: 1728` on two different dates is BMR
  modelling because the tracker was not worn - and **five separate instances
  turned up in one import**, which is what makes it a rule rather than three
  patches. `modelled` names the FIELDS on a row that are model outputs,
  because the distinction is per-field: one row can carry a measured step
  count and an estimated burn.

  The same defect applies to a categorical label. **1,093 of 1,502 session
  types in one live record were a vendor classifier's guess**, and nothing
  distinguished them from the 409 the athlete asserted - so any analysis
  grouping by `type` was silently mixing attestations with model output at
  unknown confidence. `type_source` records how a label was arrived at.

  A RED-S screen run on an estimated burn now **declares its basis** rather
  than declining. Refusing would remove a false positive by creating a
  silence, for every athlete whose tracker models their burn - which is most
  of them - and in that tier silence is the dangerous direction.
- **A capture axis: how a value was acquired** (#77, #78). Three questions
  were answered by one string and two of them had no field at all: what
  observed it (`origin`, shipped in #51), HOW it got here, and what evidence
  survives (#80, still to come).

  The athlete's framing is the issue: *"me telling narratively what the rower
  said is different from me taking a picture of it, or having a Bluetooth
  connection and seeing the data that way, or the app importing it through a
  connector."* Those four share ONE origin - the same console showing the same
  number - and have completely different error modes. So `capture` is a
  property of the ACQUISITION EVENT rather than of the chain: a photo-read and
  a BLE-read of one console on one evening are two claims with one origin and
  two captures.

  **The ordering is not a quality ranking.** `ble` has no reader in the loop
  and no durable artifact; `photo` has a reader in the loop but the evidence
  survives and can be re-read. Different virtues, and a query can ask for
  either. Grounded in FHIR `Observation.method`, which is deliberately
  separate from `Observation.device` and `Observation.performer`.

  `trust_ceiling` gains a `transcribed` level, taken as the weakest of the
  acquisition and the chain: a photograph of a console read by a model is an
  inference over an artifact, not a reading of an instrument, and must not
  present as device-measured.
- **`sessions` finally carries the provenance chain.** `origin`, `path` and
  `origin_evidence` landed on `weight`, `daily` and `measurements` in #51 and
  were never extended - and sessions is exactly where multi-instrument claims
  collide.
- **A catalogued source registry** (#79). Source names were free text, so a
  console meant whatever the writer typed that day, and nothing knew a scale
  cannot observe distance. `semantics/sources.toml` catalogues 49 instruments
  with a `kind` (Google Fit's `Device.type` axis, extended) and aliases, so
  `Polar Pacer Pro`, `polar-pacer-pro` and `PacerPro` are one thing.

  It answers `provenance.toml`'s own "roles, not vendors" rule rather than
  contradicting it: that file classifies what KIND of hop something is, this
  one normalises WHICH instrument. And it avoids the G85 failure the same way
  `session_types` did - an unrecognised source RESOLVES to `other` carrying
  its kind, never errors, and there is deliberately no `other-console` or
  `other-wearable` to multiply the catalog by the kind axis.

  **Nothing personal lives in it.** A source named for someone's own gym or
  their own spreadsheet resolves to `other`, which is what the catchall is
  for, and the checks work on the kind so nothing is lost by that.

  The catalog implies no precedence. Which instrument to believe stays in the
  athlete's config, because a figure stated in chat outranks a vendor channel
  in one record and would not in another.
- **A claim its instrument cannot have made is a validation finding.** A
  scale reporting distance, a rowing console reporting sleep: not resolution
  ties to adjudicate but rows that cannot be true as written.

  Held as a **deny list at the kind level**. It was first written as a
  per-instrument list of what each device CAN observe, and that was wrong in
  the direction that costs something - an Oura ring does report calories, a
  hand-typed row can carry a heart rate read off a watch, a relaying app
  carries whatever it received, and watch models differ. Every one of those
  was flagged by a whitelist that merely forgot them. An omission from a deny
  list produces silence instead.
- **`track`, `activity_id` and `activity_source` on `sessions`** (#43). The
  link from a session to the file that recorded it lived in a prose note and
  was recovered by regex - unqueryable, unvalidatable, and silently broken by
  any change of wording. Two fields rather than one, post-coordinated: `track`
  is a LOCAL ARTIFACT (a repo-relative path, what `vitai route` reads),
  `activity_id` is an EXTERNAL IDENTITY (what dedupes a re-run import). They
  have different lifetimes - an archive can be re-laid-out without the id
  changing, and an id is meaningless off-platform while the file stays
  readable. `activity_source` names who ASSIGNED the id, which is not
  necessarily who recorded the activity (#35).

  `vitai route --session <activity_id|date>` and `Vitai.session_route()`
  resolve the track from the record, so route geometry can rebuild from
  `data/*.jsonl` like everything else in `derived/`.

  An absolute path is a validation error - it leaks a username and a machine
  layout into a portable record, and breaks a rebuild anywhere else. A
  dangling pointer is an ADVISORY and never fails a build: the session is the
  fact, the track is an attachment.
- **The record is bitemporal: `recorded_at` on every dataset** (#37).
  Transaction time - when a line was *written* - alongside the valid time
  `date` already carried. Found on a live record: two `goals` rows shared an
  effective date, one superseding the other, and **nothing in the data said
  which won**. Resolution fell back to file order, which is real information
  right up until a sort, a reformat, a merge or a git conflict resolution
  rewrites it. An ordering a formatter can change is not an ordering.

  Putting a time on `date` would have been the wrong repair: it forces the
  athlete to state something they never meant - "I decided this at 14:32" is
  a fact about a keystroke - and it still would not sort, because **valid
  time is not monotonic and must not be**. A line written today about a
  decision made last week is legitimately backdated. Transaction time is
  monotonic by construction and never authored by a human, which is exactly
  what a tie-break needs (Snodgrass: valid time vs transaction time).

  The migration is a **read no-op**: absent sorts before present, so a file
  of unstamped rows resolves in exactly the order it always did.
- **`append_many` / `Vitai.append_many()` and JSONL on `vitai append`'s
  stdin** (#44). The primitive bulk import actually wants: the file is read
  once to find where the clock got to, every row is stamped strictly past the
  one before it, every row is validated before any is written, and the batch
  lands in a single open. Looping over the single-row form re-parses a growing
  file per row - 5,425 rows take 0.11 s as a batch against 2.5 s for 1,000 in
  a loop, and the gap widens with the import. A batch containing one bad row
  writes nothing at all, rather than leaving a caller to work out how far it
  got.
- **`vitai append` / `Vitai.append()`** (#37). The write half of P9, and the
  reason the clock is trustworthy rather than aspirational: every row in this
  record is written by a hand-rolled script, and a field callers must
  remember to set will be absent exactly when two rows land on the same date,
  which is the only moment it was needed. Append stamps `recorded_at` and
  `_gen`, fills absent keys with null, **refuses a caller-supplied
  `recorded_at`** - a clock you can write is not a clock - and validates
  before writing, because an append-only file cannot be un-appended.
- **`weight.measured_at`** (#37): observation time, HH:MM local. Body mass
  swings about a kilogram between morning-fasted and evening, so an
  unrecorded drift from evening to morning weigh-ins manufactures a week of
  apparent progress. Absent stays absent - the engine never infers a probable
  weigh-in time, it says the rate could not be checked.

- **Events: the dated fixtures a plan is built backwards from** (#24, G86).
  A new `events` dataset - a race, a scan, a wedding, a competition weigh-in.
  An event is not a milestone: a milestone is a fraction of a target the
  engine DERIVES from progress already made, while an event happens whether
  the athlete is ready or not and is owned by somebody else. Two concepts had
  one word and only the derived one existed. Goals anchor to an event, and an
  immovable fixture makes the goal's deadline hard by derivation rather than
  by re-declaring it. `vitai events` + `Vitai.events()`, and a "Coming up"
  countdown in the weekly rollup.

  The vocabulary is a registry (`semantics/events.toml`), post-coordinated on
  two axes: `kind` (what sort of fixture) from RFC 5545 VEVENT, and
  `priority` (how much the plan bends for it) from Friel's A/B/C.
- **Attested-only goals** (#24, G86/G83). `verification` says who can ever
  settle a goal: the engine (`measured`), another app (`external`, the G19
  case) or *nobody* (`attested`). "I want to enjoy running again" has no
  metric and never will, and the schema REQUIRED one - so the thing athletes
  say they would be saddest to lose in five years had nowhere to live at all.
  The engine now holds a goal it can never verdict: it tracks it, surfaces
  it, asks about it, and takes the athlete's word as the only evidence there
  will ever be. An attested goal is never scored and never rendered at 0%.

### Fixed
- **An unattributed row lost every contest it entered, silently** (#73). A
  row with no `source` ranks last in the precedence ladder - right for
  genuinely unknown provenance, wrong for the commonest cause, which is a
  writer that forgot to stamp it.

  **The asymmetry is the point.** A vendor channel always stamps itself,
  because a machine wrote it. A hand-entered figure, a chat-stated number, a
  note typed on a phone are the rows a human forgets - and they are exactly
  the rows the ladder is written to rank ABOVE vendor channels. So the
  omission inverted the ladder precisely where it matters, twice in one live
  session, both times worth over 1,000 kcal/day.

  Three things now report it. `vitai validate` flags a source term present in
  data but absent from the ladder, catching the cheaper instance at the door -
  and it found five in this repo's own demo on its first run, including a
  first-hand `hand` reading sorted below two relayed vendor channels.
  Resolution records EVERY discarded claim rather than only the runner-up, so
  a resolved value can say what it beat. And an `unattributed_claim_lost`
  tripwire fires when a claim carrying no source was discarded with a
  different value.

  **Ranking is deliberately unchanged.** Whether unattributed should sort
  last at all is a real question, and changing it silently would be its own
  inversion; what was unacceptable was that it happened with no trace.
- **`recorded_at` is now strictly monotonic, so bulk-appended rows can
  actually be ordered** (#44). Importing 227 readings through the helper #37
  added produced **one distinct stamp across all of them** on this machine -
  a second is an eternity in a write loop, and the monotonicity check admitted
  equal when equal is the failure case. A tie orders nothing, which was the
  field's only purpose.

  The stamp is now a hybrid logical clock at microsecond resolution:
  wall-clock time whenever it has genuinely moved on, otherwise one tick past
  its predecessor. Under load it drifts microseconds ahead of true time, which
  is the right trade - an ordering that is occasionally a few microseconds
  optimistic is strictly better than one that does not exist. A wall clock
  more than a minute BEHIND the last stamp is refused rather than clamped,
  because that is a wrong clock rather than a coarse one.

  Bulk import is not an edge case here, it is how rows arrive: every source so
  far lands as hundreds of rows in a tight loop. It also blocked #37's own
  migration, since backfilling offsets across 172 session rows is itself a
  bulk write.
- **A repeated `recorded_at` is now reported whatever the rows are dated.**
  The tie check keyed on `(identity, date, recorded_at)`, so a bulk import
  spanning 227 different dates stamped every row identically and `vitai
  validate` called the file valid. That narrow check is what let the defect
  hide. A serial appender cannot write two rows at one instant.
- **Transaction time is compared as an INSTANT, not as text.** Two stamps
  written either side of a timezone change were ordered by wall clock, since
  `+02:00` sorts after `+00:00` as a string regardless of which came first -
  the #38 mistake, one clock over.
- **A record holding both naive and offset-aware `start_time` no longer
  crashes the build** (#38). `_same_activity` raised
  `TypeError: can't compare offset-naive and offset-aware datetimes` the
  moment both shapes coexisted - and the schema's own validator example shows
  an offset while the Polar connector wrote naive, so **following the
  documentation broke the engine**. That is the worst version of this bug: it
  punishes the correct behaviour.

  It also blocked its own repair. Offsets cannot be backfilled row by row,
  because from the first converted row until the last the record holds both
  shapes and is unbuildable - so the comparison had to tolerate the mixture
  before any migration could begin.

  **No offset is guessed.** Two naive values share a frame by construction and
  stay comparable; two aware values compare as instants across differing
  offsets; a MIXED pair is declined and reported, and the weaker shape test
  decides. The obvious repair - lend the aware row's offset to the naive one -
  fails on the commonest pairing there is, since platforms routinely emit UTC
  beside a connector writing naive local time, and a `+00:00` lent to a
  `+02:00` row lands two hours from where it happened while still looking like
  a clean instant. A misplaced instant is worse than an absent one.

  The undecidable case is reported as `incomparable_timestamps` rather than as
  a shape-only merge: both rows *have* a `start_time`, and telling the athlete
  to record one they already have would send them nowhere. `vitai validate`
  reports a mixed record as an ADVISORY, never an error - those rows are
  history, not mistakes.

  GPX fix times are now read as UTC when written without a designator, which
  is what GPX 1.1 specifies rather than a guess, so one track carrying both
  spellings cannot raise either.
- **A weight rate no longer prints an actionable verdict it cannot support**
  (#37). When the weigh-in times behind a rate are spread widely enough that
  the diurnal drift alone accounts for it, the rollup reads `NOT READABLE -
  weigh-in times vary too much` and `verdicts` emits `nodata`, both alongside
  the number and a caveat quantifying the spread. Previously the demo record
  rendered `SLOW - check logging` off a rate that 12.4 h of weigh-in spread
  could fully explain - advice to cut harder, derived from a clock. P3:
  confidence never launders upward, and a crisp verdict on an unreadable
  number is exactly that.

- **A moved SOFT deadline is no longer flagged as goalpost-moving** (#24,
  G86/G20). `deadline_kind` (`hard` | `soft`) on goals. A race date cannot be
  moved, so pushing it is a retreat from something real; a date the athlete
  invented is a direction of travel they may revise at no cost to anyone, and
  flagging that accuses them of gaming a commitment nobody else ever held
  them to. A live record was carrying exactly that false positive.

  Where hardness is UNKNOWN - a goal written before the field existed - the
  engine records that the deadline moved and says it does not know whether
  that matters, rather than guessing in either direction. The push is never
  hidden; only the accusation is withheld. A loosened TARGET is still flagged
  regardless, so hardness cannot be used to launder a genuine retreat.
- **A goal correction is no longer counted as churn** (#26, G31). `goals`
  gains `change_kind` (`change` | `correction`), which `thresholds` has had
  since G31 and which matters more on goals because goals are what
  `plan_churn` analyses. A correction asserts the retired line was never a
  real intention; counting it manufactures a plan-stability problem that does
  not exist. A correction must carry a `reason` - unexplained, it cannot be
  told from a quiet retreat wearing the right label.
- **A goal scoped to `weight` or `measurements` reports unknown progress, not
  0%.** `GOAL_DATASETS` widened in #18, but the contribution engine only
  iterates `daily` and `sessions`, so a weight goal silently rendered as
  `0/78 (0%)`. Telling an athlete who has lost 3 kg that they are at 0% of
  their weight goal is the G69 harm in a new place. Reaching a target from a
  starting point is an APPROACH, not an accumulation, and modelling it needs
  the goal KINDS of G62; until then the engine says it does not know, which
  is both true and safe.

### Changed
- **Vocabularies are curated registries, not Python sets** (#18, G85).
  `semantics/session_types.toml` and `semantics/restrictions.toml` join
  `body_sites.toml`, loaded by a new `vitai.vocab`.

  The root cause, stated plainly: *a vocabulary in code can only be extended
  by a developer, so it can only ever contain what the developer had seen.*
  `gym_a` and `gym_b` - one athlete's Strength A and Strength B days - shipped
  in a public MIT engine, while cycling, swimming, rowing, hiking, yoga,
  climbing, skiing and every team and racket sport collapsed to `other`.
- **Restrictions are post-coordinated.** `ACTIVITY_CLASSES` mixed a scope
  quantifier, a setting, a loading modality, anatomical regions and specific
  activities in one flat list, and could not express two real clinical gates:

  | The clinician said | The old vocabulary |
  |---|---|
  | No loaded lumbar flexion | no value came close |
  | No loaded hip work, squats still fine | `lower_body` bans the permitted squats |

  Both sat in a live record with `restricts: null` and a RESTRICTION NOT
  ENFORCEABLE marker, because a wrong gate is worse than an unenforced one -
  so an athlete with an active injury gate got `no active safety escalations`.
  A new `restriction` field (gen 3) says it on separate axes:
  `pattern=hinge region=hip load=loaded`. An absent axis means "any"; a squat
  is `pattern=squat`, so the hip rule leaves it alone. `region` reuses
  `body_sites.toml` wholesale, sites and regions and aliases - "lumbar"
  resolves to `lower_back`.
- **`Vitai`/`safety` gained `is_movement_gated`** for "may I do a hip thrust
  today", alongside `is_gated`'s "may I run today".
- **Session-to-gate-class mapping moved into the registry.** The hardcoded map
  gave `gym_a` and `gym_b` identical class sets, so the two labels carried no
  gating information at all - which is its own evidence they were programme
  names rather than a taxonomy.
- **A goal can be scoped to `weight`** (folded in from #24): `dataset` accepted
  only `daily`/`sessions`, so a weight goal - the most common goal in the
  domain - had nowhere to point.
- `docs/vocabularies.md` records the rule and the sweep.

### Fixed
- The rollup counted strength sessions with `startswith("gym")`, which would
  have silently zeroed the weekly column on any rename. No test covered it;
  one does now.

### Deliberately not done
- **`gym_a`/`gym_b` are retired, not deleted.** A value-level retirement
  (`KEY_RETIREMENT` works on keys, not values): they stay legal forever, stop
  being offered, and resolve forward to `strength`.
- **`severity` keeps `red_flag`.** It does mix a magnitude scale with a
  routing decision, but it is what the safety asymmetry rests on and what the
  ingest skill instructs writing. Its own change, not a side effect here.
- **`restricts` survives as a coarse projection**, so no read-model consumer
  breaks.
- Seven non-safety vocabularies (`CONTEXT_MODES`, `SETTINGS`, `WEATHERS`,
  `MEASUREMENT_KINDS`, `SESSION_CONTEXTS`, `PROVIDER_TYPES`, `FEELS`) are
  still Python sets with their defects documented. Next slice.

Safety layer: the persona guardrail fixtures now hold (issue #12). All eight
`xfail(strict=True)` specifications flip to passing.
### Added
- **`vitai check` - adjudicate a stated value against the record** (#15).
  An LLM coach narrates numbers, and its narration is as untrustworthy a
  source as any vendor estimate. P1 says sources are claims the engine
  adjudicates; that rule had never been applied to the coach's own sentences.
  `check` answers **CONFIRMED / REFUTED / NOT-IN-RECORD** with the values and
  the delta, and exits 1 on a refutation so a skill can be held to the record
  mechanically rather than on its honour.
  - It checks the claim against BOTH the day's total and each individual row,
    because "I ran 8k" may mean one 8 km run or two 4 km runs - and says which
    reading makes it true rather than picking one and being confidently wrong.
  - **NOT-IN-RECORD is a distinct verdict.** Absence cannot refute a claim: a
    day with nothing logged does not prove the run did not happen, and
    answering REFUTED there would be the engine overreaching in exactly the
    way it accuses the model of.
  - Tolerance is a config value (`[preferences] check_tolerance`, default 2%),
    not a constant.
- **`vitai day` / `vitai window` / `vitai ramp`** - read-only factual dumps
  that exist so a number is never stated from memory. `day` shows what the
  canonical row is hiding, including claims that were merged away. `window`
  totals over N **calendar** days, since a window that skipped the empty ones
  would report a fortnight as a week. `ramp` prints week-on-week volume with
  its **base-size caveat attached** - a ramp percentage over a one-week base
  is not a trend, and that maturity signal (G27) is engine-owned rather than
  something each caller has to remember to add.
- All four land as CLI **and** `Vitai.*` methods in the same change (P9).

### Fixed
- **Resolution no longer false-merges repeated similar activities** (#14).
  Shape-matching - same type, similar duration, similar distance - was being
  used as a proxy for identity when `start_time` was absent. For repeated
  activities it is a proxy for ROUTINE instead: a dog walked three times a
  day, a commute each way, sets of the same length. Anyone with a habit
  generates near-identical shapes by design, and the resolver was merging
  them. A real record reported **1.39 km** of walking on a day when **6.26 km
  across four walks** had happened, and nothing surfaced it.

  This is the mirror of double-counting and worse: double-counting inflates a
  number visibly, a false merge silently deletes data and leaves a plausible
  canonical row behind. Three changes:
  - A shape match now also requires **disjoint sources**. A genuine
    cross-platform duplicate has a signature shape does not carry - two
    different systems claiming one physical event. Two claims from the same
    source with the same shape are far more likely to be two real events, and
    an identical re-emission from one connector is a connector bug that
    exact-duplicate detection (G26) already covers.
  - More than two shape-alike, timestamp-less claims of one type on a date is
    a **routine, not a duplicate set** - none are merged.
  - Every shape-only merge, every near miss, and every routine left unmerged
    now emits a **visible tripwire** saying what was decided and that
    recording `start_time` resolves it positively. Previously a merge was
    invisible outside the `claims` table.

  `_same_activity` returns three outcomes rather than two -
  `match | possible | distinct` - so an uncertain pair is a refusal to decide
  rather than a weak merge.
### Added
- **Gate preconditions** (#19). A rehab plan says *"5 gentle hops on the right
  leg before each run; pain in the groin means do not run that day"* - a gate
  CONDITIONAL on a test performed that morning. The engine could say
  restricted or not restricted, so the whole instruction had to sit in a
  `note` where no rule could read it: the prose problem G28 exists to solve,
  reappearing one level down. A medical episode may now carry a
  `precondition` naming a daily check, with results in a new `checks.jsonl`.

  A preconditioned gate has **three** states, not two:
  - `cleared` - today's check passed; the restriction lifts, for today only;
  - `blocked` - today's check failed;
  - `check_not_done` - nothing recorded, and the restriction stands.

  **Not-done is not pass.** An athlete who never ran the check is not cleared
  by silence, and `Vitai.pending_checks()` lets a coach say "you have not done
  the hop test today" rather than assuming either outcome. This is the first
  mechanism that can CLEAR a gate from athlete-supplied input, so the
  asymmetry is preserved deliberately: only an explicit pass clears, and only
  for that day.
- **`onset_date` on medical, `occurred_date` on achievements** (#19). The row
  `date` was doing double duty as when-this-was-written and
  when-it-began. Recording a resolved 2025 injury today produced
  `resolved_date 2025-12-01 precedes onset 2026-07-27`, and back-dating the
  row to work around it destroyed the only record of when it was entered -
  which P2 needs (the record is a timeline of what was KNOWN when) and G29
  needs (a condition recorded today that began two years ago should inform
  old weeks). Both dates now exist; onset defaults to the row date, so
  nothing existing moves.
  - `resolved_date` is validated against onset rather than the entry date.
  - The episode window opens at **onset**; head selection still reads `date`,
    because P2's as-of reconstruction is a question about knowledge.

### Changed
- `meta.contract` is **5**: adds the `checks` table, `onset_date`/
  `precondition` on `medical`, `occurred_date` on `achievements`, and
  `status`/`precondition` columns on `gates`. **A consumer reading `gates`
  must now check `status`** - a row with status `cleared` is reported but does
  not block.
- The demo carries a conditional gate whose check passes, fails, and is left
  undone on consecutive days, so all three states render; plus a historical
  episode with an onset two years before its entry date.

Increment 3 - medical layer + SAFETY ESCALATION (G11 + G28). Read-model
contract bumped to **4**.

### Added
- **`medical.jsonl`** (G11): one condition's whole lifecycle under a `slug` -
  onset, visit, restriction, resolution. Carries `severity` that the ENGINE
  reads, `restricts` (which activity classes are gated), `resolved_date`
  (which closes the episode window streak-forgiveness will be computed from),
  and a coarse `provider_type` - which KIND of clinician, never which one.
- **Deterministic severity-to-action (G28)** in `safety.py`. This was the last
  decision outside the P4 firewall: "see a clinician" lived as prose in a
  skill file, where a coach optimising for adherence could reason around it,
  soften it, or never reach it. It is now a branch, and the escalation
  messages are module constants - what an athlete reads in an emergency is
  exactly what was reviewed and tested, not something a model assembled.
  - a symptom CLASS beyond musculoskeletal: pain recorded at `chest` routes
    to a clinician from EITHER dataset, because `chest` is a legitimate
    musculoskeletal site and that is exactly the trap - a coach handed it
    alongside a hip will happily suggest a substitution;
  - ABSOLUTE-danger thresholds judged with no reference to baseline (resting
    heart rate outside 30-120, self-reported pain at 9+). The existing rhr
    tripwire is relative, which is the right tool for fatigue and the wrong
    one for danger: a baseline that drifted upward over months never trips;
  - a **RED-S / low-energy-availability composite** over deficit + rate of
    loss + training load - the syndrome that a tool which coaches deficits
    can itself cause, which is why the engine watches for it rather than the
    athlete;
  - an explicit `severity: red_flag` path, honoured whoever wrote it.
- **Gates as data.** An open episode that restricts an activity class, or
  pain over the configured gate, produces a gate row carrying its own
  escalation text. `Vitai.gated("run")` is a deterministic fact about a date.
- **The fast path.** The weekly cadence is right for coaching and wrong for
  danger. Anything urgent dated today prints at `vitai build` time on stderr,
  before any coaching output exists to bury it, and `vitai safety` exits **2**
  while something urgent stands so a script can ask "safe to train today?"
  without parsing prose.
- **`vitai safety`** plus `Vitai.safety()`, `.urgent()`, `.gates()`,
  `.gated()`, `.episodes()` and `.safety_banner()` (P9 parity).
- **`vitai build --on DATE`** to evaluate gates, escalations and the rollup as
  of a date - which is also what lets the demo render its own live gate.
- The weekly rollup gains a **Gates** section, below tripwires: a tripwire is
  something to discuss, a gate is already decided.
- The **never-shame carve-out is now written down** in the coach skill, with
  its boundaries: it licenses urgency and plainness, never blame; it applies
  only to the gate/escalation tier; the words are the engine's.

### Changed
- `meta.contract` is **4**, adding `medical`, `gates` and `escalations`. A
  consumer that renders training suggestions MUST read `gates` or it will
  propose activity the record has blocked.
- The rollup's pain tripwire reads `pain`/`pain_site` (falling back to the
  retired `hip_pain`) and names the site rather than assuming the hip.
- The CI demo job builds as of the synthetic athlete's last day and asserts
  a live gate renders and a resolved episode does not.

### Deliberately not done
- No diagnosis, ever. Every escalation routes to a human clinician and the
  banner says so.
- Out of scope per the plan: FHIR import, document attachments, medication
  interactions.
- Thresholds are conservative SCREENING bounds, not clinical criteria. The
  resting-heart-rate floor sits below a trained endurance athlete's genuinely
  low rate on purpose - a safety layer that cries wolf at normal athlete
  physiology teaches people to ignore it.

---

Body sites become a curated vocabulary (follow-up to increment 2).

### Added
- **`semantics/body_sites.toml`** - the first curated registry (P5): neither
  data nor code, versioned in-repo, human-mergeable, with its evidence in its
  own comments. About 25 musculoskeletal sites in a two-level
  `region -> site` hierarchy, each with aliases.
- **`pain_side`** (`left | right | bilateral | null`), post-coordinating
  laterality rather than baking it into the site name. This is the HL7 FHIR
  (`BodyStructure.includedStructure.structure` + `.laterality`) and openEHR
  (`CLUSTER.anatomical_location`) pattern - two standards that made the same
  call independently. It also stops the vocabulary doubling.
- **`vitai.anatomy`**: `resolve()` maps what an athlete actually types onto
  the canonical slug ("IT band" and "itb" -> `knee`, "lumbar" -> `lower_back`),
  plus `region_of()`, `is_paired()`, `describe()` and a verified-only
  `osiics_of()`.
- **`docs/prior-art-anatomy.md`** - the sweep behind all of the above, with
  adopt/adapt/avoid calls.

### Changed
- **`pain_site` is now a closed vocabulary** instead of free text, so "knee",
  "Knee", "left knee" and "patella" stop being four unrelated places. Unknown
  sites are rejected with the vocabulary listed; aliases are accepted and
  normalised to the canonical slug at read time.
- A **paired** site with a pain score now requires a side - "my knee hurts"
  does not tell a coach which knee to stop loading - and a **midline** site
  refuses one, because claiming a side there is false precision.
- Legacy `hip_pain` lines still map forward to `pain` at site `hip` and are
  deliberately given **no** side: the old field never recorded which hip, and
  inventing one would manufacture a fact.

### Deliberately not done
- No clinical ontology is vendored. SNOMED CT cannot be redistributed by
  non-Affiliates; UBERON is multi-species and runs to tens of thousands of
  classes. OSIICS (the IOC's sports system, free with acknowledgement) is
  mapped instead - but only the region letters verified from a primary source
  are recorded, and the rest are left blank rather than guessed.
- Pain remains one score at one site per day. Multiple simultaneous sites and
  pain quality (sharp/dull/burning) are not modelled.

## [Unreleased] - increment 2

Increment 2 - provenance, context, feel + RESOLUTION (G1, G3, G4, G7, G15,
G29). Read-model contract bumped to **3**.

### Added
- **The resolution layer (G15) - the conservation golden rule.** A calorie is
  eaten once and burned once. When two sources describe the same day, the
  record holds ONE canonical value per quantity, chosen by precedence, and
  never a sum. Three rules: per-quantity precedence (the watch wins
  `kcal_out` while the food ledger wins `kcal_in`, on the same day);
  activity identity, so one run logged on two platforms is one run, matched
  by intersecting `start_time` intervals or, lacking times, by type plus
  duration/distance tolerance bands; and energy as attribution, not addition
  - a device's daily burn already contains its sessions' energy.
  Primary tables now hold canonical rows; raw claims are projected to
  `claims`, and every adjudication is auditable.
- **Resolution explanations (G29)** as ROUTINE output, not an error channel:
  `vitai resolve` says which source won a contested field and why, every
  time, so "why does the record say 2,443" always has an answer.
- **Conservation tripwires**, flagged and never auto-fixed: sessions
  attributing more energy than the day measured, near-miss duplicate
  sessions that failed the fuzzy match narrowly, and high-precedence sources
  disagreeing beyond tolerance.
- **Claims as JTMS nodes (Doyle 1979) with cascade retraction.** Each
  resolved value carries a justification (`claim_id`, source, tier, quantity
  class). Revoking a justification retracts what stood on it: an inference
  declaring `depends_on` a corrected claim is retracted with it rather than
  left as a stale belief whose evidence no longer exists. The labeled-
  assumption-set and cascade-invalidate rule only - no ATMS engine, and
  confidence remains a property of tier and source, never LLM-assigned.
- **`daily` gen-2 fields**: `source`, `mood`, `feel`, `coverage`, and
  `pain` + `pain_site` generalizing `hip_pain`.
- **`sessions` gen-2 fields**: `source`, `start_time`, `elevation_m`,
  `setting`, `route`, `place`, `with`, `context`, `planned`, `weather`.
- **`measurements.jsonl`** (G16): sparse anchor-class reads that do not come
  off the scale (tape, DEXA, InBody). Anchors top the precedence ladder.
- **`context.jsonl`** (G34): dated situational mode, facilities and place.
  The engine uses it to EXPLAIN missingness rather than flag it - a week
  with no weigh-in while the facilities line says there was no scale is not
  a lapse. `has_facility()` deliberately distinguishes "no scale" from "we
  do not know".
- **`suppressed_metrics`** (G33, the subtractive primitive) and **`nudge_ok`**
  (G7) in `[preferences]`. A suppressed metric keeps being recorded and
  stops being scored: someone recovering from a bad relationship with a
  number can stop being judged on it without deleting their history.
- **`vitai resolve` and `vitai context`**, with `Vitai.resolution()`,
  `.canonical()`, `.explanations()`, `.conservation()`, `.retractions()`
  and `.context()` (P9 parity).

### Changed
- **Migration: `hip_pain` -> `pain` + `pain_site`.** No action required and
  nothing to rewrite. `hip_pain` is retired at generation 2, which means it
  stays legal forever and stops being required: old lines keep validating
  and the engine reads them as pain at site `hip`. A line carrying both
  keeps its explicit `pain`. The same mechanism retires `sessions.location`
  in favour of `place` + `route`.
- **`meta.contract` is 3.** Primary tables changed meaning: they now hold
  canonical rows rather than raw lines. A single-source repo is unaffected -
  where there is nothing to adjudicate, nothing moves, which the
  `test_single_source_resolution_is_byte_identical` regression pins.
- Weekly verdicts read `pain` (falling back to `hip_pain`) and skip any
  metric listed in `suppressed_metrics`.
- The demo athlete gained a mid-block generation switch (so one file holds
  both shapes), a declared travel week whose missing weigh-ins are explained
  by context rather than flagged, a two-source day resolving field-wise, a
  rainy partner walk on a named route, and sparse tape/DEXA measurements.

### Fixed
- **Resolution no longer false-merges repeated similar activities** (#14).
  Shape-matching - same type, similar duration, similar distance - was being
  used as a proxy for identity when `start_time` was absent. For repeated
  activities it is a proxy for ROUTINE instead: a dog walked three times a
  day, a commute each way, sets of the same length. Anyone with a habit
  generates near-identical shapes by design, and the resolver was merging
  them. A real record reported **1.39 km** of walking on a day when **6.26 km
  across four walks** had happened, and nothing surfaced it.

  This is the mirror of double-counting and worse: double-counting inflates a
  number visibly, a false merge silently deletes data and leaves a plausible
  canonical row behind. Three changes:
  - A shape match now also requires **disjoint sources**. A genuine
    cross-platform duplicate has a signature shape does not carry - two
    different systems claiming one physical event. Two claims from the same
    source with the same shape are far more likely to be two real events, and
    an identical re-emission from one connector is a connector bug that
    exact-duplicate detection (G26) already covers.
  - More than two shape-alike, timestamp-less claims of one type on a date is
    a **routine, not a duplicate set** - none are merged.
  - Every shape-only merge, every near miss, and every routine left unmerged
    now emits a **visible tripwire** saying what was decided and that
    recording `start_time` resolves it positively. Previously a merge was
    invisible outside the `claims` table.

  `_same_activity` returns three outcomes rather than two -
  `match | possible | distinct` - so an uncertain pair is a refusal to decide
  rather than a weak merge.
- **RED-S no longer requires the scale to move.** The composite demanded a
  deficit AND rate of loss AND load, all three. That reasoning holds for a
  losing athlete and is wrong for the syndrome: RED-S very commonly presents
  WEIGHT-STABLE, because the body downregulates instead of shedding - resting
  heart rate drifts, periods stop, resting metabolic rate falls. Requiring
  loss made weight stability *exonerating*, when in this syndrome stability is
  frequently the finding itself. Rate of loss is now sufficient but not
  necessary: low **energy availability** + training load + any ONE
  corroborating marker (fast loss, sustained resting-HR drift, menstrual
  function reported absent, bone-stress history) fires.
- **Energy availability is computed properly** - (intake - exercise energy) /
  fat-free mass - which is the measure the syndrome is actually defined by and
  needs no weight trend at all. It is never estimated: with no body-composition
  read the metric is not produced, because a guessed body-fat percentage is a
  manufactured input to a clinical decision.

### Added
- **The prose safety net (G59).** The escalation path only worked for athletes
  who file structured entries. Five exertional chest-pain episodes of
  increasing duration went unseen because every one was written into a
  free-text note and downplayed - which is how frightened people report
  things. A deterministic phrase scan over notes now escalates red-flag
  language wherever it was actually written. It is a net, not a parser: it can
  only ADD an escalation, and it is negation-guarded so "no chest pain" does
  not cry wolf.
- **Absolute intake and protein floors (G68)**, firing with no configuration
  at all - the same pattern as the absolute resting-HR band. The athlete who
  exposed this had configured nothing, as every new user has not, and got
  `tripwires: none` while eating ~1200 kcal a day and losing a kilo a week.
- **The clinical hold tier (G73).** A hold is not a louder message, it is a
  different act: it routes through the gate mechanism, so algorithmic
  progression suspends and the coach is structurally unable to issue training
  advice. Printing a warning and then carrying on prescribing was the failure
  it exists to prevent.
- **Physiological states and medications as modifiers (G57/G72).**
  `medical.jsonl` gains `kind: state` and an `expects` field. A declared state
  (nursing, pregnancy) RAISES the intake floor; a medication that expects
  rapid loss suppresses the rate verdict, which would otherwise tell someone
  whose treatment is working that she is failing a target nobody set for her.
  A modifier may raise a floor or drop a misfiring verdict - it can never
  silence an absolute floor.
- Safety findings now also surface as **verdict rows** (`intake_floor`,
  `protein_floor`, `energy_availability`, `symptom_chest_pain`,
  `symptom_syncope`), because a finding that only exists in a channel nobody
  renders is a finding nobody sees.

### Changed
- **`status` no longer leads with weight** (G62/G64). Weight-first was
  architectural rather than chosen, and it meant an athlete who had explicitly
  refused a weight goal opened every session being told she had failed to
  weigh herself. It now reports what is in the record - steps, or days logged.
- **The rollup gained a Steps section** (G64): fourteen days of phone step
  data, the only real data one athlete's life produces, rendered nowhere.
- **The rate line states its direction in words** (G69). It rendered
  `+1.10 kg/week` to an athlete who had LOST 1.5 kg, because positive means
  losing. For a scale-anxious under-eater that misreading is actively
  dangerous, so it now reads "losing 1.10 kg/week" and the sign is a detail.

## [Unreleased] - increment 3