# Vocabularies: one axis, post-coordinated, grounded, in the registry

The rule, in one line:

> **One axis per vocabulary. Post-coordinate rather than pre-coordinate.
> Ground it in prior art before writing it. Registry, not code.**

This document exists because the same mistake was made ten times and caught
twice. It is G85 in `model.md`; this is the practical form.

## What went wrong

Every closed vocabulary except one was written from **the examples in front of
the author** rather than designed as a taxonomy. The operator's own diagnosis:
*"designing for my examples specifically rather than genericizing first and
capturing more edge cases."*

The evidence was not subtle:

- `SESSION_TYPES` shipped `gym_a` and `gym_b` - one athlete's Strength A and
  Strength B days - in a public MIT engine, while cycling, swimming, rowing,
  hiking, yoga, climbing, skiing and every team and racket sport collapsed to
  `other`.
- `ACTIVITY_CLASSES` mixed a scope quantifier (`all`), a setting (`gym`), a
  loading modality (`impact`), anatomical regions (`upper_body`) and specific
  activities (`run`) in one flat list.
- `CONTEXT_MODES` mixes weather, health, calendar, employment and social.
- `SETTINGS` contains a piece of equipment (`treadmill`) and lacks `gym`,
  which lives in the wrong vocabulary entirely.
- `WEATHERS` cannot say "cold and raining".
- `MEASUREMENT_KINDS` bakes units into value names, so an imperial user cannot
  log at all.

The cost was not cosmetic. Two real clinical gates were **inexpressible**:

| The clinician said | Why the old vocabulary could not say it |
|---|---|
| No loaded lumbar flexion | No value came close |
| No loaded hip work, squats still fine | `lower_body` would have banned the permitted squats |

Both sat in a live record with `restricts: null` and a RESTRICTION NOT
ENFORCEABLE marker, because a **wrong** gate is worse than an unenforced one.
The consequence: an athlete with an active, unassessed injury gate got
`no active safety escalations`.

## Why post-coordination

`body_sites.toml` is the only vocabulary without the defect, and that is not a
coincidence - it is the only one that got a prior-art sweep first (issue #9).
Its lesson was laterality: **name the structure, qualify it separately**. A
knee is a knee; left is a different field. Pre-coordinating `left_knee` would
have doubled the vocabulary and reintroduced the ambiguity it removed.

A restriction is the same shape:

```
pattern=hinge region=hip load=loaded      # no loaded hip work
pattern=flexion region=lower_back load=loaded   # no loaded lumbar flexion
```

An absent axis means "any". A squat is `pattern=squat`, so the hip rule does
not touch it - which is exactly what the clinician said and what one flat list
could never encode.

## Why the registry, not code

**A vocabulary in code can only be extended by a developer, so it can only
ever contain what the developer had seen.** That is the root cause, not a
symptom. `gym_a` is in a public engine because the author had a Strength A
day; swimming was missing because he does not swim.

A registry (`src/vitai/semantics/*.toml`) is versioned, carries its evidence
in its own comments, can retire a value without deleting it, and can grow
without a code change.

**One deliberate limit.** Registries are curated files with generous aliases,
not athlete-writable at runtime. For `session_types` the issue's
athlete-extensible argument is right and the aliases carry it. For
safety-bearing vocabularies it is not: an activity class no rule understands
is an *unenforced gate*, which is the precise harm this work removes. Widening
a safety vocabulary stays a reviewed change; mapping an athlete's words onto
it does not.

## Value retirement

`KEY_RETIREMENT` retires a *key* at a generation. It could not retire a
*value* inside a still-live key, which is what `gym_a` needed. Registries do:

```toml
[retired.gym_a]
maps_to = "strength"
since_gen = 2
reason = "one athlete's programme label (Strength A) in a public engine"
```

The value stays legal forever - an old line carrying it is history, not an
error - stops being offered, and resolves forward.

## The sweep: adopted, adapted, avoided

| Source | Call | Why |
|---|---|---|
| **Compendium of Physical Activities** (Ainsworth et al.) | **Adopt** at major-heading level | 5-digit codes: first two digits a major heading (bicycling, conditioning, running, water activities, sports), last three a specific activity, 600+ total. The major-heading level is right for a three-minute weekly ritual; 605 options is a researcher's problem, not an athlete's. Recorded per type as `compendium` where the mapping is clean, blank where it is not. |
| **Seven fundamental movement patterns** (squat, hinge, lunge, push, pull, carry, rotate) | **Adopt**, extended | The standard strength-coaching taxonomy. Extended with `flexion`, `extension`, `gait`, `jump` and `isometric`, which a rehab restriction actually needs and which the seven do not cover. |
| **`body_sites.toml`** | **Reuse wholesale** | The `region` axis is not redefined. Both its sites (knee, achilles) and its regions (lower_limb, trunk) resolve, with aliases - "lumbar" and "lumbar spine" both give `lower_back`. Inventing a second anatomy would be the same mistake in a new place. |
| **ICF** (WHO) | **Reference the framework, vendor nothing** | ICF is the reference classification for activity limitation and informs the shape of the restriction axes. But WHO licenses ICF **on the same terms as ICD** - free to reference, distribution needs formal permission. This is the SNOMED CT situation from #9 again: map outward, never ship. |
| **SNOMED CT** | **Avoid as content** | Established in #9: non-Affiliates may not distribute its content or derivatives, and this is a public MIT repo anyone may fork. |
| **HL7 FHIR / openEHR post-coordination** | **Adopt the pattern** | Already adopted for laterality in #9; the restriction axes are the same idea applied to movement. |

## The audit, for any new vocabulary

Before a vocabulary ships, from `skills/vitai-validate/SKILL.md`:

1. Does it mix axes? Split it.
2. Would a stranger find their case in it? If a cyclist, a swimmer, a climber
   or a shift worker falls into `other`, it is a sample of the author.
3. Are there personal labels in it? `gym_a` shipped in a public engine.
4. Are units baked into value names? `waist_cm` excludes an imperial user.
5. Is it pre-coordinated where it could post-coordinate?
6. Can the athlete's own words reach it? If only a developer can extend it, it
   can only ever contain what the developer had seen.

## Status

Migrated to registries: **session types** (`session_types.toml`) and
**restrictions** (`restrictions.toml`, five axes).

Still Python sets, with their defects documented above and unfixed:
`CONTEXT_MODES`, `SETTINGS`, `WEATHERS`, `MEASUREMENT_KINDS`,
`SESSION_CONTEXTS`, `PROVIDER_TYPES`, `FEELS`. None of them is safety-bearing,
which is why they queued behind the ones that are. They are the next slice.

Two judgement calls recorded rather than hidden:

- **`severity` keeps `red_flag`.** The issue is right that it mixes a
  magnitude scale with a routing decision. It is also the value the entire
  safety asymmetry rests on, and the ingest skill instructs writing it.
  Splitting it touches the highest-stakes hardcoded path in the codebase and
  deserves its own change, not a side effect of a vocabulary sweep.
- **`restricts` survives as a coarse projection.** `gates.restricts` is a
  read-model column the CLI, the rollup and `is_gated` all split on. The
  structured `restriction` rides alongside it rather than replacing it, so no
  consumer breaks and both questions - "may I run today", "may I do a hip
  thrust today" - have an answer.
